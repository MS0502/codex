#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v18_patch as v18


REVISION = "v18b-proton11-valve-glibc-1"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v18b(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat18-proton11-unified"',
        'versionName "11.1-trcompat18b-proton11-valve-glibc"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v18_PROTON11.zip": "TR_DIAG_v18B_PROTON11_GLIBC.zip",
        "DIAGNOSTICS_RESET version=18-proton11-unified":
            "DIAGNOSTICS_RESET version=18b-proton11-valve-glibc",
        "TalesRunner KR XIGNCODE fingerprint v18 Proton 11 unified":
            "TalesRunner KR XIGNCODE fingerprint v18b Valve Proton 11 glibc",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"v18b diagnostics anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")
    old_revision = 'private static final String REVISION = "v18-proton11-unified-1";'
    if old_revision not in text:
        raise RuntimeError("v18 Wine runtime revision anchor not found")
    text = text.replace(
        old_revision,
        f'private static final String REVISION = "{REVISION}";',
        1,
    )
    text = text.replace(".trcompat-v18.tmp", ".trcompat-v18b.tmp")
    patcher.write_text(text, encoding="utf-8")

    rootfs_patcher = root / "app/src/main/java/com/winlator/core/TrCompatRootfsPatcher.java"
    text = rootfs_patcher.read_text(encoding="utf-8")
    if old_revision not in text:
        raise RuntimeError("v18 rootfs runtime revision anchor not found")
    text = text.replace(
        old_revision,
        f'private static final String REVISION = "{REVISION}";',
        1,
    )
    text = text.replace(".trcompat-v18.tmp", ".trcompat-v18b.tmp")
    rootfs_patcher.write_text(text, encoding="utf-8")

    old_report = root / "v18-proton-rootfs-report.txt"
    if not old_report.is_file():
        raise RuntimeError("v18 rootfs report not found")
    report_text = old_report.read_text(encoding="utf-8")
    report_text = report_text.replace(
        "revision=v18-proton11-unified-1",
        f"revision={REVISION}",
        1,
    )
    report_text += "runtime_source=ValveSoftware/Proton proton-11.0-1-beta5 glibc x86_64\n"
    (root / "v18b-proton-rootfs-report.txt").write_text(report_text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: apply_v18b_patch.py WINLATOR_APP_DIR PROTON_WINE_TREE PROTON_COMPONENT_DIR",
            file=sys.stderr,
        )
        return 2

    root = Path(sys.argv[1]).resolve()
    saved_argv = sys.argv[:]
    try:
        sys.argv = [
            str(Path(v18.__file__).resolve()),
            saved_argv[1],
            saved_argv[2],
            saved_argv[3],
        ]
        result = v18.main()
    finally:
        sys.argv = saved_argv
    if result != 0:
        return result

    patch_v18b(root)
    print("Winlator TR Compat v18b Valve Proton 11 glibc runtime applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
