#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_v24_patch as v24


OLD_PACKAGE = b"com.winlator.trcompat"
NEW_PACKAGE = b"com.winlator.trforens"
OLD_PACKAGE_TEXT = OLD_PACKAGE.decode("ascii")
NEW_PACKAGE_TEXT = NEW_PACKAGE.decode("ascii")

if len(OLD_PACKAGE) != len(NEW_PACKAGE):
    raise RuntimeError("separate package relocation must preserve byte length")


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=True)


def patch_file(path: Path) -> int:
    data = path.read_bytes()
    count = data.count(OLD_PACKAGE)
    if count:
        path.write_bytes(data.replace(OLD_PACKAGE, NEW_PACKAGE))
    return count


def patch_tree(tree: Path) -> tuple[int, int]:
    patched_files = 0
    occurrences = 0
    for path in sorted(tree.rglob("*")):
        if path.is_symlink():
            target = os.readlink(path)
            count = target.count(OLD_PACKAGE_TEXT)
            if count:
                path.unlink()
                path.symlink_to(target.replace(OLD_PACKAGE_TEXT, NEW_PACKAGE_TEXT))
                patched_files += 1
                occurrences += count
            continue
        if not path.is_file():
            continue
        count = patch_file(path)
        if count:
            patched_files += 1
            occurrences += count
    return patched_files, occurrences


def repack_tzst(tree: Path, archive: Path, tar_name: str) -> None:
    tar_path = tree.parent / tar_name
    run(
        "tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner",
        "--mtime=@0", "--format=gnu", "-C", str(tree), "-cf", str(tar_path), "."
    )
    run("zstd", "-19", "-f", str(tar_path), "-o", str(archive))


def patch_tzst(archive: Path, label: str) -> tuple[int, int]:
    if not archive.is_file():
        raise RuntimeError(f"missing {label} archive: {archive}")
    with tempfile.TemporaryDirectory(prefix=f"tr-v25-{label}-") as temp_name:
        temp = Path(temp_name)
        tree = temp / "tree"
        tree.mkdir()
        run("tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(tree))
        files, occurrences = patch_tree(tree)
        residual_files, residual_occurrences = patch_tree(tree)
        if residual_files or residual_occurrences:
            raise RuntimeError(f"{label}: residual relocation markers remain")
        if occurrences:
            repack_tzst(tree, archive, f"{label}.tar")
        return files, occurrences


def patch_uncompressed_app_files(root: Path) -> tuple[int, int]:
    app = root / "app"
    patched_files = 0
    occurrences = 0
    skip_suffixes = {".tzst", ".zip", ".apk", ".idsig"}
    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() in skip_suffixes:
            continue
        count = patch_file(path)
        if count:
            patched_files += 1
            occurrences += count
    return patched_files, occurrences


def ensure_no_uncompressed_old_package(root: Path) -> None:
    skip_suffixes = {".tzst", ".zip", ".apk", ".idsig"}
    residual = []
    for path in sorted((root / "app").rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() in skip_suffixes:
            continue
        try:
            if OLD_PACKAGE in path.read_bytes():
                residual.append(str(path.relative_to(root)))
        except OSError:
            continue
    if residual:
        raise RuntimeError(f"old package remains in uncompressed app files: {residual[:20]}")


def patch_v25(root: Path) -> None:
    build = root / "app/build.gradle"
    build_text = build.read_text(encoding="utf-8")
    old_version = 'versionName "11.1-trcompat24-forensic"'
    new_version = 'versionName "11.1-trforens25-forensic"'
    if build_text.count(old_version) != 1:
        raise RuntimeError("v24 version anchor not found exactly once")
    build.write_text(build_text.replace(old_version, new_version, 1), encoding="utf-8")

    diagnostics = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    diagnostics_text = diagnostics.read_text(encoding="utf-8")
    diagnostic_replacements = {
        "TR_DIAG_v24_FORENSIC.zip": "TR_DIAG_v25_FORENSIC.zip",
        "DIAGNOSTICS_RESET version=24-forensic": "DIAGNOSTICS_RESET version=25-forensic-separate",
        "TalesRunner KR XIGNCODE fingerprint v24 forensic": "TalesRunner KR XIGNCODE fingerprint v25 forensic separate",
    }
    for old, new in diagnostic_replacements.items():
        if old not in diagnostics_text:
            raise RuntimeError(f"v25 diagnostic anchor missing: {old}")
        diagnostics_text = diagnostics_text.replace(old, new)
    diagnostics.write_text(diagnostics_text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    patcher_text = patcher.read_text(encoding="utf-8")
    old_revision = 'private static final String REVISION = "v24-current-build-forensic-1";'
    if patcher_text.count(old_revision) != 1:
        raise RuntimeError("v24 Wine revision anchor not found exactly once")
    patcher.write_text(
        patcher_text.replace(
            old_revision,
            'private static final String REVISION = "v25-separate-forensic-1";',
            1,
        ).replace(".trcompat-v24.tmp", ".trforens-v25.tmp"),
        encoding="utf-8",
    )

    source_files, source_occurrences = patch_uncompressed_app_files(root)

    strings = root / "app/src/main/res/values/strings.xml"
    strings_text = strings.read_text(encoding="utf-8")
    strings_text, label_count = re.subn(
        r'(<string\s+name="app_name">).*?(</string>)',
        r'\1Winlator TR Forensic\2',
        strings_text,
        count=1,
    )
    if label_count != 1:
        raise RuntimeError("app_name resource not found exactly once")
    strings.write_text(strings_text, encoding="utf-8")

    rootfs_files, rootfs_occurrences = patch_tzst(
        root / "app/src/main/assets/rootfs.tzst",
        "rootfs-v25",
    )
    if (rootfs_files, rootfs_occurrences) != (165, 447):
        raise RuntimeError(
            f"unexpected rootfs relocation coverage: files={rootfs_files} occurrences={rootfs_occurrences}"
        )

    box64_archives = sorted((root / "app/src/main/assets/box64").glob("box64-*.tzst"))
    if len(box64_archives) != 1:
        raise RuntimeError(f"expected one Box64 archive, found {box64_archives}")
    box64_files, box64_occurrences = patch_tzst(box64_archives[0], "box64-v25")
    if (box64_files, box64_occurrences) != (1, 2):
        raise RuntimeError(
            f"unexpected Box64 archive relocation coverage: files={box64_files} occurrences={box64_occurrences}"
        )

    ensure_no_uncompressed_old_package(root)

    report = root / "v25-package-relocation-report.txt"
    report.write_text(
        "\n".join(
            [
                f"old_package={OLD_PACKAGE_TEXT}",
                f"new_package={NEW_PACKAGE_TEXT}",
                f"byte_length={len(OLD_PACKAGE)}",
                f"uncompressed_patched_files={source_files}",
                f"uncompressed_occurrences={source_occurrences}",
                f"rootfs_patched_files={rootfs_files}",
                f"rootfs_occurrences={rootfs_occurrences}",
                f"box64_patched_files={box64_files}",
                f"box64_occurrences={box64_occurrences}",
            ]
        ) + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v25_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v24.__file__).resolve()), str(root), str(component_dir)]
        result = v24.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_v25(root)
    print("Winlator TR Forensic v25 separate-package diagnostics applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
