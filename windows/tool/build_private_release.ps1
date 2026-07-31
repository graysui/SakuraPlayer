[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$CertificateThumbprint,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot 'dist'
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$releaseRoot = Join-Path $projectRoot 'build\windows\x64\runner\Release'
$stagingRoot = Join-Path $projectRoot 'build\private-release-stage'
$bundleRoot = Join-Path $stagingRoot 'SakuraPlayer'

function Invoke-CheckedCommand {
    param([scriptblock]$Command, [string]$FailureMessage)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

if (-not $SkipBuild) {
    Push-Location $projectRoot
    try {
        Invoke-CheckedCommand { flutter build windows --release } 'Flutter Windows release build failed.'
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $releaseRoot -PathType Container)) {
    throw 'Windows release output is missing. Run without -SkipBuild first.'
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
if (Test-Path -LiteralPath $stagingRoot) {
    $expectedStage = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build\private-release-stage'))
    if ([System.IO.Path]::GetFullPath($stagingRoot) -ne $expectedStage) {
        throw 'Refusing to clean an unexpected staging directory.'
    }
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null

try {
    Copy-Item -Path (Join-Path $releaseRoot '*') -Destination $bundleRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE') -Destination $bundleRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination $bundleRoot
    Copy-Item -LiteralPath (Join-Path (Split-Path $projectRoot -Parent) 'THIRD_PARTY_NOTICES.md') `
        -Destination (Join-Path $bundleRoot 'PROJECT_THIRD_PARTY_NOTICES.md')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'package\Install-SakuraPlayer.ps1') -Destination $bundleRoot
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'package\Uninstall-SakuraPlayer.ps1') -Destination $bundleRoot

    $versionLine = Select-String -LiteralPath (Join-Path $projectRoot 'pubspec.yaml') -Pattern '^version:\s*(.+)$'
    if ($null -eq $versionLine) {
        throw 'pubspec.yaml does not contain a version.'
    }
    $version = $versionLine.Matches[0].Groups[1].Value.Trim()
    $safeVersion = $version.Replace('+', '-')
    $commit = (git -C (Split-Path $projectRoot -Parent) rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') {
        throw 'Unable to resolve the source Git commit.'
    }
    git -C (Split-Path $projectRoot -Parent) diff --quiet HEAD -- `
        windows docs/specs/001-sakuraplayer-v1/contracts/runtime-configuration.md
    $sourceState = switch ($LASTEXITCODE) {
        0 { 'clean' }
        1 { 'modified' }
        default { throw 'Unable to determine the tracked source tree state.' }
    }
    @(
        'SakuraPlayer private Windows release',
        "Version: $version",
        "Source commit: $commit",
        "Source tree: $sourceState",
        'License: GPL-3.0-only',
        "Authenticode: $(if ([string]::IsNullOrWhiteSpace($CertificateThumbprint)) { 'unsigned' } else { 'signed' })",
        'Install: run Install-SakuraPlayer.ps1 as the target desktop user.'
    ) | Set-Content -LiteralPath (Join-Path $bundleRoot 'BUILD_INFO.txt') -Encoding UTF8

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
        foreach ($target in @(
            (Join-Path $bundleRoot 'sakuraplayer_windows.exe'),
            (Join-Path $bundleRoot 'Install-SakuraPlayer.ps1'),
            (Join-Path $bundleRoot 'Uninstall-SakuraPlayer.ps1')
        )) {
            $signature = Set-AuthenticodeSignature -LiteralPath $target -Certificate $certificate -HashAlgorithm SHA256
            if ($signature.Status -ne 'Valid') {
                throw "Authenticode signing failed for $([System.IO.Path]::GetFileName($target))."
            }
        }
    }

    $manifestPath = Join-Path $bundleRoot 'SHA256SUMS.txt'
    $hashLines = foreach ($file in Get-ChildItem -LiteralPath $bundleRoot -Recurse -File | Sort-Object FullName) {
        if ($file.FullName -eq $manifestPath) {
            continue
        }
        $relative = $file.FullName.Substring($bundleRoot.Length).TrimStart('\', '/').Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
    $hashLines | Set-Content -LiteralPath $manifestPath -Encoding ASCII

    & (Join-Path $PSScriptRoot 'verify_release_contents.ps1') -BundlePath $bundleRoot

    $archivePath = Join-Path $outputRoot "SakuraPlayer-Windows-$safeVersion.zip"
    $archiveHashPath = "$archivePath.sha256"
    foreach ($oldOutput in @($archivePath, $archiveHashPath)) {
        if (Test-Path -LiteralPath $oldOutput) {
            Remove-Item -LiteralPath $oldOutput -Force
        }
    }
    Compress-Archive -LiteralPath $bundleRoot -DestinationPath $archivePath -CompressionLevel Optimal
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    "$archiveHash  $([System.IO.Path]::GetFileName($archivePath))" |
        Set-Content -LiteralPath $archiveHashPath -Encoding ASCII

    Write-Host "Private release: $archivePath"
    Write-Host "SHA-256 manifest: $archiveHashPath"
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
