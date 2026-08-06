param(
    [string]$ModelDirectory = "D:\KoboldCpp\models\admin\Qwen3-VL-8B-Instruct-GGUF",
    [string]$LlamaServer = "D:\llama.cpp-nanbeige42\build-vulkan\bin\Release\llama-server.exe",
    [int]$Port = 8080,
    [int]$ContextTokens = 12288
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$modelPath = Join-Path $ModelDirectory "Qwen3VL-8B-Instruct-Q4_K_M.gguf"
$projectorPath = Join-Path $ModelDirectory "mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf"
$runDirectory = Join-Path $projectRoot "data\runs\model_server"
$pidPath = Join-Path $runDirectory "qwen3_vl_8b_vulkan.pid"
$stdoutPath = Join-Path $runDirectory "qwen3_vl_8b_vulkan_stdout.log"
$stderrPath = Join-Path $runDirectory "qwen3_vl_8b_vulkan_stderr.log"

foreach ($requiredPath in @($LlamaServer, $modelPath, $projectorPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file is missing: $requiredPath"
    }
}

$expectedHashes = @{
    $modelPath = "67D1659BFE71B89D50B45A4AD1A9E5B997E5BB16CE5DA66A6A6167ABD569E9E2"
    $projectorPath = "C6BA85508D82F42590E6EB77D5340369AB6FECF107A7561D809523D8AA5F3BFD"
}
foreach ($entry in $expectedHashes.GetEnumerator()) {
    $actualHash = (Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash
    if ($actualHash -ne $entry.Value) {
        throw "SHA-256 mismatch for $($entry.Key). Expected $($entry.Value), got $actualHash"
    }
}

$existingServer = Get-Process -Name "llama-server" -ErrorAction SilentlyContinue
if ($existingServer) {
    $ids = ($existingServer | Select-Object -ExpandProperty Id) -join ", "
    throw "A llama-server process is already running (PID $ids). Stop the intended project server explicitly before starting Qwen."
}

New-Item -ItemType Directory -Force -Path $runDirectory | Out-Null
$arguments = @(
    "-m", $modelPath,
    "--mmproj", $projectorPath,
    "--image-min-tokens", "1024",
    "--host", "127.0.0.1",
    "--port", $Port,
    "-ngl", "99",
    "--device", "Vulkan0",
    "--ctx-size", $ContextTokens,
    "--parallel", "1",
    "--flash-attn", "on",
    "--cache-type-k", "q8_0",
    "--cache-type-v", "q8_0",
    "--reasoning", "off",
    "--reasoning-budget", "0"
)

$serverProcess = Start-Process `
    -FilePath $LlamaServer `
    -ArgumentList $arguments `
    -WorkingDirectory (Split-Path -Parent $LlamaServer) `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

$serverProcess.Id | Set-Content -LiteralPath $pidPath -Encoding ascii
Write-Host "Qwen3-VL-8B server started as PID $($serverProcess.Id)."
Write-Host "Endpoint: http://127.0.0.1:$Port/v1"
Write-Host "Logs: $runDirectory"
