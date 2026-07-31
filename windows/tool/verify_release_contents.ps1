[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath
)

$ErrorActionPreference = 'Stop'
$bundle = [System.IO.Path]::GetFullPath($BundlePath)
if (-not (Test-Path -LiteralPath $bundle -PathType Container)) {
    throw "Release bundle does not exist: $bundle"
}

$requiredFiles = @(
    'sakuraplayer_windows.exe',
    'flutter_windows.dll',
    'libmpv-2.dll',
    'data/app.so',
    'data/icudtl.dat',
    'data/flutter_assets/NOTICES.Z',
    'BUILD_INFO.txt',
    'LICENSE',
    'THIRD_PARTY_NOTICES.md',
    'PROJECT_THIRD_PARTY_NOTICES.md',
    'Install-SakuraPlayer.ps1',
    'Uninstall-SakuraPlayer.ps1',
    'SHA256SUMS.txt'
)

foreach ($relativePath in $requiredFiles) {
    $nativePath = $relativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath (Join-Path $bundle $nativePath) -PathType Leaf)) {
        throw "Required release artifact is missing: $relativePath"
    }
}

$forbiddenExtensions = @('.pdb', '.ilk', '.exp', '.lib', '.pfx', '.pem', '.key')
$forbiddenNames = @('.env', '.env.local', 'debug.log')
$files = @(Get-ChildItem -LiteralPath $bundle -Recurse -File)
foreach ($file in $files) {
    if ($forbiddenExtensions -contains $file.Extension.ToLowerInvariant()) {
        throw "Forbidden release artifact: $($file.Name)"
    }
    if ($forbiddenNames -contains $file.Name.ToLowerInvariant()) {
        throw "Forbidden release artifact: $($file.Name)"
    }
}

foreach ($platform in @('android', 'ios', 'linux', 'macos', 'web')) {
    if (Test-Path -LiteralPath (Join-Path $bundle $platform)) {
        throw "Unexpected platform directory in Windows release: $platform"
    }
}

$manifestPath = Join-Path $bundle 'SHA256SUMS.txt'
$manifestLines = @(Get-Content -LiteralPath $manifestPath | Where-Object { $_.Trim().Length -gt 0 })
$expectedPaths = @{}
foreach ($file in $files) {
    if ($file.FullName -eq $manifestPath) {
        continue
    }
    $relative = $file.FullName.Substring($bundle.Length).TrimStart('\', '/').Replace('\', '/')
    $expectedPaths[$relative] = $file.FullName
}

$seenPaths = @{}
foreach ($line in $manifestLines) {
    if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') {
        throw 'SHA256SUMS.txt contains an invalid line.'
    }
    $expectedHash = $Matches[1].ToUpperInvariant()
    $relative = $Matches[2].Replace('\', '/')
    if ($relative.StartsWith('/') -or $relative.Contains('../') -or -not $expectedPaths.ContainsKey($relative)) {
        throw "SHA256SUMS.txt references an unsafe or unknown path: $relative"
    }
    if ($seenPaths.ContainsKey($relative)) {
        throw "SHA256SUMS.txt contains a duplicate path: $relative"
    }
    $actualHash = (Get-FileHash -LiteralPath $expectedPaths[$relative] -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "Release hash mismatch: $relative"
    }
    $seenPaths[$relative] = $true
}

if ($seenPaths.Count -ne $expectedPaths.Count) {
    $missing = @($expectedPaths.Keys | Where-Object { -not $seenPaths.ContainsKey($_) } | Sort-Object)
    throw "SHA256SUMS.txt is incomplete: $($missing -join ', ')"
}

Write-Host "Verified SakuraPlayer release bundle ($($files.Count) files)."
