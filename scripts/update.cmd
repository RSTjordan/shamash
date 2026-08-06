@echo off
REM Updates the kit (git pull, fast-forward only), restarts the background
REM tasks if anything changed, then runs the doctor so you can see the state
REM you were left in. Never touches config.json or brief\ -- those are yours.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8

REM Everything below is ONE line on purpose: update.py's git pull rewrites
REM this very file, and cmd re-reads a running batch file by byte offset --
REM any line after the pull would be parsed from the NEW file at an OLD
REM offset (observed: "'f' is not recognized"). A single line is parsed
REM whole before it runs, and the trailing exit /b stops cmd from reading
REM the file again afterwards.
py -3 scripts\update.py && (echo. & py -3 scripts\doctor.py) & exit /b
