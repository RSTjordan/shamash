@echo off
REM One job-runner tick -- run periodically via the generic scheduler
REM (state\schedule.json). At most ONE work-shift runs per tick; no runnable
REM job means a heartbeat line and instant exit. The runner does its own
REM logging (logs\jobs.log) and failure notifications; this launcher log only
REM catches Python-level crashes.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
py -3 scripts\job-runner.py >> logs\job-runner-launcher.log 2>&1
