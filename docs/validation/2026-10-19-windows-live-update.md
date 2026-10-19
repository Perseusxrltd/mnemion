# Actual Windows automatic update, 19 October 2026

The user's ordinary Windows x64 installation was observed at **4.15.0** before
its six-hour scheduled check window. It then downloaded **4.20.0**, installed it
and restarted without an operator update-check, install command or forced quit.
The new main process started at **18:37:33 UTC**. The regular interval is six
hours plus up to fifteen minutes of jitter; this update occurred within that
window.

After the restart, the installed engine's authenticated local `app.status`
operation returned:

```json
{
  "version": "4.20.0",
  "platform": "win32",
  "architecture": "x64",
  "preferences": {
    "automaticUpdates": true,
    "startAtLogin": true,
    "background": true
  },
  "enabled": true,
  "managed": false,
  "supported": true,
  "status": {
    "state": "Up to date",
    "checkedAt": "2026-10-19T18:39:03.152Z"
  },
  "can_request_restart": false,
  "ready_version": null
}
```

The running process versions independently reported 4.20.0. The status request
read the existing private OS-account control endpoint; no endpoint credential,
workspace key, recovery key or user memory is included here.

This proves one real unattended desktop update and preservation of these app
preferences. It does not prove a remote workspace upgraded, a boot cycle ran,
the missing original office database was recovered, or every device in a fleet
updated. The separate 4.20 public release rehearsal passed on all six desktop
targets; later releases retain their own gates.
