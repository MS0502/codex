#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$PREFIX/glibc"
OUT="$HOME/storage/downloads/box64_mprotect_trace_patch_result.txt"

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  -- bash -s <<'DEBIAN' 2>&1 | tee "$OUT"
set -euo pipefail
cd /root/box64

SRC=src/wrapped/wrappedlibc.c
BACKUP=src/wrapped/wrappedlibc.c.pre_mprotect_trace

if grep -q '\[BOX64_MPROTECT_TRACE\]' "$SRC"; then
    echo "TRACE_PATCH_ALREADY_PRESENT"
else
    cp -f "$SRC" "$BACKUP"

    python3 - <<'PY'
from pathlib import Path

path = Path("src/wrapped/wrappedlibc.c")
text = path.read_text()

old = '''    errno = 0;
    int ret = mprotect(addr, len, prot);
    int saved_errno = ret ? errno : 0;
'''

new = '''    int trace_execwrite =
        (prot & (PROT_EXEC | PROT_WRITE)) == (PROT_EXEC | PROT_WRITE);

    if(trace_execwrite)
        fprintf(stderr,
            "[BOX64_MPROTECT_TRACE] before addr=%p len=0x%lx prot=0x%x\\n",
            addr, len, prot);

    errno = 0;
    int ret = mprotect(addr, len, prot);
    int saved_errno = ret ? errno : 0;

    if(trace_execwrite)
        fprintf(stderr,
            "[BOX64_MPROTECT_TRACE] after addr=%p len=0x%lx prot=0x%x "
            "ret=%d errno=%d (%s)\\n",
            addr, len, prot, ret, saved_errno,
            saved_errno ? strerror(saved_errno) : "OK");
'''

count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one my_mprotect block, found {count}")

text = text.replace(old, new, 1)
path.write_text(text)
print("TRACE_PATCH_APPLIED")
PY
fi

echo "=== SOURCE CHECK ==="
grep -n -A18 -B5 '\[BOX64_MPROTECT_TRACE\]' "$SRC"

echo "=== BUILD ==="
cmake --build build -j4

echo "=== BINARY ==="
file build/box64
build/box64 --version || true

echo "MPROTECT_TRACE_PATCH_READY"
DEBIAN

echo
echo "RESULT_LOG=$OUT"
