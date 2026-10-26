@echo off
chcp 65001 >nul
setlocal
title IssueDoctor - 启动网站
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1"
set "exit_code=%ERRORLEVEL%"
echo.
if not "%exit_code%"=="0" echo 启动失败，请确认已先运行“01_首次安装.bat”。
pause
exit /b %exit_code%
