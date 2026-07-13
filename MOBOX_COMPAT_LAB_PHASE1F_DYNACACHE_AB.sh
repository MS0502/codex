#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
STAMP="$(date +%Y%m%d_%H%M%S)"
NAME="MOBOX_COMPAT_LAB_PHASE1F_${STAMP}"
OUTDIR="${DOWNLOADS}/TR_KR_LOCAL/${NAME}"
LATEST_SUMMARY="${DOWNLOADS}/MOBOX_COMPAT_LAB_PHASE1F_SUMMARY.txt"
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
SRC=/tmp/mobox_phase1f_dynacache_ab.c
X64=/tmp/mobox_phase1f_dynacache_ab_x64
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
#define ADDR1 ((void *)(uintptr_t)0x60000000u)
#define ADDR2 ((void *)(uintptr_t)0x60020000u)

static int make_temp_file(char path[64])
{
    strcpy(path, "/tmp/mobox_phase1f_file_XXXXXX");
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

static int one_map(const char *path, void *wanted, int dirty, int index)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        printf("RESULT FAIL stage=open index=%d errno=%d\n", index, errno);
        fflush(stdout);
        return 20;
    }

    printf("STEP mmap_begin index=%d wanted=%p\n", index, wanted);
    fflush(stdout);

    errno = 0;
    void *page = mmap(wanted, PAGE_SIZE_, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_FIXED, fd, 0);
    int map_errno = page == MAP_FAILED ? errno : 0;
    close(fd);

    printf("STEP mmap_end index=%d page=%p errno=%d\n",
           index, page, map_errno);
    fflush(stdout);
    if (page == MAP_FAILED) return 21;

    if (dirty) {
        volatile unsigned char *p = (volatile unsigned char *)page;
        unsigned char old = p[0];
        p[0] = (unsigned char)(old ^ 1u);
        p[0] = old;
        printf("STEP dirty_done index=%d\n", index);
        fflush(stdout);
    }

    errno = 0;
    int rc = mprotect(page, PAGE_SIZE_, PROT_READ | PROT_EXEC);
    printf("STEP mprotect_end index=%d rc=%d errno=%d\n",
           index, rc, rc ? errno : 0);
    fflush(stdout);
    if (rc) {
        munmap(page, PAGE_SIZE_);
        return 22;
    }

    errno = 0;
    rc = munmap(page, PAGE_SIZE_);
    printf("STEP munmap_end index=%d rc=%d errno=%d\n",
           index, rc, rc ? errno : 0);
    fflush(stdout);
    return rc ? 23 : 0;
}

int main(int argc, char **argv)
{
    if (argc != 4) {
        fprintf(stderr, "usage: %s FILE SOURCE DIRTY\n", argv[0]);
        return 64;
    }

    const char *input = argv[1];
    const char *source = argv[2];
    int dirty = atoi(argv[3]);
    char temp_path[64] = {0};
    const char *path = input;

    if (!strcmp(source, "temp")) {
        if (make_temp_file(temp_path)) return 65;
        path = temp_path;
    }

    printf("STEP start source=%s dirty=%d\n", source, dirty);
    fflush(stdout);

    int rc = one_map(path, ADDR1, dirty, 1);
    if (!rc) rc = one_map(path, ADDR2, dirty, 2);

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
cp -f "$SRC" "$OUTDIR/mobox_phase1f_dynacache_ab.c"
file "$X64" "$BOX" >"$OUTDIR/binaries.txt"
"$BOX" --version >>"$OUTDIR/binaries.txt" 2>&1 || true
uname -a >"$OUTDIR/system.txt"
sha256sum "$NTDLL" >"$OUTDIR/ntdll_before.sha256"

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_LD_LIBRARY_PATH="/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/mobox/lib/x86_64-linux-gnu"

printf 'mode\tscenario\trepetition\texit_code\tpass\tfallbacks\twarnings\tsegv_mmap\tlast_step\n' >"$RESULTS"

run_case() {
    mode="$1"
    dyn="$2"
    cache="$3"
    folder_mode="$4"
    scenario="$5"
    rep="$6"
    source="$7"
    dirty="$8"

    prefix="${mode}_${scenario}_r${rep}"
    stdout_file="$OUTDIR/${prefix}.stdout.txt"
    stderr_file="$OUTDIR/${prefix}.stderr.full.txt"
    key_file="$OUTDIR/${prefix}.stderr.key.txt"

    cache_folder=""
    if [ "$folder_mode" = fresh ]; then
        cache_folder="$OUTDIR/cache_${prefix}"
        mkdir -p "$cache_folder"
    fi

    echo "=== RUN mode=$mode scenario=$scenario rep=$rep ==="
    set +e
    if [ -n "$cache_folder" ]; then
        timeout 30s env \
          BOX64_DYNAREC="$dyn" \
          BOX64_DYNACACHE="$cache" \
          BOX64_DYNACACHE_FOLDER="$cache_folder" \
          BOX64_LOG=1 \
          BOX64_DYNAREC_LOG=0 \
          "$BOX" "$X64" "$NTDLL" "$source" "$dirty" \
          >"$stdout_file" 2>"$stderr_file"
    else
        timeout 30s env \
          BOX64_DYNAREC="$dyn" \
          BOX64_DYNACACHE="$cache" \
          BOX64_LOG=1 \
          BOX64_DYNAREC_LOG=0 \
          "$BOX" "$X64" "$NTDLL" "$source" "$dirty" \
          >"$stdout_file" 2>"$stderr_file"
    fi
    rc=$?
    set -e

    pass=0
    grep -q '^RESULT PASS' "$stdout_file" && pass=1 || true
    fallbacks="$(grep -c 'BOX64_EXECMOD_COW_V4.*success' "$stderr_file" 2>/dev/null || true)"
    warnings="$(grep -c 'cannot add DynaCache Block' "$stderr_file" 2>/dev/null || true)"
    segv_mmap="$(grep -c 'SIGSEGV .*box64/mmap' "$stderr_file" 2>/dev/null || true)"
    last_step="$(grep -E '^(STEP|RESULT)' "$stdout_file" | tail -1 | tr '\t' ' ' || true)"

    {
        grep -E 'BOX64_EXECMOD_COW_V4|DynaCache|SIGSEGV|box64/mmap|Sigfault/Segbus while quitting' "$stderr_file" | head -120 || true
        echo "COUNTS exit=$rc pass=$pass fallbacks=$fallbacks warnings=$warnings segv_mmap=$segv_mmap"
    } >"$key_file"

    if [ "$rc" -eq 0 ] && [ "$pass" -eq 1 ]; then
        rm -f "$stderr_file"
    else
        mv -f "$stderr_file" "$OUTDIR/${prefix}.failure.stderr.txt"
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$mode" "$scenario" "$rep" "$rc" "$pass" "$fallbacks" \
      "$warnings" "$segv_mmap" "$last_step" >>"$RESULTS"

    echo "=== EXIT mode=$mode scenario=$scenario rc=$rc pass=$pass segv_mmap=$segv_mmap ==="
}

for rep in 1 2 3; do
    run_case dynarec 1 1 default ntdll_dirty_cache1_default "$rep" ntdll 1
    run_case dynarec 1 1 fresh   ntdll_dirty_cache1_fresh   "$rep" ntdll 1
    run_case dynarec 1 0 default ntdll_dirty_cache0         "$rep" ntdll 1
    run_case interp  0 1 default ntdll_dirty_interp         "$rep" ntdll 1
done

for rep in 1 2; do
    run_case dynarec 1 1 default ntdll_clean_cache1 "$rep" ntdll 0
    run_case dynarec 1 0 default ntdll_clean_cache0 "$rep" ntdll 0
    run_case dynarec 1 1 default temp_dirty_cache1  "$rep" temp 1
    run_case dynarec 1 0 default temp_dirty_cache0  "$rep" temp 1
done

sha256sum "$NTDLL" >"$OUTDIR/ntdll_after.sha256"

python3 - "$OUTDIR" <<'PY'
from pathlib import Path
import csv, json, sys

outdir = Path(sys.argv[1])
with (outdir / 'results.tsv').open(newline='', errors='replace') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))

problems = [r for r in rows if r['exit_code'] != '0' or r['pass'] != '1']
by_scenario = {}
for r in rows:
    by_scenario.setdefault(r['scenario'], []).append(int(r['exit_code']))

hash_ok = ((outdir / 'ntdll_before.sha256').read_text().split()[0] ==
           (outdir / 'ntdll_after.sha256').read_text().split()[0])

lines = [
    'MOBOX COMPAT LAB PHASE 1F - DYNACACHE A/B',
    '==========================================',
    f'total runs: {len(rows)}',
    f'problem runs: {len(problems)}',
    f'ntdll hash unchanged: {hash_ok}',
    '',
    'Per scenario:',
]
for scenario in sorted(by_scenario):
    subset = [r for r in rows if r['scenario'] == scenario]
    exits = ','.join(r['exit_code'] for r in subset)
    segv = sum(int(r['segv_mmap']) for r in subset)
    warnings = sum(int(r['warnings']) for r in subset)
    lines.append(f'{scenario}: exits={exits} mmap_segv={segv} warnings={warnings}')

lines += ['', 'Problem runs:']
for r in problems:
    lines.append(json.dumps(r, ensure_ascii=False))

(outdir / 'SUMMARY.txt').write_text('\n'.join(lines) + '\n')
(outdir / 'summary.json').write_text(json.dumps({
    'total_runs': len(rows),
    'problem_runs': len(problems),
    'ntdll_hash_unchanged': hash_ok,
    'by_scenario': by_scenario,
}, indent=2) + '\n')
print('\n'.join(lines))
PY

DEBIAN

cp -f "$OUTDIR/SUMMARY.txt" "$LATEST_SUMMARY"
tar -C "$(dirname "$OUTDIR")" -czf "$LATEST_ARCHIVE" "$(basename "$OUTDIR")"
termux-media-scan "$LATEST_SUMMARY" "$LATEST_ARCHIVE" >/dev/null 2>&1 || true

echo
echo "PHASE1F_SUMMARY=$LATEST_SUMMARY"
echo "PHASE1F_ARCHIVE=$LATEST_ARCHIVE"
