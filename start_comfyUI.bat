@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "COMFYUI_START=%SCRIPT_DIR%\comfyui\start.bat"

if not exist "%COMFYUI_START%" (
    echo Not found: %COMFYUI_START%
    exit /b 1
)

call "%COMFYUI_START%" %*
exit /b %errorlevel%
