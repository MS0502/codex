#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:160]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def write_diagnostics_class(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    path.write_text(r'''package com.winlator.core;

import android.os.Environment;
import android.system.Os;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/** Diagnostics for the separate TR compatibility build. No protected file is modified. */
public final class TrCompatDiagnostics {
    private static final Object LOCK = new Object();
    private static final int MAX_PROCESS_LINES = 2500;
    private static final int MAX_LINE_CHARS = 3000;
    private static final AtomicInteger PROCESS_LINE_COUNT = new AtomicInteger();
    private static File parentDir;
    private static File traceFile;
    private static File fingerprintFile;
    private static File zipFile;

    private TrCompatDiagnostics() {}

    private static void ensurePaths() {
        if (parentDir != null) return;
        parentDir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS), "Winlator");
        if (!parentDir.isDirectory()) parentDir.mkdirs();
        traceFile = new File(parentDir, "startup_trace.txt");
        fingerprintFile = new File(parentDir, "xign_fingerprint.txt");
        zipFile = new File(parentDir, "TR_DIAG_v6.zip");
    }

    public static void reset() {
        synchronized (LOCK) {
            ensurePaths();
            PROCESS_LINE_COUNT.set(0);
            traceFile.delete();
            fingerprintFile.delete();
            zipFile.delete();
            trace("DIAGNOSTICS_RESET version=6");
        }
    }

    public static void trace(String message) {
        synchronized (LOCK) {
            ensurePaths();
            String safe = message == null ? "null" : message.replace('\r', ' ').replace('\n', ' ');
            try (FileWriter writer = new FileWriter(traceFile, true)) {
                writer.write(System.currentTimeMillis()+" "+safe+"\n");
                writer.flush();
            }
            catch (Exception e) {
                System.err.println("TR_DIAG_WRITE_FAILED "+e);
            }
        }
    }

    public static void traceThrowable(String prefix, Throwable throwable) {
        trace(prefix+" class="+throwable.getClass().getName()+" message="+String.valueOf(throwable.getMessage()));
        for (StackTraceElement element : throwable.getStackTrace()) trace(prefix+" stack="+element.toString());
        Throwable cause = throwable.getCause();
        if (cause != null && cause != throwable) {
            trace(prefix+" cause="+cause.getClass().getName()+" message="+String.valueOf(cause.getMessage()));
            for (StackTraceElement element : cause.getStackTrace()) trace(prefix+" cause_stack="+element.toString());
        }
    }

    private static String sanitizeProcessLine(String value) {
        String safe = value;
        safe = safe.replaceAll("(?i)(authorization\\s*[:=]\\s*bearer\\s+)[A-Za-z0-9._~+/-]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?i)(\\b(?:access_?token|id_?token|refresh_?token|jwe|jwt|auth(?:orization)?)\\b\\s*[:=]\\s*)[^\\s&;,]+", "$1[REDACTED]");
        safe = safe.replaceAll("(?<![A-Za-z0-9_-])(?:[A-Za-z0-9_-]{10,}\\.){2,4}[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])", "[REDACTED_TOKEN]");
        return safe;
    }

    public static void traceProcessLine(String stream, String line) {
        int index = PROCESS_LINE_COUNT.incrementAndGet();
        if (index > MAX_PROCESS_LINES) {
            if (index == MAX_PROCESS_LINES + 1) trace("PROCESS_OUTPUT_TRUNCATED limit="+MAX_PROCESS_LINES);
            return;
        }
        String value = sanitizeProcessLine(line == null ? "null" : line);
        if (value.length() > MAX_LINE_CHARS) value = value.substring(0, MAX_LINE_CHARS)+"...[truncated]";
        trace("PROCESS_"+stream+" "+value);
    }

    public static String describeFile(String label, File file, boolean hash) {
        StringBuilder out = new StringBuilder();
        out.append(label).append(" path=").append(file.getPath());
        out.append(" exists=").append(file.exists());
        out.append(" file=").append(file.isFile());
        out.append(" dir=").append(file.isDirectory());
        out.append(" read=").append(file.canRead());
        out.append(" write=").append(file.canWrite());
        out.append(" exec=").append(file.canExecute());
        out.append(" length=").append(file.isFile() ? file.length() : -1);
        try {
            out.append(" canonical=").append(file.getCanonicalPath());
        }
        catch (Exception e) {
            out.append(" canonical_error=").append(e.getClass().getSimpleName()).append(':').append(e.getMessage());
        }
        try {
            long mode = Os.stat(file.getPath()).st_mode & 07777;
            out.append(" mode=").append(String.format(Locale.US, "%04o", mode));
        }
        catch (Exception e) {
            out.append(" stat_error=").append(e.getClass().getSimpleName()).append(':').append(e.getMessage());
        }
        try {
            out.append(" symlink_target=").append(Os.readlink(file.getPath()));
        }
        catch (Exception ignored) {}
        if (hash && file.isFile() && file.canRead()) out.append(" sha256=").append(sha256(file));
        return out.toString();
    }

    public static String sha256(File file) {
        try (InputStream input = new BufferedInputStream(new FileInputStream(file))) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[1024 * 128];
            int read;
            while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
            StringBuilder value = new StringBuilder();
            for (byte b : digest.digest()) value.append(String.format(Locale.US, "%02x", b & 0xff));
            return value.toString();
        }
        catch (Exception e) {
            return "ERROR:"+e.getClass().getSimpleName()+":"+String.valueOf(e.getMessage());
        }
    }

    private static boolean isXignCandidate(File file) {
        String name = file.getName().toLowerCase(Locale.US);
        return (name.startsWith("x") && name.endsWith(".xem"))
                || (name.startsWith("xldr") && name.endsWith(".exe"))
                || (name.startsWith("xhunter") && name.endsWith(".sys"))
                || (name.contains("xigncode") && (name.endsWith(".dll") || name.endsWith(".exe") || name.endsWith(".sys")));
    }

    public static void collectXignFingerprint() {
        ensurePaths();
        File base = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "TR_KR_LOCAL");
        List<File> matches = new ArrayList<>();
        ArrayDeque<Object[]> queue = new ArrayDeque<>();
        queue.add(new Object[]{base, 0});
        while (!queue.isEmpty()) {
            Object[] item = queue.removeFirst();
            File current = (File)item[0];
            int depth = (Integer)item[1];
            File[] children = current.listFiles();
            if (children == null) continue;
            Arrays.sort(children, Comparator.comparing(File::getName, String.CASE_INSENSITIVE_ORDER));
            for (File child : children) {
                if (child.isDirectory() && depth < 5) queue.addLast(new Object[]{child, depth + 1});
                else if (child.isFile() && isXignCandidate(child)) matches.add(child);
            }
        }
        Collections.sort(matches, Comparator.comparing(File::getPath, String.CASE_INSENSITIVE_ORDER));

        Map<String, String> thai2026 = new HashMap<>();
        thai2026.put("x3.xem", "b421f4ed073f686128d283c35cd40744f2aa625020fc8706e7236b63498b23c8");
        thai2026.put("x3_x64.xem", "6a8e373d7c10060f8612bb0f9a0d13a1c3de73ebd9b73f89d50df30ce673fad7");
        thai2026.put("xcorona.xem", "798b1568e6ce197071b771fe897870c04bddf75279382ec00f7cc9128f330de8");
        thai2026.put("xcorona_arm64.xem", "e49c7c79a6612acd2f47929a89cb66c4ae847705f042d1bb6c0205188e0d7062");
        thai2026.put("xcorona_x64.xem", "f082c98677ea4b6a2088fb74906ab798e1d9ad58c51f66d783bcdffaa599526b7");
        thai2026.put("xnina.xem", "59e781ef16cfdb01f79d34291045c80358eda2de9e2da8593be9a1802cbdb56d");
        thai2026.put("xnina_x64.xem", "6dcf873c19259ee8da533be1fa604f728812ed5cc9de288bb37368ba1ed5dae0");

        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(fingerprintFile, false)) {
                writer.write("TalesRunner KR XIGNCODE fingerprint v6\n");
                writer.write("BASE="+base.getPath()+"\n");
                writer.write("BASE_EXISTS="+base.exists()+"\n");
                writer.write("COUNT="+matches.size()+"\n\n");
                for (File file : matches) {
                    String hash = sha256(file);
                    String reference = thai2026.get(file.getName().toLowerCase(Locale.US));
                    writer.write("FILE="+file.getPath()+"\n");
                    writer.write("SIZE="+file.length()+"\n");
                    writer.write("SHA256="+hash+"\n");
                    if (reference != null) {
                        writer.write("TH_2026_REFERENCE_SHA256="+reference+"\n");
                        writer.write("TH_2026_REFERENCE_MATCH="+String.valueOf(reference.equalsIgnoreCase(hash))+"\n");
                    }
                    writer.write("\n");
                }
                writer.flush();
                trace("XIGN_FINGERPRINT_COMPLETE count="+matches.size()+" file="+fingerprintFile.getPath());
            }
            catch (Exception e) {
                traceThrowable("XIGN_FINGERPRINT_EXCEPTION", e);
            }
        }
        exportZip();
    }

    private static void addToZip(ZipOutputStream zip, File file, String entryName) throws Exception {
        if (!file.isFile()) return;
        zip.putNextEntry(new ZipEntry(entryName));
        try (InputStream input = new BufferedInputStream(new FileInputStream(file))) {
            byte[] buffer = new byte[1024 * 64];
            int read;
            while ((read = input.read(buffer)) != -1) zip.write(buffer, 0, read);
        }
        zip.closeEntry();
    }

    public static void exportZip() {
        synchronized (LOCK) {
            ensurePaths();
            File temp = new File(parentDir, "TR_DIAG_v6.zip.tmp");
            temp.delete();
            try (ZipOutputStream zip = new ZipOutputStream(new BufferedOutputStream(new FileOutputStream(temp)))) {
                addToZip(zip, traceFile, "startup_trace.txt");
                addToZip(zip, fingerprintFile, "xign_fingerprint.txt");
            }
            catch (Exception e) {
                temp.delete();
                traceThrowable("ZIP_EXPORT_EXCEPTION", e);
                return;
            }
            zipFile.delete();
            if (!temp.renameTo(zipFile)) {
                trace("ZIP_EXPORT_RENAME_FAILED from="+temp.getPath()+" to="+zipFile.getPath());
                return;
            }
            System.out.println("TR_DIAG_ZIP="+zipFile.getPath());
        }
    }
}
''', encoding="utf-8")


def patch_base_v5(root: Path) -> None:
    replace_once(root / "app/build.gradle", "applicationId 'com.winlator'", "applicationId 'com.winlator.trcompat'")
    replace_once(root / "app/build.gradle", 'versionName "11.1"', 'versionName "11.1-trcompat6"')
    replace_once(
        root / "app/build.gradle",
        "android {\n    compileSdk 34\n",
        "android {\n    compileSdk 34\n\n    packagingOptions {\n        pickFirst 'lib/arm64-v8a/*.so'\n    }\n",
    )
    replace_once(root / "app/src/main/AndroidManifest.xml", 'android:authorities="com.winlator.FileProvider"', 'android:authorities="com.winlator.trcompat.FileProvider"')
    replace_once(root / "app/src/main/java/com/winlator/MainActivity.java", "public static final boolean DEBUG_MODE = false;", "public static final boolean DEBUG_MODE = true;")
    replace_once(
        root / "app/src/main/java/com/winlator/core/WineInfo.java",
        'private static final Pattern pattern = Pattern.compile("^wine\\\\-([0-9\\\\.]+)\\\\-?([0-9\\\\.]+)?\\\\-?(x86|x86_64)?$");',
        'private static final Pattern pattern = Pattern.compile("^wine\\\\-([0-9\\\\.]+)(?:\\\\-([A-Za-z0-9._]+))?(?:\\\\-(x86|x86_64))?$");',
    )
    replace_once(
        root / "app/src/main/java/com/winlator/core/WineInstaller.java",
        '''        RootFS rootFS = RootFS.find(context);\n        File rootDir = rootFS.getRootDir();\n        String wineBinPath = wineBin64.isFile() ? wineBin64.getPath() : wineBin.getPath();\n        final String winePath = wineDir.getPath();\n\n        final AtomicReference<WineInfo> wineInfoRef = new AtomicReference<>();\n        Callback<String> debugCallback = (line) -> {\n            Pattern pattern = Pattern.compile("^wine\\\\-([0-9\\\\.]+)\\\\-?([0-9\\\\.]+)?", Pattern.CASE_INSENSITIVE);\n            Matcher matcher = pattern.matcher(line);\n            if (matcher.find()) {\n                String version = matcher.group(1);\n                String subversion = matcher.groupCount() >= 2 ? matcher.group(2) : null;\n                wineInfoRef.set(new WineInfo(version, subversion, winePath));\n            }\n        };\n\n        ProcessHelper.addDebugCallback(debugCallback);\n\n        File linkFile = new File(rootDir, RootFS.HOME_PATH);\n        linkFile.delete();\n        FileUtils.symlink(wineDir, linkFile);\n\n        XEnvironment environment = new XEnvironment(context, rootFS);\n        GuestProgramLauncherComponent guestProgramLauncherComponent = new GuestProgramLauncherComponent();\n        guestProgramLauncherComponent.setGuestExecutable(wineBinPath+" --version");\n        guestProgramLauncherComponent.setTerminationCallback((status) -> {\n            callback.call(wineInfoRef.get());\n            ProcessHelper.removeDebugCallback(debugCallback);\n        });\n        environment.addComponent(guestProgramLauncherComponent);\n        environment.startEnvironmentComponents();\n''',
        '''        callback.call(new WineInfo("10.10", "trcompat", wineDir.getPath()));\n''',
    )
    replace_once(
        root / "app/src/main/java/com/winlator/SettingsFragment.java",
        '''    private void installWine(final WineInfo wineInfo) {\n        Context context = getContext();\n        File installedWineDir = RootFS.find(context).getInstalledWineDir();\n\n        File wineDir = new File(installedWineDir, wineInfo.identifier());\n        if (wineDir.isDirectory()) {\n            AppUtils.showToast(context, R.string.unable_to_install_wine);\n            return;\n        }\n\n        Intent intent = new Intent(context, XServerDisplayActivity.class);\n        intent.putExtra("generate_wineprefix", true);\n        intent.putExtra("wine_info", wineInfo);\n        context.startActivity(intent);\n    }\n''',
        '''    private void installWine(final WineInfo wineInfo) {\n        final Context context = getContext();\n        final File installedWineDir = RootFS.find(context).getInstalledWineDir();\n        final File sourceWineDir = new File(wineInfo.path);\n        final File targetWineDir = new File(installedWineDir, wineInfo.identifier());\n        final File patternFile = new File(installedWineDir, "container-pattern-"+wineInfo.fullVersion()+".tzst");\n\n        if (targetWineDir.exists() || patternFile.exists() || !sourceWineDir.isDirectory()) {\n            AppUtils.showToast(context, R.string.unable_to_install_wine);\n            return;\n        }\n\n        preloaderDialog.show(R.string.finishing_installation);\n        Executors.newSingleThreadExecutor().execute(() -> {\n            boolean wineReady = sourceWineDir.renameTo(targetWineDir);\n            if (!wineReady) wineReady = FileUtils.copy(sourceWineDir, targetWineDir);\n\n            FileUtils.copy(context, "container_pattern.tzst", patternFile);\n            boolean patternReady = patternFile.isFile() && patternFile.length() > 0;\n            FileUtils.delete(new File(installedWineDir, "preinstall"));\n\n            if (!wineReady || !patternReady) {\n                FileUtils.delete(targetWineDir);\n                FileUtils.delete(patternFile);\n                preloaderDialog.closeOnUiThread();\n                AppUtils.showToast(context, R.string.unable_to_install_wine);\n                return;\n            }\n\n            preloaderDialog.closeOnUiThread();\n            AppUtils.RestartApplicationOptions options = new AppUtils.RestartApplicationOptions();\n            options.selectedMenuItemId = R.id.menu_item_settings;\n            AppUtils.restartApplication((Activity)context, options);\n        });\n    }\n''',
    )
    manager = root / "app/src/main/java/com/winlator/container/ContainerManager.java"
    replace_once(
        manager,
        '''    private void copyCommonDlls(String srcName, String dstName, JSONObject commonDlls, File containerDir) throws JSONException {\n        File srcDir = new File(RootFS.find(context).getRootDir(), "/opt/wine/lib/wine/"+srcName);\n        JSONArray dlnames = commonDlls.getJSONArray(dstName);\n''',
        '''    private void copyCommonDlls(File wineRoot, String srcName, String dstName, JSONObject commonDlls, File containerDir) throws JSONException {\n        File srcDir = new File(wineRoot, "lib/wine/"+srcName);\n        JSONArray dlnames = commonDlls.getJSONArray(dstName);\n''',
    )
    replace_once(
        manager,
        '''                    JSONObject commonDlls = new JSONObject(FileUtils.readString(context, "common_dlls.json"));\n                    copyCommonDlls("x86_64-windows", "system32", commonDlls, containerDir);\n                    copyCommonDlls("i386-windows", "syswow64", commonDlls, containerDir);\n''',
        '''                    JSONObject commonDlls = new JSONObject(FileUtils.readString(context, "common_dlls.json"));\n                    File mainWineRoot = new File(RootFS.find(context).getRootDir(), "/opt/wine");\n                    copyCommonDlls(mainWineRoot, "x86_64-windows", "system32", commonDlls, containerDir);\n                    copyCommonDlls(mainWineRoot, "i386-windows", "syswow64", commonDlls, containerDir);\n''',
    )
    replace_once(
        manager,
        '''            WineInfo wineInfo = WineInfo.fromIdentifier(context, wineVersion);\n            File file = new File(installedWineDir, "container-pattern-"+wineInfo.fullVersion()+".tzst");\n            return TarCompressorUtils.extract(TarCompressorUtils.Type.ZSTD, file, containerDir);\n''',
        '''            WineInfo wineInfo = WineInfo.fromIdentifier(context, wineVersion);\n            File file = new File(installedWineDir, "container-pattern-"+wineInfo.fullVersion()+".tzst");\n            boolean result = TarCompressorUtils.extract(TarCompressorUtils.Type.ZSTD, file, containerDir);\n\n            if (result) {\n                try {\n                    JSONObject commonDlls = new JSONObject(FileUtils.readString(context, "common_dlls.json"));\n                    File importedWineRoot = new File(wineInfo.path);\n                    copyCommonDlls(importedWineRoot, "x86_64-windows", "system32", commonDlls, containerDir);\n                    copyCommonDlls(importedWineRoot, "i386-windows", "syswow64", commonDlls, containerDir);\n                }\n                catch (JSONException e) {\n                    return false;\n                }\n            }\n\n            return result;\n''',
    )
    strings = root / "app/src/main/res/values/strings.xml"
    text = strings.read_text(encoding="utf-8")
    if '<string name="app_name">Winlator</string>' not in text:
        raise RuntimeError("app_name anchor not found")
    strings.write_text(text.replace('<string name="app_name">Winlator</string>', '<string name="app_name">Winlator TR Compat</string>', 1), encoding="utf-8")


def patch_process_helper(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/core/ProcessHelper.java"
    replace_once(
        path,
        '''    public static int exec(String command, EnvVars envVars, File workingDir, Callback<Integer> terminationCallback) {\n        int pid = -1;\n        try {\n            ProcessBuilder processBuilder = (new ProcessBuilder(splitCommand(command))).directory(workingDir);\n            if (debugCallbacks.isEmpty()) processBuilder.redirectOutput(new File("/dev/null")).redirectErrorStream(true);\n\n            Map<String, String> environment = processBuilder.environment();\n            for (String name : envVars) environment.put(name, envVars.get(name));\n\n            java.lang.Process process = processBuilder.start();\n            Field pidField = process.getClass().getDeclaredField("pid");\n            pidField.setAccessible(true);\n            pid = pidField.getInt(process);\n            pidField.setAccessible(false);\n\n            if (!debugCallbacks.isEmpty()) {\n                createDebugThread(process.getInputStream());\n                createDebugThread(process.getErrorStream());\n            }\n\n            if (terminationCallback != null) createWaitForThread(process, terminationCallback);\n        }\n        catch (Exception e) {}\n        return pid;\n    }\n\n    private static void createDebugThread(final InputStream inputStream) {\n''',
        '''    public static int exec(String command, EnvVars envVars, File workingDir, Callback<Integer> terminationCallback) {\n        int pid = -1;\n        String[] argv = splitCommand(command);\n        TrCompatDiagnostics.trace("PROCESS_HELPER_ENTER command="+command);\n        TrCompatDiagnostics.trace("PROCESS_ARGV="+java.util.Arrays.toString(argv));\n        TrCompatDiagnostics.trace("PROCESS_WORKING_DIR="+(workingDir == null ? "null" : workingDir.getPath())+" exists="+(workingDir != null && workingDir.isDirectory()));\n        try {\n            ProcessBuilder processBuilder = (new ProcessBuilder(argv)).directory(workingDir);\n            Map<String, String> environment = processBuilder.environment();\n            if (envVars != null) {\n                for (String name : envVars) environment.put(name, envVars.get(name));\n            }\n            String[] keys = {"HOME", "USER", "TMPDIR", "DISPLAY", "PATH", "LD_LIBRARY_PATH", "BOX64_LD_LIBRARY_PATH", "ANDROID_SYSVSHM_SERVER", "WINEPREFIX", "WINEDEBUG", "WINEESYNC", "BOX64_TRACE_FILE", "BOX64_RCFILE"};\n            for (String key : keys) TrCompatDiagnostics.trace("PROCESS_ENV "+key+"="+String.valueOf(environment.get(key)));\n\n            TrCompatDiagnostics.trace("PROCESS_BUILDER_BEFORE_START");\n            java.lang.Process process = processBuilder.start();\n            TrCompatDiagnostics.trace("PROCESS_BUILDER_STARTED class="+process.getClass().getName());\n\n            try {\n                Field pidField = process.getClass().getDeclaredField("pid");\n                pidField.setAccessible(true);\n                pid = pidField.getInt(process);\n                pidField.setAccessible(false);\n                TrCompatDiagnostics.trace("PROCESS_PID="+pid);\n            }\n            catch (Throwable pidError) {\n                TrCompatDiagnostics.traceThrowable("PROCESS_PID_EXCEPTION", pidError);\n            }\n\n            createDebugThread(process.getInputStream(), "STDOUT");\n            createDebugThread(process.getErrorStream(), "STDERR");\n            if (terminationCallback != null) createWaitForThread(process, terminationCallback);\n        }\n        catch (Throwable e) {\n            TrCompatDiagnostics.traceThrowable("PROCESS_EXCEPTION", e);\n            TrCompatDiagnostics.exportZip();\n        }\n        TrCompatDiagnostics.trace("PROCESS_HELPER_RETURN_PID="+pid);\n        return pid;\n    }\n\n    private static void createDebugThread(final InputStream inputStream, final String streamName) {\n''',
    )
    replace_once(
        path,
        '''                while ((line = reader.readLine()) != null) {\n                    synchronized (debugCallbacks) {\n''',
        '''                while ((line = reader.readLine()) != null) {\n                    TrCompatDiagnostics.traceProcessLine(streamName, line);\n                    synchronized (debugCallbacks) {\n''',
    )
    replace_once(
        path,
        '''                int status = process.waitFor();\n                terminationCallback.call(status);\n''',
        '''                int status = process.waitFor();\n                TrCompatDiagnostics.trace("PROCESS_EXIT status="+status);\n                TrCompatDiagnostics.exportZip();\n                terminationCallback.call(status);\n''',
    )
    replace_once(
        path,
        '''            catch (InterruptedException e) {}\n''',
        '''            catch (InterruptedException e) {\n                TrCompatDiagnostics.traceThrowable("PROCESS_WAIT_INTERRUPTED", e);\n            }\n''',
    )


def patch_guest_launcher(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    replace_once(
        path,
        '''    public void start() {\n        synchronized (lock) {\n            stop();\n            extractBox64File();\n            copyDefaultBox64RCFile();\n            pid = execGuestProgram();\n        }\n    }\n''',
        '''    public void start() {\n        synchronized (lock) {\n            TrCompatDiagnostics.trace("GUEST_LAUNCHER_START_ENTER");\n            stop();\n            TrCompatDiagnostics.trace("GUEST_BEFORE_EXTRACT_BOX64");\n            extractBox64File();\n            TrCompatDiagnostics.trace("GUEST_AFTER_EXTRACT_BOX64");\n            copyDefaultBox64RCFile();\n            TrCompatDiagnostics.trace("GUEST_AFTER_BOX64RC");\n            pid = execGuestProgram();\n            TrCompatDiagnostics.trace("GUEST_EXEC_RETURN_PID="+pid);\n            if (pid == -1) TrCompatDiagnostics.exportZip();\n        }\n    }\n''',
    )
    replace_once(
        path,
        '''        String command = rootDir+"/usr/local/bin/box64 "+guestExecutable;\n\n        return ProcessHelper.exec(command, envVars, rootDir, (status) -> {\n''',
        '''        String command = rootDir+"/usr/local/bin/box64 "+guestExecutable;\n        File box64File = new File(rootDir, "/usr/local/bin/box64");\n        File wineRoot = new File(rootDir.getPath()+rootFS.getWinePath());\n        File wineFile = new File(wineRoot, "bin/wine");\n        File wineserverFile = new File(wineRoot, "bin/wineserver");\n        File ntdllFile = new File(wineRoot, "lib/wine/x86_64-unix/ntdll.so");\n        File wow64File = new File(wineRoot, "lib/wine/x86_64-windows/wow64.dll");\n\n        TrCompatDiagnostics.trace("GUEST_EXEC_ENTER");\n        TrCompatDiagnostics.trace("ROOT_DIR="+rootDir.getPath());\n        TrCompatDiagnostics.trace("WINE_PATH="+rootFS.getWinePath());\n        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("BOX64", box64File, true));\n        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("WINE_BIN", wineFile, true));\n        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("WINESERVER", wineserverFile, true));\n        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("NTDLL_SO", ntdllFile, true));\n        TrCompatDiagnostics.trace("NTDLL_EXPECTED_SHA256=6f4f2250dc7e8453bba2c164c49d47aa3f492f57d8e178a6cf0b4ddb45b821f9");\n        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("WOW64_DLL", wow64File, true));\n        TrCompatDiagnostics.trace("WOW64_EXPECTED_SHA256=a100b12aa2c4b2151203f881b3b48e9a5af0e000526ccc31ed31de3c72aebe71");\n        TrCompatDiagnostics.trace("COMMAND="+command);\n        TrCompatDiagnostics.trace("WORKING_DIR="+rootDir.getPath());\n        TrCompatDiagnostics.trace("PATH="+envVars.get("PATH"));\n        TrCompatDiagnostics.trace("LD_LIBRARY_PATH="+envVars.get("LD_LIBRARY_PATH"));\n        TrCompatDiagnostics.trace("BOX64_LD_LIBRARY_PATH="+envVars.get("BOX64_LD_LIBRARY_PATH"));\n        TrCompatDiagnostics.trace("WINEPREFIX="+envVars.get("WINEPREFIX"));\n        TrCompatDiagnostics.trace("TMPDIR="+envVars.get("TMPDIR"));\n        TrCompatDiagnostics.trace("TRACE_FILE="+envVars.get("BOX64_TRACE_FILE"));\n\n        return ProcessHelper.exec(command, envVars, rootDir, (status) -> {\n''',
    )
    replace_once(
        path,
        '''import com.winlator.core.ProcessHelper;\n''',
        '''import com.winlator.core.ProcessHelper;\nimport com.winlator.core.TrCompatDiagnostics;\n''',
    )


def patch_activity(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    replace_once(path, "import com.winlator.core.ProcessHelper;\n", "import com.winlator.core.ProcessHelper;\nimport com.winlator.core.TrCompatDiagnostics;\n")
    replace_once(
        path,
        '''    private String screenEffectProfile;\n\n    @Override\n''',
        '''    private String screenEffectProfile;\n    private volatile String trStartupStage = "created";\n\n    private void trTrace(String stage) {\n        trStartupStage = stage;\n        TrCompatDiagnostics.trace(stage);\n    }\n\n    @Override\n''',
    )
    replace_once(
        path,
        '''        super.onCreate(savedInstanceState);\n        AppUtils.hideSystemUI(this);\n''',
        '''        super.onCreate(savedInstanceState);\n        TrCompatDiagnostics.reset();\n        trTrace("ON_CREATE");\n        Executors.newSingleThreadExecutor().execute(TrCompatDiagnostics::collectXignFingerprint);\n        AppUtils.hideSystemUI(this);\n''',
    )
    replace_once(
        path,
        '''            String wineVersion = container.getWineVersion();\n            wineInfo = WineInfo.fromIdentifier(this, wineVersion);\n\n            if (wineInfo != WineInfo.MAIN_WINE_INFO) rootFS.setWinePath(wineInfo.path);\n''',
        '''            String wineVersion = container.getWineVersion();\n            wineInfo = WineInfo.fromIdentifier(this, wineVersion);\n            trTrace("WINE_SELECTED id="+wineVersion+" parsed="+wineInfo.fullVersion()+" path="+wineInfo.path);\n\n            if (wineInfo != WineInfo.MAIN_WINE_INFO) rootFS.setWinePath(wineInfo.path);\n            trTrace("ROOTFS root="+rootFS.getRootDir().getPath()+" winePath="+rootFS.getWinePath());\n''',
    )
    replace_once(
        path,
        '''                    xServerView.getRenderer().setCursorVisible(true);\n                    preloaderDialog.closeOnUiThread();\n''',
        '''                    xServerView.getRenderer().setCursorVisible(true);\n                    trTrace("WINDOW_MAPPED class="+window.getClassName());\n                    TrCompatDiagnostics.exportZip();\n                    preloaderDialog.closeOnUiThread();\n''',
    )
    replace_once(
        path,
        '''        Executors.newSingleThreadExecutor().execute(() -> {\n            if (!isGenerateWineprefix()) {\n                setupWineSystemFiles();\n                extractGraphicsDriverFiles();\n                changeWineAudioDriver();\n            }\n            setupXEnvironment();\n        });\n''',
        '''        new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(() -> {\n            if (!trStartupStage.startsWith("WINDOW_MAPPED")) {\n                trTrace("WATCHDOG_TIMEOUT last="+trStartupStage);\n                TrCompatDiagnostics.exportZip();\n                preloaderDialog.closeOnUiThread();\n                AppUtils.showToast(this, "TR startup timeout: "+trStartupStage);\n            }\n        }, 90000L);\n\n        Executors.newSingleThreadExecutor().execute(() -> {\n            try {\n                trTrace("ASYNC_BEGIN");\n                if (!isGenerateWineprefix()) {\n                    trTrace("BEFORE_SETUP_WINE_SYSTEM_FILES");\n                    setupWineSystemFiles();\n                    trTrace("AFTER_SETUP_WINE_SYSTEM_FILES");\n                    trTrace("BEFORE_EXTRACT_GRAPHICS_DRIVER_FILES");\n                    extractGraphicsDriverFiles();\n                    trTrace("AFTER_EXTRACT_GRAPHICS_DRIVER_FILES");\n                    trTrace("BEFORE_CHANGE_WINE_AUDIO_DRIVER");\n                    changeWineAudioDriver();\n                    trTrace("AFTER_CHANGE_WINE_AUDIO_DRIVER");\n                }\n                trTrace("BEFORE_SETUP_X_ENVIRONMENT");\n                setupXEnvironment();\n                trTrace("AFTER_SETUP_X_ENVIRONMENT_RETURN");\n            }\n            catch (Throwable t) {\n                TrCompatDiagnostics.traceThrowable("STARTUP_EXCEPTION", t);\n                TrCompatDiagnostics.exportZip();\n                runOnUiThread(() -> {\n                    preloaderDialog.closeOnUiThread();\n                    AppUtils.showToast(this, "TR startup exception: "+t.getClass().getSimpleName());\n                });\n            }\n        });\n''',
    )
    replace_once(path, "    private void setupWineSystemFiles() {\n", "    private void setupWineSystemFiles() {\n        trTrace(\"SETUP_WINE_SYSTEM_FILES_ENTER\");\n")
    replace_once(path, "            applyGeneralPatches(container);\n", "            trTrace(\"BEFORE_APPLY_GENERAL_PATCHES\");\n            applyGeneralPatches(container);\n            trTrace(\"AFTER_APPLY_GENERAL_PATCHES\");\n")
    replace_once(
        path,
        '''        if (verifyUserRegistry()) containerDataChanged = true;\n        if (extractDXWrapperFiles()) containerDataChanged = true;\n\n        if (!wincomponents.equals(container.getExtra("wincomponents"))) {\n            extractWinComponentFiles();\n''',
        '''        trTrace("BEFORE_VERIFY_USER_REGISTRY");\n        if (verifyUserRegistry()) containerDataChanged = true;\n        trTrace("AFTER_VERIFY_USER_REGISTRY");\n        trTrace("BEFORE_EXTRACT_DX_WRAPPER_FILES");\n        if (extractDXWrapperFiles()) containerDataChanged = true;\n        trTrace("AFTER_EXTRACT_DX_WRAPPER_FILES");\n\n        if (!wincomponents.equals(container.getExtra("wincomponents"))) {\n            trTrace("BEFORE_EXTRACT_WIN_COMPONENT_FILES");\n            extractWinComponentFiles();\n            trTrace("AFTER_EXTRACT_WIN_COMPONENT_FILES");\n''',
    )
    replace_once(
        path,
        '''        WineStartMenuCreator.create(this, container);\n        WineUtils.createDosdevicesSymlinks(container, true);\n''',
        '''        trTrace("BEFORE_START_MENU_CREATE");\n        WineStartMenuCreator.create(this, container);\n        trTrace("AFTER_START_MENU_CREATE");\n        trTrace("BEFORE_DOSDEVICES_SYMLINKS");\n        WineUtils.createDosdevicesSymlinks(container, true);\n        trTrace("AFTER_DOSDEVICES_SYMLINKS");\n''',
    )
    replace_once(
        path,
        '''        if (containerDataChanged) container.saveData();\n    }\n\n    private void setupXEnvironment() {\n''',
        '''        if (containerDataChanged) container.saveData();\n        trTrace("SETUP_WINE_SYSTEM_FILES_EXIT");\n    }\n\n    private void setupXEnvironment() {\n        trTrace("SETUP_X_ENVIRONMENT_ENTER");\n''',
    )
    replace_once(path, "        environment = new XEnvironment(this, rootFS);\n", "        trTrace(\"BEFORE_NEW_XENVIRONMENT\");\n        environment = new XEnvironment(this, rootFS);\n        trTrace(\"AFTER_NEW_XENVIRONMENT\");\n")
    replace_once(
        path,
        '''        guestProgramLauncherComponent.setEnvVars(envVars);\n        guestProgramLauncherComponent.setTerminationCallback((status) -> exit());\n''',
        '''        guestProgramLauncherComponent.setEnvVars(envVars);\n        guestProgramLauncherComponent.setTerminationCallback((status) -> {\n            trTrace("GUEST_TERMINATED status="+status);\n            TrCompatDiagnostics.exportZip();\n            exit();\n        });\n''',
    )
    replace_once(
        path,
        '''        environment.startEnvironmentComponents();\n\n        winHandler.start();\n''',
        '''        trTrace("BEFORE_START_ENVIRONMENT_COMPONENTS");\n        environment.startEnvironmentComponents();\n        trTrace("AFTER_START_ENVIRONMENT_COMPONENTS");\n\n        winHandler.start();\n        trTrace("AFTER_WINHANDLER_START");\n''',
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_v6_patch.py WINLATOR_APP_DIR", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    patch_base_v5(root)
    write_diagnostics_class(root)
    patch_process_helper(root)
    patch_guest_launcher(root)
    patch_activity(root)
    print("Winlator TR Compat v6 diagnostic patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
