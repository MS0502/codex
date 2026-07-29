#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?usage: run_v18j_taskbar_mode.sh MODE}"
case "$MODE" in
  exact|desktop-only|winhandler-cmd|wfm-direct) ;;
  *) echo "unsupported mode: $MODE" >&2; exit 2 ;;
esac

cp tr_winlator_apk/run_v18k_noshape_variant.sh "runner-${MODE}.sh"
RUNNER="runner-${MODE}.sh"
export TASKBAR_MODE="$MODE"

python3 - "$RUNNER" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
mode = os.environ['TASKBAR_MODE']
text = path.read_text(encoding='utf-8')
text = text.replace('EVIDENCE="evidence-${VARIANT}"', f'EVIDENCE="evidence-taskbar-{mode}"', 1)

exact = "  'C:\\windows\\winhandler.exe' /dir 'C:\\windows' 'wfm.exe' \\\n"
if exact not in text:
    raise SystemExit('exact startup anchor missing')
if mode == 'desktop-only':
    text = text.replace(exact, '', 1)
elif mode == 'winhandler-cmd':
    text = text.replace(exact, "  'C:\\windows\\winhandler.exe' /dir 'C:\\windows' 'cmd.exe' \\\n", 1)
elif mode == 'wfm-direct':
    text = text.replace(exact, "  'C:\\windows\\wfm.exe' \\\n", 1)
elif mode != 'exact':
    raise SystemExit(mode)

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

# Modes that intentionally omit wfm.exe may not create a Computer window.
text = text.replace('test "$computer" -ge 5\n', 'true # taskbar mode records Computer count\n', 1)
path.write_text(text, encoding='utf-8')
PY

bash -n "$RUNNER"
grep -n -A5 -B2 'explorer /desktop' "$RUNNER" > "taskbar-${MODE}-command.txt"
PATH="/usr/local/bin:$PATH" bash "$RUNNER" v18j-baseline

EVIDENCE="evidence-taskbar-${MODE}"
printf 'mode=%s\n' "$MODE" >> "$EVIDENCE/taskbar-summary.txt"
for label in 3s 10s 30s 55s; do
  file="$EVIDENCE/taskbar-probe-${label}.txt"
  printf '%s=' "$label" >> "$EVIDENCE/taskbar-summary.txt"
  if [ -s "$file" ]; then
    grep -m1 -o 'TRAY_FOUND=[01]' "$file" >> "$EVIDENCE/taskbar-summary.txt" || echo 'probe-output-invalid' >> "$EVIDENCE/taskbar-summary.txt"
  else
    echo 'probe-file-missing' >> "$EVIDENCE/taskbar-summary.txt"
  fi
done
cat "$EVIDENCE/taskbar-summary.txt"
