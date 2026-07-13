#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

DOWNLOADS="${HOME}/storage/downloads"
TR_DIR="${DOWNLOADS}/TR_KR_LOCAL"
TOKEN="${TR_DIR}/tr_access_token.tmp"
BASE="${HOME}/MOBOX_TR_STAGE_TRACE_V2.sh"
GEN="${HOME}/.MOBOX_TR_STAGE_TRACE_INTERP.generated.sh"

if [ ! -f "$BASE" ]; then
  echo "ERROR: base trace script not found: $BASE" >&2
  echo "Download MOBOX_TR_STAGE_TRACE_V2.sh first." >&2
  exit 2
fi

if [ ! -s "$TOKEN" ]; then
  echo "AUTH_TOKEN_MISSING_OR_EMPTY"
  echo "Correct order: official site Game Start -> TR_AUTH_BRIDGE.py -> this script"
  exit 3
fi

python3 - "$BASE" "$GEN" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1]).read_text()
src = src.replace('MOBOX_TR_STAGE_TRACE_V2', 'MOBOX_TR_STAGE_TRACE_INTERP')
src = src.replace('MOBOX TALESRUNNER STAGE TRACE V2',
                  'MOBOX TALESRUNNER STAGE TRACE INTERP')
src = src.replace('export BOX64_DYNAREC=1', 'export BOX64_DYNAREC=0')
src = src.replace('export BOX64_DYNACACHE=1', 'export BOX64_DYNACACHE=0')

required = [
    'export BOX64_DYNAREC=0',
    'export BOX64_DYNACACHE=0',
    'MOBOX_TR_STAGE_TRACE_INTERP_SANITIZED.txt',
    'MOBOX_TR_STAGE_TRACE_INTERP_FULL_SANITIZED.txt.gz',
]
for item in required:
    if item not in src:
        raise SystemExit(f'generated trace validation failed: {item}')

Path(sys.argv[2]).write_text(src)
PY

chmod +x "$GEN"
bash -n "$GEN"

echo "INTERP_TRACE_READY"
echo "BOX64_DYNAREC=0"
echo "BOX64_DYNACACHE=0"
exec "$GEN"
