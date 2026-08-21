[CmdletBinding()]
param(
    [switch]$IncludeChromium
)

$ErrorActionPreference = "Stop"

$ScriptsRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptsRoot
Set-Location $ProjectRoot

$BuildRoot = Join-Path $ProjectRoot ".artifacts"
$DistRoot = Join-Path $BuildRoot "dist"
$WorkRoot = Join-Path $BuildRoot "build"
$BuildEnv = Join-Path $BuildRoot "venv"
$IconPath = Join-Path $WorkRoot "靶场扫描助手.ico"
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null

function New-WindowsIconFromPng {
    param(
        [Parameter(Mandatory = $true)][string]$PngPath,
        [Parameter(Mandatory = $true)][string]$IcoPath
    )

    # Windows 的 ICO 可以直接包含 PNG 图像帧；不需要 Pillow 或额外转换工具。
    $png = [System.IO.File]::ReadAllBytes($PngPath)
    $stream = [System.IO.File]::Open($IcoPath, [System.IO.FileMode]::Create)
    $writer = [System.IO.BinaryWriter]::new($stream)
    try {
        $writer.Write([uint16]0)             # reserved
        $writer.Write([uint16]1)             # icon type
        $writer.Write([uint16]1)             # image count
        $writer.Write([byte]0)               # width: 256
        $writer.Write([byte]0)               # height: 256
        $writer.Write([byte]0)               # color count
        $writer.Write([byte]0)               # reserved
        $writer.Write([uint16]1)             # color planes
        $writer.Write([uint16]32)            # bits per pixel
        $writer.Write([uint32]$png.Length)  # image bytes
        $writer.Write([uint32]22)            # image offset
        $writer.Write($png)
    }
    finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

$SystemPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $SystemPython) {
    throw "未找到 Python。构建 Windows EXE 前需要本机有 Python 作为构建工具。"
}

$BuildPython = Join-Path $BuildEnv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $BuildPython)) {
    Write-Host "创建隔离构建环境 .artifacts\venv ..."
    & $SystemPython.Source -m venv $BuildEnv
}

Write-Host "安装构建依赖..."
& $BuildPython -m pip install -r (Join-Path $ProjectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "构建依赖安装失败，退出码：$LASTEXITCODE" }

New-WindowsIconFromPng `
    -PngPath (Join-Path $ProjectRoot "scanner_app\desktop\web\app_icon.png") `
    -IcoPath $IconPath

if ($IncludeChromium) {
    Write-Host "构建完整版：安装 Playwright 并准备 Chromium..."
    & $BuildPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "运行时依赖安装失败，退出码：$LASTEXITCODE" }
    $env:PLAYWRIGHT_BROWSERS_PATH = "0"
    & $BuildPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Chromium 准备失败，退出码：$LASTEXITCODE" }
    $env:VULANHUB_INCLUDE_CHROMIUM = "1"
}
else {
    Write-Host "构建精简版：不内置 Chromium，EXE 仅保留扫描与桌面界面。"
    Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue
    $env:VULANHUB_INCLUDE_CHROMIUM = "0"
}

$running = Get-Process -Name "靶场扫描助手" -ErrorAction SilentlyContinue
if ($running) {
    throw "检测到靶场扫描助手仍在运行，请先关闭窗口后再构建。"
}

Write-Host "开始生成 .artifacts\dist\靶场扫描助手.exe ..."
& $BuildPython -m PyInstaller --noconfirm --clean --distpath $DistRoot --workpath $WorkRoot (Join-Path $ScriptsRoot "build_windows.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码：$LASTEXITCODE" }

$OutputExe = Join-Path $DistRoot "靶场扫描助手.exe"
if (-not (Test-Path -LiteralPath $OutputExe)) {
    throw "构建命令完成，但没有找到输出文件：$OutputExe"
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $OutputExe).Length / 1MB, 1)
Write-Host "构建完成：$OutputExe（$sizeMb MB）"
