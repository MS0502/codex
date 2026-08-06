# Winlator TR Compat v30 — X3 boundary and Korean font validation

## Status

Validated diagnostic build. Keep PR draft until one authenticated Galaxy Z Fold6 run produces `TR_DIAG_v30_X3_BOUNDARY_FONT.zip` and the result is reviewed.

This build does not decrypt, unpack, patch, bypass, disable, emulate, or fabricate any protected module, driver, service, device, IOCTL, authentication result, or security result.

## Static evidence input

- archive: `XIGNCODE_STATIC_SET.zip`
- archive SHA-256: `3eb242228f46a33170ba366bfc61eb5c7d726034547f6b8c8c848a11ce97fa5a`
- detailed report: `docs/TR_XIGNCODE_STATIC_BOUNDARY_2026-08-06.md`

Strict PE validation showed:

- loader: one top-level x86-64 PE image;
- `x3_x64.xem`: one top-level x86-64 PE DLL;
- `xcorona_x64.xem`: top-level x64 DLL plus one protected 32-bit GUI PE;
- `xmag_x64.xem`: zero validated PE candidates;
- `xnina_x64.xem`: zero validated PE candidates.

`x3_x64.xem` statically imports general service-management APIs including `OpenSCManagerW`, `CreateServiceW`, `OpenServiceW/A`, `StartServiceW`, `ControlService`, and `QueryServiceStatusEx`. The prior authenticated v29 run showed zero x3 file opens/maps and zero protected-service calls. v30 adds module-load and version-query observation to correlate this exact boundary without changing it.

## Exact validated build

- source head: `d5d31034ebdc9700ab25acda51d6c4cd7a4bdf49`
- workflow run: `31070033406`
- APK artifact: `WINLATOR_TR_COMPAT_V30_X3_BOUNDARY_FONT_APK`
- APK artifact ID: `8955410654`
- APK artifact ZIP digest: `sha256:4cf50e0a7e6a53d3ade7a488904de78f89c4c8be4aa0abbfc3d36aa50761deff`
- build-log artifact ID: `8955408977`
- build-log ZIP digest: `sha256:4316c057685c349e599d3f974ca5ec3cbb9407fbfb940ccd6b0b155c4208fcd7`

## APK

- filename: `Winlator_TR_Compat_v30_X3_BOUNDARY_FONT.apk`
- size: `167152105` bytes
- SHA-256: `a0d42972ac391db6d2e0ab7f40ec135bf54154427ee6250fda2e8134ca4cc6b9`
- package: `com.winlator.trcompat`
- versionCode: `30`
- versionName: `11.1-trcompat30-x3-boundary-font`
- APK Signature Scheme v2: verified in registered CI
- signer certificate SHA-256: `3819847878a333cc204bd93ab89a28a9867c066da5def40401d840fda9f9f017`

The package and signer remain continuous with v26-v29, so the APK is intended to update the existing installation without deleting its container or Wine prefix.

## Exact runtime assets

v30 restores its runtime inputs from the exact validated v29 APK rather than trusting a newly compiled Wine PE.

- embedded rootfs SHA-256: `fd084ca23321b9ae357716f570a8d79143754ae1d182aa5082f2ecf26a87ca9b`
- validated v29 `ntoskrnl.exe` SHA-256: `e174c45a200457f6453c8465d6d70a0a9ef2dca35a6362b85f8f4d0747617bb5`
- Korean locale asset SHA-256: `11add0c675b516bc1d27e8b9bde9cf05123ca9e5a86a757eb77b6e7edbee7d75`
- rootfs reinstall forced: false
- container home preserved: true
- Wine-prefix reset forced: false

The registered workflow proved that the v30 delta changes only:

- `app/build.gradle`;
- `XServerDisplayActivity.java`;
- `TrCompatDiagnostics.java`;
- `TrCompatKoreanSupport.java`;
- one audit report file.

## Added observation

v30 retains the validated v29 generic driver-load and IRP tracer and adds Wine channels for:

- DLL/image loading (`+loaddll`);
- Windows-version queries (`+ver`).

The focused diagnostic filter retains lines involving XEM modules, image loads, version queries, service-control APIs, token privilege adjustment, native-driver loading, device creation, and subsequent IRP activity.

No return status, output buffer, device object, service state, version response, or security result is changed.

## Korean UI activation

Before the Wine environment starts, v30:

1. reuses readable Korean/CJK fonts already present under Android system partitions;
2. copies selected font files into the existing prefix's `C:\\windows\\Fonts` directory;
3. creates one-time backups of `system.reg` and `user.reg`;
4. registers the selected font and sets substitutes for Gulim, Dotum, Batang, Malgun Gothic, `MS Shell Dlg`, and `MS Shell Dlg 2`;
5. adds Wine font replacements for common fallback faces;
6. restores the registry backups if activation throws an error.

No third-party font file is embedded or redistributed in the APK.

## Independent artifact inspection

After downloading the final artifact outside the workflow:

- APK ZIP integrity passed;
- APK SHA-256 matched the artifact manifest;
- embedded rootfs hash matched the validated v29 rootfs;
- embedded `ntoskrnl.exe` matched the validated v29 tracer;
- embedded Korean locale matched the validated v29 locale asset;
- DEX contained the expected diagnostic, Windows Fonts, registry backup, registry rollback, and font-substitution markers;
- the embedded tracer retained generic driver-load and IRP markers;
- target-specific game/vendor/device/IOCTL strings remained absent from the tracer.

## Expected phone evidence

After one official authenticated launch:

`/storage/emulated/0/Documents/Winlator/TR_DIAG_v30_X3_BOUNDARY_FONT.zip`

Review should determine:

- whether an XEM image, especially x3, is opened or mapped;
- which version/environment queries precede or follow that decision;
- whether any service-control API is reached;
- whether Windows Fonts and registry substitution completed or rolled back;
- whether Korean UI glyphs render instead of squares;
- the unchanged protected-device and process-lifetime outcome.
