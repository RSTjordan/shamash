@echo off
REM Prints the full diagnostic report to the console — nothing is written to
REM the logs, and nothing secret is printed. Copy the whole output when
REM asking for help.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8
py -3 scripts\doctor.py %*
