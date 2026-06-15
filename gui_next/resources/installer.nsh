; Custom NSIS hooks for the LosslessBob installer (electron-builder).
;
; customInit runs early in .onInit, before file extraction. The default
; electron-builder "app is running" check only looks for LosslessBob.exe —
; it does not know about LosslessBobBackend.exe, the Flask backend spawned
; as a child process of the Electron main process. If that backend is left
; running (e.g. the app was killed via Task Manager or crashed, so
; before-quit never fired), its exe under resources\backend\ stays locked
; and extraction repeatedly fails, surfacing as
; "LosslessBob cannot be closed. Please close it manually and click Retry."
; even though LosslessBob.exe itself is not running.
;
; Force-kill any leftover backend process before extraction so updates/
; installs don't require manual intervention. taskkill exits non-zero when
; no matching process exists; nsExec::Exec ignores that and continues.
!macro customInit
  nsExec::Exec `"$SYSDIR\cmd.exe" /c taskkill /F /IM LosslessBobBackend.exe`
!macroend
