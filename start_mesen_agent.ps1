param(
    [switch]$Execute,
    [switch]$EnableLlm,
    [switch]$EnableBattle,
    [int]$MaxActions = 0,
    [string]$Goal = "Finish the randomized game as quickly as safely possible."
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

$arguments = @("run_agent.py", "--goal", $Goal)
if ($Execute) { $arguments += "--execute" }
if ($EnableLlm) {
    & (Join-Path $projectRoot "start_project_ollama_cuda.ps1")
    $arguments += "--enable-llm"
}
if ($EnableBattle) { $arguments += "--enable-battle" }
if ($MaxActions -gt 0) { $arguments += @("--max-actions", "$MaxActions") }

Push-Location $projectRoot
try {
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
