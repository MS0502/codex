#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path


ALIASES = {
    "libudev.so.0": "libudev.so.1",
    "libXinerama.so": "libXinerama.so.1",
}
ROOT_LIBRARIES = (
    "libudev.so.1",
    "libusb-1.0.so.0",
    "libXinerama.so.1",
    "libdbus-1.so.3",
)
REQUIRED_NAMES = ROOT_LIBRARIES + tuple(ALIASES)
CORE_LIBRARIES = {
    "ld-linux-aarch64.so.1",
    "libc.so.6",
    "libdl.so.2",
    "libm.so.6",
    "libpthread.so.0",
    "librt.so.1",
    "libgcc_s.so.1",
    "libresolv.so.2",
}
NEEDED_RE = re.compile(r"Shared library: \[([^\]]+)\]")
MACHINE_RE = re.compile(r"Machine:\s+AArch64")


def merge_tree(source_root: Path, target_root: Path) -> None:
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        target = target_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, target)


def is_aarch64_elf(path: Path) -> bool:
    try:
        output = subprocess.check_output(
            ["readelf", "-h", str(path)], text=True, errors="replace"
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(MACHINE_RE.search(output))


def needed(path: Path) -> list[str]:
    output = subprocess.check_output(
        ["readelf", "-d", str(path)], text=True, errors="replace"
    )
    return NEEDED_RE.findall(output)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: v18j_overlay_rootfs.py ROOTFS OVERLAY REPORT", file=sys.stderr)
        return 2

    root = Path(sys.argv[1])
    overlay = Path(sys.argv[2])
    report_path = Path(sys.argv[3])
    if not root.is_dir() or not overlay.is_dir():
        raise SystemExit("rootfs or overlay directory is missing")

    merge_tree(overlay, root)

    native_dirs = [
        root / "usr/lib/aarch64-linux-gnu",
        root / "lib/aarch64-linux-gnu",
        root / "usr/lib64",
        root / "lib64",
    ]
    native_dirs = [path for path in native_dirs if path.is_dir()]
    if not native_dirs:
        raise SystemExit("no ARM64 native library directories found")

    primary = root / "usr/lib/aarch64-linux-gnu"
    if not primary.is_dir():
        raise SystemExit(f"missing primary ARM64 library directory: {primary}")

    alias_rows: list[str] = []
    for alias, soname in ALIASES.items():
        source = primary / soname
        if not source.exists():
            raise SystemExit(f"missing native wrapper target: {source}")
        target = primary / alias
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(source.name)
        alias_rows.append(f"{target.relative_to(root)} -> {source.name}")

    resolved: dict[str, str] = {}
    for soname in REQUIRED_NAMES:
        candidates = [directory / soname for directory in native_dirs]
        path = next(
            (candidate for candidate in candidates if candidate.exists() or candidate.is_symlink()),
            None,
        )
        if path is None:
            raise SystemExit(f"v18j rootfs missing ARM64 provider: {soname}")
        resolved[soname] = str(path.relative_to(root))

    providers: dict[str, list[Path]] = {}
    for directory in native_dirs:
        for path in directory.rglob("*"):
            if not (path.is_file() or path.is_symlink()):
                continue
            try:
                real = path.resolve(strict=True)
            except OSError:
                continue
            if not is_aarch64_elf(real):
                continue
            providers.setdefault(path.name, []).append(path)

    queue = deque(ROOT_LIBRARIES)
    audited: set[str] = set()
    audit_rows: list[str] = []
    unresolved: dict[str, list[str]] = {}

    while queue:
        soname = queue.popleft()
        if soname in audited or soname in CORE_LIBRARIES:
            continue
        audited.add(soname)
        paths = providers.get(soname, [])
        if not paths:
            unresolved[soname] = ["provider_missing"]
            audit_rows.append(f"{soname} provider=missing")
            continue
        path = sorted(paths)[0]
        direct = needed(path)
        missing: list[str] = []
        for dependency in direct:
            if dependency in CORE_LIBRARIES:
                continue
            if dependency not in providers:
                missing.append(dependency)
            else:
                queue.append(dependency)
        audit_rows.append(
            f"{soname} path={path.relative_to(root)} needed={direct} "
            f"unresolved={sorted(missing)}"
        )
        if missing:
            unresolved[soname] = sorted(missing)

    report = "\n".join(
        [
            "revision=v18j-proton11-native-wrapper-overlay-4",
            "base_run=29679424111",
            *[f"alias={row}" for row in alias_rows],
            *[f"resolved_{name}={path}" for name, path in sorted(resolved.items())],
            *audit_rows,
            f"unresolved={unresolved}",
            "",
        ]
    )
    print(report)
    report_path.write_text(report, encoding="utf-8")
    if unresolved:
        raise SystemExit(f"ARM64 native dependency closure incomplete: {unresolved}")

    marker = root / "etc/trcompat-v18j-native-wrapper-closure"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("v18j-proton11-native-wrapper-overlay-4\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
