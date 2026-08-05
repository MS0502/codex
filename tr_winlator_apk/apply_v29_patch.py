#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

NTOSKRNL_ASSET = "trcompat_wine_v29/ntoskrnl.exe"
LOCALE_ASSET = "trcompat_locale_v29/ko_KR.utf8.tzst"
V27_NTOSKRNL_SHA256 = "bac18cca32f701c0315203ab489e2b557b78a2c72cf160256245c6015282c5c8"


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
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def install_ntoskrnl_asset(root: Path, component_dir: Path) -> str:
    source = component_dir / "ntoskrnl.exe"
    if not source.is_file() or source.read_bytes()[:2] != b"MZ":
        raise RuntimeError("v29 ntoskrnl component missing or not PE")
    data = source.read_bytes()
    required = [b"IRP_TRACE begin", b"IRP_UNHANDLED", b"DRIVER_LOAD ZwLoadDriver begin",
                b"DRIVER_LOAD DriverEntry enter", b"DRIVER_LOAD IoCreateDevice created"]
    for marker in required:
        if marker not in data:
            raise RuntimeError(f"v29 ntoskrnl marker absent: {marker!r}")
    lowered = data.lower()
    for forbidden in (b"xhunter", b"xigncode", b"wellbia", b"6d4084", b"talesrunner"):
        if forbidden in lowered:
            raise RuntimeError(f"target-specific marker in v29 ntoskrnl: {forbidden!r}")

    destination = root / "app/src/main/assets" / NTOSKRNL_ASSET
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    os.chmod(destination, 0o644)
    return sha256(destination)


def build_korean_locale_asset(root: Path) -> str:
    rootfs = root / "app/src/main/assets/rootfs.tzst"
    if not rootfs.is_file():
        raise RuntimeError("rootfs asset missing")

    with tempfile.TemporaryDirectory(prefix="tr-v29-ko-locale-") as tmp_name:
        tmp = Path(tmp_name)
        tree = tmp / "tree"
        tree.mkdir()
        subprocess.run([
            "tar", "--use-compress-program=unzstd", "-xf", str(rootfs), "-C", str(tree),
            "./usr/share/i18n",
        ], check=True)
        (tree / "usr/lib/locale").mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["I18NPATH"] = str(tree / "usr/share/i18n")
        subprocess.run([
            "localedef", "--no-archive", f"--prefix={tree}",
            "-i", "ko_KR", "-f", "UTF-8", "ko_KR.UTF-8",
        ], env=env, check=True)

        locale_dir = tree / "usr/lib/locale/ko_KR.utf8"
        required = ["LC_CTYPE", "LC_COLLATE", "LC_TIME", "LC_MESSAGES/SYS_LC_MESSAGES"]
        for rel in required:
            if not (locale_dir / rel).is_file():
                raise RuntimeError(f"compiled Korean locale missing {rel}")

        tar_path = tmp / "ko-locale.tar"
        subprocess.run([
            "tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner", "--mtime=@0",
            "--format=gnu", "-C", str(tree), "-cf", str(tar_path),
            "./usr/lib/locale/ko_KR.utf8",
        ], check=True)
        asset = root / "app/src/main/assets" / LOCALE_ASSET
        asset.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["zstd", "-19", "-f", str(tar_path), "-o", str(asset)], check=True)
        os.chmod(asset, 0o644)
        return sha256(asset)


def update_ntoskrnl_patcher(root: Path, expected_hash: str) -> None:
    path = root / "app/src/main/java/com/winlator/core/TrCompatNtKernelPatcher.java"
    text = path.read_text(encoding="utf-8")
    replacements = {
        'private static final String REVISION = "v28-active-irp-trace-1";':
            'private static final String REVISION = "v29-driver-load-trace-1";',
        'private static final String ASSET = "trcompat_wine_v28/ntoskrnl.exe";':
            f'private static final String ASSET = "{NTOSKRNL_ASSET}";',
        'private static final String BASELINE_SHA256 = "ac89fd958b5a8a0f133cfe412e66a78395828bf3e237dc74868a2e39845f3c6c";':
            f'private static final String BASELINE_SHA256 = "{V27_NTOSKRNL_SHA256}";',
        'private static final String EXPECTED_SHA256 = "bac18cca32f701c0315203ab489e2b557b78a2c72cf160256245c6015282c5c8";':
            f'private static final String EXPECTED_SHA256 = "{expected_hash}";',
        '".trcompat-v28.bak"': '".trcompat-v29.bak"',
        '".trcompat-v28.tmp"': '".trcompat-v29.tmp"',
        '".trcompat-v28.rollback.tmp"': '".trcompat-v29.rollback.tmp"',
    }
    for old, new in replacements.items():
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f"v29 ntoskrnl patcher anchor count {count}: {old}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def write_korean_support(root: Path) -> None:
    java = r'''package com.winlator.core;

import android.content.Context;
import android.system.Os;

import com.winlator.xenvironment.RootFS;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/** Adds a compiled Korean UTF-8 locale and reuses Korean-capable fonts already
 * present on the Android device. Failure is diagnostic-only and never blocks
 * Wine or changes driver/security behavior. */
public final class TrCompatKoreanSupport {
    private static final String REVISION = "v29-korean-support-1";
    private static final String LOCALE_ASSET = "__LOCALE_ASSET__";
    private static final String LOCALE_PROBE = "usr/lib/locale/ko_KR.utf8/LC_CTYPE";
    private static final String FONT_DESTINATION = "usr/share/fonts/trcompat-korean";
    private static final int MAX_FONTS = 4;

    private TrCompatKoreanSupport() {}

    public static void apply(Context context, RootFS rootFS) {
        File root = rootFS.getRootDir();
        TrCompatDiagnostics.trace("KOREAN_SUPPORT_BEGIN revision="+REVISION+" root="+root.getPath());
        try {
            File localeProbe = new File(root, LOCALE_PROBE);
            if (!localeProbe.isFile()) {
                TarCompressorUtils.extract(TarCompressorUtils.Type.ZSTD, context, LOCALE_ASSET, root);
                TrCompatDiagnostics.trace("KOREAN_LOCALE_EXTRACTED asset="+LOCALE_ASSET);
            }
            localeProbe = new File(root, LOCALE_PROBE);
            TrCompatDiagnostics.trace("KOREAN_LOCALE_VERIFY exists="+localeProbe.isFile()+
                    " size="+(localeProbe.isFile() ? localeProbe.length() : -1)+
                    " path="+localeProbe.getPath());
        }
        catch (Throwable error) {
            TrCompatDiagnostics.traceThrowable("KOREAN_LOCALE_EXCEPTION", error);
        }

        try {
            File destination = new File(root, FONT_DESTINATION);
            if (!destination.isDirectory() && !destination.mkdirs()) {
                throw new java.io.IOException("unable to create "+destination.getPath());
            }
            List<File> candidates = collectCandidates();
            int copied = 0;
            for (File source : candidates) {
                if (copied >= MAX_FONTS) break;
                File target = new File(destination, source.getName());
                if (!target.isFile() || target.length() != source.length()) copy(source, target);
                try { Os.chmod(target.getPath(), 0644); } catch (Throwable ignored) {}
                String digest = TrCompatDiagnostics.sha256(target);
                TrCompatDiagnostics.trace("KOREAN_FONT_READY source="+source.getPath()+
                        " destination="+target.getPath()+" size="+target.length()+" sha256="+digest);
                copied++;
            }
            TrCompatDiagnostics.trace("KOREAN_FONT_SUMMARY candidates="+candidates.size()+" copied="+copied);
        }
        catch (Throwable error) {
            TrCompatDiagnostics.traceThrowable("KOREAN_FONT_EXCEPTION", error);
        }
    }

    private static List<File> collectCandidates() {
        List<File> result = new ArrayList<>();
        List<File> roots = Arrays.asList(new File("/system/fonts"), new File("/product/fonts"), new File("/vendor/fonts"));
        for (File root : roots) {
            File[] files = root.listFiles();
            if (files == null) continue;
            Arrays.sort(files, Comparator.comparing(File::getName, String.CASE_INSENSITIVE_ORDER));
            for (File file : files) {
                if (!file.isFile() || !file.canRead()) continue;
                String name = file.getName().toLowerCase(Locale.ROOT);
                boolean font = name.endsWith(".ttf") || name.endsWith(".ttc") || name.endsWith(".otf");
                boolean korean = name.contains("cjk") || name.contains("korean") || name.contains("hangul") ||
                        name.contains("notosanskr") || name.contains("notoserifkr") || name.contains("samsungonekorean") ||
                        name.contains("droidsansfallback");
                if (font && korean) result.add(file);
            }
        }
        return result;
    }

    private static void copy(File source, File destination) throws Exception {
        File temp = new File(destination.getPath()+".tmp");
        if (temp.exists() && !temp.delete()) throw new java.io.IOException("unable to delete "+temp.getPath());
        try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(source));
             BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(temp, false))) {
            byte[] buffer = new byte[128 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            output.flush();
        }
        if (destination.exists() && !destination.delete()) throw new java.io.IOException("unable to replace "+destination.getPath());
        if (!temp.renameTo(destination)) throw new java.io.IOException("unable to install "+destination.getPath());
    }
}
'''.replace("__LOCALE_ASSET__", LOCALE_ASSET)
    path = root / "app/src/main/java/com/winlator/core/TrCompatKoreanSupport.java"
    if path.exists():
        raise RuntimeError(f"unexpected existing Korean support class: {path}")
    path.write_text(java, encoding="utf-8")


def patch_activity(root: Path) -> None:
    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    replace_once(
        activity,
        "import com.winlator.core.TrCompatNtKernelPatcher;\n",
        "import com.winlator.core.TrCompatNtKernelPatcher;\nimport com.winlator.core.TrCompatKoreanSupport;\n",
    )
    replace_once(
        activity,
        '''            TrCompatNtKernelPatcher.apply(this, rootFS);\n            trTrace("NTOSKRNL_PATCH_RETURN");\n''',
        '''            TrCompatKoreanSupport.apply(this, rootFS);\n            trTrace("KOREAN_SUPPORT_RETURN");\n            TrCompatNtKernelPatcher.apply(this, rootFS);\n            trTrace("NTOSKRNL_PATCH_RETURN");\n''',
    )
    replace_once(
        activity,
        '''            if (shortcut != null) envVars.putAll(shortcut.getExtra("envVars"));\n            if (!envVars.has("WINEESYNC")) envVars.put("WINEESYNC", "1");\n''',
        '''            if (shortcut != null) envVars.putAll(shortcut.getExtra("envVars"));\n            if (!envVars.has("LANG")) envVars.put("LANG", "ko_KR.UTF-8");\n            if (!envVars.has("LC_ALL")) envVars.put("LC_ALL", "ko_KR.UTF-8");\n            if (!envVars.has("WINEESYNC")) envVars.put("WINEESYNC", "1");\n''',
    )


def patch_metadata_and_diagnostics(root: Path) -> None:
    replace_once(root / "app/build.gradle",
                 'versionName "11.1-trcompat28-irp-trace-active"',
                 'versionName "11.1-trcompat29-driver-load-ko"')
    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v28_IRP_TRACE_ACTIVE.zip": "TR_DIAG_v29_DRIVER_LOAD_KO.zip",
        "DIAGNOSTICS_RESET version=28-irp-trace-active": "DIAGNOSTICS_RESET version=29-driver-load-ko",
        "TalesRunner KR XIGNCODE fingerprint v28 active IRP trace":
            "Generic Wine driver-load and Korean locale diagnostics v29",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"v29 diagnostics anchor missing: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")


def write_report(root: Path, ntoskrnl_hash: str, locale_hash: str) -> None:
    (root / "v29-driver-load-ko-report.txt").write_text(
        "schema=trcompat.v29.driver-load-ko.v1\n"
        "rootfs_reinstall_forced=false\n"
        "container_home_preserved=true\n"
        f"accepted_existing_ntoskrnl_sha256={V27_NTOSKRNL_SHA256}\n"
        f"required_active_ntoskrnl_sha256={ntoskrnl_hash}\n"
        f"ntoskrnl_asset=assets/{NTOSKRNL_ASSET}\n"
        f"korean_locale_asset=assets/{LOCALE_ASSET}\n"
        f"korean_locale_asset_sha256={locale_hash}\n"
        "korean_fonts_source=device_system_partitions_only\n"
        "windows_acp_registry_changed=false\n"
        "driver_or_ioctl_status_changed=false\n",
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v29_patch.py WINLATOR_APP_DIR COMPONENT_DIR", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    ntoskrnl_hash = install_ntoskrnl_asset(root, component_dir)
    locale_hash = build_korean_locale_asset(root)
    update_ntoskrnl_patcher(root, ntoskrnl_hash)
    write_korean_support(root)
    patch_activity(root)
    patch_metadata_and_diagnostics(root)
    write_report(root, ntoskrnl_hash, locale_hash)

    print(f"Applied v29 driver-load trace and Korean support: ntoskrnl={ntoskrnl_hash} locale={locale_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
