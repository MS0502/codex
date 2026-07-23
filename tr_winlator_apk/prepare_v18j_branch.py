from pathlib import Path

workflow = Path(".github/workflows/tr-winlator-v18j-native-wrapper-closure.yml")
text = workflow.read_text(encoding="utf-8")
replacements = {
    "TR Winlator v18i Proton 11 runtime closure APK":
        "TR Winlator v18j Proton 11 native wrapper closure APK",
    "tr-wine-compat-proton11-runtime-closure-v18i":
        "tr-wine-compat-proton11-native-wrapper-closure-v18j",
    "tr-winlator-v18i-runtime-closure":
        "tr-winlator-v18j-native-wrapper-closure",
    "proton11-wine-source-v18i":
        "proton11-wine-source-v18j",
    "tr_v18i_proton11_runtime_closure":
        "tr_v18j_proton11_native_wrapper_closure",
    "apply_v18i_patch.py":
        "apply_v18j_patch.py",
    "v18i-apply.log":
        "v18j-apply.log",
    "11.1-trcompat18i-proton11-runtime-closure":
        "11.1-trcompat18j-proton11-native-wrapper-closure",
    "v18i-proton11-runtime-closure-1":
        "v18j-proton11-native-wrapper-closure-1",
    "v18i-runtime-closure-report.txt":
        "v18j-native-wrapper-closure-report.txt",
    "out-v18i":
        "out-v18j",
    "Winlator_11.1_TR_Compat_v18I_PROTON11_RUNTIME_CLOSURE.apk":
        "Winlator_11.1_TR_Compat_v18J_PROTON11_NATIVE_WRAPPER_CLOSURE.apk",
    "WINLATOR_11_1_TR_COMPAT_APK_V18I_PROTON11_RUNTIME_CLOSURE":
        "WINLATOR_11_1_TR_COMPAT_APK_V18J_PROTON11_NATIVE_WRAPPER_CLOSURE",
    "WINLATOR_11_1_TR_COMPAT_V18I_BUILD_LOG":
        "WINLATOR_11_1_TR_COMPAT_V18J_BUILD_LOG",
    "proton-v18i-source-patch.txt":
        "proton-v18j-source-patch.txt",
    "proton-v18i-source.patch":
        "proton-v18j-source.patch",
    "apk-build-v18i.log":
        "apk-build-v18j.log",
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"workflow anchor missing: {old}")
    text = text.replace(old, new)

old_download = "apt-get download libudev1:arm64 libusb-1.0-0:arm64"
new_download = (
    "apt-get download libudev1:arm64 libusb-1.0-0:arm64 "
    "libxinerama1:arm64 libdbus-1-3:arm64"
)
if text.count(old_download) != 1:
    raise SystemExit("workflow package download anchor mismatch")
text = text.replace(old_download, new_download, 1)

old_find = """          find native-runtime -name 'libudev.so.1*' -o -name 'libusb-1.0.so.0*' \\
            | sort | tee native-runtime-files.txt
          test -n "$(find native-runtime -name libudev.so.1 -print -quit)"
          test -n "$(find native-runtime -name libusb-1.0.so.0 -print -quit)"
          while IFS= read -r library; do file "$library"; done \\
            < <(find native-runtime -type f \\( -name 'libudev.so.1*' -o -name 'libusb-1.0.so.0*' \\)) \\
            | tee native-runtime-file-types.txt
"""
new_find = """          find native-runtime \\
            \\( -name 'libudev.so.1*' -o -name 'libusb-1.0.so.0*' \\
               -o -name 'libXinerama.so.1*' -o -name 'libdbus-1.so.3*' \\) \\
            | sort | tee native-runtime-files.txt
          test -n "$(find native-runtime -name libudev.so.1 -print -quit)"
          test -n "$(find native-runtime -name libusb-1.0.so.0 -print -quit)"
          test -n "$(find native-runtime -name libXinerama.so.1 -print -quit)"
          test -n "$(find native-runtime -name libdbus-1.so.3 -print -quit)"
          while IFS= read -r library; do file "$library"; done \\
            < <(find native-runtime -type f \\
              \\( -name 'libudev.so.1*' -o -name 'libusb-1.0.so.0*' \\
                 -o -name 'libXinerama.so.1*' -o -name 'libdbus-1.so.3*' \\)) \\
            | tee native-runtime-file-types.txt
"""
if text.count(old_find) != 1:
    raise SystemExit("workflow native runtime validation anchor mismatch")
text = text.replace(old_find, new_find, 1)

old_rootfs = """          UDEV="$(find rootfs-check -name libudev.so.1 -print -quit)"
          USB="$(find rootfs-check -name libusb-1.0.so.0 -print -quit)"
          test -n "$UDEV"
          test -n "$USB"
          file -L "$UDEV" "$USB" | tee packaged-native-runtime-file.txt
"""
new_rootfs = """          UDEV="$(find rootfs-check -name libudev.so.1 -print -quit)"
          UDEV0="$(find rootfs-check -name libudev.so.0 -print -quit)"
          USB="$(find rootfs-check -name libusb-1.0.so.0 -print -quit)"
          XINERAMA="$(find rootfs-check -name libXinerama.so.1 -print -quit)"
          XINERAMA_ALIAS="$(find rootfs-check -name libXinerama.so -print -quit)"
          DBUS="$(find rootfs-check -name libdbus-1.so.3 -print -quit)"
          test -n "$UDEV"
          test -n "$UDEV0"
          test -n "$USB"
          test -n "$XINERAMA"
          test -n "$XINERAMA_ALIAS"
          test -n "$DBUS"
          file -L "$UDEV" "$UDEV0" "$USB" "$XINERAMA" "$XINERAMA_ALIAS" "$DBUS" \\
            | tee packaged-native-runtime-file.txt
"""
if text.count(old_rootfs) != 1:
    raise SystemExit("workflow rootfs validation anchor mismatch")
text = text.replace(old_rootfs, new_rootfs, 1)
workflow.write_text(text, encoding="utf-8")

patcher = Path("tr_winlator_apk/apply_v18j_patch.py")
text = patcher.read_text(encoding="utf-8")
replacements = {
    'REVISION = "v18i-proton11-runtime-closure-1"':
        'REVISION = "v18j-proton11-native-wrapper-closure-1"',
    'prefix="tr-v18i-rootfs-"':
        'prefix="tr-v18j-rootfs-"',
    'required = ("libudev.so.1", "libusb-1.0.so.0")':
        'required = ("libudev.so.1", "libudev.so.0", "libusb-1.0.so.0", '
        '"libXinerama.so.1", "libXinerama.so", "libdbus-1.so.3")',
    '"v18i-runtime-closure-report.txt"':
        '"v18j-native-wrapper-closure-report.txt"',
    '"rootfs-v18i.tar"':
        '"rootfs-v18j.tar"',
    'versionName "11.1-trcompat18i-proton11-runtime-closure"':
        'versionName "11.1-trcompat18j-proton11-native-wrapper-closure"',
    '"TR_DIAG_v18I_PROTON11_RUNTIME_CLOSURE.zip"':
        '"TR_DIAG_v18J_PROTON11_NATIVE_WRAPPER_CLOSURE.zip"',
    '"DIAGNOSTICS_RESET version=18i-proton11-runtime-closure"':
        '"DIAGNOSTICS_RESET version=18j-proton11-native-wrapper-closure"',
    '"TalesRunner KR XIGNCODE fingerprint v18i Proton 11 runtime closure"':
        '"TalesRunner KR XIGNCODE fingerprint v18j Proton 11 native wrapper closure"',
    'f"v18i diagnostics anchor not found: {old}"':
        'f"v18j diagnostics anchor not found: {old}"',
    '".trcompat-v18i.tmp"':
        '".trcompat-v18j.tmp"',
    '"usage: apply_v18i_patch.py WINLATOR_APP_DIR PROTON_WINE_TREE "':
        '"usage: apply_v18j_patch.py WINLATOR_APP_DIR PROTON_WINE_TREE "',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"patcher anchor missing: {old}")
    text = text.replace(old, new)

anchor = "        shutil.copytree(native_runtime, tree, dirs_exist_ok=True, symlinks=True)\n\n"
alias_block = """        shutil.copytree(native_runtime, tree, dirs_exist_ok=True, symlinks=True)

        # Device Box64 traces show that the Android wrappers translate the
        # requested x86_64 SONAMEs to these native host names.
        native_aliases = {
            "libudev.so.0": "libudev.so.1",
            "libXinerama.so": "libXinerama.so.1",
        }
        for alias, target in native_aliases.items():
            targets = sorted(
                path for path in tree.rglob(target)
                if path.is_file() or path.is_symlink()
            )
            if not targets:
                raise RuntimeError(f"native wrapper target missing: {target}")
            alias_path = targets[0].parent / alias
            if alias_path.exists() or alias_path.is_symlink():
                alias_path.unlink()
            alias_path.symlink_to(targets[0].name)

"""
if text.count(anchor) != 1:
    raise SystemExit("patcher copytree anchor mismatch")
text = text.replace(anchor, alias_block, 1)
patcher.write_text(text, encoding="utf-8")

plan = Path("tr_winlator_apk/v18j_plan.md")
text = plan.read_text(encoding="utf-8")
text = text.replace("v18I", "v18J").replace("v18i", "v18j")
text += """

## v18J device-log-driven native wrapper closure

The failed v18I Z Fold6 trace proves that copying only the requested SONAME
does not satisfy Box64's Android native wrappers:

- `libudev.so.1` is translated to native `libudev.so.0`;
- `libXinerama.so.1` is translated to native `libXinerama.so`;
- `libdbus-1.so.3` is requested by mountmgr and absent.

v18J packages the pinned ARM64 libraries, creates only the exact native aliases
observed in the trace, and validates every alias in the final rootfs. It does
not alter TalesRunner, XIGNCODE, or security-module behavior.
"""
plan.write_text(text, encoding="utf-8")
