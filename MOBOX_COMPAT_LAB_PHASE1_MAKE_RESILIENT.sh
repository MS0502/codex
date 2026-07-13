#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TARGET="${HOME}/MOBOX_COMPAT_LAB_PHASE1.sh"

if [ ! -f "$TARGET" ]; then
    echo "ERROR: $TARGET not found" >&2
    exit 2
fi

python3 - "$TARGET" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

old = '''run_mode() {
    mode="$1"
    outfile="$2"
    errfile="$3"
    shift 3
    echo "=== RUN $mode ==="
    timeout 180s "$@" >"$outfile" 2>"$errfile"
}
'''

new = '''run_mode() {
    mode="$1"
    outfile="$2"
    errfile="$3"
    shift 3
    echo "=== RUN $mode ==="

    set +e
    timeout 180s "$@" >"$outfile" 2>"$errfile"
    rc=$?
    set -e

    printf '%s\\n' "$rc" >"$OUTDIR/${mode}.exitcode"
    echo "=== RUN $mode EXIT=$rc ==="

    # A crash or timeout is a test result, not a harness failure.
    return 0
}
'''

if new not in text:
    if old not in text:
        raise SystemExit('run_mode block not found; refusing unsafe patch')
    text = text.replace(old, new, 1)

old_tail = '''print('\\n'.join(lines[:8]))
PY

DEBIAN
'''

new_tail = '''print('\\n'.join(lines[:8]))
PY

{
    echo
    echo "Run exit codes:"
    for mode in native dynarec interp; do
        if [ -f "$OUTDIR/${mode}.exitcode" ]; then
            printf '%s: ' "$mode"
            cat "$OUTDIR/${mode}.exitcode"
        else
            echo "$mode: missing"
        fi
    done
} >>"$OUTDIR/SUMMARY.txt"

DEBIAN
'''

if new_tail not in text:
    if old_tail not in text:
        raise SystemExit('summary tail not found; refusing unsafe patch')
    text = text.replace(old_tail, new_tail, 1)

path.write_text(text)
print('PHASE1_RESILIENT_PATCH_APPLIED')
PY

chmod +x "$TARGET"
echo "PATCHED_SCRIPT=$TARGET"
