#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v13_patch as v13


WINEDEBUG_V13 = (
    "-all,err+all,warn+all,fixme+all,+timestamp,+pid,+tid,"
    "+process,+module,+loaddll,+file,+reg,+winhttp,+wininet,"
    "+winsock,+schannel,+crypt,+seh"
)
WINEDEBUG_V14 = (
    "-all,err+all,warn+all,+timestamp,+pid,+tid,"
    "+process,+file,+reg,+ntoskrnl,+service,+server,+seh"
)


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v14(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat13-xign-diag"',
        'versionName "11.1-trcompat14-wellbia-log"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v13_XIGN.zip": "TR_DIAG_v14_WELLBIA.zip",
        "DIAGNOSTICS_RESET version=13-xign": "DIAGNOSTICS_RESET version=14-wellbia",
        "TalesRunner KR XIGNCODE fingerprint v13 diagnostics": "TalesRunner KR XIGNCODE fingerprint v14 Wellbia log capture",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v14 anchor not found: {old}")
        text = text.replace(old, new)

    import_anchor = "import java.security.MessageDigest;\n"
    import_replacement = (
        "import java.security.MessageDigest;\n"
        "import java.nio.charset.StandardCharsets;\n"
        "import java.util.HashSet;\n"
        "import java.util.Set;\n"
        "import java.util.concurrent.atomic.AtomicBoolean;\n"
    )
    if import_anchor not in text:
        raise RuntimeError("diagnostics import anchor not found")
    text = text.replace(import_anchor, import_replacement, 1)

    old_fields = '''    private static final AtomicInteger WINE_DEBUG_LINE_COUNT = new AtomicInteger();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File wineDebugFile;
    private static File zipFile;
'''
    new_fields = '''    private static final AtomicInteger WINE_DEBUG_LINE_COUNT = new AtomicInteger();
    private static final AtomicBoolean WELLBIA_COLLECTOR_STARTED = new AtomicBoolean();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File wineDebugFile;
    private static File wellbiaCaptureFile;
    private static File wellbiaLogsFile;
    private static File zipFile;
'''
    if old_fields not in text:
        raise RuntimeError("diagnostics field anchor not found")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        wineDebugFile = new File(parentDir, "wine_api_trace.txt");
        zipFile = new File(parentDir, "TR_DIAG_v14_WELLBIA.zip");
'''
    new_paths = '''        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        wineDebugFile = new File(parentDir, "wine_api_trace.txt");
        wellbiaCaptureFile = new File(parentDir, "wellbia_capture.txt");
        wellbiaLogsFile = new File(parentDir, "wellbia_sanitized_logs.txt");
        zipFile = new File(parentDir, "TR_DIAG_v14_WELLBIA.zip");
'''
    if old_paths not in text:
        raise RuntimeError("diagnostics path anchor not found")
    text = text.replace(old_paths, new_paths, 1)

    old_reset = '''            WINE_DEBUG_LINE_COUNT.set(0);
            traceFile.delete();
            fingerprintFile.delete();
            wineDebugFile.delete();
            zipFile.delete();
'''
    new_reset = '''            WINE_DEBUG_LINE_COUNT.set(0);
            WELLBIA_COLLECTOR_STARTED.set(false);
            traceFile.delete();
            fingerprintFile.delete();
            wineDebugFile.delete();
            wellbiaCaptureFile.delete();
            wellbiaLogsFile.delete();
            zipFile.delete();
'''
    if old_reset not in text:
        raise RuntimeError("diagnostics reset anchor not found")
    text = text.replace(old_reset, new_reset, 1)

    method_anchor = '''    public static String describeFile(String label, File file, boolean hash) {
'''
    collector_methods = r'''    private static boolean isWellbiaCandidate(File file) {
        String name = file.getName().toLowerCase(Locale.US);
        String path = file.getPath().toLowerCase(Locale.US);
        return path.contains("wellbia") || name.contains("xign") || name.contains("xldr")
                || name.contains("xhunter") || name.endsWith(".xem");
    }

    private static boolean isTextLog(File file) {
        String name = file.getName().toLowerCase(Locale.US);
        return name.endsWith(".log") || name.endsWith(".txt");
    }

    private static void collectCandidates(File root, int depth, List<File> out, Set<String> seen) {
        if (root == null || !root.exists() || depth < 0) return;
        if (root.isFile()) {
            if (!isWellbiaCandidate(root)) return;
            try {
                String canonical = root.getCanonicalPath();
                if (seen.add(canonical)) out.add(root);
            }
            catch (Exception e) {
                if (seen.add(root.getPath())) out.add(root);
            }
            return;
        }
        File[] children = root.listFiles();
        if (children == null) return;
        Arrays.sort(children, Comparator.comparing(File::getName, String.CASE_INSENSITIVE_ORDER));
        for (File child : children) {
            if (child.isDirectory()) collectCandidates(child, depth - 1, out, seen);
            else collectCandidates(child, depth, out, seen);
        }
    }

    private static String readSanitizedText(File file) {
        final int limit = 1024 * 1024;
        try (InputStream input = new BufferedInputStream(new FileInputStream(file))) {
            byte[] buffer = new byte[limit];
            int total = 0;
            while (total < limit) {
                int read = input.read(buffer, total, limit - total);
                if (read < 0) break;
                total += read;
            }
            boolean utf16 = total >= 2 && ((buffer[0] == (byte)0xff && buffer[1] == (byte)0xfe)
                    || (buffer[0] == (byte)0xfe && buffer[1] == (byte)0xff));
            if (!utf16 && total > 32) {
                int zeroes = 0;
                for (int i = 1; i < total; i += 2) if (buffer[i] == 0) zeroes++;
                utf16 = zeroes > total / 8;
            }
            String value = new String(buffer, 0, total,
                    utf16 ? StandardCharsets.UTF_16LE : StandardCharsets.UTF_8);
            StringBuilder out = new StringBuilder();
            String[] lines = value.replace('\r', '\n').split("\\n+");
            for (String line : lines) {
                String safe = sanitizeProcessLine(line);
                if (safe.length() > MAX_LINE_CHARS) safe = safe.substring(0, MAX_LINE_CHARS)+"...[truncated]";
                out.append(safe).append('\n');
            }
            if (file.length() > limit) out.append("[FILE_TRUNCATED_AT_1_MIB]\n");
            return out.toString();
        }
        catch (Exception e) {
            return "[READ_FAILED "+e.getClass().getSimpleName()+":"+String.valueOf(e.getMessage())+"]\n";
        }
    }

    public static void collectWellbiaArtifacts(File rootDir, String stage) {
        ensurePaths();
        List<File> matches = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        File downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
        collectCandidates(new File(rootDir, "home/xuser/.wine/drive_c/users/xuser/AppData/Local/WELLBIA"), 4, matches, seen);
        collectCandidates(new File(rootDir, "home/xuser/.wine/drive_c/windows"), 2, matches, seen);
        collectCandidates(new File(downloads, "TR_KR_LOCAL"), 7, matches, seen);
        collectCandidates(downloads, 1, matches, seen);
        Collections.sort(matches, Comparator.comparing(File::getPath, String.CASE_INSENSITIVE_ORDER));

        synchronized (LOCK) {
            try (FileWriter report = new FileWriter(wellbiaCaptureFile, false);
                 FileWriter logs = new FileWriter(wellbiaLogsFile, false)) {
                report.write("stage="+stage+" time="+System.currentTimeMillis()+" count="+matches.size()+"\n");
                int copiedLogs = 0;
                for (File file : matches) {
                    report.write(describeFile("CANDIDATE", file, true));
                    report.write(" modified="+file.lastModified()+"\n");
                    if (isTextLog(file) && copiedLogs < 16) {
                        logs.write("===== "+file.getPath()+" =====\n");
                        logs.write(readSanitizedText(file));
                        logs.write("\n");
                        copiedLogs++;
                    }
                }
                report.write("sanitized_text_logs="+copiedLogs+"\n");
                report.flush();
                logs.flush();
                trace("WELLBIA_CAPTURE stage="+stage+" count="+matches.size()+" text_logs="+copiedLogs);
            }
            catch (Exception e) {
                traceThrowable("WELLBIA_CAPTURE_EXCEPTION", e);
            }
        }
    }

    public static void startWellbiaCollector(final File rootDir) {
        if (rootDir == null || !WELLBIA_COLLECTOR_STARTED.compareAndSet(false, true)) return;
        Thread thread = new Thread(() -> {
            int[] waits = {0, 15, 30, 60, 90, 120, 180, 240};
            int previous = 0;
            for (int seconds : waits) {
                try {
                    if (seconds > previous) Thread.sleep((seconds - previous) * 1000L);
                }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                collectWellbiaArtifacts(rootDir, "t+"+seconds+"s");
                exportZip();
                previous = seconds;
            }
        }, "tr-wellbia-collector");
        thread.setDaemon(true);
        thread.start();
        trace("WELLBIA_COLLECTOR_STARTED root="+rootDir.getPath());
    }

'''
    if method_anchor not in text:
        raise RuntimeError("diagnostics method anchor not found")
    text = text.replace(method_anchor, collector_methods + method_anchor, 1)

    old_zip = '''                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wineDebugFile, "wine_api_trace.txt");
'''
    new_zip = '''                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wineDebugFile, "wine_api_trace.txt");
                addToZip(zip, wellbiaCaptureFile, "wellbia_capture.txt");
                addToZip(zip, wellbiaLogsFile, "wellbia_sanitized_logs.txt");
'''
    if old_zip not in text:
        raise RuntimeError("diagnostics zip anchor not found")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")

    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    text = activity.read_text(encoding="utf-8")
    if WINEDEBUG_V13 not in text:
        raise RuntimeError("v13 WINEDEBUG value not found")
    text = text.replace(WINEDEBUG_V13, WINEDEBUG_V14, 1)

    old_root_trace = '''            trTrace("ROOTFS root="+rootFS.getRootDir().getPath()+" winePath="+rootFS.getWinePath());
'''
    new_root_trace = old_root_trace + '''            TrCompatDiagnostics.startWellbiaCollector(rootFS.getRootDir());
'''
    if old_root_trace not in text:
        raise RuntimeError("rootfs collector anchor not found")
    text = text.replace(old_root_trace, new_root_trace, 1)
    activity.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v14_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v13.__file__).resolve()), str(root), str(component_dir)]
        result = v13.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_v14(root)
    print("Winlator TR Compat v14 Wellbia log capture applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
