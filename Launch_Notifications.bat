@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python notification_settings.py
) else (
    py -3 notification_settings.py
)
if errorlevel 1 (
    echo.
    echo See README.md for Python and Tkinter setup.
    pause
)
