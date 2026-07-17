#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${1:-/storage/emulated/0/Download/TR_KR_LOCAL}"
OUT="/storage/emulated/0/Download/TR_KR_METADATA_ONLY"
TMP="$PREFIX/tmp/TR_KR_METADATA_COMPARE.py"

command -v python >/dev/null 2>&1 || pkg install -y python

python - <<'PY' >/dev/null 2>&1 || python -m pip install --user pefile
import pefile
PY

cat > "$TMP" <<'PYCODE'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

try:
    import pefile
except ImportError:
    print("ERROR: pefile이 없습니다. 먼저 실행: pip install --user pefile", file=sys.stderr)
    raise SystemExit(2)

TARGET_PATTERNS = (
    re.compile(r"^talesrunner\.exe$", re.I),
    re.compile(r"^trgame\.exe$", re.I),
    re.compile(r"^xldr_.*(?:KR|TalesRunner).*_x64\.exe$", re.I),
    re.compile(r"^x3(?:_x64|_arm64)?\.xem$", re.I),
    re.compile(r"^xcorona(?:_x64|_arm64)?\.xem$", re.I),
    re.compile(r"^xmag(?:_x64|_arm64)?\.xem$", re.I),
    re.compile(r"^xnina(?:_x64|_arm64)?\.xem$", re.I),
    re.compile(r"^xhunter.*\.sys$", re.I),
)

THAI_REFERENCE = {
    "x3.xem": {"size": 3730408, "sha256": "b421f4ed073f686128d283c35cd40744f2aa625020fc8706e7236b63498b23c8", "file_version": "2024.4.24.220", "product_version": "3.5.0.63"},
    "x3_x64.xem": {"size": 6426912, "sha256": "6a8e373d7c10060f8612bb0f9a0d13a1c3de73ebd9b73f89d50df30ce673fad7", "file_version": "2024.4.24.220", "product_version": "3.5.0.63"},
    "xcorona.xem": {"size": 6529880, "sha256": "798b1568e6ce197071b771fe897870c04bddf75279382ec00f7cc9128f330de8", "file_version": "2024.4.24.220", "product_version": "5.0.0.0"},
    "xcorona_x64.xem": {"size": 6973552, "sha256": "f082c98677ea4b6a2088fb74906ab798e1d9ad58c51f66d783bcdfaa599526b7", "file_version": "2024.4.24.220", "product_version": "5.0.0.0"},
    "xcorona_arm64.xem": {"size": 12389160, "sha256": "e49c7c79a6612acd2f47929a89cb66c4ae847705f042d1bb6c0205188e0d7062", "file_version": "2024.4.24.220", "product_version": "5.0.0.0"},
    "xnina.xem": {"size": 1777664, "sha256": "59e781ef16cfdb01f79d34291045c80358eda2de9e2da8593be9a1802cbdb56d"},
    "xnina_x64.xem": {"size": 2031616, "sha256": "6dcf873c19259ee8da533bef1a604f728812ed5cc9de288bb37368ba1ed5dae0"},
    "xldr_TalesRunner_TH_loader_x64.exe": {"size": 12104544, "sha256": "1c173d8e6490f81b35f0c199195cd0ef6ef88ecf5a0671d03e9dca92f0aa0ad9", "file_version": "2025.3.27.39", "product_version": "5.0.0.1"},
}

MACHINE_NAMES = {0x014C: "x86", 0x8664: "x64", 0xAA64: "ARM64"}

def selected(path: Path) -> bool:
    return any(p.match(path.name) for p in TARGET_PATTERNS)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def decode(value) -> str:
    if isinstance(value, bytes):
        for enc in ("utf-8", "utf-16le", "cp949", "cp1252"):
            try:
                return value.decode(enc).rstrip("\x00")
            except Exception:
                pass
        return value.hex()
    return str(value)

def version_info(pe: pefile.PE) -> dict[str, str]:
    out: dict[str, str] = {}
    for group in getattr(pe, "FileInfo", []) or []:
        for item in group:
            if getattr(item, "Key", b"") == b"StringFileInfo":
                for table in item.StringTable:
                    for key, value in table.entries.items():
                        out[decode(key)] = decode(value)
    return out

def certificate_table(path: Path, pe: pefile.PE) -> dict:
    result = {"present": False, "offset": 0, "size": 0, "sha256": None, "note": "Authenticode certificate table metadata only; trust chain is not verified."}
    try:
        directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]]
        offset, size = int(directory.VirtualAddress), int(directory.Size)
        result["offset"] = offset
        result["size"] = size
        if offset > 0 and size >= 8 and offset + size <= path.stat().st_size:
            with path.open("rb") as f:
                f.seek(offset)
                blob = f.read(size)
            result["present"] = True
            result["sha256"] = hashlib.sha256(blob).hexdigest()
            if len(blob) >= 8:
                length, revision, cert_type = struct.unpack_from("<IHH", blob, 0)
                result["win_certificate_length"] = length
                result["revision"] = hex(revision)
                result["certificate_type"] = hex(cert_type)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result

def inspect(path: Path, root: Path) -> dict:
    row = {
        "relative_path": str(path.relative_to(root)),
        "name": path.name,
        "size": path.stat().st_size,
        "mtime_utc": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(),
        "sha256": sha256(path),
    }
    try:
        pe = pefile.PE(str(path), fast_load=False)
        row["pe"] = True
        machine = int(pe.FILE_HEADER.Machine)
        row["machine"] = hex(machine)
        row["architecture"] = MACHINE_NAMES.get(machine, "unknown")
        row["compile_timestamp_utc"] = dt.datetime.fromtimestamp(int(pe.FILE_HEADER.TimeDateStamp), dt.timezone.utc).isoformat()
        row["version_info"] = version_info(pe)
        row["imports"] = sorted({decode(entry.dll) for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])})
        row["certificate_table"] = certificate_table(path, pe)
    except Exception as exc:
        row["pe"] = False
        row["pe_error"] = f"{type(exc).__name__}: {exc}"
    return row

def thai_comparison(row: dict) -> dict | None:
    ref = THAI_REFERENCE.get(row["name"])
    if ref is None:
        return None
    vi = row.get("version_info", {})
    file_ver = vi.get("FileVersion")
    product_ver = vi.get("ProductVersion")
    return {
        "thai_reference_exists": True,
        "same_size": row["size"] == ref["size"],
        "same_sha256": row["sha256"] == ref["sha256"],
        "korean_file_version": file_ver,
        "thai_file_version": ref.get("file_version"),
        "same_file_version": file_ver == ref.get("file_version") if ref.get("file_version") is not None else None,
        "korean_product_version": product_ver,
        "thai_product_version": ref.get("product_version"),
        "same_product_version": product_ver == ref.get("product_version") if ref.get("product_version") is not None else None,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Collect metadata only from Korean TalesRunner executable/XIGNCODE files.")
    parser.add_argument("root", nargs="?", default="/storage/emulated/0/Download/TR_KR_LOCAL", help="Korean TalesRunner root folder")
    parser.add_argument("--out", default="/storage/emulated/0/Download/TR_KR_METADATA_ONLY", help="Output directory")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    out = Path(args.out).expanduser()
    if not root.is_dir():
        print(f"ERROR: 폴더가 없습니다: {root}", file=sys.stderr)
        return 1

    out.mkdir(parents=True, exist_ok=True)
    files = [p for p in root.rglob("*") if p.is_file() and selected(p)]
    files.sort(key=lambda p: str(p).lower())

    rows = []
    for path in files:
        row = inspect(path, root)
        comp = thai_comparison(row)
        if comp is not None:
            row["thai_comparison"] = comp
        rows.append(row)

    inventory = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": str(root),
        "privacy": "Only executable/XIGNCODE filenames, hashes, PE metadata and certificate-table metadata were collected. Login batches, cookies, tokens, logs and account data were not read.",
        "file_count": len(rows),
        "files": rows,
    }

    json_path = out / "TR_KR_METADATA_ONLY.json"
    txt_path = out / "TR_KR_METADATA_ONLY.txt"
    json_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")

    with txt_path.open("w", encoding="utf-8") as f:
        f.write(f"GENERATED_UTC={inventory['generated_utc']}\n")
        f.write(f"ROOT={root}\n")
        f.write(f"FILE_COUNT={len(rows)}\n")
        f.write("AUTH_DATA_READ=NO\n\n")
        for row in rows:
            f.write(f"PATH={row['relative_path']}\n")
            f.write(f"SIZE={row['size']}\n")
            f.write(f"SHA256={row['sha256']}\n")
            f.write(f"PE={row.get('pe')} ARCH={row.get('architecture')} MACHINE={row.get('machine')} COMPILE_UTC={row.get('compile_timestamp_utc')}\n")
            for key, value in sorted(row.get("version_info", {}).items()):
                f.write(f"VERSION_{key}={value}\n")
            cert = row.get("certificate_table", {})
            f.write(f"CERT_TABLE_PRESENT={cert.get('present')} CERT_TABLE_SIZE={cert.get('size')} CERT_TABLE_SHA256={cert.get('sha256')}\n")
            comp = row.get("thai_comparison")
            if comp:
                f.write(f"THAI_COMPARE SAME_SIZE={comp['same_size']} SAME_SHA256={comp['same_sha256']} SAME_FILE_VERSION={comp['same_file_version']} SAME_PRODUCT_VERSION={comp['same_product_version']}\n")
            f.write("\n")

    expected = [
        "talesrunner.exe", "trgame.exe", "x3.xem", "x3_x64.xem",
        "xcorona.xem", "xcorona_x64.xem", "xcorona_arm64.xem",
        "xmag.xem", "xmag_x64.xem", "xnina.xem", "xnina_x64.xem",
    ]
    names = {r["name"].lower() for r in rows}
    missing = [name for name in expected if name.lower() not in names]
    (out / "TR_KR_EXPECTED_NAME_CHECK.txt").write_text(
        "\n".join([
            "This is an inventory check, not a claim that every listed file is required.",
            "PRESENT:",
            *[f"  {name}" for name in expected if name.lower() in names],
            "MISSING:",
            *[f"  {name}" for name in missing],
            "",
        ]),
        encoding="utf-8",
    )

    print(f"완료: {txt_path}")
    print(f"완료: {json_path}")
    print(f"파일 수: {len(rows)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
PYCODE

python "$TMP" "$ROOT" --out "$OUT"

cd "/storage/emulated/0/Download"
rm -f TR_KR_METADATA_ONLY.zip
python - <<'PY'
from pathlib import Path
import zipfile
src = Path("/storage/emulated/0/Download/TR_KR_METADATA_ONLY")
dst = Path("/storage/emulated/0/Download/TR_KR_METADATA_ONLY.zip")
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(src.iterdir()):
        if p.is_file():
            z.write(p, p.name)
print(dst)
PY

ls -lh "/storage/emulated/0/Download/TR_KR_METADATA_ONLY.zip"
