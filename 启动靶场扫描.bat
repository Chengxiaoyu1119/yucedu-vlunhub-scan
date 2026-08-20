@echo off
setlocal
cd /d "%~dp0"

rem 兼容旧快捷方式：真正的无控制台入口是“启动靶场扫描.vbs”。
wscript.exe //nologo "%~dp0启动靶场扫描.vbs"
exit /b %ERRORLEVEL%
