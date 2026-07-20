# v18K ARM64 runtime gate

This marker triggers the base-branch pull-request workflow after its registration.
No APK or runtime binary is changed.

Attempt 11 builds Xvfb with `shape.c` and the SHAPE extension registration removed, proves `xdpyinfo` has no SHAPE entry, then runs v18J baseline and the two-file XShape-restored candidate on that server.
