[CmdletBinding()]
$ErrorActionPreference = "Stop"

$ScriptsRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptsRoot
Set-Location $ProjectRoot

$BuildRoot = Join-Path $ProjectRoot ".artifacts"
$DistRoot = Join-Path $BuildRoot "dist"
$WorkRoot = Join-Path $BuildRoot "build"
$BuildEnv = Join-Path $BuildRoot "venv"
$RuntimeRoot = Join-Path $BuildRoot "runtime\windows"
$BrowserCacheRoot = Join-Path $RuntimeRoot "playwright-browsers"
$DistBrowserRoot = Join-Path $DistRoot "playwright-browsers"
$DistPlaywrightRuntimeRoot = Join-Path $DistRoot "playwright-runtime"
$IconPath = Join-Path $WorkRoot "靶场扫描助手.ico"
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

function Install-PlaywrightChromium {
    param(
        [Parameter(Mandatory = $true)][string]$BrowserPath
    )

    $env:PLAYWRIGHT_BROWSERS_PATH = $BrowserPath

    $existingBrowser = Get-ChildItem -LiteralPath $BrowserPath -Recurse -Filter "chrome.exe" -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($existingBrowser) {
        Write-Host "复用已有 Chromium：$($existingBrowser.FullName)"
        return
    }

    $installArgs = @("install", "chromium")
    $installHelp = (& $BuildPython -m playwright install --help 2>&1 | Out-String)
    if ($installHelp -match "--no-shell") {
        # 截图只需要完整 Chromium；不下载 headless shell 可缩小发行包。
        $installArgs += "--no-shell"
    }
    & $BuildPython -m playwright @installArgs
    if ($LASTEXITCODE -ne 0) { throw "Chromium 准备失败，退出码：$LASTEXITCODE" }
}

function New-WindowsIconFromPng {
    param(
        [Parameter(Mandatory = $true)][string]$PngPath,
        [Parameter(Mandatory = $true)][string]$IcoPath
    )

    # 生成多尺寸 PNG 图像帧，避免单帧 1024px PNG 被 Windows 外壳当作无效图标。
    Add-Type -AssemblyName System.Drawing
    $source = [System.Drawing.Image]::FromFile($PngPath)
    $sizes = @(16, 24, 32, 48, 64, 128, 256)
    $frames = @()
    try {
        foreach ($size in $sizes) {
            $bitmap = [System.Drawing.Bitmap]::new(
                $size,
                $size,
                [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
            )
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $frameStream = [System.IO.MemoryStream]::new()
            try {
                $graphics.Clear([System.Drawing.Color]::Transparent)
                $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $graphics.DrawImage($source, 0, 0, $size, $size)
                $bitmap.Save($frameStream, [System.Drawing.Imaging.ImageFormat]::Png)
                $frames += [PSCustomObject]@{
                    Size = $size
                    Data = $frameStream.ToArray()
                }
            }
            finally {
                $frameStream.Dispose()
                $graphics.Dispose()
                $bitmap.Dispose()
            }
        }
    }
    finally {
        $source.Dispose()
    }

    $stream = [System.IO.File]::Open($IcoPath, [System.IO.FileMode]::Create)
    $writer = [System.IO.BinaryWriter]::new($stream)
    try {
        $writer.Write([uint16]0)             # reserved
        $writer.Write([uint16]1)             # icon type
        $writer.Write([uint16]$frames.Count) # image count
        $offset = 6 + (16 * $frames.Count)
        foreach ($frame in $frames) {
            $dimension = if ($frame.Size -eq 256) { [byte]0 } else { [byte]$frame.Size }
            $writer.Write($dimension)         # width
            $writer.Write($dimension)         # height
            $writer.Write([byte]0)            # color count
            $writer.Write([byte]0)            # reserved
            $writer.Write([uint16]1)          # color planes
            $writer.Write([uint16]32)         # bits per pixel
            $writer.Write([uint32]$frame.Data.Length)
            $writer.Write([uint32]$offset)
            $offset += $frame.Data.Length
        }
        foreach ($frame in $frames) {
            $writer.Write($frame.Data)
        }
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

Write-Host "构建便携版：EXE 保持精简，Chromium 放在同级 playwright-browsers 目录。"
Remove-Item -LiteralPath $DistBrowserRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $BrowserCacheRoot | Out-Null
Install-PlaywrightChromium -BrowserPath $BrowserCacheRoot

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

if (-not (Test-Path -LiteralPath $BrowserCacheRoot)) {
    throw "外置 Chromium 缓存目录不存在：$BrowserCacheRoot"
}
Copy-Item -LiteralPath $BrowserCacheRoot -Destination $DistBrowserRoot -Recurse -Force
$browserExe = Get-ChildItem -LiteralPath $DistBrowserRoot -Recurse -Filter "chrome.exe" -File |
    Select-Object -First 1
if (-not $browserExe) {
    throw "外置 Chromium 未生成 chrome.exe：$DistBrowserRoot"
}
$browserSizeMb = [math]::Round(
    ((Get-ChildItem -LiteralPath $DistBrowserRoot -Recurse -File |
        Measure-Object -Property Length -Sum).Sum) / 1MB, 1
)
Write-Host "外置 Chromium 已准备：$DistBrowserRoot（$browserSizeMb MB）"

$PlaywrightNodePath = Join-Path $BuildEnv "Lib\site-packages\playwright\driver\node.exe"
if (-not (Test-Path -LiteralPath $PlaywrightNodePath)) {
    throw "Playwright Node 驱动不存在：$PlaywrightNodePath"
}
Remove-Item -LiteralPath $DistPlaywrightRuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $DistPlaywrightRuntimeRoot | Out-Null
Copy-Item -LiteralPath $PlaywrightNodePath `
    -Destination (Join-Path $DistPlaywrightRuntimeRoot "node.exe") -Force
Write-Host "外置 Playwright Node 驱动已准备：$DistPlaywrightRuntimeRoot\node.exe"

$sizeMb = [math]::Round((Get-Item -LiteralPath $OutputExe).Length / 1MB, 1)
Write-Host "构建完成：$OutputExe（$sizeMb MB）"
