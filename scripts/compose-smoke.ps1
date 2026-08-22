param(
    [string]$ProjectName = "estateops-smoke"
)

$ErrorActionPreference = "Stop"
$required = @(
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_ROOT_PASSWORD",
    "REDIS_PASSWORD",
    "JWT_SECRET_KEY"
)
$missing = $required | Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', ')"
}

docker compose --project-name $ProjectName config --quiet
docker compose --project-name $ProjectName up --build --detach --wait --wait-timeout 240

try {
    $services = docker compose --project-name $ProjectName ps --format json | ConvertFrom-Json
    $unhealthy = @($services | Where-Object {
        $_.Service -ne "migrate" -and $_.State -ne "running"
    })
    if ($unhealthy.Count -gt 0) {
        throw "One or more application services are not running."
    }

    $migrationState = docker compose --project-name $ProjectName ps migrate --format json |
        ConvertFrom-Json
    if ($migrationState.ExitCode -ne 0) {
        throw "The one-shot migration service did not complete successfully."
    }

    docker compose --project-name $ProjectName exec --no-TTY backend `
        python -m app.deployment_checks assert-empty

    $backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
    $frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3000" }
    Invoke-RestMethod -Uri "http://127.0.0.1:$backendPort/health/ready" |
        Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$frontendPort/login" |
        Out-Null
} finally {
    docker compose --project-name $ProjectName down
}
