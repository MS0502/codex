#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
TERMUX_TMPDIR="${TMPDIR:-${TERMUX_PREFIX}/tmp}"
ROOT="${TERMUX_PREFIX}/glibc"
XSOCK="${TERMUX_TMPDIR}/.X11-unix"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/TR_KR_LOCAL/MOBOX_TR_COMPAT_DIAG_SANITIZED.txt"

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
  -- bash -s <<'DEBIAN'
set +e

BOX=/root/box64/build/box64
WROOT=/opt/mobox/wine-9.3-vanilla-wow64
WINE="$WROOT/bin/wine"
WINESERVER="$WROOT/bin/wineserver"
WINEPREFIX=/root/.wine-mobox-execmod
TR_BATCH='D:\TR_KR_LOCAL\TR_LOGIN_AND_RUN_FIXED.bat'
RAW=/tmp/mobox_tr_compat_diag_raw.txt
PROC=/tmp/mobox_tr_compat_diag_proc.txt
OUT=/mnt/downloads/TR_KR_LOCAL/MOBOX_TR_COMPAT_DIAG_SANITIZED.txt

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

mkdir -p "$WINEPREFIX/dosdevices"
ln -sfn /mnt/downloads "$WINEPREFIX/dosdevices/d:"

pkill -f '[w]ineserver' 2>/dev/null
sleep 2

: >"$RAW"
: >"$PROC"

(
  i=0
  while [ "$i" -lt 180 ]; do
    printf '\n=== PROCESS SAMPLE %03d %s ===\n' "$i" "$(date -Iseconds)"
    ps -eo pid,ppid,rss,vsz,stat,comm | grep -Ei 'wine|xldr|tales|xign|services|explorer|winedevice|rpcss|plugplay|svchost' | grep -v grep || true
    i=$((i + 1))
    sleep 1
  done
) >"$PROC" 2>&1 &
SAMPLER=$!

cd /mnt/downloads/TR_KR_LOCAL
WINEDEBUG='-all,+timestamp,+pid,+tid,+seh,+loaddll' \
BOX64_LOG=1 \
timeout 180s "$BOX" "$WINE" cmd /c "$TR_BATCH" >"$RAW" 2>&1
RUN_RESULT=$?

kill "$SAMPLER" 2>/dev/null
wait "$SAMPLER" 2>/dev/null

{
  echo "=== RUN RESULT ==="
  echo "RUN_RESULT=$RUN_RESULT"
  echo
  echo "=== WINE AND BOX64 LOG ==="
  cat "$RAW"
  echo
  echo "=== PROCESS SAMPLES (NO COMMAND LINES) ==="
  cat "$PROC"
} >/tmp/mobox_tr_compat_diag_combined.txt

python3 - <<'PY'
from pathlib import Path
import re

src = Path('/tmp/mobox_tr_compat_diag_combined.txt').read_text(errors='replace')
patterns = [
    (r'(?i)trlauncher://\S+', 'trlauncher://<REDACTED>'),
    (r'(?i)(authorization\s*:\s*bearer\s+)[^\s"\']+', r'\1<REDACTED>'),
    (r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer <REDACTED>'),
    (r'(?i)\b(access_token|refresh_token|id_token)\b\s*[:=]\s*["\']?[^"\'\s,;]+', r'\1=<REDACTED>'),
    (r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '<JWT_REDACTED>'),
    (r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b', '<UUID_REDACTED>'),
]
for pattern, repl in patterns:
    src = re.sub(pattern, repl, src)
Path('/mnt/downloads/TR_KR_LOCAL/MOBOX_TR_COMPAT_DIAG_SANITIZED.txt').write_text(src)
PY

rm -f "$RAW" "$PROC" /tmp/mobox_tr_compat_diag_combined.txt
"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true

echo "=== KEY RESULTS ==="
grep -Ei 'RUN_RESULT=|c0000005|unhandled exception|page fault|err:|error initializing|warning:|missing|unimplemented|unsupported' "$OUT" | tail -n 200 || true
echo
echo "SANITIZED_LOG=$OUT"
DEBIAN
