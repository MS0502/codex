#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v12_patch as v12


REVISION = "v15-lowload-process-driver-1"
WINEDEBUG_VALUE = "-all,+timestamp,+pid,+tid,+process,+service,+ntoskrnl,+seh"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v15(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat12-baseline"',
        'versionName "11.1-trcompat15-lowload"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v12_BASELINE.zip": "TR_DIAG_v15_LOWLOAD.zip",
        "DIAGNOSTICS_RESET version=12-baseline": "DIAGNOSTICS_RESET version=15-lowload",
        "TalesRunner KR XIGNCODE fingerprint v12 baseline": "TalesRunner KR XIGNCODE fingerprint v15 low-load",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v15 anchor not found: {old}")
        text = text.replace(old, new)

    import_anchor = "import java.security.MessageDigest;\n"
    import_replacement = (
        "import java.security.MessageDigest;\n"
        "import java.nio.charset.StandardCharsets;\n"
        "import java.util.concurrent.atomic.AtomicBoolean;\n"
    )
    if import_anchor not in text:
        raise RuntimeError("diagnostics import anchor not found")
    text = text.replace(import_anchor, import_replacement, 1)

    old_fields = '''    private static final AtomicInteger PROCESS_LINE_COUNT = new AtomicInteger();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File zipFile;
'''
    new_fields = '''    private static final AtomicInteger PROCESS_LINE_COUNT = new AtomicInteger();
    private static final AtomicBoolean LOWLOAD_COLLECTOR_STARTED = new AtomicBoolean();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File wellbiaLowloadFile;
    private static File zipFile;
'''
    if old_fields not in text:
        raise RuntimeError("diagnostics field anchor not found")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        traceFile = new File(parentDir, "startup_trace.txt");
        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        zipFile = new File(parentDir, "TR_DIAG_v15_LOWLOAD.zip");
'''
    new_paths = '''        traceFile = new File(parentDir, "startup_trace.txt");
        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        wellbiaLowloadFile = new File(parentDir, "wellbia_lowload.txt");
        zipFile = new File(parentDir, "TR_DIAG_v15_LOWLOAD.zip");
'''
    if old_paths not in text:
        raise RuntimeError("diagnostics path anchor not found")
    text = text.replace(old_paths, new_paths, 1)

    old_reset = '''            PROCESS_LINE_COUNT.set(0);
            traceFile.delete();
            fingerprintFile.delete();
            zipFile.delete();
'''
    new_reset = '''            PROCESS_LINE_COUNT.set(0);
            LOWLOAD_COLLECTOR_STARTED.set(false);
            traceFile.delete();
            fingerprintFile.delete();
            wellbiaLowloadFile.delete();
            zipFile.delete();
'''
    if old_reset not in text:
        raise RuntimeError("diagnostics reset anchor not found")
    text = text.replace(old_reset, new_reset, 1)

    process_method_anchor = '''    public static void traceProcessLine(String stream, String line) {
        int index = PROCESS_LINE_COUNT.incrementAndGet();
        if (index > MAX_PROCESS_LINES) {
            if (index == MAX_PROCESS_LINES + 1) trace("PROCESS_OUTPUT_TRUNCATED limit="+MAX_PROCESS_LINES);
            return;
        }
        String value = sanitizeProcessLine(line == null ? "null" : line);
        if (value.length() > MAX_LINE_CHARS) value = value.substring(0, MAX_LINE_CHARS)+"...[truncated]";
        trace("PROCESS_"+stream+" "+value);
    }
'''
    focused_methods = process_method_anchor + r'''

    public static String sanitizeExternal(String value) {
        return sanitizeProcessLine(value == null ? "null" : value);
    }

    public static void traceFocusedProcessLine(String stream, String line) {
        String value = sanitizeProcessLine(line == null ? "null" : line);
        String lower = value.toLowerCase(Locale.US);
        boolean relevant = lower.contains("talesrunner.exe") || lower.contains("trgame.exe")
                || lower.contains("xldr_") || lower.contains("xign") || lower.contains("xhunter")
                || lower.contains(".xem") || lower.contains("ntcreateuserprocess")
                || lower.contains("createprocess") || lower.contains("process exit")
                || lower.contains("terminateprocess") || lower.contains("exit code")
                || lower.contains("service") || lower.contains("driver")
                || lower.contains("ntoskrnl") || lower.contains("exception")
                || lower.contains("status_") || lower.contains("err:");
        if (!relevant) return;

        int index = PROCESS_LINE_COUNT.incrementAndGet();
        if (index > 8000) {
            if (index == 8001) trace("FOCUSED_OUTPUT_TRUNCATED limit=8000");
            return;
        }
        if (value.length() > MAX_LINE_CHARS) value = value.substring(0, MAX_LINE_CHARS)+"...[truncated]";
        trace("FOCUSED_"+stream+" "+value);
    }

    private static boolean lowloadLogCandidate(File file) {
        if (file == null || !file.isFile()) return false;
        String name = file.getName().toLowerCase(Locale.US);
        return name.endsWith(".log") || name.endsWith(".txt");
    }

    private static boolean keywordString(String value) {
        String lower = value.toLowerCase(Locale.US);
        return lower.contains("e019") || lower.contains("error") || lower.contains("fail")
                || lower.contains("xign") || lower.contains("xhunter")
                || lower.contains("driver") || lower.contains("status")
                || lower.contains("code") || lower.contains("kernel");
    }

    private static List<String> extractSafeKeywordStrings(File file) {
        List<String> out = new ArrayList<>();
        final int limit = 256 * 1024;
        try (InputStream input = new BufferedInputStream(new FileInputStream(file))) {
            byte[] data = new byte[limit];
            int total = 0;
            while (total < limit) {
                int read = input.read(data, total, limit - total);
                if (read < 0) break;
                total += read;
            }

            StringBuilder ascii = new StringBuilder();
            for (int i = 0; i < total; i++) {
                int c = data[i] & 0xff;
                if (c >= 32 && c <= 126) ascii.append((char)c);
                else {
                    if (ascii.length() >= 4) {
                        String safe = sanitizeProcessLine(ascii.toString());
                        if (keywordString(safe)) out.add(safe);
                    }
                    ascii.setLength(0);
                }
                if (out.size() >= 100) break;
            }
            if (ascii.length() >= 4 && out.size() < 100) {
                String safe = sanitizeProcessLine(ascii.toString());
                if (keywordString(safe)) out.add(safe);
            }

            StringBuilder utf16 = new StringBuilder();
            for (int i = 0; i + 1 < total && out.size() < 100; i += 2) {
                int c = data[i] & 0xff;
                int hi = data[i + 1] & 0xff;
                if (hi == 0 && c >= 32 && c <= 126) utf16.append((char)c);
                else {
                    if (utf16.length() >= 4) {
                        String safe = sanitizeProcessLine(utf16.toString());
                        if (keywordString(safe)) out.add(safe);
                    }
                    utf16.setLength(0);
                }
            }
            if (utf16.length() >= 4 && out.size() < 100) {
                String safe = sanitizeProcessLine(utf16.toString());
                if (keywordString(safe)) out.add(safe);
            }
        }
        catch (Exception e) {
            out.add("[READ_FAILED "+e.getClass().getSimpleName()+":"+String.valueOf(e.getMessage())+"]");
        }
        return out;
    }

    public static void collectWellbiaLowload(File rootDir, String stage) {
        ensurePaths();
        File dir = new File(rootDir, "home/xuser/.wine/drive_c/users/xuser/AppData/Local/WELLBIA");
        List<File> files = new ArrayList<>();
        File[] children = dir.listFiles();
        if (children != null) {
            Arrays.sort(children, Comparator.comparing(File::getName, String.CASE_INSENSITIVE_ORDER));
            for (File child : children) if (lowloadLogCandidate(child)) files.add(child);
        }

        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(wellbiaLowloadFile, true)) {
                writer.write("===== stage="+stage+" time="+System.currentTimeMillis()+" dir="+dir.getPath()+" exists="+dir.isDirectory()+" count="+files.size()+" =====\n");
                for (File file : files) {
                    writer.write(describeFile("WELLBIA_LOG", file, true));
                    writer.write(" modified="+file.lastModified()+"\n");
                    List<String> strings = extractSafeKeywordStrings(file);
                    writer.write("keyword_strings="+strings.size()+"\n");
                    for (String value : strings) {
                        if (value.length() > MAX_LINE_CHARS) value = value.substring(0, MAX_LINE_CHARS)+"...[truncated]";
                        writer.write("STRING="+value+"\n");
                    }
                }
                writer.flush();
                trace("WELLBIA_LOWLOAD_CAPTURE stage="+stage+" count="+files.size());
            }
            catch (Exception e) {
                traceThrowable("WELLBIA_LOWLOAD_EXCEPTION", e);
            }
        }
    }

    public static void startLowloadCollector(final File rootDir) {
        if (rootDir == null || !LOWLOAD_COLLECTOR_STARTED.compareAndSet(false, true)) return;
        Thread thread = new Thread(() -> {
            int[] waits = {0, 30, 60, 90, 120, 180};
            int previous = 0;
            for (int seconds : waits) {
                try {
                    if (seconds > previous) Thread.sleep((seconds - previous) * 1000L);
                }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                collectWellbiaLowload(rootDir, "t+"+seconds+"s");
                exportZip();
                previous = seconds;
            }
        }, "tr-lowload-collector");
        thread.setDaemon(true);
        thread.start();
        trace("LOWLOAD_COLLECTOR_STARTED root="+rootDir.getPath());
    }
'''
    if process_method_anchor not in text:
        raise RuntimeError("diagnostics process method anchor not found")
    text = text.replace(process_method_anchor, focused_methods, 1)

    old_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
'''
    new_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
'''
    if old_zip not in text:
        raise RuntimeError("diagnostics zip anchor not found")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")

    process = root / "app/src/main/java/com/winlator/core/ProcessHelper.java"
    text = process.read_text(encoding="utf-8")
    replacements = {
        'TrCompatDiagnostics.trace("PROCESS_HELPER_ENTER command="+command);': 'TrCompatDiagnostics.trace("PROCESS_HELPER_ENTER command="+TrCompatDiagnostics.sanitizeExternal(command));',
        'TrCompatDiagnostics.trace("PROCESS_ARGV="+java.util.Arrays.toString(argv));': 'TrCompatDiagnostics.trace("PROCESS_ARGV="+TrCompatDiagnostics.sanitizeExternal(java.util.Arrays.toString(argv)));',
        '                    TrCompatDiagnostics.traceProcessLine(streamName, line);': '                    TrCompatDiagnostics.traceFocusedProcessLine(streamName, line);',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"ProcessHelper anchor not found: {old}")
        text = text.replace(old, new, 1)
    process.write_text(text, encoding="utf-8")

    guest = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    text = guest.read_text(encoding="utf-8")
    old_command_trace = '        TrCompatDiagnostics.trace("COMMAND="+command);\n'
    new_command_trace = '        TrCompatDiagnostics.trace("COMMAND="+TrCompatDiagnostics.sanitizeExternal(command));\n'
    if old_command_trace not in text:
        raise RuntimeError("guest command trace anchor not found")
    text = text.replace(old_command_trace, new_command_trace, 1)
    guest.write_text(text, encoding="utf-8")

    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    text = activity.read_text(encoding="utf-8")
    old_sync = '''            envVars.put("WINEESYNC", "0");
            envVars.put("WINEFSYNC", "0");
            trTrace("SYNC_COMPAT_FORCED WINEESYNC=0 WINEFSYNC=0");
'''
    new_sync = f'''            envVars.put("WINEESYNC", "0");
            envVars.put("WINEFSYNC", "0");
            String trWineDebug = "{WINEDEBUG_VALUE}";
            envVars.put("WINEDEBUG", trWineDebug);
            trTrace("SYNC_COMPAT_FORCED WINEESYNC=0 WINEFSYNC=0");
            trTrace("WINEDEBUG_LOWLOAD="+trWineDebug);
'''
    if old_sync not in text:
        raise RuntimeError("WINEDEBUG low-load anchor not found")
    text = text.replace(old_sync, new_sync, 1)

    old_root = '''            trTrace("ROOTFS root="+rootFS.getRootDir().getPath()+" winePath="+rootFS.getWinePath());
'''
    new_root = old_root + '''            TrCompatDiagnostics.startLowloadCollector(rootFS.getRootDir());
'''
    if old_root not in text:
        raise RuntimeError("rootfs collector anchor not found")
    text = text.replace(old_root, new_root, 1)
    activity.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")
    old_revision = 'private static final String REVISION = "v12-official-baseline-1";'
    if old_revision not in text:
        raise RuntimeError("v12 runtime revision anchor not found")
    text = text.replace(old_revision, f'private static final String REVISION = "{REVISION}";', 1)
    text = text.replace(".trcompat-v12.tmp", ".trcompat-v15.tmp")
    patcher.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v15_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v12.__file__).resolve()), str(root), str(component_dir)]
        result = v12.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_v15(root)
    print("Winlator TR Compat v15 low-load diagnostics applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
