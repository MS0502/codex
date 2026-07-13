#!/data/data/com.termux/files/usr/bin/bash
set -u

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
TERMUX_TMPDIR="${TMPDIR:-${TERMUX_PREFIX}/tmp}"
ROOT="${TERMUX_PREFIX}/glibc"
XSOCK="${TERMUX_TMPDIR}/.X11-unix"
OUT="${HOME}/storage/downloads/mobox_wine_postboot_diag.txt"
mkdir -p "$(dirname "$OUT")"

if [ ! -d "$ROOT" ]; then
  echo "ERROR: Mobox glibc root not found: $ROOT" >&2
  exit 2
fi

if [ ! -x "$ROOT/wine-9.3-vanilla-wow64/bin/wine" ]; then
  echo "ERROR: Wine binary not found under: $ROOT/wine-9.3-vanilla-wow64" >&2
  exit 2
fi

{
  echo "=== HOST CHECK ==="
  date -Iseconds
  echo "ROOT=$ROOT"
  echo "XSOCK=$XSOCK"
  ls -ld "$XSOCK" 2>&1 || true
  ls -l "$XSOCK/X0" 2>&1 || true
  echo

  proot-distro login debian \
    --bind "$ROOT:/opt/mobox" \
    --bind "$XSOCK:/tmp/.X11-unix" \
    -- bash -s <<'DEBIAN'
set +e

BOX=/root/box64/build/box64
WROOT=/opt/mobox/wine-9.3-vanilla-wow64
WINE="$WROOT/bin/wine"
WINESERVER="$WROOT/bin/wineserver"

export DISPLAY=:0
export XDG_RUNTIME_DIR=/tmp/runtime-box64
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

export WINEPREFIX=/root/.wine-mobox-execmod
export WINEARCH=win64
export WINEDLLOVERRIDES="winemenubuilder.exe=d"
export WINEDEBUG=-all

export BOX64_LOG=0
export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_PATH="$WROOT/bin"
export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu"

echo "=== RUNTIME IDENTITY ==="
uname -a
cat /etc/os-release 2>/dev/null || true
"$BOX" --version 2>&1
"$BOX" "$WINE" --version 2>&1
printf 'DISPLAY=%s\n' "$DISPLAY"
printf 'WINEPREFIX=%s\n' "$WINEPREFIX"
echo

echo "=== PREFIX STATE (DO NOT DELETE) ==="
for p in \
  "$WINEPREFIX" \
  "$WINEPREFIX/system.reg" \
  "$WINEPREFIX/user.reg" \
  "$WINEPREFIX/userdef.reg" \
  "$WINEPREFIX/dosdevices/c:"; do
  if [ -e "$p" ] || [ -L "$p" ]; then
    ls -ld "$p"
  else
    echo "MISSING: $p"
  fi
done
echo

echo "=== X11 SOCKET INSIDE PROOT ==="
ls -ld /tmp/.X11-unix 2>&1
ls -l /tmp/.X11-unix/X0 2>&1
if [ -S /tmp/.X11-unix/X0 ]; then
  echo "X11_SOCKET=present"
else
  echo "X11_SOCKET=missing"
fi
echo

echo "=== MEMORY BEFORE ==="
grep -E 'MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree' /proc/meminfo
ulimit -a 2>&1
echo

echo "=== NATIVE ARM64 LIBRARY CHECK ==="
LIBS='libfreetype.so.6 libfontconfig.so.1 libdbus-1.so.3 libcups.so.2 libgstreamer-1.0.so.0 libgstvideo-1.0.so.0 libgstaudio-1.0.so.0 libgsttag-1.0.so.0 libgobject-2.0.so.0 libglib-2.0.so.0 libSDL2-2.0.so.0 libusb-1.0.so.0 libudev.so.1 libX11.so.6 libXext.so.6 libXrender.so.1 libXrandr.so.2 libXfixes.so.3 libXcursor.so.1 libXi.so.6 libXinerama.so.1'
MISSING_NATIVE=0
for so in $LIBS; do
  path=$(ldconfig -p 2>/dev/null | awk -v n="$so" '$1 == n && /aarch64|AArch64|ARM64/ {print $NF; exit}')
  if [ -z "$path" ]; then
    path=$(find /lib/aarch64-linux-gnu /usr/lib/aarch64-linux-gnu -maxdepth 2 -name "$so" -print -quit 2>/dev/null)
  fi
  if [ -n "$path" ]; then
    echo "FOUND $so -> $path"
  else
    echo "MISSING $so"
    MISSING_NATIVE=$((MISSING_NATIVE + 1))
  fi
done
echo "NATIVE_MISSING_COUNT=$MISSING_NATIVE"
echo

echo "=== PACKAGE CANDIDATES (READ-ONLY) ==="
for pkg in \
  libfreetype6 libfontconfig1 libdbus-1-3 \
  libcups2 libcups2t64 \
  libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
  libglib2.0-0 libglib2.0-0t64 \
  libsdl2-2.0-0 libusb-1.0-0 libudev1; do
  candidate=$(apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/ {print $2; exit}')
  if [ -n "$candidate" ] && [ "$candidate" != "(none)" ]; then
    echo "PACKAGE_CANDIDATE $pkg=$candidate"
  fi
done
echo

echo "=== CLEAN STALE WINE PROCESSES ==="
pkill -f '[w]ineserver' 2>/dev/null
pkill -f '[w]ineboot.exe' 2>/dev/null
sleep 2
ps -ef | grep -E 'wine|wineserver|box64' | grep -v grep || true
echo

echo "=== HEADLESS CORE TEST: cmd /c ver ==="
HEADLESS_LOG=/tmp/mobox_headless_core_test.log
: >"$HEADLESS_LOG"
timeout 60s "$BOX" "$WINE" cmd /c ver >"$HEADLESS_LOG" 2>&1
HEADLESS_RESULT=$?
cat "$HEADLESS_LOG"
HEADLESS_OLD_NTDLL_COUNT=$(grep -cE 'ntdll\.dll section \.text|BOX64_MPROTECT_FAIL|virtual_setup_exception' "$HEADLESS_LOG" 2>/dev/null || true)
echo "HEADLESS_RESULT=$HEADLESS_RESULT"
echo "HEADLESS_OLD_NTDLL_COUNT=$HEADLESS_OLD_NTDLL_COUNT"
echo

echo "=== WAIT FOR WINESERVER ==="
timeout 30s "$BOX" "$WINESERVER" -w
WINESERVER_WAIT_RESULT=$?
echo "WINESERVER_WAIT_RESULT=$WINESERVER_WAIT_RESULT"
echo

echo "=== GUI TEST ==="
GUI_LOG=/tmp/mobox_gui_test.log
: >"$GUI_LOG"
if [ -S /tmp/.X11-unix/X0 ]; then
  WINEDEBUG=err+all timeout 25s "$BOX" "$WINE" explorer /desktop=moboxdiag,640x480 cmd /c ver >"$GUI_LOG" 2>&1
  GUI_RESULT=$?
else
  GUI_RESULT=125
  echo "GUI test skipped: /tmp/.X11-unix/X0 is not a socket" >"$GUI_LOG"
fi
cat "$GUI_LOG"
GUI_NODRV_COUNT=$(grep -c 'nodrv_CreateWindow' "$GUI_LOG" 2>/dev/null || true)
GUI_OLD_NTDLL_COUNT=$(grep -cE 'ntdll\.dll section \.text|BOX64_MPROTECT_FAIL|virtual_setup_exception' "$GUI_LOG" 2>/dev/null || true)
echo "GUI_RESULT=$GUI_RESULT"
echo "GUI_NODRV_COUNT=$GUI_NODRV_COUNT"
echo "GUI_OLD_NTDLL_COUNT=$GUI_OLD_NTDLL_COUNT"
echo

echo "=== PROCESS SNAPSHOT ==="
ps -eo pid,ppid,rss,vsz,stat,comm,args | grep -E 'wine|wineserver|box64' | grep -v grep || true
echo

echo "=== MEMORY AFTER ==="
grep -E 'MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree' /proc/meminfo
echo

echo "=== POSSIBLE OOM/SIGKILL EVIDENCE ==="
dmesg 2>&1 | tail -n 300 | grep -Ei 'out of memory|oom|killed process|lowmemory|sigkill' || true
echo

echo "=== SUMMARY ==="
echo "HEADLESS_RESULT=$HEADLESS_RESULT"
echo "HEADLESS_OLD_NTDLL_COUNT=$HEADLESS_OLD_NTDLL_COUNT"
echo "WINESERVER_WAIT_RESULT=$WINESERVER_WAIT_RESULT"
echo "GUI_RESULT=$GUI_RESULT"
echo "GUI_NODRV_COUNT=$GUI_NODRV_COUNT"
echo "GUI_OLD_NTDLL_COUNT=$GUI_OLD_NTDLL_COUNT"
echo "NATIVE_MISSING_COUNT=$MISSING_NATIVE"

# Leave the existing prefix intact. Stop only leftover Wine processes.
"$BOX" "$WINESERVER" -k >/dev/null 2>&1 || true
DEBIAN
} >"$OUT" 2>&1

RESULT=$?
echo "=== 핵심 결과 ==="
grep -E 'HEADLESS_RESULT|HEADLESS_OLD_NTDLL_COUNT|WINESERVER_WAIT_RESULT|GUI_RESULT|GUI_NODRV_COUNT|GUI_OLD_NTDLL_COUNT|NATIVE_MISSING_COUNT|X11_SOCKET=|MISSING:|MISSING lib|FOUND lib|PACKAGE_CANDIDATE|Killed|out of memory|oom|killed process' "$OUT" | tail -n 160 || true
echo
echo "전체 로그: $OUT"
exit "$RESULT"
