@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -m pip install -r requirements.txt
) else (
    python -m pip install -r requirements.txt
)

if not %errorlevel% equ 0 (
    echo.
    echo Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully.
pause
