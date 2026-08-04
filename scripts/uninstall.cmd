@echo off
setlocal
REM Removes the Shamash background machinery: the four scheduled tasks and
REM any still-running processes started from this folder. It deletes NO data
REM — what stays, and how to remove it by hand, is printed at the end.
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

echo This will stop Shamash and remove its Windows scheduled tasks:
echo   ShamashBridge, ShamashContactBridge, ShamashWatcher, ShamashScheduler
echo.
echo It deletes NO files: your message history, config and brief stay on disk
echo until you remove them yourself (instructions at the end).
echo.
set "CONFIRM="
set /p CONFIRM=Type yes to continue:
if /i not "%CONFIRM%"=="yes" (
  echo.
  echo Nothing was changed.
  exit /b 1
)

echo.
echo Removing scheduled tasks...
for %%T in (ShamashBridge ShamashContactBridge ShamashWatcher ShamashScheduler) do (
  schtasks /End /TN %%T >nul 2>&1
  schtasks /Delete /TN %%T /F >nul 2>&1 && echo   removed %%T || echo   %%T was not registered
)

echo.
echo Stopping any leftover Shamash processes...
REM Only processes of the kinds Shamash starts (the bridge exe, python, the
REM hidden-window hosts) AND whose command line or exe path points into this
REM folder. The 'uninstall' exclusion keeps this window itself alive.
powershell -NoProfile -Command "$root = '%ROOT%'.ToLower(); Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(whatsapp-bridge\.exe|python[^\\]*\.exe|pythonw[^\\]*\.exe|py\.exe|pyw\.exe|wscript\.exe|cmd\.exe)$' } | Where-Object { $cl = (($_.CommandLine, $_.ExecutablePath) -join ' ').ToLower(); $cl.Contains($root) -and -not $cl.Contains('uninstall') } | ForEach-Object { Write-Host ('  stopping ' + $_.Name + ' (pid ' + $_.ProcessId + ')'); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo.
echo Done. What was NOT deleted, on purpose:
echo.
echo   %ROOT%
echo       The kit itself, plus your config.json and install\install.log.
echo   %ROOT%\brief
echo       Everything you taught it — plain text, worth a read before you bin it.
echo   %ROOT%\bridge\whatsapp-bridge\store  (and ...\contact-bridge\store)
echo       Your WhatsApp message history IN THE CLEAR, and the pairing.
echo   %USERPROFILE%\.local\share\whatsapp-mcp\outbox
echo       Files that were staged for sending.
echo.
echo To remove everything:
echo   1. On your phone: WhatsApp - Settings - Linked devices - log out this
echo      computer. (Do the same in WhatsApp Business if the assistant had its
echo      own number.) This revokes the pairing at the source.
echo   2. Delete the folder %ROOT%
echo   3. Delete %USERPROFILE%\.local\share\whatsapp-mcp
echo.
echo The installed dependencies (git, go, python, ffmpeg) are shared tools and
echo were left alone — remove them with winget only if nothing else uses them.
endlocal
