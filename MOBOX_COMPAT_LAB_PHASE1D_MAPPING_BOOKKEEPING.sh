#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
STAMP="$(date +%Y%m%d_%H%M%S)"
NAME="MOBOX_COMPAT_LAB_PHASE1D_${STAMP}"
OUTDIR="${DOWNLOADS}/TR_KR_LOCAL/${NAME}"
LATEST_SUMMARY="${DOWNLOADS}/MOBOX_COMPAT_LAB_PHASE1D_SUMMARY.txt"
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
SRC=/tmp/mobox_phase1d_mapping_probe.c
X64=/tmp/mobox_phase1d_mapping_probe_x64
RESULTS="$OUTDIR/results.tsv"

for cmd in x86_64-linux-gnu-gcc python3 timeout file grep awk; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: missing required command: $cmd" >&2
        exit 10
    }
done
[ -x "$BOX" ] || { echo "ERROR: Box64 missing: $BOX" >&2; exit 11; }
[ -f "$NTDLL" ] || { echo "ERROR: ntdll missing: $NTDLL" >&2; exit 12; }

cat >"$SRC" <<'C'
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#define FILE_ADDR ((void *)(uintptr_t)0x60000000u)
#define OTHER_ADDR ((void *)(uintptr_t)0x61000000u)
#define PAGE 4096u

static void print_map(const char *tag, void *addr)
{
    FILE *fp = fopen("/proc/self/maps", "r");
    char line[512];
    unsigned long long start, end;
    uintptr_t target = (uintptr_t)addr;
    if (!fp) {
        printf("STEP %s map_open_failed errno=%d\n", tag, errno);
        fflush(stdout);
        return;
    }
    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "%llx-%llx", &start, &end) == 2 &&
            target >= start && target < end) {
            line[strcspn(line, "\n")] = '\0';
            printf("STEP %s map=%s\n", tag, line);
            fflush(stdout);
            fclose(fp);
            return;
        }
    }
    fclose(fp);
    printf("STEP %s map_not_found\n", tag);
    fflush(stdout);
}

static int make_temp_file(char path[64])
{
    strcpy(path, "/tmp/mobox_phase1d_file_XXXXXX");
    int fd = mkstemp(path);
    if (fd < 0) return -1;
    unsigned char buf[PAGE];
    memset(buf, 0x90, sizeof(buf));
    if (write(fd, buf, sizeof(buf)) != (ssize_t)sizeof(buf)) {
        close(fd);
        unlink(path);
        return -1;
    }
    close(fd);
    return 0;
}

static int map_file_cycle(const char *path, int dirty, int exec_mode, int repeats)
{
    for (int n = 0; n < repeats; ++n) {
        int fd = open(path, O_RDONLY);
        if (fd < 0) {
            printf("STEP file_open_failed iter=%d errno=%d\n", n, errno);
            fflush(stdout);
            return 20;
        }

        errno = 0;
        void *p = mmap(FILE_ADDR, PAGE, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_FIXED, fd, 0);
        printf("STEP file_mmap iter=%d page=%p errno=%d\n",
               n, p, p == MAP_FAILED ? errno : 0);
        fflush(stdout);
        close(fd);
        if (p == MAP_FAILED) return 21;

        print_map("file_before", p);

        if (dirty) {
            volatile unsigned char *b = (volatile unsigned char *)p;
            unsigned char old = b[0];
            b[0] = (unsigned char)(old ^ 1u);
            b[0] = old;
            printf("STEP file_dirty iter=%d\n", n);
            fflush(stdout);
        }

        int prot = PROT_READ;
        if (exec_mode == 1) prot = PROT_READ | PROT_EXEC;
        if (exec_mode == 2) prot = PROT_READ | PROT_WRITE | PROT_EXEC;

        errno = 0;
        int rc = mprotect(p, PAGE, prot);
        printf("STEP file_protect iter=%d rc=%d errno=%d prot=0x%x\n",
               n, rc, rc ? errno : 0, prot);
        fflush(stdout);
        print_map("file_after", p);
        if (rc) {
            munmap(p, PAGE);
            return 22;
        }

        errno = 0;
        rc = munmap(p, PAGE);
        printf("STEP file_unmap iter=%d rc=%d errno=%d\n",
               n, rc, rc ? errno : 0);
        fflush(stdout);
        if (rc) return 23;
    }
    return 0;
}

static int run_jit(void *addr)
{
    errno = 0;
    void *p = mmap(addr, PAGE, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    printf("STEP jit_mmap wanted=%p page=%p errno=%d\n",
           addr, p, p == MAP_FAILED ? errno : 0);
    fflush(stdout);
    if (p == MAP_FAILED) return 30;

    static const unsigned char code[] = {
        0xB8, 0x2A, 0x00, 0x00, 0x00, 0xC3
    };
    memcpy(p, code, sizeof(code));
    __builtin___clear_cache((char *)p, (char *)p + 64);

    errno = 0;
    int rc = mprotect(p, PAGE, PROT_READ | PROT_EXEC);
    printf("STEP jit_protect rc=%d errno=%d\n", rc, rc ? errno : 0);
    fflush(stdout);
    print_map("jit_after", p);
    if (rc) {
        munmap(p, PAGE);
        return 31;
    }

    printf("STEP jit_call_begin fn=%p\n", p);
    fflush(stdout);
    rc = ((int (*)(void))p)();
    printf("STEP jit_call_end value=%d\n", rc);
    fflush(stdout);
    munmap(p, PAGE);
    return rc == 42 ? 0 : 32;
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s SCENARIO NTDLL\n", argv[0]);
        return 64;
    }

    const char *scenario = argv[1];
    const char *file_path = argv[2];
    char temp_path[64] = {0};
    int dirty = 0;
    int exec_mode = 0;
    int repeats = 1;
    void *jit_addr = FILE_ADDR;
    int do_file = 1;

    if (!strcmp(scenario, "baseline_jit")) {
        do_file = 0;
    } else if (!strcmp(scenario, "temp_clean_same")) {
        if (make_temp_file(temp_path)) return 65;
        file_path = temp_path;
    } else if (!strcmp(scenario, "temp_dirty_noexec_same")) {
        if (make_temp_file(temp_path)) return 65;
        file_path = temp_path; dirty = 1;
    } else if (!strcmp(scenario, "temp_dirty_exec_same")) {
        if (make_temp_file(temp_path)) return 65;
        file_path = temp_path; dirty = 1; exec_mode = 1;
    } else if (!strcmp(scenario, "ntdll_clean_same")) {
    } else if (!strcmp(scenario, "ntdll_dirty_noexec_same")) {
        dirty = 1;
    } else if (!strcmp(scenario, "ntdll_dirty_exec_same")) {
        dirty = 1; exec_mode = 1;
    } else if (!strcmp(scenario, "ntdll_dirty_exec_other")) {
        dirty = 1; exec_mode = 1; jit_addr = OTHER_ADDR;
    } else if (!strcmp(scenario, "ntdll_dirty_exec_repeat4_same")) {
        dirty = 1; exec_mode = 1; repeats = 4;
    } else if (!strcmp(scenario, "ntdll_dirty_rwx_same")) {
        dirty = 1; exec_mode = 2;
    } else {
        fprintf(stderr, "unknown scenario: %s\n", scenario);
        return 66;
    }

    printf("STEP scenario=%s do_file=%d dirty=%d exec_mode=%d repeats=%d jit=%p\n",
           scenario, do_file, dirty, exec_mode, repeats, jit_addr);
    fflush(stdout);

    int rc = 0;
    if (do_file) rc = map_file_cycle(file_path, dirty, exec_mode, repeats);
    if (!rc) rc = run_jit(jit_addr);

    if (temp_path[0]) unlink(temp_path);
    if (rc) {
        printf("RESULT FAIL rc=%d\n", rc);
        fflush(stdout);
        return rc;
    }

    printf("RESULT PASS\n");
    fflush(stdout);
    return 0;
}
C

x86_64-linux-gnu-gcc -O0 -g3 -Wall -Wextra -std=c11 "$SRC" -o "$X64"
cp -f "$SRC" "$OUTDIR/mobox_phase1d_mapping_probe.c"
file "$X64" "$BOX" >"$OUTDIR/binaries.txt"
"$BOX" --version >>"$OUTDIR/binaries.txt" 2>&1 || true
uname -a >"$OUTDIR/system.txt"
sha256sum "$NTDLL" >"$OUTDIR/ntdll_before.sha256"

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_LD_LIBRARY_PATH="/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/mobox/lib/x86_64-linux-gnu"

printf 'mode\tscenario\trepetition\texit_code\tresult_pass\tfallbacks\tquit_faults\tdynacache_warnings\tlast_step\n' >"$RESULTS"

scenarios=(
  baseline_jit
  temp_clean_same
  temp_dirty_noexec_same
  temp_dirty_exec_same
  ntdll_clean_same
  ntdll_dirty_noexec_same
  ntdll_dirty_exec_same
  ntdll_dirty_exec_other
  ntdll_dirty_exec_repeat4_same
  ntdll_dirty_rwx_same
)

run_case() {
    mode="$1"
    dyn="$2"
    scenario="$3"
    rep="$4"
    prefix="${mode}_${scenario}_r${rep}"
    out="$OUTDIR/${prefix}.stdout.txt"
    err="$OUTDIR/${prefix}.stderr.txt"

    echo "=== RUN mode=$mode scenario=$scenario rep=$rep ==="
    set +e
    timeout 30s env \
      BOX64_DYNAREC="$dyn" \
      BOX64_LOG=1 \
      BOX64_DYNAREC_LOG=0 \
      "$BOX" "$X64" "$scenario" "$NTDLL" \
      >"$out" 2>"$err"
    rc=$?
    set -e

    result_pass=$(grep -c '^RESULT PASS$' "$out" || true)
    fallbacks=$(grep -c 'BOX64_EXECMOD_COW_V4.*success' "$err" || true)
    quit_faults=$(grep -c 'Sigfault/Segbus while quitting' "$err" || true)
    warnings=$(grep -c 'cannot add DynaCache Block' "$err" || true)
    last_step=$(grep -E '^(STEP|RESULT)' "$out" | tail -1 | tr '\t' ' ' || true)

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$mode" "$scenario" "$rep" "$rc" "$result_pass" \
      "$fallbacks" "$quit_faults" "$warnings" "$last_step" >>"$RESULTS"
    echo "=== EXIT rc=$rc pass=$result_pass fallback=$fallbacks quit_fault=$quit_faults warnings=$warnings ==="
}

for mode in dynarec interp; do
    if [ "$mode" = dynarec ]; then dyn=1; else dyn=0; fi
    for scenario in "${scenarios[@]}"; do
        for rep in 1 2; do
            run_case "$mode" "$dyn" "$scenario" "$rep"
        done
    done
done

sha256sum "$NTDLL" >"$OUTDIR/ntdll_after.sha256"

python3 - "$OUTDIR" <<'PY'
from pathlib import Path
import csv
import sys

outdir = Path(sys.argv[1])
with (outdir / 'results.tsv').open(newline='', errors='replace') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))

bad = [r for r in rows if r['exit_code'] != '0' or r['result_pass'] != '1' or r['quit_faults'] != '0']
ntdll_ok = ((outdir / 'ntdll_before.sha256').read_text().split()[0] ==
            (outdir / 'ntdll_after.sha256').read_text().split()[0])

lines = [
    'MOBOX COMPAT LAB PHASE 1D - MAPPING BOOKKEEPING',
    '================================================',
    f'total runs: {len(rows)}',
    f'clean runs: {len(rows) - len(bad)}',
    f'problem runs: {len(bad)}',
    f'ntdll hash unchanged: {ntdll_ok}',
    '',
    'Per scenario:',
]
for r in rows:
    lines.append(
        f"{r['mode']} {r['scenario']} r{r['repetition']}: "
        f"exit={r['exit_code']} pass={r['result_pass']} "
        f"fallback={r['fallbacks']} quit_fault={r['quit_faults']} "
        f"warnings={r['dynacache_warnings']} | {r['last_step']}"
    )

(outdir / 'SUMMARY.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines[:7]))
PY
DEBIAN

cp -f "$OUTDIR/SUMMARY.txt" "$LATEST_SUMMARY"
tar -C "$(dirname "$OUTDIR")" -czf "$LATEST_ARCHIVE" "$(basename "$OUTDIR")"
termux-media-scan "$LATEST_SUMMARY" "$LATEST_ARCHIVE" >/dev/null 2>&1 || true

echo
echo "PHASE1D_SUMMARY=$LATEST_SUMMARY"
echo "PHASE1D_ARCHIVE=$LATEST_ARCHIVE"
