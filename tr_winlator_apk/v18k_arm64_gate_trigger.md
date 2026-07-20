# v18K ARM64 runtime gate

This marker triggers the base-branch pull-request workflow after its registration.
No APK or runtime binary is changed.

Attempt 2 adds the rootfs native ARM64 `LD_LIBRARY_PATH` required by the packaged Box64 executable.
