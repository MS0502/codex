#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
TR_DIR="${DOWNLOADS}/TR_KR_LOCAL"
TOKEN="${TR_DIR}/tr_access_token.tmp"
BASE_TRACE="${HOME}/MOBOX_TR_STAGE_TRACE_V2.sh"
WINLATOR_RUNTIME="${HOME}/winlator-11.1-wine-root"
WINLATOR_WINE="${WINLATOR_RUNTIME}/opt/wine/bin/wine"
EXPECTED_WINE_SHA="1d21e085e2febb15f3be3f6e51459cf5e6c543abece9b463773cc03eedab2263"
GENERATED="${HOME}/.MOBOX_TR_PHASE2B_WINE1010_TMPFIX.generated.sh"
META="${DOWNLOADS}/MOBOX_TR_PHASE2B_WINE1010_TMPFIX_META.txt"
KEY="${DOWNLOADS}/MOBOX_TR_PHASE2B_WINE1010_TMPFIX_SANITIZED.txt"
FULL="${DOWNLOADS}/MOBOX_TR_PHASE2B_WINE1010_TMPFIX_FULL_SANITIZED.txt.gz"

[ -d "$ROOT" ] || { echo "ERROR: Mobox glibc root missing: $ROOT" >&2; exit 2; }
[ -f "$BASE_TRACE" ] || { echo "ERROR: base trace missing: $BASE_TRACE" >&2; exit 3; }
[ -x "$WINLATOR_WINE" ] || { echo "ERROR: extracted Winlator Wine missing: $WINLATOR_WINE" >&2; exit 4; }
[ -s "$TOKEN" ] || {
  echo "AUTH_TOKEN_MISSING_OR_EMPTY"
  echo "Order: official site Game Start -> TR_AUTH_BRIDGE.py -> this script"
  exit 5
}

actual_wine_sha="$(sha256sum "$WINLATOR_WINE" | awk '{print $1}')"
[ "$actual_wine_sha" = "$EXPECTED_WINE_SHA" ] || {
  echo "ERROR: Winlator Wine binary hash mismatch" >&2
  echo "EXPECTED=$EXPECTED_WINE_SHA" >&2
  echo "ACTUAL=$actual_wine_sha" >&2
  exit 6
}

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  --bind "$WINLATOR_RUNTIME:/mnt/winlator-runtime" \
  -- bash -s <<'DEBIAN'
set -euo pipefail

BOX=/root/box64/build/box64
BASE=/root/.wine-mobox-execmod
TEST=/root/.wine-mobox-phase2b-wine1010
WINE9_SERVER=/opt/mobox/wine-9.3-vanilla-wow64/bin/wineserver
WINE10_ROOT=/mnt/winlator-runtime/opt/wine
WINE10_SERVER="$WINE10_ROOT/bin/wineserver"
COMPILED_TMP=/data/data/com.winlator/files/rootfs/tmp
META=/mnt/downloads/MOBOX_TR_PHASE2B_WINE1010_TMPFIX_META.txt

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_DYNAREC=1
export BOX64_DYNACACHE=0
export BOX64_PATH="$WINE10_ROOT/bin"
export BOX64_LD_LIBRARY_PATH="$WINE10_ROOT/lib/wine/x86_64-unix:$WINE10_ROOT/lib:$WINE10_ROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu:/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"

[ -d "$BASE" ] || { echo "ERROR: base prefix missing: $BASE" >&2; exit 10; }
"$BOX" "$WINE9_SERVER" -k >/dev/null 2>&1 || true
"$BOX" "$WINE10_SERVER" -k >/dev/null 2>&1 || true
sleep 2

if [ ! -f "$TEST/user.reg" ] || [ ! -d "$TEST/drive_c" ]; then
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
lines = path.read_text(errors='replace').splitlines()
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

mkdir -p "$COMPILED_TMP"
chmod 1777 "$COMPILED_TMP"

version_line="$(grep -A8 -m1 '^\[Software\\\\Wine\]' "$TEST/user.reg" | grep '^"Version"=' | head -1 || true)"
[ "$version_line" = '"Version"="win10"' ] || {
  echo "ERROR: offline win10 registry verification failed" >&2
  exit 11
}

{
  echo "MOBOX TALESRUNNER PHASE 2B WINE10.10 TMPFIX META"
  echo "================================================="
  echo "BASE_PREFIX=$BASE"
  echo "TEST_PREFIX=$TEST"
  echo "BASE_PREFIX_UNMODIFIED=1"
  echo "WINE_RUNTIME=$WINE10_ROOT"
  echo "WINE_VERSION_PROBE=$(timeout 30s "$BOX" "$WINE10_ROOT/bin/wine" --version 2>&1 | tail -1 || true)"
  echo "WINDOWS_VERSION_LINE=$version_line"
  echo "WINEESYNC=1"
  echo "COMPILED_TMP=$COMPILED_TMP"
  echo "COMPILED_TMP_EXISTS=$([ -d "$COMPILED_TMP" ] && echo 1 || echo 0)"
  echo "COMPILED_TMP_MODE=$(stat -c %a "$COMPILED_TMP" 2>/dev/null || echo unknown)"
  echo "NATIVE_WINCOMPONENTS_NOT_ADDED=1"
} >"$META"
DEBIAN

python3 - "$BASE_TRACE" "$GENERATED" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1]).read_text()
src = src.replace('MOBOX_TR_STAGE_TRACE_V2', 'MOBOX_TR_PHASE2B_WINE1010_TMPFIX')
src = src.replace('MOBOX TALESRUNNER STAGE TRACE V2',
                  'MOBOX TALESRUNNER PHASE 2B WINLATOR WINE 10.10 TMPFIX TRACE')
src = src.replace('ROOT="${TERMUX_PREFIX}/glibc"',
                  'ROOT="${TERMUX_PREFIX}/glibc"\nWINLATOR_RUNTIME="${HOME}/winlator-11.1-wine-root"')
src = src.replace(
    '  --bind "$DOWNLOADS:/mnt/downloads" \\\n  -- bash -s <<\'DEBIAN\'',
    '  --bind "$DOWNLOADS:/mnt/downloads" \\\n  --bind "$WINLATOR_RUNTIME:/mnt/winlator-runtime" \\\n  -- bash -s <<\'DEBIAN\'',
)
src = src.replace('WROOT=/opt/mobox/wine-9.3-vanilla-wow64',
                  'WROOT=/mnt/winlator-runtime/opt/wine')
src = src.replace('WINEPREFIX=/root/.wine-mobox-execmod',
                  'WINEPREFIX=/root/.wine-mobox-phase2b-wine1010')
src = src.replace('export WINEPREFIX\n',
                  'export WINEPREFIX\nexport WINEESYNC=1\n', 1)
src = src.replace(
    'export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu"',
    'export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu:/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"',
)
src = src.replace('BOX64_DYNACACHE_FOLDER=/root/.cache/box64-tr-v4-862fef5',
                  'BOX64_DYNACACHE_FOLDER=/root/.cache/box64-tr-v4-wine1010-tmpfix')
src = src.replace('+loaddll,+virtual,+process', '+loaddll,+process')
needle = 'chmod 700 "$XDG_RUNTIME_DIR"\n'
insert = '''chmod 700 "$XDG_RUNTIME_DIR"
WINLATOR_COMPILED_TMP=/data/data/com.winlator/files/rootfs/tmp
mkdir -p "$WINLATOR_COMPILED_TMP"
chmod 1777 "$WINLATOR_COMPILED_TMP"
export TMPDIR="$WINLATOR_COMPILED_TMP"
export TMP="$WINLATOR_COMPILED_TMP"
export TEMP="$WINLATOR_COMPILED_TMP"
'''
if needle not in src:
    raise SystemExit('generated trace validation failed: XDG runtime insertion point')
src = src.replace(needle, insert, 1)

required = [
    '--bind "$WINLATOR_RUNTIME:/mnt/winlator-runtime"',
    'WROOT=/mnt/winlator-runtime/opt/wine',
    'WINEPREFIX=/root/.wine-mobox-phase2b-wine1010',
    'export WINEESYNC=1',
    'WINLATOR_COMPILED_TMP=/data/data/com.winlator/files/rootfs/tmp',
    'export TMPDIR="$WINLATOR_COMPILED_TMP"',
    'MOBOX_TR_PHASE2B_WINE1010_TMPFIX_SANITIZED.txt',
    'MOBOX_TR_PHASE2B_WINE1010_TMPFIX_FULL_SANITIZED.txt.gz',
]
for item in required:
    if item not in src:
        raise SystemExit(f'generated trace validation failed: {item}')
Path(sys.argv[2]).write_text(src)
PY

chmod +x "$GENERATED"
bash -n "$GENERATED"

echo "PHASE2B_TMPFIX_READY"
echo "WINE_RUNTIME=Winlator_11.1_Wine_10.10"
echo "TEST_PREFIX=/root/.wine-mobox-phase2b-wine1010"
echo "COMPILED_TMP=/data/data/com.winlator/files/rootfs/tmp"
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
echo "PHASE2B_TMPFIX_TRACE_RC=$trace_rc"
echo "META=$META"
echo "KEY_LOG=$KEY"
echo "FULL_LOG=$FULL"
exit "$trace_rc"
