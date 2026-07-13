#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DOWNLOADS="${HOME}/storage/downloads"
APK="${HOME}/storage/shared/Download/Winlator_11.1.apk"
EXPECTED_SHA="80bdea17d8497a2ae0ff637e68d82a884ccc5ca4406880950b96fd2483e50970"
WORK="${TERMUX_PREFIX}/tmp/winlator_11_1_rootfs_probe.$$"
RUNTIME="${HOME}/winlator-11.1-wine-root"
REPORT="${DOWNLOADS}/WINLATOR_11_1_ROOTFS_WINE_PROBE.txt"

cleanup() {
  rm -rf "$WORK"
}
trap cleanup EXIT

for cmd in python3 zstd tar sha256sum file find grep sed awk; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $cmd" >&2
    echo "Install required tools with: pkg install zstd file binutils" >&2
    exit 2
  }
done

if [ ! -f "$APK" ]; then
  APK="$(find "$DOWNLOADS" "$HOME/storage/shared/Download" -maxdepth 2 -type f -iname 'Winlator_11.1.apk' 2>/dev/null | head -1 || true)"
fi
[ -n "${APK:-}" ] && [ -f "$APK" ] || {
  echo "ERROR: Winlator_11.1.apk not found in Download" >&2
  exit 3
}

actual_sha="$(sha256sum "$APK" | awk '{print $1}')"
if [ "$actual_sha" != "$EXPECTED_SHA" ]; then
  echo "ERROR: APK SHA256 mismatch" >&2
  echo "EXPECTED=$EXPECTED_SHA" >&2
  echo "ACTUAL=$actual_sha" >&2
  exit 4
fi

mkdir -p "$WORK/assets" "$WORK/patchroot"

python3 - "$APK" "$WORK/assets" <<'PY'
from pathlib import Path
import sys, zipfile

apk = Path(sys.argv[1])
out = Path(sys.argv[2])
needed = [
    'assets/rootfs.tzst',
    'assets/rootfs_patches.tzst',
    'assets/box64/default.box64rc',
    'assets/box64/env_vars.json',
]
with zipfile.ZipFile(apk) as z:
    names = set(z.namelist())
    missing = [name for name in needed[:2] if name not in names]
    if missing:
        raise SystemExit('missing required APK assets: ' + ', '.join(missing))
    for name in needed:
        if name not in names:
            continue
        target = out / Path(name).name
        with z.open(name) as src, target.open('wb') as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
PY

ROOTFS="$WORK/assets/rootfs.tzst"
PATCHES="$WORK/assets/rootfs_patches.tzst"
ROOT_LIST="$WORK/rootfs.list"
PATCH_LIST="$WORK/patches.list"

zstd -t "$ROOTFS" >/dev/null
zstd -t "$PATCHES" >/dev/null
zstd -dc "$ROOTFS" | tar -tf - >"$ROOT_LIST"
zstd -dc "$PATCHES" | tar -tf - >"$PATCH_LIST"

wine_entry="$(grep -m1 -E '^\.?/?opt/wine/bin/wine$' "$ROOT_LIST" || true)"
if [ -z "$wine_entry" ]; then
  wine_entry="$(grep -m1 -E '(^|/)opt/wine/bin/wine$' "$ROOT_LIST" || true)"
fi
[ -n "$wine_entry" ] || {
  echo "ERROR: opt/wine/bin/wine not found inside rootfs.tzst" >&2
  exit 5
}

wine_subtree="${wine_entry%/bin/wine}"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"
zstd -dc "$ROOTFS" | tar -xf - -C "$RUNTIME" "$wine_subtree"

# Apply Winlator's rootfs overlay exactly as packaged. The patch archive is small,
# and extracting it under the isolated runtime root cannot touch Android or Mobox.
zstd -dc "$PATCHES" | tar -xf - -C "$WORK/patchroot"
patch_wine="$(find "$WORK/patchroot" -type d -path '*/opt/wine' -print -quit || true)"
if [ -n "$patch_wine" ]; then
  target_wine="$(find "$RUNTIME" -type d -path '*/opt/wine' -print -quit || true)"
  [ -n "$target_wine" ] || { echo "ERROR: extracted Wine root missing" >&2; exit 6; }
  cp -a "$patch_wine"/. "$target_wine"/
fi

wine_bin="$(find "$RUNTIME" -type f -path '*/opt/wine/bin/wine' -print -quit || true)"
[ -n "$wine_bin" ] || { echo "ERROR: extracted wine binary missing" >&2; exit 7; }
wroot="${wine_bin%/bin/wine}"
wineserver_bin="$wroot/bin/wineserver"

{
  echo "WINLATOR 11.1 ROOTFS WINE PROBE"
  echo "================================"
  date -Iseconds
  echo "APK=$APK"
  echo "APK_SHA256=$actual_sha"
  echo "APK_SHA256_MATCH=1"
  echo "ROOTFS_COMPRESSED_SIZE=$(stat -c %s "$ROOTFS")"
  echo "PATCHES_COMPRESSED_SIZE=$(stat -c %s "$PATCHES")"
  echo "ROOTFS_WINE_ENTRY=$wine_entry"
  echo "EXTRACTED_RUNTIME=$RUNTIME"
  echo "EXTRACTED_WROOT=$wroot"
  echo "PATCH_WINE_OVERLAY=$([ -n "$patch_wine" ] && echo 1 || echo 0)"
  echo
  echo "=== ROOTFS KEY ENTRIES ==="
  grep -E '(^|/)(opt/wine|usr/lib.*/wine|wine64|wineserver|wineboot|wine\.inf)(/|$)' "$ROOT_LIST" | head -300 || true
  echo
  echo "=== ROOTFS PATCH KEY ENTRIES ==="
  grep -E '(^|/)(opt/wine|usr/lib.*/wine|wine64|wineserver|wineboot|wine\.inf)(/|$)' "$PATCH_LIST" | head -300 || true
  echo
  echo "=== EXTRACTED FILE IDENTITY ==="
  file "$wine_bin" || true
  [ -e "$wineserver_bin" ] && file "$wineserver_bin" || true
  sha256sum "$wine_bin" || true
  [ -e "$wineserver_bin" ] && sha256sum "$wineserver_bin" || true
  echo
  echo "=== EXTRACTED WINE TREE SIZE ==="
  du -sh "$wroot" || true
  echo
  echo "=== STRING VERSION CANDIDATES ==="
  if command -v strings >/dev/null 2>&1; then
    strings "$wine_bin" 2>/dev/null | grep -Eio 'wine[- ]?[0-9]+([.][0-9]+){1,3}[^[:space:]]*' | head -40 || true
    strings "$wineserver_bin" 2>/dev/null | grep -Eio 'wine[- ]?[0-9]+([.][0-9]+){1,3}[^[:space:]]*' | head -40 || true
  else
    echo "strings command unavailable"
  fi
  echo
  echo "=== DEFAULT BOX64RC ==="
  [ -f "$WORK/assets/default.box64rc" ] && cat "$WORK/assets/default.box64rc" || echo "NOT_PRESENT"
  echo
  echo "=== BOX64 ENV VAR METADATA ==="
  [ -f "$WORK/assets/env_vars.json" ] && cat "$WORK/assets/env_vars.json" || echo "NOT_PRESENT"
} >"$REPORT"

# Run only the harmless --version probe. No Wine prefix is created and no game is launched.
set +e
proot-distro login debian \
  --bind "$RUNTIME:/mnt/winlator-runtime" \
  --env PROBE_REPORT="/mnt/downloads/WINLATOR_11_1_ROOTFS_WINE_PROBE.txt" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  -- bash -s >>"$REPORT" 2>&1 <<'DEBIAN'
set -u
BOX=/root/box64/build/box64
wine_bin="$(find /mnt/winlator-runtime -type f -path '*/opt/wine/bin/wine' -print -quit)"
wroot="${wine_bin%/bin/wine}"

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_DYNACACHE=0
export BOX64_PATH="$wroot/bin"
export BOX64_LD_LIBRARY_PATH="$wroot/lib/wine/x86_64-unix:$wroot/lib:$wroot/lib64:/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"

echo
echo "=== BOX64 WINE --VERSION PROBE ==="
echo "BOX=$BOX"
echo "WROOT=$wroot"
if [ ! -x "$BOX" ]; then
  echo "PROBE_RESULT=box64_missing"
  exit 20
fi
if [ ! -x "$wine_bin" ]; then
  echo "PROBE_RESULT=wine_not_executable"
  exit 21
fi

timeout 30s "$BOX" "$wine_bin" --version
rc=$?
echo "PROBE_EXIT=$rc"
exit "$rc"
DEBIAN
probe_rc=$?
set -e

echo "PROBE_WRAPPER_EXIT=$probe_rc" >>"$REPORT"
termux-media-scan "$REPORT" >/dev/null 2>&1 || true

echo "ROOTFS_WINE_PROBE_READY"
echo "RUNTIME=$RUNTIME"
echo "REPORT=$REPORT"
echo "PROBE_EXIT=$probe_rc"
