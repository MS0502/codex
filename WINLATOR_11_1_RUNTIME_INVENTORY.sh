#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

OUT="${HOME}/storage/downloads/WINLATOR_11_1_RUNTIME_INVENTORY.txt"
TMP="${PREFIX:-/data/data/com.termux/files/usr}/tmp/winlator_runtime_inventory.$$"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

PM=/system/bin/pm
DUMPSYS=/system/bin/dumpsys

if [ ! -x "$PM" ]; then
  echo "ERROR: Android package manager not found: $PM" >&2
  exit 2
fi

packages="$($PM list packages 2>/dev/null | sed 's/^package://' | grep -i 'winlator' || true)"
if [ -z "$packages" ]; then
  echo "ERROR: no installed package containing winlator was found" >&2
  exit 3
fi

{
  echo "WINLATOR 11.1 RUNTIME INVENTORY"
  echo "================================"
  date -Iseconds
  echo
  echo "=== MATCHING PACKAGES ==="
  printf '%s\n' "$packages"
  echo
} >"$OUT"

for pkg in $packages; do
  {
    echo "=== PACKAGE: $pkg ==="
    if [ -x "$DUMPSYS" ]; then
      "$DUMPSYS" package "$pkg" 2>/dev/null | grep -E 'versionName=|versionCode=|codePath=|primaryCpuAbi=|secondaryCpuAbi=' | head -30 || true
    fi
    echo
    echo "--- APK PATHS ---"
  } >>"$OUT"

  apk_paths="$($PM path "$pkg" 2>/dev/null | sed 's/^package://' || true)"
  printf '%s\n' "$apk_paths" >>"$OUT"

  idx=0
  for apk in $apk_paths; do
    idx=$((idx + 1))
    echo >>"$OUT"
    echo "--- APK $idx ZIP INVENTORY: $apk ---" >>"$OUT"

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
    with apk.open('rb') as f:
        digest = hashlib.sha256(f.read(8 * 1024 * 1024)).hexdigest()
    with zipfile.ZipFile(apk) as z:
        infos = z.infolist()
        matched = [i for i in infos if patterns.search(i.filename)]
        libs = [i for i in infos if i.filename.startswith('lib/arm64-v8a/')]
        with out.open('a', errors='replace') as w:
            w.write(f'APK_SIZE={apk.stat().st_size}\n')
            w.write(f'APK_FIRST8M_SHA256={digest}\n')
            w.write(f'ZIP_ENTRY_COUNT={len(infos)}\n')
            w.write('\nMATCHED_ENTRIES\n')
            for i in matched[:2500]:
                w.write(f'{i.file_size:12d} {i.compress_size:12d} {i.filename}\n')
            if len(matched) > 2500:
                w.write(f'... TRUNCATED {len(matched) - 2500} MATCHED ENTRIES ...\n')
            w.write('\nARM64_LIBRARIES\n')
            for i in libs[:1000]:
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
                hit_lines = []
                for line in data.splitlines():
                    if patterns.search(line) or '10.10' in line or '11.1' in line:
                        # Do not dump very long or credential-like lines.
                        if len(line) <= 500 and 'authkey' not in line.lower() and 'token' not in line.lower():
                            hit_lines.append(line)
                if hit_lines:
                    w.write(f'[{i.filename}]\n')
                    for line in hit_lines[:80]:
                        w.write(line + '\n')
except Exception as exc:
    with out.open('a') as w:
        w.write(f'APK_READ_ERROR={type(exc).__name__}: {exc}\n')
PY
  done

  {
    echo
    echo "--- SHARED STORAGE VISIBILITY ---"
    for d in \
      "/sdcard/Android/data/$pkg" \
      "/storage/emulated/0/Android/data/$pkg" \
      "${HOME}/storage/shared/Android/data/$pkg"; do
      if [ -e "$d" ]; then
        echo "VISIBLE $d"
        find "$d" -maxdepth 4 -type f 2>/dev/null | grep -Ei '(wine|box64|rootfs|imagefs|component|dxvk|vkd3d)' | head -300 || true
      else
        echo "NOT_VISIBLE $d"
      fi
    done
    echo
  } >>"$OUT"
done

termux-media-scan "$OUT" >/dev/null 2>&1 || true

echo "RUNTIME_INVENTORY_READY"
echo "REPORT=$OUT"
