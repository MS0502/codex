#!/usr/bin/env bash
set -euo pipefail

VARIANT="${1:?usage: run_v18k_noshape_variant.sh VARIANT}"
case "$VARIANT" in
  v18j-baseline|xshape-restored) ;;
  *) echo "unsupported variant: $VARIANT" >&2; exit 2 ;;
esac

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

V18H_ARTIFACT_ID=8436186617
V18J_ARTIFACT_ID=8442434345
V18H_APK_SHA256=d540254e93452b099621b9deee8de94405f27612b232abb5366dc7a3ff56a9d9
V18J_APK_SHA256=4003bcb0c863519720116d93540e161d640800692c0e002f7e8ac42434e5a215
EVIDENCE="evidence-${VARIANT}"
DISPLAY_NUMBER=100
TCP_DISPLAY="127.0.0.1:${DISPLAY_NUMBER}.0"
mkdir -p "$EVIDENCE"

cleanup() {
  sudo pkill -KILL box64 2>/dev/null || true
  sudo pkill -KILL Xorg 2>/dev/null || true
  sudo umount -l rootfs/tmp 2>/dev/null || true
  sudo umount -l rootfs/proc 2>/dev/null || true
  sudo umount -R -l rootfs/sys 2>/dev/null || true
  sudo umount -R -l rootfs/dev 2>/dev/null || true
}
trap cleanup EXIT

get_artifact() {
  local id="$1" archive="$2" directory="$3"
  curl --fail --location --retry 3 \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/artifacts/${id}/zip" \
    -o "$archive"
  mkdir -p "$directory"
  unzip -q "$archive" -d "$directory"
}

get_artifact "$V18J_ARTIFACT_ID" v18j.zip v18j-artifact
JAPK="$(find v18j-artifact -maxdepth 1 -type f -name '*.apk' -print -quit)"
test -n "$JAPK"
printf '%s  %s\n' "$V18J_APK_SHA256" "$JAPK" | sha256sum -c -

if [ "$VARIANT" = xshape-restored ]; then
  get_artifact "$V18H_ARTIFACT_ID" v18h.zip v18h-artifact
  HAPK="$(find v18h-artifact -maxdepth 1 -type f -name '*.apk' -print -quit)"
  test -n "$HAPK"
  printf '%s  %s\n' "$V18H_APK_SHA256" "$HAPK" | sha256sum -c -
fi

mkdir -p j-apk rootfs box64 prefix
unzip -q "$JAPK" \
  assets/rootfs.tzst assets/rootfs_patches.tzst \
  assets/container_pattern.tzst assets/common_dlls.json \
  assets/box64/box64-0.4.0.tzst -d j-apk
tar --use-compress-program=unzstd -xf j-apk/assets/rootfs.tzst -C rootfs
tar --use-compress-program=unzstd -xf j-apk/assets/box64/box64-0.4.0.tzst -C box64
tar --use-compress-program=unzstd -xf j-apk/assets/container_pattern.tzst -C prefix

if [ "$VARIANT" = xshape-restored ]; then
  mkdir -p h-apk h-rootfs
  unzip -q "$HAPK" assets/rootfs.tzst -d h-apk
  tar --use-compress-program=unzstd -xf h-apk/assets/rootfs.tzst -C h-rootfs
  cp -f h-rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \
    rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so
  cp -f h-rootfs/opt/wine/lib/wine/i386-unix/winex11.so \
    rootfs/opt/wine/lib/wine/i386-unix/winex11.so
  printf '%s  %s\n' 15d0fccef857a9a6fb96879fe5e6dd5e742473b27adf2a7188c0b06ec14b1b28 \
    rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so | sha256sum -c -
  printf '%s  %s\n' 541d6113b94e77f24a6d3ae0bb48774e24e420737371ed57c2c9b1c0f3ec0174 \
    rootfs/opt/wine/lib/wine/i386-unix/winex11.so | sha256sum -c -
  nm -D rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \
    | grep -F XShapeCombineRectangles
else
  printf '%s  %s\n' 41f74b52929d5227712f7ea4ef33e2af85b2cd8599271f9153bce74658564f29 \
    rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so | sha256sum -c -
  printf '%s  %s\n' 10983a122bcafe0ad73ea4d275849686c87b95024057f0514e2268e2495a2ee6 \
    rootfs/opt/wine/lib/wine/i386-unix/winex11.so | sha256sum -c -
  test "$(nm -D rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \
    | grep -c XShapeCombineRectangles || true)" -eq 0
fi

# These v18J modules must remain unchanged in both variants.
printf '%s  %s\n' 2a65d3deed782f67daba9d34408376da56c87ea820bad3be4372a9e9aef50770 \
  rootfs/opt/wine/lib/wine/x86_64-unix/nsiproxy.so | sha256sum -c -
printf '%s  %s\n' 4bf627033adcdd63280dea023b49f124861d7e99109ac62971b5c10b8b57aac1 \
  rootfs/opt/wine/lib/wine/i386-unix/nsiproxy.so | sha256sum -c -
printf '%s  %s\n' 16e8f7ba0f00761e818ee41f8e10b4b7c859948383436ddec5d43207a27c6bd1 \
  rootfs/opt/wine/bin/wine | sha256sum -c -
printf '%s  %s\n' 094c046bba4c745105ea7a39cb62e4767162b3c6e2ebd03253fbda4a69265cdb \
  rootfs/opt/wine/bin/wineserver | sha256sum -c -
sha256sum \
  rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \
  rootfs/opt/wine/lib/wine/i386-unix/winex11.so \
  rootfs/opt/wine/lib/wine/x86_64-unix/nsiproxy.so \
  > "$EVIDENCE/runtime-variant-sha256.txt"

python3 tr_winlator_apk/materialize_main_wine_container.py \
  rootfs prefix j-apk/assets/common_dlls.json \
  | tee "$EVIDENCE/container-materialization.txt"
sudo mkdir -p rootfs/home/xuser rootfs/data/data/com.winlator.trcompat/files
sudo cp -a prefix/.wine rootfs/home/xuser/.wine
sudo tar --use-compress-program=unzstd -xf j-apk/assets/rootfs_patches.tzst -C rootfs
sudo install -D -m 0755 box64/usr/local/bin/box64 rootfs/usr/local/bin/box64
sudo chown -R 0:0 rootfs/home/xuser/.wine
sudo ln -sfn / rootfs/data/data/com.winlator.trcompat/files/rootfs
sudo mkdir -p rootfs/etc rootfs/var/lib/dbus rootfs/tmp rootfs/dev rootfs/proc rootfs/sys
printf '%s\n' 0123456789abcdef0123456789abcdef | sudo tee rootfs/etc/machine-id >/dev/null
sudo ln -sfn /etc/machine-id rootfs/var/lib/dbus/machine-id

cat > xopen-display.c <<'EOF'
#include <X11/Xlib.h>
#include <stdio.h>
int main(void) {
    Display *d = XOpenDisplay(NULL);
    if (!d) { fprintf(stderr, "XOpenDisplay failed for %s\n", XDisplayName(NULL)); return 1; }
    printf("XOpenDisplay ok display=%s screens=%d\n", DisplayString(d), ScreenCount(d));
    XCloseDisplay(d);
    return 0;
}
EOF
gcc -O2 xopen-display.c -lX11 -o xopen-display
sudo install -D -m 0755 xopen-display rootfs/usr/local/bin/xopen-display

cat > xorg-noshape.conf <<'EOF'
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
EOF

Xorg -extension '?' > "$EVIDENCE/xorg-extension-list.txt" 2>&1 || true
sudo mount --rbind /dev rootfs/dev
sudo mount --make-rslave rootfs/dev
sudo mount -t proc proc rootfs/proc
sudo mount --rbind /sys rootfs/sys
sudo mount --make-rslave rootfs/sys
sudo mount --bind /tmp rootfs/tmp

sudo Xorg ":${DISPLAY_NUMBER}" -noreset -ac -listen tcp -extension SHAPE \
  -config "$PWD/xorg-noshape.conf" -logfile "$PWD/$EVIDENCE/Xorg.log" \
  > "$EVIDENCE/xserver.log" 2>&1 &
XSERVER_PID=$!
echo "$XSERVER_PID" > "$EVIDENCE/xserver.pid"
for _ in $(seq 1 40); do
  xdpyinfo -display "$TCP_DISPLAY" >/dev/null 2>&1 && break
  sleep 1
done
xdpyinfo -display "$TCP_DISPLAY" > "$EVIDENCE/xdpyinfo.txt"
test "$(grep -c SHAPE "$EVIDENCE/xdpyinfo.txt" || true)" -eq 0
sudo env DISPLAY="$TCP_DISPLAY" XAUTHORITY=/dev/null \
  LD_LIBRARY_PATH=/lib:/usr/lib:/usr/lib/aarch64-linux-gnu \
  /usr/sbin/chroot rootfs /usr/local/bin/xopen-display \
  2>&1 | tee "$EVIDENCE/xopen-display.txt"
grep -F 'XOpenDisplay ok' "$EVIDENCE/xopen-display.txt"

sudo env HOME=/home/xuser USER=xuser DISPLAY="$TCP_DISPLAY" XAUTHORITY=/dev/null \
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
  'C:\windows\winhandler.exe' /dir 'C:\windows' 'wfm.exe' \
  > "$EVIDENCE/wine.log" 2>&1 &
RUNTIME_PID=$!

alive=0
desktop=0
computer=0
viewable=0
pid_changes=0
previous_explorer=''
for second in 10 20 30 40 50 60; do
  sleep 10
  if kill -0 "$RUNTIME_PID" 2>/dev/null; then alive=$((alive + 1)); fi
  xwininfo -display "$TCP_DISPLAY" -root -tree \
    > "$EVIDENCE/xwininfo-${second}.txt" 2>&1 || true
  grep -q 'shell - Wine Desktop' "$EVIDENCE/xwininfo-${second}.txt" \
    && desktop=$((desktop + 1)) || true
  ID="$(awk '/"Computer"/ {print $1; exit}' "$EVIDENCE/xwininfo-${second}.txt")"
  if [ -n "$ID" ]; then
    computer=$((computer + 1))
    xwininfo -display "$TCP_DISPLAY" -id "$ID" -all \
      > "$EVIDENCE/computer-${second}.txt" 2>&1 || true
    grep -Fq 'Map State: IsViewable' "$EVIDENCE/computer-${second}.txt" \
      && viewable=$((viewable + 1)) || true
  fi
  explorer_pids="$(pgrep -f 'explorer.exe|explorer /desktop' | sort -n | tr '\n' ',' || true)"
  printf 't=%s explorer_pids=%s\n' "$second" "$explorer_pids" \
    >> "$EVIDENCE/process-samples.txt"
  if [ -n "$previous_explorer" ] && [ "$explorer_pids" != "$previous_explorer" ]; then
    pid_changes=$((pid_changes + 1))
  fi
  previous_explorer="$explorer_pids"
  import -display "$TCP_DISPLAY" -window root "$EVIDENCE/root-${second}.png" || true
done

printf 'variant=%s\nalive_checks=%s\ndesktop_checks=%s\ncomputer_checks=%s\nviewable_checks=%s\nexplorer_pid_changes=%s\n' \
  "$VARIANT" "$alive" "$desktop" "$computer" "$viewable" "$pid_changes" \
  | tee "$EVIDENCE/result.txt"
grep -Ei 'winebus[^\n]*c0000135|service[^\n]*126|RpcSs[^\n]*fail|Initialization of L"winex11.drv" failed|segmentation fault|SIGSEGV' \
  "$EVIDENCE/wine.log" > "$EVIDENCE/fatal-markers.txt" || true
grep -Ei 'BadRequest|X Error|XShape|shape extension' "$EVIDENCE/wine.log" \
  > "$EVIDENCE/xshape-markers.txt" || true

kill "$RUNTIME_PID" 2>/dev/null || true
wait "$RUNTIME_PID" || true

test "$alive" -ge 5
test "$desktop" -ge 5
test "$computer" -ge 5
test "$pid_changes" -eq 0
test ! -s "$EVIDENCE/fatal-markers.txt"
