#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path


def readelf_needed(path: Path) -> list[str]:
    proc = subprocess.run(["readelf", "-d", str(path)], text=True, capture_output=True)
    if proc.returncode != 0:
        return []
    return re.findall(r"Shared library: \[(.*?)\]", proc.stdout)


def readelf_symbols(path: Path) -> str:
    return subprocess.run(["readelf", "-Ws", str(path)], text=True, capture_output=True, check=True).stdout


def file_strings(path: Path) -> str:
    return subprocess.run(["strings", str(path)], text=True, capture_output=True, check=True).stdout


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wine_tree", type=Path)
    parser.add_argument("rootfs", type=Path)
    parser.add_argument("report_dir", type=Path)
    args = parser.parse_args()
    wine = args.wine_tree.resolve()
    rootfs = args.rootfs.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for base in (wine / "bin", wine / "lib/wine/x86_64-unix", wine / "lib/wine/i386-unix"):
        if base.exists():
            candidates.extend(path for path in base.rglob("*") if is_elf(path))
    candidates = sorted(set(candidates))
    if not candidates:
        raise RuntimeError("no Wine ELF runtime files found")

    native_names = set()
    for base in (rootfs / "lib", rootfs / "usr/lib", rootfs / "usr/local/lib"):
        if base.exists():
            native_names.update(path.name for path in base.rglob("*") if path.is_file() or path.is_symlink())
    wine_names = {path.name for path in candidates}
    provided = native_names | wine_names

    manifest: dict[str, list[str]] = {}
    missing: dict[str, list[str]] = defaultdict(list)
    for path in candidates:
        relative = str(path.relative_to(wine))
        deps = readelf_needed(path)
        manifest[relative] = deps
        for dep in deps:
            if dep not in provided:
                missing[dep].append(relative)

    prohibited = {
        "libudev.so.1", "libusb-1.0.so.0", "libavcodec.so.58", "libavformat.so.58",
        "libavutil.so.56", "libgstgl-1.0.so.0", "libpiper.so",
    }
    found_prohibited = {
        dep: [path for path, deps in manifest.items() if dep in deps]
        for dep in sorted(prohibited)
        if any(dep in deps for deps in manifest.values())
    }

    required = [
        wine / "bin/wine", wine / "bin/wineserver",
        wine / "lib/wine/x86_64-unix/ntdll.so",
        wine / "lib/wine/x86_64-unix/winebus.so",
        wine / "lib/wine/i386-unix/winebus.so",
        wine / "lib/wine/x86_64-unix/nsiproxy.so",
        wine / "lib/wine/x86_64-unix/winex11.so",
    ]
    absent_required = [str(path.relative_to(wine)) for path in required if not path.is_file()]

    legacy_hits = {}
    for path in (wine / "bin/wineserver", wine / "lib/wine/x86_64-unix/ntdll.so",
                 wine / "lib/wine/i386-unix/ntdll.so"):
        if path.is_file() and "/tmp/.wine-%u" in file_strings(path):
            legacy_hits[str(path.relative_to(wine))] = True

    winex11_symbols = ""
    for path in (wine / "lib/wine/x86_64-unix/winex11.so", wine / "lib/wine/i386-unix/winex11.so"):
        if path.is_file():
            winex11_symbols += readelf_symbols(path)
    xshape_hits = sorted(set(re.findall(r"\bXShape[A-Za-z0-9_]*", winex11_symbols)))

    nsi_hits = {}
    for path in (wine / "lib/wine/x86_64-unix/nsiproxy.so", wine / "lib/wine/i386-unix/nsiproxy.so"):
        if path.is_file():
            text = file_strings(path)
            hits = [needle for needle in ("bind failed, errno", "NETLINK_ROUTE") if needle in text]
            if hits:
                nsi_hits[str(path.relative_to(wine))] = hits

    wine_dynamic = readelf_needed(wine / "bin/wine")
    wine_symbols = readelf_symbols(wine / "bin/wine")
    abi_errors = []
    if "libc.so.6" not in wine_dynamic:
        abi_errors.append("bin/wine does not require glibc libc.so.6")
    if "__libc_init" in wine_symbols:
        abi_errors.append("bin/wine imports Android Bionic __libc_init")

    machine_id = rootfs / "etc/machine-id"
    machine_text = machine_id.read_text(encoding="ascii", errors="ignore").strip() if machine_id.is_file() else ""
    machine_seed_ok = bool(re.fullmatch(r"0{32}", machine_text))

    report = {
        "elf_count": len(candidates),
        "manifest": manifest,
        "missing_direct_dependencies": dict(sorted(missing.items())),
        "prohibited_optional_dependencies": found_prohibited,
        "absent_required_files": absent_required,
        "legacy_wineserver_paths": legacy_hits,
        "xshape_symbols": xshape_hits,
        "nsiproxy_forbidden_strings": nsi_hits,
        "abi_errors": abi_errors,
        "machine_id_seed_is_32_zero_hex": machine_seed_ok,
        "native_library_count": len(native_names),
    }
    (report_dir / "v18i-runtime-audit.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (report_dir / "v18i-runtime-dependencies.txt").write_text(
        "\n".join(f"{path}: {' '.join(deps)}" for path, deps in sorted(manifest.items())) + "\n",
        encoding="utf-8")
    (report_dir / "v18i-rootfs-native-libraries.txt").write_text("\n".join(sorted(native_names)) + "\n", encoding="utf-8")

    failures = []
    if missing:
        failures.append(f"unresolved direct dependencies: {dict(missing)}")
    if found_prohibited:
        failures.append(f"unsupported optional dependencies remain: {found_prohibited}")
    if absent_required:
        failures.append(f"required runtime files missing: {absent_required}")
    if legacy_hits:
        failures.append(f"legacy /tmp wineserver paths remain: {legacy_hits}")
    if xshape_hits:
        failures.append(f"XShape imports remain: {xshape_hits}")
    if nsi_hits:
        failures.append(f"forbidden Android netlink notification code remains: {nsi_hits}")
    failures.extend(abi_errors)
    if not machine_seed_ok:
        failures.append("rootfs /etc/machine-id seed is missing or invalid")

    if failures:
        print(json.dumps(report, indent=2, sort_keys=True))
        raise RuntimeError("v18I runtime audit failed:\n- " + "\n- ".join(failures))

    print(f"v18I runtime audit passed for {len(candidates)} ELF files and {len(native_names)} rootfs libraries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
