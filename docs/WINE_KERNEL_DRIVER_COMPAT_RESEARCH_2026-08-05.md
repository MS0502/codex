# Wine native Windows kernel-driver compatibility research — 2026-08-05

## Scope

This document records prior art and the next diagnostic implementation boundary for native Windows `.sys` loading under Wine/Winlator.

The work is compatibility research only. It must not fabricate a device, driver, service, IOCTL result, security state, or authentication result. It must not inspect or log IRP payload buffers, credentials, tokens, or game-specific secrets.

## Confirmed Wine architecture

Wine does not execute a driver in a real Windows Ring-0 kernel. Native `.sys` PE images are loaded into the user-space `winedevice.exe` service process and receive emulated NT kernel objects and APIs from Wine's `ntoskrnl.exe` implementation.

The pinned Wine 10.10 source used by this branch already provides the following pipeline:

1. `winedevice.exe` receives a service control request.
2. `device_handler()` calls `ZwLoadDriver()` or `ZwUnloadDriver()`.
3. `ZwLoadDriver()` validates the service as `SERVICE_KERNEL_DRIVER` or `SERVICE_FILE_SYSTEM_DRIVER`.
4. `load_driver()` resolves the service `ImagePath` and calls `LoadLibraryExW()` on the `.sys` image.
5. `init_driver()` locates the PE entry point and calls the driver's `DriverEntry` function.
6. `IoCreateDriver()` initializes `DRIVER_OBJECT`, `DriverExtension`, and default dispatch entries.
7. Drivers may create `DEVICE_OBJECT`s and symbolic links through `IoCreateDevice()` and `IoCreateSymbolicLink()`.
8. Wine dispatches create, close, read, write, flush, file-system-control, and device-control IRPs through the registered `MajorFunction[]` table.

Pinned source:

- Winlator app: `brunodev85/winlator-app@c2f4ad4534f4637b543a9a3b085e28f50cf6d01c`
- Wine: `brunodev85/wine-10.10-custom@494fb8f4a30fcb9d0b9c00f72a7f2b7a17e787b0`

Primary source files:

- `programs/winedevice/device.c`
- `dlls/ntoskrnl.exe/ntoskrnl.c`
- `dlls/ntoskrnl.exe/tests/driver.c`

## Prior research cases

### Native DRM and protection drivers

Wine has previously loaded native `.sys` images far enough to exercise relocation, import resolution, `DriverEntry`, device creation, and dispatch setup. Examples discussed in Wine development and bug archives include CrypKey, SDProtect, StarForce, Protect DiSC, Sentinel HASP, Norton/Symantec, VeraCrypt, nProtect/Tachyon, Denuvo Anti-Cheat, SteelSeries, and miHoYo protection drivers.

The recurring failure classes were:

- missing or semantically incomplete `ntoskrnl` APIs;
- missing framework modules such as `wdfldr.sys`, `fltmgr.sys`, or `netio.sys`;
- incomplete layered-device and cross-driver pointer semantics;
- unsupported privileged CPU instructions or physical-memory access;
- incomplete file-system filter manager support;
- unsupported process, thread, image, registry, and object callbacks;
- user-space Wine being unable to represent actual Windows kernel trust state.

### File-system filter progress

Wine development has continued to add Filter Manager functions. This is evidence that native-driver compatibility is active incremental work rather than a completely abandoned subsystem. The correct method is to identify a general missing semantic, add a general implementation and test, and avoid target-specific success paths.

### NDISwrapper and ReactOS

NDISwrapper demonstrated that a narrow Windows-driver ABI can be hosted on Linux when the hardware class and API surface are tightly constrained. ReactOS demonstrates the opposite end: broad Windows-driver compatibility requires coherent I/O, object, memory, PnP, security, HAL, and driver-framework implementations.

These projects are useful architectural references but are not directly reusable as an Android ARM64 solution for arbitrary x86-64 drivers.

### NTSYNC design lesson

Wine's NTSYNC work shows a practical pattern: implement a specific missing NT semantic with a safe Linux-kernel backend instead of placing arbitrary Windows driver code in the Linux kernel. Any future host-kernel assistance in this project must follow that narrow, general-purpose model.

## Current device evidence

The validated v28 run established:

- authentication and launcher execution succeeded;
- the protected child process was created;
- repeated opens of a required NT device name occurred;
- no corresponding device object was present;
- no target driver load, `DriverEntry`, or `IoCreateDevice` event was visible in the existing trace;
- the child exited with `-1` while the loader cleaned up normally.

The next unresolved question is earlier than IRP dispatch:

> Was a driver service or `.sys` image ever installed or loaded, and if so, exactly where did the generic Wine loading pipeline stop?

## v29 diagnostic objectives

### Wine load-pipeline trace

Record only structural metadata for:

- `winedevice` service control start/stop;
- requested service key path;
- service open result and service type;
- configured `ImagePath` after environment expansion;
- resolved DOS path used for loading;
- `LoadLibraryExW()` result and `GetLastError()`;
- PE machine, subsystem, image size, entry-point RVA, and imported module names;
- `IoCreateDriver()` entry and result;
- `DriverEntry` address, entry, return `NTSTATUS`, and exception boundary;
- `IoCreateDevice()` name, type, characteristics, status, and resulting object pointer;
- `IoCreateSymbolicLink()` source, target, and status;
- `IoAttachDevice*()` calls and current implementation result;
- callback-registration API calls already implemented or stubbed;
- `DriverUnload` registration and unload outcome.

Do not record:

- input/output buffer bytes;
- authentication values;
- process memory contents;
- target-specific names in compiled instrumentation;
- hard-coded service, device, driver, vendor, game, or IOCTL identifiers.

### Static PE driver audit

A separate host-side tool will enumerate `.sys` files without executing them and report:

- SHA-256 and file size;
- PE machine and subsystem;
- section table and entry-point RVA;
- imported modules and functions;
- delay imports when present;
- load-configuration presence;
- Authenticode certificate-table presence and size;
- WDM/KMDF indicators such as `wdfldr.sys`, `WdfVersionBind`, and WDF import modules;
- Filter Manager, networking, storage, and HAL dependency indicators.

The audit must not disassemble protected logic or attempt to derive expected security responses.

### Synthetic test driver

Before interpreting a real protected launch, CI must prove the tracing path with Wine's own harmless test driver or an equivalent minimal WDM test driver:

- service creation;
- `ZwLoadDriver`;
- `.sys` image mapping;
- `DriverEntry`;
- `IoCreateDevice`;
- symbolic link creation;
- create/close IRPs;
- one buffered IOCTL round trip;
- unload.

## Korean text defect found in the pinned rootfs

The v28 rootfs was audited directly.

Present:

- `/usr/bin/localedef`;
- Korean locale source `/usr/share/i18n/locales/ko_KR`;
- `UTF-8`, `EUC-KR`, and `CP949` charmaps;
- Korean gconv modules.

Missing:

- compiled `/usr/lib/locale/ko_KR.utf8`;
- Korean/CJK TrueType or OpenType fonts.

Only six scalable fonts are present, and none provide Hangul coverage. The compiled locales are limited to `en_US.utf8`, `pt_BR.utf8`, and `ru_RU.utf8`.

This is sufficient to explain both common failure modes:

1. missing-glyph squares or blank Hangul due to absent CJK fonts;
2. incorrect ANSI-code-page behavior in an existing prefix created under a non-Korean locale.

## v29 Korean compatibility plan

The Korean fix is kept independent from driver behavior.

1. Compile `ko_KR.utf8` into the rootfs during the deterministic build.
2. Verify rootfs and build-host glibc compatibility before accepting the generated locale.
3. Set `LANG=ko_KR.UTF-8` and `LC_ALL=ko_KR.UTF-8` before the Wine environment starts, unless the user explicitly overrides them.
4. Do not redistribute a third-party font file. At runtime, copy a readable Korean-capable font already present in Android `/system/fonts`, `/product/fonts`, or `/vendor/fonts` into the app-private rootfs font directory.
5. Record selected source path, destination path, size, and SHA-256 in diagnostics.
6. Refuse to alter Windows locale registry values automatically in the first build. First verify whether host locale plus a Hangul-capable font fixes rendering. Registry ACP/OEMCP changes are higher-risk for an existing prefix and require separate evidence.
7. Driver-load traces must be byte-identical regardless of whether the Korean font copy succeeds.

## Decision gates after one v29 phone run

- No service key or `.sys` access: the user-mode loader did not attempt native-driver installation; Wine API implementation is not yet the limiting factor.
- Service exists but image path/file is absent: installation/path translation defect.
- Image maps but an import module is missing: classify WDM, KMDF, Filter Manager, networking, storage, or HAL dependency.
- `DriverEntry` returns a documented failure after a general API call: candidate for general Wine implementation and synthetic test.
- Device and symbolic link are created but open fails: object namespace or IRP path defect.
- Driver requires privileged instructions, physical memory, real kernel callbacks, or Windows trust state: structural Wine boundary.

## References

Primary references used for the architecture and prior-art review:

- Wine source tree: https://gitlab.winehq.org/wine/wine
- Pinned custom Wine source: https://github.com/brunodev85/wine-10.10-custom
- Winlator source: https://github.com/brunodev85/winlator-app
- Wine bug and development archives: https://list.winehq.org/
- ReactOS documentation: https://reactos.org/
- NDISwrapper project archive: https://sourceforge.net/projects/ndiswrapper/
- Linux NTSYNC discussions and implementation history in Wine and Linux kernel mailing lists.
