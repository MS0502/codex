#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v16_patch as v16


REVISION = "v17-region-ab-1"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_method(text: str, start_anchor: str, end_anchor: str, replacement: str) -> str:
    start = text.find(start_anchor)
    if start < 0:
        raise RuntimeError(f"method start anchor not found: {start_anchor!r}")
    end = text.find(end_anchor, start)
    if end < 0:
        raise RuntimeError(f"method end anchor not found: {end_anchor!r}")
    return text[:start] + replacement + text[end:]


def patch_v17(root: Path) -> None:
    replace_once(
        root / "app/build.gradle",
        'versionName "11.1-trcompat16-lifetime"',
        'versionName "11.1-trcompat17-region-ab"',
    )

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")

    replacements = {
        "TR_DIAG_v16_LIFETIME.zip": "TR_DIAG_v17_REGION_AB.zip",
        "DIAGNOSTICS_RESET version=16-lifetime": "DIAGNOSTICS_RESET version=17-region-ab",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics v17 anchor not found: {old}")
        text = text.replace(old, new)

    import_anchor = "import java.io.BufferedInputStream;\n"
    if import_anchor not in text:
        raise RuntimeError("v17 BufferedInputStream import anchor not found")
    text = text.replace(
        import_anchor,
        import_anchor + "import java.io.BufferedReader;\n",
        1,
    )

    input_anchor = "import java.io.InputStream;\n"
    if input_anchor not in text:
        raise RuntimeError("v17 InputStream import anchor not found")
    text = text.replace(
        input_anchor,
        input_anchor + "import java.io.InputStreamReader;\n",
        1,
    )

    old_fields = '''    private static File wellbiaLowloadFile;
    private static File processLifetimeFile;
    private static File zipFile;
    private static String lastLifetimeSnapshot = "";
'''
    new_fields = '''    private static File wellbiaLowloadFile;
    private static File processLifetimeFile;
    private static File moduleMapsFile;
    private static File zipFile;
    private static String lastLifetimeSnapshot = "";
    private static String lastModuleMapsSnapshot = "";
'''
    if old_fields not in text:
        raise RuntimeError("diagnostics v17 field anchor not found")
    text = text.replace(old_fields, new_fields, 1)

    old_paths = '''        wellbiaLowloadFile = new File(parentDir, "wellbia_lowload.txt");
        processLifetimeFile = new File(parentDir, "process_lifetime.txt");
        zipFile = new File(parentDir, "TR_DIAG_v17_REGION_AB.zip");
'''
    new_paths = '''        wellbiaLowloadFile = new File(parentDir, "wellbia_lowload.txt");
        processLifetimeFile = new File(parentDir, "process_lifetime.txt");
        moduleMapsFile = new File(parentDir, "module_maps.txt");
        zipFile = new File(parentDir, "TR_DIAG_v17_REGION_AB.zip");
'''
    if old_paths not in text:
        raise RuntimeError("diagnostics v17 path anchor not found")
    text = text.replace(old_paths, new_paths, 1)

    old_reset = '''            LOWLOAD_COLLECTOR_STARTED.set(false);
            lastLifetimeSnapshot = "";
            traceFile.delete();
            fingerprintFile.delete();
            wellbiaLowloadFile.delete();
            processLifetimeFile.delete();
            zipFile.delete();
'''
    new_reset = '''            LOWLOAD_COLLECTOR_STARTED.set(false);
            lastLifetimeSnapshot = "";
            lastModuleMapsSnapshot = "";
            traceFile.delete();
            fingerprintFile.delete();
            wellbiaLowloadFile.delete();
            processLifetimeFile.delete();
            moduleMapsFile.delete();
            zipFile.delete();
'''
    if old_reset not in text:
        raise RuntimeError("diagnostics v17 reset anchor not found")
    text = text.replace(old_reset, new_reset, 1)

    old_candidate = '''    private static boolean isXignCandidate(File file) {
        String name = file.getName().toLowerCase(Locale.US);
        return (name.startsWith("x") && name.endsWith(".xem"))
                || (name.startsWith("xldr") && name.endsWith(".exe"))
                || (name.startsWith("xhunter") && name.endsWith(".sys"))
                || (name.contains("xigncode") && (name.endsWith(".dll") || name.endsWith(".exe") || name.endsWith(".sys")));
    }
'''
    new_candidate = '''    private static boolean isXignCandidate(File file) {
        String name = file.getName().toLowerCase(Locale.US);
        return name.equals("talesrunner.exe") || name.equals("trgame.exe")
                || (name.startsWith("x") && name.endsWith(".xem"))
                || (name.startsWith("xldr") && name.endsWith(".exe"))
                || (name.startsWith("xhunter") && name.endsWith(".sys"))
                || (name.contains("xigncode") && (name.endsWith(".dll") || name.endsWith(".exe") || name.endsWith(".sys")));
    }
'''
    if old_candidate not in text:
        raise RuntimeError("diagnostics v17 runtime candidate anchor not found")
    text = text.replace(old_candidate, new_candidate, 1)

    fingerprint_method = r'''    public static void collectXignFingerprint() {
        ensurePaths();
        File downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
        File[] bases = {
                new File(downloads, "TR_KR_LOCAL"),
                new File(downloads, "TR_TH_LOCAL")
        };

        synchronized (LOCK) {
            try (FileWriter writer = new FileWriter(fingerprintFile, false)) {
                writer.write("TalesRunner KR/TH runtime fingerprint v17 region A/B\n");
                writer.write("COLLECTED_AT="+System.currentTimeMillis()+"\n\n");

                int totalMatches = 0;
                for (File base : bases) {
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
                            if (child.isDirectory() && depth < 6) queue.addLast(new Object[]{child, depth + 1});
                            else if (child.isFile() && isXignCandidate(child)) matches.add(child);
                        }
                    }
                    Collections.sort(matches, Comparator.comparing(File::getPath, String.CASE_INSENSITIVE_ORDER));
                    totalMatches += matches.size();

                    String region = base.getName().contains("_TH_") ? "TH" : "KR";
                    writer.write("REGION="+region+"\n");
                    writer.write("BASE="+base.getPath()+"\n");
                    writer.write("BASE_EXISTS="+base.exists()+"\n");
                    writer.write("COUNT="+matches.size()+"\n");
                    for (File file : matches) {
                        String relative;
                        try {
                            String basePath = base.getCanonicalPath();
                            String filePath = file.getCanonicalPath();
                            relative = filePath.startsWith(basePath)
                                    ? filePath.substring(basePath.length()).replaceFirst("^/+", "")
                                    : file.getName();
                        }
                        catch (Exception e) {
                            relative = file.getName();
                        }
                        writer.write("FILE="+relative+"\n");
                        writer.write("SIZE="+file.length()+"\n");
                        writer.write("MODIFIED="+file.lastModified()+"\n");
                        writer.write("SHA256="+sha256(file)+"\n\n");
                    }
                    writer.write("----\n\n");
                }
                writer.flush();
                trace("REGION_FINGERPRINT_COMPLETE total="+totalMatches+" file="+fingerprintFile.getPath());
            }
            catch (Exception e) {
                traceThrowable("REGION_FINGERPRINT_EXCEPTION", e);
            }
        }
        exportZip();
    }

'''
    text = replace_method(
        text,
        "    public static void collectXignFingerprint() {\n",
        "    private static void addToZip",
        fingerprint_method,
    )

    module_anchor = '''    private static boolean lowloadLogCandidate(File file) {
'''
    module_methods = r'''    private static boolean moduleMapRelevant(String value) {
        String lower = value == null ? "" : value.toLowerCase(Locale.US);
        return lower.contains("talesrunner") || lower.contains("trgame")
                || lower.contains("xldr") || lower.contains("x3_")
                || lower.contains("/x3.") || lower.contains("xcorona")
                || lower.contains("xmag") || lower.contains("xnina")
                || lower.contains("xhunter") || lower.contains("xigncode")
                || lower.contains("wellbia") || lower.contains(".xem");
    }

    public static void collectModuleMaps(String stage) {
        ensurePaths();
        List<ProcessHelper.PStat> processes = new ArrayList<>(ProcessHelper.getChildProcesses());
        Collections.sort(processes, Comparator.comparingInt((ProcessHelper.PStat item) -> item.pid));

        StringBuilder snapshot = new StringBuilder();
        int processCount = 0;
        int mapCount = 0;
        for (ProcessHelper.PStat stat : processes) {
            if (!lifetimeRelevant(stat) || stat.pid <= 0) continue;
            processCount++;
            File maps = new File("/proc/"+stat.pid+"/maps");
            if (!maps.isFile() || !maps.canRead()) {
                snapshot.append("PID=").append(stat.pid)
                        .append(" NAME=").append(stat.name)
                        .append(" MAPS_READABLE=false\n");
                continue;
            }
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(new FileInputStream(maps), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (!moduleMapRelevant(line)) continue;
                    mapCount++;
                    String safe = sanitizeProcessLine(line);
                    if (safe.length() > MAX_LINE_CHARS) {
                        safe = safe.substring(0, MAX_LINE_CHARS)+"...[truncated]";
                    }
                    snapshot.append("PID=").append(stat.pid)
                            .append(" NAME=").append(stat.name)
                            .append(" MAP=").append(safe)
                            .append('\n');
                }
            }
            catch (Exception e) {
                snapshot.append("PID=").append(stat.pid)
                        .append(" NAME=").append(stat.name)
                        .append(" MAPS_ERROR=").append(e.getClass().getSimpleName())
                        .append(':').append(String.valueOf(e.getMessage()))
                        .append('\n');
            }
        }

        String current = snapshot.toString();
        boolean changed;
        synchronized (LOCK) {
            changed = !current.equals(lastModuleMapsSnapshot);
            lastModuleMapsSnapshot = current;
            try (FileWriter writer = new FileWriter(moduleMapsFile, true)) {
                writer.write("===== stage="+stage+" time="+System.currentTimeMillis()
                        +" processes="+processCount+" maps="+mapCount
                        +" changed="+changed+" =====\n");
                if (current.isEmpty()) writer.write("[NO_RELEVANT_MAPPINGS]\n");
                else writer.write(current);
                writer.flush();
            }
            catch (Exception e) {
                traceThrowable("MODULE_MAPS_EXCEPTION", e);
            }
        }
        trace("MODULE_MAPS stage="+stage+" processes="+processCount
                +" maps="+mapCount+" changed="+changed);
    }

'''
    if module_anchor not in text:
        raise RuntimeError("diagnostics v17 module-map anchor not found")
    text = text.replace(module_anchor, module_methods + module_anchor, 1)

    old_collector = '''                collectProcessLifetime(stage);
                if (seconds == 0 || seconds == 30 || seconds == 60
'''
    new_collector = '''                collectProcessLifetime(stage);
                collectModuleMaps(stage);
                if (seconds == 0 || seconds == 30 || seconds == 60
'''
    if old_collector not in text:
        raise RuntimeError("diagnostics v17 collector anchor not found")
    text = text.replace(old_collector, new_collector, 1)

    old_zip = '''                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
                addToZip(zip, processLifetimeFile, "process_lifetime.txt");
'''
    new_zip = '''                addToZip(zip, wellbiaLowloadFile, "wellbia_lowload.txt");
                addToZip(zip, processLifetimeFile, "process_lifetime.txt");
                addToZip(zip, moduleMapsFile, "module_maps.txt");
'''
    if old_zip not in text:
        raise RuntimeError("diagnostics v17 zip anchor not found")
    text = text.replace(old_zip, new_zip, 1)
    diag.write_text(text, encoding="utf-8")

    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    text = activity.read_text(encoding="utf-8")
    if "WINEDEBUG_LIFETIME=" not in text:
        raise RuntimeError("v16 WINEDEBUG lifetime marker not found")
    text = text.replace("WINEDEBUG_LIFETIME=", "WINEDEBUG_REGION_AB=", 1)
    activity.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java"
    text = patcher.read_text(encoding="utf-8")
    old_revision = 'private static final String REVISION = "v16-lifetime-server-1";'
    if old_revision not in text:
        raise RuntimeError("v16 runtime revision anchor not found")
    text = text.replace(old_revision, f'private static final String REVISION = "{REVISION}";', 1)
    text = text.replace(".trcompat-v16.tmp", ".trcompat-v17.tmp")
    patcher.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v17_patch.py WINLATOR_APP_DIR OFFICIAL_COMPONENT_DIR", file=sys.stderr)
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

    patch_v17(root)
    print("Winlator TR Compat v17 KR/TH region A/B diagnostics applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
