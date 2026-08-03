@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=Z:\sdcard\Download\TR_DIAG_V18"
if not exist "%ROOT%" set "ROOT=Z:\storage\emulated\0\Download\TR_DIAG_V18"
if not exist "%ROOT%" (
  echo TR_DIAG_V18 shared folder not found.
  pause
  exit /b 2
)

set "OUT=%ROOT%\runtime"
if not exist "%OUT%" mkdir "%OUT%"
del /q "%OUT%\WINDOWS_DONE.flag" 2>nul

set "WB=C:\users\xuser\AppData\Local\WELLBIA\xldr_TalesRunner_KR_loader_x64.exe.log"
set "RUNNER=Z:\sdcard\Download\TR_KR_LOCAL\TR_LOGIN_AND_RUN_FIXED.bat"
if not exist "%RUNNER%" set "RUNNER=Z:\storage\emulated\0\Download\TR_KR_LOCAL\TR_LOGIN_AND_RUN_FIXED.bat"

(
  echo started=%DATE% %TIME%
  echo root=%ROOT%
  echo wellbia=%WB%
  echo runner=%RUNNER%
) > "%OUT%\windows_manifest.txt"

if exist "%WB%" (
  copy /y "%WB%" "%OUT%\wellbia_before.bin" >nul
  for %%I in ("%WB%") do echo wellbia_before_size=%%~zI>>"%OUT%\windows_manifest.txt"
) else (
  echo wellbia_before_missing=true>>"%OUT%\windows_manifest.txt"
)

tasklist /v > "%OUT%\tasklist_before.txt" 2>&1

if not exist "%RUNNER%" (
  echo official_runner_missing=true>>"%OUT%\windows_manifest.txt"
  echo Official launch BAT not found: %RUNNER%
  > "%OUT%\WINDOWS_DONE.flag" echo failed_missing_runner
  pause
  exit /b 3
)

call "%RUNNER%" > "%OUT%\official_launch_output.txt" 2>&1
set "RUNNER_EXIT=%ERRORLEVEL%"
echo official_runner_exit=%RUNNER_EXIT%>>"%OUT%\windows_manifest.txt"

rem The official BAT normally returns after spawning the protected process chain.
timeout /t 30 /nobreak >nul 2>&1

tasklist /v > "%OUT%\tasklist_after.txt" 2>&1

if exist "%WB%" (
  copy /y "%WB%" "%OUT%\wellbia_after.bin" >nul
  for %%I in ("%WB%") do echo wellbia_after_size=%%~zI>>"%OUT%\windows_manifest.txt"
) else (
  echo wellbia_after_missing=true>>"%OUT%\windows_manifest.txt"
)

echo finished=%DATE% %TIME%>>"%OUT%\windows_manifest.txt"
> "%OUT%\WINDOWS_DONE.flag" echo done

echo.
echo Diagnostic capture finished.
echo Return to Termux and wait for the ZIP path.
exit /b 0
