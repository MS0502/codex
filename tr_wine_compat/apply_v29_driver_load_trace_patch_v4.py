#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v29_driver_load_trace_patch as base

REVISION = "v29-generic-driver-load-trace-4"


def replace_once_in_function(path: Path, signature: str, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(signature) != 1:
        raise RuntimeError(f"expected one function signature: {signature}")
    start = text.index(signature)
    opening = text.index("{", start + len(signature))
    depth = 0
    end = None
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise RuntimeError(f"unterminated function: {signature}")
    block = text[start:end]
    if block.count(old) != 1:
        raise RuntimeError(f"expected one function-local anchor: {old!r}")
    block = block.replace(old, new, 1)
    path.write_text(text[:start] + block + text[end:], encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_v29_driver_load_trace_patch_v4.py WINE_SOURCE_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    saved = sys.argv[:]
    try:
        sys.argv = [str(Path(base.__file__).resolve()), str(root)]
        result = base.main()
    finally:
        sys.argv = saved
    if result != 0:
        return result

    source = root / "dlls/ntoskrnl.exe/ntoskrnl.c"
    replace_once_in_function(
        source,
        "NTSTATUS WINAPI ZwLoadDriver( const UNICODE_STRING *service_name )",
        "    SERVICE_STATUS_HANDLE service_handle;\n",
        "    SERVICE_STATUS_HANDLE service_handle = NULL;\n",
    )

    text = source.read_text(encoding="utf-8")
    if "SERVICE_STATUS_HANDLE service_handle = NULL;" not in text:
        raise RuntimeError("service handle initialization missing")
    for marker in (
        "DRIVER_LOAD ZwLoadDriver begin",
        "DRIVER_LOAD image-load return",
        "DRIVER_LOAD DriverEntry return",
        "DRIVER_LOAD IoCreateDevice created",
    ):
        if marker not in text:
            raise RuntimeError(f"missing trace marker: {marker}")
    for forbidden in ("xhunter", "xigncode", "wellbia", "6d4084", "talesrunner"):
        if forbidden in text.lower():
            raise RuntimeError(f"target-specific marker found: {forbidden}")

    print(f"Applied {REVISION}; service handle trace value is defined on all failure paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
