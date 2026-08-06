#!/usr/bin/env bash
set -euo pipefail

REPO="MS0502/codex"
V29_RUN="31006499944"
V29_ARTIFACT="WINLATOR_TR_COMPAT_V29_DRIVER_LOAD_KO_APK"
V29_APK_SHA="00dce0cd3be538317c65672b6d58035b102ea8fdde2c828c52a5d1e2726048d9"
SIGNER_SHA="3819847878a333cc204bd93ab89a28a9867c066da5def40401d840fda9f9f017"
ROOTFS_SHA="fd084ca23321b9ae357716f570a8d79143754ae1d182aa5082f2ecf26a87ca9b"
V29_NT_SHA="e174c45a200457f6453c8465d6d70a0a9ef2dca35a6362b85f8f4d0747617bb5"
V29_LOCALE_SHA="11add0c675b516bc1d27e8b9bde9cf05123ca9e5a86a757eb77b6e7edbee7d75"
AAPT="$ANDROID_HOME/build-tools/34.0.0/aapt"
APKSIGNER="$ANDROID_HOME/build-tools/34.0.0/apksigner"

python3 -m py_compile tr_winlator_apk/apply_v30_boundary_font_patch.py
chmod +x ci/build_v29_driver_load_ko.sh
ci/build_v29_driver_load_ko.sh

# The Wine PE output is not byte-reproducible across rebuilds. Restore the
# exact validated v29 APK assets rather than trusting a fresh compiler output.
rm -rf exact-v29
mkdir -p exact-v29
gh run download "$V29_RUN" --repo "$REPO" --name "$V29_ARTIFACT" --dir exact-v29
EXACT_V29_APK="$(find exact-v29 -type f -name '*.apk' -print -quit)"
test -n "$EXACT_V29_APK"
test -s "$EXACT_V29_APK"
test "$(sha256sum "$EXACT_V29_APK" | cut -d' ' -f1)" = "$V29_APK_SHA"
"$APKSIGNER" verify --verbose --print-certs "$EXACT_V29_APK" | tee exact-v29-signature.txt
grep 'Verified using v2 scheme (APK Signature Scheme v2): true' exact-v29-signature.txt
grep "Signer #1 certificate SHA-256 digest: $SIGNER_SHA" exact-v29-signature.txt

unzip -p "$EXACT_V29_APK" assets/rootfs.tzst > exact-v29-rootfs.tzst
unzip -p "$EXACT_V29_APK" assets/trcompat_wine_v29/ntoskrnl.exe > exact-v29-ntoskrnl.exe
unzip -p "$EXACT_V29_APK" assets/trcompat_locale_v29/ko_KR.utf8.tzst > exact-v29-ko-locale.tzst
test "$(sha256sum exact-v29-rootfs.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
test "$(sha256sum exact-v29-ntoskrnl.exe | cut -d' ' -f1)" = "$V29_NT_SHA"
test "$(sha256sum exact-v29-ko-locale.tzst | cut -d' ' -f1)" = "$V29_LOCALE_SHA"
cmp -s exact-v29-rootfs.tzst winlator-app/app/src/main/assets/rootfs.tzst
cmp -s exact-v29-ko-locale.tzst winlator-app/app/src/main/assets/trcompat_locale_v29/ko_KR.utf8.tzst

cp exact-v29-ntoskrnl.exe winlator-app/app/src/main/assets/trcompat_wine_v29/ntoskrnl.exe
chmod 0644 winlator-app/app/src/main/assets/trcompat_wine_v29/ntoskrnl.exe

# Canonicalize the reconstructed v29 Java contract to the exact validated
# tracer hash. This is the source state from which v30 is audited.
python3 - <<'PY'
from pathlib import Path
import re
expected='e174c45a200457f6453c8465d6d70a0a9ef2dca35a6362b85f8f4d0747617bb5'
patcher=Path('winlator-app/app/src/main/java/com/winlator/core/TrCompatNtKernelPatcher.java')
text=patcher.read_text(encoding='utf-8')
pattern=r'(private static final String EXPECTED_SHA256 = ")[0-9a-f]{64}(";)'
text,count=re.subn(pattern,rf'\g<1>{expected}\g<2>',text,count=1)
if count != 1: raise SystemExit(f'EXPECTED_SHA256 replacement count={count}')
patcher.write_text(text,encoding='utf-8')
report=Path('winlator-app/v29-driver-load-ko-report.txt')
rtext=report.read_text(encoding='utf-8')
rtext,count=re.subn(r'required_active_ntoskrnl_sha256=[0-9a-f]{64}',
                    'required_active_ntoskrnl_sha256='+expected,rtext,count=1)
if count != 1: raise SystemExit(f'v29 report hash replacement count={count}')
report.write_text(rtext,encoding='utf-8')
PY

test "$(sha256sum winlator-app/app/src/main/assets/rootfs.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
test "$(sha256sum winlator-app/app/src/main/assets/trcompat_wine_v29/ntoskrnl.exe | cut -d' ' -f1)" = "$V29_NT_SHA"
test "$(sha256sum winlator-app/app/src/main/assets/trcompat_locale_v29/ko_KR.utf8.tzst | cut -d' ' -f1)" = "$V29_LOCALE_SHA"
grep -q "$V29_NT_SHA" winlator-app/app/src/main/java/com/winlator/core/TrCompatNtKernelPatcher.java
grep -q "required_active_ntoskrnl_sha256=$V29_NT_SHA" winlator-app/v29-driver-load-ko-report.txt

# Record the canonical, exact-asset v29 source inventory immediately before v30.
python3 - <<'PY'
from pathlib import Path
import hashlib,json,stat
root=Path('winlator-app'); out={}
for p in sorted(root.rglob('*')):
    if not p.is_file() or p.is_symlink(): continue
    rel=p.relative_to(root).as_posix()
    out[rel]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
              'mode':stat.S_IMODE(p.stat().st_mode),'size':p.stat().st_size}
Path('v29-source-inventory-for-v30.json').write_text(json.dumps(out,sort_keys=True),encoding='utf-8')
PY

python3 tr_winlator_apk/apply_v30_boundary_font_patch.py winlator-app 2>&1 | tee v30-apply.log

# v30 must not alter the embedded rootfs, validated v29 driver trace binary,
# or validated locale asset.
test "$(sha256sum winlator-app/app/src/main/assets/rootfs.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
test "$(sha256sum winlator-app/app/src/main/assets/trcompat_wine_v29/ntoskrnl.exe | cut -d' ' -f1)" = "$V29_NT_SHA"
test "$(sha256sum winlator-app/app/src/main/assets/trcompat_locale_v29/ko_KR.utf8.tzst | cut -d' ' -f1)" = "$V29_LOCALE_SHA"

python3 - <<'PY'
from pathlib import Path
import hashlib,json,stat
root=Path('winlator-app')
before=json.loads(Path('v29-source-inventory-for-v30.json').read_text(encoding='utf-8'))
after={}
for p in sorted(root.rglob('*')):
    if not p.is_file() or p.is_symlink(): continue
    rel=p.relative_to(root).as_posix()
    after[rel]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                'mode':stat.S_IMODE(p.stat().st_mode),'size':p.stat().st_size}
added=set(after)-set(before); removed=set(before)-set(after)
changed={p for p in set(before)&set(after) if before[p]!=after[p]}
expected_added={'v30-x3-boundary-font-report.txt'}
expected_changed={
 'app/build.gradle',
 'app/src/main/java/com/winlator/XServerDisplayActivity.java',
 'app/src/main/java/com/winlator/core/TrCompatDiagnostics.java',
 'app/src/main/java/com/winlator/core/TrCompatKoreanSupport.java',
}
if added!=expected_added: raise SystemExit(f'unexpected v30 added: {sorted(added)}')
if removed: raise SystemExit(f'unexpected v30 removed: {sorted(removed)}')
if changed!=expected_changed: raise SystemExit(f'unexpected v30 changed: {sorted(changed)}')
print('v30 exact source delta proved')
PY

for assertion in \
  'rootfs_reinstall_forced=false' \
  'container_home_preserved=true' \
  'windows_font_registry_backup=true' \
  'windows_font_registry_rollback_on_failure=true' \
  'game_or_protection_files_changed=false' \
  'driver_or_ioctl_status_changed=false'; do
  grep -q "$assertion" winlator-app/v30-x3-boundary-font-report.txt
done

grep -q 'public static final byte LATEST_VERSION = 19;' winlator-app/app/src/main/java/com/winlator/xenvironment/RootFSInstaller.java
grep -q 'public static final byte UPDATE_WINEPREFIX_VERSION = 16;' winlator-app/app/src/main/java/com/winlator/xenvironment/RootFSInstaller.java
grep -q 'KOREAN_WINDOWS_FONT_REGISTRY' winlator-app/app/src/main/java/com/winlator/core/TrCompatKoreanSupport.java
grep -q 'TR_DIAG_v30_X3_BOUNDARY_FONT.zip' winlator-app/app/src/main/java/com/winlator/core/TrCompatDiagnostics.java
grep -q '+loaddll,+ver' winlator-app/app/src/main/java/com/winlator/XServerDisplayActivity.java

(
  cd winlator-app
  chmod +x gradlew
  set -o pipefail
  ./gradlew --no-daemon --stacktrace assembleDebug 2>&1 | tee ../apk-build-v30.log
)

APK=winlator-app/app/build/outputs/apk/debug/app-debug.apk
"$AAPT" dump badging "$APK" | tee apk-badging-v30.txt
grep "package: name='com.winlator.trcompat'" apk-badging-v30.txt
grep "versionCode='30'" apk-badging-v30.txt
grep "versionName='11.1-trcompat30-x3-boundary-font'" apk-badging-v30.txt
"$APKSIGNER" verify --verbose --print-certs "$APK" | tee apk-signature-v30.txt
grep 'Verified using v2 scheme (APK Signature Scheme v2): true' apk-signature-v30.txt
grep "Signer #1 certificate SHA-256 digest: $SIGNER_SHA" apk-signature-v30.txt

unzip -p "$APK" assets/rootfs.tzst > embedded-rootfs-v30.tzst
test "$(sha256sum embedded-rootfs-v30.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
unzip -p "$APK" assets/trcompat_wine_v29/ntoskrnl.exe > embedded-v29-ntoskrnl-v30.exe
test "$(sha256sum embedded-v29-ntoskrnl-v30.exe | cut -d' ' -f1)" = "$V29_NT_SHA"
unzip -p "$APK" assets/trcompat_locale_v29/ko_KR.utf8.tzst > embedded-ko-locale-v30.tzst
test "$(sha256sum embedded-ko-locale-v30.tzst | cut -d' ' -f1)" = "$V29_LOCALE_SHA"
unzip -p "$APK" classes.dex | strings > classes-v30-strings.txt
for marker in \
  'TR_DIAG_v30_X3_BOUNDARY_FONT.zip' \
  'KOREAN_WINDOWS_FONT_READY' \
  'KOREAN_WINDOWS_FONT_REGISTRY' \
  'KOREAN_REGISTRY_BACKUP' \
  'KOREAN_REGISTRY_ROLLBACK' \
  'Noto Sans CJK KR' \
  'MS Shell Dlg 2'; do
  grep -q "$marker" classes-v30-strings.txt
done

# Protection-specific code and response fabrication remain absent.
! grep -Eqi 'fake.*xhunter|bypass|disable.*xign|ioctl.*success|device.*spoof' \
  tr_winlator_apk/apply_v30_boundary_font_patch.py \
  winlator-app/v30-x3-boundary-font-report.txt

sha256sum "$APK" embedded-rootfs-v30.tzst embedded-v29-ntoskrnl-v30.exe embedded-ko-locale-v30.tzst \
  | tee final-sha256-v30.txt

rm -rf out-v30
mkdir out-v30
cp "$APK" out-v30/Winlator_TR_Compat_v30_X3_BOUNDARY_FONT.apk
sha256sum out-v30/Winlator_TR_Compat_v30_X3_BOUNDARY_FONT.apk > out-v30/SHA256SUMS.txt
cat > out-v30/README_KO.txt <<'EOF'
v30은 검증된 v29의 일반 드라이버/IRP 추적 바이너리를 그대로 유지한다.
추가 Wine 채널은 DLL 로딩과 버전 질의만 기록한다.
기기 시스템의 한국어 폰트를 기존 Wine prefix의 C:\windows\Fonts에 복사하고,
registry 백업 후 FontSubstitutes/Wine font replacements를 설정한다.
실패 시 registry 백업으로 원복한다.
게임·보호 모듈·서비스·장치·IOCTL·인증 결과는 수정하지 않는다.
실행 후 Documents/Winlator/TR_DIAG_v30_X3_BOUNDARY_FONT.zip을 수집한다.
EOF
