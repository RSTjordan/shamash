' Launches the given command with its console window hidden, WAITS for it and
' propagates its exit code — so Task Scheduler sees the real process lifetime
' (RestartOnFailure, ExecutionTimeLimit and IgnoreNew actually work). A VBS
' that fires and exits would make every task report success instantly and
' none of those settings would ever trigger.
' Usage: wscript.exe run-hidden.vbs <path-to-cmd-or-exe>
Set shell = CreateObject("WScript.Shell")
code = shell.Run("""" & WScript.Arguments(0) & """", 0, True)
WScript.Quit code
