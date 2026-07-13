#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
DOWNLOADS="$HOME_DIR/storage/downloads"
WORK="$HOME_DIR/.cache/proot-sysvipc-fix-build"
OUT="$HOME_DIR/proot-sysvipc-fixed"
REPORT="$DOWNLOADS/PROOT_SYSVIPC_SELFEXE_FIX_REPORT.txt"
VERSION="5.1.107.84"
ZIP="$WORK/proot-v${VERSION}.zip"
SRC="$WORK/proot-${VERSION}"
URL="https://github.com/termux/proot/archive/v${VERSION}.zip"
EXPECTED_SHA256="a44ddbf18bc72c9780d56948b03aeda6d285392503ece0cae17cfc02e7bc7928"

mkdir -p "$WORK" "$OUT" "$DOWNLOADS"
: >"$REPORT"

{
  echo "PROOT SYSVIPC SELFEXE FIX BUILD"
  echo "================================"
  date -Iseconds
  echo "SOURCE_VERSION=$VERSION"
  echo "SYSTEM_PROOT=$(command -v proot || true)"
  echo "SYSTEM_PROOT_VERSION=$(dpkg-query -W -f='${Version}' proot 2>/dev/null || true)"
  echo "TERMUX_PREFIX=$TERMUX_PREFIX"
  echo
} >>"$REPORT"

echo "[1/6] build dependencies"
pkg install -y clang make unzip libandroid-shmem libtalloc >>"$REPORT" 2>&1

echo "[2/6] download verified source"
rm -rf "$SRC"
curl -fL "$URL" -o "$ZIP" >>"$REPORT" 2>&1
actual_sha="$(sha256sum "$ZIP" | awk '{print $1}')"
echo "SOURCE_ZIP_SHA256=$actual_sha" >>"$REPORT"
if [ "$actual_sha" != "$EXPECTED_SHA256" ]; then
  echo "ERROR: source SHA256 mismatch" | tee -a "$REPORT" >&2
  exit 20
fi
unzip -q -o "$ZIP" -d "$WORK"

source_file="$SRC/src/extension/sysvipc/sysvipc_shm.c"
[ -f "$source_file" ] || {
  echo "ERROR: source file missing: $source_file" | tee -a "$REPORT" >&2
  exit 21
}

echo "[3/6] apply generic Termux system-linker re-exec fix"
python3 - "$source_file" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
include_needle = '#include <fcntl.h> /* open, fcntl */\n'
if '#include <stdlib.h> /* getenv */' not in text:
    if include_needle not in text:
        raise SystemExit('include insertion point not found')
    text = text.replace(
        include_needle,
        include_needle + '#include <stdlib.h> /* getenv */\n',
        1,
    )

old = '\t\t\t\texecl("/proc/self/exe", "proot", "--shm-helper", NULL);\n'
new = '''\t\t\t\t/* When Termux starts PRoot through Android's system linker,\n\t\t\t\t * /proc/self/exe points to linker(64), not to PRoot. Re-exec\n\t\t\t\t * the real binary explicitly through the linker in that case. */\n\t\t\t\tconst char *real_proot = getenv("TERMUX_EXEC__PROC_SELF_EXE");\n\t\t\t\tif (real_proot != NULL && real_proot[0] == '/') {\n#if defined(__aarch64__) || defined(__x86_64__)\n\t\t\t\t\texecl("/system/bin/linker64", "linker64", real_proot, "--shm-helper", NULL);\n#else\n\t\t\t\t\texecl("/system/bin/linker", "linker", real_proot, "--shm-helper", NULL);\n#endif\n\t\t\t\t} else {\n\t\t\t\t\texecl("/proc/self/exe", "proot", "--shm-helper", NULL);\n\t\t\t\t}\n'''
if old not in text:
    raise SystemExit('helper re-exec line not found or already changed unexpectedly')
text = text.replace(old, new, 1)
path.write_text(text)
PY

grep -n -A18 -B3 'real_proot' "$source_file" >>"$REPORT"

echo "[4/6] compile isolated PRoot"
make -C "$SRC/src" clean >>"$REPORT" 2>&1 || true
CPPFLAGS="-DARG_MAX=131072" \
make -C "$SRC/src" \
  -j"$(nproc)" \
  CC=clang \
  PROOT_WITH_LIBANDROID_SHMEM=true \
  PROOT_UNBUNDLE_LOADER="$TERMUX_PREFIX/libexec/proot" \
  >>"$REPORT" 2>&1

[ -x "$SRC/src/proot" ] || {
  echo "ERROR: compiled PRoot missing" | tee -a "$REPORT" >&2
  exit 22
}
install -m 700 "$SRC/src/proot" "$OUT/proot"

echo "[5/6] binary validation"
{
  echo "CUSTOM_PROOT=$OUT/proot"
  file "$OUT/proot"
  sha256sum "$OUT/proot"
  "$OUT/proot" --version | head -n 6
  echo "TERMUX_EXEC__PROC_SELF_EXE_CURRENT=${TERMUX_EXEC__PROC_SELF_EXE:-unset}"
  echo
} >>"$REPORT" 2>&1

echo "[6/6] PRoot SysV IPC probe"
set +e
PD_PROOT_BIN="$OUT/proot" proot-distro login debian \
  --bind "$DOWNLOADS:/mnt/downloads" \
  -- bash -s >>"$REPORT" 2>&1 <<'PROBE_DEBIAN'
python3 - <<'PY'
import ctypes
import os
import sys

libc = ctypes.CDLL(None, use_errno=True)
IPC_PRIVATE = 0
IPC_CREAT = 0o1000
IPC_RMID = 0
shmid = libc.shmget(IPC_PRIVATE, 4096, IPC_CREAT | 0o600)
if shmid < 0:
    err = ctypes.get_errno()
    print(f"CUSTOM_PROOT_SYSVIPC_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(31)
print(f"CUSTOM_PROOT_SYSVIPC_SHMID={shmid}")
rc = libc.shmctl(shmid, IPC_RMID, None)
if rc != 0:
    err = ctypes.get_errno()
    print(f"CUSTOM_PROOT_SYSVIPC_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(32)
print("CUSTOM_PROOT_SYSVIPC_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e

echo "PROBE_EXIT=$probe_rc" >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

if [ "$probe_rc" -ne 0 ] || ! grep -q '^CUSTOM_PROOT_SYSVIPC_PROBE_OK$' "$REPORT"; then
  echo "CUSTOM_PROOT_SYSVIPC_PROBE_FAILED"
  echo "REPORT=$REPORT"
  tail -n 80 "$REPORT" || true
  exit 23
fi

echo "CUSTOM_PROOT_SYSVIPC_PROBE_OK"
echo "CUSTOM_PROOT=$OUT/proot"
echo "REPORT=$REPORT"
