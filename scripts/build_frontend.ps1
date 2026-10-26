$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "未找到 npm，请先安装 Node.js 20+。"
}
Push-Location $projectRoot
try {
    npm ci
    npm run build
} finally {
    Pop-Location
}
