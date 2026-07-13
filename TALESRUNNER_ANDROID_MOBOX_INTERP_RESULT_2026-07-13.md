# TalesRunner Android Mobox — Box64 interpreter comparison result

Date: 2026-07-13

## Scope

Normal Wine/Box64 compatibility diagnosis only.

- No XIGNCODE bypass.
- No executable patching.
- No security component disabling.
- No memory protection override.

## Interpreter test

The test ran with:

```text
MODE=interp
BOX64_DYNAREC=0
```

The same access violation observed with DynaRec was reproduced exactly:

```text
code=c0000005 (EXCEPTION_ACCESS_VIOLATION)
rip=0000000140243d68
info[0]=0000000000000001
info[1]=0000000281140048
handler=000000014024D790
```

Register values around the fault also matched the DynaRec run, including:

```text
rdx=0000000281140040
rdi=0000000281140000
r10=0000000281140000
```

## Process map confirmation

The captured `talesrunner.exe` process map identified the write target as the first page of Wine's Windows `ntdll.dll` image:

```text
281140000-281141000 r--p .../wine/x86_64-windows/ntdll.dll
281141000-2811b5000 r-xp
```

Therefore address `0x281140048` is `ntdll.dll` image base plus offset `0x48`, inside its read-only PE header page.

The faulting instruction is inside the mapped TalesRunner image:

```text
140000000-140001000 r--p
140001000-140077000 r-xp
...
140220000-1411f0000 rwxp
```

## Conclusion

1. Box64 DynaRec is not the cause. The interpreter reproduces the exact same fault.
2. The game attempts to write to Wine `ntdll.dll` PE-header memory at `ntdll_base + 0x48`.
3. That page is still mapped read-only when the write occurs.
4. TalesRunner's own vectored exception handler receives the fault and produces the Security Error path.
5. No `xldr_TalesRunner_KR_loader_x64.exe` or separate XIGNCODE process appears before this failure.

## Next diagnostic

Run `MOBOX_TR_NTDLL_PROTECT_TRACE.sh`.

The script enables Wine's `virtual` and `seh` debug channels and records whether TalesRunner requested a protection change for the `ntdll.dll` header before writing it. It only traces behavior and does not modify protection or bypass the security path.

Expected output:

```text
~/storage/downloads/TR_KR_LOCAL/MOBOX_TR_NTDLL_PROTECT_TRACE_SANITIZED.txt
```

Decision:

- A protection request is logged but fails or does not change the map: investigate Wine/Android image-protection compatibility.
- No protection request is logged: the game intentionally writes directly to a read-only image header and rejects Wine at its own initialization layer.
- The request succeeds but the page remains read-only: investigate Wine 9.3 mapping/protection implementation and compare a newer unmodified Wine build.
