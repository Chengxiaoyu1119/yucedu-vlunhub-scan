$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$SystemPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $SystemPython) {
    throw "未找到 Python。构建 Windows EXE 前需要本机有 Python 作为构建工具。"
}

$BuildEnv = Join-Path $ProjectRoot ".build_venv"
$BuildPython = Join-Path $BuildEnv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $BuildPython)) {
    Write-Host "创建隔离构建环境 .build_venv ..."
    & $SystemPython.Source -m venv $BuildEnv
}

Write-Host "安装构建依赖..."
& $BuildPython -m pip install -r (Join-Path $ProjectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "构建依赖安装失败，退出码：$LASTEXITCODE" }

$env:PLAYWRIGHT_BROWSERS_PATH = "0"
Write-Host "下载/准备 Playwright Chromium..."
& $BuildPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Chromium 准备失败，退出码：$LASTEXITCODE" }

Write-Host "开始生成 dist\靶场扫描助手.exe ..."
& $BuildPython -m PyInstaller --noconfirm --clean --distpath (Join-Path $ProjectRoot "dist") --workpath (Join-Path $ProjectRoot "build") (Join-Path $ProjectRoot "build_windows.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码：$LASTEXITCODE" }

$OutputExe = Join-Path $ProjectRoot "dist\靶场扫描助手.exe"
if (-not (Test-Path -LiteralPath $OutputExe)) {
    throw "构建命令完成，但没有找到输出文件：$OutputExe"
}

Write-Host "构建完成：$OutputExe"
