# v18K ARM64 runtime gate

This marker triggers the base-branch pull-request workflow after its registration.
No APK or runtime binary is changed.

Attempt 6 uses X.Org loopback TCP transport so the isolated chroot can prove `XOpenDisplay()` before Wine starts.
