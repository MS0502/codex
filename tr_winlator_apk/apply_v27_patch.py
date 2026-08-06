#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_v26_crash_observability_patch as v26

OLD_ROOT = b"/data/data/com.winlator/files/rootfs"
ALIAS_ROOT = b"/data/user/0/com.winlator.trcompat/r"


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


def repack(tree: Path, output: Path) -> None:
    tar_path = tree.parent / "rootfs-v27.tar"
    run("tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner",
        "--mtime=@0", "--format=gnu", "-C", str(tree), "-cf", str(tar_path), ".")
    run("zstd", "-19", "-f", str(tar_path), "-o", str(output))


def install_ntoskrnl(root: Path, component: Path) -> None:
    archive = root / "app/src/main/assets/rootfs.tzst"
    if not archive.is_file() or not component.is_file():
        raise RuntimeError("missing rootfs or v27 ntoskrnl component")

    with tempfile.TemporaryDirectory(prefix="tr-v27-rootfs-") as tmp_name:
        tmp = Path(tmp_name)
        tree = tmp / "tree"
        tree.mkdir()
        run("tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(tree))
        target = tree / "opt/wine/lib/wine/x86_64-windows/ntoskrnl.exe"
        if not target.is_file():
            raise RuntimeError(f"baseline ntoskrnl missing: {target}")
        baseline_hash = sha256(target)

        data = component.read_bytes()
        if data[:2] != b"MZ":
            raise RuntimeError("v27 ntoskrnl is not a PE image")
        count = data.count(OLD_ROOT)
        if count:
            if len(OLD_ROOT) != len(ALIAS_ROOT):
                raise RuntimeError("root alias length mismatch")
            data = data.replace(OLD_ROOT, ALIAS_ROOT)
        target.write_bytes(data)
        os.chmod(target, 0o755)
        final_hash = sha256(target)
        if final_hash == baseline_hash:
            raise RuntimeError("instrumented ntoskrnl is byte-identical to baseline")
        repack(tree, archive)

    report = root / "v27-irp-component-report.txt"
    report.write_text(
        f"baseline_ntoskrnl_sha256={baseline_hash}\n"
        f"v27_ntoskrnl_sha256={final_hash}\n"
        f"embedded_root_path_occurrences={count}\n"
        f"v27_rootfs_sha256={sha256(archive)}\n",
        encoding="utf-8",
    )


def patch_diagnostics(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat26-crash-observability"',
        'versionName "11.1-trcompat27-irp-trace"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    for old, new in {
        "TR_DIAG_v16_LIFETIME.zip": "TR_DIAG_v27_IRP_TRACE.zip",
        "DIAGNOSTICS_RESET version=16-lifetime": "DIAGNOSTICS_RESET version=27-irp-trace",
        "TalesRunner KR XIGNCODE fingerprint v16 lifetime": "TalesRunner KR XIGNCODE fingerprint v27 IRP trace",
    }.items():
        if old not in text:
            raise RuntimeError(f"diagnostic anchor missing: {old}")
        text = text.replace(old, new)

    old_fields = '''    private static File processLifetimeFile;
    private static File zipFile;
    private static String lastLifetimeSnapshot = "";
'''
    new_fields = '''    private static File processLifetimeFile;
    private static File wellbiaStringsFile;
    private static File zipFile;
    private static String lastLifetimeSnapshot = "";
'''
    if old_fields not in text:
        raise RuntimeError("diagnostic fields anchor missing")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        processLifetimeFile = new File(parentDir, "process_lifetime.txt");
        zipFile = new File(parentDir, "TR_DIAG_v27_IRP_TRACE.zip");
'''
    new_paths = '''        processLifetimeFile = new File(parentDir, "process_lifetime.txt");
        wellbiaStringsFile = new File(parentDir, "wellbia_strings_sanitized.txt");
        zipFile = new File(parentDir, "TR_DIAG_v27_IRP_TRACE.zip");
'''
    if old_paths not in text:
        raise RuntimeError("diagnostic paths anchor missing")
    text = text.replace(old_paths, new_paths, 1)

    old_reset = '''            processLifetimeFile.delete();
            zipFile.delete();
'''
    new_reset = '''            processLifetimeFile.delete();
            wellbiaStringsFile.delete();
            zipFile.delete();
'''
    if old_reset not in text:
        raise RuntimeError("diagnostic reset anchor missing")
    text = text.replace(old_reset, new_reset, 1)

    method_anchor = '''    private static boolean lowloadLogCandidate(File file) {
'''
    method = r'''    private static void appendPrintableRun(StringBuilder output, StringBuilder run) {
        if (run.length() < 4) {
            run.setLength(0);
            return;
        }
        String safe = sanitizeProcessLine(run.toString());
        if (safe.length() > 4096) safe = safe.substring(0, 4096) + "[TRUNCATED]";
        output.append(safe).append('\n');
        run.setLength(0);
    }

    public static void collectWellbiaPrintableStrings(File rootDir, String stage) {
        ensurePaths();
        File source = new File(rootDir,
                "home/xuser/.wine/drive_c/users/xuser/AppData/Local/WELLBIA/"+
                "xldr_TalesRunner_KR_loader_x64.exe.log");
        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(wellbiaStringsFile, true)) {
                writer.write("===== stage="+stage+" time="+System.currentTimeMillis()+
                        " exists="+source.isFile()+" length="+(source.isFile()?source.length():-1)+" =====\n");
                if (!source.isFile() || !source.canRead()) return;
                int max = (int)Math.min(source.length(), 1024L * 1024L);
                byte[] data = new byte[max];
                int total = 0;
                try (InputStream input = new BufferedInputStream(new FileInputStream(source))) {
                    while (total < data.length) {
                        int read = input.read(data, total, data.length-total);
                        if (read < 0) break;
                        total += read;
                    }
                }

                StringBuilder extracted = new StringBuilder();
                StringBuilder run = new StringBuilder();
                for (int i = 0; i < total; i++) {
                    int value = data[i] & 0xff;
                    if (value >= 0x20 && value <= 0x7e) run.append((char)value);
                    else appendPrintableRun(extracted, run);
                }
                appendPrintableRun(extracted, run);

                run.setLength(0);
                for (int i = 0; i + 1 < total; i += 2) {
                    int lo = data[i] & 0xff;
                    int hi = data[i+1] & 0xff;
                    if (hi == 0 && lo >= 0x20 && lo <= 0x7e) run.append((char)lo);
                    else appendPrintableRun(extracted, run);
                }
                appendPrintableRun(extracted, run);

                writer.write(extracted.toString());
                writer.flush();
            }
            catch (Exception e) {
                traceThrowable("WELLBIA_STRINGS_EXCEPTION", e);
            }
        }
    }

'''
    if method_anchor not in text:
        raise RuntimeError("diagnostic method anchor missing")
    text = text.replace(method_anchor, method + method_anchor, 1)

    old_collect = '''                collectProcessLifetime(stage);
                if (seconds == 0 || seconds == 30 || seconds == 60
                        || seconds == 90 || seconds == 120 || seconds == 180) {
                    collectWellbiaLowload(rootDir, stage);
                }
                exportZip();
'''
    new_collect = '''                collectProcessLifetime(stage);
                collectWellbiaPrintableStrings(rootDir, stage);
                if (seconds == 0 || seconds == 30 || seconds == 60
                        || seconds == 90 || seconds == 120 || seconds == 180) {
                    collectWellbiaLowload(rootDir, stage);
                }
                exportZip();
'''
    if old_collect not in text:
        raise RuntimeError("diagnostic collector anchor missing")
    text = text.replace(old_collect, new_collect, 1)

    old_zip = '''                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
                addToZip(zip, processLifetimeFile, "process_lifetime.txt");
'''
    new_zip = '''                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
                addToZip(zip, processLifetimeFile, "process_lifetime.txt");
                addToZip(zip, wellbiaStringsFile, "wellbia_strings_sanitized.txt");
'''
    if old_zip not in text:
        raise RuntimeError("diagnostic zip anchor missing")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("usage: apply_v27_patch.py WINLATOR_APP_DIR COMPONENT_DIR [--already-v26]", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()
    already_v26 = len(sys.argv) == 4 and sys.argv[3] == "--already-v26"

    if not already_v26:
        saved = sys.argv[:]
        try:
            sys.argv = [str(Path(v26.__file__).resolve()), str(root), str(component_dir)]
            result = v26.main()
        finally:
            sys.argv = saved
        if result != 0:
            return result

    patch_diagnostics(root)
    install_ntoskrnl(root, component_dir / "ntoskrnl.exe")
    print("Winlator TR Compat v27 generic IRP trace applied; runtime statuses are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
