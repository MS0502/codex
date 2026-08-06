#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v16_patch as v16


JAVA_SOURCE = r'''package com.winlator;

import android.app.ActivityManager;
import android.app.Application;
import android.app.ApplicationExitInfo;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Environment;
import android.os.Process;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.InputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * Crash-only observability for the exact v16 runtime.
 *
 * This class does not modify rootfs, Wine, Box64, containers, game files,
 * authentication, or security-module behavior.
 */
public final class TrCrashApplication extends Application {
    private static final Object LOCK = new Object();
    private static final String REPORT_NAME = "TR_CRASH_v26.txt";
    private static final String PREFS_NAME = "tr_crash_v26";
    private static final String PREF_LAST_EXIT = "last_exit_timestamp";
    private static final int MAX_TRACE_BYTES = 2 * 1024 * 1024;

    @Override
    public void onCreate() {
        super.onCreate();
        installJavaCrashHandler();
        exportInternalFallbacks();
        collectHistoricalExitInfoAsync();
    }

    private void installJavaCrashHandler() {
        final Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() {
            @Override
            public void uncaughtException(Thread thread, Throwable error) {
                try {
                    StringWriter stack = new StringWriter();
                    PrintWriter printer = new PrintWriter(stack);
                    error.printStackTrace(printer);
                    printer.flush();

                    StringBuilder report = new StringBuilder();
                    report.append("===== JAVA_UNCAUGHT ").append(now()).append(" =====\n");
                    report.append("thread=").append(thread == null ? "null" : safe(thread.getName()))
                            .append(" id=").append(thread == null ? -1 : thread.getId()).append('\n');
                    report.append("process=").append(getPackageName())
                            .append(" pid=").append(Process.myPid())
                            .append(" sdk=").append(Build.VERSION.SDK_INT).append('\n');
                    report.append(stack).append('\n');
                    writeTextWithFallback(REPORT_NAME, report.toString());
                }
                catch (Throwable ignored) {}

                if (previous != null) {
                    previous.uncaughtException(thread, error);
                }
                else {
                    Process.killProcess(Process.myPid());
                    System.exit(10);
                }
            }
        });
    }

    private void collectHistoricalExitInfoAsync() {
        if (Build.VERSION.SDK_INT < 30) return;
        Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                collectHistoricalExitInfo();
            }
        }, "tr-exit-info-v26");
        worker.setDaemon(true);
        worker.start();
    }

    private void collectHistoricalExitInfo() {
        try {
            ActivityManager manager = (ActivityManager)getSystemService(Context.ACTIVITY_SERVICE);
            if (manager == null) return;

            List<ApplicationExitInfo> source = manager.getHistoricalProcessExitReasons(
                    getPackageName(), 0, 16
            );
            if (source == null || source.isEmpty()) return;

            List<ApplicationExitInfo> exits = new ArrayList<>(source);
            Collections.sort(exits, new Comparator<ApplicationExitInfo>() {
                @Override
                public int compare(ApplicationExitInfo left, ApplicationExitInfo right) {
                    return Long.compare(left.getTimestamp(), right.getTimestamp());
                }
            });

            SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
            long lastRecorded = prefs.getLong(PREF_LAST_EXIT, 0L);
            long newestRecorded = lastRecorded;

            for (ApplicationExitInfo info : exits) {
                if (info.getTimestamp() <= lastRecorded) continue;

                StringBuilder report = new StringBuilder();
                report.append("===== APPLICATION_EXIT ").append(now()).append(" =====\n");
                report.append("timestamp=").append(info.getTimestamp()).append('\n');
                report.append("reason=").append(reasonName(info.getReason()))
                        .append('(').append(info.getReason()).append(")\n");
                report.append("status=").append(info.getStatus()).append('\n');
                report.append("importance=").append(info.getImportance()).append('\n');
                report.append("pss_kb=").append(info.getPss()).append('\n');
                report.append("rss_kb=").append(info.getRss()).append('\n');
                report.append("process=").append(safe(info.getProcessName())).append('\n');
                report.append("description=").append(safe(info.getDescription())).append('\n');

                boolean metadataSaved = writeTextWithFallback(REPORT_NAME, report.toString());
                saveTraceIfPresent(info);
                if (metadataSaved) newestRecorded = Math.max(newestRecorded, info.getTimestamp());
            }

            if (newestRecorded > lastRecorded) {
                prefs.edit().putLong(PREF_LAST_EXIT, newestRecorded).apply();
            }
        }
        catch (Throwable error) {
            writeThrowable("EXIT_INFO_COLLECTION_FAILURE", error);
        }
    }

    private void saveTraceIfPresent(ApplicationExitInfo info) {
        InputStream input = null;
        try {
            input = info.getTraceInputStream();
            if (input == null) return;
            String name = "TR_EXIT_TRACE_v26_" + info.getTimestamp() + "_"
                    + reasonName(info.getReason()) + ".bin";
            writeStreamWithFallback(name, input, MAX_TRACE_BYTES);
        }
        catch (Throwable error) {
            writeThrowable("EXIT_TRACE_COLLECTION_FAILURE", error);
        }
        finally {
            if (input != null) {
                try { input.close(); }
                catch (Throwable ignored) {}
            }
        }
    }

    private boolean writeTextWithFallback(String name, String text) {
        synchronized (LOCK) {
            if (appendText(externalDirectory(), name, text)) return true;
            return appendText(internalDirectory(), name, text);
        }
    }

    private boolean appendText(File directory, String name, String text) {
        try {
            if (!ensureDirectory(directory)) return false;
            File target = new File(directory, name);
            try (FileWriter writer = new FileWriter(target, true)) {
                writer.write(text);
                writer.flush();
            }
            return true;
        }
        catch (Throwable ignored) {
            return false;
        }
    }

    private boolean writeStreamWithFallback(String name, InputStream source, int maxBytes) {
        synchronized (LOCK) {
            File external = externalDirectory();
            if (writeStream(external, name, source, maxBytes)) return true;
            return false;
        }
    }

    private boolean writeStream(File directory, String name, InputStream source, int maxBytes) {
        try {
            if (!ensureDirectory(directory)) {
                return writeStreamToInternal(name, source, maxBytes);
            }
            return copyLimited(source, new File(directory, name), maxBytes);
        }
        catch (Throwable ignored) {
            try {
                return writeStreamToInternal(name, source, maxBytes);
            }
            catch (Throwable ignoredAgain) {
                return false;
            }
        }
    }

    private boolean writeStreamToInternal(String name, InputStream source, int maxBytes) throws Exception {
        File directory = internalDirectory();
        if (!ensureDirectory(directory)) return false;
        return copyLimited(source, new File(directory, name), maxBytes);
    }

    private boolean copyLimited(InputStream source, File target, int maxBytes) throws Exception {
        try (BufferedInputStream input = new BufferedInputStream(source);
             BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(target, false))) {
            byte[] buffer = new byte[16384];
            int total = 0;
            while (total < maxBytes) {
                int wanted = Math.min(buffer.length, maxBytes - total);
                int read = input.read(buffer, 0, wanted);
                if (read < 0) break;
                output.write(buffer, 0, read);
                total += read;
            }
            output.flush();
        }
        return true;
    }

    private void exportInternalFallbacks() {
        synchronized (LOCK) {
            File internal = internalDirectory();
            File external = externalDirectory();
            if (!internal.isDirectory() || !ensureDirectory(external)) return;
            File[] files = internal.listFiles();
            if (files == null) return;

            for (File source : files) {
                if (!source.isFile()) continue;
                String exportName = "INTERNAL_FALLBACK_" + source.getName();
                File target = new File(external, exportName);
                try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(source));
                     BufferedOutputStream output = new BufferedOutputStream(new FileOutputStream(target, true))) {
                    byte[] buffer = new byte[16384];
                    int read;
                    while ((read = input.read(buffer)) >= 0) output.write(buffer, 0, read);
                    output.flush();
                    if (!source.delete()) source.deleteOnExit();
                }
                catch (Throwable ignored) {}
            }
        }
    }

    private void writeThrowable(String label, Throwable error) {
        try {
            StringWriter stack = new StringWriter();
            PrintWriter printer = new PrintWriter(stack);
            error.printStackTrace(printer);
            printer.flush();
            writeTextWithFallback(REPORT_NAME,
                    "===== " + label + " " + now() + " =====\n" + stack + "\n");
        }
        catch (Throwable ignored) {}
    }

    private File externalDirectory() {
        return new File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS),
                "Winlator"
        );
    }

    private File internalDirectory() {
        return new File(getFilesDir(), "tr-crash-v26");
    }

    private static boolean ensureDirectory(File directory) {
        return directory.isDirectory() || directory.mkdirs();
    }

    private static String now() {
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", Locale.US).format(new Date());
    }

    private static String safe(String value) {
        if (value == null) return "null";
        String result = value.replace('\r', ' ').replace('\n', ' ');
        return result.length() <= 4096 ? result : result.substring(0, 4096) + "[TRUNCATED]";
    }

    private static String reasonName(int reason) {
        switch (reason) {
            case ApplicationExitInfo.REASON_EXIT_SELF: return "EXIT_SELF";
            case ApplicationExitInfo.REASON_SIGNALED: return "SIGNALED";
            case ApplicationExitInfo.REASON_LOW_MEMORY: return "LOW_MEMORY";
            case ApplicationExitInfo.REASON_CRASH: return "CRASH";
            case ApplicationExitInfo.REASON_CRASH_NATIVE: return "CRASH_NATIVE";
            case ApplicationExitInfo.REASON_ANR: return "ANR";
            case ApplicationExitInfo.REASON_INITIALIZATION_FAILURE: return "INITIALIZATION_FAILURE";
            case ApplicationExitInfo.REASON_PERMISSION_CHANGE: return "PERMISSION_CHANGE";
            case ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE: return "EXCESSIVE_RESOURCE_USAGE";
            case ApplicationExitInfo.REASON_USER_REQUESTED: return "USER_REQUESTED";
            case ApplicationExitInfo.REASON_USER_STOPPED: return "USER_STOPPED";
            case ApplicationExitInfo.REASON_DEPENDENCY_DIED: return "DEPENDENCY_DIED";
            case ApplicationExitInfo.REASON_OTHER: return "OTHER";
            case ApplicationExitInfo.REASON_FREEZER: return "FREEZER";
            case ApplicationExitInfo.REASON_PACKAGE_STATE_CHANGE: return "PACKAGE_STATE_CHANGE";
            case ApplicationExitInfo.REASON_PACKAGE_UPDATED: return "PACKAGE_UPDATED";
            default: return "UNKNOWN";
        }
    }
}
'''


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_v26(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat16-lifetime"',
        'versionName "11.1-trcompat26-crash-observability"',
    )

    manifest = root / "app/src/main/AndroidManifest.xml"
    replace_once(
        manifest,
        "    <application\n        android:icon=\"@mipmap/ic_launcher\"",
        "    <application\n        android:name=\".TrCrashApplication\"\n        android:icon=\"@mipmap/ic_launcher\"",
    )

    application = root / "app/src/main/java/com/winlator/TrCrashApplication.java"
    if application.exists():
        raise RuntimeError(f"unexpected existing crash application: {application}")
    application.write_text(JAVA_SOURCE, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: apply_v26_crash_observability_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR",
            file=sys.stderr,
        )
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

    patch_v26(root)
    print("Winlator TR Compat v26 crash observability applied over exact v16 baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
