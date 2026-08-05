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
ASSET_RELATIVE = Path("trcompat-v28/ntoskrnl.exe")


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


def extract_runtime_asset(root: Path) -> str:
    archive = root / "app/src/main/assets/rootfs.tzst"
    target_asset = root / "app/src/main/assets" / ASSET_RELATIVE
    target_asset.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tr-v28-asset-") as tmp_name:
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
            raise RuntimeError(f"unexpected embedded v27 ntoskrnl hash: {digest}")
        data = extracted.read_bytes()
        if not data.startswith(b"MZ") or b"IRP_TRACE begin" not in data:
            raise RuntimeError("runtime refresh asset is not the validated v27 tracer")
        target_asset.write_bytes(data)
        os.chmod(target_asset, 0o644)

    return digest


def patch_application(root: Path) -> None:
    application = root / "app/src/main/java/com/winlator/TrCrashApplication.java"
    text = application.read_text(encoding="utf-8")

    old_import = "import java.text.SimpleDateFormat;\n"
    new_import = "import java.security.MessageDigest;\nimport java.text.SimpleDateFormat;\n"
    if old_import not in text:
        raise RuntimeError("TrCrashApplication import anchor missing")
    text = text.replace(old_import, new_import, 1)

    old_constants = '''    private static final int MAX_TRACE_BYTES = 2 * 1024 * 1024;\n'''
    new_constants = f'''    private static final int MAX_TRACE_BYTES = 2 * 1024 * 1024;\n    private static final String RUNTIME_REPORT_NAME = "TR_ROOTFS_UPDATE_v28.txt";\n    private static final String V26_NTOSKRNL_SHA256 = "{V26_NTOSKRNL_SHA256}";\n    private static final String V27_NTOSKRNL_SHA256 = "{V27_NTOSKRNL_SHA256}";\n    private static final String V28_NTOSKRNL_ASSET = "trcompat-v28/ntoskrnl.exe";\n'''
    if old_constants not in text:
        raise RuntimeError("TrCrashApplication constants anchor missing")
    text = text.replace(old_constants, new_constants, 1)

    old_on_create = '''        super.onCreate();\n        installJavaCrashHandler();\n'''
    new_on_create = '''        super.onCreate();\n        installV28NtKernel();\n        installJavaCrashHandler();\n'''
    if old_on_create not in text:
        raise RuntimeError("TrCrashApplication onCreate anchor missing")
    text = text.replace(old_on_create, new_on_create, 1)

    method_anchor = '''    private void installJavaCrashHandler() {\n'''
    methods = r'''    private static String sha256File(File source) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(source))) {
            byte[] buffer = new byte[16384];
            int read;
            while ((read = input.read(buffer)) >= 0) digest.update(buffer, 0, read);
        }
        StringBuilder result = new StringBuilder();
        for (byte value : digest.digest()) result.append(String.format(Locale.US, "%02x", value & 0xff));
        return result.toString();
    }

    private void reportRuntimeUpdate(String detail) {
        String text = "===== ROOTFS_UPDATE " + now() + " =====\n" + safe(detail) + "\n";
        synchronized (LOCK) {
            if (!appendText(externalDirectory(), RUNTIME_REPORT_NAME, text)) {
                appendText(internalDirectory(), RUNTIME_REPORT_NAME, text);
            }
        }
    }

    private void installV28NtKernel() {
        File target = new File(getFilesDir(),
                "rootfs/opt/wine/lib/wine/x86_64-windows/ntoskrnl.exe");
        File parent = target.getParentFile();
        File temporary = parent == null ? null : new File(parent, "ntoskrnl.exe.trcompat-v28.tmp");
        File backup = parent == null ? null : new File(parent, "ntoskrnl.exe.trcompat-v26.bak");
        boolean targetMoved = false;
        try {
            if (!target.isFile()) {
                reportRuntimeUpdate("state=TARGET_MISSING action=NONE embedded_rootfs_will_supply_v27=true");
                return;
            }

            String before = sha256File(target);
            if (V27_NTOSKRNL_SHA256.equals(before)) {
                reportRuntimeUpdate("state=ALREADY_CURRENT before=" + before + " action=NONE");
                return;
            }
            if (!V26_NTOSKRNL_SHA256.equals(before)) {
                reportRuntimeUpdate("state=UNKNOWN_BASE before=" + before + " action=REFUSED");
                return;
            }
            if (parent == null || (!parent.isDirectory() && !parent.mkdirs())) {
                throw new IllegalStateException("target parent unavailable");
            }

            if (temporary.exists() && !temporary.delete()) {
                throw new IllegalStateException("stale temporary file cannot be removed");
            }
            try (InputStream input = getAssets().open(V28_NTOSKRNL_ASSET);
                 BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(temporary, false))) {
                byte[] buffer = new byte[16384];
                int read;
                while ((read = input.read(buffer)) >= 0) output.write(buffer, 0, read);
                output.flush();
            }
            String staged = sha256File(temporary);
            if (!V27_NTOSKRNL_SHA256.equals(staged)) {
                throw new IllegalStateException("staged hash mismatch: " + staged);
            }
            temporary.setReadable(true, false);
            temporary.setWritable(true, true);
            temporary.setExecutable(true, false);

            if (backup.exists() && !backup.delete()) {
                throw new IllegalStateException("old backup cannot be removed");
            }
            if (!target.renameTo(backup)) {
                throw new IllegalStateException("baseline rename failed");
            }
            targetMoved = true;
            if (!temporary.renameTo(target)) {
                throw new IllegalStateException("staged install rename failed");
            }
            targetMoved = false;
            target.setReadable(true, false);
            target.setWritable(true, true);
            target.setExecutable(true, false);

            String after = sha256File(target);
            if (!V27_NTOSKRNL_SHA256.equals(after)) {
                if (target.exists()) target.delete();
                if (!backup.renameTo(target)) {
                    throw new IllegalStateException("post-verify mismatch and rollback failed: " + after);
                }
                throw new IllegalStateException("post-verify mismatch rolled back: " + after);
            }
            reportRuntimeUpdate("state=UPDATED before=" + before + " after=" + after
                    + " backup=" + backup.getAbsolutePath());
        }
        catch (Throwable error) {
            try {
                if (targetMoved && backup != null && backup.isFile() && !target.exists()) {
                    backup.renameTo(target);
                }
                if (temporary != null && temporary.exists()) temporary.delete();
            }
            catch (Throwable ignored) {}
            reportRuntimeUpdate("state=FAILED action=ROLLBACK_ATTEMPTED error="
                    + error.getClass().getName() + ":" + safe(error.getMessage()));
        }
    }

'''
    if method_anchor not in text:
        raise RuntimeError("TrCrashApplication method anchor missing")
    text = text.replace(method_anchor, methods + method_anchor, 1)
    application.write_text(text, encoding="utf-8")


def patch_diagnostics(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat27-irp-trace"',
        'versionName "11.1-trcompat28-irp-trace-active"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    text = text.replace("TR_DIAG_v27_IRP_TRACE.zip", "TR_DIAG_v28_IRP_TRACE_ACTIVE.zip")
    text = text.replace(
        "DIAGNOSTICS_RESET version=27-irp-trace",
        "DIAGNOSTICS_RESET version=28-irp-trace-active",
    )

    old_fields = '''    private static File wellbiaStringsFile;\n    private static File zipFile;\n'''
    new_fields = '''    private static File wellbiaStringsFile;\n    private static File runtimeUpdateFile;\n    private static File zipFile;\n'''
    if old_fields not in text:
        raise RuntimeError("v28 diagnostic field anchor missing")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        wellbiaStringsFile = new File(parentDir, "wellbia_strings_sanitized.txt");\n        zipFile = new File(parentDir, "TR_DIAG_v28_IRP_TRACE_ACTIVE.zip");\n'''
    new_paths = '''        wellbiaStringsFile = new File(parentDir, "wellbia_strings_sanitized.txt");\n        runtimeUpdateFile = new File(parentDir, "TR_ROOTFS_UPDATE_v28.txt");\n        zipFile = new File(parentDir, "TR_DIAG_v28_IRP_TRACE_ACTIVE.zip");\n'''
    if old_paths not in text:
        raise RuntimeError("v28 diagnostic path anchor missing")
    text = text.replace(old_paths, new_paths, 1)

    old_zip = '''                addToZip(zip, wellbiaStringsFile, "wellbia_strings_sanitized.txt");\n'''
    new_zip = '''                addToZip(zip, wellbiaStringsFile, "wellbia_strings_sanitized.txt");\n                addToZip(zip, runtimeUpdateFile, "TR_ROOTFS_UPDATE_v28.txt");\n'''
    if old_zip not in text:
        raise RuntimeError("v28 diagnostic zip anchor missing")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("usage: apply_v28_runtime_refresh_patch.py WINLATOR_APP_DIR COMPONENT_DIR [--already-v27]", file=sys.stderr)
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

    asset_hash = extract_runtime_asset(root)
    patch_application(root)
    patch_diagnostics(root)

    report = root / "v28-runtime-refresh-report.txt"
    report.write_text(
        f"accepted_v26_ntoskrnl_sha256={V26_NTOSKRNL_SHA256}\n"
        f"installed_v27_ntoskrnl_sha256={V27_NTOSKRNL_SHA256}\n"
        f"runtime_asset_sha256={asset_hash}\n"
        f"runtime_asset_path=assets/{ASSET_RELATIVE.as_posix()}\n",
        encoding="utf-8",
    )
    print("Winlator TR Compat v28 safe existing-rootfs refresh applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
