@echo off
chcp 65001 >nul
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_project.ps1" -Mode check
set "project_exit=%errorlevel%"
if not "%project_exit%"=="0" pause
exit /b %project_exit%
