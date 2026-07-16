#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_v8_patch as v8

OLD_ROOT = b"/data/data/com.winlator/files/rootfs"
ALIAS_ROOT = b"/data/user/0/com.winlator.trcompat/r"
REVISION = "v9-full-rootfs-alias-1"

if len(OLD_ROOT) != len(ALIAS_ROOT):
    raise RuntimeError("rootfs alias must preserve byte length")


def run(*args: str, stdout=None) -> subprocess.CompletedProcess:
    print("+", " ".join(args))
    return subprocess.run(args, check=True, stdout=stdout)


def replace_once(path: Path, old: str, new: str) -> None:
    v8.replace_once(path, old, new)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_blob(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    count = data.count(OLD_ROOT)
    if count:
        path.write_bytes(data.replace(OLD_ROOT, ALIAS_ROOT))
    return (1 if count else 0, count)


def patch_tree(root: Path) -> tuple[int, int, int]:
    scanned = patched_files = occurrences = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            target = os.readlink(path)
            old = OLD_ROOT.decode("ascii")
            if old in target:
                path.unlink()
                path.symlink_to(target.replace(old, ALIAS_ROOT.decode("ascii")))
                patched_files += 1
                occurrences += target.count(old)
            continue
        if not path.is_file():
            continue
        scanned += 1
        changed, count = patch_blob(path)
        patched_files += changed
        occurrences += count
    return scanned, patched_files, occurrences


def repack_tzst(tree: Path, output: Path, tar_name: str) -> None:
    tar_path = tree.parent / tar_name
    run(
        "tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner",
        "--mtime=@0", "--format=gnu", "-C", str(tree), "-cf", str(tar_path), "."
    )
    run("zstd", "-19", "-f", str(tar_path), "-o", str(output))


def patch_rootfs_archive(root: Path) -> tuple[int, int, int, str]:
    archive = root / "app/src/main/assets/rootfs.tzst"
    if not archive.is_file():
        raise RuntimeError(f"missing rootfs archive: {archive}")

    with tempfile.TemporaryDirectory(prefix="tr-v9-rootfs-") as temp_name:
        temp = Path(temp_name)
        tree = temp / "tree"
        tree.mkdir()
        run("tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(tree))
        scanned, files, occurrences = patch_tree(tree)
        if files < 300 or occurrences < 800:
            raise RuntimeError(
                f"unexpected rootfs path coverage: scanned={scanned} files={files} occurrences={occurrences}"
            )
        repack_tzst(tree, archive, "rootfs-v9.tar")

    digest = sha256(archive)
    print(
        f"rootfs v9 patch scanned={scanned} patched_files={files} "
        f"occurrences={occurrences} sha256={digest}"
    )
    return scanned, files, occurrences, digest


def patch_box64_payloads(root: Path) -> tuple[int, str, str]:
    archives = sorted((root / "app/src/main/assets/box64").glob("box64-*.tzst"))
    if len(archives) != 1:
        raise RuntimeError(f"expected one Box64 archive, found {archives}")
    archive = archives[0]

    with tempfile.TemporaryDirectory(prefix="tr-v9-box64-") as temp_name:
        temp = Path(temp_name)
        tree = temp / "tree"
        tree.mkdir()
        run("tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(tree))
        box64 = tree / "usr/local/bin/box64"
        if not box64.is_file():
            raise RuntimeError("Box64 missing from archive")
        _, archive_occurrences = patch_blob(box64)
        if archive_occurrences < 1:
            raise RuntimeError("Box64 archive no longer contains expected original rootfs path")
        repack_tzst(tree, archive, "box64-v9.tar")

    native_box64 = root / "app/src/main/jniLibs/arm64-v8a/libtr_box64_exec.so"
    _, native_occurrences = patch_blob(native_box64)
    if native_occurrences < 1:
        raise RuntimeError("native Box64 no longer contains expected original rootfs path")

    archive_hash = sha256(archive)
    native_hash = sha256(native_box64)
    print(
        f"Box64 v9 alias patch archive_occurrences={archive_occurrences} "
        f"native_occurrences={native_occurrences} archive_sha256={archive_hash} "
        f"native_sha256={native_hash}"
    )
    return archive_occurrences + native_occurrences, archive_hash, native_hash


def patch_versions(root: Path) -> None:
    replace_once(root / "app/build.gradle", 'versionName "11.1-trcompat8"', 'versionName "11.1-trcompat9"')

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v8.zip": "TR_DIAG_v9.zip",
        "DIAGNOSTICS_RESET version=8": "DIAGNOSTICS_RESET version=9",
        "TalesRunner KR XIGNCODE fingerprint v8": "TalesRunner KR XIGNCODE fingerprint v9",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v9 anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")


def write_rootfs_runtime_patcher(root: Path) -> None:
    java = r'''package com.winlator.core;

import android.content.Context;
import android.system.Os;
import android.system.OsConstants;

import com.winlator.xenvironment.RootFS;

import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayDeque;

/**
 * Repairs ordinary absolute rootfs paths after using a separate Android package.
 * Replacement is byte-for-byte equal length, so ELF and cache offsets are preserved.
 */
public final class TrCompatRootfsPatcher {
    private static final String REVISION = "__REVISION__";
    private static final byte[] OLD = "/data/data/com.winlator/files/rootfs".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] ALIAS = "/data/user/0/com.winlator.trcompat/r".getBytes(StandardCharsets.US_ASCII);

    private TrCompatRootfsPatcher() {}

    public static void apply(Context context, RootFS rootFS) {
        File root = rootFS.getRootDir();
        File dataDir = new File(context.getApplicationInfo().dataDir);
        File alias = new File(dataDir, "r");
        File marker = new File(root, ".trcompat-rootfs-"+REVISION);

        try {
            ensureAlias(alias, root);
            TrCompatDiagnostics.trace("ROOTFS_ALIAS path="+alias.getPath()+" target="+root.getPath());

            if (marker.isFile()) {
                TrCompatDiagnostics.trace("ROOTFS_ALIAS_PATCH_ALREADY_CURRENT marker="+marker.getPath());
                return;
            }

            if (OLD.length != ALIAS.length) throw new java.io.IOException("alias length mismatch");
            int scanned = 0;
            int patchedFiles = 0;
            int occurrences = 0;

            File[] roots = {
                    new File(root, "bin"),
                    new File(root, "sbin"),
                    new File(root, "lib"),
                    new File(root, "usr"),
                    new File(root, "etc"),
                    new File(root, "var"),
                    new File(root, "opt/wine"),
                    new File(root, "opt/installed-wine/wine-10.10-trcompat")
            };

            for (File start : roots) {
                int[] result = patchTree(start);
                scanned += result[0];
                patchedFiles += result[1];
                occurrences += result[2];
            }

            try (FileOutputStream output = new FileOutputStream(marker, false)) {
                String report = REVISION+" scanned="+scanned+" patchedFiles="+patchedFiles+" occurrences="+occurrences+"\n";
                output.write(report.getBytes(StandardCharsets.UTF_8));
                output.flush();
            }
            TrCompatDiagnostics.trace(
                    "ROOTFS_ALIAS_PATCH_COMPLETE revision="+REVISION+
                    " scanned="+scanned+" patchedFiles="+patchedFiles+" occurrences="+occurrences
            );
        }
        catch (Throwable error) {
            TrCompatDiagnostics.traceThrowable("ROOTFS_ALIAS_PATCH_EXCEPTION", error);
            TrCompatDiagnostics.exportZip();
            throw new RuntimeException("Unable to repair separate-package rootfs paths", error);
        }
    }

    private static void ensureAlias(File alias, File root) throws Exception {
        try {
            String current = Os.readlink(alias.getPath());
            if (root.getPath().equals(current)) return;
        }
        catch (Throwable ignored) {}
        if (alias.exists() || Files.isSymbolicLink(alias.toPath())) {
            if (!alias.delete()) throw new java.io.IOException("unable to replace alias "+alias.getPath());
        }
        Os.symlink(root.getPath(), alias.getPath());
    }

    private static int[] patchTree(File start) throws Exception {
        int scanned = 0;
        int patchedFiles = 0;
        int occurrences = 0;
        if (!start.exists()) return new int[]{0, 0, 0};

        ArrayDeque<File> queue = new ArrayDeque<>();
        queue.add(start);
        while (!queue.isEmpty()) {
            File file = queue.removeFirst();
            android.system.StructStat stat;
            try { stat = Os.lstat(file.getPath()); }
            catch (Throwable ignored) { continue; }
            int type = stat.st_mode & OsConstants.S_IFMT;

            if (type == OsConstants.S_IFLNK) {
                String target = Os.readlink(file.getPath());
                String old = new String(OLD, StandardCharsets.US_ASCII);
                if (target.contains(old)) {
                    String replacement = target.replace(old, new String(ALIAS, StandardCharsets.US_ASCII));
                    if (!file.delete()) throw new java.io.IOException("unable to replace symlink "+file.getPath());
                    Os.symlink(replacement, file.getPath());
                    patchedFiles++;
                    occurrences++;
                }
                continue;
            }
            if (type == OsConstants.S_IFDIR) {
                File[] children = file.listFiles();
                if (children != null) for (File child : children) queue.addLast(child);
                continue;
            }
            if (type != OsConstants.S_IFREG) continue;
            if (file.length() > 64L * 1024L * 1024L) {
                TrCompatDiagnostics.trace("ROOTFS_ALIAS_PATCH_SKIP_LARGE path="+file.getPath()+" length="+file.length());
                continue;
            }

            scanned++;
            int count = patchFile(file, (int)(stat.st_mode & 0777));
            if (count > 0) {
                patchedFiles++;
                occurrences += count;
            }
        }
        return new int[]{scanned, patchedFiles, occurrences};
    }

    private static int patchFile(File file, int mode) throws Exception {
        byte[] data = Files.readAllBytes(file.toPath());
        int count = 0;
        for (int i = 0; i <= data.length - OLD.length; i++) {
            boolean match = true;
            for (int j = 0; j < OLD.length; j++) {
                if (data[i+j] != OLD[j]) { match = false; break; }
            }
            if (!match) continue;
            System.arraycopy(ALIAS, 0, data, i, ALIAS.length);
            count++;
            i += OLD.length - 1;
        }
        if (count == 0) return 0;

        File temp = new File(file.getPath()+".trcompat-v9.tmp");
        if (temp.exists() && !temp.delete()) throw new java.io.IOException("unable to remove temp "+temp.getPath());
        try (BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(temp, false))) {
            output.write(data);
            output.flush();
        }
        Os.chmod(temp.getPath(), mode == 0 ? 0644 : mode);
        Os.rename(temp.getPath(), file.getPath());
        TrCompatDiagnostics.trace("ROOTFS_ALIAS_PATCH_FILE path="+file.getPath()+" occurrences="+count);
        return count;
    }
}
'''
    java = java.replace("__REVISION__", REVISION)
    path = root / "app/src/main/java/com/winlator/core/TrCompatRootfsPatcher.java"
    path.write_text(java, encoding="utf-8")


def patch_runtime(root: Path) -> None:
    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    replace_once(
        activity,
        "import com.winlator.core.TrCompatWinePatcher;\n",
        "import com.winlator.core.TrCompatWinePatcher;\nimport com.winlator.core.TrCompatRootfsPatcher;\n",
    )
    replace_once(
        activity,
        '''            trTrace("ROOTFS root="+rootFS.getRootDir().getPath()+" winePath="+rootFS.getWinePath());
            TrCompatWinePatcher.apply(this, rootFS);
''',
        '''            trTrace("ROOTFS root="+rootFS.getRootDir().getPath()+" winePath="+rootFS.getWinePath());
            TrCompatRootfsPatcher.apply(this, rootFS);
            trTrace("ROOTFS_ALIAS_PATCH_RETURN");
            TrCompatWinePatcher.apply(this, rootFS);
''',
    )
    replace_once(
        activity,
        '''            envVars.putAll(container.getEnvVars());
            if (shortcut != null) envVars.putAll(shortcut.getExtra("envVars"));
            if (!envVars.has("WINEESYNC")) envVars.put("WINEESYNC", "1");
''',
        '''            envVars.putAll(container.getEnvVars());
            if (shortcut != null) envVars.putAll(shortcut.getExtra("envVars"));
            envVars.put("WINEESYNC", "0");
            envVars.put("WINEFSYNC", "0");
            trTrace("SYNC_COMPAT_FORCED WINEESYNC=0 WINEFSYNC=0");
''',
    )

    guest = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    replace_once(
        guest,
        '''        TrCompatDiagnostics.trace("LAUNCH_STAGE1_DIRECT_BEGIN");
        int result = ProcessHelper.exec(directCommand, envVars, rootDir, finalCallback);
''',
        '''        File xSocketFile = new File(rootDir, "/tmp/.X11-unix/X0");
        long xWaitStarted = System.currentTimeMillis();
        while (!xSocketFile.exists() && System.currentTimeMillis() - xWaitStarted < 3000L) {
            try { Thread.sleep(25L); }
            catch (InterruptedException error) { Thread.currentThread().interrupt(); break; }
        }
        TrCompatDiagnostics.trace("XSERVER_SOCKET_READY exists="+xSocketFile.exists()+
                " waitMs="+(System.currentTimeMillis()-xWaitStarted)+" path="+xSocketFile.getPath());

        TrCompatDiagnostics.trace("LAUNCH_STAGE1_DIRECT_BEGIN");
        int result = ProcessHelper.exec(directCommand, envVars, rootDir, finalCallback);
''',
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v9_patch.py WINLATOR_APP_DIR WINE_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    v8.v7.v6.patch_base_v5(root)
    v8.v7.v6.write_diagnostics_class(root)
    v8.v7.v6.patch_process_helper(root)
    v8.v7.v6.patch_guest_launcher(root)
    v8.v7.v6.patch_activity(root)
    v8.v7.patch_versions(root)
    v8.v7.prepare_box64_and_native_fallback(root)
    v8.v7.patch_box64_refresh(root)
    v8.v7.patch_three_stage_launcher(root)
    v8.patch_versions(root)
    hashes = v8.prepare_wine_assets(root, component_dir)
    v8.write_runtime_patcher(root, hashes)
    v8.patch_runtime_call_and_diagnostics(root, hashes)

    patch_versions(root)
    rootfs_report = patch_rootfs_archive(root)
    box64_report = patch_box64_payloads(root)
    write_rootfs_runtime_patcher(root)
    patch_runtime(root)

    report = root / "v9-rootfs-patch-report.txt"
    report.write_text(
        "revision="+REVISION+"\n"
        f"old={OLD_ROOT.decode()}\n"
        f"alias={ALIAS_ROOT.decode()}\n"
        f"rootfs_scanned={rootfs_report[0]}\n"
        f"rootfs_patched_files={rootfs_report[1]}\n"
        f"rootfs_occurrences={rootfs_report[2]}\n"
        f"rootfs_sha256={rootfs_report[3]}\n"
        f"box64_occurrences={box64_report[0]}\n"
        f"box64_archive_sha256={box64_report[1]}\n"
        f"box64_native_sha256={box64_report[2]}\n",
        encoding="utf-8",
    )

    print("Winlator TR Compat v9 full rootfs alias repair patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
