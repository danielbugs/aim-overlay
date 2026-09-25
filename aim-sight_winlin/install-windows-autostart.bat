@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows-autostart.ps1"
if errorlevel 1 (
    echo.
    echo Failed to create the Aim Sight startup shortcut.
    pause
    exit /b 1
)

echo.
echo Aim Sight will start automatically when you sign in to Windows.
pause
