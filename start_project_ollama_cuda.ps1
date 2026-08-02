param(
    [int]$Port = 11435
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$endpoint = "http://127.0.0.1:$Port/api/tags"

try {
    $null = Invoke-RestMethod -Uri $endpoint -TimeoutSec 2
    Write-Host "Project Ollama already available on 127.0.0.1:$Port"
    return
}
catch {
    # Expected when the project-local server is not running yet.
}

$ollama = (Get-Command ollama.exe -ErrorAction Stop).Source
$runDir = Join-Path $projectRoot "data\runs"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

# These variables exist only in this launcher and its child. The user's global
# Ollama server on port 11434 and its Intel/Vulkan policy remain untouched.
$env:OLLAMA_HOST = "127.0.0.1:$Port"
$env:OLLAMA_VULKAN = "0"
$env:GGML_VK_VISIBLE_DEVICES = "-1"
$env:CUDA_VISIBLE_DEVICES = "0"
$env:OLLAMA_CONTEXT_LENGTH = "8192"
$env:OLLAMA_MODELS = "D:\KoboldCpp\models"
$env:OLLAMA_NO_CLOUD = "1"

$process = Start-Process `
    -FilePath $ollama `
    -ArgumentList "serve" `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runDir "ollama_cuda_11435_stdout.log") `
    -RedirectStandardError (Join-Path $runDir "ollama_cuda_11435_stderr.log") `
    -PassThru

$deadline = [DateTime]::UtcNow.AddSeconds(20)
do {
    Start-Sleep -Milliseconds 250
    if ($process.HasExited) {
        throw "Project Ollama exited during startup with code $($process.ExitCode)"
    }
    try {
        $null = Invoke-RestMethod -Uri $endpoint -TimeoutSec 2
        $process.Id | Set-Content -LiteralPath (Join-Path $runDir "ollama_cuda_11435.pid")
        Write-Host "Project Ollama CUDA server started on 127.0.0.1:$Port (PID $($process.Id))"
        return
    }
    catch {
        # Continue until the bounded deadline.
    }
} while ([DateTime]::UtcNow -lt $deadline)

throw "Project Ollama did not become ready on port $Port within 20 seconds"
