#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${ARTIFACT_ID:?ARTIFACT_ID is required}"
: "${EXPECTED_APK_SHA256:?EXPECTED_APK_SHA256 is required}"
: "${RUNTIME_NAME:?RUNTIME_NAME is required}"
: "${STARTUP:?STARTUP is required}"

case "$STARTUP" in
  wfm) EXE=wfm.exe ;;
  cmd) EXE=cmd.exe ;;
  *) echo "unsupported STARTUP=$STARTUP" >&2; exit 2 ;;
esac

ROOT="$PWD"
EVIDENCE="$ROOT/evidence"
mkdir -p artifact apk rootfs box64 prefix "$EVIDENCE"

cleanup() {
  set +e
  sudo pkill -KILL box64 2>/dev/null || true
  sudo pkill -KILL Xvfb 2>/dev/null || true
  sudo umount -l rootfs/tmp 2>/dev/null || true
  sudo umount -l rootfs/proc 2>/dev/null || true
  sudo umount -R -l rootfs/sys 2>/dev/null || true
  sudo umount -R -l rootfs/dev 2>/dev/null || true
}
trap cleanup EXIT

curl --fail --location --retry 3 \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/artifacts/${ARTIFACT_ID}/zip" \
  -o artifact.zip
unzip -q artifact.zip -d artifact
APK="$(find artifact -maxdepth 1 -type f -name '*.apk' -print -quit)"
test -n "$APK"
printf '%s  %s\n' "$EXPECTED_APK_SHA256" "$APK" | sha256sum -c -
cp "$APK" runtime.apk
sha256sum runtime.apk | tee "$EVIDENCE/apk-sha256.txt"

unzip -q runtime.apk \
  assets/rootfs.tzst \
  assets/rootfs_patches.tzst \
  assets/container_pattern.tzst \
  assets/box64/box64-0.4.0.tzst \
  assets/common_dlls.json \
  -d apk

tar --use-compress-program=unzstd -xf apk/assets/rootfs.tzst -C rootfs
tar --use-compress-program=unzstd -xf apk/assets/box64/box64-0.4.0.tzst -C box64
tar --use-compress-program=unzstd -xf apk/assets/container_pattern.tzst -C prefix

sudo install -D -m 0755 box64/usr/local/bin/box64 rootfs/usr/local/bin/box64
sudo mkdir -p rootfs/home/xuser rootfs/data/data/com.winlator.trcompat/files
sudo cp -a prefix/.wine rootfs/home/xuser/.wine
sudo ln -sfn / rootfs/data/data/com.winlator.trcompat/files/rootfs
sudo mkdir -p rootfs/etc rootfs/var/lib/dbus rootfs/tmp rootfs/dev rootfs/proc rootfs/sys
printf '%s\n' 0123456789abcdef0123456789abcdef | sudo tee rootfs/etc/machine-id >/dev/null
sudo ln -sfn /etc/machine-id rootfs/var/lib/dbus/machine-id

sudo python3 tr_winlator_apk/materialize_main_wine_container.py \
  rootfs rootfs/home/xuser apk/assets/common_dlls.json \
  | tee "$EVIDENCE/container-materialization.txt"

# Winlator's app-level shell executables are delivered by rootfs_patches,
# not by rootfs.tzst or container_pattern.tzst. Apply them before hashing
# or launching the exact C:\windows\winhandler.exe -> wfm/cmd path.
sudo tar --use-compress-program=unzstd -xf apk/assets/rootfs_patches.tzst -C rootfs

# The archived prefix may preserve a non-root owner. This harness launches
# Wine as root inside chroot, so normalize ownership after every extraction.
sudo chown -R 0:0 rootfs/home/xuser/.wine

file rootfs/usr/local/bin/box64 rootfs/opt/wine/bin/wine \
  rootfs/opt/wine/bin/wineserver \
  rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \
  | tee "$EVIDENCE/runtime-file-types.txt"

sha256sum \
  rootfs/opt/wine/bin/wine \
  rootfs/opt/wine/bin/wineserver \
  rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \
  rootfs/home/xuser/.wine/drive_c/windows/wfm.exe \
  rootfs/home/xuser/.wine/drive_c/windows/winhandler.exe \
  | tee "$EVIDENCE/runtime-sha256.txt"

gcc -O2 -Wall -Wextra tr_winlator_apk/x11_structure_trace.c \
  -o x11_structure_trace -lX11
file x11_structure_trace | tee "$EVIDENCE/xevent-trace-file.txt"

sudo mount --rbind /dev rootfs/dev
sudo mount --make-rslave rootfs/dev
sudo mount -t proc proc rootfs/proc
sudo mount --rbind /sys rootfs/sys
sudo mount --make-rslave rootfs/sys
sudo mount --bind /tmp rootfs/tmp

Xvfb :99 -ac -screen 0 1280x720x24 -nolisten tcp >"$EVIDENCE/xserver.log" 2>&1 &
echo $! > "$EVIDENCE/xserver.pid"
for _ in $(seq 1 40); do
  xdpyinfo -display :99 >/dev/null 2>&1 && break
  sleep 1
done
xdpyinfo -display :99 > "$EVIDENCE/xdpyinfo.txt"

DISPLAY=:99 ./x11_structure_trace >"$EVIDENCE/xevents.txt" 2>&1 &
EVENT_PID=$!

printf 'runtime=%s\nstartup=%s\nexe=%s\n' "$RUNTIME_NAME" "$STARTUP" "$EXE" \
  | tee "$EVIDENCE/case.txt"

sudo env HOME=/home/xuser USER=xuser DISPLAY=:99 XAUTHORITY=/dev/null \
  WINEPREFIX=/home/xuser/.wine WINEDEBUG=warn+all,err+all \
  WINEESYNC=1 WINE_DO_NOT_CREATE_DXGI_DEVICE_MANAGER=1 \
  MESA_DEBUG=silent MESA_NO_ERROR=1 \
  PATH=/opt/wine/bin:/usr/local/bin:/usr/bin:/bin \
  LD_LIBRARY_PATH=/lib:/usr/lib:/usr/lib/aarch64-linux-gnu \
  BOX64_NOBANNER=0 BOX64_LOG=1 BOX64_DYNAREC=1 \
  BOX64_PATH=/opt/wine/bin:/usr/bin:/bin \
  BOX64_LD_LIBRARY_PATH=/opt/wine/lib:/usr/lib:/lib \
  /usr/bin/timeout --signal=TERM 75s \
  /usr/sbin/chroot rootfs /usr/local/bin/box64 /opt/wine/bin/wine \
  explorer /desktop=shell,1280x720 \
  'C:\windows\winhandler.exe' /dir 'C:\windows' "$EXE" \
  >"$EVIDENCE/wine.log" 2>&1 &
RUNTIME_PID=$!
echo "$RUNTIME_PID" > "$EVIDENCE/runtime.pid"

alive=0
desktop_seen=0
app_seen=0
app_viewable=0
app_unmapped=0
previous=0

for second in 3 10 20 40 60; do
  sleep "$((second - previous))"
  previous=$second
  kill -0 "$RUNTIME_PID" 2>/dev/null && alive=$((alive + 1)) || true

  TREE="$EVIDENCE/xwininfo-${second}.txt"
  xwininfo -display :99 -root -tree >"$TREE" 2>&1 || true
  grep -q 'shell - Wine Desktop' "$TREE" \
    && desktop_seen=$((desktop_seen + 1)) || true

  if [ "$STARTUP" = wfm ]; then
    ID="$(awk '/"Computer"/ {print $1; exit}' "$TREE")"
  else
    ID="$(awk '/cmd.exe/ {print $1; exit}' "$TREE")"
  fi

  if [ -n "$ID" ]; then
    app_seen=$((app_seen + 1))
    xwininfo -display :99 -id "$ID" -all \
      >"$EVIDENCE/app-${second}.txt" 2>&1 || true
    xprop -display :99 -id "$ID" \
      >"$EVIDENCE/app-${second}-xprop.txt" 2>&1 || true
    grep -Fq 'Map State: IsViewable' "$EVIDENCE/app-${second}.txt" \
      && app_viewable=$((app_viewable + 1)) || true
    grep -Fq 'Map State: IsUnMapped' "$EVIDENCE/app-${second}.txt" \
      && app_unmapped=$((app_unmapped + 1)) || true
  fi

  import -display :99 -window root "$EVIDENCE/root-${second}.png" || true
done

printf 'runtime=%s\nstartup=%s\nalive_checks=%s\ndesktop_checks=%s\napp_checks=%s\nviewable_checks=%s\nunmapped_checks=%s\n' \
  "$RUNTIME_NAME" "$STARTUP" "$alive" "$desktop_seen" "$app_seen" \
  "$app_viewable" "$app_unmapped" | tee "$EVIDENCE/result.txt"

grep -Ei \
  'c0000005|handle_state_change|DestroyNotify|winebus[^[:space:]]*c0000135|service.*126|RpcSs.*fail|segmentation fault|SIGSEGV' \
  "$EVIDENCE/wine.log" > "$EVIDENCE/focused-wine-markers.txt" || true

kill "$RUNTIME_PID" 2>/dev/null || true
wait "$RUNTIME_PID" || true
wait "$EVENT_PID" || true

test "$alive" -ge 4
test "$desktop_seen" -ge 4
