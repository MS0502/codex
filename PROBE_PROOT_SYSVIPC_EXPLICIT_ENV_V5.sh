#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DOWNLOADS="$HOME_DIR/storage/downloads"
CUSTOM_DIR="$HOME_DIR/proot-sysvipc-fixed-v2"
CUSTOM_PROOT="$CUSTOM_DIR/proot"
CUSTOM_LOADER="$CUSTOM_DIR/loader"
CUSTOM_LOADER32="$CUSTOM_DIR/loader32"
PROOT_TMP="$HOME_DIR/.cache/proot-sysvipc-v5-tmp"
REPORT="$DOWNLOADS/PROOT_SYSVIPC_EXPLICIT_ENV_V5_REPORT.txt"

mkdir -p "$DOWNLOADS" "$PROOT_TMP"
chmod 700 "$PROOT_TMP"
: >"$REPORT"

for required in "$CUSTOM_PROOT" "$CUSTOM_LOADER"; do
  [ -x "$required" ] || {
    echo "ERROR: missing executable: $required" | tee -a "$REPORT" >&2
    exit 2
  }
done

CUSTOM_PATH="$CUSTOM_DIR:${PATH:-$TERMUX_PREFIX/bin}"
selected="$(env PATH="$CUSTOM_PATH" sh -c 'command -v proot' 2>/dev/null || true)"

{
  echo "PROOT SYSVIPC EXPLICIT ENV V5 PROBE"
  echo "===================================="
  date -Iseconds
  echo "PROOT_DISTRO_VERSION=$(dpkg-query -W -f='${Version}' proot-distro 2>/dev/null || true)"
  echo "SYSTEM_PROOT=$(command -v proot || true)"
  echo "CUSTOM_PROOT=$CUSTOM_PROOT"
  echo "PATH_SELECTED_PROOT=$selected"
  echo "CUSTOM_PROOT_SHA256=$(sha256sum "$CUSTOM_PROOT" | awk '{print $1}')"
  echo "CUSTOM_LOADER=$CUSTOM_LOADER"
  echo "CUSTOM_LOADER_SHA256=$(sha256sum "$CUSTOM_LOADER" | awk '{print $1}')"
  if [ -x "$CUSTOM_LOADER32" ]; then
    echo "CUSTOM_LOADER32=$CUSTOM_LOADER32"
    echo "CUSTOM_LOADER32_SHA256=$(sha256sum "$CUSTOM_LOADER32" | awk '{print $1}')"
  fi
  echo "PROOT_TMP_DIR=$PROOT_TMP"
  echo "PATCH_MARKER_COUNT=$(strings "$CUSTOM_PROOT" | grep -c '\[PROOT_SHM_HELPER_V2\]' || true)"
  echo
} >>"$REPORT"

if [ "$selected" != "$CUSTOM_PROOT" ]; then
  echo "PATH_OVERRIDE_SELECTION_FAILED" | tee -a "$REPORT" >&2
  termux-media-scan "$REPORT" >/dev/null 2>&1 || true
  exit 3
fi

set +e
env PATH="$CUSTOM_PATH" proot-distro login debian \
  -e "PROOT_LOADER=$CUSTOM_LOADER" \
  -e "PROOT_LOADER_32=$CUSTOM_LOADER32" \
  -e "PROOT_TMP_DIR=$PROOT_TMP" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  -- bash -s >>"$REPORT" 2>&1 <<'PROBE_DEBIAN'
python3 - <<'PY'
import ctypes
import os
import sys

print(f"GUEST_PROOT_LOADER={os.environ.get('PROOT_LOADER')}")
print(f"GUEST_PROOT_LOADER_32={os.environ.get('PROOT_LOADER_32')}")
print(f"GUEST_PROOT_TMP_DIR={os.environ.get('PROOT_TMP_DIR')}")

libc = ctypes.CDLL(None, use_errno=True)
IPC_PRIVATE = 0
IPC_CREAT = 0o1000
IPC_RMID = 0

shmid = libc.shmget(IPC_PRIVATE, 4096, IPC_CREAT | 0o600)
if shmid < 0:
    err = ctypes.get_errno()
    print(f"EXPLICIT_ENV_V5_SYSVIPC_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(31)

print(f"EXPLICIT_ENV_V5_SYSVIPC_SHMID={shmid}")
rc = libc.shmctl(shmid, IPC_RMID, None)
if rc != 0:
    err = ctypes.get_errno()
    print(f"EXPLICIT_ENV_V5_SYSVIPC_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(32)

print("EXPLICIT_ENV_V5_SYSVIPC_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e

{
  echo "PROBE_EXIT=$probe_rc"
  echo "FINISHED=$(date -Iseconds)"
} >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

if [ "$probe_rc" -ne 0 ] || ! grep -q '^EXPLICIT_ENV_V5_SYSVIPC_PROBE_OK$' "$REPORT"; then
  echo "EXPLICIT_ENV_V5_SYSVIPC_PROBE_FAILED"
  echo "REPORT=$REPORT"
  tail -n 140 "$REPORT" || true
  exit 4
fi

echo "EXPLICIT_ENV_V5_SYSVIPC_PROBE_OK"
echo "REPORT=$REPORT"
