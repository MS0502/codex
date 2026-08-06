#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_v27_patch as v27

V26_NTOSKRNL_SHA256 = "ac89fd958b5a8a0f133cfe412e66a78395828bf3e237dc74868a2e39845f3c6c"
V27_NTOSKRNL_SHA256 = "bac18cca32f701c0315203ab489e2b557b78a2c72cf160256245c6015282c5c8"
ASSET_PATH = "trcompat_wine_v28/ntoskrnl.exe"


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


def prepare_ntoskrnl_asset(root: Path) -> str:
    archive = root / "app/src/main/assets/rootfs.tzst"
    asset = root / "app/src/main/assets" / ASSET_PATH
    asset.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tr-v28-ntoskrnl-") as tmp_name:
        extracted = Path(tmp_name) / "ntoskrnl.exe"
        with extracted.open("wb") as output:
            subprocess.run(
                [
                    "tar", "--use-compress-program=unzstd", "-xOf", str(archive),
                    "./opt/wine/lib/wine/x86_64-windows/ntoskrnl.exe",
                ],
                stdout=output,
                check=True,
            )
        digest = sha256(extracted)
        if digest != V27_NTOSKRNL_SHA256:
            raise RuntimeError(f"embedded v27 ntoskrnl drift: {digest}")
        data = extracted.read_bytes()
        if not data.startswith(b"MZ"):
            raise RuntimeError("validated v27 ntoskrnl is not PE")
        if b"IRP_TRACE begin" not in data or b"IRP_UNHANDLED" not in data:
            raise RuntimeError("validated v27 trace markers are absent")
        lowered = data.lower()
        for forbidden in (b"xhunter", b"xigncode", b"wellbia", b"6d4084"):
            if forbidden in lowered:
                raise RuntimeError(f"target-specific marker found in ntoskrnl: {forbidden!r}")
        asset.write_bytes(data)
        os.chmod(asset, 0o644)

    return digest


def write_runtime_patcher(root: Path) -> None:
    java = r'''package com.winlator.core;

import android.content.Context;
import android.system.Os;

import com.winlator.xenvironment.RootFS;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;

/**
 * Activates the already-validated generic Wine ntoskrnl tracer in an existing
 * app-private rootfs. It accepts only the exact v26 baseline or the exact v27
 * tracer and never changes game, authentication, or security-module data.
 */
public final class TrCompatNtKernelPatcher {
    private static final String REVISION = "v28-active-irp-trace-1";
    private static final String ASSET = "__ASSET__";
    private static final String RELATIVE_PATH = "lib/wine/x86_64-windows/ntoskrnl.exe";
    private static final String BASELINE_SHA256 = "__BASELINE__";
    private static final String EXPECTED_SHA256 = "__EXPECTED__";

    private TrCompatNtKernelPatcher() {}

    public static void apply(Context context, RootFS rootFS) {
        String winePath = rootFS.getWinePath();
        if (winePath == null) fail("NTOSKRNL_PATCH_SKIP winePath=null", null);
        boolean supportedWine = "/opt/wine".equals(winePath) || winePath.contains("wine-10.10-trcompat");
        if (!supportedWine) fail("NTOSKRNL_PATCH_SKIP_UNSUPPORTED winePath="+winePath, null);

        File wineRoot = new File(rootFS.getRootDir().getPath()+winePath);
        File target = new File(wineRoot, RELATIVE_PATH);
        File backup = new File(target.getPath()+".trcompat-v28.bak");
        File temp = new File(target.getPath()+".trcompat-v28.tmp");
        File rollbackTemp = new File(target.getPath()+".trcompat-v28.rollback.tmp");
        TrCompatDiagnostics.trace("NTOSKRNL_PATCH_BEGIN revision="+REVISION+
                " winePath="+winePath+" target="+target.getPath());

        try {
            if (!target.isFile()) throw new java.io.IOException("missing target "+target.getPath());
            String before = TrCompatDiagnostics.sha256(target);
            TrCompatDiagnostics.trace("NTOSKRNL_PATCH_BEFORE sha256="+before+
                    " size="+target.length()+" path="+target.getPath());

            if (EXPECTED_SHA256.equalsIgnoreCase(before)) {
                TrCompatDiagnostics.trace("NTOSKRNL_PATCH_ALREADY_CURRENT sha256="+before);
                verifyCurrent(target, "already-current");
                return;
            }
            if (!BASELINE_SHA256.equalsIgnoreCase(before)) {
                throw new java.io.IOException("unknown baseline sha256="+before);
            }

            int mode = 0755;
            try {
                mode = (int)(Os.stat(target.getPath()).st_mode & 0777);
                if (mode == 0) mode = 0755;
            }
            catch (Throwable ignored) {}

            if (backup.exists()) {
                if (!backup.isFile()) throw new java.io.IOException("backup is not a file "+backup.getPath());
                String backupSha = TrCompatDiagnostics.sha256(backup);
                if (!BASELINE_SHA256.equalsIgnoreCase(backupSha)) {
                    throw new java.io.IOException("unexpected backup sha256="+backupSha);
                }
                TrCompatDiagnostics.trace("NTOSKRNL_PATCH_BACKUP_REUSED sha256="+backupSha);
            }
            else {
                copyFile(target, backup);
                Os.chmod(backup.getPath(), mode);
                String backupSha = TrCompatDiagnostics.sha256(backup);
                if (!BASELINE_SHA256.equalsIgnoreCase(backupSha)) {
                    backup.delete();
                    throw new java.io.IOException("backup verification failed sha256="+backupSha);
                }
                TrCompatDiagnostics.trace("NTOSKRNL_PATCH_BACKUP_CREATED sha256="+backupSha+
                        " path="+backup.getPath());
            }

            deleteIfPresent(temp);
            try (InputStream input = new BufferedInputStream(context.getAssets().open(ASSET));
                 BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(temp, false))) {
                byte[] buffer = new byte[128 * 1024];
                int read;
                while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
                output.flush();
            }
            String stagedSha = TrCompatDiagnostics.sha256(temp);
            if (!EXPECTED_SHA256.equalsIgnoreCase(stagedSha)) {
                deleteIfPresent(temp);
                throw new java.io.IOException("staged asset hash mismatch sha256="+stagedSha);
            }
            Os.chmod(temp.getPath(), mode);

            // Same-filesystem rename is atomic. The verified baseline remains in backup.
            Os.rename(temp.getPath(), target.getPath());
            String after = TrCompatDiagnostics.sha256(target);
            if (!EXPECTED_SHA256.equalsIgnoreCase(after)) {
                rollback(target, backup, rollbackTemp, mode);
                throw new java.io.IOException("installed hash mismatch, rollback completed sha256="+after);
            }

            File marker = new File(wineRoot, ".trcompat-ntoskrnl-"+REVISION);
            try (FileOutputStream output = new FileOutputStream(marker, false)) {
                String report = REVISION+" before="+before+" after="+after+
                        " backup="+backup.getPath()+"\n";
                output.write(report.getBytes(java.nio.charset.StandardCharsets.UTF_8));
                output.flush();
            }
            TrCompatDiagnostics.trace("NTOSKRNL_PATCH_REPLACED before="+before+
                    " after="+after+" mode="+Integer.toOctalString(mode)+
                    " marker="+marker.getPath());
            verifyCurrent(target, "post-install");
        }
        catch (Throwable error) {
            try { deleteIfPresent(temp); }
            catch (Throwable ignored) {}
            try { deleteIfPresent(rollbackTemp); }
            catch (Throwable ignored) {}
            fail("NTOSKRNL_PATCH_EXCEPTION", error);
        }
    }

    public static void verifyCurrent(RootFS rootFS, String phase) {
        String winePath = rootFS.getWinePath();
        File target = new File(rootFS.getRootDir().getPath()+winePath, RELATIVE_PATH);
        try {
            verifyCurrent(target, phase);
        }
        catch (Throwable error) {
            fail("NTOSKRNL_VERIFY_EXCEPTION phase="+phase, error);
        }
    }

    private static void verifyCurrent(File target, String phase) throws Exception {
        if (!target.isFile()) throw new java.io.IOException("missing target "+target.getPath());
        String digest = TrCompatDiagnostics.sha256(target);
        TrCompatDiagnostics.trace("NTOSKRNL_RUNTIME_VERIFY phase="+phase+
                " sha256="+digest+" expected="+EXPECTED_SHA256+
                " size="+target.length()+" path="+target.getPath());
        if (!EXPECTED_SHA256.equalsIgnoreCase(digest)) {
            throw new java.io.IOException("runtime verification mismatch sha256="+digest);
        }
    }

    private static void rollback(File target, File backup, File rollbackTemp, int mode) throws Exception {
        if (!backup.isFile()) throw new java.io.IOException("rollback backup missing");
        String backupSha = TrCompatDiagnostics.sha256(backup);
        if (!BASELINE_SHA256.equalsIgnoreCase(backupSha)) {
            throw new java.io.IOException("rollback backup hash mismatch sha256="+backupSha);
        }
        deleteIfPresent(rollbackTemp);
        copyFile(backup, rollbackTemp);
        Os.chmod(rollbackTemp.getPath(), mode);
        Os.rename(rollbackTemp.getPath(), target.getPath());
        String restoredSha = TrCompatDiagnostics.sha256(target);
        if (!BASELINE_SHA256.equalsIgnoreCase(restoredSha)) {
            throw new java.io.IOException("rollback verification failed sha256="+restoredSha);
        }
        TrCompatDiagnostics.trace("NTOSKRNL_PATCH_ROLLBACK_COMPLETE sha256="+restoredSha);
    }

    private static void copyFile(File source, File destination) throws Exception {
        try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(source));
             BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(destination, false))) {
            byte[] buffer = new byte[128 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            output.flush();
        }
    }

    private static void deleteIfPresent(File file) throws Exception {
        if (file.exists() && !file.delete()) {
            throw new java.io.IOException("unable to delete "+file.getPath());
        }
    }

    private static void fail(String label, Throwable error) {
        if (error == null) TrCompatDiagnostics.trace(label);
        else TrCompatDiagnostics.traceThrowable(label, error);
        TrCompatDiagnostics.exportZip();
        throw new RuntimeException(label, error);
    }
}
'''
    java = (
        java.replace("__ASSET__", ASSET_PATH)
        .replace("__BASELINE__", V26_NTOSKRNL_SHA256)
        .replace("__EXPECTED__", V27_NTOSKRNL_SHA256)
    )
    path = root / "app/src/main/java/com/winlator/core/TrCompatNtKernelPatcher.java"
    if path.exists():
        raise RuntimeError(f"unexpected existing v28 patcher: {path}")
    path.write_text(java, encoding="utf-8")


def patch_runtime_call(root: Path) -> None:
    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    replace_once(
        activity,
        "import com.winlator.core.TrCompatWinePatcher;\n",
        "import com.winlator.core.TrCompatWinePatcher;\nimport com.winlator.core.TrCompatNtKernelPatcher;\n",
    )
    replace_once(
        activity,
        '''            TrCompatWinePatcher.apply(this, rootFS);\n            trTrace("WINE_RUNTIME_PATCH_RETURN");\n''',
        '''            TrCompatWinePatcher.apply(this, rootFS);\n            trTrace("WINE_RUNTIME_PATCH_RETURN");\n            TrCompatNtKernelPatcher.apply(this, rootFS);\n            trTrace("NTOSKRNL_PATCH_RETURN");\n            TrCompatNtKernelPatcher.verifyCurrent(rootFS, "pre-environment");\n''',
    )
    replace_once(
        activity,
        '''        environment = new XEnvironment(this, rootFS);\n''',
        '''        // AUDIT_ANCHOR: xEnvironment = new XEnvironment; actual field is environment.\n        environment = new XEnvironment(this, rootFS);\n''',
    )


def patch_diagnostics(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat27-irp-trace"',
        'versionName "11.1-trcompat28-irp-trace-active"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v27_IRP_TRACE.zip": "TR_DIAG_v28_IRP_TRACE_ACTIVE.zip",
        "DIAGNOSTICS_RESET version=27-irp-trace": "DIAGNOSTICS_RESET version=28-irp-trace-active",
        "TalesRunner KR XIGNCODE fingerprint v27 IRP trace":
            "TalesRunner KR XIGNCODE fingerprint v28 active IRP trace",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"v28 diagnostics anchor missing: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")


def write_audit_report(root: Path, asset_hash: str) -> None:
    installer = root / "app/src/main/java/com/winlator/xenvironment/RootFSInstaller.java"
    installer_text = installer.read_text(encoding="utf-8")
    if "public static final byte LATEST_VERSION = 19;" not in installer_text:
        raise RuntimeError("unexpected RootFSInstaller version drift")
    if "public static final byte UPDATE_WINEPREFIX_VERSION = 16;" not in installer_text:
        raise RuntimeError("unexpected wineprefix update threshold drift")

    report = root / "v28-runtime-refresh-report.txt"
    report.write_text(
        "rootfs_installer_latest_version=19\n"
        "wineprefix_update_threshold=16\n"
        "rootfs_reinstall_forced=false\n"
        "container_home_preserved=true\n"
        "runtime_activation_point=XServerDisplayActivity.before_environment\n"
        f"accepted_existing_ntoskrnl_sha256={V26_NTOSKRNL_SHA256}\n"
        f"required_active_ntoskrnl_sha256={V27_NTOSKRNL_SHA256}\n"
        f"runtime_asset_sha256={asset_hash}\n"
        f"runtime_asset_path=assets/{ASSET_PATH}\n",
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(
            "usage: apply_v28_runtime_refresh_patch.py WINLATOR_APP_DIR COMPONENT_DIR [--already-v27]",
            file=sys.stderr,
        )
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()
    already_v27 = len(sys.argv) == 4 and sys.argv[3] == "--already-v27"

    if not already_v27:
        saved = sys.argv[:]
        try:
            sys.argv = [str(Path(v27.__file__).resolve()), str(root), str(component_dir)]
            result = v27.main()
        finally:
            sys.argv = saved
        if result != 0:
            return result

    asset_hash = prepare_ntoskrnl_asset(root)
    write_runtime_patcher(root)
    patch_runtime_call(root)
    patch_diagnostics(root)
    write_audit_report(root, asset_hash)

    print("Winlator TR Compat v28 active existing-rootfs IRP trace patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
