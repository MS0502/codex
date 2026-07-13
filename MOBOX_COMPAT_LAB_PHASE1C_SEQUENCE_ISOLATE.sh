#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
ROOT="${TERMUX_PREFIX}/glibc"
DOWNLOADS="${HOME}/storage/downloads"
STAMP="$(date +%Y%m%d_%H%M%S)"
NAME="MOBOX_COMPAT_LAB_PHASE1C_${STAMP}"
OUTDIR="${DOWNLOADS}/TR_KR_LOCAL/${NAME}"
LATEST_SUMMARY="${DOWNLOADS}/MOBOX_COMPAT_LAB_PHASE1C_SUMMARY.txt"
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
SRC=/tmp/mobox_phase1c_sequence_probe.c
X64=/tmp/mobox_phase1c_sequence_probe_x64
RESULTS="$OUTDIR/results.tsv"

mkdir -p "$OUTDIR"

for cmd in x86_64-linux-gnu-gcc python3 timeout file sha256sum; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: missing required command: $cmd" >&2
        exit 10
    }
done

[ -x "$BOX" ] || {
    echo "ERROR: Box64 not found: $BOX" >&2
    exit 11
}
[ -f "$NTDLL" ] || {
    echo "ERROR: ntdll.dll not found: $NTDLL" >&2
    exit 12
}

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

static int direct_write_probe(volatile unsigned char *p)
{
    unsigned char old = *p;
    *p = (unsigned char)(old ^ 1u);
    *p = old;
    return 0;
}

static int safe_exec_probe(void *page)
{
    typedef int (*fn_t)(void);
    fn_t fn = (fn_t)page;
    probe_signal = 0;
    if (sigsetjmp(probe_jmp, 1)) return -1000 - (int)probe_signal;
    return fn();
}

static void emit_return_value(void *page, uint32_t value)
{
    unsigned char code[6];
    code[0] = 0xB8;
    memcpy(code + 1, &value, sizeof(value));
    code[5] = 0xC3;
    memcpy(page, code, sizeof(code));
    __builtin___clear_cache((char *)page, (char *)page + 64);
}

static void *map_case(const char *source, const char *path, size_t len,
                      int init_prot, int fixed, int *fd_out,
                      void **reserve_out)
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
        if (fd < 0) return MAP_FAILED;
    }

    if (fixed) {
        reserve = mmap(NULL, len + 65536, PROT_NONE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (reserve == MAP_FAILED) {
            if (fd >= 0) close(fd);
            return MAP_FAILED;
        }
        wanted = reserve;
        flags |= MAP_FIXED;
    }

    p = mmap(wanted, len, init_prot, flags, fd, 0);
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

static int run_exact_matrix(const char *ntdll_path, int use_safe_write)
{
    char temp_path[] = "/tmp/mobox_phase1c_file_XXXXXX";
    unsigned char buf[8192];
    int tmpfd = mkstemp(temp_path);
    int case_no = 0;

    memset(buf, 0xA5, sizeof(buf));
    if (tmpfd < 0 || write(tmpfd, buf, sizeof(buf)) != (ssize_t)sizeof(buf)) {
        fprintf(stderr, "prepare temp failed errno=%d\n", errno);
        return 30;
    }
    close(tmpfd);

    const char *sources[] = {"anon", "temp", "ntdll"};
    for (size_t s = 0; s < 3; ++s) {
        for (int fixed = 0; fixed <= 1; ++fixed) {
            int dirty_max = strcmp(sources[s], "anon") ? 1 : 0;
            for (int dirty = 0; dirty <= dirty_max; ++dirty) {
                for (size_t i = 0; i < sizeof(prot_defs)/sizeof(prot_defs[0]); ++i) {
                    for (size_t j = 0; j < sizeof(prot_defs)/sizeof(prot_defs[0]); ++j) {
                        if (i == j) continue;

                        const char *path = !strcmp(sources[s], "temp")
                            ? temp_path : ntdll_path;
                        int fd = -1;
                        void *reserve = NULL;
                        void *p = map_case(sources[s], path, 4096,
                                           prot_defs[i].prot, fixed,
                                           &fd, &reserve);
                        ++case_no;

                        if (p == MAP_FAILED) {
                            printf("STEP matrix_map_fail case=%d source=%s errno=%d\n",
                                   case_no, sources[s], errno);
                            fflush(stdout);
                            unlink(temp_path);
                            return 31;
                        }

                        if (dirty) {
                            if (!(prot_defs[i].prot & PROT_WRITE) &&
                                mprotect(p, 4096, PROT_READ | PROT_WRITE)) {
                                printf("STEP matrix_prep_rw_fail case=%d errno=%d\n",
                                       case_no, errno);
                                fflush(stdout);
                                cleanup_case(p, 4096, fd, reserve, fixed);
                                unlink(temp_path);
                                return 32;
                            }

                            int wr = use_safe_write
                                ? safe_write_probe((volatile unsigned char *)p)
                                : direct_write_probe((volatile unsigned char *)p);
                            if (wr) {
                                printf("STEP matrix_write_fail case=%d rc=%d\n",
                                       case_no, wr);
                                fflush(stdout);
                                cleanup_case(p, 4096, fd, reserve, fixed);
                                unlink(temp_path);
                                return 33;
                            }

                            if (prot_defs[i].prot != (PROT_READ | PROT_WRITE) &&
                                mprotect(p, 4096, prot_defs[i].prot)) {
                                printf("STEP matrix_restore_fail case=%d errno=%d\n",
                                       case_no, errno);
                                fflush(stdout);
                                cleanup_case(p, 4096, fd, reserve, fixed);
                                unlink(temp_path);
                                return 34;
                            }
                        }

                        if (mprotect(p, 4096, prot_defs[j].prot)) {
                            printf("STEP matrix_final_fail case=%d source=%s "
                                   "fixed=%d dirty=%d %s_to_%s errno=%d\n",
                                   case_no, sources[s], fixed, dirty,
                                   prot_defs[i].name, prot_defs[j].name, errno);
                            fflush(stdout);
                            cleanup_case(p, 4096, fd, reserve, fixed);
                            unlink(temp_path);
                            return 35;
                        }

                        if (prot_defs[j].prot & PROT_WRITE) {
                            int wr = use_safe_write
                                ? safe_write_probe((volatile unsigned char *)p)
                                : direct_write_probe((volatile unsigned char *)p);
                            if (wr) {
                                printf("STEP matrix_final_write_fail case=%d rc=%d\n",
                                       case_no, wr);
                                fflush(stdout);
                                cleanup_case(p, 4096, fd, reserve, fixed);
                                unlink(temp_path);
                                return 36;
                            }
                        }

                        cleanup_case(p, 4096, fd, reserve, fixed);
                    }
                }
            }
        }
    }

    unlink(temp_path);
    printf("STEP matrix_complete cases=%d\n", case_no);
    fflush(stdout);
    return case_no == 120 ? 0 : 37;
}

static int run_jit(int use_safe_exec)
{
    void *page = mmap((void *)(uintptr_t)0x60000000u, 4096,
                      PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED,
                      -1, 0);
    if (page == MAP_FAILED) {
        printf("STEP jit_mmap_fail errno=%d\n", errno);
        fflush(stdout);
        return 40;
    }

    printf("STEP jit_mmap page=%p\n", page);
    fflush(stdout);
    emit_return_value(page, 42);

    errno = 0;
    int rc = mprotect(page, 4096, PROT_READ | PROT_EXEC);
    printf("STEP jit_protect rc=%d errno=%d\n", rc, rc ? errno : 0);
    fflush(stdout);
    if (rc) return 41;

    printf("STEP jit_call_begin safe=%d\n", use_safe_exec);
    fflush(stdout);
    rc = use_safe_exec ? safe_exec_probe(page) : ((int (*)(void))page)();
    printf("STEP jit_call_end value=%d\n", rc);
    fflush(stdout);

    munmap(page, 4096);
    return rc == 42 ? 0 : 42;
}

int main(int argc, char **argv)
{
    int install_handlers = 0;
    int run_matrix = 0;
    int safe_write = 0;
    int safe_exec = 0;

    if (argc != 3) {
        fprintf(stderr, "usage: %s MODE NTDLL_PATH\n", argv[0]);
        return 64;
    }

    if (!strcmp(argv[1], "fresh_direct")) {
    } else if (!strcmp(argv[1], "fresh_safeexec")) {
        install_handlers = 1;
        safe_exec = 1;
    } else if (!strcmp(argv[1], "exact_direct")) {
        run_matrix = 1;
    } else if (!strcmp(argv[1], "exact_handlers_direct")) {
        install_handlers = 1;
        run_matrix = 1;
    } else if (!strcmp(argv[1], "exact_original")) {
        install_handlers = 1;
        run_matrix = 1;
        safe_write = 1;
        safe_exec = 1;
    } else {
        fprintf(stderr, "unknown mode: %s\n", argv[1]);
        return 65;
    }

    printf("STEP mode=%s handlers=%d matrix=%d safe_write=%d safe_exec=%d\n",
           argv[1], install_handlers, run_matrix, safe_write, safe_exec);
    fflush(stdout);

    if (install_handlers) {
        install_probe_handlers();
        printf("STEP handlers_installed\n");
        fflush(stdout);
    }

    if (run_matrix) {
        int rc = run_exact_matrix(argv[2], safe_write);
        if (rc) return rc;
    }

    int rc = run_jit(safe_exec);
    if (rc) return rc;

    printf("RESULT PASS\n");
    fflush(stdout);
    return 0;
}
C

x86_64-linux-gnu-gcc -O2 -g3 -Wall -Wextra -std=c11 "$SRC" -o "$X64"
cp -f "$SRC" "$OUTDIR/mobox_phase1c_sequence_probe.c"
file "$X64" "$BOX" >"$OUTDIR/binaries.txt"
"$BOX" --version >>"$OUTDIR/binaries.txt" 2>&1 || true
uname -a >"$OUTDIR/system.txt"
sha256sum "$NTDLL" >"$OUTDIR/ntdll_before.sha256"

export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_LD_LIBRARY_PATH="/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/mobox/lib/x86_64-linux-gnu"

printf 'mode\tcase\trepetition\texit_code\tlast_step\n' >"$RESULTS"

run_case() {
    mode="$1"
    dyn="$2"
    case_name="$3"
    repetition="$4"
    prefix="${mode}_${case_name}_r${repetition}"
    stdout_file="$OUTDIR/${prefix}.stdout.txt"
    stderr_file="$OUTDIR/${prefix}.stderr.txt"

    echo "=== RUN mode=$mode case=$case_name repetition=$repetition ==="
    set +e
    timeout 90s env \
      BOX64_DYNAREC="$dyn" \
      BOX64_LOG=1 \
      BOX64_DYNAREC_LOG=1 \
      "$BOX" "$X64" "$case_name" "$NTDLL" \
      >"$stdout_file" 2>"$stderr_file"
    rc=$?
    set -e

    last_step="$(grep -E '^(STEP|RESULT)' "$stdout_file" | tail -1 | tr '\t' ' ' || true)"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$mode" "$case_name" "$repetition" "$rc" "$last_step" >>"$RESULTS"
    printf '%s\n' "$rc" >"$OUTDIR/${prefix}.exitcode"
    echo "=== EXIT mode=$mode case=$case_name repetition=$repetition rc=$rc last=$last_step ==="
}

cases=(
  fresh_direct
  fresh_safeexec
  exact_direct
  exact_handlers_direct
  exact_original
)

for repetition in 1 2 3; do
    for case_name in "${cases[@]}"; do
        run_case dynarec 1 "$case_name" "$repetition"
    done
done

for repetition in 1 2 3; do
    for case_name in "${cases[@]}"; do
        run_case interp 0 "$case_name" "$repetition"
    done
done

sha256sum "$NTDLL" >"$OUTDIR/ntdll_after.sha256"

python3 - "$OUTDIR" <<'PY'
from pathlib import Path
import csv
import sys

outdir = Path(sys.argv[1])
with (outdir / "results.tsv").open(newline="", errors="replace") as f:
    rows = list(csv.DictReader(f, delimiter="\t"))

failed = [r for r in rows if r["exit_code"] != "0"]
by_case = {}
for row in rows:
    key = (row["mode"], row["case"])
    by_case.setdefault(key, []).append(row["exit_code"])

before = (outdir / "ntdll_before.sha256").read_text().split()[0]
after = (outdir / "ntdll_after.sha256").read_text().split()[0]

lines = [
    "MOBOX COMPAT LAB PHASE 1C - SEQUENCE / SIGNAL ISOLATION",
    "=======================================================",
    f"total runs: {len(rows)}",
    f"passed: {len(rows) - len(failed)}",
    f"failed: {len(failed)}",
    f"ntdll hash unchanged: {before == after}",
    "",
    "Per case:",
]
for (mode, case), codes in sorted(by_case.items()):
    lines.append(f"{mode} {case}: exits={','.join(codes)}")

lines.extend(["", "Failures:"])
if failed:
    for row in failed:
        lines.append(
            f"{row['mode']} {row['case']} r{row['repetition']}: "
            f"exit={row['exit_code']} | {row['last_step']}"
        )
else:
    lines.append("None")

(outdir / "SUMMARY.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
PY

first_failed="$(
  awk -F '\t' 'NR>1 && $1=="dynarec" && $4!="0" {print $2; exit}' "$RESULTS"
)"
if [ -n "$first_failed" ]; then
    set +e
    timeout 90s env \
      BOX64_DYNAREC=1 \
      BOX64_LOG=2 \
      BOX64_DYNAREC_LOG=2 \
      "$BOX" "$X64" "$first_failed" "$NTDLL" \
      >"$OUTDIR/failing_dynarec_verbose.stdout.txt" \
      2>"$OUTDIR/failing_dynarec_verbose.stderr.txt"
    echo "$?" >"$OUTDIR/failing_dynarec_verbose.exitcode"
    set -e

    if command -v strace >/dev/null 2>&1; then
        set +e
        timeout 90s strace -f \
          -e trace=mmap,mprotect,munmap,rt_sigaction,rt_sigreturn \
          -o "$OUTDIR/failing_dynarec.strace.txt" \
          env BOX64_DYNAREC=1 BOX64_LOG=0 BOX64_DYNAREC_LOG=0 \
          "$BOX" "$X64" "$first_failed" "$NTDLL" \
          >"$OUTDIR/failing_dynarec_strace.stdout.txt" \
          2>"$OUTDIR/failing_dynarec_strace.stderr.txt"
        echo "$?" >"$OUTDIR/failing_dynarec_strace.exitcode"
        set -e
    fi
fi
DEBIAN

cp -f "$OUTDIR/SUMMARY.txt" "$LATEST_SUMMARY"
tar -C "$(dirname "$OUTDIR")" -czf "$LATEST_ARCHIVE" "$(basename "$OUTDIR")"
termux-media-scan "$LATEST_SUMMARY" "$LATEST_ARCHIVE" >/dev/null 2>&1 || true

echo
echo "PHASE1C_SUMMARY=$LATEST_SUMMARY"
echo "PHASE1C_ARCHIVE=$LATEST_ARCHIVE"
