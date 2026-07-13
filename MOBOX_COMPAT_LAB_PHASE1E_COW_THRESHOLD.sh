#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
STAMP="$(date +%Y%m%d_%H%M%S)"
NAME="MOBOX_COMPAT_LAB_PHASE1E_${STAMP}"
OUTDIR="${DOWNLOADS}/TR_KR_LOCAL/${NAME}"
LATEST_SUMMARY="${DOWNLOADS}/MOBOX_COMPAT_LAB_PHASE1E_SUMMARY.txt"
LATEST_ARCHIVE="${DOWNLOADS}/${NAME}.tar.gz"

mkdir -p "$OUTDIR"

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  --env LAB_OUTDIR="/mnt/downloads/TR_KR_LOCAL/${NAME}" \
  -- bash -s <<'DEBIAN'
set -euo pipefail

OUTDIR="${LAB_OUTDIR:?}"
BOX=/root/box64/build/box64
NTDLL=/opt/mobox/wine-9.3-vanilla-wow64/lib/wine/x86_64-windows/ntdll.dll
SRC=/tmp/mobox_phase1e_cow_threshold.c
X64=/tmp/mobox_phase1e_cow_threshold_x64
RESULTS="$OUTDIR/results.tsv"

mkdir -p "$OUTDIR"

for cmd in x86_64-linux-gnu-gcc python3 timeout file sha256sum; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: missing required command: $cmd" >&2
        exit 10
    }
done

[ -x "$BOX" ] || { echo "ERROR: Box64 not found: $BOX" >&2; exit 11; }
[ -f "$NTDLL" ] || { echo "ERROR: ntdll.dll not found: $NTDLL" >&2; exit 12; }

cat >"$SRC" <<'C'
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define PAGE_SIZE_ 4096u
#define BASE_ADDR ((uintptr_t)0x60000000u)
#define ADDR_STEP ((uintptr_t)0x00020000u)

static int make_temp_file(char path[64])
{
    strcpy(path, "/tmp/mobox_phase1e_file_XXXXXX");
    int fd = mkstemp(path);
    if (fd < 0) return -1;
    unsigned char page[PAGE_SIZE_];
    memset(page, 0x90, sizeof(page));
    if (write(fd, page, sizeof(page)) != (ssize_t)sizeof(page)) {
        close(fd);
        unlink(path);
        return -1;
    }
    close(fd);
    return 0;
}

static void *wanted_address(const char *addr_mode, int iteration)
{
    if (!strcmp(addr_mode, "auto")) return NULL;
    if (!strcmp(addr_mode, "same")) return (void *)BASE_ADDR;
    if (!strcmp(addr_mode, "unique"))
        return (void *)(BASE_ADDR + (uintptr_t)iteration * ADDR_STEP);
    return (void *)(uintptr_t)-1;
}

static int final_protection(const char *pattern, int iteration, int count)
{
    if (!strcmp(pattern, "rx")) return PROT_READ | PROT_EXEC;
    if (!strcmp(pattern, "rwx")) return PROT_READ | PROT_WRITE | PROT_EXEC;
    if (!strcmp(pattern, "mixed")) {
        int rwx_count = count >= 8 ? 8 : count / 3;
        return iteration >= count - rwx_count
            ? (PROT_READ | PROT_WRITE | PROT_EXEC)
            : (PROT_READ | PROT_EXEC);
    }
    return -1;
}

int main(int argc, char **argv)
{
    if (argc != 7) {
        fprintf(stderr,
                "usage: %s FILE SOURCE_MODE ADDR_MODE COUNT PATTERN LABEL\n",
                argv[0]);
        return 64;
    }

    const char *input_path = argv[1];
    const char *source_mode = argv[2];
    const char *addr_mode = argv[3];
    int count = atoi(argv[4]);
    const char *pattern = argv[5];
    const char *label = argv[6];
    char temp_path[64] = {0};
    const char *path = input_path;

    if (!strcmp(source_mode, "baseline")) {
        printf("RESULT PASS label=%s count=0\n", label);
        fflush(stdout);
        return 0;
    }

    int use_temp = strstr(source_mode, "temp") != NULL;
    int dirty = strstr(source_mode, "dirty") != NULL;

    if (use_temp) {
        if (make_temp_file(temp_path)) {
            fprintf(stderr, "temp file creation failed errno=%d\n", errno);
            return 65;
        }
        path = temp_path;
    }

    if (count <= 0 || count > 128) return 66;
    if (wanted_address(addr_mode, 0) == (void *)(uintptr_t)-1) return 67;
    if (final_protection(pattern, 0, count) < 0) return 68;

    printf("STEP start label=%s source=%s addr=%s count=%d pattern=%s dirty=%d\n",
           label, source_mode, addr_mode, count, pattern, dirty);
    fflush(stdout);

    for (int i = 0; i < count; ++i) {
        int fd = open(path, O_RDONLY);
        if (fd < 0) {
            printf("RESULT FAIL stage=open iter=%d errno=%d\n", i, errno);
            fflush(stdout);
            if (temp_path[0]) unlink(temp_path);
            return 20;
        }

        void *wanted = wanted_address(addr_mode, i);
        int flags = MAP_PRIVATE;
        if (wanted) flags |= MAP_FIXED;

        errno = 0;
        void *page = mmap(wanted, PAGE_SIZE_, PROT_READ | PROT_WRITE,
                          flags, fd, 0);
        int map_errno = page == MAP_FAILED ? errno : 0;
        close(fd);

        if (page == MAP_FAILED) {
            printf("RESULT FAIL stage=mmap iter=%d errno=%d wanted=%p\n",
                   i, map_errno, wanted);
            fflush(stdout);
            if (temp_path[0]) unlink(temp_path);
            return 21;
        }

        if (dirty) {
            volatile unsigned char *p = (volatile unsigned char *)page;
            unsigned char old = p[0];
            p[0] = (unsigned char)(old ^ 1u);
            p[0] = old;
        }

        int prot = final_protection(pattern, i, count);
        errno = 0;
        int rc = mprotect(page, PAGE_SIZE_, prot);
        int protect_errno = rc ? errno : 0;
        if (rc) {
            printf("RESULT FAIL stage=mprotect iter=%d errno=%d prot=0x%x\n",
                   i, protect_errno, prot);
            fflush(stdout);
            munmap(page, PAGE_SIZE_);
            if (temp_path[0]) unlink(temp_path);
            return 22;
        }

        errno = 0;
        rc = munmap(page, PAGE_SIZE_);
        if (rc) {
            printf("RESULT FAIL stage=munmap iter=%d errno=%d\n", i, errno);
            fflush(stdout);
            if (temp_path[0]) unlink(temp_path);
            return 23;
        }

        if (i == 0 || i + 1 == count || ((i + 1) % 8) == 0) {
            printf("STEP progress label=%s completed=%d prot=0x%x\n",
                   label, i + 1, prot);
            fflush(stdout);
        }
    }

    if (temp_path[0]) unlink(temp_path);
    printf("RESULT PASS label=%s count=%d\n", label, count);
    fflush(stdout);
    return 0;
}
C

x86_64-linux-gnu-gcc -O0 -g3 -Wall -Wextra -std=c11 "$SRC" -o "$X64"
cp -f "$SRC" "$OUTDIR/mobox_phase1e_cow_threshold.c"
file "$X64" "$BOX" >"$OUTDIR/binaries.txt"
"$BOX" --version >>"$OUTDIR/binaries.txt" 2>&1 || true
uname -a >"$OUTDIR/system.txt"
sha256sum "$NTDLL" >"$OUTDIR/ntdll_before.sha256"

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_LD_LIBRARY_PATH="/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/mobox/lib/x86_64-linux-gnu"

printf 'mode\tscenario\trepetition\texit_code\tpass\tfallbacks\twarnings\tquit_fault\tlast_step\n' >"$RESULTS"

run_case() {
    mode="$1"
    dyn="$2"
    scenario="$3"
    rep="$4"
    source_mode="$5"
    addr_mode="$6"
    count="$7"
    pattern="$8"

    prefix="${mode}_${scenario}_r${rep}"
    stdout_file="$OUTDIR/${prefix}.stdout.txt"
    stderr_file="$OUTDIR/${prefix}.stderr.full.txt"
    key_file="$OUTDIR/${prefix}.stderr.key.txt"

    echo "=== RUN mode=$mode scenario=$scenario rep=$rep ==="
    set +e
    timeout 45s env \
      BOX64_DYNAREC="$dyn" \
      BOX64_LOG=1 \
      BOX64_DYNAREC_LOG=0 \
      "$BOX" "$X64" "$NTDLL" "$source_mode" "$addr_mode" \
      "$count" "$pattern" "$scenario" \
      >"$stdout_file" 2>"$stderr_file"
    rc=$?
    set -e

    pass=0
    grep -q '^RESULT PASS' "$stdout_file" && pass=1 || true
    fallbacks="$(grep -c 'BOX64_EXECMOD_COW_V4.*success' "$stderr_file" 2>/dev/null || true)"
    warnings="$(grep -c 'cannot add DynaCache Block' "$stderr_file" 2>/dev/null || true)"
    quit_fault="$(grep -c 'Sigfault/Segbus while quitting' "$stderr_file" 2>/dev/null || true)"
    last_step="$(grep -E '^(STEP|RESULT)' "$stdout_file" | tail -1 | tr '\t' ' ' || true)"

    {
        grep -E 'BOX64_EXECMOD_COW_V4|Loaded DynaCache|Delete Mapping|Sigfault/Segbus while quitting|DynaCache will not serialize|Free DynaBlocks|Unmap elf memory' "$stderr_file" | head -80 || true
        echo "COUNTS fallbacks=$fallbacks warnings=$warnings quit_fault=$quit_fault exit=$rc pass=$pass"
    } >"$key_file"

    problem=0
    if [ "$rc" -ne 0 ] || [ "$pass" -ne 1 ] || [ "$quit_fault" -ne 0 ]; then
        problem=1
    fi

    if [ "$problem" -eq 0 ]; then
        rm -f "$stderr_file"
    else
        mv -f "$stderr_file" "$OUTDIR/${prefix}.failure.stderr.txt"
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$mode" "$scenario" "$rep" "$rc" "$pass" "$fallbacks" \
      "$warnings" "$quit_fault" "$last_step" >>"$RESULTS"

    echo "=== EXIT mode=$mode scenario=$scenario rc=$rc pass=$pass fallbacks=$fallbacks warnings=$warnings quit_fault=$quit_fault ==="
}

scenarios=(
  'baseline|baseline|same|0|rx'
  'ntdll_same_rx_n1|ntdll_dirty|same|1|rx'
  'ntdll_same_rx_n2|ntdll_dirty|same|2|rx'
  'ntdll_same_rx_n4|ntdll_dirty|same|4|rx'
  'ntdll_same_rx_n8|ntdll_dirty|same|8|rx'
  'ntdll_same_rx_n12|ntdll_dirty|same|12|rx'
  'ntdll_same_rx_n16|ntdll_dirty|same|16|rx'
  'ntdll_same_rx_n20|ntdll_dirty|same|20|rx'
  'ntdll_same_rx_n24|ntdll_dirty|same|24|rx'
  'ntdll_same_rx_n28|ntdll_dirty|same|28|rx'
  'ntdll_same_rx_n32|ntdll_dirty|same|32|rx'
  'ntdll_unique_rx_n4|ntdll_dirty|unique|4|rx'
  'ntdll_unique_rx_n8|ntdll_dirty|unique|8|rx'
  'ntdll_unique_rx_n12|ntdll_dirty|unique|12|rx'
  'ntdll_unique_rx_n16|ntdll_dirty|unique|16|rx'
  'ntdll_unique_rx_n20|ntdll_dirty|unique|20|rx'
  'ntdll_unique_rx_n24|ntdll_dirty|unique|24|rx'
  'ntdll_unique_rx_n28|ntdll_dirty|unique|28|rx'
  'ntdll_auto_rx_n28|ntdll_dirty|auto|28|rx'
  'ntdll_same_mixed_n28|ntdll_dirty|same|28|mixed'
  'ntdll_unique_mixed_n28|ntdll_dirty|unique|28|mixed'
  'ntdll_same_rwx_n28|ntdll_dirty|same|28|rwx'
  'ntdll_clean_same_rx_n28|ntdll_clean|same|28|rx'
  'temp_dirty_same_rx_n28|temp_dirty|same|28|rx'
)

for entry in "${scenarios[@]}"; do
    IFS='|' read -r scenario source_mode addr_mode count pattern <<<"$entry"
    run_case dynarec 1 "$scenario" 1 "$source_mode" "$addr_mode" "$count" "$pattern"
    run_case dynarec 1 "$scenario" 2 "$source_mode" "$addr_mode" "$count" "$pattern"
done

for entry in "${scenarios[@]}"; do
    IFS='|' read -r scenario source_mode addr_mode count pattern <<<"$entry"
    run_case interp 0 "$scenario" 1 "$source_mode" "$addr_mode" "$count" "$pattern"
done

sha256sum "$NTDLL" >"$OUTDIR/ntdll_after.sha256"

python3 - "$OUTDIR" <<'PY'
from pathlib import Path
import csv
import json
import sys

outdir = Path(sys.argv[1])
with (outdir / 'results.tsv').open(newline='', errors='replace') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))

for row in rows:
    for field in ['repetition', 'exit_code', 'pass', 'fallbacks', 'warnings', 'quit_fault']:
        row[field] = int(row[field])

problems = [r for r in rows if r['exit_code'] != 0 or r['pass'] != 1 or r['quit_fault'] != 0]
dyn = [r for r in rows if r['mode'] == 'dynarec']
interp = [r for r in rows if r['mode'] == 'interp']

# Earliest same-address RX count that shows a hidden quit fault.
threshold_rows = []
for r in dyn:
    if r['scenario'].startswith('ntdll_same_rx_n'):
        try:
            count = int(r['scenario'].rsplit('n', 1)[1])
        except ValueError:
            continue
        if r['quit_fault'] or r['exit_code'] != 0:
            threshold_rows.append(count)
threshold = min(threshold_rows) if threshold_rows else None

before = (outdir / 'ntdll_before.sha256').read_text().split()[0]
after = (outdir / 'ntdll_after.sha256').read_text().split()[0]

summary = {
    'phase': '1E',
    'total_runs': len(rows),
    'dynarec_runs': len(dyn),
    'interp_runs': len(interp),
    'problem_runs': len(problems),
    'same_rx_first_problem_count': threshold,
    'ntdll_hash_unchanged': before == after,
}
(outdir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
(outdir / 'problems.json').write_text(json.dumps(problems, indent=2) + '\n')

lines = [
    'MOBOX COMPAT LAB PHASE 1E - COW THRESHOLD',
    '==========================================',
    f"total runs: {len(rows)}",
    f"dynarec runs: {len(dyn)}",
    f"interp runs: {len(interp)}",
    f"problem runs: {len(problems)}",
    f"same-address RX first problem count: {threshold}",
    f"ntdll hash unchanged: {before == after}",
    '',
    'Dynarec results:',
]
for r in dyn:
    lines.append(
        f"{r['scenario']} r{r['repetition']}: exit={r['exit_code']} "
        f"pass={r['pass']} fallback={r['fallbacks']} warnings={r['warnings']} "
        f"quit_fault={r['quit_fault']} | {r['last_step']}"
    )

lines.extend(['', 'Problem runs:'])
if problems:
    for r in problems:
        lines.append(json.dumps(r, ensure_ascii=False))
else:
    lines.append('none')

(outdir / 'SUMMARY.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines[:10]))
PY

DEBIAN

cp -f "$OUTDIR/SUMMARY.txt" "$LATEST_SUMMARY"
tar -C "$(dirname "$OUTDIR")" -czf "$LATEST_ARCHIVE" "$(basename "$OUTDIR")"
termux-media-scan "$LATEST_SUMMARY" "$LATEST_ARCHIVE" >/dev/null 2>&1 || true

echo
echo "PHASE1E_SUMMARY=$LATEST_SUMMARY"
echo "PHASE1E_ARCHIVE=$LATEST_ARCHIVE"
