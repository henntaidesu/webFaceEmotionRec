@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "BACKEND_DIR=%SCRIPT_DIR%\backend"
set "WEBSITE_DIR=%SCRIPT_DIR%\webside"
set "CONDA_ENV_NAME=webFaceEmotionRec"

REM 查找并激活 conda 环境
where conda >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%i in ('conda info --base') do set "CONDA_BASE=%%i"
) else (
    if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
        set "CONDA_BASE=%USERPROFILE%\miniconda3"
    ) else if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
        set "CONDA_BASE=%USERPROFILE%\anaconda3"
    ) else (
        echo 未找到 conda，请先安装并确保可以使用环境: %CONDA_ENV_NAME%
        exit /b 1
    )
)

call "%CONDA_BASE%\Scripts\activate.bat" "%CONDA_ENV_NAME%"
if %errorlevel% neq 0 (
    echo 激活 conda 环境失败: %CONDA_ENV_NAME%
    exit /b 1
)

REM 前端依赖检查
if exist "%WEBSITE_DIR%\package.json" (
    if not exist "%WEBSITE_DIR%\node_modules" (
        echo 检测到前端依赖未安装，正在执行 npm install...
        pushd "%WEBSITE_DIR%"
        call npm install
        popd
    )
)

echo 正在启动后端服务（后台运行）...
start /b "" cmd /c "cd /d "%BACKEND_DIR%" && call "%CONDA_BASE%\Scripts\activate.bat" "%CONDA_ENV_NAME%" && python main.py"

echo 正在启动前端服务（当前窗口运行，Ctrl+C 退出）...
cd /d "%WEBSITE_DIR%"
call npm run dev

endlocal
