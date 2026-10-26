param(
    [switch]$BuildFrontend,
    [switch]$WithVector,
    [switch]$WithPdf
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvPath = Join-Path $projectRoot ".venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"

function Assert-LastCommandSucceeded([string]$step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$step 失败，退出码：$LASTEXITCODE"
    }
}

function Find-CompatiblePython {
    $candidates = @(
        @{ Command = "py"; Prefix = @("-3.12") },
        @{ Command = "py"; Prefix = @("-3.11") },
        @{ Command = "py"; Prefix = @("-3.10") },
        @{ Command = "py"; Prefix = @() },
        @{ Command = "python"; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }
        try {
            $version = & $candidate.Command @($candidate.Prefix) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            $parts = $version.Trim().Split(".")
            if (($parts.Count -eq 2) -and ([int]$parts[0] -eq 3) -and ([int]$parts[1] -ge 10)) {
                return $candidate
            }
        } catch {
            continue
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    $python = Find-CompatiblePython
    if (-not $python) {
        throw "未找到 Python 3.10 或更高版本。请先安装 64 位 Python。"
    }
    & $python.Command @($python.Prefix) -m venv $venvPath
    Assert-LastCommandSucceeded "创建虚拟环境"
}

# 核心依赖：足以完成全部诊断、评分、治理与报告导出（约 30 MB）。
& $pythonPath -m pip install --disable-pip-version-check --index-url "https://pypi.org/simple" -r (Join-Path $projectRoot "requirements.txt")
Assert-LastCommandSucceeded "安装核心依赖"

if ($WithVector) {
    Write-Host "安装可选能力：本地语义向量（会连带安装 PyTorch，体积较大）..."
    & $pythonPath -m pip install --disable-pip-version-check --index-url "https://pypi.org/simple" -r (Join-Path $projectRoot "requirements-vector.txt")
    Assert-LastCommandSucceeded "安装向量依赖"
}

if ($WithPdf) {
    Write-Host "安装可选能力：服务端 PDF 导出（Playwright + Chromium）..."
    & $pythonPath -m pip install --disable-pip-version-check --index-url "https://pypi.org/simple" -r (Join-Path $projectRoot "requirements-pdf.txt")
    Assert-LastCommandSucceeded "安装 PDF 依赖"
    & $pythonPath -m playwright install chromium
    Assert-LastCommandSucceeded "安装 Chromium"
}

if ($BuildFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "未找到 npm；不使用 -BuildFrontend 时可直接使用仓库内已编译资源。"
    }
    Push-Location $projectRoot
    try {
        npm ci
        npm run build
    } finally {
        Pop-Location
    }
}

$env:ISSUEDOCTOR_DATA_DIR = Join-Path $projectRoot "data"
Push-Location $projectRoot
try {
    & $pythonPath -m flask --app wsgi db upgrade
    Assert-LastCommandSucceeded "初始化数据库"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "核心安装完成（不含重型依赖）。运行 scripts\run_windows.bat，然后访问 http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "查看可用能力：.venv\Scripts\python.exe -m issuedoctor.cli doctor"
if (-not $WithVector) {
    Write-Host "如需本地语义向量：重新运行本脚本并加 -WithVector" -ForegroundColor DarkGray
}
if (-not $WithPdf) {
    Write-Host "如需服务端 PDF 导出：重新运行本脚本并加 -WithPdf；当前可用网页打印导出" -ForegroundColor DarkGray
}
