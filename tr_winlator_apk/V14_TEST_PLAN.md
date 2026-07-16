# v14 test plan

1. Update the existing TR Compat app; do not uninstall it.
2. Select built-in `Wine 10.10-custom` (`/opt/wine`), Box64 Intermediate, Startup Normal.
3. Run `D:\\TR_KR_LOCAL\\TR_REPAIR_SERVICES_AND_RUN.bat`.
4. Wait up to four minutes because the collector snapshots at 0/15/30/60/90/120/180/240 seconds.
5. After XIGNCODE reports an error, wait ten seconds and close the container normally.
6. Upload `/storage/emulated/0/Documents/Winlator/TR_DIAG_v14_WELLBIA.zip`.

The test only captures redacted diagnostics. It does not alter XIGNCODE files, security decisions, kernel devices, or authentication data.
