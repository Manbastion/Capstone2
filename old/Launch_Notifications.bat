@echo off
cd /d "%~dp0"
py -3 -E notification_settings.py
if errorlevel 1 pause
