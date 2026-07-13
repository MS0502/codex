#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
TR_DIR="${DOWNLOADS}/TR_KR_LOCAL"
TOKEN="${TR_DIR}/tr_access_token.tmp"
BASE_TRACE="${HOME}/MOBOX_TR_STAGE_TRACE_V2.sh"
GENERATED="${HOME}/.MOBOX_TR_PHASE2A_WIN10_ESYNC.generated.sh"
META="${DOWNLOADS}/MOBOX_TR_PHASE2A_WIN10_ESYNC_META.txt"
KEY="${DOWNLOADS}/MOBOX_TR_PHASE2A_WIN10_ESYNC_SANITIZED.txt"
FULL="${DOWNLOADS}/MOBOX_TR_PHASE2A_WIN10_ESYNC_FULL_SANITIZED.txt.gz"

if [ ! -d "$ROOT" ]; then
  echo "ERROR: Mobox glibc root not found: $ROOT" >&2
  exit 2
fi
if [ ! -f "$BASE_TRACE" ]; then
  echo "ERROR: base trace missing: $BASE_TRACE" >&2
  exit 3
fi
if [ ! -s "$TOKEN" ]; then
  echo "AUTH_TOKEN_MISSING_OR_EMPTY"
  echo "Order: official site Game Start -> TR_AUTH_BRIDGE.py -> this script"
  exit 4
fi

# Prepare and modify a separate prefix without starting Wine. Starting Wine just
# to run reg.exe caused Android to kill the helper before the actual game test.
proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  -- bash -s <<'DEBIAN'
set -euo pipefail

BOX=/root/box64/build/box64
WROOT=/opt/mobox/wine-9.3-vanilla-wow64
WINESERVER="$WROOT/bin/wineserver"
BASE=/root/.wine-mobox-execmod
TEST=/root/.wine-mobox-phase2a-win10-esync
META=/mnt/downloads/MOBOX_TR_PHASE2A_WIN10_ESYNC_META.txt

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_PATH="$WROOT/bin"
export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu"
export BOX64_DYNAREC=1
export BOX64_DYNACACHE=1
export BOX64_DYNACACHE_FOLDER=/root/.cache/box64-tr-v4-862fef5
mkdir -p "$BOX64_DYNACACHE_FOLDER"

[ -d "$BASE" ] || { echo "ERROR: base prefix missing: $BASE" >&2; exit 10; }
"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true
sleep 2

clone_state=existing
if [ ! -f "$TEST/user.reg" ] || [ ! -d "$TEST/drive_c" ]; then
  clone_state=rebuilt
  tmp="${TEST}.tmp.$$"
  rm -rf "$tmp" "$TEST"
  mkdir -p "$tmp"
  cp -a "$BASE"/. "$tmp"/
  mv "$tmp" "$TEST"
fi

python3 - "$TEST/user.reg" <<'PY'
from pathlib import Path
import re, sys

path = Path(sys.argv[1])
text = path.read_text(errors='replace')
lines = text.splitlines()
section_re = re.compile(r'^\[Software\\\\Wine\](?:\s+\d+)?$')
version_re = re.compile(r'^"Version"=')

start = next((i for i, line in enumerate(lines) if section_re.match(line)), None)
if start is None:
    if lines and lines[-1] != '':
        lines.append('')
    lines.extend(['[Software\\\\Wine]', '"Version"="win10"'])
else:
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith('['):
            end = i
            break
    kept = [line for line in lines[start + 1:end] if not version_re.match(line)]
    lines[start + 1:end] = ['"Version"="win10"'] + kept

path.write_text('\n'.join(lines) + '\n')
PY

version_line="$(grep -A8 -m1 '^\[Software\\\\Wine\]' "$TEST/user.reg" | grep '^"Version"=' | head -1 || true)"
[ "$version_line" = '"Version"="win10"' ] || {
  echo "ERROR: offline win10 registry patch verification failed" >&2
  exit 11
}

{
  echo "MOBOX TALESRUNNER PHASE 2A META"
  echo "================================"
  echo "BASE_PREFIX=$BASE"
  echo "TEST_PREFIX=$TEST"
  echo "CLONE_STATE=$clone_state"
  echo "BASE_PREFIX_UNMODIFIED=1"
  echo "WINDOWS_VERSION_PATCH=offline_user_reg"
  echo "WINDOWS_VERSION_LINE=$version_line"
  echo "WINEESYNC=1"
  echo "PRETEST_WINE_START_SKIPPED=1"
} >"$META"
DEBIAN

python3 - "$BASE_TRACE" "$GENERATED" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1]).read_text()
src = src.replace('MOBOX_TR_STAGE_TRACE_V2', 'MOBOX_TR_PHASE2A_WIN10_ESYNC')
src = src.replace('MOBOX TALESRUNNER STAGE TRACE V2',
                  'MOBOX TALESRUNNER PHASE 2A WIN10 ESYNC TRACE')
src = src.replace('WINEPREFIX=/root/.wine-mobox-execmod',
                  'WINEPREFIX=/root/.wine-mobox-phase2a-win10-esync')
src = src.replace('export WINEPREFIX\n',
                  'export WINEPREFIX\nexport WINEESYNC=1\n', 1)

required = [
    'WINEPREFIX=/root/.wine-mobox-phase2a-win10-esync',
    'export WINEESYNC=1',
    'MOBOX_TR_PHASE2A_WIN10_ESYNC_SANITIZED.txt',
    'MOBOX_TR_PHASE2A_WIN10_ESYNC_FULL_SANITIZED.txt.gz',
]
for item in required:
    if item not in src:
        raise SystemExit(f'generated trace validation failed: {item}')
Path(sys.argv[2]).write_text(src)
PY

chmod +x "$GENERATED"
bash -n "$GENERATED"

echo "PHASE2A_V2_READY"
echo "TEST_PREFIX=/root/.wine-mobox-phase2a-win10-esync"
echo "WINE_VERSION=win10_offline"
echo "WINEESYNC=1"

set +e
"$GENERATED"
trace_rc=$?
set -e

if [ -f "$KEY" ] && [ -f "$META" ]; then
  tmp="${KEY}.tmp"
  {
    cat "$META"
    echo
    cat "$KEY"
  } >"$tmp"
  mv "$tmp" "$KEY"
fi

termux-media-scan "$META" "$KEY" "$FULL" >/dev/null 2>&1 || true

echo
echo "PHASE2A_TRACE_RC=$trace_rc"
echo "META=$META"
echo "KEY_LOG=$KEY"
echo "FULL_LOG=$FULL"
exit "$trace_rc"
