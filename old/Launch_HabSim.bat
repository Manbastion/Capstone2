@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if exist "%~dp0HabSimClient.exe" goto bundled_here
if exist "%~dp0HabSimClient\HabSimClient.exe" goto bundled_folder
if exist "%~dp0dist\HabSimClient\HabSimClient.exe" goto bundled_dist

if not exist "%USERPROFILE%\CapstoneGH" mkdir "%USERPROFILE%\CapstoneGH"
set "HABSIM_LOG=%USERPROFILE%\CapstoneGH\launcher.log"
echo HabSim launcher diagnostics > "%HABSIM_LOG%"
set "HABSIM_PY="
call :probe py -3.13
if defined HABSIM_PY goto source
call :probe py -3
if defined HABSIM_PY goto source
call :probe python
if defined HABSIM_PY goto source
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" call :probe "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined HABSIM_PY goto source
echo.
echo HabSim needs Python 3.10 or newer with Tkinter to run this source download.
echo Easiest option: ask your team for the built HabSimClient Windows folder.
echo Extract the entire folder, then open HabSimClient.exe. Python is included.
echo For source use, install Python with Tcl/Tk from https://www.python.org/downloads/windows/
echo Diagnostic log: "%HABSIM_LOG%"
pause
exit /b 1

:probe
%* -E -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >> "%HABSIM_LOG%" 2>&1
if not errorlevel 1 set "HABSIM_PY=%*"
exit /b 0

:source
%HABSIM_PY% -E "%~dp0habsim_client.py" %* >> "%HABSIM_LOG%" 2>&1
if errorlevel 1 goto failed
exit /b 0

:bundled_here
start "" /wait "%~dp0HabSimClient.exe" %*
if errorlevel 1 goto failed
exit /b 0
:bundled_folder
start "" /wait "%~dp0HabSimClient\HabSimClient.exe" %*
if errorlevel 1 goto failed
exit /b 0
:bundled_dist
start "" /wait "%~dp0dist\HabSimClient\HabSimClient.exe" %*
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo HabSim could not start. Keep this window open and share the error with your team.
if defined HABSIM_LOG type "%HABSIM_LOG%"
echo Also check "%USERPROFILE%\CapstoneGH\client_startup.log".
pause
exit /b 1
