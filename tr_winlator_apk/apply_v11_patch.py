#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v10_patch as v10


REVISION = "v11-main-wine-token-1"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v11(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat10"',
        'versionName "11.1-trcompat11"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v10.zip": "TR_DIAG_v11.zip",
        "DIAGNOSTICS_RESET version=10": "DIAGNOSTICS_RESET version=11",
        "TalesRunner KR XIGNCODE fingerprint v10": "TalesRunner KR XIGNCODE fingerprint v11",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v11 anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")

    old_revision = 'private static final String REVISION = "v10-official-runtime-token-1";'
    if old_revision not in text:
        raise RuntimeError("v10 Wine runtime revision anchor not found")
    text = text.replace(
        old_revision,
        f'private static final String REVISION = "{REVISION}";',
        1,
    )

    old_gate = '''        if (winePath == null || !winePath.contains("wine-10.10-trcompat")) {
            TrCompatDiagnostics.trace("WINE_RUNTIME_PATCH_SKIP winePath="+String.valueOf(winePath));
            return;
        }
'''
    new_gate = '''        if (winePath == null) {
            TrCompatDiagnostics.trace("WINE_RUNTIME_PATCH_SKIP winePath=null");
            return;
        }
        boolean supportedWine = "/opt/wine".equals(winePath) || winePath.contains("wine-10.10-trcompat");
        if (!supportedWine) {
            TrCompatDiagnostics.trace("WINE_RUNTIME_PATCH_SKIP_UNSUPPORTED winePath="+winePath);
            return;
        }
        TrCompatDiagnostics.trace("WINE_RUNTIME_PATCH_TARGET winePath="+winePath);
'''
    if old_gate not in text:
        raise RuntimeError("Wine path gate anchor not found")
    text = text.replace(old_gate, new_gate, 1)
    text = text.replace(".trcompat-v10.tmp", ".trcompat-v11.tmp")
    patcher.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v11_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v10.__file__).resolve()), str(root), str(component_dir)]
        result = v10.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_v11(root)
    print("Winlator TR Compat v11 main /opt/wine TokenPrivateNameSpace repair applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
