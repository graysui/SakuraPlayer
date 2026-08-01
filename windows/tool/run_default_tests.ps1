[CmdletBinding()]
param(
    [switch]$SkipBackendAlgorithms,
    [switch]$SkipWindowsIntegration
)

$ErrorActionPreference = 'Stop'
$windowsRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$repositoryRoot = Split-Path $windowsRoot -Parent

function Invoke-CheckedCommand {
    param([scriptblock]$Command, [string]$FailureMessage)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

if (-not $SkipBackendAlgorithms) {
    $algorithmTests = @(
        'tests/unit/resources/test_avdb_crypto.py',
        'tests/unit/resources/test_number_normalizer.py',
        'tests/unit/resources/test_source_labels.py',
        'tests/unit/resources/test_sync_service.py',
        'tests/unit/catalog/test_core_import.py',
        'tests/unit/catalog/test_metadata_priority.py',
        'tests/unit/worker/test_metadata_supervisor.py',
        'tests/unit/cloud_cache/test_cache_state.py',
        'tests/unit/cloud_cache/test_safe_cleanup.py',
        'tests/unit/playback/test_signature.py',
        'tests/unit/playback/test_completion_rule.py',
        'tests/unit/playback/test_progress_service.py',
        'tests/unit/playback/test_subtitle_options.py'
    )
    & docker image inspect sakuraplayer-test *> $null
    if ($LASTEXITCODE -ne 0) {
        Push-Location $repositoryRoot
        try {
            Invoke-CheckedCommand {
                docker build -f backend/docker/api.Dockerfile --target test -t sakuraplayer-test .
            } 'Unable to build the locked Python 3.10.16 test image.'
        }
        finally {
            Pop-Location
        }
    }
    Invoke-CheckedCommand {
        docker run --rm `
            --mount "type=bind,source=$repositoryRoot,target=/workspace,readonly" `
            --workdir /workspace/backend `
            --entrypoint python `
            sakuraplayer-test `
            -m pytest @algorithmTests -q -p no:cacheprovider
    } 'Backend AC-129 algorithm tests failed.'
}

Push-Location $windowsRoot
try {
    Invoke-CheckedCommand { flutter analyze } 'Flutter analyze failed.'
    Invoke-CheckedCommand { flutter test } 'Flutter unit/widget tests failed.'
    if (-not $SkipWindowsIntegration) {
        Invoke-CheckedCommand {
            flutter test integration_test/fake_backend_flow_test.dart -d windows
        } 'Offline Windows integration test failed.'
        Invoke-CheckedCommand {
            flutter test integration_test/windows_user_journey_test.dart -d windows
        } 'Offline Windows user journey failed.'
    }
}
finally {
    Pop-Location
}

Write-Host 'Default offline acceptance tests passed.'
