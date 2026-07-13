#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
TERMUX_TMPDIR="${TMPDIR:-${TERMUX_PREFIX}/tmp}"
ROOT="${TERMUX_PREFIX}/glibc"
XSOCK="${TERMUX_TMPDIR}/.X11-unix"
DOWNLOADS="${HOME}/storage/downloads"
MODE="${1:-dynarec}"

case "$MODE" in
  dynarec|interp) ;;
  *)
    echo "Usage: $0 {dynarec|interp}" >&2
    exit 64
    ;;
esac

if [ ! -S "$XSOCK/X0" ]; then
  echo "ERROR: Termux:X11 server is not reachable at $XSOCK/X0" >&2
  exit 2
fi

if [ ! -f "$DOWNLOADS/TR_KR_LOCAL/TR_LOGIN_AND_RUN_FIXED.bat" ]; then
  echo "ERROR: TR_LOGIN_AND_RUN_FIXED.bat not found" >&2
  exit 3
fi

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$XSOCK:/tmp/.X11-unix" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  --env MOBOX_DIAG_MODE="$MODE" \
  -- bash -s <<'DEBIAN'
set +e

BOX=/root/box64/build/box64
WROOT=/opt/mobox/wine-9.3-vanilla-wow64
WINE="$WROOT/bin/wine"
WINESERVER="$WROOT/bin/wineserver"
WINEPREFIX=/root/.wine-mobox-execmod
TR_BATCH='D:\TR_KR_LOCAL\TR_LOGIN_AND_RUN_FIXED.bat'
MODE="${MOBOX_DIAG_MODE:-dynarec}"
RAW=/tmp/mobox_tr_compat_diag_raw.txt
PROC=/tmp/mobox_tr_compat_diag_proc.txt
MAPS=/tmp/mobox_tr_compat_diag_maps.txt
COMBINED=/tmp/mobox_tr_compat_diag_combined.txt
OUT="/mnt/downloads/TR_KR_LOCAL/MOBOX_TR_COMPAT_${MODE^^}_SANITIZED.txt"

cleanup() {
  rm -f "$RAW" "$PROC" "$MAPS" "$COMBINED"
}
trap cleanup EXIT

export DISPLAY=:0
export XDG_RUNTIME_DIR=/tmp/runtime-box64
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

export WINEPREFIX
export WINEARCH=win64
export WINEDLLOVERRIDES="winemenubuilder.exe=d"
export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_PATH="$WROOT/bin"
export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu"
export BOX64_LOG=0

if [ "$MODE" = interp ]; then
  export BOX64_DYNAREC=0
else
  export BOX64_DYNAREC=1
fi

mkdir -p "$WINEPREFIX/dosdevices"
ln -sfn /mnt/downloads "$WINEPREFIX/dosdevices/d:"

pkill -f '[w]ineserver' 2>/dev/null
sleep 2

: >"$RAW"
: >"$PROC"
: >"$MAPS"

(
  i=0
  captured=""
  while [ "$i" -lt 360 ]; do
    printf '\n=== PROCESS SAMPLE %03d %s ===\n' "$i" "$(date -Iseconds)"
    ps -eo pid,ppid,rss,vsz,stat,comm | grep -Ei 'wine|xldr|tales|xign|services|explorer|winedevice|rpcss|plugplay|svchost' | grep -v grep || true

    for pid in $(pgrep -x talesrunner.exe 2>/dev/null); do
      case " $captured " in
        *" $pid "*) ;;
        *)
          if [ -r "/proc/$pid/maps" ]; then
            {
              echo "=== TALESRUNNER MAPS pid=$pid time=$(date -Iseconds) ==="
              cat "/proc/$pid/maps"
            } >>"$MAPS"
            captured="$captured $pid"
          fi
          ;;
      esac
    done

    i=$((i + 1))
    sleep 0.5
  done
) >"$PROC" 2>&1 &
SAMPLER=$!

cd /mnt/downloads/TR_KR_LOCAL
WINEDEBUG='-all,+timestamp,+pid,+tid,+seh,+loaddll' \
  timeout 180s "$BOX" "$WINE" cmd /c "$TR_BATCH" >"$RAW" 2>&1
RUN_RESULT=$?

kill "$SAMPLER" 2>/dev/null
wait "$SAMPLER" 2>/dev/null

{
  echo "=== DIAGNOSTIC MODE ==="
  echo "MODE=$MODE"
  echo "BOX64_DYNAREC=$BOX64_DYNAREC"
  echo
  echo "=== RUN RESULT ==="
  echo "RUN_RESULT=${RUN_RESULT:-unknown}"
  echo
  echo "=== WINE LOG ==="
  cat "$RAW"
  echo
  echo "=== TALESRUNNER PROCESS MAPS (NO COMMAND LINES) ==="
  cat "$MAPS"
  echo
  echo "=== PROCESS SAMPLES (NO COMMAND LINES) ==="
  cat "$PROC"
} >"$COMBINED"

python3 - "$COMBINED" "$OUT" <<'PY'
from pathlib import Path
import re
import sys

src = Path(sys.argv[1]).read_text(errors='replace')

# Remove complete Box64 argv records containing the authentication argument.
src = re.sub(
    r'(?im)^.*argv\[\d+\]="-authkey:[^"]*".*$',
    '[AUTH ARGUMENT REDACTED]',
    src,
)

patterns = [
    (r'(?i)trlauncher://\S+', 'trlauncher://<REDACTED>'),
    (r'(?i)(-authkey:)[^\s"\']+', r'\1<REDACTED>'),
    (r'(?i)(authorization\s*:\s*bearer\s+)[^\s"\']+', r'\1<REDACTED>'),
    (r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer <REDACTED>'),
    (r'(?i)\b(access_token|refresh_token|id_token)\b\s*[:=]\s*["\']?[^"\'\s,;]+', r'\1=<REDACTED>'),
    # JWT (3 parts) and JWE (5 parts), including an empty encrypted-key part.
    (r'\beyJ[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]*){2,4}\b', '<JWT_OR_JWE_REDACTED>'),
    (r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b', '<UUID_REDACTED>'),
]
for pattern, repl in patterns:
    src = re.sub(pattern, repl, src)

# Refuse to publish a file if an obvious credential shape remains.
leaks = []
if re.search(r'(?i)-authkey:(?!<REDACTED>)[^\s"\']+', src):
    leaks.append('authkey')
if re.search(r'\beyJ[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]*){2,4}\b', src):
    leaks.append('JWT/JWE')
if leaks:
    raise SystemExit('refusing to write sanitized log; possible leak: ' + ', '.join(leaks))

Path(sys.argv[2]).write_text(src)
PY
SANITIZE_RESULT=$?

"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true

if [ "$SANITIZE_RESULT" -ne 0 ]; then
  echo "ERROR: sanitizer rejected the log; no shareable output was written." >&2
  exit 9
fi

echo "=== KEY RESULTS ==="
grep -Ei 'MODE=|BOX64_DYNAREC=|RUN_RESULT=|c0000005|EXCEPTION_ACCESS_VIOLATION|info\[[01]\]|rip=|call_vectored_handlers|error initializing|unimplemented|unsupported' "$OUT" | tail -n 240 || true
echo
echo "SANITIZED_LOG=$OUT"
DEBIAN
