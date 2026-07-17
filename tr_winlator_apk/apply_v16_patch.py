#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v15_patch as v15


REVISION = "v16-lifetime-server-1"
WINEDEBUG_V15 = "-all,+timestamp,+pid,+tid,+process,+service,+ntoskrnl,+seh"
WINEDEBUG_V16 = "-all,+timestamp,+pid,+tid,+process,+server,+service,+ntoskrnl"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v16(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat15-lowload"',
        'versionName "11.1-trcompat16-lifetime"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v15_LOWLOAD.zip": "TR_DIAG_v16_LIFETIME.zip",
        "DIAGNOSTICS_RESET version=15-lowload": "DIAGNOSTICS_RESET version=16-lifetime",
        "TalesRunner KR XIGNCODE fingerprint v15 low-load": "TalesRunner KR XIGNCODE fingerprint v16 lifetime",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v16 anchor not found: {old}")
        text = text.replace(old, new)

    old_fields = '''    private static final AtomicBoolean LOWLOAD_COLLECTOR_STARTED = new AtomicBoolean();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File wellbiaLowloadFile;
    private static File zipFile;
'''
    new_fields = '''    private static final AtomicBoolean LOWLOAD_COLLECTOR_STARTED = new AtomicBoolean();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File wellbiaLowloadFile;
    private static File processLifetimeFile;
    private static File zipFile;
    private static String lastLifetimeSnapshot = "";
'''
    if old_fields not in text:
        raise RuntimeError("diagnostics v16 field anchor not found")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        wellbiaLowloadFile = new File(parentDir, "wellbia_lowload.txt");
        zipFile = new File(parentDir, "TR_DIAG_v16_LIFETIME.zip");
'''
    new_paths = '''        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        wellbiaLowloadFile = new File(parentDir, "wellbia_lowload.txt");
        processLifetimeFile = new File(parentDir, "process_lifetime.txt");
        zipFile = new File(parentDir, "TR_DIAG_v16_LIFETIME.zip");
'''
    if old_paths not in text:
        raise RuntimeError("diagnostics v16 path anchor not found")
    text = text.replace(old_paths, new_paths, 1)

    old_reset = '''            LOWLOAD_COLLECTOR_STARTED.set(false);
            traceFile.delete();
            fingerprintFile.delete();
            wellbiaLowloadFile.delete();
            zipFile.delete();
'''
    new_reset = '''            LOWLOAD_COLLECTOR_STARTED.set(false);
            lastLifetimeSnapshot = "";
            traceFile.delete();
            fingerprintFile.delete();
            wellbiaLowloadFile.delete();
            processLifetimeFile.delete();
            zipFile.delete();
'''
    if old_reset not in text:
        raise RuntimeError("diagnostics v16 reset anchor not found")
    text = text.replace(old_reset, new_reset, 1)

    old_sanitize = r'''    private static String sanitizeProcessLine(String value) {
        String safe = value;
        safe = safe.replaceAll("(?i)(authorization\\s*[:=]\\s*bearer\\s+)[A-Za-z0-9._~+/-]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?i)(\\b(?:access_?token|id_?token|refresh_?token|jwe|jwt|auth(?:orization)?)\\b\\s*[:=]\\s*)[^\\s&;,]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?<![A-Za-z0-9_-])(?:[A-Za-z0-9_-]{10,}\\.){2,4}[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])", "[REDACTED_TOKEN]");
        return safe;
    }
'''
    new_sanitize = r'''    private static String sanitizeProcessLine(String value) {
        String safe = value == null ? "null" : value;
        safe = safe.replaceAll("(?i)(authorization\\s*[:=]\\s*bearer\\s+)[A-Za-z0-9._~+/-]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?i)([?&](?:access_?token|id_?token|refresh_?token|token|authkey|ticket|session|sessionkey|signature|sig|code)=)[^&\\s]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?i)(\\b(?:access_?token|id_?token|refresh_?token|token|authkey|ticket|session|sessionkey|signature|sig|jwe|jwt|auth(?:orization)?)\\b\\s*[:=]\\s*)[^\\s&;,]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?<![A-Za-z0-9_-])(?:[A-Za-z0-9_-]{10,}\\.){2,5}[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])", "[REDACTED_TOKEN]");
        safe = safe.replaceAll("(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{80,}(?![A-Za-z0-9_-])", "[REDACTED_LONG_VALUE]");
        return safe;
    }
'''
    if old_sanitize not in text:
        raise RuntimeError("diagnostics v16 sanitizer anchor not found")
    text = text.replace(old_sanitize, new_sanitize, 1)

    old_external = '''    public static String sanitizeExternal(String value) {
        return sanitizeProcessLine(value == null ? "null" : value);
    }
'''
    new_external = '''    public static String summarizeCommand(String value) {
        if (value == null) return "length=0 targets=none";
        String lower = value.toLowerCase(Locale.US);
        StringBuilder targets = new StringBuilder();
        String[] names = {
                "talesrunner.exe", "trgame.exe", "xldr_", "wine", "wineserver",
                "box64", "services.exe", "explorer.exe", "cmd.exe"
        };
        for (String name : names) {
            if (lower.contains(name)) {
                if (targets.length() > 0) targets.append(',');
                targets.append(name);
            }
        }
        if (targets.length() == 0) targets.append("other");
        return "length="+value.length()+" targets="+targets;
    }
'''
    if old_external not in text:
        raise RuntimeError("diagnostics v16 command summary anchor not found")
    text = text.replace(old_external, new_external, 1)

    old_relevant = '''                || lower.contains("ntcreateuserprocess")
                || lower.contains("createprocess") || lower.contains("process exit")
                || lower.contains("terminateprocess") || lower.contains("exit code")
                || lower.contains("service") || lower.contains("driver")
'''
    new_relevant = '''                || lower.contains("ntcreateuserprocess")
                || lower.contains("createprocess") || lower.contains("new_process")
                || lower.contains("process exit") || lower.contains("exit_process")
                || lower.contains("terminateprocess") || lower.contains("terminate_process")
                || lower.contains("process terminated") || lower.contains("exit code")
                || lower.contains("service") || lower.contains("driver")
'''
    if old_relevant not in text:
        raise RuntimeError("diagnostics v16 focused filter anchor not found")
    text = text.replace(old_relevant, new_relevant, 1)

    method_anchor = '''    private static boolean lowloadLogCandidate(File file) {
'''
    lifetime_methods = r'''    private static boolean lifetimeRelevant(ProcessHelper.PStat stat) {
        String lower = stat.name == null ? "" : stat.name.toLowerCase(Locale.US);
        return stat.guestProcess || lower.contains("box64") || lower.contains("wine")
                || lower.contains("wineserver") || lower.contains("services")
                || lower.contains("talesrunner") || lower.contains("trgame")
                || lower.contains("xldr") || lower.contains(".exe");
    }

    public static void collectProcessLifetime(String stage) {
        ensurePaths();
        List<ProcessHelper.PStat> processes = new ArrayList<>(ProcessHelper.getChildProcesses());
        Collections.sort(processes, Comparator.comparingInt((ProcessHelper.PStat item) -> item.pid));

        StringBuilder snapshot = new StringBuilder();
        int count = 0;
        for (ProcessHelper.PStat stat : processes) {
            if (!lifetimeRelevant(stat)) continue;
            count++;
            snapshot.append("PID=").append(stat.pid)
                    .append(" NAME=").append(stat.name)
                    .append(" STATE=").append(stat.state)
                    .append(" PPID=").append(stat.parentPID)
                    .append(" GUEST=").append(stat.guestProcess)
                    .append('\n');
        }

        String current = snapshot.toString();
        boolean changed;
        synchronized (LOCK) {
            changed = !current.equals(lastLifetimeSnapshot);
            lastLifetimeSnapshot = current;
            try (FileWriter writer = new FileWriter(processLifetimeFile, true)) {
                writer.write("===== stage="+stage+" time="+System.currentTimeMillis()
                        +" count="+count+" changed="+changed+" =====\n");
                if (current.isEmpty()) writer.write("[NO_RELEVANT_PROCESSES]\n");
                else writer.write(current);
                writer.flush();
            }
            catch (Exception e) {
                traceThrowable("PROCESS_LIFETIME_EXCEPTION", e);
            }
        }
        trace("PROCESS_LIFETIME stage="+stage+" count="+count+" changed="+changed);
    }

'''
    if method_anchor not in text:
        raise RuntimeError("diagnostics v16 lifetime method anchor not found")
    text = text.replace(method_anchor, lifetime_methods + method_anchor, 1)

    old_collector = '''            int[] waits = {0, 30, 60, 90, 120, 180};
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
'''
    new_collector = '''            int[] waits = {0, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180};
            int previous = 0;
            for (int seconds : waits) {
                try {
                    if (seconds > previous) Thread.sleep((seconds - previous) * 1000L);
                }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                String stage = "t+"+seconds+"s";
                collectProcessLifetime(stage);
                if (seconds == 0 || seconds == 30 || seconds == 60
                        || seconds == 90 || seconds == 120 || seconds == 180) {
                    collectWellbiaLowload(rootDir, stage);
                }
                exportZip();
                previous = seconds;
            }
'''
    if old_collector not in text:
        raise RuntimeError("diagnostics v16 collector anchor not found")
    text = text.replace(old_collector, new_collector, 1)

    old_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
'''
    new_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
                addToZip(zip, processLifetimeFile, "process_lifetime.txt");
'''
    if old_zip not in text:
        raise RuntimeError("diagnostics v16 zip anchor not found")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")

    process = root / "app/src/main/java/com/winlator/core/ProcessHelper.java"
    text = process.read_text(encoding="utf-8")
    replacements = {
        'TrCompatDiagnostics.trace("PROCESS_HELPER_ENTER command="+TrCompatDiagnostics.sanitizeExternal(command));':
            'TrCompatDiagnostics.trace("PROCESS_HELPER_ENTER "+TrCompatDiagnostics.summarizeCommand(command));',
        'TrCompatDiagnostics.trace("PROCESS_ARGV="+TrCompatDiagnostics.sanitizeExternal(java.util.Arrays.toString(argv)));':
            'TrCompatDiagnostics.trace("PROCESS_ARGV_SUMMARY "+TrCompatDiagnostics.summarizeCommand(java.util.Arrays.toString(argv)));',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"ProcessHelper v16 anchor not found: {old}")
        text = text.replace(old, new, 1)
    process.write_text(text, encoding="utf-8")

    guest = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    text = guest.read_text(encoding="utf-8")
    old_command = '        TrCompatDiagnostics.trace("COMMAND="+TrCompatDiagnostics.sanitizeExternal(command));\n'
    new_command = '        TrCompatDiagnostics.trace("COMMAND_SUMMARY "+TrCompatDiagnostics.summarizeCommand(command));\n'
    if old_command not in text:
        raise RuntimeError("guest v16 command summary anchor not found")
    text = text.replace(old_command, new_command, 1)
    guest.write_text(text, encoding="utf-8")

    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    text = activity.read_text(encoding="utf-8")
    if WINEDEBUG_V15 not in text:
        raise RuntimeError("v15 WINEDEBUG value not found")
    text = text.replace(WINEDEBUG_V15, WINEDEBUG_V16, 1)
    text = text.replace("WINEDEBUG_LOWLOAD=", "WINEDEBUG_LIFETIME=", 1)
    activity.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")
    old_revision = 'private static final String REVISION = "v15-lowload-process-driver-1";'
    if old_revision not in text:
        raise RuntimeError("v15 runtime revision anchor not found")
    text = text.replace(old_revision, f'private static final String REVISION = "{REVISION}";', 1)
    text = text.replace(".trcompat-v15.tmp", ".trcompat-v16.tmp")
    patcher.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v16_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v15.__file__).resolve()), str(root), str(component_dir)]
        result = v15.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_v16(root)
    print("Winlator TR Compat v16 process lifetime diagnostics applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
