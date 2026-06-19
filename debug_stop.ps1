$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $Root "artifacts\runtime"
$StopLog = Join-Path $RuntimeDir "stop.log"
$ProcessTools = Join-Path $Root "scripts\runtime_processes.ps1"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
. $ProcessTools

function Write-StopLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $StopLog -Value $line -Encoding UTF8
}

Write-StopLog "Stopping local QQ agent services."
Stop-LocalAgentServers -LogAction ${function:Write-StopLog}
Stop-LocalModelServers -ProjectRoot $Root -LogAction ${function:Write-StopLog}
Stop-LocalPortListeners -Ports @(8765, 18080) -LogAction ${function:Write-StopLog}

Push-Location $Root
try {
    Write-StopLog "Stopping SearXNG container."
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = docker compose -f "docker-compose.searxng.yml" down 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorAction

    foreach ($line in $output) {
        Write-StopLog $line
    }

    if ($exitCode -eq 0) {
        Write-StopLog "SearXNG container is stopped."
    }
    else {
        Write-StopLog "SearXNG stop returned exit code $exitCode."
    }
}
catch {
    Write-StopLog "SearXNG stop failed: $($_.Exception.Message)"
}
finally {
    Pop-Location
}

Write-StopLog "Stop completed."
Write-Host ""
Write-Host "Stop log: $StopLog"
