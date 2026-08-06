# Patch: bridge logging (bridge/whatsapp-bridge/main.go)

Without this patch the bridge writes a permanent plaintext transcript of every
chat into its log file, plus DEBUG stanza floods (~44 MB/day observed). Apply
it before first pairing, and re-apply + rebuild after any update of the clone.

Three changes in `main.go`:

1. A package-level `quietLogger` wrapper (above `func main()`) whose `Debugf`
   is a no-op and whose `Sub` re-wraps, used for both the client and database
   loggers:

       type quietLogger struct{ waLog.Logger }
       func (l quietLogger) Debugf(msg string, args ...interface{}) {}
       func (l quietLogger) Sub(module string) waLog.Logger { return quietLogger{l.Logger.Sub(module)} }

       logger := waLog.Logger(quietLogger{waLog.Stdout("Client", "INFO", true)})
       dbLog  := waLog.Logger(quietLogger{waLog.Stdout("Database", "INFO", true)})

   Setting the level to "INFO" alone is NOT sufficient in practice — the
   running bridge keeps emitting `[Client/Send DEBUG]` dumps despite the
   library's level filter; the wrapper drops them unconditionally.

   Escape hatch — REQUIRED for pairing: gate it on an env var, because the QR
   pairing helpers parse the "Emitting QR code" DEBUG line:

       if os.Getenv("BRIDGE_VERBOSE") == "1" {
           logger = waLog.Stdout("Client", "DEBUG", true)
       }

2. The `Stored message:` Infof calls in `handleHistorySync` are collapsed into
   one line logging sender/chat/media-type/length — NEVER the message body.

3. The live-message `fmt.Printf` in the event handler is redacted the same
   way: media type and length only, no content.

## Build & swap procedure

A restart-on-failure task will relaunch the old exe within seconds of a kill,
so order matters. Two things that look fine but are not:

- **Never `taskkill /IM whatsapp-bridge.exe`** — both bridges run an exe of
  that name, so it kills the other channel too. Kill by `ExecutablePath`.
- **Windows renames a running `.exe` happily**, so a successful `Move-Item`
  does not prove the old process is gone, and `/api/health` answers just as
  cheerfully from the old binary. This patch adds no route, so the
  new-route probe cannot verify it — see "Verifying" below.

Main bridge:

```powershell
$dir = "<install>\bridge\whatsapp-bridge"
cd $dir
go build -o whatsapp-bridge-new.exe .

schtasks /End /TN ShamashBridge
Get-CimInstance Win32_Process -Filter "Name='whatsapp-bridge.exe'" |
    Where-Object { $_.ExecutablePath -eq "$dir\whatsapp-bridge.exe" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Block until the port is free; a live listener means the old exe is still up.
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline -and
       (Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue)) {
    Start-Sleep -Milliseconds 500
}

Move-Item "$dir\whatsapp-bridge.exe" "$dir\whatsapp-bridge-old.exe" -Force
Move-Item "$dir\whatsapp-bridge-new.exe" "$dir\whatsapp-bridge.exe"
schtasks /Run /TN ShamashBridge
```

Contact bridge — **not** a second build. There is no Go source under
`contact-bridge`; its exe is a *copy* of the binary just built above, and its
task, dir and port are its own (8081 by default — take the real value from
`config.json`'s `channels.contact.bridge_port`):

```powershell
$src = "<install>\bridge\whatsapp-bridge\whatsapp-bridge.exe"   # just built
$dir = "<install>\bridge\contact-bridge"
$port = 8081

schtasks /End /TN ShamashContactBridge
# Kill by ExecutablePath — NEVER by image name; both bridges are called
# whatsapp-bridge.exe and an /IM kill takes the other channel down with it.
Get-CimInstance Win32_Process -Filter "Name='whatsapp-bridge.exe'" |
    Where-Object { $_.ExecutablePath -eq "$dir\whatsapp-bridge.exe" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline -and
       (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
    Start-Sleep -Milliseconds 500
}

Move-Item "$dir\whatsapp-bridge.exe" "$dir\whatsapp-bridge-old.exe" -Force
Copy-Item $src "$dir\whatsapp-bridge.exe"
schtasks /Run /TN ShamashContactBridge
```

**Verifying.** `/api/health` proves the port answers, nothing more. For THIS
patch the witness is the log itself: after the restart, tail the bridge's log
and confirm the `[Client/Send DEBUG]` stanzas are gone and that stored/live
message lines carry media type and length only, never message text. If
`patches/bridge-polls.md` is also applied to the same build, its route probe
is the stronger check on both ports — an empty `POST /api/poll` returns 400
from the new binary and 404 from the old.

Roll back either bridge by stopping its task the same way and moving
`-old.exe` back.
