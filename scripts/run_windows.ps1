$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '尚未安装。请先双击项目根目录中的 "01_首次安装.bat"。'
}

$env:ISSUEDOCTOR_DATA_DIR = Join-Path $projectRoot "data"
$port = 5000
while (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    $port++
    if ($port -gt 5010) {
        throw "5000–5010 端口均被占用，请关闭占用这些端口的程序后重试。"
    }
}
$url = "http://127.0.0.1:$port"
Write-Host "IssueDoctor 正在启动：$url"
Write-Host "运行期间请保持此窗口打开；按 Ctrl+C 可停止网站。"

Push-Location $projectRoot
$server = $null
try {
    & $pythonPath -m flask --app wsgi db upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "数据库升级失败，退出码：$LASTEXITCODE"
    }
    $serverArgs = @("-m", "flask", "--app", "wsgi", "run", "--host", "127.0.0.1", "--port", $port)
    $server = Start-Process -FilePath $pythonPath -ArgumentList $serverArgs -WorkingDirectory $projectRoot -PassThru -NoNewWindow
    $started = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($server.HasExited) {
            throw "网站进程提前退出，退出码：$($server.ExitCode)"
        }
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 | Out-Null
            $started = $true
            break
        } catch {
            continue
        }
    }
    if (-not $started) {
        throw "15 秒内未能访问网站。"
    }
    Start-Process $url
    Wait-Process -Id $server.Id
} finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
    }
    Pop-Location
}
