# v18K ARM64 runtime gate

This marker triggers the base-branch pull-request workflow after its registration.
No APK or runtime binary is changed.

Attempt 8 replaces only the x86_64 and i386 `winex11.so` files with the proven v18H XShape-enabled builds, then runs the exact Winlator shell on X servers with SHAPE enabled and disabled.
