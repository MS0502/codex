#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v29_patch as common

REVISION = "v30-x3-boundary-font-1"
OLD_WINEDEBUG = "-all,+timestamp,+pid,+tid,+process,+server,+service,+ntoskrnl"
NEW_WINEDEBUG = OLD_WINEDEBUG + ",+loaddll,+ver"


def patch_korean_support(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/core/TrCompatKoreanSupport.java"
    text = path.read_text(encoding="utf-8")

    replacements = {
        'private static final String REVISION = "v29-korean-support-1";':
            'private static final String REVISION = "v30-windows-fonts-1";',
        '            TrCompatDiagnostics.trace("KOREAN_FONT_SUMMARY candidates="+candidates.size()+" copied="+copied);\n':
            '            TrCompatDiagnostics.trace("KOREAN_FONT_SUMMARY candidates="+candidates.size()+" copied="+copied);\n'
            '            installWineFontsAndRegistry(root, candidates);\n',
    }
    for old, new in replacements.items():
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f"{REVISION}: Korean support anchor count {count}: {old!r}")
        text = text.replace(old, new, 1)

    method_anchor = "    private static List<File> collectCandidates() {\n"
    methods = r'''    private static void backupOnce(File source, File backup) throws Exception {
        if (!source.isFile() || backup.exists()) return;
        copy(source, backup);
        TrCompatDiagnostics.trace("KOREAN_REGISTRY_BACKUP source="+source.getPath()+
                " backup="+backup.getPath()+" sha256="+TrCompatDiagnostics.sha256(backup));
    }

    private static void restoreBackup(File backup, File target) {
        try {
            if (!backup.isFile()) return;
            copy(backup, target);
            TrCompatDiagnostics.trace("KOREAN_REGISTRY_ROLLBACK target="+target.getPath()+
                    " sha256="+TrCompatDiagnostics.sha256(target));
        }
        catch (Throwable rollbackError) {
            TrCompatDiagnostics.traceThrowable("KOREAN_REGISTRY_ROLLBACK_EXCEPTION", rollbackError);
        }
    }

    private static void installWineFontsAndRegistry(File root, List<File> candidates) {
        File prefix = new File(root, "home/xuser/.wine");
        File windowsFonts = new File(prefix, "drive_c/windows/Fonts");
        File systemReg = new File(prefix, "system.reg");
        File userReg = new File(prefix, "user.reg");
        File systemBackup = new File(prefix, "system.reg.trcompat-v30.bak");
        File userBackup = new File(prefix, "user.reg.trcompat-v30.bak");

        try {
            if (!windowsFonts.isDirectory() && !windowsFonts.mkdirs())
                throw new java.io.IOException("unable to create "+windowsFonts.getPath());

            File noto = null;
            File ttf = null;
            for (File source : candidates) {
                String lower = source.getName().toLowerCase(Locale.ROOT);
                File target = new File(windowsFonts, source.getName());
                if (!target.isFile() || target.length() != source.length()) copy(source, target);
                try { Os.chmod(target.getPath(), 0644); } catch (Throwable ignored) {}
                TrCompatDiagnostics.trace("KOREAN_WINDOWS_FONT_READY source="+source.getPath()+
                        " destination="+target.getPath()+" size="+target.length()+
                        " sha256="+TrCompatDiagnostics.sha256(target));
                if (lower.equals("notosanscjk-regular.ttc")) noto = target;
                if (ttf == null && lower.endsWith(".ttf")) ttf = target;
            }

            if (noto == null && ttf == null)
                throw new java.io.IOException("no Korean font candidate reached Windows Fonts");

            backupOnce(systemReg, systemBackup);
            backupOnce(userReg, userBackup);

            final String face = noto != null ? "Noto Sans CJK KR" : "SECCJK";
            final String fontFile = noto != null ? noto.getName() : ttf.getName();
            final String fontsKey = "Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts";
            final String substitutesKey = "Software\\Microsoft\\Windows NT\\CurrentVersion\\FontSubstitutes";
            final String replacementsKey = "Software\\Wine\\Fonts\\Replacements";

            try (WineRegistryEditor editor = new WineRegistryEditor(systemReg)) {
                editor.setStringValue(fontsKey, "TrCompat Korean UI (TrueType)", fontFile);
                editor.setStringValues(substitutesKey,
                        new String[]{"Gulim", face},
                        new String[]{"굴림", face},
                        new String[]{"Dotum", face},
                        new String[]{"돋움", face},
                        new String[]{"Batang", face},
                        new String[]{"바탕", face},
                        new String[]{"Malgun Gothic", face},
                        new String[]{"맑은 고딕", face},
                        new String[]{"MS Shell Dlg", face},
                        new String[]{"MS Shell Dlg 2", face});
            }

            try (WineRegistryEditor editor = new WineRegistryEditor(userReg)) {
                editor.setStringValues(replacementsKey,
                        new String[]{"Arial", face},
                        new String[]{"Tahoma", face},
                        new String[]{"MS Sans Serif", face},
                        new String[]{"System", face},
                        new String[]{"Helv", face});
            }

            TrCompatDiagnostics.trace("KOREAN_WINDOWS_FONT_REGISTRY face="+face+
                    " file="+fontFile+" system_reg_sha256="+TrCompatDiagnostics.sha256(systemReg)+
                    " user_reg_sha256="+TrCompatDiagnostics.sha256(userReg));
        }
        catch (Throwable error) {
            TrCompatDiagnostics.traceThrowable("KOREAN_WINDOWS_FONT_EXCEPTION", error);
            restoreBackup(systemBackup, systemReg);
            restoreBackup(userBackup, userReg);
        }
    }

'''
    if text.count(method_anchor) != 1:
        raise RuntimeError(f"{REVISION}: collectCandidates anchor missing")
    text = text.replace(method_anchor, methods + method_anchor, 1)
    path.write_text(text, encoding="utf-8")


def patch_activity(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    text = path.read_text(encoding="utf-8")
    if text.count(OLD_WINEDEBUG) != 1:
        raise RuntimeError(f"{REVISION}: expected one v29 WINEDEBUG value")
    text = text.replace(OLD_WINEDEBUG, NEW_WINEDEBUG, 1)
    path.write_text(text, encoding="utf-8")


def patch_diagnostics(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = path.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v29_DRIVER_LOAD_KO.zip": "TR_DIAG_v30_X3_BOUNDARY_FONT.zip",
        "DIAGNOSTICS_RESET version=29-driver-load-ko": "DIAGNOSTICS_RESET version=30-x3-boundary-font",
        "Generic Wine driver-load and Korean locale diagnostics v29":
            "Generic module/service boundary and Windows Korean font diagnostics v30",
        '                || lower.contains(".xem") || lower.contains("ntcreateuserprocess")\n':
            '                || lower.contains(".xem") || lower.contains("loaddll")\n'
            '                || lower.contains("loadlibrary") || lower.contains("getversion")\n'
            '                || lower.contains("openscmanager") || lower.contains("createservice")\n'
            '                || lower.contains("openservice") || lower.contains("startservice")\n'
            '                || lower.contains("queryservicestatus") || lower.contains("controlservice")\n'
            '                || lower.contains("adjusttokenprivileges") || lower.contains("ntcreateuserprocess")\n',
    }
    for old, new in replacements.items():
        count = text.count(old)
        if count < 1:
            raise RuntimeError(f"{REVISION}: diagnostics anchor absent: {old!r}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def patch_metadata(root: Path) -> None:
    path = root / "app/build.gradle"
    text = path.read_text(encoding="utf-8")
    for old, new in (
        ('versionName "11.1-trcompat29-driver-load-ko"',
         'versionName "11.1-trcompat30-x3-boundary-font"'),
        ('versionCode 28', 'versionCode 30'),
    ):
        if text.count(old) != 1:
            raise RuntimeError(f"{REVISION}: Gradle anchor count {text.count(old)}: {old}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def write_report(root: Path) -> None:
    (root / "v30-x3-boundary-font-report.txt").write_text(
        "schema=trcompat.v30.x3-boundary-font.v1\n"
        "baseline=v29-exact-assets\n"
        "rootfs_reinstall_forced=false\n"
        "container_home_preserved=true\n"
        "wine_debug_added=loaddll,ver\n"
        "windows_fonts_source=device_system_partitions_only\n"
        "windows_font_registry_backup=true\n"
        "windows_font_registry_rollback_on_failure=true\n"
        "game_or_protection_files_changed=false\n"
        "driver_or_ioctl_status_changed=false\n",
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_v30_boundary_font_patch.py WINLATOR_APP_DIR", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch_korean_support(root)
    patch_activity(root)
    patch_diagnostics(root)
    patch_metadata(root)
    write_report(root)

    required = (
        "TR_DIAG_v30_X3_BOUNDARY_FONT.zip",
        "KOREAN_WINDOWS_FONT_REGISTRY",
        "+loaddll,+ver",
        'versionName "11.1-trcompat30-x3-boundary-font"',
    )
    joined = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (
        root / "app/build.gradle",
        root / "app/src/main/java/com/winlator/XServerDisplayActivity.java",
        root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java",
        root / "app/src/main/java/com/winlator/core/TrCompatKoreanSupport.java",
    ))
    for marker in required:
        if marker not in joined:
            raise RuntimeError(f"{REVISION}: final marker missing: {marker}")

    print(f"Applied {REVISION}; no protected result or payload was modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
