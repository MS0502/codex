#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

OUT="${HOME}/storage/downloads/WINLATOR_11_1_RUNTIME_INVENTORY_V2.txt"
TMP="${PREFIX:-/data/data/com.termux/files/usr}/tmp/winlator_runtime_inventory_v2.$$"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

PM=/system/bin/pm
CMD=/system/bin/cmd
DUMPSYS=/system/bin/dumpsys

if [ ! -x "$PM" ]; then
  echo "ERROR: Android package manager not found: $PM" >&2
  exit 2
fi

candidates=(
  com.winlator
  com.winlator.cmod
  com.winlator.bionic
  com.winlator.glibc
  com.winlator.frost
  com.winlator.afei
  com.winlator.xmod
  com.winlator.mali
)

: >"$TMP/packages.txt"
: >"$TMP/probes.txt"

add_pkg() {
  local pkg="$1"
  [ -n "$pkg" ] || return 0
  grep -Fxq "$pkg" "$TMP/packages.txt" 2>/dev/null || printf '%s\n' "$pkg" >>"$TMP/packages.txt"
}

# Normal discovery. Some Android versions hide packages from an app UID, so this
# is only one source and is not treated as authoritative.
$PM list packages 2>/dev/null \
  | sed 's/^package://' \
  | grep -i 'winlator' \
  | while IFS= read -r pkg; do add_pkg "$pkg"; done || true

# Explicit package probes bypass the substring-discovery failure seen on some
# Samsung/Android builds. Official Winlator normally uses com.winlator.
for pkg in "${candidates[@]}"; do
  pm_out="$($PM path "$pkg" 2>&1 || true)"
  cmd_out=""
  if [ -x "$CMD" ]; then
    cmd_out="$($CMD package path "$pkg" 2>&1 || true)"
  fi
  {
    echo "PACKAGE=$pkg"
    echo "PM_PATH=$(printf '%s' "$pm_out" | tr '\n' ' ')"
    echo "CMD_PATH=$(printf '%s' "$cmd_out" | tr '\n' ' ')"
  } >>"$TMP/probes.txt"
  if printf '%s\n%s\n' "$pm_out" "$cmd_out" | grep -q '^package:'; then
    add_pkg "$pkg"
  fi
done

# Installer APK fallback. This still identifies bundled Wine/Box64/runtime assets
# even when Android package visibility blocks installed-package discovery.
: >"$TMP/apks.txt"
for base in \
  "${HOME}/storage/downloads" \
  "${HOME}/storage/shared/Download" \
  "/sdcard/Download" \
  "/storage/emulated/0/Download"; do
  [ -d "$base" ] || continue
  find "$base" -maxdepth 3 -type f \( -iname '*winlator*.apk' -o -iname 'Winlator_11.1.apk' \) \
    2>/dev/null >>"$TMP/apks.txt" || true
done
sort -u "$TMP/apks.txt" -o "$TMP/apks.txt"

{
  echo "WINLATOR 11.1 RUNTIME INVENTORY V2"
  echo "==================================="
  date -Iseconds
  echo
  echo "=== DISCOVERED INSTALLED PACKAGES ==="
  if [ -s "$TMP/packages.txt" ]; then
    cat "$TMP/packages.txt"
  else
    echo "NONE_VISIBLE_TO_TERMUX"
  fi
  echo
  echo "=== EXPLICIT PACKAGE PROBES ==="
  cat "$TMP/probes.txt"
  echo
  echo "=== INSTALLER APK FALLBACKS ==="
  if [ -s "$TMP/apks.txt" ]; then
    cat "$TMP/apks.txt"
  else
    echo "NONE_FOUND"
  fi
  echo
} >"$OUT"

inventory_apk() {
  local apk="$1"
  local label="$2"
  {
    echo "=== APK INVENTORY: $label ==="
    echo "APK_PATH=$apk"
  } >>"$OUT"

  python3 - "$apk" "$OUT" <<'PY'
from pathlib import Path
import hashlib
import re
import sys
import zipfile

apk = Path(sys.argv[1])
out = Path(sys.argv[2])
patterns = re.compile(
    r'(wine|box64|box86|glibc|rootfs|imagefs|container|component|dxvk|vkd3d|'
    r'vcrun|msvcr|msvcp|xaudio|directx|turnip|zink|alsa|esync|winetricks)',
    re.I,
)
text_ext = ('.txt', '.json', '.xml', '.ini', '.conf', '.cfg', '.properties', '.sh', '.md')

try:
    stat = apk.stat()
    h = hashlib.sha256()
    with apk.open('rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    with zipfile.ZipFile(apk) as z:
        infos = z.infolist()
        matched = [i for i in infos if patterns.search(i.filename)]
        libs = [i for i in infos if i.filename.startswith('lib/arm64-v8a/')]
        with out.open('a', errors='replace') as w:
            w.write(f'APK_SIZE={stat.st_size}\n')
            w.write(f'APK_SHA256={h.hexdigest()}\n')
            w.write(f'ZIP_ENTRY_COUNT={len(infos)}\n')
            w.write('\nMATCHED_ENTRIES\n')
            for i in matched[:4000]:
                w.write(f'{i.file_size:12d} {i.compress_size:12d} {i.filename}\n')
            if len(matched) > 4000:
                w.write(f'... TRUNCATED {len(matched) - 4000} MATCHED ENTRIES ...\n')
            w.write('\nARM64_LIBRARIES\n')
            for i in libs[:1500]:
                w.write(f'{i.file_size:12d} {i.compress_size:12d} {i.filename}\n')
            w.write('\nSMALL_TEXT_METADATA_HITS\n')
            for i in infos:
                low = i.filename.lower()
                if i.file_size > 2 * 1024 * 1024 or not low.endswith(text_ext):
                    continue
                try:
                    data = z.read(i).decode('utf-8', errors='replace')
                except Exception:
                    continue
                hits = []
                for line in data.splitlines():
                    if patterns.search(line) or '10.10' in line or '11.1' in line:
                        if len(line) <= 500 and 'authkey' not in line.lower() and 'token' not in line.lower():
                            hits.append(line)
                if hits:
                    w.write(f'[{i.filename}]\n')
                    for line in hits[:100]:
                        w.write(line + '\n')
except Exception as exc:
    with out.open('a') as w:
        w.write(f'APK_READ_ERROR={type(exc).__name__}: {exc}\n')
PY
  echo >>"$OUT"
}

# Installed package APKs.
while IFS= read -r pkg; do
  [ -n "$pkg" ] || continue
  {
    echo "=== PACKAGE METADATA: $pkg ==="
    if [ -x "$DUMPSYS" ]; then
      "$DUMPSYS" package "$pkg" 2>/dev/null \
        | grep -E 'versionName=|versionCode=|codePath=|primaryCpuAbi=|secondaryCpuAbi=' \
        | head -40 || true
    fi
    echo
  } >>"$OUT"

  apk_paths="$($PM path "$pkg" 2>/dev/null | sed 's/^package://' || true)"
  if [ -z "$apk_paths" ] && [ -x "$CMD" ]; then
    apk_paths="$($CMD package path "$pkg" 2>/dev/null | sed 's/^package://' || true)"
  fi
  idx=0
  for apk in $apk_paths; do
    idx=$((idx + 1))
    inventory_apk "$apk" "$pkg#$idx"
  done
done <"$TMP/packages.txt"

# Downloaded installer APKs, deduplicated by path.
idx=0
while IFS= read -r apk; do
  [ -n "$apk" ] || continue
  idx=$((idx + 1))
  inventory_apk "$apk" "download#$idx"
done <"$TMP/apks.txt"

{
  echo "=== FINAL STATUS ==="
  if grep -q '^=== APK INVENTORY:' "$OUT"; then
    echo "APK_INVENTORY_AVAILABLE=1"
  else
    echo "APK_INVENTORY_AVAILABLE=0"
    echo "NEXT_ACTION=Run /system/bin/pm path com.winlator and report its exact output."
  fi
} >>"$OUT"

termux-media-scan "$OUT" >/dev/null 2>&1 || true

echo "RUNTIME_INVENTORY_V2_READY"
echo "REPORT=$OUT"
