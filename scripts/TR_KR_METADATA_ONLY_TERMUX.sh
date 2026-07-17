#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${1:-/storage/emulated/0/Download/TR_KR_LOCAL}"
OUT="/storage/emulated/0/Download/TR_KR_METADATA_ONLY"
ZIP="/storage/emulated/0/Download/TR_KR_METADATA_ONLY.zip"
TMP="$PREFIX/tmp/tr_kr_metadata.py"

command -v python >/dev/null 2>&1 || pkg install -y python
mkdir -p "$OUT"

cat > "$TMP" <<'PY'
from __future__ import annotations
import datetime as dt, hashlib, json, re, struct, sys, zipfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
if not root.is_dir():
    raise SystemExit(f"ERROR: 폴더가 없습니다: {root}")
out.mkdir(parents=True, exist_ok=True)

patterns = [
    r"^talesrunner\.exe$", r"^trgame\.exe$", r"^xldr_.*_x64\.exe$",
    r"^x3(?:_x64|_arm64)?\.xem$", r"^xcorona(?:_x64|_arm64)?\.xem$",
    r"^xmag(?:_x64|_arm64)?\.xem$", r"^xnina(?:_x64|_arm64)?\.xem$",
    r"^xhunter.*\.sys$",
]
rx = [re.compile(x, re.I) for x in patterns]

thai = {
    "x3_x64.xem": (6426912, "6a8e373d7c10060f8612bb0f9a0d13a1c3de73ebd9b73f89d50df30ce673fad7"),
    "xcorona_x64.xem": (6973552, "f082c98677ea4b6a2088fb74906ab798e1d9ad58c51f66d783bcdfaa599526b7"),
    "xnina_x64.xem": (2031616, "6dcf873c19259ee8da533bef1a604f728812ed5cc9de288bb37368ba1ed5dae0"),
    "xldr_TalesRunner_TH_loader_x64.exe": (12104544, "1c173d8e6490f81b35f0c199195cd0ef6ef88ecf5a0671d03e9dca92f0aa0ad9"),
}

machine_names = {0x14c:"x86", 0x8664:"x64", 0xaa64:"ARM64"}

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024), b''): h.update(c)
    return h.hexdigest()

def pe_meta(p: Path):
    r={"pe":False}
    try:
        with p.open('rb') as f:
            if f.read(2) != b'MZ': return r
            f.seek(0x3c); peoff=struct.unpack('<I',f.read(4))[0]
            f.seek(peoff)
            if f.read(4) != b'PE\0\0': return r
            machine, sections, timestamp = struct.unpack('<HHI', f.read(8))
            f.seek(peoff+20)
            opt_size=struct.unpack('<H',f.read(2))[0]
            f.seek(peoff+24)
            magic=struct.unpack('<H',f.read(2))[0]
            data_dir_off = peoff+24+(112 if magic==0x20b else 96)
            f.seek(data_dir_off+8*4)
            cert_off, cert_size = struct.unpack('<II',f.read(8))
        r.update({
            "pe":True,"machine":hex(machine),"architecture":machine_names.get(machine,"unknown"),
            "compile_timestamp_utc":dt.datetime.fromtimestamp(timestamp,dt.timezone.utc).isoformat(),
            "optional_header_size":opt_size,"certificate_table_offset":cert_off,
            "certificate_table_size":cert_size,"certificate_table_present":bool(cert_off and cert_size),
        })
    except Exception as e:
        r["pe_error"]=f"{type(e).__name__}: {e}"
    return r

files=[]
for p in root.rglob('*'):
    if p.is_file() and any(x.match(p.name) for x in rx): files.append(p)
files.sort(key=lambda p:str(p).lower())

rows=[]
for p in files:
    digest=sha256(p)
    row={
        "relative_path":str(p.relative_to(root)),"name":p.name,"size":p.stat().st_size,
        "sha256":digest,"mtime_utc":dt.datetime.fromtimestamp(p.stat().st_mtime,dt.timezone.utc).isoformat(),
    }
    row.update(pe_meta(p))
    ref=thai.get(p.name)
    if ref:
        row["thai_compare"]={"same_size":p.stat().st_size==ref[0],"same_sha256":digest==ref[1]}
    rows.append(row)

report={
    "generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
    "root":str(root),"auth_data_read":False,"file_count":len(rows),"files":rows,
}
(out/'TR_KR_METADATA_ONLY.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'TR_KR_METADATA_ONLY.txt').open('w',encoding='utf-8') as f:
    f.write(f"ROOT={root}\nFILE_COUNT={len(rows)}\nAUTH_DATA_READ=NO\n\n")
    for r in rows:
        f.write(f"PATH={r['relative_path']}\nSIZE={r['size']}\nSHA256={r['sha256']}\n")
        f.write(f"PE={r.get('pe')} ARCH={r.get('architecture')} MACHINE={r.get('machine')} COMPILE_UTC={r.get('compile_timestamp_utc')}\n")
        f.write(f"CERT_TABLE_PRESENT={r.get('certificate_table_present')} CERT_TABLE_SIZE={r.get('certificate_table_size')}\n")
        if 'thai_compare' in r:
            f.write(f"THAI_COMPARE SAME_SIZE={r['thai_compare']['same_size']} SAME_SHA256={r['thai_compare']['same_sha256']}\n")
        f.write('\n')

names={r['name'].lower() for r in rows}
expected=['talesrunner.exe','trgame.exe','x3.xem','x3_x64.xem','xcorona.xem','xcorona_x64.xem','xcorona_arm64.xem','xmag.xem','xmag_x64.xem','xnina.xem','xnina_x64.xem']
(out/'TR_KR_EXPECTED_NAME_CHECK.txt').write_text(
    'Inventory only; missing does not prove required.\n\nPRESENT:\n' +
    ''.join(f'  {x}\n' for x in expected if x in names) +
    'MISSING:\n' + ''.join(f'  {x}\n' for x in expected if x not in names), encoding='utf-8')
print(f"완료: {len(rows)}개 파일")
PY

python "$TMP" "$ROOT" "$OUT"
rm -f "$ZIP"
python - "$OUT" "$ZIP" <<'PY'
import sys, zipfile
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
with zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(src.iterdir()):
        if p.is_file(): z.write(p,p.name)
print(dst)
PY
ls -lh "$ZIP"
