#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="/storage/emulated/0/Download/TR_DIAG_V18"
BASE="/storage/emulated/0/Download/TR_KR_LOCAL"
GAME="$BASE/game"
TRGAME="$GAME/trgame.exe"
EXPECTED_TRGAME_SHA256="35403c283d7a2e28cc9bffc833bf14742c482c742d51760ac52b02a8fced5e61"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$ROOT/run_$STAMP"
RUNTIME="$ROOT/runtime"
ARCHIVE="/storage/emulated/0/Download/TR_DIAG_V18_${STAMP}.zip"
PKG="com.winlator.trcompat"

mkdir -p "$OUT"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"

exec > >(tee -a "$OUT/collector_console.txt") 2>&1

echo "TR Diagnostic v18"
echo "started=$(date -Iseconds)"
echo "output=$OUT"

if [ ! -f "$TRGAME" ]; then
  echo "ERROR: current trgame.exe not found: $TRGAME"
  exit 2
fi

actual_hash="$(sha256sum "$TRGAME" | awk '{print $1}')"
actual_size="$(stat -c '%s' "$TRGAME")"
{
  echo "expected_sha256=$EXPECTED_TRGAME_SHA256"
  echo "actual_sha256=$actual_hash"
  echo "size=$actual_size"
  echo "path=$TRGAME"
} > "$OUT/current_trgame.txt"

if [ "$actual_hash" != "$EXPECTED_TRGAME_SHA256" ]; then
  echo "ERROR: trgame.exe changed. Refusing to mix a new build with the v18 baseline."
  echo "EXPECTED=$EXPECTED_TRGAME_SHA256"
  echo "ACTUAL=$actual_hash"
  termux-media-scan "$OUT/current_trgame.txt" >/dev/null 2>&1 || true
  exit 3
fi

echo "CURRENT_TRGAME_VERIFIED"

{
  echo "created=$(date -Iseconds)"
  echo "uname=$(uname -a 2>/dev/null || true)"
  echo "model=$(getprop ro.product.model 2>/dev/null || true)"
  echo "android=$(getprop ro.build.version.release 2>/dev/null || true)"
  echo "sdk=$(getprop ro.build.version.sdk 2>/dev/null || true)"
  echo "abi=$(getprop ro.product.cpu.abi 2>/dev/null || true)"
  echo "winlator_package=$PKG"
  /system/bin/dumpsys package "$PKG" 2>/dev/null \
    | grep -E 'versionName=|versionCode=|debuggable|firstInstallTime=|lastUpdateTime=' \
    | head -n 30 || true
} > "$OUT/environment.txt"

capture_pid=""
if run-as "$PKG" true >/dev/null 2>&1; then
  echo "RUN_AS_AVAILABLE=true" | tee "$OUT/access.txt"
  (
    end=$((SECONDS + 240))
    while [ "$SECONDS" -lt "$end" ] && [ ! -f "$RUNTIME/WINDOWS_DONE.flag" ]; do
      now="$(date +%s%3N)"
      run-as "$PKG" sh -c '
        for p in /proc/[0-9]*; do
          [ -r "$p/cmdline" ] || continue
          cmd=$(tr "\000" " " < "$p/cmdline" 2>/dev/null)
          case "$cmd" in
            *talesrunner.exe*|*xldr_TalesRunner_KR_loader_x64.exe*|*trgame.exe*)
              pid=${p##*/}
              echo "PID=$pid CMD=$cmd"
              if [ -r "$p/status" ]; then
                grep -E "^(Name|State|PPid|Uid|Gid|Threads):" "$p/status" 2>/dev/null || true
              fi
              if [ -r "$p/maps" ]; then
                echo "--- MAPS pid=$pid ---"
                cat "$p/maps" 2>/dev/null || true
              fi
              echo "--- END pid=$pid ---"
              ;;
          esac
        done
      ' > "$OUT/proc_${now}.txt" 2>&1 || true
      sleep 0.25
    done
  ) &
  capture_pid=$!
else
  echo "RUN_AS_AVAILABLE=false" | tee "$OUT/access.txt"
  echo "The installed Winlator package is not debuggable; Android process maps cannot be read by this collector." >> "$OUT/access.txt"
fi

logcat_pid=""
if logcat -d -t 1 >/dev/null 2>&1; then
  logcat -c >/dev/null 2>&1 || true
  logcat -v threadtime > "$OUT/android_logcat.txt" 2>&1 &
  logcat_pid=$!
fi

# Open Winlator. The user only needs to run the staged BAT from the shared folder.
monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true

echo
echo "Winlator에서 다음 BAT를 한 번 실행하세요:"
echo 'Z:\\sdcard\\Download\\TR_DIAG_V18\\TR_DIAG_V18_WINDOWS.bat'
echo "최대 4분 동안 완료 신호를 기다립니다."

end=$((SECONDS + 240))
while [ "$SECONDS" -lt "$end" ]; do
  [ -f "$RUNTIME/WINDOWS_DONE.flag" ] && break
  sleep 1
done

if [ -n "$capture_pid" ]; then
  wait "$capture_pid" 2>/dev/null || true
fi
if [ -n "$logcat_pid" ]; then
  kill "$logcat_pid" 2>/dev/null || true
  wait "$logcat_pid" 2>/dev/null || true
fi

if [ -d "$RUNTIME" ]; then
  cp -a "$RUNTIME/." "$OUT/runtime/" 2>/dev/null || true
fi

# Remove transient authentication material from all collected text before archive creation.
find "$OUT" -type f \( -iname '*.txt' -o -iname '*.log' -o -iname '*.csv' \) -print0 \
| while IFS= read -r -d '' f; do
    tmp="$f.redacted"
    sed -E \
      -e 's/(-authkey:)[^[:space:]"'"']+/\1[REDACTED]/gI' \
      -e 's/(authkey[=:])[A-Za-z0-9._~+\/-]+/\1[REDACTED]/gI' \
      -e 's/(authorization:[[:space:]]*)(Bearer[[:space:]]+)?[^[:space:]]+/\1[REDACTED]/gI' \
      -e 's/(token[=:])[A-Za-z0-9._~+\/-]+/\1[REDACTED]/gI' \
      "$f" > "$tmp" 2>/dev/null && mv -f "$tmp" "$f" || rm -f "$tmp"
  done

{
  echo "finished=$(date -Iseconds)"
  echo "windows_done=$([ -f "$RUNTIME/WINDOWS_DONE.flag" ] && echo true || echo false)"
  echo "trgame_sha256=$actual_hash"
  echo "archive=$ARCHIVE"
} > "$OUT/summary.txt"

rm -f "$ARCHIVE"
(cd "$(dirname "$OUT")" && zip -qr "$ARCHIVE" "$(basename "$OUT")")
termux-media-scan "$ARCHIVE" >/dev/null 2>&1 || true

echo
echo "[OK] $ARCHIVE"
