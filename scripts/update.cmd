@echo off
REM Updates the kit (git pull, fast-forward only), restarts the background
REM tasks if anything changed, then runs the doctor so you can see the state
REM you were left in. Never touches config.json or brief\ — those are yours.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8

py -3 scripts\update.py
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
py -3 scripts\doctor.py
