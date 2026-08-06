@echo off
rem Main-channel WhatsApp bridge (the linked device on the owner's own
rem account). Started at logon by the ShamashBridge scheduled task via
rem run-hidden.vbs; runs until killed. The task's restart-on-failure brings
rem it back if it dies.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

rem The port lives in config.json (channels.main.bridge_port) -- the single
rem source of truth. Ask config.py rather than hardcode; fall back to the
rem exe's default (8080) if config can't be read (e.g. mid-install).
set "PORT="
for /f "usebackq delims=" %%p in (`py -3 -c "import sys; sys.path.insert(0, r'%ROOT%\scripts'); import config; print(config.load(required=False)['channels']['main']['bridge_port'])" 2^>nul`) do set "PORT=%%p"
if defined PORT set "WHATSAPP_BRIDGE_PORT=%PORT%"

rem No webhook consumer exists in this kit -- disable it, otherwise every
rem inbound message logs a failed TCP connect.
set "WEBHOOK_URL="

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
set "LOG=%ROOT%\logs\bridge.log"
rem Rotate the log on start so it can't grow without bound (the bridge holds
rem the file open while running, so rotation only works here).
for %%A in ("%LOG%") do if %%~zA GTR 20000000 (
  del "%LOG%.1" 2>nul
  move /y "%LOG%" "%LOG%.1" >nul
)

cd /d "%ROOT%\bridge\whatsapp-bridge"
rem Explicit .\ path: with NoDefaultCurrentDirectoryInExePath=1 set, cmd no
rem longer finds bare exe names in the current directory.
.\whatsapp-bridge.exe >> "%LOG%" 2>&1
