@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

title 靶场扫描助手
set "APP_EXE=%~dp0dist\靶场扫描助手.exe"
if not exist "%APP_EXE%" set "APP_EXE=%~dp0靶场扫描助手.exe"

if not exist "%APP_EXE%" (
    echo [错误] 未找到靶场扫描助手.exe。
    echo 请先运行 build_windows.ps1 生成 Windows 发布版。
    echo 该发布版会把 Python、pywebview、Playwright 和 Chromium 一起打包。
    pause
    exit /b 1
)

echo 正在启动靶场扫描助手...
"%APP_EXE%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [错误] 程序启动失败，退出码：%EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
