# Winlator TR Compat v29 driver-load trace and Korean support validation

## Status

Validated diagnostic build. Keep PR draft until one authenticated Z Fold6 run produces `TR_DIAG_v29_DRIVER_LOAD_KO.zip` and the result is reviewed.

The build is compatibility instrumentation. It does not fabricate or alter a driver, device, service, IOCTL result, authentication result, security state, or protected-process result. It does not log IRP payload buffers or credentials.

## Exact validated source and workflow

- source head: `597f5b5182237c099cd6f8fe7f496614aec503c9`
- registered workflow run: `31006499944`
- APK artifact: `WINLATOR_TR_COMPAT_V29_DRIVER_LOAD_KO_APK`
- APK artifact ID: `8930759446`
- APK artifact ZIP digest: `sha256:60634ce4b413552ecd6db3f5fcc901bda16717f9a9bbd2ebf089a409dd77d028`
- build-log artifact: `WINLATOR_TR_COMPAT_V29_DRIVER_LOAD_KO_BUILD_LOG`
- build-log artifact ID: `8930756276`
- build-log ZIP digest: `sha256:edebbe99aed9803b89928947ce249b7f20222d99ff4449d89547c4f9cd4f02e2`

## APK

- filename: `Winlator_TR_Compat_v29_DRIVER_LOAD_KO.apk`
- size: `167149573` bytes
- SHA-256: `00dce0cd3be538317c65672b6d58035b102ea8fdde2c828c52a5d1e2726048d9`
- package: `com.winlator.trcompat`
- versionCode: `28`
- versionName: `11.1-trcompat29-driver-load-ko`
- APK Signature Scheme v2: verified
- signer certificate SHA-256: `3819847878a333cc204bd93ab89a28a9867c066da5def40401d840fda9f9f017`

The package and signer are continuous with v26-v28, so it is intended to update the existing installation without deleting its container or Wine prefix.

## Existing-rootfs contract

- embedded rootfs SHA-256: `fd084ca23321b9ae357716f570a8d79143754ae1d182aa5082f2ecf26a87ca9b`
- v28 rootfs comparison: byte-identical
- rootfs reinstall forced: false
- container home preserved: true
- accepted existing ntoskrnl SHA-256: `bac18cca32f701c0315203ab489e2b557b78a2c72cf160256245c6015282c5c8`
- required active v29 ntoskrnl SHA-256: `e174c45a200457f6453c8465d6d70a0a9ef2dca35a6362b85f8f4d0747617bb5`

The runtime patcher accepts only the exact validated v28 active tracer as its baseline, creates and verifies a backup, stages and verifies the v29 binary, atomically replaces the target on the same filesystem, and verifies it again before the Wine environment starts.

## Generic native-driver loading trace

The v29 Wine `ntoskrnl.exe` records structural metadata for:

- `ZwLoadDriver()` request and service-open result;
- kernel/file-system driver service type and configuration;
- expanded and resolved driver image path;
- `LoadLibraryExW()` mapping result and error code;
- PE machine, subsystem, image size, section count, and entry-point RVA;
- `IoCreateDriver()` initialization;
- `DriverEntry` entry and return `NTSTATUS`;
- `IoCreateDevice()` name, type, characteristics, status, and object;
- `IoCreateSymbolicLink()` source, target, and result;
- existing generic IRP begin, completion, return, and unhandled outcomes.

The built PE contains no hard-coded strings for a game, vendor, protected-driver name, previously observed device name, or previously observed IOCTL value.

The driver trace does not modify return statuses, completion status, output buffers, or device objects.

## Static PE audit tool

`tr_wine_compat/audit_pe_driver.py` reports without execution:

- SHA-256 and size;
- PE machine, subsystem, entry point, image base, sections, and flags;
- import modules and imported functions;
- delay-import modules;
- Authenticode certificate-table presence and size;
- KMDF, Filter Manager, networking, storage, and HAL dependency indicators.

Wine's `ntoskrnl.exe` is correctly classified as an x86-64 PE DLL with Windows CUI subsystem 3. Native subsystem 1 is a separate expectation for actual `.sys` driver images.

## Korean support

The pinned rootfs contained Korean locale source, UTF-8/EUC-KR/CP949 charmaps, and Korean conversion modules, but lacked a compiled Korean locale and Hangul-capable scalable fonts.

v29 adds:

- deterministic `ko_KR.utf8` locale asset generated with glibc 2.39;
- locale asset SHA-256: `11add0c675b516bc1d27e8b9bde9cf05123ca9e5a86a757eb77b6e7edbee7d75`;
- runtime installation under `usr/lib/locale/ko_KR.utf8`;
- `LANG=ko_KR.UTF-8` and `LC_ALL=ko_KR.UTF-8` unless explicitly overridden;
- reuse of readable Korean/CJK fonts already supplied by Android under `/system/fonts`, `/product/fonts`, or `/vendor/fonts`;
- font source, destination, size, and SHA-256 diagnostics.

No third-party font is embedded or redistributed. Windows ACP/OEMCP registry values are not modified in v29. Existing forced `WINEESYNC=0` and `WINEFSYNC=0` compatibility behavior remains unchanged.

## Independent artifact checks

The downloaded artifact was independently checked after CI:

- APK ZIP integrity: no errors;
- APK SHA-256: exact match;
- rootfs SHA-256: exact match and byte-identical to v28;
- embedded v29 ntoskrnl SHA-256: exact match;
- embedded Korean locale asset SHA-256: exact match;
- locale contains `LC_CTYPE`, `LC_COLLATE`, `LC_TIME`, `LC_MESSAGES`, and the other expected glibc locale categories;
- DEX contains `KOREAN_SUPPORT_BEGIN`, `KOREAN_FONT_READY`, `NTOSKRNL_RUNTIME_VERIFY`, `ko_KR.UTF-8`, and `TR_DIAG_v29_DRIVER_LOAD_KO.zip` markers;
- target-specific forbidden markers were absent from the v29 Wine trace PE.

## Expected device evidence

After one official authenticated launch:

`/storage/emulated/0/Documents/Winlator/TR_DIAG_v29_DRIVER_LOAD_KO.zip`

A valid result should show:

- `NTOSKRNL_PATCH_REPLACED` or `NTOSKRNL_PATCH_ALREADY_CURRENT`;
- `NTOSKRNL_RUNTIME_VERIFY` with the required v29 SHA-256;
- `KOREAN_LOCALE_VERIFY`;
- `KOREAN_FONT_SUMMARY` and, when Android exposes a matching font, `KOREAN_FONT_READY`;
- `KOREAN_ENV LANG=ko_KR.UTF-8 LC_ALL=ko_KR.UTF-8`;
- generic `DRIVER_LOAD` records if any native driver service or image load is attempted;
- existing `IRP_TRACE` records for subsequent device operations.
