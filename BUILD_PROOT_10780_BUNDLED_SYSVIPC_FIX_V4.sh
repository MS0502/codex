#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DOWNLOADS="$HOME_DIR/storage/downloads"
WORK="$HOME_DIR/.cache/proot-10780-bundled-sysvipc-v4"
SRC="$WORK/proot-5.1.107.80"
ZIP="$WORK/proot-v5.1.107.80.zip"
OUT="$HOME_DIR/proot-sysvipc-fixed-10780-bundled"
CUSTOM_PROOT="$OUT/proot"
REPORT="$DOWNLOADS/PROOT_10780_BUNDLED_SYSVIPC_V4_REPORT.txt"
URL="https://github.com/termux/proot/archive/v5.1.107.80.zip"
EXPECTED_SHA256="d237b21b6d84a3acb00507f96251dcf2bbfbee9ffc66ab6258a3f86ef7874186"

mkdir -p "$WORK" "$OUT" "$DOWNLOADS"
chmod 700 "$OUT"
: >"$REPORT"

installed_version="$(dpkg-query -W -f='${Version}' proot 2>/dev/null || true)"
{
  echo "PROOT 5.1.107.80 BUNDLED SYSVIPC V4"
  echo "===================================="
  date -Iseconds
  echo "INSTALLED_PROOT_VERSION=$installed_version"
  echo "CUSTOM_PROOT=$CUSTOM_PROOT"
  echo "SOURCE_URL=$URL"
  echo
} >>"$REPORT"

if [ "$installed_version" != "5.1.107.80" ]; then
  echo "ERROR: installed PRoot is not 5.1.107.80" | tee -a "$REPORT" >&2
  exit 10
fi

echo "[1/6] dependencies"
pkg install -y clang make unzip libandroid-shmem libtalloc >>"$REPORT" 2>&1

echo "[2/6] verified exact source"
rm -rf "$SRC"
curl -fL "$URL" -o "$ZIP" >>"$REPORT" 2>&1
actual_sha="$(sha256sum "$ZIP" | awk '{print $1}')"
echo "SOURCE_SHA256=$actual_sha" >>"$REPORT"
if [ "$actual_sha" != "$EXPECTED_SHA256" ]; then
  echo "ERROR: source SHA256 mismatch" | tee -a "$REPORT" >&2
  exit 11
fi
unzip -q -o "$ZIP" -d "$WORK"

source_file="$SRC/src/extension/sysvipc/sysvipc_shm.c"
[ -f "$source_file" ] || {
  echo "ERROR: source file missing" | tee -a "$REPORT" >&2
  exit 12
}

echo "[3/6] patch helper re-exec only"
python3 - "$source_file" "$CUSTOM_PROOT" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
target = sys.argv[2]
text = path.read_text()

needle = '#include <fcntl.h> /* open, fcntl */\n'
extra = '#include <stdio.h> /* dprintf, perror */\n#include <stdlib.h> /* NULL */\n'
if extra not in text:
    if needle not in text:
        raise SystemExit('include insertion point not found')
    text = text.replace(needle, needle + extra, 1)

old = '\t\t\t\texecl("/proc/self/exe", "proot", "--shm-helper", NULL);\n'
new = f'''\t\t\t\t/* Termux may expose linker64 as /proc/self/exe.\n\t\t\t\t * Start this exact patched PRoot through Android's linker64\n\t\t\t\t * using a raw execve syscall so LD_PRELOAD cannot rewrite it. */\n\t\t\t\textern char **environ;\n#if defined(__aarch64__) || defined(__x86_64__)\n\t\t\t\tchar *helper_argv[] = {{\n\t\t\t\t\t"/system/bin/linker64",\n\t\t\t\t\t"{target}",\n\t\t\t\t\t"--shm-helper",\n\t\t\t\t\tNULL\n\t\t\t\t}};\n#else\n\t\t\t\tchar *helper_argv[] = {{\n\t\t\t\t\t"/system/bin/linker",\n\t\t\t\t\t"{target}",\n\t\t\t\t\t"--shm-helper",\n\t\t\t\t\tNULL\n\t\t\t\t}};\n#endif\n\t\t\t\tdprintf(2, "[PROOT_SHM_HELPER_10780_BUNDLED_V4] target=%s\\n", helper_argv[1]);\n\t\t\t\tsyscall(SYS_execve, helper_argv[0], helper_argv, environ);\n'''
if old not in text:
    raise SystemExit('expected helper execl line not found')
text = text.replace(old, new, 1)
path.write_text(text)
PY

grep -n -A30 -B4 'PROOT_SHM_HELPER_10780_BUNDLED_V4' "$source_file" >>"$REPORT"

echo "[4/6] compile with bundled loader"
make -C "$SRC/src" clean >>"$REPORT" 2>&1 || true
CPPFLAGS="-DARG_MAX=131072" \
make -C "$SRC/src" \
  -j"$(nproc)" \
  CC=clang \
  PROOT_WITH_LIBANDROID_SHMEM=true \
  >>"$REPORT" 2>&1

[ -x "$SRC/src/proot" ] || {
  echo "ERROR: compiled PRoot missing" | tee -a "$REPORT" >&2
  exit 13
}
install -m 700 "$SRC/src/proot" "$CUSTOM_PROOT"

echo "[5/6] validate bundled binary"
CUSTOM_PATH="$OUT:${PATH:-$TERMUX_PREFIX/bin}"
selected="$(env PATH="$CUSTOM_PATH" sh -c 'command -v proot' 2>/dev/null || true)"
{
  echo "PATH_SELECTED_PROOT=$selected"
  file "$CUSTOM_PROOT"
  sha256sum "$CUSTOM_PROOT"
  echo "PATCH_MARKER_COUNT=$(strings "$CUSTOM_PROOT" | grep -c '\[PROOT_SHM_HELPER_10780_BUNDLED_V4\]' || true)"
  echo "BUNDLED_LOADER_MARKER_COUNT=$(strings "$CUSTOM_PROOT" | grep -c '_binary_loader_exe_start' || true)"
  "$CUSTOM_PROOT" --version | head -n 6
  echo
} >>"$REPORT" 2>&1

if [ "$selected" != "$CUSTOM_PROOT" ]; then
  echo "ERROR: custom PRoot PATH selection failed" | tee -a "$REPORT" >&2
  exit 14
fi

echo "[6/6] Debian entry and SysV IPC probe"
set +e
env -u PROOT_LOADER -u PROOT_LOADER_32 -u PROOT_TMP_DIR \
  PATH="$CUSTOM_PATH" \
  proot-distro login debian \
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
    print(f"PROOT_10780_BUNDLED_V4_SYSVIPC_FAIL shmget errno={err} {os.strerror(err)}")
    sys.exit(31)
print(f"PROOT_10780_BUNDLED_V4_SYSVIPC_SHMID={shmid}")
if libc.shmctl(shmid, IPC_RMID, None) != 0:
    err = ctypes.get_errno()
    print(f"PROOT_10780_BUNDLED_V4_SYSVIPC_FAIL shmctl errno={err} {os.strerror(err)}")
    sys.exit(32)
print("PROOT_10780_BUNDLED_V4_SYSVIPC_PROBE_OK")
PY
PROBE_DEBIAN
probe_rc=$?
set -e

{
  echo "PROBE_EXIT=$probe_rc"
  echo "FINISHED=$(date -Iseconds)"
} >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

if [ "$probe_rc" -ne 0 ] || ! grep -q '^PROOT_10780_BUNDLED_V4_SYSVIPC_PROBE_OK$' "$REPORT"; then
  echo "PROOT_10780_BUNDLED_V4_SYSVIPC_PROBE_FAILED"
  echo "REPORT=$REPORT"
  tail -n 140 "$REPORT" || true
  exit 15
fi

echo "PROOT_10780_BUNDLED_V4_SYSVIPC_PROBE_OK"
echo "CUSTOM_PROOT=$CUSTOM_PROOT"
echo "REPORT=$REPORT"
