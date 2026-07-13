#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="${DOWNLOADS}/TR_KR_LOCAL/MOBOX_COMPAT_LAB_PHASE1_${STAMP}"
LATEST_SUMMARY="${DOWNLOADS}/MOBOX_COMPAT_LAB_PHASE1_SUMMARY.txt"
LATEST_ARCHIVE="${DOWNLOADS}/MOBOX_COMPAT_LAB_PHASE1_${STAMP}.tar.gz"

mkdir -p "$OUTDIR"

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$DOWNLOADS:/mnt/downloads" \
  --env LAB_OUTDIR="/mnt/downloads/TR_KR_LOCAL/MOBOX_COMPAT_LAB_PHASE1_${STAMP}" \
  -- bash -s <<'DEBIAN'
set -euo pipefail

OUTDIR="${LAB_OUTDIR:?}"
BOX=/root/box64/build/box64
NTDLL=/opt/mobox/wine-9.3-vanilla-wow64/lib/wine/x86_64-windows/ntdll.dll
SRC=/tmp/mobox_compat_phase1.c
NATIVE=/tmp/mobox_compat_phase1_native
X64=/tmp/mobox_compat_phase1_x64

mkdir -p "$OUTDIR"

for cmd in gcc x86_64-linux-gnu-gcc python3 sha256sum timeout; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: missing required command: $cmd" >&2
        exit 10
    fi
done

if [ ! -x "$BOX" ]; then
    echo "ERROR: Box64 not found: $BOX" >&2
    exit 11
fi
if [ ! -f "$NTDLL" ]; then
    echo "ERROR: ntdll.dll not found: $NTDLL" >&2
    exit 12
fi

cat >"$SRC" <<'C'
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

typedef struct {
    const char *name;
    int prot;
} prot_def_t;

static const prot_def_t prot_defs[] = {
    {"R",   PROT_READ},
    {"RW",  PROT_READ | PROT_WRITE},
    {"RX",  PROT_READ | PROT_EXEC},
    {"RWX", PROT_READ | PROT_WRITE | PROT_EXEC},
};

static sigjmp_buf probe_jmp;
static volatile sig_atomic_t probe_signal;

static void probe_handler(int sig)
{
    probe_signal = sig;
    siglongjmp(probe_jmp, 1);
}

static void install_probe_handlers(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = probe_handler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGILL, &sa, NULL);
}

static const char *map_perms(void *addr, char out[5])
{
    FILE *fp = fopen("/proc/self/maps", "r");
    char line[512];
    uintptr_t target = (uintptr_t)addr;
    unsigned long long start, end;
    char perms[5];

    strcpy(out, "????");
    if (!fp) return out;

    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "%llx-%llx %4s", &start, &end, perms) == 3 &&
            target >= start && target < end) {
            memcpy(out, perms, 4);
            out[4] = '\0';
            break;
        }
    }
    fclose(fp);
    return out;
}

static int safe_write_probe(volatile unsigned char *p)
{
    unsigned char old;
    probe_signal = 0;
    if (sigsetjmp(probe_jmp, 1)) return -(int)probe_signal;
    old = *p;
    *p = (unsigned char)(old ^ 1u);
    *p = old;
    return 0;
}

static int safe_exec_probe(void *page)
{
    typedef int (*fn_t)(void);
    fn_t fn = (fn_t)page;
    int value;

    probe_signal = 0;
    if (sigsetjmp(probe_jmp, 1)) return -1000 - (int)probe_signal;
    value = fn();
    return value;
}

static int write_test_code(void *page)
{
#if defined(__x86_64__)
    static const unsigned char code[] = {0xB8, 0x2A, 0x00, 0x00, 0x00, 0xC3};
    memcpy(page, code, sizeof(code));
#elif defined(__aarch64__)
    static const uint32_t code[] = {0x52800540u, 0xD65F03C0u};
    memcpy(page, code, sizeof(code));
#else
    return -1;
#endif
    __builtin___clear_cache((char *)page, (char *)page + 64);
    return 0;
}

static void *map_case(const char *source, const char *path, size_t len,
                      int init_prot, int fixed, int *fd_out, void **reserve_out,
                      int *map_errno)
{
    int fd = -1;
    int flags = MAP_PRIVATE;
    void *reserve = NULL;
    void *wanted = NULL;
    void *p;

    if (!strcmp(source, "anon")) {
        flags |= MAP_ANONYMOUS;
    } else {
        fd = open(path, O_RDONLY);
        if (fd < 0) {
            *map_errno = errno;
            return MAP_FAILED;
        }
    }

    if (fixed) {
        reserve = mmap(NULL, len + 65536, PROT_NONE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (reserve == MAP_FAILED) {
            *map_errno = errno;
            if (fd >= 0) close(fd);
            return MAP_FAILED;
        }
        wanted = reserve;
        flags |= MAP_FIXED;
    }

    errno = 0;
    p = mmap(wanted, len, init_prot, flags, fd, 0);
    *map_errno = (p == MAP_FAILED) ? errno : 0;

    if (p == MAP_FAILED && reserve && reserve != MAP_FAILED)
        munmap(reserve, len + 65536);

    *fd_out = fd;
    *reserve_out = reserve;
    return p;
}

static void cleanup_case(void *p, size_t len, int fd, void *reserve, int fixed)
{
    if (fixed && reserve && reserve != MAP_FAILED)
        munmap(reserve, len + 65536);
    else if (p && p != MAP_FAILED)
        munmap(p, len);
    if (fd >= 0) close(fd);
}

static void run_matrix(const char *label, const char *ntdll_path)
{
    char temp_path[] = "/tmp/mobox_compat_file_XXXXXX";
    unsigned char buf[8192];
    int tmpfd = mkstemp(temp_path);
    int case_no = 0;
    size_t i, j;

    memset(buf, 0xA5, sizeof(buf));
    if (tmpfd < 0 || write(tmpfd, buf, sizeof(buf)) != (ssize_t)sizeof(buf)) {
        fprintf(stderr, "failed to prepare temp file: %s\n", strerror(errno));
        exit(20);
    }
    close(tmpfd);

    printf("record\tmode\tcase_id\tsource\tfixed\tdirty\tinit\tfinal\tmap_rc\tmap_errno\tprep_rc\tprep_errno\tprotect_rc\tprotect_errno\tperms\twrite_probe\texec_probe\n");

    const char *sources[] = {"anon", "temp", "ntdll"};
    for (size_t s = 0; s < 3; ++s) {
        for (int fixed = 0; fixed <= 1; ++fixed) {
            int dirty_max = strcmp(sources[s], "anon") ? 1 : 0;
            for (int dirty = 0; dirty <= dirty_max; ++dirty) {
                for (i = 0; i < sizeof(prot_defs)/sizeof(prot_defs[0]); ++i) {
                    for (j = 0; j < sizeof(prot_defs)/sizeof(prot_defs[0]); ++j) {
                        if (i == j) continue;

                        const char *path = !strcmp(sources[s], "temp") ? temp_path : ntdll_path;
                        size_t len = 4096;
                        int fd = -1, map_errno = 0, prep_rc = 0, prep_errno = 0;
                        int protect_rc = -999, protect_errno = 0;
                        int write_probe = 9999, exec_probe = 9999;
                        void *reserve = NULL;
                        void *p = map_case(sources[s], path, len,
                                           prot_defs[i].prot, fixed,
                                           &fd, &reserve, &map_errno);
                        char perms[5] = "----";

                        ++case_no;
                        if (p != MAP_FAILED && dirty) {
                            if (!(prot_defs[i].prot & PROT_WRITE)) {
                                errno = 0;
                                prep_rc = mprotect(p, len, PROT_READ | PROT_WRITE);
                                prep_errno = prep_rc ? errno : 0;
                            }
                            if (!prep_rc) {
                                int wr = safe_write_probe((volatile unsigned char *)p);
                                if (wr) {
                                    prep_rc = -2;
                                    prep_errno = -wr;
                                }
                            }
                            if (!prep_rc && prot_defs[i].prot != (PROT_READ | PROT_WRITE)) {
                                errno = 0;
                                prep_rc = mprotect(p, len, prot_defs[i].prot);
                                prep_errno = prep_rc ? errno : 0;
                            }
                        }

                        if (p != MAP_FAILED && !prep_rc) {
                            errno = 0;
                            protect_rc = mprotect(p, len, prot_defs[j].prot);
                            protect_errno = protect_rc ? errno : 0;
                            map_perms(p, perms);
                            if (!protect_rc && (prot_defs[j].prot & PROT_WRITE))
                                write_probe = safe_write_probe((volatile unsigned char *)p);
                        }

                        printf("matrix\t%s\t%03d\t%s\t%d\t%d\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%d\t%d\n",
                               label, case_no, sources[s], fixed, dirty,
                               prot_defs[i].name, prot_defs[j].name,
                               p == MAP_FAILED ? -1 : 0, map_errno,
                               prep_rc, prep_errno, protect_rc, protect_errno,
                               perms, write_probe, exec_probe);
                        fflush(stdout);
                        cleanup_case(p, len, fd, reserve, fixed);
                    }
                }
            }
        }
    }

    const struct {
        const char *id;
        int final_prot;
    } jit_cases[] = {
        {"JIT_RW_TO_RX", PROT_READ | PROT_EXEC},
        {"JIT_RW_TO_RWX", PROT_READ | PROT_WRITE | PROT_EXEC},
        {"JIT_RW_TO_R", PROT_READ},
        {"JIT_RW_TO_RW", PROT_READ | PROT_WRITE},
    };

    for (size_t k = 0; k < sizeof(jit_cases)/sizeof(jit_cases[0]); ++k) {
        void *p = mmap(NULL, 4096, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        int map_errno = p == MAP_FAILED ? errno : 0;
        int prep_rc = 0;
        int protect_rc = -999, protect_errno = 0;
        int exec_probe = 9999, write_probe = 9999;
        char perms[5] = "----";

        if (p != MAP_FAILED) {
            prep_rc = write_test_code(p);
            errno = 0;
            protect_rc = mprotect(p, 4096, jit_cases[k].final_prot);
            protect_errno = protect_rc ? errno : 0;
            map_perms(p, perms);
            if (!protect_rc && (jit_cases[k].final_prot & PROT_WRITE))
                write_probe = safe_write_probe((volatile unsigned char *)p + 128);
            if (!protect_rc && (jit_cases[k].final_prot & PROT_EXEC))
                exec_probe = safe_exec_probe(p);
        }
        printf("jit\t%s\t%s\tanon\t0\t1\tRW\t%s\t%d\t%d\t%d\t0\t%d\t%d\t%s\t%d\t%d\n",
               label, jit_cases[k].id,
               (jit_cases[k].final_prot == (PROT_READ|PROT_EXEC)) ? "RX" :
               (jit_cases[k].final_prot == (PROT_READ|PROT_WRITE|PROT_EXEC)) ? "RWX" :
               (jit_cases[k].final_prot == PROT_READ) ? "R" : "RW",
               p == MAP_FAILED ? -1 : 0, map_errno, prep_rc,
               protect_rc, protect_errno, perms, write_probe, exec_probe);
        if (p != MAP_FAILED) munmap(p, 4096);
    }

    unlink(temp_path);
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s MODE NTDLL_PATH\n", argv[0]);
        return 64;
    }
    install_probe_handlers();
    run_matrix(argv[1], argv[2]);
    return 0;
}
C

cp -f "$SRC" "$OUTDIR/mobox_compat_phase1.c"

echo "=== BUILD NATIVE ==="
gcc -O2 -Wall -Wextra -std=c11 "$SRC" -o "$NATIVE"

echo "=== BUILD X86_64 ==="
x86_64-linux-gnu-gcc -O2 -Wall -Wextra -std=c11 "$SRC" -o "$X64"

sha256sum "$NTDLL" >"$OUTDIR/ntdll_before.sha256"
file "$NATIVE" "$X64" "$BOX" >"$OUTDIR/binaries.txt"
"$BOX" --version >>"$OUTDIR/binaries.txt" 2>&1 || true
uname -a >"$OUTDIR/system.txt"
cat /proc/version >>"$OUTDIR/system.txt"

run_mode() {
    mode="$1"
    outfile="$2"
    errfile="$3"
    shift 3
    echo "=== RUN $mode ==="
    timeout 180s "$@" >"$outfile" 2>"$errfile"
}

run_mode native "$OUTDIR/native.tsv" "$OUTDIR/native.stderr.txt" \
    "$NATIVE" native "$NTDLL"

export BOX64_NORCFILES=1
export BOX64_LOG=0
export BOX64_MMAP32=0
export BOX64_LD_LIBRARY_PATH="/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/mobox/lib/x86_64-linux-gnu"

export BOX64_DYNAREC=1
run_mode dynarec "$OUTDIR/dynarec.tsv" "$OUTDIR/dynarec.stderr.txt" \
    "$BOX" "$X64" dynarec "$NTDLL"

export BOX64_DYNAREC=0
run_mode interp "$OUTDIR/interp.tsv" "$OUTDIR/interp.stderr.txt" \
    "$BOX" "$X64" interp "$NTDLL"

sha256sum "$NTDLL" >"$OUTDIR/ntdll_after.sha256"

python3 - "$OUTDIR" <<'PY'
from pathlib import Path
import csv
import json
import sys

outdir = Path(sys.argv[1])
files = {
    'native': outdir / 'native.tsv',
    'dynarec': outdir / 'dynarec.tsv',
    'interp': outdir / 'interp.tsv',
}

KEY_FIELDS = ['record', 'case_id', 'source', 'fixed', 'dirty', 'init', 'final']
COMPARE_FIELDS = ['map_rc', 'map_errno', 'prep_rc', 'prep_errno',
                  'protect_rc', 'protect_errno', 'perms',
                  'write_probe', 'exec_probe']

def load(path):
    with path.open(newline='', errors='replace') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    return {tuple(row[k] for k in KEY_FIELDS): row for row in rows}

data = {name: load(path) for name, path in files.items()}
all_keys = sorted(set().union(*(d.keys() for d in data.values())))

mismatches = []
for key in all_keys:
    n = data['native'].get(key)
    d = data['dynarec'].get(key)
    i = data['interp'].get(key)
    for pair_name, left, right in [
        ('native_vs_dynarec', n, d),
        ('native_vs_interp', n, i),
        ('dynarec_vs_interp', d, i),
    ]:
        if left is None or right is None:
            mismatches.append({'pair': pair_name, 'key': key, 'reason': 'missing_row'})
            continue
        diff = {field: [left[field], right[field]]
                for field in COMPARE_FIELDS if left[field] != right[field]}
        if diff:
            mismatches.append({'pair': pair_name, 'key': key, 'diff': diff})

counts = {name: len(rows) for name, rows in data.items()}
summary = {
    'phase': 1,
    'counts': counts,
    'total_comparisons': len(all_keys) * 3,
    'mismatch_count': len(mismatches),
    'ntdll_hash_unchanged': (outdir / 'ntdll_before.sha256').read_text().split()[0]
                            == (outdir / 'ntdll_after.sha256').read_text().split()[0],
}

(outdir / 'mismatches.json').write_text(json.dumps(mismatches, indent=2))

lines = [
    'MOBOX COMPAT LAB PHASE 1',
    '========================',
    f"native cases: {counts['native']}",
    f"dynarec cases: {counts['dynarec']}",
    f"interp cases: {counts['interp']}",
    f"comparisons: {summary['total_comparisons']}",
    f"mismatches: {summary['mismatch_count']}",
    f"ntdll hash unchanged: {summary['ntdll_hash_unchanged']}",
    '',
    'First 40 mismatches:',
]
for item in mismatches[:40]:
    lines.append(json.dumps(item, ensure_ascii=False))

(outdir / 'SUMMARY.txt').write_text('\n'.join(lines) + '\n')
(outdir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('\n'.join(lines[:8]))
PY

DEBIAN

cp -f "$OUTDIR/SUMMARY.txt" "$LATEST_SUMMARY"
tar -C "$(dirname "$OUTDIR")" -czf "$LATEST_ARCHIVE" "$(basename "$OUTDIR")"
termux-media-scan "$LATEST_SUMMARY" "$LATEST_ARCHIVE" >/dev/null 2>&1 || true

echo
echo "PHASE1_SUMMARY=$LATEST_SUMMARY"
echo "PHASE1_ARCHIVE=$LATEST_ARCHIVE"
