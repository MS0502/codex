#!/usr/bin/env bash
set -euo pipefail

REPO="MS0502/codex"
V28_RUN="30999623220"
V28_ARTIFACT="WINLATOR_TR_COMPAT_V28_ACTIVE_IRP_TRACE_APK"
V28_APK_SHA="82aa2b1bf09f7b3ac98a93e22cfa832c34523e974e3694c0c7ceddf7b8a1ff92"
SIGNER_SHA="3819847878a333cc204bd93ab89a28a9867c066da5def40401d840fda9f9f017"
ROOTFS_SHA="fd084ca23321b9ae357716f570a8d79143754ae1d182aa5082f2ecf26a87ca9b"
V27_NT_SHA="bac18cca32f701c0315203ab489e2b557b78a2c72cf160256245c6015282c5c8"
WINE_COMMIT="494fb8f4a30fcb9d0b9c00f72a7f2b7a17e787b0"
WINLATOR_COMMIT="c2f4ad4534f4637b543a9a3b085e28f50cf6d01c"

rm -rf exact-v28 wine-src build64 wine-components-v29 winlator-app locale-audit out-v29
mkdir -p exact-v28 wine-components-v29

python3 -m py_compile \
  tr_wine_compat/apply_v27_irp_trace_patch.py \
  tr_wine_compat/apply_v29_driver_load_trace_patch.py \
  tr_wine_compat/audit_pe_driver.py \
  tr_winlator_apk/apply_v26_crash_observability_patch.py \
  tr_winlator_apk/apply_v27_patch.py \
  tr_winlator_apk/apply_v28_runtime_refresh_patch.py \
  tr_winlator_apk/apply_v29_patch.py

localedef --version | head -n1 | tee localedef-version.txt
grep -q ' 2\.39' localedef-version.txt

# Exact validated v28 input.
gh run download "$V28_RUN" --repo "$REPO" --name "$V28_ARTIFACT" --dir exact-v28
V28_APK=exact-v28/Winlator_TR_Compat_v28_ACTIVE_IRP_TRACE.apk
test -s "$V28_APK"
test "$(sha256sum "$V28_APK" | cut -d' ' -f1)" = "$V28_APK_SHA"
APKSIGNER="$ANDROID_HOME/build-tools/34.0.0/apksigner"
AAPT="$ANDROID_HOME/build-tools/34.0.0/aapt"
"$APKSIGNER" verify --verbose --print-certs "$V28_APK" | tee exact-v28-signature.txt
grep 'Verified using v2 scheme (APK Signature Scheme v2): true' exact-v28-signature.txt
grep "Signer #1 certificate SHA-256 digest: $SIGNER_SHA" exact-v28-signature.txt

unzip -p "$V28_APK" assets/rootfs.tzst > exact-v28-rootfs.tzst
test "$(sha256sum exact-v28-rootfs.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
tar --use-compress-program=unzstd -xOf exact-v28-rootfs.tzst ./usr/lib/libc.so.6 > rootfs-libc.so.6
strings rootfs-libc.so.6 > rootfs-libc-strings.txt
grep 'stable release version 2.39' rootfs-libc-strings.txt | head -n1 | tee rootfs-glibc-version.txt

tar --use-compress-program=unzstd -xOf exact-v28-rootfs.tzst \
  ./opt/wine/lib/wine/x86_64-windows/ntoskrnl.exe > exact-v28-ntoskrnl.exe
test "$(sha256sum exact-v28-ntoskrnl.exe | cut -d' ' -f1)" = "$V27_NT_SHA"
strings exact-v28-ntoskrnl.exe | grep -q 'IRP_TRACE begin'

# Build generic v29 trace-only ntoskrnl.
git init wine-src
git -C wine-src remote add origin https://github.com/brunodev85/wine-10.10-custom.git
git -C wine-src fetch --depth 1 origin "$WINE_COMMIT"
git -C wine-src checkout --detach FETCH_HEAD
test "$(git -C wine-src rev-parse HEAD)" = "$WINE_COMMIT"
python3 tr_wine_compat/apply_v27_irp_trace_patch.py wine-src
python3 tr_wine_compat/apply_v29_driver_load_trace_patch.py wine-src
git -C wine-src diff --check
git -C wine-src diff -- dlls/ntoskrnl.exe/ntoskrnl.c | tee v29-wine-source.diff
for marker in \
  'IRP_TRACE begin' \
  'DRIVER_LOAD ZwLoadDriver begin' \
  'DRIVER_LOAD image-load return' \
  'DRIVER_LOAD DriverEntry return' \
  'DRIVER_LOAD IoCreateDevice created'; do
  grep -q "$marker" wine-src/dlls/ntoskrnl.exe/ntoskrnl.c
done
! grep -Eqi 'xhunter|6d4084|wellbia|xigncode|talesrunner' \
  tr_wine_compat/apply_v29_driver_load_trace_patch.py \
  wine-src/dlls/ntoskrnl.exe/ntoskrnl.c

mkdir build64
(
  cd build64
  ../wine-src/configure \
    --enable-win64 \
    --prefix=/data/data/com.winlator/files/rootfs/opt/wine \
    --without-alsa --without-capi --without-coreaudio --without-cups \
    --without-dbus --without-fontconfig --without-freetype --without-gettext \
    --without-gettextpo --without-gphoto --without-gssapi --without-inotify \
    --without-krb5 --without-ldap --without-netapi --without-openal \
    --without-opencl --without-opengl --without-oss --without-pcap \
    --without-pcsclite --without-pulse --without-sane --without-sdl \
    --without-udev --without-unwind --without-usb --without-v4l2 \
    --without-vulkan --without-wayland --without-x --without-xattr
)
set -o pipefail
make -C build64 -j2 dlls/ntoskrnl.exe/x86_64-windows/ntoskrnl.exe \
  2>&1 | tee v29-wine-build.log
cp build64/dlls/ntoskrnl.exe/x86_64-windows/ntoskrnl.exe wine-components-v29/ntoskrnl.exe
x86_64-w64-mingw32-strip --strip-unneeded wine-components-v29/ntoskrnl.exe
file wine-components-v29/ntoskrnl.exe | tee v29-ntoskrnl-file.txt
grep -q 'PE32+ executable' v29-ntoskrnl-file.txt
for marker in \
  'IRP_TRACE begin' \
  'DRIVER_LOAD ZwLoadDriver begin' \
  'DRIVER_LOAD DriverEntry enter' \
  'DRIVER_LOAD IoCreateDevice created'; do
  strings wine-components-v29/ntoskrnl.exe | grep -q "$marker"
done
! strings wine-components-v29/ntoskrnl.exe | grep -Eqi 'xhunter|6d4084|wellbia|xigncode|talesrunner'
sha256sum wine-components-v29/ntoskrnl.exe | tee v29-ntoskrnl-sha256.txt
python3 tr_wine_compat/audit_pe_driver.py \
  wine-components-v29/ntoskrnl.exe --output v29-ntoskrnl-pe-audit.json
grep -q '"machine_name": "x86_64"' v29-ntoskrnl-pe-audit.json
grep -q '"native_subsystem": true' v29-ntoskrnl-pe-audit.json

# Reproduce exact v28 application source and rootfs.
git init winlator-app
git -C winlator-app remote add origin https://github.com/brunodev85/winlator-app.git
git -C winlator-app fetch --depth 1 origin "$WINLATOR_COMMIT"
git -C winlator-app checkout --detach FETCH_HEAD
test "$(git -C winlator-app rev-parse HEAD)" = "$WINLATOR_COMMIT"
git -C winlator-app lfs pull

BASE_ROOTFS=winlator-app/app/src/main/assets/rootfs.tzst
test "$(sha256sum "$BASE_ROOTFS" | cut -d' ' -f1)" = \
  27c12533323e0cc0e5f4ddf141a0d567e340cf2740e5aebaefc63b039fd19613

cp exact-v28-ntoskrnl.exe wine-components-v29/ntoskrnl-v27.exe
tar --use-compress-program=unzstd -xOf "$BASE_ROOTFS" ./opt/wine/lib/wine/x86_64-unix/ntdll.so > wine-components-v29/ntdll.so
tar --use-compress-program=unzstd -xOf "$BASE_ROOTFS" ./opt/wine/lib/wine/x86_64-windows/wow64.dll > wine-components-v29/wow64.dll
tar --use-compress-program=unzstd -xOf "$BASE_ROOTFS" ./opt/wine/bin/wineserver > wine-components-v29/wineserver
tar --use-compress-program=unzstd -xOf "$BASE_ROOTFS" ./opt/wine/lib/wine/x86_64-unix/nsiproxy.so > wine-components-v29/nsiproxy.so
python3 - <<'PY'
from pathlib import Path
import hashlib
root=Path('wine-components-v29')
old=b'/data/data/com.winlator/files/rootfs'
alias=b'/data/user/0/com.winlator.trcompat/r'
source={
 'ntdll.so':'39f254917b939051ab32fe2df6357acc47b22b39e0c62dce4766e052286bdb0f',
 'wow64.dll':'2fbdc987de14bf15aa56ac2c3f9f4e4a2034905cc0812ea5d5b83005a69965df',
 'wineserver':'f91a57493829473f3c08dc4f8976a47646b7df736c352c0359e26f2c1cb9784f',
 'nsiproxy.so':'bac106d309fd86b3a64b6d55c8b115d618b1629204dd56731e5616401b3e6aad',
}
final={
 'ntdll.so':'d24a6f8c3fcadfb8fda16002dac47ca71304eccc702453c4424c4cfb859cdfad',
 'wow64.dll':'2fbdc987de14bf15aa56ac2c3f9f4e4a2034905cc0812ea5d5b83005a69965df',
 'wineserver':'ea66ec3d956bea4b1c4e880352a655dad6036186b3645dc02cd11062386a13cc',
 'nsiproxy.so':'f747f50334ac75b26d60485ff6ed707d4b310456495374c2b43d219378ac2787',
}
for name, expected in source.items():
    p=root/name; data=p.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected: raise SystemExit(f'{name}: source drift')
    data=data.replace(old,alias); p.write_bytes(data)
    if hashlib.sha256(data).hexdigest()!=final[name]: raise SystemExit(f'{name}: final drift')
PY
chmod 755 wine-components-v29/ntdll.so wine-components-v29/wineserver wine-components-v29/nsiproxy.so

python3 tr_winlator_apk/apply_v26_crash_observability_patch.py \
  winlator-app wine-components-v29 2>&1 | tee v29-v26-baseline.log
mv wine-components-v29/ntoskrnl.exe wine-components-v29/ntoskrnl-v29.exe
mv wine-components-v29/ntoskrnl-v27.exe wine-components-v29/ntoskrnl.exe
python3 tr_winlator_apk/apply_v27_patch.py \
  winlator-app wine-components-v29 --already-v26 2>&1 | tee v29-v27-baseline.log
python3 tr_winlator_apk/apply_v28_runtime_refresh_patch.py \
  winlator-app wine-components-v29 --already-v27 2>&1 | tee v29-v28-baseline.log
mv wine-components-v29/ntoskrnl.exe wine-components-v29/ntoskrnl-v27.exe
mv wine-components-v29/ntoskrnl-v29.exe wine-components-v29/ntoskrnl.exe

test "$(sha256sum winlator-app/app/src/main/assets/rootfs.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
cmp -s winlator-app/app/src/main/assets/rootfs.tzst exact-v28-rootfs.tzst
python3 - <<'PY'
from pathlib import Path
import hashlib,json,stat
root=Path('winlator-app'); out={}
for p in sorted(root.rglob('*')):
    if not p.is_file() or p.is_symlink(): continue
    rel=p.relative_to(root).as_posix()
    out[rel]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
              'mode':stat.S_IMODE(p.stat().st_mode),'size':p.stat().st_size}
Path('v28-source-inventory.json').write_text(json.dumps(out,sort_keys=True),encoding='utf-8')
PY

# Apply v29.
python3 tr_winlator_apk/apply_v29_patch.py \
  winlator-app wine-components-v29 2>&1 | tee v29-apply.log
grep -R 'versionName "11.1-trcompat29-driver-load-ko"' -n winlator-app/app/build.gradle
grep -R 'TR_DIAG_v29_DRIVER_LOAD_KO.zip' -n winlator-app/app/src/main/java/com/winlator/core/TrCompatDiagnostics.java
grep -R 'v29-driver-load-trace-1' -n winlator-app/app/src/main/java/com/winlator/core/TrCompatNtKernelPatcher.java
grep -R 'v29-korean-support-1' -n winlator-app/app/src/main/java/com/winlator/core/TrCompatKoreanSupport.java
grep -R 'ko_KR.UTF-8' -n winlator-app/app/src/main/java/com/winlator/XServerDisplayActivity.java

python3 - <<'PY'
from pathlib import Path
import hashlib,json,stat
root=Path('winlator-app')
before=json.loads(Path('v28-source-inventory.json').read_text(encoding='utf-8'))
after={}
for p in sorted(root.rglob('*')):
    if not p.is_file() or p.is_symlink(): continue
    rel=p.relative_to(root).as_posix()
    after[rel]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                'mode':stat.S_IMODE(p.stat().st_mode),'size':p.stat().st_size}
added=set(after)-set(before); removed=set(before)-set(after)
changed={p for p in set(before)&set(after) if before[p]!=after[p]}
expected_added={
 'app/src/main/assets/trcompat_wine_v29/ntoskrnl.exe',
 'app/src/main/assets/trcompat_locale_v29/ko_KR.utf8.tzst',
 'app/src/main/java/com/winlator/core/TrCompatKoreanSupport.java',
 'v29-driver-load-ko-report.txt',
}
expected_changed={
 'app/build.gradle',
 'app/src/main/java/com/winlator/XServerDisplayActivity.java',
 'app/src/main/java/com/winlator/core/TrCompatDiagnostics.java',
 'app/src/main/java/com/winlator/core/TrCompatNtKernelPatcher.java',
}
if added!=expected_added: raise SystemExit(f'unexpected added: {sorted(added)}')
if removed: raise SystemExit(f'unexpected removed: {sorted(removed)}')
if changed!=expected_changed: raise SystemExit(f'unexpected changed: {sorted(changed)}')
print('v29 exact source delta proved')
PY

test "$(sha256sum winlator-app/app/src/main/assets/rootfs.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
cmp -s winlator-app/app/src/main/assets/rootfs.tzst exact-v28-rootfs.tzst
NT=winlator-app/app/src/main/assets/trcompat_wine_v29/ntoskrnl.exe
test "$(sha256sum "$NT" | cut -d' ' -f1)" = "$(sha256sum wine-components-v29/ntoskrnl.exe | cut -d' ' -f1)"
strings "$NT" | grep -q 'DRIVER_LOAD ZwLoadDriver begin'
strings "$NT" | grep -q 'DRIVER_LOAD DriverEntry return'
! strings "$NT" | grep -Eqi 'xhunter|6d4084|wellbia|xigncode|talesrunner'

LOCALE=winlator-app/app/src/main/assets/trcompat_locale_v29/ko_KR.utf8.tzst
test -s "$LOCALE"
mkdir locale-audit
tar --use-compress-program=unzstd -xf "$LOCALE" -C locale-audit
test -s locale-audit/usr/lib/locale/ko_KR.utf8/LC_CTYPE
test -s locale-audit/usr/lib/locale/ko_KR.utf8/LC_COLLATE
test -s locale-audit/usr/lib/locale/ko_KR.utf8/LC_MESSAGES/SYS_LC_MESSAGES
test "$(find locale-audit -type f | wc -l)" -ge 6

for assertion in \
  'rootfs_reinstall_forced=false' \
  'container_home_preserved=true' \
  'windows_acp_registry_changed=false' \
  'driver_or_ioctl_status_changed=false'; do
  grep -q "$assertion" winlator-app/v29-driver-load-ko-report.txt
done

grep -q 'public static final byte LATEST_VERSION = 19;' winlator-app/app/src/main/java/com/winlator/xenvironment/RootFSInstaller.java
grep -q 'public static final byte UPDATE_WINEPREFIX_VERSION = 16;' winlator-app/app/src/main/java/com/winlator/xenvironment/RootFSInstaller.java

# Build and verify signed APK.
(
  cd winlator-app
  chmod +x gradlew
  set -o pipefail
  ./gradlew --no-daemon --stacktrace assembleDebug 2>&1 | tee ../apk-build-v29.log
)
APK=winlator-app/app/build/outputs/apk/debug/app-debug.apk
"$AAPT" dump badging "$APK" | tee apk-badging-v29.txt
grep "package: name='com.winlator.trcompat'" apk-badging-v29.txt
grep "versionCode='28'" apk-badging-v29.txt
grep "versionName='11.1-trcompat29-driver-load-ko'" apk-badging-v29.txt
"$APKSIGNER" verify --verbose --print-certs "$APK" | tee apk-signature-v29.txt
grep 'Verified using v2 scheme (APK Signature Scheme v2): true' apk-signature-v29.txt
grep "Signer #1 certificate SHA-256 digest: $SIGNER_SHA" apk-signature-v29.txt

unzip -p "$APK" assets/rootfs.tzst > embedded-rootfs-v29.tzst
test "$(sha256sum embedded-rootfs-v29.tzst | cut -d' ' -f1)" = "$ROOTFS_SHA"
cmp -s embedded-rootfs-v29.tzst exact-v28-rootfs.tzst
unzip -p "$APK" assets/trcompat_wine_v29/ntoskrnl.exe > embedded-v29-ntoskrnl.exe
test "$(sha256sum embedded-v29-ntoskrnl.exe | cut -d' ' -f1)" = "$(sha256sum wine-components-v29/ntoskrnl.exe | cut -d' ' -f1)"
strings embedded-v29-ntoskrnl.exe | grep -q 'DRIVER_LOAD ZwLoadDriver begin'
strings embedded-v29-ntoskrnl.exe | grep -q 'DRIVER_LOAD DriverEntry enter'
strings embedded-v29-ntoskrnl.exe | grep -q 'IRP_TRACE begin'
! strings embedded-v29-ntoskrnl.exe | grep -Eqi 'xhunter|6d4084|wellbia|xigncode|talesrunner'
unzip -p "$APK" assets/trcompat_locale_v29/ko_KR.utf8.tzst > embedded-ko-locale-v29.tzst
test "$(sha256sum embedded-ko-locale-v29.tzst | cut -d' ' -f1)" = "$(sha256sum "$LOCALE" | cut -d' ' -f1)"
unzip -p "$APK" classes.dex | strings > classes-v29-strings.txt
grep -q 'KOREAN_SUPPORT_BEGIN' classes-v29-strings.txt
grep -q 'KOREAN_FONT_READY' classes-v29-strings.txt
grep -q 'TR_DIAG_v29_DRIVER_LOAD_KO.zip' classes-v29-strings.txt
grep -q 'NTOSKRNL_RUNTIME_VERIFY' classes-v29-strings.txt
sha256sum "$APK" embedded-rootfs-v29.tzst embedded-v29-ntoskrnl.exe embedded-ko-locale-v29.tzst | tee final-sha256-v29.txt

mkdir out-v29
cp "$APK" out-v29/Winlator_TR_Compat_v29_DRIVER_LOAD_KO.apk
sha256sum out-v29/Winlator_TR_Compat_v29_DRIVER_LOAD_KO.apk > out-v29/SHA256SUMS.txt
cat > out-v29/README_KO.txt <<'EOF'
v29은 일반 Wine 네이티브 드라이버 로딩 파이프라인을 추적한다.
서비스, ImagePath, PE 매핑, DriverEntry, 장치·심볼릭 링크 생성 결과만 기록한다.
드라이버·장치·IOCTL·보안·인증 결과를 조작하지 않는다.
기존 컨테이너와 Wine prefix를 유지하고 rootfs 전체 재설치를 강제하지 않는다.
별도 ko_KR.UTF-8 로캘을 설치하고 기기 시스템 파티션의 한국어 폰트를 앱 내부에서 재사용한다.
실행 후 Documents/Winlator/TR_DIAG_v29_DRIVER_LOAD_KO.zip을 수집한다.
EOF
