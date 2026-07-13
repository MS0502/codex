#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DOWNLOADS="$HOME_DIR/storage/downloads"
WORK="$HOME_DIR/.cache/proot-10780-sysvipc-fix-build"
SRC="$WORK/proot"
OUT="$HOME_DIR/proot-sysvipc-fixed-10780"
CUSTOM_PROOT="$OUT/proot"
SYSTEM_LOADER_DIR="$TERMUX_PREFIX/libexec/proot"
SYSTEM_LOADER="$SYSTEM_LOADER_DIR/loader"
SYSTEM_LOADER32="$SYSTEM_LOADER_DIR/loader32"
PROOT_TMP="$TERMUX_PREFIX/tmp"
REPORT="$DOWNLOADS/PROOT_10780_SYSVIPC_FIX_V3_REPORT.txt"
TAG="v5.1.107.80"

mkdir -p "$WORK" "$OUT" "$DOWNLOADS" "$PROOT_TMP"
chmod 700 "$OUT"
: >"$REPORT"

installed_version="$(dpkg-query -W -f='${Version}' proot 2>/dev/null || true)"
{
  echo "PROOT 5.1.107.80 SYSVIPC FIX V3"
  echo "================================"
  date -Iseconds
  echo "INSTALLED_PROOT_VERSION=$installed_version"
  echo "SOURCE_TAG=$TAG"
  echo "SYSTEM_PROOT=$(command -v proot || true)"
  echo "SYSTEM_LOADER=$SYSTEM_LOADER"
  echo "SYSTEM_LOADER32=$SYSTEM_LOADER32"
  echo "CUSTOM_PROOT=$CUSTOM_PROOT"
  echo "PROOT_TMP_DIR=$PROOT_TMP"
  echo
} >>"$REPORT"

if [ "$installed_version" != "5.1.107.80" ]; then
  echo "ERROR: installed PRoot is not 5.1.107.80" | tee -a "$REPORT" >&2
  exit 10
fi
if [ ! -x "$SYSTEM_LOADER" ]; then
  echo "ERROR: exact installed system loader is missing: $SYSTEM_LOADER" | tee -a "$REPORT" >&2
  exit 11
fi

{
  file "$SYSTEM_LOADER"
  sha256sum "$SYSTEM_LOADER"
  if [ -x "$SYSTEM_LOADER32" ]; then
    file "$SYSTEM_LOADER32"
    sha256sum "$SYSTEM_LOADER32"
  fi
  echo
} >>"$REPORT" 2>&1

echo "[1/6] build dependencies"
pkg install -y git clang make libandroid-shmem libtalloc >>"$REPORT" 2>&1

echo "[2/6] clone exact source tag"
rm -rf "$SRC"
git clone --depth 1 --branch "$TAG" https://github.com/termux/proot.git "$SRC" >>"$REPORT" 2>&1
source_commit="$(git -C "$SRC" rev-parse HEAD)"
echo "SOURCE_COMMIT=$source_commit" >>"$REPORT"

echo "[3/6] patch only SysV IPC helper re-exec"
source_file="$SRC/src/extension/sysvipc/sysvipc_shm.c"
python3 - "$source_file" "$CUSTOM_PROOT" <<'PY'
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
new = f'''\t\t\t\t/* Android/Termux may expose linker64 as /proc/self/exe.\n\t\t\t\t * Re-exec the exact patched PRoot through Android's linker and\n\t\t\t\t * issue execve as a raw syscall so termux-exec cannot rewrite it. */\n\t\t\t\textern char **environ;\n#if defined(__aarch64__) || defined(__x86_64__)\n\t\t\t\tchar *helper_argv[] = {{\n\t\t\t\t\t"/system/bin/linker64",\n\t\t\t\t\t"{target}",\n\t\t\t\t\t"--shm-helper",\n\t\t\t\t\tNULL\n\t\t\t\t}};\n#else\n\t\t\t\tchar *helper_argv[] = {{\n\t\t\t\t\t"/system/bin/linker",\n\t\t\t\t\t"{target}",\n\t\t\t\t\t"--shm-helper",\n\t\t\t\t\tNULL\n\t\t\t\t}};\n#endif\n\t\t\t\tdprintf(2, "[PROOT_SHM_HELPER_10780_V3] target=%s\\n", helper_argv[1]);\n\t\t\t\tsyscall(SYS_execve, helper_argv[0], helper_argv, environ);\n'''
if old not in text:
    raise SystemExit('expected helper execl line not found')
text = text.replace(old, new, 1)
path.write_text(text)
PY

grep -n -A30 -B4 'PROOT_SHM_HELPER_10780_V3' "$source_file" >>"$REPORT"

echo "[4/6] compile exact-version PRoot only"
make -C "$SRC/src" clean >>"$REPORT" 2>&1 || true
CPPFLAGS="-DARG_MAX=131072" \
make -C "$SRC/src" \
  -j"$(nproc)" \
  CC=clang \
  PROOT_WITH_LIBANDROID_SHMEM=true \
  PROOT_UNBUNDLE_LOADER="$SYSTEM_LOADER_DIR" \
  >>"$REPORT" 2>&1

[ -x "$SRC/src/proot" ] || {
  echo "ERROR: compiled PRoot missing" | tee -a "$REPORT" >&2
  exit 12
}
install -m 700 "$SRC/src/proot" "$CUSTOM_PROOT"

echo "[5/6] validate exact-version binary and system loader pairing"
CUSTOM_PATH="$OUT:${PATH:-$TERMUX_PREFIX/bin}"
selected="$(env PATH="$CUSTOM_PATH" sh -c 'command -v proot' 2>/dev/null || true)"
{
  echo "PATH_SELECTED_PROOT=$selected"
  file "$CUSTOM_PROOT"
  sha256sum "$CUSTOM_PROOT"
  strings "$CUSTOM_PROOT" | grep -F '[PROOT_SHM_HELPER_10780_V3]' || true
  "$CUSTOM_PROOT" --version | head -n 6
  echo
} >>"$REPORT" 2>&1

if [ "$selected" != "$CUSTOM_PROOT" ]; then
  echo "ERROR: custom PRoot PATH selection failed" | tee -a "$REPORT" >&2
  exit 13
fi

echo "[6/6] Debian entry plus SysV IPC probe"
set +e
env -u PROOT_LOADER -u PROOT_LOADER_32 \
  PATH="$CUSTOM_PATH" \
  PROOT_TMP_DIR="$PROOT_TMP" \
  proot-distro login debian \
    -e "PROOT_TMP_DIR=$PROOT_TMP" \
    --bind "$DOWNLOADS:/mnt/downloads" \
    -- bash -s >>"$REPORT" 2>&1 <<'PROBE_DEBIAN'
python3 - <<'PY'
import ctypes
import os
import sys

print(f"GUEST_PROOT_TMP_DIR={os.environ.get('PROOT_TMP_DIR')}")
libc = ctypes.CDLL(None, use_errno=True)
IPC_PRIVATE = 0
IPC_CREAT = 0o1000
IPC_RMID = 0
shmid = libc.shmget(IPC_PRIVATE, 4096, IPC_CREAT | 0o600)
if shmid < 0:
    err = ctypes.get_errno()
    print(f"PROOT_10780_V3_SYSVIPC_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(31)
print(f"PROOT_10780_V3_SYSVIPC_SHMID={shmid}")
if libc.shmctl(shmid, IPC_RMID, None) != 0:
    err = ctypes.get_errno()
    print(f"PROOT_10780_V3_SYSVIPC_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(32)
print("PROOT_10780_V3_SYSVIPC_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e

{
  echo "PROBE_EXIT=$probe_rc"
  echo "FINISHED=$(date -Iseconds)"
} >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

if [ "$probe_rc" -ne 0 ] || ! grep -q '^PROOT_10780_V3_SYSVIPC_PROBE_OK$' "$REPORT"; then
  echo "PROOT_10780_V3_SYSVIPC_PROBE_FAILED"
  echo "REPORT=$REPORT"
  tail -n 140 "$REPORT" || true
  exit 14
fi

echo "PROOT_10780_V3_SYSVIPC_PROBE_OK"
echo "CUSTOM_PROOT=$CUSTOM_PROOT"
echo "REPORT=$REPORT"
