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

The exe is locked while running, and a restart-on-failure task will relaunch
the old exe within seconds of a kill — order matters:

    go build -o whatsapp-bridge-new.exe .
    schtasks /End /TN ShamashBridge
    taskkill /IM whatsapp-bridge.exe /F
    move /Y whatsapp-bridge-new.exe whatsapp-bridge.exe
    schtasks /Run /TN ShamashBridge

(Same procedure for the contact bridge with `ShamashContactBridge`.)
