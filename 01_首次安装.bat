@echo off
chcp 65001 >nul
setlocal
title IssueDoctor - 首次安装
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows.ps1"
set "exit_code=%ERRORLEVEL%"
echo.
if not "%exit_code%"=="0" echo 安装未成功，请截图保留上方完整报错。
pause
exit /b %exit_code%
