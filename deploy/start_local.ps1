param([switch]$Rebuild)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$difyCompose = Join-Path (Split-Path $projectRoot -Parent) 'dify-local\docker\compose.local.json'
if (!(Test-Path -LiteralPath $difyCompose)) {
    throw 'Local Dify configuration is missing. See docs/05-local-runbook.md.'
}
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'backend\.env'))) {
    throw 'Backend local configuration is missing. See docs/05-local-runbook.md.'
}

Push-Location $projectRoot
try {
    & docker desktop start --timeout 60
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop did not start.' }
    & docker compose -f $difyCompose up -d
    if ($LASTEXITCODE -ne 0) { throw 'Dify startup failed.' }
    $composeArgs = @('compose', '--env-file', 'backend/.env', '-f', 'deploy/compose.yaml', '--profile', 'demo', '--profile', 'web', 'up', '-d')
    if ($Rebuild) { $composeArgs += '--build' }
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Recruiter startup failed.' }
    $ready = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        try {
            $null = Invoke-WebRequest -Uri 'http://localhost:8000/health/ready' -UseBasicParsing -TimeoutSec 5
            $null = Invoke-WebRequest -Uri 'http://localhost:8080/signin' -UseBasicParsing -TimeoutSec 5
            $ready = $true
            break
        } catch { Start-Sleep -Seconds 2 }
    }
    if (!$ready) { throw 'Services started but readiness checks did not pass.' }
    Write-Host 'HR:        http://localhost:5173'
    Write-Host 'Business:  http://localhost:5174'
    Write-Host 'Candidate: http://localhost:5175 (requires HR-issued link)'
    Write-Host 'Dify:      http://localhost:8080'
    Write-Host 'Local services are ready. Login credentials remain in backend/.env and backend/.env.dify-local.'
} finally { Pop-Location }
