#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import apply_v9_patch as v9


def patch_rootfs_archive_unique(root: Path) -> tuple[int, int, int, str]:
    archive = root / "app/src/main/assets/rootfs.tzst"
    if not archive.is_file():
        raise RuntimeError(f"missing rootfs archive: {archive}")

    with tempfile.TemporaryDirectory(prefix="tr-v9-rootfs-") as temp_name:
        temp = Path(temp_name)
        tree = temp / "tree"
        tree.mkdir()
        v9.run("tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(tree))
        scanned, files, occurrences = v9.patch_tree(tree)

        # Count unique physical archive entries. The earlier 300/800 threshold came
        # from a scan that followed symlink aliases and counted the same ELF several
        # times. The pinned Winlator 11.1 rootfs has 165 unique files and 447 byte
        # occurrences containing the original package root path.
        if files < 150 or occurrences < 400:
            raise RuntimeError(
                f"unexpected unique rootfs path coverage: scanned={scanned} "
                f"files={files} occurrences={occurrences}"
            )
        v9.repack_tzst(tree, archive, "rootfs-v9.tar")

    digest = v9.sha256(archive)
    print(
        f"rootfs v9 unique patch scanned={scanned} patched_files={files} "
        f"occurrences={occurrences} sha256={digest}"
    )
    return scanned, files, occurrences, digest


def main() -> int:
    v9.patch_rootfs_archive = patch_rootfs_archive_unique
    return v9.main()


if __name__ == "__main__":
    raise SystemExit(main())
