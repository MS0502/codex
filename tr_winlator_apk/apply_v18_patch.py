#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_v12_patch as v12
import apply_v9_patch as v9


REVISION = "v18-proton11-unified-1"
OLD_ROOT = b"/data/data/com.winlator/files/rootfs"
ALIAS_ROOT = b"/data/user/0/com.winlator.trcompat/r"
ANDROID_ROOT_PATTERN = re.compile(rb"/data/(?:data|user/0)/[A-Za-z0-9._-]+/files/rootfs")


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def validate_proton_tree(proton_root: Path) -> None:
    required = (
        "bin/wine",
        "bin/wineserver",
        "lib/wine/x86_64-unix/ntdll.so",
        "lib/wine/x86_64-windows/wow64.dll",
        "lib/wine/x86_64-unix/nsiproxy.so",
        "lib/wine/x86_64-windows/ntoskrnl.exe",
    )
    missing = [relative for relative in required if not (proton_root / relative).is_file()]
    if missing:
        raise RuntimeError(f"Proton Wine tree is incomplete: {missing}")


def find_embedded_android_roots(tree: Path) -> set[bytes]:
    found: set[bytes] = set()
    for path in sorted(tree.rglob("*")):
        if path.is_symlink():
            target = os.readlink(path).encode("utf-8", errors="ignore")
            found.update(ANDROID_ROOT_PATTERN.findall(target))
            continue
        if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        found.update(ANDROID_ROOT_PATTERN.findall(data))
    return found


def replace_rootfs_wine(root: Path, proton_root: Path) -> tuple[int, int, int, str]:
    archive = root / "app/src/main/assets/rootfs.tzst"
    if not archive.is_file():
        raise RuntimeError(f"missing rootfs archive: {archive}")

    validate_proton_tree(proton_root)
    embedded = find_embedded_android_roots(proton_root)
    unsupported = sorted(value for value in embedded if value not in {OLD_ROOT, ALIAS_ROOT})
    if unsupported:
        decoded = [value.decode("utf-8", errors="replace") for value in unsupported]
        raise RuntimeError(f"Proton Wine contains unsupported fixed Android rootfs paths: {decoded}")

    with tempfile.TemporaryDirectory(prefix="tr-v18-rootfs-") as temp_name:
        temp = Path(temp_name)
        tree = temp / "tree"
        tree.mkdir()
        run("tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(tree))

        destination = tree / "opt/wine"
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            else:
                shutil.rmtree(destination)
        shutil.copytree(proton_root, destination, symlinks=True)

        scanned, patched_files, occurrences = v9.patch_tree(destination)
        remaining = find_embedded_android_roots(destination)
        unsupported_remaining = sorted(value for value in remaining if value != ALIAS_ROOT)
        if unsupported_remaining:
            decoded = [value.decode("utf-8", errors="replace") for value in unsupported_remaining]
            raise RuntimeError(f"unrelocated Proton Wine Android rootfs paths remain: {decoded}")

        v9.repack_tzst(tree, archive, "rootfs-v18-proton11.tar")

    digest = sha256(archive)
    print(
        "Proton Wine rootfs replacement "
        f"scanned={scanned} patched_files={patched_files} occurrences={occurrences} sha256={digest}"
    )
    return scanned, patched_files, occurrences, digest


def patch_v18(root: Path, report: tuple[int, int, int, str]) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat12-baseline"',
        'versionName "11.1-trcompat18-proton11-unified"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v12_BASELINE.zip": "TR_DIAG_v18_PROTON11.zip",
        "DIAGNOSTICS_RESET version=12-baseline": "DIAGNOSTICS_RESET version=18-proton11-unified",
        "TalesRunner KR XIGNCODE fingerprint v12 baseline": "TalesRunner KR XIGNCODE fingerprint v18 Proton 11 unified",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v18 anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")
    old_revision = 'private static final String REVISION = "v12-official-baseline-1";'
    if old_revision not in text:
        raise RuntimeError("v12 Wine runtime revision anchor not found")
    text = text.replace(
        old_revision,
        f'private static final String REVISION = "{REVISION}";',
        1,
    )
    text = text.replace(".trcompat-v12.tmp", ".trcompat-v18.tmp")
    patcher.write_text(text, encoding="utf-8")

    rootfs_patcher = root / "app/src/main/java/com/winlator/core/TrCompatRootfsPatcher.java"
    text = rootfs_patcher.read_text(encoding="utf-8")
    text = text.replace(
        'private static final String REVISION = "v9-full-rootfs-alias-1";',
        f'private static final String REVISION = "{REVISION}";',
        1,
    )
    text = text.replace(".trcompat-v9.tmp", ".trcompat-v18.tmp")
    rootfs_patcher.write_text(text, encoding="utf-8")

    wine_info = root / "app/src/main/java/com/winlator/core/WineInfo.java"
    text = wine_info.read_text(encoding="utf-8")
    if 'public static final String MAIN_WINE_VERSION = "10.10";' not in text:
        raise RuntimeError("main Wine version anchor not found")
    text = text.replace(
        'public static final String MAIN_WINE_VERSION = "10.10";',
        'public static final String MAIN_WINE_VERSION = "11.0";',
        1,
    )
    text = text.replace(
        '        if (identifier.equals(MAIN_WINE_INFO.identifier())) return MAIN_WINE_INFO;\n',
        '        if (identifier.equals(MAIN_WINE_INFO.identifier()) || identifier.equals("wine-10.10-custom")) return MAIN_WINE_INFO;\n',
        1,
    )
    text = text.replace(
        '        return wineVersion == null ||wineVersion.equals(MAIN_WINE_INFO.identifier());\n',
        '        return wineVersion == null || wineVersion.equals(MAIN_WINE_INFO.identifier()) || wineVersion.equals("wine-10.10-custom");\n',
        1,
    )
    wine_info.write_text(text, encoding="utf-8")

    report_path = root / "v18-proton-rootfs-report.txt"
    report_path.write_text(
        f"revision={REVISION}\n"
        f"proton_tree_scanned={report[0]}\n"
        f"proton_tree_patched_files={report[1]}\n"
        f"proton_tree_alias_occurrences={report[2]}\n"
        f"rootfs_sha256={report[3]}\n",
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: apply_v18_patch.py WINLATOR_APP_DIR PROTON_WINE_TREE PROTON_COMPONENT_DIR",
            file=sys.stderr,
        )
        return 2

    root = Path(sys.argv[1]).resolve()
    proton_root = Path(sys.argv[2]).resolve()
    component_dir = Path(sys.argv[3]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v12.__file__).resolve()), str(root), str(component_dir)]
        result = v12.main()
    finally:
        sys.argv = saved_argv
    if result != 0:
        return result

    report = replace_rootfs_wine(root, proton_root)
    patch_v18(root, report)
    print("Winlator TR Compat v18 unified Proton Wine 11 runtime applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
