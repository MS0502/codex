#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
DOWNLOADS="$HOME_DIR/storage/downloads"
CUSTOM_DIR="$HOME_DIR/proot-sysvipc-fixed-v2"
CUSTOM_PROOT="$CUSTOM_DIR/proot"
REPORT="$DOWNLOADS/PROOT_SYSVIPC_PATH_OVERRIDE_V3_REPORT.txt"

mkdir -p "$DOWNLOADS"
: >"$REPORT"

[ -x "$CUSTOM_PROOT" ] || {
  echo "ERROR: missing custom PRoot: $CUSTOM_PROOT" | tee -a "$REPORT" >&2
  exit 2
}

CUSTOM_PATH="$CUSTOM_DIR:${PATH:-/data/data/com.termux/files/usr/bin}"
selected="$(env PATH="$CUSTOM_PATH" sh -c 'command -v proot' 2>/dev/null || true)"

{
  echo "PROOT SYSVIPC PATH OVERRIDE V3 PROBE"
  echo "===================================="
  date -Iseconds
  echo "PROOT_DISTRO_VERSION=$(dpkg-query -W -f='${Version}' proot-distro 2>/dev/null || true)"
  echo "SYSTEM_PROOT=$(command -v proot || true)"
  echo "CUSTOM_PROOT=$CUSTOM_PROOT"
  echo "CUSTOM_PROOT_SHA256=$(sha256sum "$CUSTOM_PROOT" | awk '{print $1}')"
  echo "PATH_SELECTED_PROOT=$selected"
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
  --bind "$DOWNLOADS:/mnt/downloads" \
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
    print(f"PATH_OVERRIDE_V3_SYSVIPC_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(31)

print(f"PATH_OVERRIDE_V3_SYSVIPC_SHMID={shmid}")
rc = libc.shmctl(shmid, IPC_RMID, None)
if rc != 0:
    err = ctypes.get_errno()
    print(f"PATH_OVERRIDE_V3_SYSVIPC_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(32)

print("PATH_OVERRIDE_V3_SYSVIPC_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e

{
  echo "PROBE_EXIT=$probe_rc"
  echo "FINISHED=$(date -Iseconds)"
} >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

if [ "$probe_rc" -ne 0 ] || ! grep -q '^PATH_OVERRIDE_V3_SYSVIPC_PROBE_OK$' "$REPORT"; then
  echo "PATH_OVERRIDE_V3_SYSVIPC_PROBE_FAILED"
  echo "REPORT=$REPORT"
  tail -n 100 "$REPORT" || true
  exit 4
fi

echo "PATH_OVERRIDE_V3_SYSVIPC_PROBE_OK"
echo "REPORT=$REPORT"
