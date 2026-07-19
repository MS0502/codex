# v18I Winlator rootfs compatibility profile

Evidence from the v18H device trace and extracted APK:

- paired wineserver path patch works and the desktop starts;
- `winebus.so` and `winepulse.so` require absent `libudev.so.1`;
- `wineusb.so` requires absent `libusb-1.0.so.0`;
- `winedmo.so` requires absent FFmpeg 58 libraries;
- `winegstreamer.so` requires absent `libgstgl-1.0.so.0`;
- `protontts.so` requires absent `libpiper.so`;
- `amd_ags_x64.so` requires absent `libdrm_amdgpu.so.1`;
- Winlator X server reports no SHAPE extension;
- Android blocks nsiproxy NETLINK_ROUTE multicast bind;
- `/etc/machine-id` is missing.

v18I must keep the exact v18H wineserver fix, disable unsupported optional host integrations at Wine configure time, disable the Linux netlink notification path while preserving enumeration, compile without XShape, generate a per-install machine-id, and fail packaging if any built Unix module has an unresolved direct rootfs dependency.
