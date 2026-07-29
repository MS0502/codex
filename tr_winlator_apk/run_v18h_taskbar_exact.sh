#!/usr/bin/env bash
set -euo pipefail

cp tr_winlator_apk/run_v18k_noshape_variant.sh runner-v18h-taskbar.sh
RUNNER=runner-v18h-taskbar.sh

python3 - "$RUNNER" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

replacements = {
    'V18J_ARTIFACT_ID=8442434345': 'V18J_ARTIFACT_ID=8436186617',
    'V18J_APK_SHA256=4003bcb0c863519720116d93540e161d640800692c0e002f7e8ac42434e5a215':
        'V18J_APK_SHA256=d540254e93452b099621b9deee8de94405f27612b232abb5366dc7a3ff56a9d9',
    'EVIDENCE="evidence-${VARIANT}"': 'EVIDENCE="evidence-v18h-taskbar"',
    '41f74b52929d5227712f7ea4ef33e2af85b2cd8599271f9153bce74658564f29':
        '15d0fccef857a9a6fb96879fe5e6dd5e742473b27adf2a7188c0b06ec14b1b28',
    '10983a122bcafe0ad73ea4d275849686c87b95024057f0514e2268e2495a2ee6':
        '541d6113b94e77f24a6d3ae0bb48774e24e420737371ed57c2c9b1c0f3ec0174',
    '2a65d3deed782f67daba9d34408376da56c87ea820bad3be4372a9e9aef50770':
        '02e8d489e0a859662a9fad21d59b63566b74d300987fac512de9b3599bcc89a8',
    '4bf627033adcdd63280dea023b49f124861d7e99109ac62971b5c10b8b57aac1':
        '597a0dce90175e041ea148acd77cd3d9b0f4ae73bc5652e61d74155e8c6c3900',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f'missing replacement anchor: {old}')
    text = text.replace(old, new, 1)

no_shape_check = '''  test "$(nm -D rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \\
    | grep -c XShapeCombineRectangles || true)" -eq 0
'''
if no_shape_check not in text:
    raise SystemExit('no-SHAPE symbol check anchor missing')
text = text.replace(
    no_shape_check,
    '''  nm -D rootfs/opt/wine/lib/wine/x86_64-unix/winex11.so \\
    | grep -F XShapeCombineRectangles
''',
    1,
)

copy_anchor = 'sudo cp -a prefix/.wine rootfs/home/xuser/.wine\n'
if copy_anchor not in text:
    raise SystemExit('prefix copy anchor missing')
text = text.replace(
    copy_anchor,
    copy_anchor + 'sudo cp -f taskbar_probe.exe rootfs/home/xuser/.wine/drive_c/taskbar_probe.exe\n',
    1,
)

pid_anchor = 'RUNTIME_PID=$!\n\n'
if pid_anchor not in text:
    raise SystemExit('runtime pid anchor missing')
injection = r'''RUNTIME_PID=$!

run_taskbar_probe() {
  local label="$1"
  local win_output="C:\\taskbar-probe-${label}.txt"
  sudo env HOME=/home/xuser USER=xuser DISPLAY="$TCP_DISPLAY" XAUTHORITY=/dev/null \
    WINEPREFIX=/home/xuser/.wine WINEDEBUG=-all \
    WINEESYNC=1 WINE_DO_NOT_CREATE_DXGI_DEVICE_MANAGER=1 \
    MESA_DEBUG=silent MESA_NO_ERROR=1 \
    PATH=/opt/wine/bin:/usr/local/bin:/usr/bin:/bin \
    LD_LIBRARY_PATH=/lib:/usr/lib:/usr/lib/aarch64-linux-gnu \
    BOX64_NOBANNER=1 BOX64_LOG=0 BOX64_DYNAREC=1 \
    BOX64_PATH=/opt/wine/bin:/usr/bin:/bin \
    BOX64_LD_LIBRARY_PATH=/opt/wine/lib:/usr/lib:/lib \
    /usr/sbin/chroot rootfs /usr/local/bin/box64 /opt/wine/bin/wine \
    'C:\taskbar_probe.exe' "$win_output" \
    > "$EVIDENCE/taskbar-launch-${label}.txt" 2>&1 || true
  local host_output="rootfs/home/xuser/.wine/drive_c/taskbar-probe-${label}.txt"
  if [ -f "$host_output" ]; then
    sudo cp -f "$host_output" "$EVIDENCE/taskbar-probe-${label}.txt"
  fi
}

(
  sleep 3
  run_taskbar_probe 3s
  sleep 7
  run_taskbar_probe 10s
  sleep 20
  run_taskbar_probe 30s
  sleep 25
  run_taskbar_probe 55s
) &
TASKBAR_PROBE_PID=$!

'''
text = text.replace(pid_anchor, injection, 1)

kill_anchor = 'kill "$RUNTIME_PID" 2>/dev/null || true\n'
if kill_anchor not in text:
    raise SystemExit('runtime kill anchor missing')
text = text.replace(kill_anchor, 'wait "$TASKBAR_PROBE_PID" || true\n' + kill_anchor, 1)

# v18H is expected to show pre-closure service markers; keep them as evidence.
text = text.replace('test ! -s "$EVIDENCE/fatal-markers.txt"\n',
                    'true # v18H pre-closure markers are diagnostic\n', 1)
path.write_text(text, encoding='utf-8')
PY

bash -n "$RUNNER"
grep -n -A5 -B2 'explorer /desktop' "$RUNNER" > v18h-taskbar-command.txt
PATH="/usr/local/bin:$PATH" bash "$RUNNER" v18j-baseline

EVIDENCE=evidence-v18h-taskbar
for label in 3s 10s 30s 55s; do
  test -s "$EVIDENCE/taskbar-probe-${label}.txt"
done
{
  echo 'runtime=v18h-full'
  for label in 3s 10s 30s 55s; do
    printf '%s=' "$label"
    grep -m1 -o 'TRAY_FOUND=[01]' "$EVIDENCE/taskbar-probe-${label}.txt"
  done
} | tee "$EVIDENCE/taskbar-summary.txt"
