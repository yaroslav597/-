param(
    [ValidateSet('wsl', 'windows')][string]$Sitl = 'wsl',
    [ValidatePattern('^[a-zA-Z0-9._-]+$')][string]$WslDistro = 'Ubuntu-24.04'
)
$ErrorActionPreference = 'Stop'
# wsl.exe writes UTF-8. Windows PowerShell otherwise decodes its output using
# the console code page (often CP866), corrupting Cyrillic project paths.
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$projectRoot = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $projectRoot '.runtime/logs'
$state = Join-Path $projectRoot '.runtime/sitl-state'
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
$sitlBinary = Join-Path $projectRoot '.runtime/sitl/ArduCopter.exe'
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$node = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/nodejs/node-v22.23.4-win-x64/node.exe' }
foreach ($required in @($python, $node, (Join-Path $projectRoot 'node_modules/vite/bin/vite.js'))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing dependency: $required. See backend/README.md for setup." }
}
New-Item -ItemType Directory -Force -Path $logs, $state | Out-Null

function Read-WslSitl([string]$action) {
    $output = & wsl.exe -d $WslDistro --exec python3 $script:linuxHelper $action
    if ($LASTEXITCODE -ne 0) { throw "WSL SITL $action failed. Check Ubuntu and build ArduPilot; see backend/README.md." }
    $output | ConvertFrom-Json
}

if ($Sitl -eq 'wsl') {
    $helper = Join-Path $PSScriptRoot 'sitl_wsl.py'
    $script:linuxHelper = (& wsl.exe -d $WslDistro --exec wslpath -a -u $helper | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $script:linuxHelper.StartsWith('/')) { throw 'Cannot access the project in WSL.' }
    Read-WslSitl 'check' | Out-Null
} elseif (-not (Test-Path -LiteralPath $sitlBinary)) {
    throw "Missing Windows SITL: $sitlBinary"
}

function Find-Listener([int]$port) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Wait-Listener([int]$port, $process) {
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Find-Listener $port) { return }
        if ($process.HasExited) { throw "Service on port $port stopped. See $logs" }
        Start-Sleep -Milliseconds 200
    }
    throw "Service on port $port did not start. See $logs"
}

# Migrate only the known project Windows simulator, after checking its flight state.
$oldListener = Find-Listener 5760
if ($Sitl -eq 'wsl' -and $oldListener) {
    $oldProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($oldListener.OwningProcess)"
    if ($oldProcess.ExecutablePath -eq $sitlBinary.Replace('/', '\')) {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/status' -TimeoutSec 3
        if ($status.armed -or $status.busy) { throw 'Cannot switch SITL while armed or a mission operation is active.' }
        $backendListener = Find-Listener 8000
        $backendProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($backendListener.OwningProcess)"
        $projectPythonPaths = @($python.Replace('/', '\'), (Join-Path $projectRoot '.runtime/python-runtime/python.exe').Replace('/', '\'))
        if ($backendProcess.CommandLine -notlike '*backend.app.main:app*' -or $backendProcess.ExecutablePath -notin $projectPythonPaths) {
            throw 'Port 8000 is owned by another backend. Stop it before switching SITL.'
        }
        Write-Host 'Switching project simulator from Windows to WSL...'
        Stop-Process -Id $backendProcess.ProcessId
        Stop-Process -Id $oldProcess.ProcessId -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    } elseif (-not (Read-WslSitl 'status').running) {
        throw 'Port 5760 is already occupied. Stop the other simulator before starting WSL SITL.'
    }
}

if ($Sitl -eq 'wsl') {
    $linuxStatus = Read-WslSitl 'status'
    if (-not $linuxStatus.running) {
        Write-Host "Starting Linux SITL in $WslDistro..."
        $process = Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', $WslDistro, '--exec', 'python3', "`"$script:linuxHelper`"", 'run') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'sitl-wsl.out.log') -RedirectStandardError (Join-Path $logs 'sitl-wsl.err.log') -PassThru
        $deadline = [DateTime]::UtcNow.AddSeconds(20)
        do {
            $linuxStatus = Read-WslSitl 'status'
            if ($linuxStatus.running) { break }
            if ($process.HasExited) { throw "WSL SITL stopped. Check $logs/sitl-wsl.err.log" }
            Start-Sleep -Milliseconds 300
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not $linuxStatus.running) { throw "WSL SITL did not start. Check $logs" }
    }
} elseif (-not (Find-Listener 5760)) {
    $process = Start-Process -FilePath $sitlBinary -ArgumentList @('--model', 'quad', '--home', '55.755,37.59,150,0', '--serial0', 'tcp:0', '--speedup', '1') -WorkingDirectory $state -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'sitl.out.log') -RedirectStandardError (Join-Path $logs 'sitl.err.log') -PassThru
    Wait-Listener 5760 $process
}
if (-not (Find-Listener 8000)) {
    $previousEndpoint = $env:MAVLINK_ENDPOINT
    try {
        $env:MAVLINK_ENDPOINT = 'tcp:127.0.0.1:5760'
        $process = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'backend.out.log') -RedirectStandardError (Join-Path $logs 'backend.err.log') -PassThru
    } finally {
        if ($null -eq $previousEndpoint) { Remove-Item Env:MAVLINK_ENDPOINT -ErrorAction SilentlyContinue } else { $env:MAVLINK_ENDPOINT = $previousEndpoint }
    }
    Wait-Listener 8000 $process
}
if (-not (Find-Listener 5173)) {
    $process = Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'frontend.out.log') -RedirectStandardError (Join-Path $logs 'frontend.err.log') -PassThru
    Wait-Listener 5173 $process
}

$services = @(
if ($Sitl -eq 'wsl') { @{ service = 'sitl'; port = 5760; provider = 'wsl'; distro = $WslDistro; linuxPid = $linuxStatus.pid } }
else { @{ service = 'sitl'; port = 5760; provider = 'windows'; pid = (Find-Listener 5760).OwningProcess } }
foreach ($entry in @(@{ name = 'backend'; port = 8000 }, @{ name = 'frontend'; port = 5173 })) {
    $listener = Find-Listener $entry.port
    @{ service = $entry.name; port = $entry.port; pid = $listener.OwningProcess }
})
$services | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $logs 'services.json')
$deadline = [DateTime]::UtcNow.AddSeconds(30)
while ([DateTime]::UtcNow -lt $deadline) {
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/status' -TimeoutSec 2
        if ($status.connected -and $status.home) {
            Write-Host 'Ready: http://127.0.0.1:5173/ (select Backend / MAVLink).'
            Write-Host "SITL: $Sitl. ArduPilot $($status.firmware), Home: $($status.home.lat), $($status.home.lng). ARM: $($status.armed)."
            exit 0
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw "Services are running, but no fresh autopilot Home was received. Check $logs. An existing backend must use TCP 5760."
