[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:LOCALAPPDATA 'Programs\SakuraPlayer')
)

$ErrorActionPreference = 'Stop'
$destinationRoot = [System.IO.Path]::GetFullPath($Destination)
$programsRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs'))
$programsPrefix = $programsRoot.TrimEnd('\') + [System.IO.Path]::DirectorySeparatorChar
if (-not $destinationRoot.StartsWith($programsPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to remove a directory outside the current user Programs directory.'
}
if (-not (Test-Path -LiteralPath (Join-Path $destinationRoot 'sakuraplayer_windows.exe') -PathType Leaf)) {
    throw 'Refusing to remove a directory that is not a SakuraPlayer installation.'
}

foreach ($shortcut in @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SakuraPlayer.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SakuraPlayer.lnk')
)) {
    if (Test-Path -LiteralPath $shortcut -PathType Leaf) {
        Remove-Item -LiteralPath $shortcut -Force
    }
}
Remove-Item -LiteralPath $destinationRoot -Recurse -Force
Write-Host 'SakuraPlayer was uninstalled. Private user data was preserved.'
