#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v9_patch as v9
import apply_v9_fixed_patch as v9_fixed


REVISION = "v10-official-runtime-token-1"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_versions(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat9"',
        'versionName "11.1-trcompat10"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v9.zip": "TR_DIAG_v10.zip",
        "DIAGNOSTICS_RESET version=9": "DIAGNOSTICS_RESET version=10",
        "TalesRunner KR XIGNCODE fingerprint v9": "TalesRunner KR XIGNCODE fingerprint v10",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v10 anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")
    if 'private static final String REVISION = "v8-wine-rootfs-path-1";' not in text:
        raise RuntimeError("Wine runtime revision anchor not found")
    text = text.replace(
        'private static final String REVISION = "v8-wine-rootfs-path-1";',
        f'private static final String REVISION = "{REVISION}";',
        1,
    )
    text = text.replace('.trcompat-v8.tmp', '.trcompat-v10.tmp')
    patcher.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v10_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    # The pinned rootfs contains 165 unique physical files and 447 occurrences.
    # Use the corrected unique-file validator while retaining the complete v9
    # rootfs alias, Box64, sync and X-server fixes.
    v9.patch_rootfs_archive = v9_fixed.patch_rootfs_archive_unique

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v9.__file__).resolve()), str(root), str(component_dir)]
        result = v9.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_versions(root)

    print("Winlator TR Compat v10 official-runtime TokenPrivateNameSpace build applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
