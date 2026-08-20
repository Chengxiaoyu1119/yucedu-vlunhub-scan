@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

title 靶场扫描助手
set "PYTHON_CMD="

where python >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    where py >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    echo [错误] 未找到 Python 3.10+。
    echo 请安装 Python，并在安装时勾选“Add Python to PATH”。
    pause
    exit /b 1
)

echo 正在启动靶场扫描助手...
%PYTHON_CMD% "%~dp0range_gui.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [错误] 程序启动失败，退出码：%EXIT_CODE%
    echo 请根据上面的错误信息安装依赖或修复环境。
    pause
)

exit /b %EXIT_CODE%
