#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
TERMUX_TMPDIR="${TMPDIR:-${TERMUX_PREFIX}/tmp}"
ROOT="${TERMUX_PREFIX}/glibc"
XSOCK="${TERMUX_TMPDIR}/.X11-unix"
DOWNLOADS="${HOME}/storage/downloads"
MODE="${1:-test}"

if [ ! -d "$ROOT" ]; then
  echo "ERROR: Mobox glibc root not found: $ROOT" >&2
  exit 2
fi

if [ ! -S "$XSOCK/X0" ]; then
  echo "ERROR: Termux:X11 socket is missing: $XSOCK/X0" >&2
  echo "Start Termux:X11 first, then retry." >&2
  exit 3
fi

if [ ! -d "$DOWNLOADS/TR_KR_LOCAL" ]; then
  echo "ERROR: Downloads/TR_KR_LOCAL not found: $DOWNLOADS/TR_KR_LOCAL" >&2
  exit 4
fi

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$XSOCK:/tmp/.X11-unix" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  --env MOBOX_LAUNCH_MODE="$MODE" \
  -- bash -s <<'DEBIAN'
set -euo pipefail

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

# Never reuse the old default cache created by earlier Box64 builds/patches.
# Phase 1F proved that the default cache crashes on a second fixed-address
# ntdll mapping, while a fresh isolated folder and DynaCache=0 both pass.
export BOX64_DYNACACHE=1
export BOX64_DYNACACHE_FOLDER=/root/.cache/box64-tr-v4-862fef5
mkdir -p "$BOX64_DYNACACHE_FOLDER"
chmod 700 "$BOX64_DYNACACHE_FOLDER"

if [ "${MOBOX_LAUNCH_MODE:-test}" = "tr-nocache" ]; then
  export BOX64_DYNACACHE=0
  unset BOX64_DYNACACHE_FOLDER
fi

if [ ! -x "$BOX" ]; then
  echo "ERROR: patched Box64 not found: $BOX" >&2
  exit 5
fi

if [ ! -x "$WINE" ]; then
  echo "ERROR: Wine not found: $WINE" >&2
  exit 6
fi

if [ ! -d "$WINEPREFIX" ]; then
  echo "ERROR: Wine prefix missing: $WINEPREFIX" >&2
  exit 7
fi

mkdir -p "$WINEPREFIX/dosdevices"
ln -sfn /mnt/downloads "$WINEPREFIX/dosdevices/d:"

TR_DIR='D:\TR_KR_LOCAL'
TR_BATCH='D:\TR_KR_LOCAL\TR_LOGIN_AND_RUN_FIXED.bat'

case "${MOBOX_LAUNCH_MODE:-test}" in
  test)
    echo "=== D DRIVE CHECK ==="
    echo "BOX64_DYNACACHE=$BOX64_DYNACACHE"
    echo "BOX64_DYNACACHE_FOLDER=${BOX64_DYNACACHE_FOLDER:-disabled}"
    ls -ld "$WINEPREFIX/dosdevices/d:"
    "$BOX" "$WINE" cmd /c dir "$TR_DIR"
    ;;
  desktop)
    echo "Opening Wine desktop..."
    exec "$BOX" "$WINE" explorer /desktop=mobox,1280x720
    ;;
  folder)
    echo "Opening D:\\TR_KR_LOCAL..."
    exec "$BOX" "$WINE" explorer "$TR_DIR"
    ;;
  cmd)
    exec "$BOX" "$WINE" cmd
    ;;
  tr|tr-nocache)
    if [ ! -f /mnt/downloads/TR_KR_LOCAL/TR_LOGIN_AND_RUN_FIXED.bat ]; then
      echo "ERROR: TR_LOGIN_AND_RUN_FIXED.bat not found." >&2
      exit 8
    fi
    echo "BOX64_DYNACACHE=$BOX64_DYNACACHE"
    echo "BOX64_DYNACACHE_FOLDER=${BOX64_DYNACACHE_FOLDER:-disabled}"
    cd /mnt/downloads/TR_KR_LOCAL
    exec "$BOX" "$WINE" cmd /c "$TR_BATCH"
    ;;
  stop)
    "$BOX" "$WINESERVER" -k || true
    ;;
  *)
    echo "Usage: $0 {test|desktop|folder|cmd|tr|tr-nocache|stop}" >&2
    exit 64
    ;;
esac
DEBIAN
