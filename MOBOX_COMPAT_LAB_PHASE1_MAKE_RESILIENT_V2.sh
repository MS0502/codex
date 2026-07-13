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

start_marker = "run_mode() {\n"
end_marker = "\n\nrun_mode native"
start = text.find(start_marker)
if start < 0:
    raise SystemExit("run_mode start not found")
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("run_mode end not found")

new_func = "\n".join([
    "run_mode() {",
    "    mode=\"$1\"",
    "    outfile=\"$2\"",
    "    errfile=\"$3\"",
    "    shift 3",
    "    echo \"=== RUN $mode ===\"",
    "",
    "    set +e",
    "    timeout 180s \"$@\" >\"$outfile\" 2>\"$errfile\"",
    "    rc=$?",
    "    set -e",
    "",
    "    printf '%s\\n' \"$rc\" >\"$OUTDIR/${mode}.exitcode\"",
    "    echo \"=== RUN $mode EXIT=$rc ===\"",
    "",
    "    # A crash or timeout is a test result, not a harness failure.",
    "    return 0",
    "}",
])

text = text[:start] + new_func + text[end:]
path.write_text(text)
print("PHASE1_RESILIENT_V2_APPLIED")
PY

chmod +x "$TARGET"

# Validate shell syntax before allowing another long run.
bash -n "$TARGET"

echo "PHASE1_SCRIPT_SYNTAX_OK"
echo "PATCHED_SCRIPT=$TARGET"
