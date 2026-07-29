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
DISPLAY_NUMBER=100
TCP_DISPLAY="127.0.0.1:${DISPLAY_NUMBER}.0"
ANDROID_TMP=/data/user/0/com.winlator.trcompat/r/tmp
mkdir -p artifact apk rootfs box64 prefix "$EVIDENCE"

cleanup() {
  set +e
  sudo pkill -KILL box64 2>/dev/null || true
  sudo pkill -KILL Xorg 2>/dev/null || true
  sudo umount -l rootfs/tmp 2>/dev/null || true
  sudo umount -l rootfs/proc 2>/dev/null || true
  sudo umount -R -l rootfs/sys 2>/dev/null || true
  sudo umount -R -l rootfs/dev 2>/dev/null || true
}
trap cleanup EXIT

# The earlier Xvfb run was not equivalent to the proven ARM64 shell harness:
# Proton stayed alive but created no desktop, while Wine 10.10 stopped at its
# Android-specific wineserver temp directory. Use the same Xorg dummy/TCP
# presentation path for both runtimes and materialize the Android paths first.
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  xserver-xorg-core xserver-xorg-video-dummy \
  >"$EVIDENCE/xorg-packages.txt" 2>&1

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
sudo mkdir -p \
  rootfs/home/xuser \
  rootfs/data/data/com.winlator.trcompat/files \
  rootfs/data/user/0/com.winlator.trcompat/files \
  "rootfs${ANDROID_TMP}" \
  rootfs/etc rootfs/var/lib/dbus rootfs/tmp rootfs/dev rootfs/proc rootfs/sys
sudo cp -a prefix/.wine rootfs/home/xuser/.wine
sudo ln -sfn / rootfs/data/data/com.winlator.trcompat/files/rootfs
sudo ln -sfn / rootfs/data/user/0/com.winlator.trcompat/files/rootfs
sudo chmod 1777 "rootfs${ANDROID_TMP}"
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

cat > xorg-dummy.conf <<'XORG'
Section "ServerFlags"
    Option "AutoAddDevices" "false"
    Option "DontVTSwitch" "true"
    Option "AllowMouseOpenFail" "true"
EndSection
Section "Device"
    Identifier "DummyDevice"
    Driver "dummy"
    VideoRam 256000
EndSection
Section "Monitor"
    Identifier "DummyMonitor"
    HorizSync 5.0-1000.0
    VertRefresh 5.0-200.0
    Modeline "1280x720" 74.50 1280 1344 1472 1664 720 723 728 748
EndSection
Section "Screen"
    Identifier "DummyScreen"
    Device "DummyDevice"
    Monitor "DummyMonitor"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1280x720"
    EndSubSection
EndSection
Section "ServerLayout"
    Identifier "DummyLayout"
    Screen "DummyScreen"
EndSection
XORG

sudo mount --rbind /dev rootfs/dev
sudo mount --make-rslave rootfs/dev
sudo mount -t proc proc rootfs/proc
sudo mount --rbind /sys rootfs/sys
sudo mount --make-rslave rootfs/sys
sudo mount --bind /tmp rootfs/tmp

sudo Xorg ":${DISPLAY_NUMBER}" -noreset -ac -listen tcp \
  -config "$ROOT/xorg-dummy.conf" -logfile "$EVIDENCE/Xorg.log" \
  >"$EVIDENCE/xserver.log" 2>&1 &
echo $! > "$EVIDENCE/xserver.pid"
for _ in $(seq 1 40); do
  xdpyinfo -display "$TCP_DISPLAY" >/dev/null 2>&1 && break
  sleep 1
done
xdpyinfo -display "$TCP_DISPLAY" > "$EVIDENCE/xdpyinfo.txt"
grep -Eq 'dimensions:[[:space:]]+1280x720' "$EVIDENCE/xdpyinfo.txt"

DISPLAY="$TCP_DISPLAY" ./x11_structure_trace >"$EVIDENCE/xevents.txt" 2>&1 &
EVENT_PID=$!

printf 'runtime=%s\nstartup=%s\nexe=%s\ndisplay=%s\nandroid_tmp=%s\n' \
  "$RUNTIME_NAME" "$STARTUP" "$EXE" "$TCP_DISPLAY" "$ANDROID_TMP" \
  | tee "$EVIDENCE/case.txt"

sudo env HOME=/home/xuser USER=xuser DISPLAY="$TCP_DISPLAY" XAUTHORITY=/dev/null \
  TMPDIR="$ANDROID_TMP" XDG_RUNTIME_DIR="$ANDROID_TMP" \
  WINEPREFIX=/home/xuser/.wine WINEDEBUG=warn+all,err+all \
  WINEESYNC=0 WINE_DO_NOT_CREATE_DXGI_DEVICE_MANAGER=1 \
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

  printf '=== %ss ===\n' "$second" >> "$EVIDENCE/processes.txt"
  ps -eo pid,ppid,stat,etime,comm,args \
    | grep -E 'box64|wine|wineserver|explorer|wfm|cmd.exe' \
    | grep -v grep >> "$EVIDENCE/processes.txt" || true

  TREE="$EVIDENCE/xwininfo-${second}.txt"
  xwininfo -display "$TCP_DISPLAY" -root -tree >"$TREE" 2>&1 || true
  grep -q 'shell - Wine Desktop' "$TREE" \
    && desktop_seen=$((desktop_seen + 1)) || true

  if [ "$STARTUP" = wfm ]; then
    ID="$(awk '/"Computer"/ {print $1; exit}' "$TREE")"
  else
    ID="$(awk '/cmd.exe/ {print $1; exit}' "$TREE")"
  fi

  if [ -n "$ID" ]; then
    app_seen=$((app_seen + 1))
    xwininfo -display "$TCP_DISPLAY" -id "$ID" -all \
      >"$EVIDENCE/app-${second}.txt" 2>&1 || true
    xprop -display "$TCP_DISPLAY" -id "$ID" \
      >"$EVIDENCE/app-${second}-xprop.txt" 2>&1 || true
    grep -Fq 'Map State: IsViewable' "$EVIDENCE/app-${second}.txt" \
      && app_viewable=$((app_viewable + 1)) || true
    grep -Fq 'Map State: IsUnMapped' "$EVIDENCE/app-${second}.txt" \
      && app_unmapped=$((app_unmapped + 1)) || true
  fi

  import -display "$TCP_DISPLAY" -window root "$EVIDENCE/root-${second}.png" || true
done

printf 'runtime=%s\nstartup=%s\nalive_checks=%s\ndesktop_checks=%s\napp_checks=%s\nviewable_checks=%s\nunmapped_checks=%s\n' \
  "$RUNTIME_NAME" "$STARTUP" "$alive" "$desktop_seen" "$app_seen" \
  "$app_viewable" "$app_unmapped" | tee "$EVIDENCE/result.txt"

grep -Ei \
  'c0000005|handle_state_change|DestroyNotify|winebus[^[:space:]]*c0000135|service.*126|RpcSs.*fail|segmentation fault|SIGSEGV|wineserver: mkdir|not owned by you' \
  "$EVIDENCE/wine.log" > "$EVIDENCE/focused-wine-markers.txt" || true

kill "$RUNTIME_PID" 2>/dev/null || true
wait "$RUNTIME_PID" || true
wait "$EVENT_PID" || true

test "$alive" -ge 4
test "$desktop_seen" -ge 4
