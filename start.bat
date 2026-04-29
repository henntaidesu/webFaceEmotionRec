@echo off
chcp 65001 >nul

setlocal

call conda activate webFaceEmotionRec

cd /d "%~dp0backend"
start /b cmd /c "python main.py"

if exist "%~dp0webside\package.json" (
    cd /d "%~dp0webside"
    call npm install
    start /b cmd /c "cd /d %~dp0webside && npm run dev"
)

cd /d "%~dp0"
pause
