#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def replace_exact(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("winlator_root", type=Path)
    args = parser.parse_args()
    root = args.winlator_root.resolve()

    replace_exact(root / "app/build.gradle", '11.1-trcompat18b-proton11-valve-glibc',
                  '11.1-trcompat18i-proton11-winlator-profile', "version name")

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    for old, new in {
        'TR_DIAG_v18B_PROTON11_GLIBC.zip': 'TR_DIAG_v18I_PROTON11_WINLATOR_PROFILE.zip',
        'version=18b-proton11-valve-glibc': 'version=18i-proton11-winlator-profile',
        'v18b Valve Proton 11 glibc': 'v18i Proton 11 Winlator profile',
    }.items():
        if text.count(old) < 1:
            raise RuntimeError(f"diagnostics anchor missing: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    for relative in (
        "app/src/main/java/com/winlator/core/TrCompatWinePatcher.java",
        "app/src/main/java/com/winlator/core/TrCompatRootfsPatcher.java",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if text.count("v18b-proton11-valve-glibc-1") != 1:
            raise RuntimeError(f"revision anchor missing in {path}")
        text = text.replace("v18b-proton11-valve-glibc-1", "v18i-proton11-winlator-profile-1", 1)
        text = text.replace(".trcompat-v18b.tmp", ".trcompat-v18i.tmp")
        path.write_text(text, encoding="utf-8")

    patcher = root / "app/src/main/java/com/winlator/core/TrCompatRootfsPatcher.java"
    text = patcher.read_text(encoding="utf-8")
    import_anchor = "import java.util.ArrayDeque;\n"
    if text.count(import_anchor) != 1:
        raise RuntimeError("ArrayDeque import anchor missing")
    text = text.replace(import_anchor, import_anchor + "import java.util.UUID;\n", 1)

    call_anchor = "            ensureAlias(alias, root);\n            TrCompatDiagnostics.trace(\"ROOTFS_ALIAS path=\"+alias.getPath()+\" target=\"+root.getPath());\n"
    if text.count(call_anchor) != 1:
        raise RuntimeError("rootfs initialization anchor missing")
    text = text.replace(call_anchor,
        "            ensureAlias(alias, root);\n"
        "            ensureMachineId(root);\n"
        "            TrCompatDiagnostics.trace(\"ROOTFS_ALIAS path=\"+alias.getPath()+\" target=\"+root.getPath());\n", 1)

    method_anchor = "    private static void ensureAlias(File alias, File root) throws Exception {\n"
    if text.count(method_anchor) != 1:
        raise RuntimeError("ensureAlias method anchor missing")
    method = r'''    private static void ensureMachineId(File root) throws Exception {
        File etc = new File(root, "etc");
        if (!etc.isDirectory() && !etc.mkdirs()) {
            throw new java.io.IOException("unable to create "+etc.getPath());
        }
        File machineId = new File(etc, "machine-id");
        String current = "";
        if (machineId.isFile()) {
            current = new String(Files.readAllBytes(machineId.toPath()), StandardCharsets.US_ASCII).trim();
        }
        if (current.matches("[0-9a-fA-F]{32}") && !current.matches("0{32}")) {
            TrCompatDiagnostics.trace("MACHINE_ID_PRESENT length="+current.length());
            return;
        }
        String generated = UUID.randomUUID().toString().replace("-", "")+"\n";
        try (FileOutputStream output = new FileOutputStream(machineId, false)) {
            output.write(generated.getBytes(StandardCharsets.US_ASCII));
            output.flush();
        }
        Os.chmod(machineId.getPath(), 0644);
        TrCompatDiagnostics.trace("MACHINE_ID_CREATED path="+machineId.getPath());
    }

'''
    text = text.replace(method_anchor, method + method_anchor, 1)
    patcher.write_text(text, encoding="utf-8")

    joined = "\n".join(p.read_text(encoding="utf-8") for p in [root / "app/build.gradle", diag, patcher])
    for value in ("11.1-trcompat18i-proton11-winlator-profile", "v18i-proton11-winlator-profile-1",
                  "ensureMachineId(root);", "UUID.randomUUID()"):
        if value not in joined:
            raise RuntimeError(f"postcondition missing: {value}")

    Path("v18i-winlator-patch.txt").write_text(
        "version=11.1-trcompat18i-proton11-winlator-profile\n"
        "revision=v18i-proton11-winlator-profile-1\n"
        "runtime_machine_id=per-install UUID\n", encoding="utf-8")
    print("v18I Winlator labeling and machine-id initialization applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
