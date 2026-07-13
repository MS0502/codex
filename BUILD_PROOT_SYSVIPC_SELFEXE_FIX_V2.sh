#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
DOWNLOADS="$HOME_DIR/storage/downloads"
WORK="$HOME_DIR/.cache/proot-sysvipc-fix-v2-build"
OUT="$HOME_DIR/proot-sysvipc-fixed-v2"
REPORT="$DOWNLOADS/PROOT_SYSVIPC_SELFEXE_FIX_V2_REPORT.txt"
VERSION="5.1.107.84"
ZIP="$WORK/proot-v${VERSION}.zip"
SRC="$WORK/proot-${VERSION}"
URL="https://github.com/termux/proot/archive/v${VERSION}.zip"
EXPECTED_SHA256="a44ddbf18bc72c9780d56948b03aeda6d285392503ece0cae17cfc02e7bc7928"
CUSTOM_PROOT_PATH="$OUT/proot"

mkdir -p "$WORK" "$OUT" "$DOWNLOADS"
: >"$REPORT"

{
  echo "PROOT SYSVIPC SELFEXE FIX V2 BUILD"
  echo "==================================="
  date -Iseconds
  echo "SOURCE_VERSION=$VERSION"
  echo "CUSTOM_PROOT_PATH=$CUSTOM_PROOT_PATH"
  echo "SYSTEM_PROOT=$(command -v proot || true)"
  echo "SYSTEM_PROOT_VERSION=$(dpkg-query -W -f='${Version}' proot 2>/dev/null || true)"
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

echo "[3/6] apply direct-syscall linker re-exec fix"
python3 - "$source_file" "$CUSTOM_PROOT_PATH" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
target = sys.argv[2]
text = path.read_text()

include_needle = '#include <fcntl.h> /* open, fcntl */\n'
extra = '#include <stdio.h> /* dprintf, perror */\n#include <stdlib.h> /* NULL */\n'
if extra not in text:
    if include_needle not in text:
        raise SystemExit('include insertion point not found')
    text = text.replace(include_needle, include_needle + extra, 1)

old = '\t\t\t\texecl("/proc/self/exe", "proot", "--shm-helper", NULL);\n'
new = f'''\t\t\t\t/* Android 10+ may start PRoot through /system/bin/linker64.\n\t\t\t\t * In that mode /proc/self/exe points to linker64, and libc execl()\n\t\t\t\t * is also intercepted by termux-exec. Bypass both problems by\n\t\t\t\t * issuing execve directly and passing the fixed PRoot path to\n\t\t\t\t * Android's linker. */\n\t\t\t\textern char **environ;\n#if defined(__aarch64__) || defined(__x86_64__)\n\t\t\t\tchar *helper_argv[] = {{\n\t\t\t\t\t"/system/bin/linker64",\n\t\t\t\t\t"{target}",\n\t\t\t\t\t"--shm-helper",\n\t\t\t\t\tNULL\n\t\t\t\t}};\n#else\n\t\t\t\tchar *helper_argv[] = {{\n\t\t\t\t\t"/system/bin/linker",\n\t\t\t\t\t"{target}",\n\t\t\t\t\t"--shm-helper",\n\t\t\t\t\tNULL\n\t\t\t\t}};\n#endif\n\t\t\t\tdprintf(2, "[PROOT_SHM_HELPER_V2] target=%s\\n", helper_argv[1]);\n\t\t\t\tsyscall(SYS_execve, helper_argv[0], helper_argv, environ);\n'''
if old not in text:
    raise SystemExit('helper re-exec line not found or source already modified')
text = text.replace(old, new, 1)
path.write_text(text)
PY

grep -n -A30 -B4 'PROOT_SHM_HELPER_V2' "$source_file" >>"$REPORT"

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
install -m 700 "$SRC/src/proot" "$CUSTOM_PROOT_PATH"

echo "[5/6] binary validation"
{
  echo "CUSTOM_PROOT=$CUSTOM_PROOT_PATH"
  file "$CUSTOM_PROOT_PATH"
  sha256sum "$CUSTOM_PROOT_PATH"
  strings "$CUSTOM_PROOT_PATH" | grep -F '[PROOT_SHM_HELPER_V2]' || true
  "$CUSTOM_PROOT_PATH" --version | head -n 6
  echo
} >>"$REPORT" 2>&1

echo "[6/6] PRoot SysV IPC probe"
set +e
PD_PROOT_BIN="$CUSTOM_PROOT_PATH" proot-distro login debian \
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
    print(f"CUSTOM_PROOT_V2_SYSVIPC_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(31)
print(f"CUSTOM_PROOT_V2_SYSVIPC_SHMID={shmid}")
rc = libc.shmctl(shmid, IPC_RMID, None)
if rc != 0:
    err = ctypes.get_errno()
    print(f"CUSTOM_PROOT_V2_SYSVIPC_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(32)
print("CUSTOM_PROOT_V2_SYSVIPC_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e

echo "PROBE_EXIT=$probe_rc" >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

if [ "$probe_rc" -ne 0 ] || ! grep -q '^CUSTOM_PROOT_V2_SYSVIPC_PROBE_OK$' "$REPORT"; then
  echo "CUSTOM_PROOT_V2_SYSVIPC_PROBE_FAILED"
  echo "REPORT=$REPORT"
  tail -n 100 "$REPORT" || true
  exit 23
fi

echo "CUSTOM_PROOT_V2_SYSVIPC_PROBE_OK"
echo "CUSTOM_PROOT=$CUSTOM_PROOT_PATH"
echo "REPORT=$REPORT"
