#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import apply_v7_patch as v7


REVISION = "v8-wine-rootfs-path-1"
COMPONENTS = (
    ("ntdll.so", "lib/wine/x86_64-unix/ntdll.so"),
    ("wow64.dll", "lib/wine/x86_64-windows/wow64.dll"),
    ("wineserver", "bin/wineserver"),
    ("nsiproxy.so", "lib/wine/x86_64-unix/nsiproxy.so"),
)


def replace_once(path: Path, old: str, new: str) -> None:
    v7.replace_once(path, old, new)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_versions(root: Path) -> None:
    replace_once(root / "app/build.gradle", 'versionName "11.1-trcompat7"', 'versionName "11.1-trcompat8"')

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v7.zip": "TR_DIAG_v8.zip",
        "DIAGNOSTICS_RESET version=7": "DIAGNOSTICS_RESET version=8",
        "TalesRunner KR XIGNCODE fingerprint v7": "TalesRunner KR XIGNCODE fingerprint v8",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v8 anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")


def prepare_wine_assets(root: Path, component_dir: Path) -> dict[str, str]:
    asset_dir = root / "app/src/main/assets/trcompat_wine_v8"
    asset_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}

    for filename, _ in COMPONENTS:
        source = component_dir / filename
        if not source.is_file():
            raise RuntimeError(f"missing v8 Wine component: {source}")
        destination = asset_dir / filename
        shutil.copy2(source, destination)
        hashes[filename] = sha256(destination)
        print(f"{filename} sha256={hashes[filename]} size={destination.stat().st_size}")

    return hashes


def write_runtime_patcher(root: Path, hashes: dict[str, str]) -> None:
    items = []
    for filename, relative in COMPONENTS:
        items.append(
            f'        new Item("trcompat_wine_v8/{filename}", "{relative}", "{hashes[filename]}")'
        )
    item_block = ",\n".join(items)

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
 * Applies ordinary Wine runtime compatibility components for the separate
 * com.winlator.trcompat package. Game and security-module files are untouched.
 */
public final class TrCompatWinePatcher {
    private static final String REVISION = "__REVISION__";

    private static final class Item {
        final String asset;
        final String relativePath;
        final String expectedSha256;

        Item(String asset, String relativePath, String expectedSha256) {
            this.asset = asset;
            this.relativePath = relativePath;
            this.expectedSha256 = expectedSha256;
        }
    }

    private static final Item[] ITEMS = {
__ITEMS__
    };

    private TrCompatWinePatcher() {}

    public static void apply(Context context, RootFS rootFS) {
        String winePath = rootFS.getWinePath();
        if (winePath == null || !winePath.contains("wine-10.10-trcompat")) {
            TrCompatDiagnostics.trace("WINE_RUNTIME_PATCH_SKIP winePath="+String.valueOf(winePath));
            return;
        }

        File wineRoot = new File(rootFS.getRootDir().getPath()+winePath);
        TrCompatDiagnostics.trace("WINE_RUNTIME_PATCH_BEGIN revision="+REVISION+" root="+wineRoot.getPath());

        try {
            for (Item item : ITEMS) applyOne(context, wineRoot, item);
            File marker = new File(wineRoot, ".trcompat-runtime-"+REVISION);
            try (FileOutputStream output = new FileOutputStream(marker, false)) {
                output.write((REVISION+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));
                output.flush();
            }
            TrCompatDiagnostics.trace("WINE_RUNTIME_PATCH_COMPLETE marker="+marker.getPath());
        }
        catch (Throwable error) {
            TrCompatDiagnostics.traceThrowable("WINE_RUNTIME_PATCH_EXCEPTION", error);
            TrCompatDiagnostics.exportZip();
            throw new RuntimeException("Unable to apply TR Compat Wine runtime components", error);
        }
    }

    private static void applyOne(Context context, File wineRoot, Item item) throws Exception {
        File target = new File(wineRoot, item.relativePath);
        if (!target.isFile()) throw new java.io.IOException("missing target "+target.getPath());

        String currentSha = TrCompatDiagnostics.sha256(target);
        TrCompatDiagnostics.trace("WINE_COMPONENT_BEFORE path="+target.getPath()+" sha256="+currentSha);
        if (item.expectedSha256.equalsIgnoreCase(currentSha)) {
            TrCompatDiagnostics.trace("WINE_COMPONENT_ALREADY_CURRENT path="+target.getPath());
            return;
        }

        int mode = 0771;
        try {
            mode = (int)(Os.stat(target.getPath()).st_mode & 0777);
            if (mode == 0) mode = 0771;
        }
        catch (Throwable ignored) {}

        File backup = new File(target.getPath()+".trcompat-v7.bak");
        if (!backup.exists()) {
            copyFile(target, backup);
            Os.chmod(backup.getPath(), mode);
            TrCompatDiagnostics.trace("WINE_COMPONENT_BACKUP path="+backup.getPath()+" sha256="+TrCompatDiagnostics.sha256(backup));
        }

        File temp = new File(target.getPath()+".trcompat-v8.tmp");
        if (temp.exists() && !temp.delete()) throw new java.io.IOException("unable to remove temp "+temp.getPath());

        try (InputStream input = new BufferedInputStream(context.getAssets().open(item.asset));
             BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(temp, false))) {
            byte[] buffer = new byte[128 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            output.flush();
        }

        String tempSha = TrCompatDiagnostics.sha256(temp);
        if (!item.expectedSha256.equalsIgnoreCase(tempSha)) {
            temp.delete();
            throw new java.io.IOException("asset hash mismatch for "+item.asset+" actual="+tempSha);
        }

        Os.chmod(temp.getPath(), mode);
        Os.rename(temp.getPath(), target.getPath());

        String finalSha = TrCompatDiagnostics.sha256(target);
        if (!item.expectedSha256.equalsIgnoreCase(finalSha)) {
            throw new java.io.IOException("installed hash mismatch for "+target.getPath()+" actual="+finalSha);
        }
        TrCompatDiagnostics.trace("WINE_COMPONENT_REPLACED path="+target.getPath()+" sha256="+finalSha+" mode="+Integer.toOctalString(mode));
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
}
'''
    java = java.replace("__REVISION__", REVISION).replace("__ITEMS__", item_block)
    path = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    path.write_text(java, encoding="utf-8")


def patch_runtime_call_and_diagnostics(root: Path, hashes: dict[str, str]) -> None:
    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    replace_once(
        activity,
        "import com.winlator.core.TrCompatDiagnostics;\n",
        "import com.winlator.core.TrCompatDiagnostics;\nimport com.winlator.core.TrCompatWinePatcher;\n",
    )
    replace_once(
        activity,
        '''            if (wineInfo != WineInfo.MAIN_WINE_INFO) rootFS.setWinePath(wineInfo.path);
            trTrace("ROOTFS root="+rootFS.getRootDir().getPath()+" winePath="+rootFS.getWinePath());
''',
        '''            if (wineInfo != WineInfo.MAIN_WINE_INFO) rootFS.setWinePath(wineInfo.path);
            trTrace("ROOTFS root="+rootFS.getRootDir().getPath()+" winePath="+rootFS.getWinePath());
            TrCompatWinePatcher.apply(this, rootFS);
            trTrace("WINE_RUNTIME_PATCH_RETURN");
''',
    )

    guest = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    text = guest.read_text(encoding="utf-8")
    old_ntdll = 'TrCompatDiagnostics.trace("NTDLL_EXPECTED_SHA256=6f4f2250dc7e8453bba2c164c49d47aa3f492f57d8e178a6cf0b4ddb45b821f9");'
    old_wow64 = 'TrCompatDiagnostics.trace("WOW64_EXPECTED_SHA256=a100b12aa2c4b2151203f881b3b48e9a5af0e000526ccc31ed31de3c72aebe71");'
    if old_ntdll not in text or old_wow64 not in text:
        raise RuntimeError("v8 expected-hash anchors not found")
    text = text.replace(
        old_ntdll,
        f'TrCompatDiagnostics.trace("NTDLL_EXPECTED_SHA256={hashes["ntdll.so"]}");',
        1,
    )
    text = text.replace(
        old_wow64,
        f'TrCompatDiagnostics.trace("WOW64_EXPECTED_SHA256={hashes["wow64.dll"]}");',
        1,
    )
    text = text.replace(
        '        File wow64File = new File(wineRoot, "lib/wine/x86_64-windows/wow64.dll");\n',
        '        File wow64File = new File(wineRoot, "lib/wine/x86_64-windows/wow64.dll");\n'
        '        File nsiproxyFile = new File(wineRoot, "lib/wine/x86_64-unix/nsiproxy.so");\n',
        1,
    )
    text = text.replace(
        f'        TrCompatDiagnostics.trace("WOW64_EXPECTED_SHA256={hashes["wow64.dll"]}");\n',
        f'        TrCompatDiagnostics.trace("WOW64_EXPECTED_SHA256={hashes["wow64.dll"]}");\n'
        f'        TrCompatDiagnostics.trace("WINESERVER_EXPECTED_SHA256={hashes["wineserver"]}");\n'
        '        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("NSIPROXY_SO", nsiproxyFile, true));\n'
        f'        TrCompatDiagnostics.trace("NSIPROXY_EXPECTED_SHA256={hashes["nsiproxy.so"]}");\n',
        1,
    )
    guest.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v8_patch.py WINLATOR_APP_DIR WINE_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    v7.v6.patch_base_v5(root)
    v7.v6.write_diagnostics_class(root)
    v7.v6.patch_process_helper(root)
    v7.v6.patch_guest_launcher(root)
    v7.v6.patch_activity(root)
    v7.patch_versions(root)
    v7.prepare_box64_and_native_fallback(root)
    v7.patch_box64_refresh(root)
    v7.patch_three_stage_launcher(root)

    patch_versions(root)
    hashes = prepare_wine_assets(root, component_dir)
    write_runtime_patcher(root, hashes)
    patch_runtime_call_and_diagnostics(root, hashes)

    print("Winlator TR Compat v8 Wine runtime path repair patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
