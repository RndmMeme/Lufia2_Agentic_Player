param(
    [switch]$InstallDeps = $false
)

$runtimeConfigPath = Join-Path $PSScriptRoot "runtime_config.json"
$helperRelativePath = "emulator/csharp_helper/bin/Release/net8.0/win-x64/Lufia2AutoTracker.Helper.exe"
$helperStartupDelaySeconds = 2

if (Test-Path $runtimeConfigPath) {
    try {
        $runtimeConfig = Get-Content $runtimeConfigPath -Raw | ConvertFrom-Json
        if ($runtimeConfig.helper.relative_executable_path) {
            $helperRelativePath = $runtimeConfig.helper.relative_executable_path
        }
        if ($runtimeConfig.helper.startup_delay_seconds -ne $null) {
            $helperStartupDelaySeconds = [int]$runtimeConfig.helper.startup_delay_seconds
        }
    }
    catch {
        Write-Host "Warning: Failed to load runtime_config.json. Using launcher defaults." -ForegroundColor Yellow
    }
}

# 1. Option to install dependencies
if ($InstallDeps) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    .\venv\Scripts\python.exe -m pip install -r requirements.txt
}

Write-Host "Starting Lufia 2 AI Agent Pipeline..." -ForegroundColor Green

# 2. Launch the C# Memory Helper in a separate, detached console window.
# We delay helper startup briefly so the Python TCP server can bind to port 64321 first.
$csharp_exe = Join-Path $PSScriptRoot $helperRelativePath
if (-not (Test-Path $csharp_exe)) {
    Write-Host "Helper executable not found at $csharp_exe" -ForegroundColor Red
    Write-Host "Update runtime_config.json or build/publish the C# helper first." -ForegroundColor Yellow
    exit 1
}

$csharp_start_cmd = "Start-Sleep -Seconds $helperStartupDelaySeconds; & `'$csharp_exe`'"
Start-Process powershell.exe -ArgumentList "-WindowStyle Normal -NoExit -Command $csharp_start_cmd"

# 3. Launch the Python main Brain/RL loop in the current console window
Write-Host "Starting Python Orchestrator... (Press Ctrl+C to stop)" -ForegroundColor Yellow
.\venv\Scripts\python.exe main.py
