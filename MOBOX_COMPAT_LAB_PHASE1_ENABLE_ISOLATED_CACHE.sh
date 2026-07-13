#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TARGET="${HOME}/MOBOX_COMPAT_LAB_PHASE1.sh"
BACKUP="${HOME}/MOBOX_COMPAT_LAB_PHASE1.sh.pre_isolated_dynacache"

if [ ! -f "$TARGET" ]; then
    echo "ERROR: $TARGET not found" >&2
    exit 2
fi

cp -f "$TARGET" "$BACKUP"

python3 - "$TARGET" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
marker = '# PHASE1_ISOLATED_DYNACACHE'

if marker not in text:
    needle = 'export BOX64_MMAP32=0\n'
    if needle not in text:
        raise SystemExit('BOX64_MMAP32 export not found; refusing patch')
    insert = '''export BOX64_MMAP32=0

# PHASE1_ISOLATED_DYNACACHE
# Use a new cache folder for every run so stale address-dependent DynaCache
# files from earlier Box64 builds cannot affect the regression result.
export BOX64_DYNACACHE=1
export BOX64_DYNACACHE_FOLDER="$OUTDIR/dynacache"
mkdir -p "$BOX64_DYNACACHE_FOLDER"
'''
    text = text.replace(needle, insert, 1)
    path.write_text(text)
    print('PHASE1_ISOLATED_DYNACACHE_APPLIED')
else:
    print('PHASE1_ISOLATED_DYNACACHE_ALREADY_PRESENT')
PY

chmod +x "$TARGET"
bash -n "$TARGET"

echo "PHASE1_SCRIPT_SYNTAX_OK"
echo "BACKUP=$BACKUP"
echo "PATCHED=$TARGET"
