# v18K ARM64 runtime gate

This marker triggers the base-branch pull-request workflow after its registration.
No APK or runtime binary is changed.

Attempt 7 applies `rootfs_patches.tzst`, uses `/home/xuser/.wine`, and runs Winlator's exact `winhandler.exe` plus `wfm.exe` shell command.
