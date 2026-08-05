#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

IMAGE_DIRECTORY_ENTRY_IMPORT = 1
IMAGE_DIRECTORY_ENTRY_SECURITY = 4
IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT = 13
IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_FILE_MACHINE_I386 = 0x014C
IMAGE_FILE_MACHINE_ARM64 = 0xAA64
IMAGE_SUBSYSTEM_NATIVE = 1


class PEError(RuntimeError):
    pass


def u16(data: bytes, off: int) -> int:
    if off < 0 or off + 2 > len(data):
        raise PEError(f"u16 out of range at {off:#x}")
    return struct.unpack_from("<H", data, off)[0]


def u32(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        raise PEError(f"u32 out of range at {off:#x}")
    return struct.unpack_from("<I", data, off)[0]


def u64(data: bytes, off: int) -> int:
    if off < 0 or off + 8 > len(data):
        raise PEError(f"u64 out of range at {off:#x}")
    return struct.unpack_from("<Q", data, off)[0]


def cstr(data: bytes, off: int, limit: int = 4096) -> str:
    if off < 0 or off >= len(data):
        raise PEError(f"string out of range at {off:#x}")
    end = data.find(b"\0", off, min(len(data), off + limit))
    if end < 0:
        raise PEError(f"unterminated string at {off:#x}")
    return data[off:end].decode("ascii", "replace")


def machine_name(machine: int) -> str:
    return {
        IMAGE_FILE_MACHINE_AMD64: "x86_64",
        IMAGE_FILE_MACHINE_I386: "i386",
        IMAGE_FILE_MACHINE_ARM64: "arm64",
    }.get(machine, f"unknown-{machine:#x}")


def parse_pe(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < 0x100 or data[:2] != b"MZ":
        raise PEError("not an MZ image")

    pe_off = u32(data, 0x3C)
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise PEError("missing PE signature")

    coff = pe_off + 4
    machine = u16(data, coff)
    section_count = u16(data, coff + 2)
    optional_size = u16(data, coff + 16)
    characteristics = u16(data, coff + 18)
    optional = coff + 20
    magic = u16(data, optional)
    if magic == 0x20B:
        is_64 = True
        entry_rva = u32(data, optional + 16)
        image_base = u64(data, optional + 24)
        subsystem = u16(data, optional + 68)
        dll_characteristics = u16(data, optional + 70)
        image_size = u32(data, optional + 56)
        dir_count = u32(data, optional + 108)
        dir_base = optional + 112
        pointer_size = 8
        ordinal_mask = 1 << 63
    elif magic == 0x10B:
        is_64 = False
        entry_rva = u32(data, optional + 16)
        image_base = u32(data, optional + 28)
        subsystem = u16(data, optional + 68)
        dll_characteristics = u16(data, optional + 70)
        image_size = u32(data, optional + 56)
        dir_count = u32(data, optional + 92)
        dir_base = optional + 96
        pointer_size = 4
        ordinal_mask = 1 << 31
    else:
        raise PEError(f"unsupported optional-header magic {magic:#x}")

    section_off = optional + optional_size
    sections: list[dict[str, int | str]] = []
    for index in range(section_count):
        off = section_off + index * 40
        if off + 40 > len(data):
            raise PEError("truncated section table")
        name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        virtual_size = u32(data, off + 8)
        virtual_address = u32(data, off + 12)
        raw_size = u32(data, off + 16)
        raw_offset = u32(data, off + 20)
        flags = u32(data, off + 36)
        sections.append({
            "name": name,
            "virtual_size": virtual_size,
            "virtual_address": virtual_address,
            "raw_size": raw_size,
            "raw_offset": raw_offset,
            "characteristics": flags,
        })

    def rva_to_offset(rva: int) -> int:
        if rva == 0:
            return 0
        for section in sections:
            va = int(section["virtual_address"])
            span = max(int(section["virtual_size"]), int(section["raw_size"]))
            if va <= rva < va + span:
                off = int(section["raw_offset"]) + (rva - va)
                if off >= len(data):
                    raise PEError(f"RVA {rva:#x} maps beyond file")
                return off
        if rva < section_off:
            return rva
        raise PEError(f"unmapped RVA {rva:#x}")

    directories: list[tuple[int, int]] = []
    for index in range(min(dir_count, 16)):
        off = dir_base + index * 8
        directories.append((u32(data, off), u32(data, off + 4)))
    while len(directories) < 16:
        directories.append((0, 0))

    imports: dict[str, list[str]] = {}
    import_rva, import_size = directories[IMAGE_DIRECTORY_ENTRY_IMPORT]
    if import_rva and import_size:
        descriptor = rva_to_offset(import_rva)
        maximum = min(len(data), descriptor + import_size)
        while descriptor + 20 <= maximum:
            original_thunk = u32(data, descriptor)
            name_rva = u32(data, descriptor + 12)
            first_thunk = u32(data, descriptor + 16)
            if not any(data[descriptor:descriptor + 20]):
                break
            module = cstr(data, rva_to_offset(name_rva)).lower()
            thunk_rva = original_thunk or first_thunk
            thunk = rva_to_offset(thunk_rva)
            functions: list[str] = []
            for index in range(65536):
                value = u64(data, thunk + index * pointer_size) if is_64 else u32(data, thunk + index * pointer_size)
                if value == 0:
                    break
                if value & ordinal_mask:
                    functions.append(f"ordinal:{value & 0xffff}")
                else:
                    hint_name = rva_to_offset(value)
                    functions.append(cstr(data, hint_name + 2))
            imports[module] = sorted(set(functions), key=str.lower)
            descriptor += 20

    delay_import_modules: list[str] = []
    delay_rva, delay_size = directories[IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT]
    if delay_rva and delay_size:
        descriptor = rva_to_offset(delay_rva)
        maximum = min(len(data), descriptor + delay_size)
        while descriptor + 32 <= maximum:
            attrs = u32(data, descriptor)
            name_value = u32(data, descriptor + 4)
            if not any(data[descriptor:descriptor + 32]):
                break
            name_rva = name_value if (attrs & 1) else name_value - image_base
            delay_import_modules.append(cstr(data, rva_to_offset(name_rva)).lower())
            descriptor += 32

    cert_offset, cert_size = directories[IMAGE_DIRECTORY_ENTRY_SECURITY]
    cert_present = bool(cert_offset and cert_size and cert_offset + cert_size <= len(data))

    imported_modules = sorted(imports, key=str.lower)
    all_import_names = {name.lower() for values in imports.values() for name in values}
    module_set = set(imported_modules)

    framework = {
        "kmdf": "wdfldr.sys" in module_set or any(name.startswith("wdf") for name in all_import_names),
        "filter_manager": "fltmgr.sys" in module_set or any(name.startswith("flt") for name in all_import_names),
        "networking": bool(module_set & {"netio.sys", "ndis.sys", "tcpip.sys", "fwpkclnt.sys"}),
        "storage": bool(module_set & {"storport.sys", "scsiport.sys", "classpnp.sys", "disk.sys"}),
        "hal": "hal.dll" in module_set,
    }

    return {
        "path": str(path),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "machine": machine,
        "machine_name": machine_name(machine),
        "is_64_bit": is_64,
        "subsystem": subsystem,
        "native_subsystem": subsystem == IMAGE_SUBSYSTEM_NATIVE,
        "entry_point_rva": entry_rva,
        "image_base": image_base,
        "image_size": image_size,
        "characteristics": characteristics,
        "dll_characteristics": dll_characteristics,
        "sections": sections,
        "imports": imports,
        "delay_import_modules": sorted(set(delay_import_modules)),
        "authenticode_certificate_table": {
            "present": cert_present,
            "file_offset": cert_offset,
            "size": cert_size,
        },
        "framework_indicators": framework,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Static structural audit for PE native driver images")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    reports: list[dict[str, Any]] = []
    failed = False
    for path in args.paths:
        try:
            reports.append(parse_pe(path))
        except Exception as error:
            failed = True
            reports.append({"path": str(path), "error": f"{type(error).__name__}: {error}"})

    payload = {
        "schema": "trcompat.pe-driver-audit.v1",
        "reports": reports,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
