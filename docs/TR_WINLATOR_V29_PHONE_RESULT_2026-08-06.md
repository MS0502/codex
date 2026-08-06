# Winlator TR Compat v29 — Z Fold6 phone result (2026-08-06)

## Input

- device: Galaxy Z Fold6 / Android 16
- build: `11.1-trcompat29-driver-load-ko`
- APK SHA-256: `00dce0cd3be538317c65672b6d58035b102ea8fdde2c828c52a5d1e2726048d9`
- diagnostic bundle: `TR_DIAG_v29_DRIVER_LOAD_KO.zip`
- observed UI: Wine desktop starts; Korean Wine-shell labels render as square glyphs; authenticated launch shows the TalesRunner windmill and then exits.

No credential or IRP payload data is retained in this record.

## Runtime patch activation

The v29 runtime components activated exactly as intended.

- Korean locale extracted and verified at `usr/lib/locale/ko_KR.utf8/LC_CTYPE`.
- Four readable Android CJK fonts were copied to `usr/share/fonts/trcompat-korean`.
- `LANG=ko_KR.UTF-8` and `LC_ALL=ko_KR.UTF-8` were present.
- v29 `ntoskrnl.exe` replaced the exact v28 baseline and verified as SHA-256 `e174c45a200457f6453c8465d6d70a0a9ef2dca35a6362b85f8f4d0747617bb5` before environment startup.

The square-glyph UI therefore is not a failure to copy the locale or source fonts. It proves that the current Wine UI font discovery/fallback path does not select fonts merely placed under the rootfs shared-font directory. The next font revision must install a CJK font into the Wine prefix `C:\windows\Fonts` before Wine process startup; registry replacement/fallback mapping remains a later fallback if prefix installation alone is insufficient.

## Native driver-loading trace

The generic driver pipeline recorded only the ordinary Wine drivers:

- `MountMgr` → `C:\windows\system32\drivers\mountmgr.sys`
- `nsiproxy` → `C:\windows\system32\drivers\nsiproxy.sys`
- `winebus` → `C:\windows\system32\drivers\winebus.sys`
- `winehid` → `C:\windows\system32\drivers\winehid.sys`

No additional `ZwLoadDriver()` request, service configuration, resolved `.sys` path, `LoadLibraryExW()` mapping, or `DriverEntry` event appeared during the authenticated TalesRunner/XIGNCODE sequence.

## Protected-device open sequence

The trace shows repeated ordinary named-object open requests for `\\??\\xhunter1` from three stages:

1. `talesrunner.exe` pre-launch phase;
2. the x64 loader process;
3. `trgame.exe` after authenticated process creation.

There is no subsequent IRP trace against a device named `xhunter1`. The IRPs visible immediately after one loader-stage request are ordinary `Harddisk` create/close operations and return `STATUS_INVALID_DEVICE_REQUEST (0xc0000010)`; they are not evidence of an xhunter dispatch.

The v29 server request trace records the open request but not the final named-object lookup status. Therefore the exact result is not yet directly proven, but the combined evidence strongly indicates that no usable `xhunter1` device object was resolved.

## Process lifetime

- `talesrunner.exe` is running at the 30 s and 45 s snapshots.
- `trgame.exe` is created with the official authenticated command line; credentials are redacted.
- the `trgame.exe` process terminates itself with exit code `-1` approximately 6.15 s after creation and approximately 2.63 s after its final `\\??\\xhunter1` open request;
- the x64 loader terminates with exit code `0` approximately 1.07 s later;
- by the 60 s snapshot, game and loader processes are gone while the Wine desktop/background processes remain.

This matches the visible windmill-then-exit behavior. It is not an Android app crash, a token bridge failure, a drive mapping failure, or a failure to launch the XIGNCODE loader.

## WELLBIA log

The private WELLBIA loader log grew from 4,800 to 5,760 bytes during the failed launch. Its printable-byte extraction is high-entropy/obfuscated and does not expose a reliable textual error code. No conclusion is drawn from those byte strings.

## Next diagnostic revision

v30 should remain trace-only and must not create, spoof, or alter a driver/device/security result.

1. Instrument Wine server `open_file_object` generically to record final `NTSTATUS` and returned handle for every named-file-object open. Correlation with the existing request line will establish the exact result of `\\??\\xhunter1` opens.
2. Build and atomically deploy the matching `wineserver` without changing lookup behavior.
3. Install the selected Android CJK font into the existing Wine prefix `drive_c/windows/Fonts` before Wine process startup, preserving the container and rootfs.
4. Keep the PR draft until the v30 phone result is reviewed.
