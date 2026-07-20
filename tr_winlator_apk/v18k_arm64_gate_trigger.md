# v18K ARM64 runtime gate

This marker triggers the base-branch pull-request workflow after its registration.
No APK or runtime binary is changed.

Attempt 5 explicitly disables Xvfb access control and requires a native ARM64 `XOpenDisplay()` preflight before Wine starts.
