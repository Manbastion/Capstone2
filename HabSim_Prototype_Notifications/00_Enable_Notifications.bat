@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
    echo Could not open this folder.
    pause
    exit /b 1
)
py -3 -E "%~dp0install_habsim_notifications.py"
if errorlevel 1 (
    echo.
    echo Setup stopped. Read the message above.
    popd
    pause
    exit /b 1
)
popd
call "%~dp0Launch_Notifications.bat"
exit /b %errorlevel%
