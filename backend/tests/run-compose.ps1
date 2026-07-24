[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$backendRoot = Join-Path $repoRoot 'backend'
$composeFile = Join-Path $backendRoot 'docker-compose.yml'
$projectName = "sakuraplayer-task001-$PID"
$testImage = "$projectName-test"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) $projectName
$envFile = Join-Path $tempRoot 'compose.env'

function New-RandomBytes([int] $Length) {
    $bytes = [byte[]]::new($Length)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return $bytes
}

function ConvertTo-Base64Url([byte[]] $Value) {
    return [Convert]::ToBase64String($Value).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Invoke-Compose([Parameter(ValueFromRemainingArguments)] [string[]] $Arguments) {
    & docker compose --env-file $envFile -f $composeFile -p $projectName @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed: $($Arguments -join ' ')"
    }
}

function Assert-Healthy([string] $Service) {
    $containerId = (& docker compose --env-file $envFile -f $composeFile -p $projectName ps -q $Service).Trim()
    if (-not $containerId) {
        throw "$Service container was not created"
    }
    $health = (& docker inspect --format '{{.State.Health.Status}}' $containerId).Trim()
    if ($health -ne 'healthy') {
        throw "$Service is not healthy: $health"
    }
}

function Get-ComponentLog([string] $Service) {
    $content = @(
        & docker compose --env-file $envFile -f $composeFile -p $projectName `
            exec -T $Service cat "/var/log/sakuraplayer/$Service.log"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "failed to read the persistent $Service log"
    }
    return $content -join "`n"
}

function Assert-SafeComponentLog(
    [string] $Service,
    [string] $Content,
    [Collections.IEnumerable] $SensitiveValues
) {
    if (-not $Content.Contains("component=$Service component_started")) {
        throw "$Service persistent log has no startup record"
    }
    foreach ($value in $SensitiveValues) {
        if ($Content.Contains([string] $value)) {
            throw "$Service persistent log contains sensitive material"
        }
    }
    if ($Content.Contains('postgresql+psycopg://')) {
        throw "$Service persistent log contains a database URL"
    }
}

function Assert-NoProjectResources {
    $containers = @(& docker ps -a --quiet --filter "label=com.docker.compose.project=$projectName")
    if ($LASTEXITCODE -ne 0) { throw 'failed to inspect project containers' }

    $networks = @(& docker network ls --quiet --filter "label=com.docker.compose.project=$projectName")
    if ($LASTEXITCODE -ne 0) { throw 'failed to inspect project networks' }

    $volumes = @(& docker volume ls --quiet --filter "label=com.docker.compose.project=$projectName")
    if ($LASTEXITCODE -ne 0) { throw 'failed to inspect project volumes' }

    $composeImages = @(& docker image ls --quiet --filter "label=com.docker.compose.project=$projectName")
    if ($LASTEXITCODE -ne 0) { throw 'failed to inspect project images' }

    $testImages = @(& docker image ls --quiet --filter "reference=$testImage")
    if ($LASTEXITCODE -ne 0) { throw 'failed to inspect the test image' }

    $remaining = @(
        if ($containers.Count -gt 0) { "containers=$($containers -join ',')" }
        if ($networks.Count -gt 0) { "networks=$($networks -join ',')" }
        if ($volumes.Count -gt 0) { "volumes=$($volumes -join ',')" }
        if ($composeImages.Count -gt 0) { "composeImages=$($composeImages -join ',')" }
        if ($testImages.Count -gt 0) { "testImages=$($testImages -join ',')" }
    )
    if ($remaining.Count -gt 0) {
        throw "Docker resources remain for ${projectName}: $($remaining -join '; ')"
    }
}

$envFileReady = $false
$locationPushed = $false
try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    $postgresPassword = "task001@:/%$(ConvertTo-Base64Url (New-RandomBytes 24))"
    $secretValues = @{
        'postgres_password.txt' = $postgresPassword
        'settings_key.txt' = ConvertTo-Base64Url (New-RandomBytes 32)
        'token_key.txt' = ConvertTo-Base64Url (New-RandomBytes 48)
        'playback_key.txt' = ConvertTo-Base64Url (New-RandomBytes 48)
        'bootstrap_token.txt' = ConvertTo-Base64Url (New-RandomBytes 48)
    }

    foreach ($entry in $secretValues.GetEnumerator()) {
        [IO.File]::WriteAllText((Join-Path $tempRoot $entry.Key), $entry.Value)
    }

    $path = { param($Name) (Join-Path $tempRoot $Name).Replace('\', '/') }
    $envLines = @(
        'SAKURAPLAYER_ENV=production-private'
        'SAKURAPLAYER_DATABASE_URL='
        'SAKURAPLAYER_PUBLISH_HOST=127.0.0.1'
        'SAKURAPLAYER_API_PORT=0'
        "SAKURAPLAYER_POSTGRES_PASSWORD_SECRET_FILE=$(& $path 'postgres_password.txt')"
        "SAKURAPLAYER_SETTINGS_KEY_SECRET_FILE=$(& $path 'settings_key.txt')"
        "SAKURAPLAYER_TOKEN_KEY_SECRET_FILE=$(& $path 'token_key.txt')"
        "SAKURAPLAYER_PLAYBACK_KEY_SECRET_FILE=$(& $path 'playback_key.txt')"
        "SAKURAPLAYER_BOOTSTRAP_TOKEN_SECRET_FILE=$(& $path 'bootstrap_token.txt')"
    )
    [IO.File]::WriteAllLines($envFile, $envLines)
    $envFileReady = $true

    Push-Location $repoRoot
    $locationPushed = $true
    Invoke-Compose config --quiet

    & docker build -f backend/docker/api.Dockerfile --target test -t $testImage .
    if ($LASTEXITCODE -ne 0) { throw 'test image build failed' }

    & docker run --rm --entrypoint python $testImage -m pytest tests/start -m 'not host_docker' -q
    if ($LASTEXITCODE -ne 0) { throw 'self-contained tests failed' }

    & python backend/tests/start/test_docker_entrypoint.py
    if ($LASTEXITCODE -ne 0) { throw 'host Docker assertions failed' }

    Invoke-Compose up -d --build --wait --wait-timeout 120
    foreach ($service in @('api', 'worker', 'scheduler', 'postgres')) {
        Assert-Healthy $service
    }

    $migrateId = (& docker compose --env-file $envFile -f $composeFile -p $projectName ps -a -q migrate).Trim()
    $migrateExit = (& docker inspect --format '{{.State.ExitCode}}' $migrateId).Trim()
    if ($migrateExit -ne '0') { throw "migrate exited with $migrateExit" }

    $sensitiveLogValues = @($secretValues.Values)
    $sensitiveLogValues += @(
        $secretValues.Values | ForEach-Object { [Uri]::EscapeDataString($_) }
    )
    $logLineCounts = @{}
    foreach ($service in @('api', 'worker', 'scheduler')) {
        $content = Get-ComponentLog $service
        Assert-SafeComponentLog $service $content $sensitiveLogValues
        $logLineCounts[$service] = ($content -split "`n").Count
    }

    $env:SAKURAPLAYER_TEST_DATABASE_URL = 'postgresql+psycopg://sakuraplayer@postgres:5432/postgres'
    $env:SAKURAPLAYER_TEST_DATABASE_PASSWORD = $postgresPassword
    & docker run --rm --network "${projectName}_default" -e SAKURAPLAYER_TEST_DATABASE_URL -e SAKURAPLAYER_TEST_DATABASE_PASSWORD --entrypoint python $testImage -m pytest tests/integration/start -q
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL integration tests failed' }

    Invoke-Compose restart
    Invoke-Compose up -d --wait --wait-timeout 120
    foreach ($service in @('api', 'worker', 'scheduler', 'postgres')) {
        Assert-Healthy $service
    }
    foreach ($service in @('api', 'worker', 'scheduler')) {
        $content = Get-ComponentLog $service
        Assert-SafeComponentLog $service $content $sensitiveLogValues
        if (($content -split "`n").Count -le $logLineCounts[$service]) {
            throw "$service persistent log did not survive and grow after restart"
        }
    }

    $apiAddress = (& docker compose --env-file $envFile -f $composeFile -p $projectName port api 8000).Trim()
    Invoke-Compose stop postgres
    $status = (& curl.exe -s -o NUL -w '%{http_code}' "http://$apiAddress/health/ready").Trim()
    if ($status -ne '503') { throw "ready returned $status while PostgreSQL was stopped" }

    Invoke-Compose up -d --wait --wait-timeout 120
    foreach ($service in @('api', 'worker', 'scheduler', 'postgres')) {
        Assert-Healthy $service
    }
}
finally {
    Remove-Item Env:SAKURAPLAYER_TEST_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:SAKURAPLAYER_TEST_DATABASE_PASSWORD -ErrorAction SilentlyContinue
    $cleanupFailures = [Collections.Generic.List[string]]::new()
    if ($envFileReady) {
        try {
            Invoke-Compose down --volumes --remove-orphans --rmi local
        }
        catch {
            $cleanupFailures.Add($_.Exception.Message)
        }
        try {
            $testImageIds = @(& docker image ls --quiet --filter "reference=$testImage")
            if ($LASTEXITCODE -ne 0) { throw 'failed to inspect the test image before removal' }
            if ($testImageIds.Count -gt 0) {
                & docker image rm $testImage
                if ($LASTEXITCODE -ne 0) { throw "failed to remove test image $testImage" }
            }
        }
        catch {
            $cleanupFailures.Add($_.Exception.Message)
        }
        try {
            Assert-NoProjectResources
        }
        catch {
            $cleanupFailures.Add($_.Exception.Message)
        }
    }
    if ($locationPushed) { Pop-Location }
    try {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction Stop
        }
        if (Test-Path -LiteralPath $tempRoot) {
            throw 'temporary secret directory still exists after removal'
        }
    }
    catch {
        $cleanupFailures.Add(
            "failed to remove the temporary secret directory: $($_.Exception.Message)"
        )
    }
    if ($cleanupFailures.Count -gt 0) {
        throw "Compose cleanup failed: $($cleanupFailures -join '; ')"
    }
}
