[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:LOCALAPPDATA 'Programs\SakuraPlayer'),
    [switch]$DesktopShortcut
)

$ErrorActionPreference = 'Stop'
$packageRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$destinationRoot = [System.IO.Path]::GetFullPath($Destination)
$programsRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs'))
$programsPrefix = $programsRoot.TrimEnd('\') + [System.IO.Path]::DirectorySeparatorChar
if (-not $destinationRoot.StartsWith($programsPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a dedicated installation directory under the current user Programs directory.'
}
$packagePrefix = $packageRoot.TrimEnd('\') + [System.IO.Path]::DirectorySeparatorChar
if ($destinationRoot -eq $packageRoot -or
    $destinationRoot.StartsWith($packagePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The installation directory must not be inside the extracted package.'
}

$manifest = Join-Path $packageRoot 'SHA256SUMS.txt'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    throw 'SHA256SUMS.txt is missing.'
}
foreach ($line in Get-Content -LiteralPath $manifest) {
    if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') {
        throw 'SHA256SUMS.txt contains an invalid line.'
    }
    $relative = $Matches[2].Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    if ([System.IO.Path]::IsPathRooted($relative) -or $relative.Contains('..')) {
        throw 'SHA256SUMS.txt contains an unsafe path.'
    }
    $source = Join-Path $packageRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Package file is missing: $relative"
    }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $Matches[1].ToUpperInvariant()) {
        throw "Package hash mismatch: $relative"
    }
}

New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null
Copy-Item -Path (Join-Path $packageRoot '*') -Destination $destinationRoot -Recurse -Force

$shell = New-Object -ComObject WScript.Shell
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SakuraPlayer.lnk'
$shortcut = $shell.CreateShortcut($startMenu)
$shortcut.TargetPath = Join-Path $destinationRoot 'sakuraplayer_windows.exe'
$shortcut.WorkingDirectory = $destinationRoot
$shortcut.Save()
if ($DesktopShortcut) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $desktopLink = $shell.CreateShortcut((Join-Path $desktop 'SakuraPlayer.lnk'))
    $desktopLink.TargetPath = Join-Path $destinationRoot 'sakuraplayer_windows.exe'
    $desktopLink.WorkingDirectory = $destinationRoot
    $desktopLink.Save()
}

Write-Host "SakuraPlayer installed to $destinationRoot"
