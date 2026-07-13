#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
TERMUX_TMPDIR="${TMPDIR:-${TERMUX_PREFIX}/tmp}"
ROOT="${TERMUX_PREFIX}/glibc"
XSOCK="${TERMUX_TMPDIR}/.X11-unix"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/TR_KR_LOCAL/MOBOX_TR_NTDLL_PROTECT_TRACE_SANITIZED.txt"

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
RAW=/tmp/mobox_tr_ntdll_protect_raw.txt
MAPS=/tmp/mobox_tr_ntdll_protect_maps.txt
COMBINED=/tmp/mobox_tr_ntdll_protect_combined.txt
SANITIZED=/tmp/mobox_tr_ntdll_protect_sanitized.txt
OUT=/mnt/downloads/TR_KR_LOCAL/MOBOX_TR_NTDLL_PROTECT_TRACE_SANITIZED.txt

cleanup() {
  rm -f "$RAW" "$MAPS" "$COMBINED" "$SANITIZED"
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
export BOX64_DYNAREC=1
export BOX64_LOG=0
export BOX64_PATH="$WROOT/bin"
export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu"

# Keep trace runs on the same isolated cache proven by Phase 1F and the
# full Phase 1 regression. Never read the old default ~/.cache/box64 data.
export BOX64_DYNACACHE=1
export BOX64_DYNACACHE_FOLDER=/root/.cache/box64-tr-v4-862fef5
mkdir -p "$BOX64_DYNACACHE_FOLDER"
chmod 700 "$BOX64_DYNACACHE_FOLDER"

mkdir -p "$WINEPREFIX/dosdevices"
ln -sfn /mnt/downloads "$WINEPREFIX/dosdevices/d:"

pkill -f '[w]ineserver' 2>/dev/null
sleep 2
: >"$RAW"
: >"$MAPS"

(
  captured=""
  i=0
  while [ "$i" -lt 1800 ]; do
    for pid in $(pgrep -x talesrunner.exe 2>/dev/null); do
      case " $captured " in
        *" $pid "*) ;;
        *)
          if [ -r "/proc/$pid/maps" ]; then
            {
              echo "=== TALESRUNNER RELEVANT MAPS pid=$pid time=$(date -Iseconds) ==="
              awk '$1 ~ /^1400/ || $1 ~ /^2810/ || $1 ~ /^2811/ || /ntdll\.dll|kernel32\.dll|kernelbase\.dll/' "/proc/$pid/maps"
            } >>"$MAPS"
            captured="$captured $pid"
          fi
          ;;
      esac
    done
    i=$((i + 1))
    sleep 0.1
  done
) &
SAMPLER=$!

cd /mnt/downloads/TR_KR_LOCAL
RUN_RESULT=unknown
WINEDEBUG='-all,+timestamp,+pid,+tid,+seh,+loaddll,+virtual' \
  timeout 180s "$BOX" "$WINE" cmd /c "$TR_BATCH" >"$RAW" 2>&1
RUN_RESULT=$?

kill "$SAMPLER" 2>/dev/null
wait "$SAMPLER" 2>/dev/null

{
  echo "=== RUN RESULT ==="
  echo "RUN_RESULT=$RUN_RESULT"
  echo "BOX64_DYNACACHE=$BOX64_DYNACACHE"
  echo "BOX64_DYNACACHE_FOLDER=$BOX64_DYNACACHE_FOLDER"
  echo
  echo "=== WINE VIRTUAL/SEH TRACE ==="
  cat "$RAW"
  echo
  cat "$MAPS"
} >"$COMBINED"

python3 - "$COMBINED" "$SANITIZED" <<'PY'
from pathlib import Path
import re
import sys

src = Path(sys.argv[1]).read_text(errors='replace')
src = re.sub(r'(?im)^.*argv\[\d+\]="-authkey:[^"]*".*$', '[AUTH ARGUMENT REDACTED]', src)
patterns = [
    (r'(?i)trlauncher://\S+', 'trlauncher://<REDACTED>'),
    (r'(?i)(-authkey:)[^\s"\']+', r'\1<REDACTED>'),
    (r'(?i)(authorization\s*:\s*bearer\s+)[^\s"\']+', r'\1<REDACTED>'),
    (r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer <REDACTED>'),
    (r'(?i)\b(access_token|refresh_token|id_token)\b\s*[:=]\s*["\']?[^"\'\s,;]+', r'\1=<REDACTED>'),
    (r'\beyJ[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]*){2,4}\b', '<JWT_OR_JWE_REDACTED>'),
    (r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b', '<UUID_REDACTED>'),
]
for pattern, repl in patterns:
    src = re.sub(pattern, repl, src)

if re.search(r'(?i)-authkey:(?!<REDACTED>)[^\s"\']+', src):
    raise SystemExit('refusing to write trace: authkey remains')
if re.search(r'\beyJ[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]*){2,4}\b', src):
    raise SystemExit('refusing to write trace: JWT/JWE remains')

Path(sys.argv[2]).write_text(src)
PY
SANITIZE_RESULT=$?

if [ "$SANITIZE_RESULT" -ne 0 ]; then
  "$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true
  echo "ERROR: sanitizer rejected the trace; no shareable output was written." >&2
  exit 9
fi

python3 - "$SANITIZED" "$OUT" <<'PY'
from pathlib import Path
import re
import sys

lines = Path(sys.argv[1]).read_text(errors='replace').splitlines()
keep = set()
patterns = [
    r'RUN_RESULT=|BOX64_DYNACACHE',
    r'NtProtectVirtualMemory|VirtualProtect|protect|mprotect',
    r'281140|281141|2811b5|ntdll\.dll',
    r'c0000005|EXCEPTION_ACCESS_VIOLATION|140243D68|140243d68',
    r'call_vectored_handlers|info\[[01]\]|rip=',
    r'TALESRUNNER RELEVANT MAPS',
    r'BOX64_EXECMOD_COW_V4|DynaCache|SIGSEGV|Sigfault/Segbus while quitting',
]
rx = re.compile('|'.join(patterns), re.I)
for i, line in enumerate(lines):
    if rx.search(line):
        for j in range(max(0, i - 4), min(len(lines), i + 5)):
            keep.add(j)

out = []
last = -2
for i in sorted(keep):
    if i > last + 1:
        out.append('---')
    out.append(lines[i])
    last = i
Path(sys.argv[2]).write_text('\n'.join(out) + '\n')
PY

"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true

echo "=== KEY RESULTS ==="
grep -Ei 'RUN_RESULT=|BOX64_DYNACACHE|NtProtectVirtualMemory|VirtualProtect|281140|281141|c0000005|EXCEPTION_ACCESS_VIOLATION|140243d68|TALESRUNNER RELEVANT MAPS|BOX64_EXECMOD_COW_V4|DynaCache|SIGSEGV' "$OUT" | tail -n 300 || true
echo
echo "SANITIZED_LOG=$OUT"
DEBIAN
