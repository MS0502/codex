#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def copy_group(
    rootfs: Path,
    prefix: Path,
    data: dict[str, list[str]],
    key: str,
    source: str,
) -> tuple[int, list[str]]:
    names = data.get(key)
    if not isinstance(names, list) or not names:
        raise RuntimeError(f"invalid or empty common DLL group: {key}")

    src_dir = rootfs / "opt/wine/lib/wine" / source
    dst_dir = prefix / ".wine/drive_c/windows" / key
    if not src_dir.is_dir() or not dst_dir.is_dir():
        raise RuntimeError(f"missing source or destination: {src_dir} -> {dst_dir}")

    copied = 0
    missing: list[str] = []
    for name in names:
        if not isinstance(name, str) or not name:
            raise RuntimeError(f"invalid DLL name in {key}: {name!r}")
        src = src_dir / name
        dst = dst_dir / name
        if not src.is_file():
            # ContainerManager calls FileUtils.copy() without treating a false
            # return for an individual optional DLL as container-creation failure.
            missing.append(name)
            continue
        shutil.copy2(src, dst)
        copied += 1
    return copied, missing


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: materialize_main_wine_container.py ROOTFS PREFIX COMMON_DLLS_JSON", file=sys.stderr)
        return 2

    rootfs = Path(sys.argv[1]).resolve()
    prefix = Path(sys.argv[2]).resolve()
    common = Path(sys.argv[3]).resolve()
    data = json.loads(common.read_text(encoding="utf-8"))

    system32, system32_missing = copy_group(
        rootfs, prefix, data, "system32", "x86_64-windows"
    )
    syswow64, syswow64_missing = copy_group(
        rootfs, prefix, data, "syswow64", "i386-windows"
    )

    required = [
        prefix / ".wine/drive_c/windows/system32/kernel32.dll",
        prefix / ".wine/drive_c/windows/system32/ntdll.dll",
        prefix / ".wine/drive_c/windows/system32/explorer.exe",
        prefix / ".wine/drive_c/windows/syswow64/kernel32.dll",
    ]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"materialized runtime file missing: {path}")

    print(f"system32_copied={system32}")
    print(f"system32_optional_missing={','.join(system32_missing)}")
    print(f"syswow64_copied={syswow64}")
    print(f"syswow64_optional_missing={','.join(syswow64_missing)}")
    for path in required:
        print(f"verified={path.relative_to(prefix)} size={path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
