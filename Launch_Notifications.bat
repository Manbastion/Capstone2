@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "%USERPROFILE%\CapstoneGH" mkdir "%USERPROFILE%\CapstoneGH"
set "HABSIM_SETTINGS_LOG=%USERPROFILE%\CapstoneGH\notification_startup.log"
echo HabSim notification settings > "%HABSIM_SETTINGS_LOG%"
set "HABSIM_SETTINGS_PY="
call :probe py -3.13
if defined HABSIM_SETTINGS_PY goto launch
call :probe py -3
if defined HABSIM_SETTINGS_PY goto launch
call :probe python
if defined HABSIM_SETTINGS_PY goto launch
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" call :probe "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined HABSIM_SETTINGS_PY goto launch
echo Install Python 3.13 with Tcl/Tk from https://www.python.org/downloads/windows/
echo Then open this file again. No app build or extra packages are needed.
goto failed

:probe
%* -E -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >> "%HABSIM_SETTINGS_LOG%" 2>&1
if not errorlevel 1 set "HABSIM_SETTINGS_PY=%*"
exit /b 0

:launch
%HABSIM_SETTINGS_PY% -E "%~dp0notification_settings.py" >> "%HABSIM_SETTINGS_LOG%" 2>&1
if not errorlevel 1 exit /b 0

:failed
echo.
echo Settings could not open. Diagnostic log:
type "%HABSIM_SETTINGS_LOG%"
echo "%HABSIM_SETTINGS_LOG%"
pause
exit /b 1
