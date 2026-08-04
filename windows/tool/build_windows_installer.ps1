[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$InnoSetupPath,
    [string]$CertificateThumbprint,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot 'dist'
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$archiveRoot = Join-Path $projectRoot 'dist'
$stagingRoot = Join-Path $projectRoot 'build\private-installer-stage'
$bundleRoot = Join-Path $stagingRoot 'SakuraPlayer'
$versionLine = Select-String -LiteralPath (Join-Path $projectRoot 'pubspec.yaml') -Pattern '^version:\s*(.+)$'
if ($null -eq $versionLine) {
    throw 'pubspec.yaml does not contain a version.'
}
$version = $versionLine.Matches[0].Groups[1].Value.Trim()
if ($version -notmatch '^(?<semver>(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))\+(?<build>[1-9]\d*)$') {
    throw 'pubspec version must use canonical X.Y.Z+B syntax.'
}
$semver = $Matches['semver']
$artifactVersion = "$semver-$($Matches['build'])"
$archiveName = "SakuraPlayer-Windows-$artifactVersion.zip"
$installerName = "SakuraPlayer-Windows-$artifactVersion-Setup.exe"
$archivePath = Join-Path $archiveRoot $archiveName
$installerPath = Join-Path $outputRoot $installerName
$installerHashPath = "$installerPath.sha256"

function Invoke-CheckedCommand {
    param([scriptblock]$Command, [string]$FailureMessage)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build_private_release.ps1') -OutputDirectory $archiveRoot
}
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    throw "Private release archive is missing: $archivePath"
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
if (Test-Path -LiteralPath $stagingRoot) {
    $expectedStage = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\private-installer-stage'))
    if ([System.IO.Path]::GetFullPath($stagingRoot) -ne $expectedStage) {
        throw 'Refusing to clean an unexpected installer staging directory.'
    }
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null

try {
    Expand-Archive -LiteralPath $archivePath -DestinationPath $stagingRoot -Force
    if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot 'sakuraplayer_windows.exe') -PathType Leaf)) {
        throw 'Expanded private release does not contain the application executable.'
    }
    & (Join-Path $PSScriptRoot 'verify_release_contents.ps1') -BundlePath $bundleRoot

    if ([string]::IsNullOrWhiteSpace($InnoSetupPath)) {
        $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            throw 'ISCC.exe was not found. Install the pinned Inno Setup toolchain first.'
        }
        $InnoSetupPath = $command.Source
    }
    $InnoSetupPath = [System.IO.Path]::GetFullPath($InnoSetupPath)
    if (-not (Test-Path -LiteralPath $InnoSetupPath -PathType Leaf)) {
        throw "Inno Setup compiler is missing: $InnoSetupPath"
    }
    foreach ($oldOutput in @($installerPath, $installerHashPath)) {
        if (Test-Path -LiteralPath $oldOutput) {
            Remove-Item -LiteralPath $oldOutput -Force
        }
    }

    $issPath = Join-Path $PSScriptRoot 'package\SakuraPlayer.iss'
    $isccArgs = @(
        '/Qp',
        "/DAppVersion=$semver",
        "/DSourceDir=$bundleRoot",
        "/O$outputRoot",
        "/F$($installerName -replace '\.exe$', '')",
        $issPath
    )
    Invoke-CheckedCommand { & $InnoSetupPath @isccArgs } 'Inno Setup installer build failed.'
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
        throw "Installer output is missing: $installerPath"
    }
    if (-not [string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
        $normalizedThumbprint = $CertificateThumbprint.Replace(' ', '').ToUpperInvariant()
        if ($normalizedThumbprint -notmatch '^[0-9A-F]{40}$') {
            throw 'CertificateThumbprint must be a 40-character SHA-1 thumbprint.'
        }
        $certificate = Get-ChildItem Cert:\CurrentUser\My | Where-Object {
            $_.Thumbprint -eq $normalizedThumbprint -and $_.HasPrivateKey
        } | Select-Object -First 1
        if ($null -eq $certificate) {
            throw 'The requested CurrentUser code-signing certificate was not found.'
        }
        $signature = Set-AuthenticodeSignature -LiteralPath $installerPath -Certificate $certificate -HashAlgorithm SHA256
        if ($signature.Status -ne 'Valid') {
            throw 'Authenticode signing failed for the Windows installer.'
        }
    }
    $installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    "$installerHash  $installerName" | Set-Content -LiteralPath $installerHashPath -Encoding ASCII
    Write-Host "Windows installer: $installerPath"
    Write-Host "SHA-256: $installerHashPath"
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
