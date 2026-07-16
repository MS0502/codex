#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import apply_v6_patch as v6

PACKAGE = "com.winlator.trcompat"
BOX64_INTERPRETER = f"/data/data/{PACKAGE}/files/rootfs/lib/ld-linux-aarch64.so.1"
REVISION = "v7-interpreter-native-fallback-1"


def run(*args: str, stdout=None) -> subprocess.CompletedProcess:
    print("+", " ".join(args))
    return subprocess.run(args, check=True, stdout=stdout)


def replace_once(path: Path, old: str, new: str) -> None:
    v6.replace_once(path, old, new)


def patch_versions(root: Path) -> None:
    replace_once(root / "app/build.gradle", 'versionName "11.1-trcompat6"', 'versionName "11.1-trcompat7"')

    diag = root / "app/src/main/java/com/winlator/core/TrCompatDiagnostics.java"
    text = diag.read_text(encoding="utf-8")
    replacements = {
        'TR_DIAG_v6.zip': 'TR_DIAG_v7.zip',
        'DIAGNOSTICS_RESET version=6': 'DIAGNOSTICS_RESET version=7',
        'TalesRunner KR XIGNCODE fingerprint v6': 'TalesRunner KR XIGNCODE fingerprint v7',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"diagnostics version anchor not found: {old}")
        text = text.replace(old, new)
    diag.write_text(text, encoding="utf-8")

    gradle = root / "app/build.gradle"
    replace_once(
        gradle,
        "    packagingOptions {\n        pickFirst 'lib/arm64-v8a/*.so'\n    }\n",
        "    packagingOptions {\n"
        "        pickFirst 'lib/arm64-v8a/*.so'\n"
        "        doNotStrip '**/libtr_box64_exec.so'\n"
        "        doNotStrip '**/libtr_glibc_loader.so'\n"
        "    }\n",
    )


def prepare_box64_and_native_fallback(root: Path) -> None:
    assets = root / "app/src/main/assets"
    box_archives = sorted((assets / "box64").glob("box64-*.tzst"))
    if len(box_archives) != 1:
        raise RuntimeError(f"expected one built-in Box64 archive, found {box_archives}")
    box_archive = box_archives[0]
    rootfs_archive = assets / "rootfs.tzst"
    if not rootfs_archive.is_file():
        raise RuntimeError(f"missing rootfs archive: {rootfs_archive}")

    jni = root / "app/src/main/jniLibs/arm64-v8a"
    jni.mkdir(parents=True, exist_ok=True)
    native_box64 = jni / "libtr_box64_exec.so"
    native_loader = jni / "libtr_glibc_loader.so"

    with tempfile.TemporaryDirectory(prefix="tr-v7-box64-") as temp_name:
        temp = Path(temp_name)
        run("tar", "--use-compress-program=unzstd", "-xf", str(box_archive), "-C", str(temp))
        box64 = temp / "usr/local/bin/box64"
        if not box64.is_file():
            raise RuntimeError(f"Box64 executable missing after extraction: {box64}")

        old_interpreter = subprocess.check_output(["patchelf", "--print-interpreter", str(box64)], text=True).strip()
        print(f"Box64 interpreter before: {old_interpreter}")
        run("patchelf", "--set-interpreter", BOX64_INTERPRETER, str(box64))
        new_interpreter = subprocess.check_output(["patchelf", "--print-interpreter", str(box64)], text=True).strip()
        if new_interpreter != BOX64_INTERPRETER:
            raise RuntimeError(f"unexpected Box64 interpreter: {new_interpreter}")
        box64.chmod(0o755)
        shutil.copy2(box64, native_box64)
        native_box64.chmod(0o755)

        tar_path = temp / "box64-v7.tar"
        run(
            "tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner",
            "--mtime=@0", "-C", str(temp), "-cf", str(tar_path), "./usr"
        )
        run("zstd", "-19", "-f", str(tar_path), "-o", str(box_archive))

    with native_loader.open("wb") as output:
        run(
            "tar", "--use-compress-program=unzstd", "-xOf", str(rootfs_archive),
            "./usr/lib/ld-linux-aarch64.so.1", stdout=output
        )
    native_loader.chmod(0o755)

    run("file", str(native_box64), str(native_loader))
    run("sha256sum", str(native_box64), str(native_loader), str(box_archive))
    print(f"Box64 interpreter after: {BOX64_INTERPRETER}")


def patch_box64_refresh(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    replace_once(
        path,
        '''        String currentBox64Version = preferences.getString("current_box64_version", "");

        if (!box64Version.equals(currentBox64Version)) {
            GeneralComponents.extractFile(GeneralComponents.Type.BOX64, context, box64Version, DefaultVersion.BOX64);
            preferences.edit().putString("current_box64_version", box64Version).apply();
        }
''',
        f'''        String currentBox64Version = preferences.getString("current_box64_version", "");
        String trCompatRevision = preferences.getString("trcompat_box64_revision", "");

        if (!box64Version.equals(currentBox64Version) || !"{REVISION}".equals(trCompatRevision)) {{
            TrCompatDiagnostics.trace("BOX64_REFRESH version="+box64Version+" oldRevision="+trCompatRevision);
            GeneralComponents.extractFile(GeneralComponents.Type.BOX64, context, box64Version, DefaultVersion.BOX64);
            preferences.edit()
                    .putString("current_box64_version", box64Version)
                    .putString("trcompat_box64_revision", "{REVISION}")
                    .apply();
        }}
''',
    )


def patch_three_stage_launcher(root: Path) -> None:
    path = root / "app/src/main/java/com/winlator/xenvironment/components/GuestProgramLauncherComponent.java"
    replace_once(
        path,
        '''        String command = rootDir+"/usr/local/bin/box64 "+guestExecutable;
        File box64File = new File(rootDir, "/usr/local/bin/box64");
''',
        '''        File box64File = new File(rootDir, "/usr/local/bin/box64");
        File rootLoaderFile = new File(rootDir, "/lib/ld-linux-aarch64.so.1");
        File nativeLibDir = new File(environment.getContext().getApplicationInfo().nativeLibraryDir);
        File nativeLoaderFile = new File(nativeLibDir, "libtr_glibc_loader.so");
        File nativeBox64File = new File(nativeLibDir, "libtr_box64_exec.so");
        String libraryPath = rootDir+"/usr/lib:"+rootDir+"/lib";
        String directCommand = box64File.getPath()+" "+guestExecutable;
        String rootLoaderCommand = rootLoaderFile.getPath()+" --library-path "+libraryPath+" "+box64File.getPath()+" "+guestExecutable;
        String nativeCommand = nativeLoaderFile.getPath()+" --library-path "+libraryPath+" "+nativeBox64File.getPath()+" "+guestExecutable;
        String command = directCommand;
''',
    )
    replace_once(
        path,
        '''        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("BOX64", box64File, true));
        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("WINE_BIN", wineFile, true));
''',
        f'''        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("BOX64", box64File, true));
        TrCompatDiagnostics.trace("BOX64_INTERPRETER_EXPECTED={BOX64_INTERPRETER}");
        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("ROOT_GLIBC_LOADER", rootLoaderFile, true));
        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("NATIVE_GLIBC_LOADER", nativeLoaderFile, true));
        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("NATIVE_BOX64", nativeBox64File, true));
        TrCompatDiagnostics.trace("COMMAND_STAGE1_DIRECT="+directCommand);
        TrCompatDiagnostics.trace("COMMAND_STAGE2_ROOT_LOADER="+rootLoaderCommand);
        TrCompatDiagnostics.trace("COMMAND_STAGE3_NATIVE="+nativeCommand);
        TrCompatDiagnostics.trace(TrCompatDiagnostics.describeFile("WINE_BIN", wineFile, true));
''',
    )
    replace_once(
        path,
        '''        return ProcessHelper.exec(command, envVars, rootDir, (status) -> {
            synchronized (lock) {
                pid = -1;
            }
            if (terminationCallback != null) terminationCallback.call(status);
        });
''',
        '''        Callback<Integer> finalCallback = (status) -> {
            synchronized (lock) {
                pid = -1;
            }
            if (terminationCallback != null) terminationCallback.call(status);
        };

        TrCompatDiagnostics.trace("LAUNCH_STAGE1_DIRECT_BEGIN");
        int result = ProcessHelper.exec(directCommand, envVars, rootDir, finalCallback);
        TrCompatDiagnostics.trace("LAUNCH_STAGE1_DIRECT_PID="+result);
        if (result == -1) {
            TrCompatDiagnostics.trace("LAUNCH_STAGE2_ROOT_LOADER_BEGIN");
            result = ProcessHelper.exec(rootLoaderCommand, envVars, rootDir, finalCallback);
            TrCompatDiagnostics.trace("LAUNCH_STAGE2_ROOT_LOADER_PID="+result);
        }
        if (result == -1) {
            TrCompatDiagnostics.trace("LAUNCH_STAGE3_NATIVE_BEGIN");
            result = ProcessHelper.exec(nativeCommand, envVars, rootDir, finalCallback);
            TrCompatDiagnostics.trace("LAUNCH_STAGE3_NATIVE_PID="+result);
        }
        TrCompatDiagnostics.exportZip();
        return result;
''',
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_v7_patch.py WINLATOR_APP_DIR", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()

    v6.patch_base_v5(root)
    v6.write_diagnostics_class(root)
    v6.patch_process_helper(root)
    v6.patch_guest_launcher(root)
    v6.patch_activity(root)

    patch_versions(root)
    prepare_box64_and_native_fallback(root)
    patch_box64_refresh(root)
    patch_three_stage_launcher(root)

    print("Winlator TR Compat v7 Box64 interpreter/native fallback patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
