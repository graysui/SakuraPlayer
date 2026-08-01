[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ([Environment]::GetEnvironmentVariable('SAKURAPLAYER_TEST_REAL115') -ne '1') {
    throw 'Set SAKURAPLAYER_TEST_REAL115=1 to run the explicit TASK-213 real 115 acceptance gate.'
}

$requiredVariables = @(
    'SAKURAPLAYER_REAL115_API_BASE_URL',
    'SAKURAPLAYER_REAL115_USERNAME',
    'SAKURAPLAYER_REAL115_PASSWORD',
    'SAKURAPLAYER_REAL115_MOVIE_ID',
    'SAKURAPLAYER_REAL115_SOURCE_ID',
    'SAKURAPLAYER_REAL115_CONFIRM_MANAGED_ROOT'
)
foreach ($name in $requiredVariables) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Required local environment variable is missing: $name"
    }
}
if ([Environment]::GetEnvironmentVariable('SAKURAPLAYER_REAL115_CONFIRM_MANAGED_ROOT') -ne '1') {
    throw 'Confirm the sample uses the application-managed real115 test root.'
}
$skipExternalSubtitles = [Environment]::GetEnvironmentVariable(
    'SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES'
)
if (
    -not [string]::IsNullOrWhiteSpace($skipExternalSubtitles) -and
    $skipExternalSubtitles -ne '1'
) {
    throw 'SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES only accepts 1 when operator-approved.'
}

$windowsRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $windowsRoot
try {
    flutter build windows --release
    if ($LASTEXITCODE -ne 0) {
        throw 'TASK-213 private release build failed.'
    }
    $driveLines = @()
    & flutter drive `
        --profile `
        --driver=test_driver/integration_test.dart `
        --target=integration_test/windows_real115_e2e_test.dart `
        -d windows 2>&1 | Tee-Object -Variable driveLines
    $driveExitCode = $LASTEXITCODE
    $driveText = $driveLines -join [Environment]::NewLine
    if (
        $driveExitCode -ne 0 -or
        $driveText -notmatch 'All tests passed!' -or
        $driveText -match 'Some tests failed|\[E\]'
    ) {
        throw 'TASK-213 real 115 profile acceptance failed.'
    }
}
finally {
    Pop-Location
}
