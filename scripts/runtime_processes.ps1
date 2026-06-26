$ErrorActionPreference = "Stop"

function Write-RuntimeProcessLog {
    param(
        [scriptblock]$LogAction,
        [string]$Message
    )

    if ($null -ne $LogAction) {
        & $LogAction $Message
        return
    }

    Write-Host $Message
}

function Get-ChildProcessTree {
    param([int[]]$ProcessIds)

    $allProcesses = Get-CimInstance Win32_Process
    $seen = @{}
    $queue = [System.Collections.Generic.Queue[int]]::new()
    foreach ($processId in $ProcessIds) {
        $queue.Enqueue($processId)
    }

    while ($queue.Count -gt 0) {
        $parentId = $queue.Dequeue()
        foreach ($child in $allProcesses | Where-Object { $_.ParentProcessId -eq $parentId }) {
            if ($seen.ContainsKey($child.ProcessId)) {
                continue
            }

            $seen[$child.ProcessId] = $child
            $queue.Enqueue([int]$child.ProcessId)
        }
    }

    return $seen.Values
}

function Stop-ProcessTree {
    param(
        [AllowEmptyCollection()]
        [object[]]$Processes = @(),
        [scriptblock]$LogAction,
        [string]$Label = "process"
    )

    if ($Processes.Count -eq 0) {
        return
    }

    $rootIds = @($Processes | ForEach-Object { [int]$_.ProcessId })
    $children = @(Get-ChildProcessTree -ProcessIds $rootIds)
    $targets = @($children | Sort-Object ProcessId -Descending) + @($Processes | Sort-Object ProcessId -Descending)
    $stopped = @{}

    foreach ($process in $targets) {
        $processId = [int]$process.ProcessId
        if ($stopped.ContainsKey($processId)) {
            continue
        }

        $stopped[$processId] = $true
        Write-RuntimeProcessLog $LogAction "Stopping $Label $processId."
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

function Get-LocalAgentServerProcesses {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $executable = [string]$_.ExecutablePath
        $isPython = $executable -match "\\python(w)?\.exe$"
        $isPython -and $_.CommandLine -match "local_qq_agent\.server\.app:create_app"
    })
}

function Get-LocalModelServerProcesses {
    param([string]$ProjectRoot)

    $escapedRoot = [regex]::Escape($ProjectRoot)
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match "llama_cpp\.server" -and $_.CommandLine -match $escapedRoot
    })
}

function Stop-LocalAgentServers {
    param([scriptblock]$LogAction)

    $processes = @(Get-LocalAgentServerProcesses)
    Stop-ProcessTree -Processes $processes -LogAction $LogAction -Label "FastAPI agent process"
}

function Stop-LocalModelServers {
    param(
        [Parameter(Mandatory=$true)]
        [string]$ProjectRoot,
        [scriptblock]$LogAction
    )

    $processes = @(Get-LocalModelServerProcesses -ProjectRoot $ProjectRoot)
    Stop-ProcessTree -Processes $processes -LogAction $LogAction -Label "llama server process"
}

function Stop-LocalPortListeners {
    param(
        [int[]]$Ports,
        [scriptblock]$LogAction
    )

    foreach ($port in $Ports) {
        $connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($connection in $connections) {
            Write-RuntimeProcessLog $LogAction "Stopping listener process $($connection.OwningProcess) on port $port."
            Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}
