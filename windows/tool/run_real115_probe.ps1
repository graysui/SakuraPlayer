[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ([Environment]::GetEnvironmentVariable('SAKURAPLAYER_TEST_REAL115') -ne '1') {
    throw 'Set SAKURAPLAYER_TEST_REAL115=1 to run the explicit real 115 probe.'
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

$windowsRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $windowsRoot
try {
    flutter test integration_test/real115_probe_test.dart -d windows
    if ($LASTEXITCODE -ne 0) {
        throw 'The explicit real 115 probe failed.'
    }
}
finally {
    Pop-Location
}
