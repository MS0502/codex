#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v11_patch as v11


REVISION = "v12-official-baseline-1"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v12(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat11"',
        'versionName "11.1-trcompat12-baseline"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v11.zip": "TR_DIAG_v12_BASELINE.zip",
        "DIAGNOSTICS_RESET version=11": "DIAGNOSTICS_RESET version=12-baseline",
        "TalesRunner KR XIGNCODE fingerprint v11": "TalesRunner KR XIGNCODE fingerprint v12 baseline",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v12 anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")

    old_revision = 'private static final String REVISION = "v11-main-wine-token-1";'
    if old_revision not in text:
        raise RuntimeError("v11 Wine runtime revision anchor not found")
    text = text.replace(
        old_revision,
        f'private static final String REVISION = "{REVISION}";',
        1,
    )
    text = text.replace(".trcompat-v11.tmp", ".trcompat-v12.tmp")
    patcher.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v12_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v11.__file__).resolve()), str(root), str(component_dir)]
        result = v11.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_v12(root)
    print("Winlator TR Compat v12 official Wine baseline applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
