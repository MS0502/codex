#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
TERMUX_TMPDIR="${TMPDIR:-${TERMUX_PREFIX}/tmp}"
ROOT="${TERMUX_PREFIX}/glibc"
XSOCK="${TERMUX_TMPDIR}/.X11-unix"
DOWNLOADS="${HOME}/storage/downloads"
OUT_KEY="${DOWNLOADS}/MOBOX_TR_STAGE_TRACE_V2_SANITIZED.txt"
OUT_FULL="${DOWNLOADS}/MOBOX_TR_STAGE_TRACE_V2_FULL_SANITIZED.txt.gz"

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
TRACE_DIR="/tmp/mobox_tr_stage_trace_v2_$$"
RAW="$TRACE_DIR/raw.txt"
PROC="$TRACE_DIR/process.txt"
MAPS="$TRACE_DIR/maps.txt"
STATUS="$TRACE_DIR/status.txt"
COMBINED="$TRACE_DIR/combined.txt"
SANITIZED="$TRACE_DIR/full_sanitized.txt"
KEY="$TRACE_DIR/key.txt"
OUT_KEY=/mnt/downloads/MOBOX_TR_STAGE_TRACE_V2_SANITIZED.txt
OUT_KEY_TR=/mnt/downloads/TR_KR_LOCAL/MOBOX_TR_STAGE_TRACE_V2_SANITIZED.txt
OUT_FULL=/mnt/downloads/MOBOX_TR_STAGE_TRACE_V2_FULL_SANITIZED.txt.gz

mkdir -p "$TRACE_DIR"
cleanup() {
  rm -rf "$TRACE_DIR"
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
export BOX64_DYNACACHE=1
export BOX64_DYNACACHE_FOLDER=/root/.cache/box64-tr-v4-862fef5
mkdir -p "$BOX64_DYNACACHE_FOLDER"
chmod 700 "$BOX64_DYNACACHE_FOLDER"

mkdir -p "$WINEPREFIX/dosdevices"
ln -sfn /mnt/downloads "$WINEPREFIX/dosdevices/d:"

"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true
sleep 2
: >"$RAW"
: >"$PROC"
: >"$MAPS"
: >"$STATUS"

(
  seen_pids=" "
  previous_snapshot=""
  i=0
  while [ "$i" -lt 1800 ]; do
    now="$(date -Iseconds)"
    snapshot="$(ps -eo pid=,ppid=,stat=,comm=,args= 2>/dev/null | grep -Ei 'wineserver|\.exe([[:space:]]|$)' | grep -v -E 'grep -E|mobox_tr_stage_trace_v2' || true)"
    if [ "$snapshot" != "$previous_snapshot" ]; then
      {
        echo "=== PROCESS SNAPSHOT time=$now sample=$i ==="
        printf '%s\n' "$snapshot"
      } >>"$PROC"
      previous_snapshot="$snapshot"
    fi

    for procdir in /proc/[0-9]*; do
      [ -r "$procdir/comm" ] || continue
      pid="${procdir##*/}"
      comm="$(cat "$procdir/comm" 2>/dev/null || true)"
      lower="$(printf '%s' "$comm" | tr '[:upper:]' '[:lower:]')"
      case "$lower" in
        talesrunner.exe|trlauncher.exe|xigncode*|xm.exe|x3.xem)
          case "$seen_pids" in
            *" $pid "*) ;;
            *)
              seen_pids="$seen_pids$pid "
              {
                echo "=== TARGET PROCESS pid=$pid comm=$comm time=$now ==="
                printf 'CMDLINE='
                tr '\0' ' ' <"$procdir/cmdline" 2>/dev/null || true
                echo
                if [ -r "$procdir/maps" ]; then
                  cat "$procdir/maps"
                else
                  echo "MAPS_UNAVAILABLE"
                fi
              } >>"$MAPS"
              ;;
          esac
          ;;
      esac
    done

    i=$((i + 1))
    sleep 0.1
  done
) &
SAMPLER=$!

cd /mnt/downloads/TR_KR_LOCAL
(
  set +e
  WINEDEBUG='-all,+timestamp,+pid,+tid,+seh,+loaddll,+virtual,+process' \
    timeout --foreground 180s "$BOX" "$WINE" cmd /c "$TR_BATCH"
  rc=$?
  printf '%s\n' "$rc" >"$STATUS"
  exit 0
) >"$RAW" 2>&1

sleep 2
kill "$SAMPLER" 2>/dev/null || true
wait "$SAMPLER" 2>/dev/null || true

if [ -s "$STATUS" ]; then
  RUN_RESULT="$(head -1 "$STATUS")"
else
  RUN_RESULT=missing
fi

{
  echo "=== RUN RESULT ==="
  echo "RUN_RESULT=$RUN_RESULT"
  echo "BOX64_DYNACACHE=$BOX64_DYNACACHE"
  echo "BOX64_DYNACACHE_FOLDER=$BOX64_DYNACACHE_FOLDER"
  echo
  echo "=== RAW WINE TRACE ==="
  cat "$RAW"
  echo
  echo "=== PROCESS TIMELINE ==="
  cat "$PROC"
  echo
  echo "=== TARGET PROCESS MAPS ==="
  cat "$MAPS"
} >"$COMBINED"

python3 - "$COMBINED" "$SANITIZED" <<'PY'
from pathlib import Path
import re
import sys

src = Path(sys.argv[1]).read_text(errors='replace')

src = re.sub(r'(?im)^.*(?:argv\[\d+\]|CMDLINE=).*-authkey:[^\n]*$',
             '[AUTH COMMAND LINE REDACTED]', src)
patterns = [
    (r'(?i)trlauncher://\S+', 'trlauncher://<REDACTED>'),
    (r'(?i)(-authkey:)[^\s"\']+', r'\1<REDACTED>'),
    (r'(?i)(authorization\s*:\s*bearer\s+)[^\s"\']+', r'\1<REDACTED>'),
    (r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer <REDACTED>'),
    (r'(?i)\b(access_token|refresh_token|id_token|session_token|ticket)\b\s*[:=]\s*["\']?[^"\'\s,;&]+', r'\1=<REDACTED>'),
    (r'(?i)([?&](?:token|auth|authkey|code|ticket|session)=)[^&#\s"\']+', r'\1<REDACTED>'),
    (r'\beyJ[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]*){2,4}\b', '<JWT_OR_JWE_REDACTED>'),
]
for pattern, repl in patterns:
    src = re.sub(pattern, repl, src)

checks = [
    r'(?i)-authkey:(?!<REDACTED>)[^\s"\']+',
    r'\beyJ[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]*){2,4}\b',
]
for check in checks:
    if re.search(check, src):
        raise SystemExit('refusing output: credential-shaped data remains')

Path(sys.argv[2]).write_text(src)
PY
SANITIZE_RESULT=$?
if [ "$SANITIZE_RESULT" -ne 0 ]; then
  "$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true
  echo "ERROR: sanitizer rejected the trace; no shareable output was written." >&2
  exit 9
fi

python3 - "$SANITIZED" "$KEY" <<'PY'
from pathlib import Path
import re
import sys

lines = Path(sys.argv[1]).read_text(errors='replace').splitlines()
text = '\n'.join(lines)

counts = {
    'c0000005': len(re.findall(r'code=c0000005|EXCEPTION_ACCESS_VIOLATION', text, re.I)),
    'rpc_6ba': len(re.findall(r'code=6ba|RPC_S_SERVER_UNAVAILABLE', text, re.I)),
    'cow_success': len(re.findall(r'BOX64_EXECMOD_COW_V4.*success', text, re.I)),
    'cow_failure': len(re.findall(r'BOX64_EXECMOD_COW_V4.*failed', text, re.I)),
    'talesrunner_seen': int(bool(re.search(r'talesrunner\.exe', text, re.I))),
    'xigncode_seen': int(bool(re.search(r'xigncode|x3\.xem|xm\.exe', text, re.I))),
}

out = [
    'MOBOX TALESRUNNER STAGE TRACE V2',
    '================================',
]
for line in lines[:8]:
    if line.startswith('RUN_RESULT=') or line.startswith('BOX64_DYNACACHE'):
        out.append(line)
out += [f'{k}={v}' for k, v in counts.items()]
out.append('')

for i, line in enumerate(lines):
    if re.search(r'^=== (PROCESS SNAPSHOT|TARGET PROCESS|TARGET PROCESS MAPS)', line):
        out.append(line)
        j = i + 1
        while j < len(lines) and not lines[j].startswith('=== '):
            if lines[j].strip():
                out.append(lines[j])
            j += 1
        out.append('')

for line in lines:
    if re.search(r'trace:loaddll:build_module Loaded .*?(TR_KR_LOCAL|talesrunner|xigncode|x3\.xem|xm\.exe)', line, re.I):
        out.append(line)

keep = set()
for i, line in enumerate(lines):
    if re.search(r'dispatch_exception code=|EXCEPTION_ACCESS_VIOLATION|Security Error', line, re.I):
        for j in range(max(0, i - 5), min(len(lines), i + 18)):
            keep.add(j)
for i in sorted(keep):
    out.append(lines[i])

for line in lines:
    if re.search(r'BOX64_EXECMOD_COW_V4|BOX64_MPROTECT_TRACE.*ret=-1|mprotect.*errno=13', line, re.I):
        out.append(line)

out += ['', '=== SANITIZED RAW TAIL (last 300 lines) ===']
out.extend(lines[-300:])

clean = []
for line in out:
    if not clean or line != clean[-1]:
        clean.append(line)
Path(sys.argv[2]).write_text('\n'.join(clean) + '\n')
PY

cp -f "$KEY" "$OUT_KEY"
cp -f "$KEY" "$OUT_KEY_TR"
gzip -c "$SANITIZED" >"$OUT_FULL"

"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true

echo "=== KEY RESULTS ==="
head -n 30 "$OUT_KEY"
echo
echo "KEY_LOG=$OUT_KEY"
echo "FULL_LOG=$OUT_FULL"
DEBIAN

termux-media-scan "$OUT_KEY" "$OUT_FULL" >/dev/null 2>&1 || true
