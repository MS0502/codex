#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$PREFIX/glibc"
OUT="$HOME/storage/downloads/box64_execmod_patch_v3_result.txt"

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  -- bash -s <<'DEBIAN' 2>&1 | tee "$OUT"
set -euo pipefail
cd /root/box64

echo "=== RESTORE SOURCE ==="
git restore src/wrapped/wrappedlibc.c
cp -f src/wrapped/wrappedlibc.c src/wrapped/wrappedlibc.c.pre_execmod_v3

python3 - <<'PY'
from pathlib import Path

path = Path("src/wrapped/wrappedlibc.c")
text = path.read_text()

signature = "EXPORT int my_mprotect(x64emu_t* emu, void *addr, unsigned long len, int prot)\n"
start = text.find(signature)
if start < 0:
    raise SystemExit("my_mprotect signature not found")

end_marker = "\ntypedef struct mallinfo"
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("my_mprotect end marker not found")

replacement = r'''EXPORT int my_mprotect(x64emu_t* emu, void *addr, unsigned long len, int prot)
{
    #ifdef DYNAREC
    last_mmap_0_addr = NULL;
    last_mmap_0_len = 0;
    #endif

    if(emu && (BOX64ENV(log)>=LOG_DEBUG || BOX64ENV(dynarec_log)>=LOG_DEBUG))
        printf_log(LOG_NONE, "mprotect(%p, 0x%lx, 0x%x)\n", addr, len, prot);

    if(prot & PROT_WRITE)
        prot |= PROT_READ;

    errno = 0;
    int ret = mprotect(addr, len, prot);
    int saved_errno = ret ? errno : 0;

    if(ret && saved_errno == EACCES && len &&
       (prot & PROT_EXEC) && !(prot & PROT_WRITE))
    {
        uintptr_t start = (uintptr_t)addr;
        uintptr_t end = start + len;
        long page_size = sysconf(_SC_PAGESIZE);
        int copyable = page_size > 0 && end >= start;

        for(uintptr_t p = start; copyable && p < end; p += page_size)
        {
            int oldprot = getProtection(p) & ~PROT_CUSTOM;
            if((oldprot & (PROT_READ | PROT_WRITE)) !=
               (PROT_READ | PROT_WRITE))
                copyable = 0;
        }

        if(copyable)
        {
            void *backup = malloc(len);

            if(backup)
            {
                memcpy(backup, addr, len);

                #ifdef DYNAREC
                cleanDBFromAddressRange(start, len, 1);
                #endif

                errno = 0;
                void *mapped = my_mmap64(
                    emu,
                    addr,
                    len,
                    PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED,
                    -1,
                    0
                );

                if(mapped == addr)
                {
                    memcpy(addr, backup, len);

                    errno = 0;
                    ret = mprotect(addr, len, prot);
                    saved_errno = ret ? errno : 0;

                    if(!ret)
                        fprintf(stderr,
                            "[BOX64_EXECMOD_FALLBACK] success "
                            "addr=%p len=0x%lx prot=0x%x\n",
                            addr, len, prot);
                    else
                        fprintf(stderr,
                            "[BOX64_EXECMOD_FALLBACK] final mprotect failed "
                            "errno=%d (%s)\n",
                            saved_errno, strerror(saved_errno));
                }
                else
                {
                    ret = -1;
                    saved_errno = errno ? errno : ENOMEM;

                    fprintf(stderr,
                        "[BOX64_EXECMOD_FALLBACK] anonymous remap failed "
                        "errno=%d (%s)\n",
                        saved_errno, strerror(saved_errno));
                }

                free(backup);
            }
            else
            {
                ret = -1;
                saved_errno = ENOMEM;
            }
        }
    }

    if(!ret && len)
        updateProtection((uintptr_t)addr, len, prot);

    errno = saved_errno;
    return ret;
}
'''

new_text = text[:start] + replacement + text[end:]

expected = 'printf_log(LOG_NONE, "mprotect(%p, 0x%lx, 0x%x)\\n", addr, len, prot);'
if expected not in new_text:
    raise SystemExit("escaped newline validation failed")

path.write_text(new_text)
print("PATCHED_V3")
PY

echo "=== SOURCE CHECK ==="
sed -n '3747,3770p' src/wrapped/wrappedlibc.c

echo "=== BUILD ==="
cmake --build build -j4

cat >/tmp/dirty_execmod_test.c <<'EOF'
#define _GNU_SOURCE
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

static void run_test(const char *path, int dirty)
{
    const uintptr_t reserve_addr = 0x7ffff00000ULL;
    const uintptr_t target_addr  = 0x7ffff41000ULL;
    const size_t reserve_len = 0x100000;
    const size_t len = 0x74000;
    const off_t offset = 0x1000;

    errno = 0;
    void *reserve = mmap((void *)reserve_addr, reserve_len,
                         PROT_NONE,
                         MAP_PRIVATE | MAP_ANONYMOUS |
                         MAP_FIXED_NOREPLACE,
                         -1, 0);

    if (reserve == MAP_FAILED) {
        printf("reserve failed: %d (%s)\n", errno, strerror(errno));
        return;
    }

    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        printf("open failed: %s\n", strerror(errno));
        munmap(reserve, reserve_len);
        return;
    }

    errno = 0;
    void *p = mmap((void *)target_addr, len,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_FIXED,
                   fd, offset);

    printf("\nMODE=%s\n", dirty ? "DIRTY" : "CLEAN");
    printf("MMAP=%p errno=%d (%s)\n", p, errno, strerror(errno));

    if (p != MAP_FAILED) {
        if (dirty) {
            volatile unsigned char *b = p;
            unsigned char old = b[0];
            b[0] = old ^ 1;
            b[0] = old;
            printf("PAGE_MODIFIED=YES\n");
        }

        errno = 0;
        int r = mprotect(p, len, PROT_READ | PROT_EXEC);
        printf("MPROTECT=%d errno=%d (%s)\n",
               r, errno, strerror(errno));
    }

    close(fd);
    munmap((void *)reserve_addr, reserve_len);
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    run_test(argv[1], 0);
    run_test(argv[1], 1);
    return 0;
}
EOF

x86_64-linux-gnu-gcc -O2 /tmp/dirty_execmod_test.c \
  -o /tmp/dirty_execmod_test_x64

FILETEST=/opt/mobox/wine-9.3-vanilla-wow64/lib/wine/x86_64-windows/ntdll.dll

export BOX64_NORCFILES=1
export BOX64_LOG=0
export BOX64_LD_LIBRARY_PATH="/usr/x86_64-linux-gnu/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/opt/mobox/lib/x86_64-linux-gnu"

echo "=== DIRTY EXECMOD FALLBACK TEST ==="
build/box64 /tmp/dirty_execmod_test_x64 "$FILETEST"
DEBIAN

echo
echo "RESULT_LOG=$OUT"
