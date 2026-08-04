@echo off
rem Contact-channel WhatsApp bridge — the agent's own number, a second bridge
rem instance with its own store, token and port. Started at logon by the
rem ShamashContactBridge scheduled task via run-hidden.vbs. Only registered
rem when channels.contact.enabled is true (stage 6b of the runbook).
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

rem The port lives in config.json (channels.contact.bridge_port) — the single
rem source of truth. Ask config.py rather than hardcode; fall back to the
rem kit default (8081) if config can't be read (e.g. mid-install).
set "PORT="
for /f "usebackq delims=" %%p in (`py -3 -c "import sys; sys.path.insert(0, r'%ROOT%\scripts'); import config; print(config.load(required=False)['channels']['contact']['bridge_port'])" 2^>nul`) do set "PORT=%%p"
if not defined PORT set "PORT=8081"
set "WHATSAPP_BRIDGE_PORT=%PORT%"

rem No webhook consumer exists in this kit — disable it.
set "WEBHOOK_URL="

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
set "LOG=%ROOT%\logs\contact-bridge.log"
rem Rotate the log on start so it can't grow without bound (the bridge holds
rem the file open while running, so rotation only works here).
for %%A in ("%LOG%") do if %%~zA GTR 20000000 (
  del "%LOG%.1" 2>nul
  move /y "%LOG%" "%LOG%.1" >nul
)

cd /d "%ROOT%\bridge\contact-bridge"
whatsapp-bridge.exe >> "%LOG%" 2>&1
