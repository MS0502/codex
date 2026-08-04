#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

import apply_v16_patch as v16


REVISION = "v24-current-build-forensic-1"
WINEDEBUG_V16 = "-all,+timestamp,+pid,+tid,+process,+server,+service,+ntoskrnl"
WINEDEBUG_V24 = "-all,+timestamp,+pid,+tid,+process,+server,+service,+ntoskrnl,+seh,+loaddll"
EXPECTED_CURRENT_TRGAME_SHA256 = "35403c283d7a2e28cc9bffc833bf14742c482c742d51760ac52b02a8fced5e61"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v24(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat16-lifetime"',
        'versionName "11.1-trcompat24-forensic"',
    )

    manifest = root / "app/src/main/AndroidManifest.xml"
    manifest_text = manifest.read_text(encoding="utf-8")
    application_anchor = "<application\n"
    if application_anchor not in manifest_text:
        raise RuntimeError("AndroidManifest application anchor not found")
    if "android:debuggable=" not in manifest_text:
        manifest_text = manifest_text.replace(
            application_anchor,
            '<application\n        android:debuggable="true"\n',
            1,
        )
    manifest.write_text(manifest_text, encoding="utf-8")

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        "TR_DIAG_v16_LIFETIME.zip": "TR_DIAG_v24_FORENSIC.zip",
        "DIAGNOSTICS_RESET version=16-lifetime": "DIAGNOSTICS_RESET version=24-forensic",
        "TalesRunner KR XIGNCODE fingerprint v16 lifetime": "TalesRunner KR XIGNCODE fingerprint v24 forensic",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v24 anchor not found: {old}")
        text = text.replace(old, new)

    import_anchor = "import java.nio.charset.StandardCharsets;\n"
    import_replacement = (
        "import java.nio.charset.StandardCharsets;\n"
        "import java.nio.file.Files;\n"
        "import java.io.BufferedReader;\n"
        "import java.io.InputStreamReader;\n"
    )
    if import_anchor not in text:
        raise RuntimeError("diagnostics v24 import anchor not found")
    text = text.replace(import_anchor, import_replacement, 1)

    old_fields = '''    private static File wellbiaLowloadFile;
    private static File processLifetimeFile;
    private static File zipFile;
    private static String lastLifetimeSnapshot = "";
'''
    new_fields = '''    private static File wellbiaLowloadFile;
    private static File processLifetimeFile;
    private static File currentBuildFile;
    private static File runtimePressureFile;
    private static File processMapsFile;
    private static File registryKeywordsFile;
    private static File wellbiaBeforeFile;
    private static File wellbiaAfterFile;
    private static File wellbiaDeltaFile;
    private static File zipFile;
    private static String lastLifetimeSnapshot = "";
'''
    if old_fields not in text:
        raise RuntimeError("diagnostics v24 field anchor not found")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        wellbiaLowloadFile = new File(parentDir, "wellbia_lowload.txt");
        processLifetimeFile = new File(parentDir, "process_lifetime.txt");
        zipFile = new File(parentDir, "TR_DIAG_v24_FORENSIC.zip");
'''
    new_paths = '''        wellbiaLowloadFile = new File(parentDir, "wellbia_lowload.txt");
        processLifetimeFile = new File(parentDir, "process_lifetime.txt");
        currentBuildFile = new File(parentDir, "current_build.txt");
        runtimePressureFile = new File(parentDir, "runtime_pressure.txt");
        processMapsFile = new File(parentDir, "process_maps_fds.txt");
        registryKeywordsFile = new File(parentDir, "registry_keywords.txt");
        wellbiaBeforeFile = new File(parentDir, "wellbia_before.bin");
        wellbiaAfterFile = new File(parentDir, "wellbia_after.bin");
        wellbiaDeltaFile = new File(parentDir, "wellbia_delta.bin");
        zipFile = new File(parentDir, "TR_DIAG_v24_FORENSIC.zip");
'''
    if old_paths not in text:
        raise RuntimeError("diagnostics v24 path anchor not found")
    text = text.replace(old_paths, new_paths, 1)

    old_reset = '''            wellbiaLowloadFile.delete();
            processLifetimeFile.delete();
            zipFile.delete();
'''
    new_reset = '''            wellbiaLowloadFile.delete();
            processLifetimeFile.delete();
            currentBuildFile.delete();
            runtimePressureFile.delete();
            processMapsFile.delete();
            registryKeywordsFile.delete();
            wellbiaBeforeFile.delete();
            wellbiaAfterFile.delete();
            wellbiaDeltaFile.delete();
            zipFile.delete();
'''
    if old_reset not in text:
        raise RuntimeError("diagnostics v24 reset anchor not found")
    text = text.replace(old_reset, new_reset, 1)

    method_anchor = '''    private static boolean lowloadLogCandidate(File file) {
'''
    methods = r'''    private static String readSmallText(File file, int maxBytes) {
        if (file == null || !file.isFile() || !file.canRead()) return "[UNAVAILABLE]";
        try (InputStream input = new BufferedInputStream(new FileInputStream(file))) {
            byte[] data = new byte[maxBytes];
            int total = 0;
            while (total < data.length) {
                int read = input.read(data, total, data.length - total);
                if (read < 0) break;
                total += read;
            }
            return new String(data, 0, total, StandardCharsets.UTF_8);
        }
        catch (Exception e) {
            return "[READ_FAILED "+e.getClass().getSimpleName()+":"+String.valueOf(e.getMessage())+"]";
        }
    }

    private static void copyFileBounded(File source, File destination, int maxBytes) throws Exception {
        try (InputStream input = new BufferedInputStream(new FileInputStream(source));
             FileOutputStream output = new FileOutputStream(destination, false)) {
            byte[] buffer = new byte[64 * 1024];
            int total = 0;
            while (total < maxBytes) {
                int read = input.read(buffer, 0, Math.min(buffer.length, maxBytes - total));
                if (read < 0) break;
                output.write(buffer, 0, read);
                total += read;
            }
            output.flush();
        }
    }

    public static void collectCurrentBuildFingerprint() {
        ensurePaths();
        File base = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "TR_KR_LOCAL");
        File game = new File(base, "game");
        File trgame = new File(game, "trgame.exe");
        File talesrunner = new File(game, "talesrunner.exe");
        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(currentBuildFile, false)) {
                writer.write("captured="+System.currentTimeMillis()+"\n");
                writer.write("expected_current_trgame_sha256=__EXPECTED_TRGAME__\n");
                File[] files = {talesrunner, trgame};
                for (File file : files) {
                    writer.write(describeFile("GAME_FILE", file, true));
                    writer.write(" modified="+file.lastModified()+"\n");
                    if (file.getName().equalsIgnoreCase("trgame.exe") && file.isFile()) {
                        String actual = sha256(file);
                        writer.write("TRGAME_EXPECTED_MATCH="+
                                String.valueOf("__EXPECTED_TRGAME__".equalsIgnoreCase(actual))+"\n");
                    }
                }
                writer.flush();
                trace("CURRENT_BUILD_CAPTURED trgame_exists="+trgame.isFile()+
                        " size="+(trgame.isFile() ? trgame.length() : -1));
            }
            catch (Exception e) {
                traceThrowable("CURRENT_BUILD_EXCEPTION", e);
            }
        }
    }

    private static void appendSelectedProcLines(FileWriter writer, String label, File file, String[] prefixes) throws Exception {
        writer.write("--- "+label+" path="+file.getPath()+" exists="+file.isFile()+" ---\n");
        if (!file.isFile() || !file.canRead()) return;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            int count = 0;
            while ((line = reader.readLine()) != null && count < 256) {
                for (String prefix : prefixes) {
                    if (line.startsWith(prefix)) {
                        writer.write(sanitizeProcessLine(line)+"\n");
                        count++;
                        break;
                    }
                }
            }
        }
    }

    public static void collectRuntimePressure(File rootDir, String stage) {
        ensurePaths();
        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(runtimePressureFile, true)) {
                Runtime runtime = Runtime.getRuntime();
                writer.write("===== stage="+stage+" time="+System.currentTimeMillis()+" =====\n");
                writer.write("java_free="+runtime.freeMemory()+" java_total="+runtime.totalMemory()+
                        " java_max="+runtime.maxMemory()+"\n");
                writer.write("root_usable="+rootDir.getUsableSpace()+" root_free="+rootDir.getFreeSpace()+
                        " root_total="+rootDir.getTotalSpace()+"\n");
                appendSelectedProcLines(writer, "meminfo", new File("/proc/meminfo"),
                        new String[]{"MemTotal:", "MemFree:", "MemAvailable:", "Buffers:", "Cached:",
                                "SwapTotal:", "SwapFree:", "Slab:", "SReclaimable:"});
                appendSelectedProcLines(writer, "self_status", new File("/proc/self/status"),
                        new String[]{"Name:", "State:", "Threads:", "VmPeak:", "VmSize:", "VmRSS:",
                                "VmData:", "VmStk:", "VmExe:", "VmLib:", "VmSwap:"});
                File pressure = new File("/proc/pressure/memory");
                writer.write("--- pressure_memory ---\n");
                String pressureText = readSmallText(pressure, 4096);
                writer.write(sanitizeProcessLine(pressureText).replace('\r', ' '));
                if (!pressureText.endsWith("\n")) writer.write("\n");
                writer.flush();
            }
            catch (Exception e) {
                traceThrowable("RUNTIME_PRESSURE_EXCEPTION", e);
            }
        }
    }

    private static boolean forensicKeyword(String value) {
        String lower = value.toLowerCase(Locale.US);
        return lower.contains("talesrunner") || lower.contains("trgame")
                || lower.contains("xldr") || lower.contains("xign")
                || lower.contains("xhunter") || lower.contains(".xem")
                || lower.contains("ntdll") || lower.contains("wow64")
                || lower.contains("ntoskrnl") || lower.contains("winedevice")
                || lower.contains("wellbia");
    }

    public static void collectProcessMapsAndFds(String stage) {
        ensurePaths();
        List<ProcessHelper.PStat> processes = new ArrayList<>(ProcessHelper.getChildProcesses());
        Collections.sort(processes, Comparator.comparingInt((ProcessHelper.PStat item) -> item.pid));
        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(processMapsFile, true)) {
                writer.write("===== stage="+stage+" time="+System.currentTimeMillis()+" =====\n");
                for (ProcessHelper.PStat stat : processes) {
                    if (!lifetimeRelevant(stat)) continue;
                    writer.write("PID="+stat.pid+" NAME="+stat.name+" STATE="+stat.state+
                            " PPID="+stat.parentPID+" GUEST="+stat.guestProcess+"\n");
                    File maps = new File("/proc/"+stat.pid+"/maps");
                    if (maps.isFile() && maps.canRead()) {
                        try (BufferedReader reader = new BufferedReader(
                                new InputStreamReader(new FileInputStream(maps), StandardCharsets.UTF_8))) {
                            String line;
                            int count = 0;
                            while ((line = reader.readLine()) != null && count < 160) {
                                if (forensicKeyword(line)) {
                                    writer.write("MAP="+sanitizeProcessLine(line)+"\n");
                                    count++;
                                }
                            }
                        }
                        catch (Exception e) {
                            writer.write("MAPS_ERROR="+e.getClass().getSimpleName()+":"+
                                    sanitizeProcessLine(String.valueOf(e.getMessage()))+"\n");
                        }
                    }
                    File fdDir = new File("/proc/"+stat.pid+"/fd");
                    File[] fds = fdDir.listFiles();
                    if (fds != null) {
                        Arrays.sort(fds, Comparator.comparing(File::getName));
                        int count = 0;
                        for (File fd : fds) {
                            if (count >= 80) break;
                            try {
                                String target = Os.readlink(fd.getPath());
                                if (forensicKeyword(target)) {
                                    writer.write("FD="+fd.getName()+" TARGET="+sanitizeProcessLine(target)+"\n");
                                    count++;
                                }
                            }
                            catch (Exception ignored) {}
                        }
                    }
                }
                writer.flush();
            }
            catch (Exception e) {
                traceThrowable("PROCESS_MAPS_EXCEPTION", e);
            }
        }
    }

    private static void collectRegistryFile(FileWriter writer, File file) throws Exception {
        writer.write("--- REGISTRY path="+file.getPath()+" exists="+file.isFile()+" length="+
                (file.isFile() ? file.length() : -1)+" ---\n");
        if (!file.isFile() || !file.canRead()) return;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            int count = 0;
            while ((line = reader.readLine()) != null && count < 240) {
                String lower = line.toLowerCase(Locale.US);
                if (lower.contains("xhunter") || lower.contains("xign") || lower.contains("wellbia")) {
                    writer.write(sanitizeProcessLine(line)+"\n");
                    count++;
                }
            }
        }
    }

    public static void collectRegistryKeywords(File rootDir, String stage) {
        ensurePaths();
        File prefix = new File(rootDir, "home/xuser/.wine");
        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(registryKeywordsFile, true)) {
                writer.write("===== stage="+stage+" time="+System.currentTimeMillis()+" =====\n");
                collectRegistryFile(writer, new File(prefix, "system.reg"));
                collectRegistryFile(writer, new File(prefix, "user.reg"));
                writer.flush();
            }
            catch (Exception e) {
                traceThrowable("REGISTRY_KEYWORDS_EXCEPTION", e);
            }
        }
    }

    public static void snapshotWellbiaRaw(File rootDir, String stage) {
        ensurePaths();
        File source = new File(rootDir,
                "home/xuser/.wine/drive_c/users/xuser/AppData/Local/WELLBIA/"+
                "xldr_TalesRunner_KR_loader_x64.exe.log");
        synchronized (LOCK) {
            try {
                if (!source.isFile() || !source.canRead()) {
                    trace("WELLBIA_RAW stage="+stage+" exists=false path="+source.getPath());
                    return;
                }
                if (!wellbiaBeforeFile.isFile()) {
                    copyFileBounded(source, wellbiaBeforeFile, 4 * 1024 * 1024);
                    trace("WELLBIA_RAW_BEFORE size="+wellbiaBeforeFile.length()+
                            " sha256="+sha256(wellbiaBeforeFile));
                }
                copyFileBounded(source, wellbiaAfterFile, 4 * 1024 * 1024);
                byte[] before = Files.readAllBytes(wellbiaBeforeFile.toPath());
                byte[] after = Files.readAllBytes(wellbiaAfterFile.toPath());
                boolean prefixMatch = after.length >= before.length;
                if (prefixMatch) {
                    for (int i = 0; i < before.length; i++) {
                        if (before[i] != after[i]) {
                            prefixMatch = false;
                            break;
                        }
                    }
                }
                if (prefixMatch && after.length > before.length) {
                    try (FileOutputStream output = new FileOutputStream(wellbiaDeltaFile, false)) {
                        output.write(after, before.length, after.length - before.length);
                        output.flush();
                    }
                }
                trace("WELLBIA_RAW_AFTER stage="+stage+" size="+after.length+
                        " sha256="+sha256(wellbiaAfterFile)+" prefix_match="+prefixMatch+
                        " delta_size="+(wellbiaDeltaFile.isFile() ? wellbiaDeltaFile.length() : 0));
            }
            catch (Exception e) {
                traceThrowable("WELLBIA_RAW_EXCEPTION", e);
            }
        }
    }

'''
    methods = methods.replace("__EXPECTED_TRGAME__", EXPECTED_CURRENT_TRGAME_SHA256)
    if method_anchor not in text:
        raise RuntimeError("diagnostics v24 method anchor not found")
    text = text.replace(method_anchor, methods + method_anchor, 1)

    old_collector_pattern = (
        r'    public static void startLowloadCollector\(final File rootDir\) \{\n'
        r'.*?'
        r'        trace\("LOWLOAD_COLLECTOR_STARTED root="\+rootDir\.getPath\(\)\);\n'
        r'    \}\n'
    )
    new_collector = r'''    public static void startForensicCollector(final File rootDir) {
        if (rootDir == null || !LOWLOAD_COLLECTOR_STARTED.compareAndSet(false, true)) return;
        Thread thread = new Thread(() -> {
            collectCurrentBuildFingerprint();
            int previous = 0;
            for (int seconds = 0; seconds <= 45; seconds++) {
                try {
                    if (seconds > previous) Thread.sleep((seconds - previous) * 1000L);
                }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                String stage = "t+"+seconds+"s";
                collectProcessLifetime(stage);
                collectRuntimePressure(rootDir, stage);
                collectProcessMapsAndFds(stage);
                if (seconds == 0 || seconds == 5 || seconds == 10 || seconds == 15
                        || seconds == 20 || seconds == 25 || seconds == 30
                        || seconds == 35 || seconds == 40 || seconds == 45) {
                    snapshotWellbiaRaw(rootDir, stage);
                    collectWellbiaLowload(rootDir, stage);
                    collectRegistryKeywords(rootDir, stage);
                    exportZip();
                }
                previous = seconds;
            }

            int[] later = {60, 90, 120, 180};
            for (int seconds : later) {
                try {
                    Thread.sleep((seconds - previous) * 1000L);
                }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                String stage = "t+"+seconds+"s";
                collectProcessLifetime(stage);
                collectRuntimePressure(rootDir, stage);
                collectProcessMapsAndFds(stage);
                snapshotWellbiaRaw(rootDir, stage);
                collectWellbiaLowload(rootDir, stage);
                collectRegistryKeywords(rootDir, stage);
                exportZip();
                previous = seconds;
            }
        }, "tr-forensic-collector");
        thread.setDaemon(true);
        thread.start();
        trace("FORENSIC_COLLECTOR_STARTED root="+rootDir.getPath());
    }
'''
    updated, count = re.subn(old_collector_pattern, new_collector, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"diagnostics v24 collector anchor count={count}")
    text = updated

    old_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
                addToZip(zip, processLifetimeFile, "process_lifetime.txt");
'''
    new_zip = '''                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
                addToZip(zip, processLifetimeFile, "process_lifetime.txt");
                addToZip(zip, currentBuildFile, "current_build.txt");
                addToZip(zip, runtimePressureFile, "runtime_pressure.txt");
                addToZip(zip, processMapsFile, "process_maps_fds.txt");
                addToZip(zip, registryKeywordsFile, "registry_keywords.txt");
                addToZip(zip, wellbiaBeforeFile, "wellbia_before.bin");
                addToZip(zip, wellbiaAfterFile, "wellbia_after.bin");
                addToZip(zip, wellbiaDeltaFile, "wellbia_delta.bin");
'''
    if old_zip not in text:
        raise RuntimeError("diagnostics v24 zip anchor not found")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")

    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    text = activity.read_text(encoding="utf-8")
    if WINEDEBUG_V16 not in text:
        raise RuntimeError("v16 WINEDEBUG value not found")
    text = text.replace(WINEDEBUG_V16, WINEDEBUG_V24, 1)
    text = text.replace("WINEDEBUG_LIFETIME=", "WINEDEBUG_FORENSIC=", 1)
    old_collector_call = "            TrCompatDiagnostics.startLowloadCollector(rootFS.getRootDir());\n"
    new_collector_call = "            TrCompatDiagnostics.startForensicCollector(rootFS.getRootDir());\n"
    if old_collector_call not in text:
        raise RuntimeError("v16 collector call not found")
    text = text.replace(old_collector_call, new_collector_call, 1)
    activity.write_text(text, encoding="utf-8")

    guest = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    text = guest.read_text(encoding="utf-8")
    command_anchor = '        TrCompatDiagnostics.trace("COMMAND_SUMMARY "+TrCompatDiagnostics.summarizeCommand(command));\n'
    if command_anchor not in text:
        raise RuntimeError("guest command summary anchor not found")
    extra = '''        TrCompatDiagnostics.trace("FORENSIC_LAUNCH winePath="+rootFS.getWinePath()+
                " root="+rootDir.getPath()+" command="+TrCompatDiagnostics.summarizeCommand(command));
'''
    text = text.replace(command_anchor, command_anchor + extra, 1)
    guest.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")
    old_revision = 'private static final String REVISION = "v16-lifetime-server-1";'
    if old_revision not in text:
        raise RuntimeError("v16 runtime revision anchor not found")
    text = text.replace(old_revision, f'private static final String REVISION = "{REVISION}";', 1)
    text = text.replace(".trcompat-v16.tmp", ".trcompat-v24.tmp")
    patcher.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v24_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(v16.__file__).resolve()), str(root), str(component_dir)]
        result = v16.main()
    finally:
        sys.argv = saved_argv

    if result != 0:
        return result

    patch_v24(root)
    print("Winlator TR Compat v24 current-build forensic diagnostics applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
