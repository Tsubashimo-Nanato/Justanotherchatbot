$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ArtifactDir = Join-Path $Root "artifacts"
$RuntimeDir = Join-Path $ArtifactDir "runtime"
$DeployLog = Join-Path $RuntimeDir "deploy.log"
$UvicornOut = Join-Path $RuntimeDir "uvicorn.out.log"
$UvicornErr = Join-Path $RuntimeDir "uvicorn.err.log"
$LlamaOut = Join-Path $RuntimeDir "llama.out.log"
$LlamaErr = Join-Path $RuntimeDir "llama.err.log"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$DebugHost = if ($env:LOCAL_QQ_AGENT_HOST) { $env:LOCAL_QQ_AGENT_HOST } else { "0.0.0.0" }
$DebugPort = if ($env:LOCAL_QQ_AGENT_PORT) { [int]$env:LOCAL_QQ_AGENT_PORT } else { 8765 }
$StartLocalModel = if ($env:LOCAL_QQ_AGENT_START_LOCAL_MODEL) { $env:LOCAL_QQ_AGENT_START_LOCAL_MODEL -ne "0" } else { $true }
$StartSearxngOnDeploy = $env:LOCAL_QQ_AGENT_START_SEARXNG -eq "1"
$SitePackages = Join-Path $Root ".venv\Lib\site-packages"
$CudaRuntimeBin = Join-Path $SitePackages "nvidia\cuda_runtime\bin"
$CudaBlasBin = Join-Path $SitePackages "nvidia\cublas\bin"
$CudaNvrtcBin = Join-Path $SitePackages "nvidia\cuda_nvrtc\bin"
$ProcessTools = Join-Path $Root "scripts\runtime_processes.ps1"
. $ProcessTools

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

function Write-DeployLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $DeployLog -Value $line -Encoding UTF8
}

function Test-PortListening {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    return $null -ne $connection
}

function Get-PrimaryLanIPv4 {
    $addresses = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
        Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq "Up" } |
        ForEach-Object { $_.IPv4Address.IPAddress } |
        Where-Object { $_ -and $_ -notlike "169.254.*" -and $_ -ne "127.0.0.1" }

    $preferred = $addresses | Where-Object { $_ -like "192.168.*" -or $_ -like "10.*" -or $_ -like "172.16.*" -or $_ -like "172.17.*" -or $_ -like "172.18.*" -or $_ -like "172.19.*" -or $_ -like "172.2?.*" -or $_ -like "172.30.*" -or $_ -like "172.31.*" } | Select-Object -First 1
    if ($preferred) {
        return $preferred
    }

    return $addresses | Select-Object -First 1
}

function Ensure-DebugFirewallRule {
    if ($DebugHost -eq "127.0.0.1" -or $DebugHost -eq "localhost") {
        Write-DeployLog "Debug server is localhost-only; firewall rule is not needed."
        return
    }

    $ruleName = "Local QQ Agent Debug $DebugPort"
    try {
        $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($existing) {
            Write-DeployLog "Firewall rule already exists: $ruleName"
            return
        }

        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $DebugPort -Profile Private | Out-Null
        Write-DeployLog "Firewall rule added for TCP port $DebugPort on Private networks."
    }
    catch {
        Write-DeployLog "Firewall rule was not added: $($_.Exception.Message)"
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$Seconds
    )

    for ($i = 0; $i -lt $Seconds; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

function Ensure-Venv {
    if (Test-Path $Python) {
        Write-DeployLog "Using existing venv: $Python"
        return
    }

    Write-DeployLog "Creating .venv with Astral CPython 3.12.10."
    Push-Location $Root
    try {
        py -V:Astral/CPython3.12.10 -m venv .venv
        & $Python -m pip install --upgrade pip
        & $Python -m pip install -e ".[dev,browser]"
        & $Python -m pip install "llama-cpp-python[server]==0.3.30" --prefer-binary --extra-index-url "https://abetlen.github.io/llama-cpp-python/whl/cu124"
        & $Python -m pip install "nvidia-cuda-runtime-cu12==12.4.127" "nvidia-cublas-cu12==12.4.5.8" "nvidia-cuda-nvrtc-cu12==12.4.127"
        & $Python -m playwright install chromium
    }
    finally {
        Pop-Location
    }
}

function Test-LlamaCudaAvailable {
    $previousPath = $env:PATH
    $env:PATH = "$CudaRuntimeBin;$CudaBlasBin;$CudaNvrtcBin;$env:PATH"
    try {
        & $Python -c "import llama_cpp; raise SystemExit(0 if llama_cpp.llama_supports_gpu_offload() else 1)" | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $env:PATH = $previousPath
    }
}

function Ensure-LlamaCudaRuntime {
    if (Test-LlamaCudaAvailable) {
        Write-DeployLog "llama-cpp CUDA offload is available."
        return
    }

    Write-DeployLog "Installing llama-cpp CUDA wheel and CUDA runtime DLL packages."
    Push-Location $Root
    try {
        & $Python -m pip install --force-reinstall --no-cache-dir "llama-cpp-python[server]==0.3.30" --prefer-binary --extra-index-url "https://abetlen.github.io/llama-cpp-python/whl/cu124"
        & $Python -m pip install "nvidia-cuda-runtime-cu12==12.4.127" "nvidia-cublas-cu12==12.4.5.8" "nvidia-cuda-nvrtc-cu12==12.4.127"
    }
    finally {
        Pop-Location
    }

    if (Test-LlamaCudaAvailable) {
        Write-DeployLog "llama-cpp CUDA offload is available after reinstall."
        return
    }

    Write-DeployLog "llama-cpp CUDA offload check failed. Model server may fall back or fail; check $LlamaErr."
}

function Ensure-Model {
    Write-DeployLog "Ensuring active model profile is downloaded."
    Push-Location $Root
    try {
        $output = & $Python (Join-Path $Root "scripts\download_model.py") 2>&1
        foreach ($line in $output) {
            Write-DeployLog $line
        }
    }
    finally {
        Pop-Location
    }
}

function Start-Searxng {
    Write-DeployLog "Starting SearXNG container."
    Push-Location $Root
    try {
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $output = docker compose -f "docker-compose.searxng.yml" up -d 2>&1
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorAction

        foreach ($line in $output) {
            Write-DeployLog $line
        }

        if ($exitCode -eq 0) {
            Write-DeployLog "SearXNG container is ready or already running."
            return
        }

        Write-DeployLog "SearXNG start returned exit code $exitCode."
    }
    catch {
        Write-DeployLog "SearXNG start failed: $($_.Exception.Message)"
    }
    finally {
        Pop-Location
    }
}

function Start-LlamaServer {
    Write-DeployLog "Starting active llama-cpp model server."
    $previousPath = $env:PATH
    $env:PATH = "$CudaRuntimeBin;$CudaBlasBin;$CudaNvrtcBin;$env:PATH"
    try {
        $script = "import json; from local_qq_agent.config import ModelConfig; from local_qq_agent.model.manager import restart_llama_server; config = ModelConfig.load(); print(json.dumps(restart_llama_server(config), ensure_ascii=False, indent=2))"
        $output = & $Python -c $script 2>&1
        foreach ($line in $output) {
            Write-DeployLog $line
        }
    }
    finally {
        $env:PATH = $previousPath
    }

    if (Wait-HttpOk "http://127.0.0.1:18080/v1/models" 180) {
        Write-DeployLog "Model server is ready."
        return
    }

    Write-DeployLog "Model server did not become ready in time. Check $LlamaErr"
}

function Start-DebugServer {
    Stop-LocalAgentServers -LogAction ${function:Write-DeployLog}
    Stop-LocalPortListeners -Ports @($DebugPort) -LogAction ${function:Write-DeployLog}
    Start-Sleep -Seconds 2
    Ensure-DebugFirewallRule
    Write-DeployLog "Starting FastAPI debug server on $DebugHost`:$DebugPort."
    Start-Process `
        -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "local_qq_agent.server.app:create_app", "--factory", "--host", $DebugHost, "--port", "$DebugPort") `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $UvicornOut `
        -RedirectStandardError $UvicornErr `
        -WindowStyle Hidden | Out-Null

    if (Wait-HttpOk "http://127.0.0.1:$DebugPort/debug" 45) {
        Write-DeployLog "Debug server is ready."
        try {
            $qqStatus = Invoke-RestMethod -Uri "http://127.0.0.1:$DebugPort/api/qq/status" -Method Get
            Write-DeployLog "QQ status after startup: available=$($qqStatus.available), armed=$($qqStatus.armed), group=$($qqStatus.group_matched)."
        }
        catch {
            Write-DeployLog "QQ status after startup failed: $($_.Exception.Message)"
        }
        return
    }

    Write-DeployLog "Debug server did not become ready in time. Check $UvicornErr"
}

Write-DeployLog "Deploy started."
Ensure-Venv
if ($StartLocalModel) {
    Ensure-LlamaCudaRuntime
    Ensure-Model
    Start-LlamaServer
}
else {
    Write-DeployLog "Skipping local model startup because LOCAL_QQ_AGENT_START_LOCAL_MODEL=0."
}
if ($StartSearxngOnDeploy) {
    Start-Searxng
}
else {
    Write-DeployLog "Skipping SearXNG startup. Local web search can be started separately when needed."
}
Start-DebugServer

$LocalDebugUrl = "http://127.0.0.1:$DebugPort/debug"
$LanAddress = Get-PrimaryLanIPv4
$LanDebugUrl = if ($LanAddress) { "http://$LanAddress`:$DebugPort/debug" } else { "" }
Write-DeployLog "Debug page available locally at $LocalDebugUrl"
if ($LanDebugUrl) {
    Write-DeployLog "Debug page available on LAN at $LanDebugUrl"
}

Write-Host ""
Write-Host "Debug page:"
Write-Host "  Local: $LocalDebugUrl"
if ($LanDebugUrl) {
    Write-Host "  LAN:   $LanDebugUrl"
}
Write-Host ""
Write-Host "Runtime logs:"
Write-Host "  $DeployLog"
Write-Host "  $UvicornErr"
Write-Host "  $LlamaErr"
Write-Host ""
Write-Host "Startup flags:"
Write-Host "  LOCAL_QQ_AGENT_START_LOCAL_MODEL=0  skips llama.cpp during deploy"
Write-Host "  LOCAL_QQ_AGENT_START_SEARXNG=1       starts SearXNG during deploy"
Write-Host ""
Write-Host "Current status:"
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$DebugPort/api/debug/compact-status" -Method Get | ConvertTo-Json -Depth 6
}
catch {
    Write-Host $_.Exception.Message
}
Write-Host ""
Write-Host "Recent deploy log:"
Get-Content $DeployLog -Tail 30
