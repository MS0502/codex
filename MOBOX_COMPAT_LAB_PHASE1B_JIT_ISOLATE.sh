#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
STAMP="$(date +%Y%m%d_%H%M%S)"
NAME="MOBOX_COMPAT_LAB_PHASE1B_${STAMP}"
OUTDIR="${DOWNLOADS}/TR_KR_LOCAL/${NAME}"
LATEST_SUMMARY="${DOWNLOADS}/MOBOX_COMPAT_LAB_PHASE1B_SUMMARY.txt"
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
SRC=/tmp/mobox_phase1b_jit_probe.c
X64=/tmp/mobox_phase1b_jit_probe_x64
RESULTS="$OUTDIR/results.tsv"

mkdir -p "$OUTDIR"

for cmd in x86_64-linux-gnu-gcc python3 timeout file; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: missing required command: $cmd" >&2
        exit 10
    }
done

[ -x "$BOX" ] || {
    echo "ERROR: Box64 not found: $BOX" >&2
    exit 11
}

cat >"$SRC" <<'C'
#define _GNU_SOURCE
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static void print_map(void *addr)
{
    FILE *fp = fopen("/proc/self/maps", "r");
    char line[512];
    uintptr_t target = (uintptr_t)addr;
    unsigned long long start, end;

    if (!fp) {
        printf("STEP map_lookup_failed errno=%d\n", errno);
        fflush(stdout);
        return;
    }

    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "%llx-%llx", &start, &end) == 2 &&
            target >= start && target < end) {
            line[strcspn(line, "\n")] = '\0';
            printf("STEP map=%s\n", line);
            fflush(stdout);
            fclose(fp);
            return;
        }
    }

    printf("STEP map_not_found\n");
    fflush(stdout);
    fclose(fp);
}

static void emit_return_value(void *page, uint32_t value)
{
    unsigned char code[6];
    code[0] = 0xB8; /* mov eax, imm32 */
    memcpy(code + 1, &value, sizeof(value));
    code[5] = 0xC3; /* ret */
    memcpy(page, code, sizeof(code));
    __builtin___clear_cache((char *)page, (char *)page + 64);
}

int main(int argc, char **argv)
{
    const size_t page_size = 4096;
    int fixed = 0;
    int final_prot = PROT_READ | PROT_EXEC;
    int cycle = 0;
    int flags = MAP_PRIVATE | MAP_ANONYMOUS;
    void *wanted = NULL;
    void *page;
    int rc;
    typedef int (*fn_t)(void);
    fn_t fn;

    if (argc != 2) {
        fprintf(stderr, "usage: %s CASE\n", argv[0]);
        return 64;
    }

    if (strstr(argv[1], "fixed")) fixed = 1;
    if (strstr(argv[1], "rwx")) final_prot = PROT_READ | PROT_WRITE | PROT_EXEC;
    if (strstr(argv[1], "cycle")) cycle = 1;

    if (fixed) {
        wanted = (void *)(uintptr_t)0x60000000u;
#ifdef MAP_FIXED_NOREPLACE
        flags |= MAP_FIXED_NOREPLACE;
#else
        flags |= MAP_FIXED;
#endif
    }

    errno = 0;
    page = mmap(wanted, page_size, PROT_READ | PROT_WRITE,
                flags, -1, 0);
    printf("STEP mmap case=%s wanted=%p page=%p errno=%d\n",
           argv[1], wanted, page, page == MAP_FAILED ? errno : 0);
    fflush(stdout);

    if (page == MAP_FAILED) return 20;

    emit_return_value(page, 42);
    printf("STEP emitted value=42\n");
    fflush(stdout);

    errno = 0;
    rc = mprotect(page, page_size, final_prot);
    printf("STEP protect1 rc=%d errno=%d prot=0x%x\n",
           rc, rc ? errno : 0, final_prot);
    fflush(stdout);
    print_map(page);
    if (rc) return 21;

    fn = (fn_t)page;
    printf("STEP call1_begin fn=%p\n", page);
    fflush(stdout);
    rc = fn();
    printf("STEP call1_end value=%d\n", rc);
    fflush(stdout);
    if (rc != 42) return 22;

    if (cycle) {
        errno = 0;
        rc = mprotect(page, page_size, PROT_READ | PROT_WRITE);
        printf("STEP cycle_to_rw rc=%d errno=%d\n", rc, rc ? errno : 0);
        fflush(stdout);
        if (rc) return 23;

        emit_return_value(page, 43);
        printf("STEP emitted value=43\n");
        fflush(stdout);

        errno = 0;
        rc = mprotect(page, page_size, PROT_READ | PROT_EXEC);
        printf("STEP cycle_to_rx rc=%d errno=%d\n", rc, rc ? errno : 0);
        fflush(stdout);
        print_map(page);
        if (rc) return 24;

        printf("STEP call2_begin fn=%p\n", page);
        fflush(stdout);
        rc = fn();
        printf("STEP call2_end value=%d\n", rc);
        fflush(stdout);
        if (rc != 43) return 25;
    }

    munmap(page, page_size);
    printf("RESULT PASS\n");
    fflush(stdout);
    return 0;
}
C

x86_64-linux-gnu-gcc -O0 -g3 -Wall -Wextra -std=c11 "$SRC" -o "$X64"
cp -f "$SRC" "$OUTDIR/mobox_phase1b_jit_probe.c"
file "$X64" "$BOX" >"$OUTDIR/binaries.txt"
"$BOX" --version >>"$OUTDIR/binaries.txt" 2>&1 || true
uname -a >"$OUTDIR/system.txt"

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_LD_LIBRARY_PATH="/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/mobox/lib/x86_64-linux-gnu"

printf 'mode\tcase\texit_code\tlast_step\n' >"$RESULTS"

run_case() {
    mode="$1"
    dyn="$2"
    case_name="$3"
    prefix="${mode}_${case_name}"
    stdout_file="$OUTDIR/${prefix}.stdout.txt"
    stderr_file="$OUTDIR/${prefix}.stderr.txt"

    echo "=== RUN mode=$mode case=$case_name ==="
    set +e
    timeout 30s env \
      BOX64_DYNAREC="$dyn" \
      BOX64_LOG=1 \
      BOX64_DYNAREC_LOG=1 \
      "$BOX" "$X64" "$case_name" \
      >"$stdout_file" 2>"$stderr_file"
    rc=$?
    set -e

    last_step="$(grep -E '^(STEP|RESULT)' "$stdout_file" | tail -1 | tr '\t' ' ' || true)"
    printf '%s\t%s\t%s\t%s\n' "$mode" "$case_name" "$rc" "$last_step" >>"$RESULTS"
    printf '%s\n' "$rc" >"$OUTDIR/${prefix}.exitcode"
    echo "=== EXIT mode=$mode case=$case_name rc=$rc last=$last_step ==="
}

cases=(
  rx_auto
  rwx_auto
  rx_fixed
  rwx_fixed
  cycle_auto
  cycle_fixed
)

for case_name in "${cases[@]}"; do
    run_case dynarec 1 "$case_name"
done

for case_name in "${cases[@]}"; do
    run_case interp 0 "$case_name"
done

# Optional syscall trace of the smallest failing path.
if command -v strace >/dev/null 2>&1; then
    set +e
    timeout 30s strace -f \
      -e trace=mmap,mprotect,munmap,rt_sigaction,rt_sigreturn \
      -o "$OUTDIR/dynarec_rx_auto.strace.txt" \
      env BOX64_DYNAREC=1 BOX64_LOG=0 BOX64_DYNAREC_LOG=0 \
      "$BOX" "$X64" rx_auto \
      >"$OUTDIR/dynarec_rx_auto_strace.stdout.txt" \
      2>"$OUTDIR/dynarec_rx_auto_strace.stderr.txt"
    echo "$?" >"$OUTDIR/dynarec_rx_auto_strace.exitcode"
    set -e
fi

# Optional host-side backtrace. This may be blocked by ptrace policy under PRoot.
if command -v gdb >/dev/null 2>&1; then
    set +e
    timeout 60s env \
      BOX64_DYNAREC=1 \
      BOX64_LOG=1 \
      BOX64_DYNAREC_LOG=1 \
      gdb -q -batch \
        -ex 'set pagination off' \
        -ex run \
        -ex 'thread apply all bt' \
        --args "$BOX" "$X64" rx_auto \
      >"$OUTDIR/dynarec_rx_auto.gdb.txt" 2>&1
    echo "$?" >"$OUTDIR/dynarec_rx_auto_gdb.exitcode"
    set -e
fi

python3 - "$OUTDIR" <<'PY'
from pathlib import Path
import csv
import sys

outdir = Path(sys.argv[1])
with (outdir / 'results.tsv').open(newline='', errors='replace') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))

failures = [r for r in rows if r['exit_code'] != '0']
lines = [
    'MOBOX COMPAT LAB PHASE 1B - JIT ISOLATION',
    '==========================================',
    f"total runs: {len(rows)}",
    f"passed: {len(rows) - len(failures)}",
    f"failed: {len(failures)}",
    '',
    'Results:',
]
for row in rows:
    lines.append(
        f"{row['mode']} {row['case']}: exit={row['exit_code']} | {row['last_step']}"
    )

lines.extend(['', 'Failure interpretation:'])
if not failures:
    lines.append('No isolated JIT failure reproduced.')
else:
    for row in failures:
        lines.append(
            f"FAIL {row['mode']} {row['case']} exit={row['exit_code']} last={row['last_step']}"
        )

(outdir / 'SUMMARY.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
PY
DEBIAN

cp -f "$OUTDIR/SUMMARY.txt" "$LATEST_SUMMARY"
tar -C "$(dirname "$OUTDIR")" -czf "$LATEST_ARCHIVE" "$(basename "$OUTDIR")"
termux-media-scan "$LATEST_SUMMARY" "$LATEST_ARCHIVE" >/dev/null 2>&1 || true

echo
echo "PHASE1B_SUMMARY=$LATEST_SUMMARY"
echo "PHASE1B_ARCHIVE=$LATEST_ARCHIVE"
