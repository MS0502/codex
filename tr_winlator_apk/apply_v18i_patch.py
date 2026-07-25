#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_v18b_patch as v18b


REVISION = "v18i-proton11-runtime-closure-1"
CRITICAL_MODULES = {"winebus.so", "winepulse.so", "wineusb.so", "nsiproxy.so"}
CORE_BOX64_LIBS = {
    "ld-linux-x86-64.so.2",
    "libc.so.6",
    "libdl.so.2",
    "libm.so.6",
    "libpthread.so.0",
    "librt.so.1",
    "libgcc_s.so.1",
}


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=True)


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def repack_tzst(tree: Path, output: Path, tar_name: str) -> None:
    tar_path = tree.parent / tar_name
    run(
        "tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner",
        "--mtime=@0", "--format=gnu", "-C", str(tree), "-cf", str(tar_path), ".",
    )
    run("zstd", "-19", "-f", str(tar_path), "-o", str(output))


def read_needed(path: Path) -> list[str]:
    output = subprocess.check_output(["readelf", "-d", str(path)], text=True, errors="replace")
    return re.findall(r"Shared library: \[([^\]]+)\]", output)


def collect_basenames(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.rglob("*"):
        if path.is_file() or path.is_symlink():
            names.add(path.name)
    return names


def validate_symlink(path: Path) -> None:
    if not path.is_symlink():
        return
    target = os.readlink(path)
    if os.path.isabs(target):
        # Absolute package symlinks are resolved inside the extracted rootfs by the
        # device runtime. Presence of the final SONAME is validated separately.
        return
    resolved = (path.parent / target).resolve()
    if not resolved.exists():
        raise RuntimeError(f"broken runtime symlink: {path} -> {target}")


def patch_rootfs_archive(root: Path, proton_root: Path, native_runtime: Path) -> str:
    archive = root / "app/src/main/assets/rootfs.tzst"
    if not archive.is_file():
        raise RuntimeError(f"missing rootfs archive: {archive}")
    if not native_runtime.is_dir():
        raise RuntimeError(f"missing native runtime tree: {native_runtime}")

    with tempfile.TemporaryDirectory(prefix="tr-v18i-rootfs-") as temp_name:
        temp = Path(temp_name)
        tree = temp / "tree"
        tree.mkdir()
        run("tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(tree))

        shutil.copytree(native_runtime, tree, dirs_exist_ok=True, symlinks=True)

        required = ("libudev.so.1", "libusb-1.0.so.0")
        resolved: dict[str, list[str]] = {}
        for soname in required:
            matches = sorted(
                path for path in tree.rglob(soname)
                if path.is_file() or path.is_symlink()
            )
            if not matches:
                raise RuntimeError(f"rootfs runtime closure missing {soname}")
            for match in matches:
                validate_symlink(match)
            resolved[soname] = [str(path.relative_to(tree)) for path in matches]

        (tree / "etc").mkdir(parents=True, exist_ok=True)
        (tree / "var/lib/dbus").mkdir(parents=True, exist_ok=True)
        # The Java first-run patcher generates one persistent ID per app/rootfs install.
        for stale in (tree / "etc/machine-id", tree / "var/lib/dbus/machine-id"):
            if stale.exists() or stale.is_symlink():
                stale.unlink()

        providers = collect_basenames(tree) | collect_basenames(proton_root) | CORE_BOX64_LIBS
        unix_dir = proton_root / "lib/wine/x86_64-unix"
        rows: list[str] = []
        critical_unresolved: dict[str, list[str]] = {}
        optional_unresolved: dict[str, list[str]] = {}
        for module in sorted(unix_dir.glob("*.so")):
            needed = read_needed(module)
            unresolved = sorted(name for name in needed if name not in providers)
            rows.append(
                f"module={module.name} needed={','.join(needed)} "
                f"unresolved={','.join(unresolved)}"
            )
            if unresolved:
                target = critical_unresolved if module.name in CRITICAL_MODULES else optional_unresolved
                target[module.name] = unresolved

        if critical_unresolved:
            raise RuntimeError(f"critical Wine Unix dependencies unresolved: {critical_unresolved}")

        report_lines = [
            f"revision={REVISION}",
            "machine_id=generated_at_first_rootfs_start_and_persisted",
            *(f"resolved_{name}={','.join(paths)}" for name, paths in sorted(resolved.items())),
            f"critical_unresolved={critical_unresolved}",
            f"optional_unresolved={optional_unresolved}",
            "",
            *rows,
            "",
        ]
        report = "\n".join(report_lines)
        (root / "v18i-runtime-closure-report.txt").write_text(report, encoding="utf-8")
        repack_tzst(tree, archive, "rootfs-v18i.tar")
        return report


def patch_machine_id_runtime(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/core/TrCompatRootfsPatcher.java"
    replace_once(
        path,
        "import java.util.ArrayDeque;\n",
        "import java.util.ArrayDeque;\nimport java.util.UUID;\n",
    )
    replace_once(
        path,
        '''            ensureAlias(alias, root);\n            TrCompatDiagnostics.trace("ROOTFS_ALIAS path="+alias.getPath()+" target="+root.getPath());\n''',
        '''            ensureAlias(alias, root);\n            TrCompatDiagnostics.trace("ROOTFS_ALIAS path="+alias.getPath()+" target="+root.getPath());\n            ensureMachineId(root);\n''',
    )

    method = r'''    private static void ensureMachineId(File root) throws Exception {
        File etcDir = new File(root, "etc");
        File dbusDir = new File(root, "var/lib/dbus");
        if (!etcDir.isDirectory() && !etcDir.mkdirs()) {
            throw new java.io.IOException("unable to create "+etcDir.getPath());
        }
        if (!dbusDir.isDirectory() && !dbusDir.mkdirs()) {
            throw new java.io.IOException("unable to create "+dbusDir.getPath());
        }

        File primary = new File(etcDir, "machine-id");
        String machineId = readMachineId(primary);
        boolean generated = false;
        if (machineId == null) {
            machineId = UUID.randomUUID().toString().replace("-", "");
            writeMachineId(primary, machineId);
            generated = true;
        }

        File dbus = new File(dbusDir, "machine-id");
        String dbusId = readMachineId(dbus);
        if (!machineId.equals(dbusId)) writeMachineId(dbus, machineId);
        TrCompatDiagnostics.trace(
                "MACHINE_ID_READY generated="+generated+
                " primary="+primary.getPath()+" dbus="+dbus.getPath()+" length="+machineId.length()
        );
    }

    private static String readMachineId(File file) {
        try {
            if (!file.isFile()) return null;
            String value = new String(Files.readAllBytes(file.toPath()), StandardCharsets.US_ASCII).trim();
            return value.matches("[0-9a-f]{32}") ? value : null;
        }
        catch (Throwable ignored) { return null; }
    }

    private static void writeMachineId(File file, String value) throws Exception {
        File temp = new File(file.getPath()+".trcompat-v18i.tmp");
        if (temp.exists() && !temp.delete()) {
            throw new java.io.IOException("unable to remove temp "+temp.getPath());
        }
        try (FileOutputStream output = new FileOutputStream(temp, false)) {
            output.write((value+"\n").getBytes(StandardCharsets.US_ASCII));
            output.flush();
        }
        Os.chmod(temp.getPath(), 0644);
        Os.rename(temp.getPath(), file.getPath());
    }

'''
    replace_once(
        path,
        "    private static void ensureAlias(File alias, File root) throws Exception {\n",
        method + "    private static void ensureAlias(File alias, File root) throws Exception {\n",
    )


def patch_versions(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat18b-proton11-valve-glibc"',
        'versionName "11.1-trcompat18i-proton11-runtime-closure"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v18B_PROTON11_GLIBC.zip": "TR_DIAG_v18I_PROTON11_RUNTIME_CLOSURE.zip",
        "DIAGNOSTICS_RESET version=18b-proton11-valve-glibc":
            "DIAGNOSTICS_RESET version=18i-proton11-runtime-closure",
        "TalesRunner KR XIGNCODE fingerprint v18b Valve Proton 11 glibc":
            "TalesRunner KR XIGNCODE fingerprint v18i Proton 11 runtime closure",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"v18i diagnostics anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    for relative in (
        "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java",
        "app/src/main/java/com/winlator/core/TrCompatRootfsPatcher.java",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        old = 'private static final String REVISION = "v18b-proton11-valve-glibc-1";'
        if old not in text:
            raise RuntimeError(f"v18i revision anchor not found: {path}")
        text = text.replace(old, f'private static final String REVISION = "{REVISION}";', 1)
        text = text.replace(".trcompat-v18b.tmp", ".trcompat-v18i.tmp")
        path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: apply_v18i_patch.py WINLATOR_APP_DIR PROTON_WINE_TREE "
            "PROTON_COMPONENT_DIR NATIVE_RUNTIME_DIR",
            file=sys.stderr,
        )
        return 2

    root = Path(sys.argv[1]).resolve()
    proton_root = Path(sys.argv[2]).resolve()
    component_dir = Path(sys.argv[3]).resolve()
    native_runtime = Path(sys.argv[4]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [
            str(Path(v18b.__file__).resolve()),
            saved_argv[1],
            saved_argv[2],
            saved_argv[3],
        ]
        result = v18b.main()
    finally:
        sys.argv = saved_argv
    if result != 0:
        return result

    report = patch_rootfs_archive(root, proton_root, native_runtime)
    patch_machine_id_runtime(root)
    patch_versions(root)
    print(report)
    print("Winlator TR Compat v18i runtime closure applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
