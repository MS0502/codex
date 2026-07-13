#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
XSOCK="${TMPDIR:-${TERMUX_PREFIX}/tmp}/.X11-unix"
DOWNLOADS="${HOME}/storage/downloads"
TR_DIR="${DOWNLOADS}/TR_KR_LOCAL"
TOKEN="${TR_DIR}/tr_access_token.tmp"
WINLATOR_RUNTIME="${HOME}/winlator-11.1-wine-root"
CUSTOM_PROOT="${HOME}/proot-sysvipc-fixed/proot"
STATUS="${DOWNLOADS}/MOBOX_TR_WINE1010_CUSTOM_PROOT_SYSVIPC_V5_STATUS.txt"
PROBE="${DOWNLOADS}/MOBOX_TR_CUSTOM_PROOT_SYSVIPC_V5_PROBE.txt"

[ -S "$XSOCK/X0" ] || { echo "ERROR: Termux:X11 is not reachable" >&2; exit 2; }
[ -s "$TOKEN" ] || {
  echo "AUTH_TOKEN_MISSING_OR_EMPTY"
  echo "Order: official site Game Start -> TR_AUTH_BRIDGE.py -> this script"
  exit 3
}
[ -x "$WINLATOR_RUNTIME/opt/wine/bin/wine" ] || {
  echo "ERROR: extracted Winlator Wine 10.10 is missing" >&2
  exit 4
}
[ -x "$CUSTOM_PROOT" ] || {
  echo "ERROR: custom patched PRoot is missing" >&2
  exit 5
}
[ -f "$TR_DIR/TR_LOGIN_AND_RUN_FIXED.bat" ] || {
  echo "ERROR: TR_LOGIN_AND_RUN_FIXED.bat is missing" >&2
  exit 6
}

# The first patched build relied on TERMUX_EXEC__PROC_SELF_EXE, but the parent
# shell may leave a stale relative script path there. Force the exact absolute
# custom-PRoot path for both probe and game runs so the helper branch can
# re-exec the real binary through Android's linker64.
export TERMUX_EXEC__PROC_SELF_EXE="$CUSTOM_PROOT"

set +e
TERMUX_EXEC__PROC_SELF_EXE="$CUSTOM_PROOT" \
PD_PROOT_BIN="$CUSTOM_PROOT" \
proot-distro login debian \
  --bind "$DOWNLOADS:/mnt/downloads" \
  -- bash -s >"$PROBE" 2>&1 <<'PROBE_DEBIAN'
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
    print(f"CUSTOM_PROOT_SYSVIPC_V5_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(51)
print(f"CUSTOM_PROOT_SYSVIPC_V5_SHMID={shmid}")
if libc.shmctl(shmid, IPC_RMID, None) != 0:
    err = ctypes.get_errno()
    print(f"CUSTOM_PROOT_SYSVIPC_V5_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(52)
print("CUSTOM_PROOT_SYSVIPC_V5_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e
termux-media-scan "$PROBE" >/dev/null 2>&1 || true
if [ "$probe_rc" -ne 0 ] || ! grep -q '^CUSTOM_PROOT_SYSVIPC_V5_PROBE_OK$' "$PROBE"; then
  echo "CUSTOM_PROOT_SYSVIPC_V5_PROBE_FAILED"
  echo "REPORT=$PROBE"
  tail -n 80 "$PROBE" || true
  exit 7
fi

echo "CUSTOM_PROOT_SYSVIPC_V5_PROBE_OK"

set +e
TERMUX_EXEC__PROC_SELF_EXE="$CUSTOM_PROOT" \
PD_PROOT_BIN="$CUSTOM_PROOT" \
proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$XSOCK:/tmp/.X11-unix" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  --bind "$WINLATOR_RUNTIME:/mnt/winlator-runtime" \
  -- bash -s <<'DEBIAN'
set +e

BOX=/root/box64/build/box64
WROOT=/mnt/winlator-runtime/opt/wine
WINE="$WROOT/bin/wine"
WINESERVER="$WROOT/bin/wineserver"
WINEPREFIX=/root/.wine-mobox-phase2b-wine1010
TR_BATCH='D:\TR_KR_LOCAL\TR_LOGIN_AND_RUN_FIXED.bat'
STATUS=/mnt/downloads/MOBOX_TR_WINE1010_CUSTOM_PROOT_SYSVIPC_V5_STATUS.txt
COMPILED_TMP=/data/data/com.winlator/files/rootfs/tmp

export DISPLAY=:0
export XDG_RUNTIME_DIR=/tmp/runtime-box64
mkdir -p "$XDG_RUNTIME_DIR" "$COMPILED_TMP" "$WINEPREFIX/dosdevices"
chmod 700 "$XDG_RUNTIME_DIR"
chmod 1777 "$COMPILED_TMP"
ln -sfn /mnt/downloads "$WINEPREFIX/dosdevices/d:"

export TMPDIR="$COMPILED_TMP"
export TMP="$COMPILED_TMP"
export TEMP="$COMPILED_TMP"
export WINEPREFIX
export WINEARCH=win64
export WINEESYNC=1
export WINEDEBUG=-all
export WINEDLLOVERRIDES="winemenubuilder.exe=d"
export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_DYNAREC=1
export BOX64_LOG=0
export BOX64_PATH="$WROOT/bin"
export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu:/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"
export BOX64_DYNACACHE=1
export BOX64_DYNACACHE_FOLDER=/root/.cache/box64-tr-v4-wine1010-custom-proot-sysvipc-v5
mkdir -p "$BOX64_DYNACACHE_FOLDER"
chmod 700 "$BOX64_DYNACACHE_FOLDER"

"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true
sleep 2

{
  echo "MOBOX TALESRUNNER WINE 10.10 CUSTOM PROOT SYSVIPC V5"
  echo "====================================================="
  date -Iseconds
  echo "WINE_VERSION=$("$BOX" "$WINE" --version 2>&1 | tail -1)"
  echo "WINEPREFIX=$WINEPREFIX"
  echo "WINEESYNC=$WINEESYNC"
  echo "PROOT_SYSVIPC=enabled"
  echo "CUSTOM_PROOT_SELFEXE_FIX=1"
  echo "TERMUX_EXEC_PROC_SELF_FORCED=1"
  echo "BOX64_DYNACACHE_FOLDER=$BOX64_DYNACACHE_FOLDER"
  echo "WINEDEBUG=$WINEDEBUG"
  echo "BASE_PREFIX_UNMODIFIED=1"
  echo
} >"$STATUS"

(
  previous=""
  i=0
  while [ "$i" -lt 1200 ]; do
    now="$(date -Iseconds)"
    current=""
    for procdir in /proc/[0-9]*; do
      [ -r "$procdir/comm" ] || continue
      pid="${procdir##*/}"
      comm="$(cat "$procdir/comm" 2>/dev/null || true)"
      lower="$(printf '%s' "$comm" | tr '[:upper:]' '[:lower:]')"
      case "$lower" in
        talesrunner.exe|trgame.exe|xldr*|xigncode*|xm.exe|x3.xem)
          current="${current}${pid} ${comm}\n"
          ;;
      esac
    done
    if [ "$current" != "$previous" ]; then
      {
        echo "=== TARGETS $now ==="
        printf '%b' "$current"
      } >>"$STATUS"
      previous="$current"
    fi
    i=$((i + 1))
    sleep 0.5
  done
) &
MONITOR=$!

cd /mnt/downloads/TR_KR_LOCAL
launch_status=255
"$BOX" "$WINE" cmd /c "$TR_BATCH" >/dev/null 2>&1
captured_status=$?
case "$captured_status" in
  ''|*[!0-9]*) launch_status=255 ;;
  *) launch_status="$captured_status" ;;
esac

sleep 3
kill "$MONITOR" 2>/dev/null || true
wait "$MONITOR" 2>/dev/null || true
{
  echo
  echo "LAUNCH_EXIT=$launch_status"
  echo "FINISHED=$(date -Iseconds)"
} >>"$STATUS"

"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true
exit 0
DEBIAN
wrapper_status=$?
set -e
termux-media-scan "$STATUS" >/dev/null 2>&1 || true

echo "CUSTOM_PROOT_SYSVIPC_V5_WRAPPER_EXIT=$wrapper_status"
echo "STATUS=$STATUS"
echo "PROBE=$PROBE"
exit "$wrapper_status"
