@echo off
setlocal
py -3 -E "%~dp0notification_settings.py"
if errorlevel 1 (
    echo.
    echo Notification settings could not open. Read the message above.
    pause
    exit /b 1
)
exit /b 0
