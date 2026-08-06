@echo off
REM One scheduler tick -- fired every 5 minutes by the ShamashScheduler task
REM (via run-hidden.vbs). Runs whatever is due in state\schedule.json. Keep
REM this wrapper trivial: all logic lives in scripts\scheduler.py, which does
REM its own logging (logs\scheduler.log); this launcher log only catches
REM Python-level crashes.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
py -3 scripts\scheduler.py >> logs\scheduler-runner.log 2>&1
