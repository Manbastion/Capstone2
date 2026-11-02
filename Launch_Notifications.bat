@echo off
call "%~dp0Launch_HabSim.bat" --settings %*
exit /b %errorlevel%
