; NSIS is a 32-bit process. On Windows ARM, System32 is redirected to the
; emulated PowerShell runtime, whose CIM initialization can hang indefinitely.
; Use the native system tools through Sysnative; keep electron-builder's
; existing application detection, shutdown and file-preservation behavior.
!include "LogicLib.nsh"
!include "getProcessInfo.nsh"
Var pid

!macro customCheckAppRunning
  ${If} ${IsNativeARM64}
    StrCpy $PowerShellPath "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
    StrCpy $CmdPath "$WINDIR\Sysnative\cmd.exe"
  ${EndIf}
  !insertmacro IS_POWERSHELL_AVAILABLE
  !insertmacro _CHECK_APP_RUNNING
!macroend
