<#
.SYNOPSIS
    Startet den WRAM Discovery Agent - OHNE den LLM-Orchestrator.
    STARTET ZUERST discovery_agent.py (TCP-Server auf Port 64321),
    DANN den C# Helper (verbindet sich als Client).
.NOTES
    Nutzt denselben C# Helper wie start_agent.ps1, aber OHNE main.py.
    Kein Konflikt mit dem LLM-Orchestrator.
#>

param()

$runtimeConfigPath = Join-Path $PSScriptRoot "..\runtime_config.json"
$helperRelativePath = "emulator/csharp_helper/bin/Release/net8.0/win-x64/Lufia2AutoTracker.Helper.exe"
$helperStartupDelaySeconds = 3

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
        Write-Host "Warning: Konnte runtime_config.json nicht laden." -ForegroundColor Yellow
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WRAM DISCOVERY AGENT - Starter"        -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Prüfen: Port 64321 frei?
$portCheck = netstat -an 2>$null | findstr ":64321"
if ($portCheck) {
    Write-Host "WARNUNG: Port 64321 ist bereits belegt!" -ForegroundColor Yellow
    Write-Host "  start_agent.ps1 noch aktiv? Dann erst beenden (Ctrl+C)." -ForegroundColor Yellow
    Write-Host ""
    Pause
}

# 2. C# Helper Pfad prüfen
$csharp_exe = Join-Path $PSScriptRoot "..\$helperRelativePath"
$csharp_exe = Resolve-Path $csharp_exe -ErrorAction SilentlyContinue
if (-not $csharp_exe) {
    Write-Host "FEHLER: Helper nicht gefunden unter:" -ForegroundColor Red
    Write-Host "  $helperRelativePath" -ForegroundColor Red
    Write-Host "  Bitte zuerst den C# Helper bauen (dotnet publish)." -ForegroundColor Yellow
    exit 1
}

# 3. discovery_agent.py starten (im Vordergrund - das ist der TCP-Server)
$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$discoveryScript = Join-Path $PSScriptRoot "discovery_agent.py"

if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

Write-Host "Starte Discovery Agent (TCP-Server)..." -ForegroundColor Green
Write-Host "  Script: $discoveryScript" -ForegroundColor Gray
Write-Host "  Python: $venvPython" -ForegroundColor Gray
Write-Host ""

# discovery_agent.py im Vordergrund starten
# Es startet den TCP-Server und wartet auf den C# Helper
# Der C# Helper wird parallel in einem separaten Fenster gestartet
$csharp_start_cmd = "Start-Sleep -Seconds $helperStartupDelaySeconds; & '$csharp_exe'"
Start-Process powershell.exe -ArgumentList "-WindowStyle Normal -NoExit -Command $csharp_start_cmd"

Write-Host "C# Helper wird in separatem Fenster gestartet (Verzoegerung: ${helperStartupDelaySeconds}s)..." -ForegroundColor Green
Write-Host ""

& $venvPython $discoveryScript