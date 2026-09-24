[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runDir = Join-Path $projectRoot "data\run"
$logDir = Join-Path $projectRoot "data\logs"
$python = Join-Path $projectRoot ".conda\python.exe"
$frontendServer = Join-Path $projectRoot "dist\standalone\server.js"
$node = (Get-Command node -ErrorAction Stop).Source

New-Item -ItemType Directory -Force -Path $runDir, $logDir | Out-Null

$backendPort = 8001
$frontendPort = 3001

foreach ($port in $frontendPort, $backendPort) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $port is already in use by PID $($listener.OwningProcess)."
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend Python runtime not found: $python"
}
if (-not (Test-Path -LiteralPath $frontendServer)) {
    throw "Frontend production bundle not found: $frontendServer. Run npm run build first."
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".env.local"))) {
    throw ".env.local is missing."
}

$backend = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $backendPort) `
    -WorkingDirectory (Join-Path $projectRoot "backend") `
    -RedirectStandardOutput (Join-Path $logDir "backend.out.log") `
    -RedirectStandardError (Join-Path $logDir "backend.err.log") `
    -WindowStyle Hidden `
    -PassThru

$previousHostname = $env:HOSTNAME
$previousPort = $env:PORT
try {
    $env:HOSTNAME = "127.0.0.1"
    $env:PORT = "$frontendPort"
    $frontend = Start-Process `
        -FilePath $node `
        -ArgumentList @($frontendServer) `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") `
        -RedirectStandardError (Join-Path $logDir "frontend.err.log") `
        -WindowStyle Hidden `
        -PassThru
}
finally {
    $env:HOSTNAME = $previousHostname
    $env:PORT = $previousPort
}

Set-Content -LiteralPath (Join-Path $runDir "backend.pid") -Value $backend.Id -Encoding ascii
Set-Content -LiteralPath (Join-Path $runDir "frontend.pid") -Value $frontend.Id -Encoding ascii

$backendReady = $false
$frontendReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (-not $backendReady) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$backendPort/api/health" -TimeoutSec 2
            $backendReady = $health.status -eq "ok"
        }
        catch {}
    }
    if (-not $frontendReady) {
        try {
            $page = Invoke-WebRequest -Uri "http://127.0.0.1:$frontendPort" -UseBasicParsing -TimeoutSec 2
            $frontendReady = $page.StatusCode -eq 200
        }
        catch {}
    }
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Milliseconds 500
}

if (-not ($backendReady -and $frontendReady)) {
    foreach ($process in $backend, $frontend) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    throw "Local services did not become ready. Check data/logs/*.log."
}

[ordered]@{
    frontend_url = "http://127.0.0.1:$frontendPort"
    backend_url = "http://127.0.0.1:$backendPort"
    api_docs_url = "http://127.0.0.1:$backendPort/docs"
    backend_pid = $backend.Id
    frontend_pid = $frontend.Id
    database = $health.database
    log_directory = $logDir
} | ConvertTo-Json
