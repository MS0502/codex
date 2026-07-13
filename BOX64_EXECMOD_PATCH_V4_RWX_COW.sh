#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$PREFIX/glibc"
OUT="$HOME/storage/downloads/box64_execmod_patch_v4_result.txt"

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  -- bash -s <<'DEBIAN' 2>&1 | tee "$OUT"
set -euo pipefail
cd /root/box64

SRC=src/wrapped/wrappedlibc.c
BACKUP=src/wrapped/wrappedlibc.c.pre_execmod_v4

if grep -q 'BOX64_EXECMOD_COW_V4' "$SRC"; then
    echo "V4_PATCH_ALREADY_PRESENT"
else
    cp -f "$SRC" "$BACKUP"

    python3 - <<'PY'
from pathlib import Path

path = Path('src/wrapped/wrappedlibc.c')
text = path.read_text()

old_cond = '''    if(ret && saved_errno == EACCES && len &&
       (prot & PROT_EXEC) && !(prot & PROT_WRITE))
'''
new_cond = '''    /* BOX64_EXECMOD_COW_V4:
     * Android may reject executable protection changes on a private
     * file-backed PE image even though an equivalent anonymous mapping is
     * allowed. Preserve the bytes and replace only the affected private
     * pages with an anonymous copy before retrying the requested protection.
     */
    if(ret && saved_errno == EACCES && len && (prot & PROT_EXEC))
'''

old_check = '''            int oldprot = getProtection(p) & ~PROT_CUSTOM;
            if((oldprot & (PROT_READ | PROT_WRITE)) !=
               (PROT_READ | PROT_WRITE))
                copyable = 0;
'''
new_check = '''            int oldprot = getProtection(p) & ~PROT_CUSTOM;
            if(!(oldprot & PROT_READ))
                copyable = 0;
'''

if old_cond not in text:
    raise SystemExit('V3 fallback condition not found')
if old_check not in text:
    raise SystemExit('V3 copyability check not found')

text = text.replace(old_cond, new_cond, 1)
text = text.replace(old_check, new_check, 1)
text = text.replace('[BOX64_EXECMOD_FALLBACK]', '[BOX64_EXECMOD_COW_V4]')

path.write_text(text)
print('V4_PATCH_APPLIED')
PY
fi

echo "=== SOURCE CHECK ==="
grep -n -A80 -B15 'BOX64_EXECMOD_COW_V4' "$SRC"

echo "=== BUILD ==="
cmake --build build -j4

echo "=== BINARY ==="
file build/box64
build/box64 --version || true

echo "BOX64_EXECMOD_V4_READY"
DEBIAN

echo
echo "RESULT_LOG=$OUT"
