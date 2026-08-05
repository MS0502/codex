# TalesRunner Winlator v27 generic IRP trace validation

## Status

The v27 diagnostic APK built and passed all registered gates. This is an observation build, not a security-result bypass or a claim that TalesRunner now runs.

## Exact inputs

- branch head: `999d0a69f272cfc495b3e16ff1ea60c21c4b45dd`
- workflow run: `30995417471`
- upstream Winlator: `c2f4ad4534f4637b543a9a3b085e28f50cf6d01c`
- Wine source: `brunodev85/wine-10.10-custom@494fb8f4a30fcb9d0b9c00f72a7f2b7a17e787b0`
- package: `com.winlator.trcompat`
- version: `11.1-trcompat27-irp-trace`

## Artifact

- artifact: `WINLATOR_TR_COMPAT_V27_IRP_TRACE_APK`
- artifact ID: `8926125425`
- artifact digest: `sha256:0ee5dc27194ce5026cfa4cb81a0e6888929b05d0c26d6810fc05d316bbe8cb4f`
- APK: `Winlator_TR_Compat_v27_IRP_TRACE.apk`
- APK size: `166745171` bytes
- APK SHA-256: `e757e67983334991d6b06251f30a24004c192750044d3f8bb4238bf20e035ada`
- APK Signature Scheme v2: verified
- signer certificate SHA-256: `3819847878a333cc204bd93ab89a28a9867c066da5def40401d840fda9f9f017`

The signer is identical to v26, so v27 is installed as an update over v26 without deleting the app or its container.

## Runtime delta proof

Independent extraction compared all 3,308 v26/v27 rootfs entries, including paths, object types, modes, symlink targets, sizes, and SHA-256 values.

- added paths: 0
- removed paths: 0
- changed paths: exactly 1
- changed path: `opt/wine/lib/wine/x86_64-windows/ntoskrnl.exe`

Hashes:

- v26 rootfs: `5d500065842618bb3ed72858c36ca9807446d8cef085c1394e32d41f7027f60b`
- v27 rootfs: `fd084ca23321b9ae357716f570a8d79143754ae1d182aa5082f2ecf26a87ca9b`
- v26 ntoskrnl: `ac89fd958b5a8a0f133cfe412e66a78395828bf3e237dc74868a2e39845f3c6c`
- v27 ntoskrnl: `bac18cca32f701c0315203ab489e2b557b78a2c72cf160256245c6015282c5c8`

The Box64 archive and native Box64 hashes remain the exact v26 values.

## Instrumentation

The generic Wine ntoskrnl trace records:

- IRP major and minor function;
- driver name and dispatch pointer;
- device type, flags and characteristics;
- IOCTL method, access, device type and function decomposition;
- dispatch return status;
- final `IoStatus.Status`, `Information`, pending and completion state;
- unhandled-IRP outcome.

It does not read or record input/output buffer contents. It does not change return statuses, output buffers, service outcomes, driver outcomes, or device outcomes. The source and built component contain no target-specific markers for XIGNCODE, xhunter, WELLBIA, or the previously observed IOCTL value.

## Device output

Expected evidence after one official authenticated launch:

`/storage/emulated/0/Documents/Winlator/TR_DIAG_v27_IRP_TRACE.zip`

This evidence is required before deciding whether the failure is a general Wine compatibility omission that can be implemented normally or a real Windows kernel/security requirement that cannot be provided by Android userspace Wine without fabrication.
