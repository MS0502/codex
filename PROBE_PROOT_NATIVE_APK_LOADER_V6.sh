#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DOWNLOADS="$HOME_DIR/storage/downloads"
CUSTOM_DIR="$HOME_DIR/proot-sysvipc-fixed-10780-bundled"
CUSTOM_PROOT="$CUSTOM_DIR/proot"
REPORT="$DOWNLOADS/PROOT_NATIVE_APK_LOADER_V6_REPORT.txt"

mkdir -p "$DOWNLOADS"
: >"$REPORT"

[ -x "$CUSTOM_PROOT" ] || {
  echo "ERROR: patched custom PRoot is missing: $CUSTOM_PROOT" | tee -a "$REPORT" >&2
  exit 2
}

# The working system PRoot does not execute a loader extracted into $HOME or
# $PREFIX/tmp. Termux supplies an executable loader from its APK native-lib dir.
# Discover that exact path from a short known-working system-PRoot process.
set +e
native_loader="$({
  proot-distro login debian -- /bin/sh -c \
    "awk '/libproot-loader[.]so/{print \\$NF; exit}' /proc/self/maps"
} 2>>"$REPORT" | tail -n 1)"
discover_rc=$?
set -e

{
  echo "PROOT NATIVE APK LOADER V6 PROBE"
  echo "================================"
  date -Iseconds
  echo "DISCOVER_EXIT=$discover_rc"
  echo "SYSTEM_PROOT=$(command -v proot || true)"
  echo "CUSTOM_PROOT=$CUSTOM_PROOT"
  echo "NATIVE_LOADER=$native_loader"
} >>"$REPORT"

if [ "$discover_rc" -ne 0 ] || [ -z "$native_loader" ] || [ ! -f "$native_loader" ]; then
  echo "NATIVE_LOADER_DISCOVERY_FAILED" | tee -a "$REPORT" >&2
  termux-media-scan "$REPORT" >/dev/null 2>&1 || true
  echo "REPORT=$REPORT"
  exit 3
fi

{
  file "$native_loader"
  sha256sum "$native_loader"
  file "$CUSTOM_PROOT"
  sha256sum "$CUSTOM_PROOT"
  echo
} >>"$REPORT" 2>&1

CUSTOM_PATH="$CUSTOM_DIR:${PATH:-$TERMUX_PREFIX/bin}"
selected="$(env PATH="$CUSTOM_PATH" sh -c 'command -v proot' 2>/dev/null || true)"
echo "PATH_SELECTED_PROOT=$selected" >>"$REPORT"
if [ "$selected" != "$CUSTOM_PROOT" ]; then
  echo "CUSTOM_PROOT_SELECTION_FAILED" | tee -a "$REPORT" >&2
  termux-media-scan "$REPORT" >/dev/null 2>&1 || true
  echo "REPORT=$REPORT"
  exit 4
fi

# Stage A: prove the custom PRoot can enter Debian when it uses the same
# executable APK-native loader as the working system PRoot. SysV IPC remains
# disabled here so this isolates loader compatibility from the helper patch.
set +e
env PATH="$CUSTOM_PATH" proot-distro login debian \
  --no-sysvipc \
  -e "PROOT_LOADER=$native_loader" \
  -- /bin/sh -c 'echo NATIVE_APK_LOADER_ENTRY_OK' \
  >>"$REPORT" 2>&1
entry_rc=$?
set -e
echo "ENTRY_EXIT=$entry_rc" >>"$REPORT"

if [ "$entry_rc" -ne 0 ] || ! grep -q '^NATIVE_APK_LOADER_ENTRY_OK$' "$REPORT"; then
  echo "NATIVE_APK_LOADER_ENTRY_FAILED"
  echo "REPORT=$REPORT"
  tail -n 100 "$REPORT" || true
  termux-media-scan "$REPORT" >/dev/null 2>&1 || true
  exit 5
fi

echo "NATIVE_APK_LOADER_ENTRY_OK"

# Stage B: enable normal PRoot SysV IPC and test one shmget/shmctl lifecycle.
set +e
env PATH="$CUSTOM_PATH" proot-distro login debian \
  -e "PROOT_LOADER=$native_loader" \
  -- bash -s >>"$REPORT" 2>&1 <<'PROBE_DEBIAN'
python3 - <<'PY'
import ctypes
import os
import sys

libc = ctypes.CDLL(None, use_errno=True)
IPC_PRIVATE = 0
IPC_CREAT = 0o1000
IPC_RMID = 0
shmid = libc.shmget(IPC_PRIVATE, 4096, IPC_CREAT | 0o600)
if shmid < 0:
    err = ctypes.get_errno()
    print(f"NATIVE_APK_LOADER_V6_SYSVIPC_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(31)
print(f"NATIVE_APK_LOADER_V6_SYSVIPC_SHMID={shmid}")
if libc.shmctl(shmid, IPC_RMID, None) != 0:
    err = ctypes.get_errno()
    print(f"NATIVE_APK_LOADER_V6_SYSVIPC_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(32)
print("NATIVE_APK_LOADER_V6_SYSVIPC_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e

{
  echo "SYSVIPC_EXIT=$probe_rc"
  echo "FINISHED=$(date -Iseconds)"
} >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

if [ "$probe_rc" -ne 0 ] || ! grep -q '^NATIVE_APK_LOADER_V6_SYSVIPC_PROBE_OK$' "$REPORT"; then
  echo "NATIVE_APK_LOADER_V6_SYSVIPC_PROBE_FAILED"
  echo "REPORT=$REPORT"
  tail -n 120 "$REPORT" || true
  exit 6
fi

echo "NATIVE_APK_LOADER_V6_SYSVIPC_PROBE_OK"
echo "REPORT=$REPORT"
