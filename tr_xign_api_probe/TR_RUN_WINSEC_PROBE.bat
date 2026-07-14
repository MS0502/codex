@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo TR Windows security API probe for Winlator
echo This only reads Windows API results and changes no game files.
echo.

if not exist "TR_WINSEC_PROBE_x64.exe" (
  echo ERROR: TR_WINSEC_PROBE_x64.exe is missing from this folder.
  pause
  exit /b 2
)

"TR_WINSEC_PROBE_x64.exe" "winlator_probe_x64.txt"
set "RC64=%ERRORLEVEL%"

if exist "TR_WINSEC_PROBE_x86.exe" (
  "TR_WINSEC_PROBE_x86.exe" "winlator_probe_x86.txt"
  set "RC86=%ERRORLEVEL%"
) else (
  set "RC86=NOT_RUN"
)

echo.
echo x64 exit: %RC64%
echo x86 exit: %RC86%
echo Results written beside this BAT file:
echo   winlator_probe_x64.txt
echo   winlator_probe_x86.txt
echo.
pause
endlocal
