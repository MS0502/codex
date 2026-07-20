#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

MODE="${1:-apply}"
PKG='com.winlator.trcompat'
ROOT='files/rootfs'
TARGET64="$ROOT/opt/wine/lib/wine/x86_64-unix/winex11.so"
TARGET32="$ROOT/opt/wine/lib/wine/i386-unix/winex11.so"
BACKUP='files/tr_v18k_xshape_backup'
V18J64='41f74b52929d5227712f7ea4ef33e2af85b2cd8599271f9153bce74658564f29'
V18J32='10983a122bcafe0ad73ea4d275849686c87b95024057f0514e2268e2495a2ee6'
PATCH64='15d0fccef857a9a6fb96879fe5e6dd5e742473b27adf2a7188c0b06ec14b1b28'
PATCH32='541d6113b94e77f24a6d3ae0bb48774e24e420737371ed57c2c9b1c0f3ec0174'
HERE="$(cd "$(dirname "$0")" && pwd)"

fail() { echo "오류: $*" >&2; exit 1; }
app_sha() {
  run-as "$PKG" sh -c "if command -v sha256sum >/dev/null 2>&1; then sha256sum '$1'; else toybox sha256sum '$1'; fi" | awk '{print $1}'
}
stream_install() {
  local source="$1" target="$2" expected="$3"
  cat "$source" | run-as "$PKG" sh -c "umask 022; cat > '${target}.new'; chmod 0755 '${target}.new'; mv -f '${target}.new' '$target'"
  [ "$(app_sha "$target")" = "$expected" ] || fail "$target 설치 후 검증 실패"
}

case "$MODE" in apply|restore|status) ;; *) fail '사용법: bash xshape_hotpatch.sh [apply|restore|status]' ;; esac
command -v run-as >/dev/null 2>&1 || fail 'Android run-as 명령을 찾을 수 없음'
run-as "$PKG" id >/dev/null 2>&1 || fail 'Termux에서 앱 데이터 접근이 차단됨. 아무 파일도 변경하지 않았어.'

current64="$(app_sha "$TARGET64")"
current32="$(app_sha "$TARGET32")"
echo "현재 64비트: $current64"
echo "현재 32비트: $current32"

if [ "$MODE" = status ]; then
  if [ "$current64" = "$V18J64" ] && [ "$current32" = "$V18J32" ]; then echo '상태: v18J 원본';
  elif [ "$current64" = "$PATCH64" ] && [ "$current32" = "$PATCH32" ]; then echo '상태: XShape 복원 핫패치';
  else echo '상태: 알 수 없는 파일 조합'; exit 2; fi
  exit 0
fi

echo 'Winlator TR Compat를 최근 앱에서도 완전히 종료한 상태여야 해.'
sleep 3

if [ "$MODE" = restore ]; then
  run-as "$PKG" sh -c "test -f '$BACKUP/x86_64-unix/winex11.so' && test -f '$BACKUP/i386-unix/winex11.so'" || fail '복원용 백업이 없음'
  run-as "$PKG" sh -c "cp -p '$BACKUP/x86_64-unix/winex11.so' '${TARGET64}.new'; chmod 0755 '${TARGET64}.new'; mv -f '${TARGET64}.new' '$TARGET64'; cp -p '$BACKUP/i386-unix/winex11.so' '${TARGET32}.new'; chmod 0755 '${TARGET32}.new'; mv -f '${TARGET32}.new' '$TARGET32'"
  [ "$(app_sha "$TARGET64")" = "$V18J64" ] || fail '64비트 원본 복원 검증 실패'
  [ "$(app_sha "$TARGET32")" = "$V18J32" ] || fail '32비트 원본 복원 검증 실패'
  echo 'v18J 원본으로 복원 완료.'
  exit 0
fi

[ -f "$HERE/payload/x86_64-unix/winex11.so" ] || fail '64비트 payload 없음'
[ -f "$HERE/payload/i386-unix/winex11.so" ] || fail '32비트 payload 없음'
echo "$PATCH64  $HERE/payload/x86_64-unix/winex11.so" | sha256sum -c -
echo "$PATCH32  $HERE/payload/i386-unix/winex11.so" | sha256sum -c -

if [ "$current64" = "$PATCH64" ] && [ "$current32" = "$PATCH32" ]; then
  echo '이미 핫패치 적용 상태야.'
  exit 0
fi
[ "$current64" = "$V18J64" ] || fail '64비트 파일이 알려진 v18J 원본과 달라 적용 중단'
[ "$current32" = "$V18J32" ] || fail '32비트 파일이 알려진 v18J 원본과 달라 적용 중단'

run-as "$PKG" sh -c "mkdir -p '$BACKUP/x86_64-unix' '$BACKUP/i386-unix'; test -f '$BACKUP/x86_64-unix/winex11.so' || cp -p '$TARGET64' '$BACKUP/x86_64-unix/winex11.so'; test -f '$BACKUP/i386-unix/winex11.so' || cp -p '$TARGET32' '$BACKUP/i386-unix/winex11.so'"
[ "$(app_sha "$BACKUP/x86_64-unix/winex11.so")" = "$V18J64" ] || fail '64비트 백업 검증 실패'
[ "$(app_sha "$BACKUP/i386-unix/winex11.so")" = "$V18J32" ] || fail '32비트 백업 검증 실패'

stream_install "$HERE/payload/x86_64-unix/winex11.so" "$TARGET64" "$PATCH64"
stream_install "$HERE/payload/i386-unix/winex11.so" "$TARGET32" "$PATCH32"
echo 'XShape 복원 핫패치 적용 완료. 변경 파일은 winex11.so 두 개뿐이야.'
echo '되돌리기: bash xshape_hotpatch.sh restore'
