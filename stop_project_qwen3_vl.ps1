param(
    [string]$LlamaServer = "D:\llama.cpp-nanbeige42\build-vulkan\bin\Release\llama-server.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidPath = Join-Path $projectRoot "data\runs\model_server\qwen3_vl_8b_vulkan.pid"

if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
    throw "No project Qwen PID file exists: $pidPath"
}

$projectPid = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
$serverProcess = Get-Process -Id $projectPid -ErrorAction SilentlyContinue
if (-not $serverProcess) {
    Remove-Item -LiteralPath $pidPath
    Write-Host "The recorded process is already stopped; stale PID file removed."
    exit 0
}

if ($serverProcess.Path -ne $LlamaServer) {
    throw "PID $projectPid does not point to the configured llama-server. Refusing to stop it."
}

Stop-Process -Id $projectPid
Remove-Item -LiteralPath $pidPath
Write-Host "Stopped project Qwen server PID $projectPid."
