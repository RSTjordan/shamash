@echo off
REM One scheduled scan -- fired at the times in config.json (schedule.scan_times)
REM by the generic scheduler (state\schedule.json -> ShamashScheduler task).
REM All logic lives in scripts\run_scan.py; this wrapper only sets encoding,
REM appends the log, and raises a WhatsApp note if the scan died.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs

py -3 scripts\run_scan.py >> logs\scan.log 2>&1
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
  py -3 scripts\notify.py "The scheduled scan failed (exit %ERR%). Check logs\scan.log on the computer, or run scripts\doctor.cmd." >> logs\scan.log 2>&1
)

exit /b %ERR%
