[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runDir = Join-Path $projectRoot "data\run"
$stopped = @()

foreach ($service in "backend", "frontend") {
    $pidFile = Join-Path $runDir "$service.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }

    $servicePid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
    $process = Get-Process -Id $servicePid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $servicePid -Force
        $stopped += "$service (PID $servicePid)"
    }
    Remove-Item -LiteralPath $pidFile -Force
}

if ($stopped.Count -eq 0) {
    Write-Output "No managed local services were running."
}
else {
    Write-Output ("Stopped: " + ($stopped -join ", "))
}
