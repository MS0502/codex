#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v12_patch as v12


REVISION = "v13-xign-api-diagnostics-2"
WINEDEBUG_VALUE = (
    "-all,err+all,warn+all,fixme+all,+timestamp,+pid,+tid,"
    "+process,+module,+loaddll,+file,+reg,+winhttp,+wininet,"
    "+winsock,+schannel,+crypt,+seh"
)


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v13(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat12-baseline"',
        'versionName "11.1-trcompat13-xign-diag"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v12_BASELINE.zip": "TR_DIAG_v13_XIGN.zip",
        "DIAGNOSTICS_RESET version=12-baseline": "DIAGNOSTICS_RESET version=13-xign",
        "TalesRunner KR XIGNCODE fingerprint v12 baseline": "TalesRunner KR XIGNCODE fingerprint v13 diagnostics",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v13 anchor not found: {old}")
        text = text.replace(old, new)

    old_fields = '''    private static final int MAX_PROCESS_LINES = 2500;
    private static final int MAX_LINE_CHARS = 3000;
    private static final AtomicInteger PROCESS_LINE_COUNT = new AtomicInteger();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File zipFile;
'''
    new_fields = '''    private static final int MAX_PROCESS_LINES = 2500;
    private static final int MAX_WINE_DEBUG_LINES = 40000;
    private static final int MAX_LINE_CHARS = 3000;
    private static final AtomicInteger PROCESS_LINE_COUNT = new AtomicInteger();
    private static final AtomicInteger WINE_DEBUG_LINE_COUNT = new AtomicInteger();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File wineDebugFile;
    private static File zipFile;
'''
    if old_fields not in text:
        raise RuntimeError("diagnostics field anchor not found")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        traceFile = new File(parentDir, "startup_trace.txt");
        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        zipFile = new File(parentDir, "TR_DIAG_v13_XIGN.zip");
'''
    new_paths = '''        traceFile = new File(parentDir, "startup_trace.txt");
        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        wineDebugFile = new File(parentDir, "wine_api_trace.txt");
        zipFile = new File(parentDir, "TR_DIAG_v13_XIGN.zip");
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
            WINE_DEBUG_LINE_COUNT.set(0);
            traceFile.delete();
            fingerprintFile.delete();
            wineDebugFile.delete();
            zipFile.delete();
'''
    if old_reset not in text:
        raise RuntimeError("diagnostics reset anchor not found")
    text = text.replace(old_reset, new_reset, 1)

    old_return = '''        return safe;
    }

    public static void traceProcessLine'''
    new_return = r'''        safe = safe.replaceAll("(?i)([?&](?:token|authkey|ticket|session|signature|sig)=)[^&\\s]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?i)(\\b(?:authkey|sessionkey|ticket|signature)\\b\\s*[:=]\\s*)[^\\s&;,]+", "$1[REDACTED]");
        return safe;
    }

    public static void traceProcessLine'''
    if old_return not in text:
        raise RuntimeError("diagnostics sanitize return anchor not found")
    text = text.replace(old_return, new_return, 1)

    old_after_process = '''    public static void traceProcessLine(String stream, String line) {
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
    new_after_process = old_after_process + r'''

    public static void traceWineDebugLine(String stream, String line) {
        ensurePaths();
        String value = sanitizeProcessLine(line == null ? "null" : line);
        String lower = value.toLowerCase(Locale.US);
        boolean important = lower.contains("xign") || lower.contains("xldr") || lower.contains(".xem")
                || lower.contains("err:") || lower.contains("warn:") || lower.contains("fixme:")
                || lower.contains("createprocess") || lower.contains("ntcreateuserprocess")
                || lower.contains("loadlibrary") || lower.contains("ldrloaddll")
                || lower.contains("createfile") || lower.contains("ntcreatefile")
                || lower.contains("regopen") || lower.contains("regquery")
                || lower.contains("winhttp") || lower.contains("wininet")
                || lower.contains("winsock") || lower.contains("schannel")
                || lower.contains("crypt32") || lower.contains("secur32")
                || lower.contains("status_") || lower.contains("hresult")
                || lower.contains("access denied") || lower.contains("not found")
                || lower.contains("failed") || lower.contains("failure");
        if (!important) return;

        int index = WINE_DEBUG_LINE_COUNT.incrementAndGet();
        if (index > MAX_WINE_DEBUG_LINES) {
            if (index == MAX_WINE_DEBUG_LINES + 1) trace("WINE_API_TRACE_TRUNCATED limit="+MAX_WINE_DEBUG_LINES);
            return;
        }
        if (value.length() > MAX_LINE_CHARS) value = value.substring(0, MAX_LINE_CHARS)+"...[truncated]";
        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(wineDebugFile, true)) {
                writer.write(System.currentTimeMillis()+" "+stream+" "+value+"\n");
                writer.flush();
            }
            catch (Exception e) {
                trace("WINE_API_TRACE_WRITE_FAILED class="+e.getClass().getSimpleName()+" message="+String.valueOf(e.getMessage()));
            }
        }
    }
'''
    if old_after_process not in text:
        raise RuntimeError("diagnostics process-line anchor not found")
    text = text.replace(old_after_process, new_after_process, 1)

    old_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
'''
    new_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wineDebugFile, "wine_api_trace.txt");
'''
    if old_zip not in text:
        raise RuntimeError("diagnostics zip anchor not found")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")

    process = root / "app/src/main/java/com/winlator/core/ProcessHelper.java"
    text = process.read_text(encoding="utf-8")
    old_process_line = '''                    TrCompatDiagnostics.traceProcessLine(streamName, line);
'''
    new_process_line = '''                    TrCompatDiagnostics.traceProcessLine(streamName, line);
                    TrCompatDiagnostics.traceWineDebugLine(streamName, line);
'''
    if old_process_line not in text:
        raise RuntimeError("ProcessHelper trace anchor not found")
    text = text.replace(old_process_line, new_process_line, 1)
    process.write_text(text, encoding="utf-8")

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
            trTrace("WINEDEBUG_DIAGNOSTIC="+trWineDebug);
'''
    if old_sync not in text:
        raise RuntimeError("WINEDEBUG environment anchor not found")
    text = text.replace(old_sync, new_sync, 1)
    activity.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v13_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
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

    patch_v13(root)
    print("Winlator TR Compat v13 XIGNCODE API diagnostics applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
