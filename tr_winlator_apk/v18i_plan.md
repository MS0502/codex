# v18I Winlator rootfs compatibility profile

Evidence from the v18H device trace and extracted APK:

- paired wineserver path patch works and the desktop starts;
- `winebus.so` and `winepulse.so` require absent `libudev.so.1`;
- `wineusb.so` requires absent `libusb-1.0.so.0`;
- Winlator X server reports no SHAPE extension;
- Android rejects the nsiproxy NETLINK_ROUTE multicast bind with `errno 13`;
- `/etc/machine-id` is missing;
- `RpcSs` fails in the same startup interval as `winebus`.

## Implemented v18I scope

1. Preserve the exact paired `WINEPREFIX/.wineserver` patch from v18H.
2. Import pinned Ubuntu 22.04 ARM64 `libudev.so.1` and `libusb-1.0.so.0` packages into the Winlator rootfs.
3. Audit every built x86_64 Wine Unix module's direct `DT_NEEDED` names against the Proton tree, rootfs, injected native runtime and Box64 core wrappers.
4. Fail packaging when a critical desktop/service module (`winebus`, `winepulse`, `wineusb`, `nsiproxy`) still has an unresolved direct dependency; retain a report for optional modules.
5. Generate a valid 32-character lowercase machine-id on first rootfs start, persist it for the rootfs lifetime, and mirror it to `/var/lib/dbus/machine-id`.
6. Disable Wine's Linux rtnetlink notification subscription while retaining ordinary NSI enumeration. Android blocks the multicast bind; the patch does not fake a successful bind.
7. Compile Wine's X11 driver without XShape calls because the bundled Android X server does not advertise SHAPE. Normal rectangular window behavior remains available.
8. Preserve existing diagnostics and add `MACHINE_ID_READY` tracing without exposing the machine-id value.

## Explicit non-goals

- No game or XIGNCODE files are changed.
- No driver/service success result is fabricated.
- No XIGNCODE bypass, fake device or IOCTL implementation is introduced.
- Optional FFmpeg/GStreamer/Piper/AMDGPU integrations are reported but are not blindly copied into the rootfs.
- v18I is not ready for a game test until Explorer remains stable through repeated folder navigation.

## Device acceptance gate

The v18I APK may proceed to TalesRunner testing only after all of the following are observed on a new container:

- no `winebus` `c0000135` or service error 126;
- `RpcSs` starts or a new independent failure is captured;
- no repeated `Xlib: extension "SHAPE" missing` warnings;
- `/etc/machine-id` exists and remains unchanged after restart;
- Explorer remains responsive for two minutes and completes ten folder-entry/exit cycles without a five-second freeze.
