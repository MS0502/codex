#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

MODE="${1:-status}"
PKG='com.winlator.trcompat'
APP_ROOT='files/rootfs'
BOX64="$APP_ROOT/usr/local/bin/box64"
BOX64_REAL="$APP_ROOT/usr/local/bin/box64.trtrace.real"
TRACER="$APP_ROOT/usr/local/bin/tr_x11_map_watch"
TRACE_DIR='files/tr_x11_trace'
ORIGINAL_BOX64_SHA256='2c6f9846e327dba80a210572d16b1811f6dd041c850e48b2d02b34677e09c421'
HERE="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD="$HERE/payload"
SUMS="$HERE/SHA256SUMS.txt"

fail() { echo "오류: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "$1 명령을 찾을 수 없음"; }
app_sha() {
  run-as "$PKG" sh -c "if command -v sha256sum >/dev/null 2>&1; then sha256sum '$1'; else toybox sha256sum '$1'; fi" \
    | awk '{print $1}'
}
app_exists() { run-as "$PKG" sh -c "test -e '$1'"; }
stream_install() {
  local source="$1" target="$2" mode="$3" expected="$4"
  cat "$source" | run-as "$PKG" sh -c \
    "umask 022; cat > '${target}.new'; chmod '$mode' '${target}.new'; mv -f '${target}.new' '$target'"
  [ "$(app_sha "$target")" = "$expected" ] || fail "$target 설치 후 해시 검증 실패"
}
expected_sha() {
  local name="$1"
  awk -v n="payload/$name" '$2 == n {print $1; exit}' "$SUMS"
}
show_status() {
  local current backup='missing'
  current="$(app_sha "$BOX64")"
  if app_exists "$BOX64_REAL"; then backup="$(app_sha "$BOX64_REAL")"; fi
  echo "현재 box64: $current"
  echo "백업 box64: $backup"
  if [ "$current" = "$ORIGINAL_BOX64_SHA256" ]; then
    echo '상태: v18J 원본 box64'
  elif [ "$backup" = "$ORIGINAL_BOX64_SHA256" ] && app_exists "$TRACER"; then
    echo '상태: 물리 기기 X11 추적 래퍼 적용됨'
  else
    echo '상태: 알 수 없는 파일 조합'
    return 2
  fi
}
collect_trace() {
  local output_dir output
  if [ -d "$HOME/storage/downloads" ]; then
    output_dir="$HOME/storage/downloads"
  else
    output_dir="$PWD"
  fi
  mkdir -p "$output_dir"
  output="$output_dir/TR_X11_MAP_TRACE_$(date +%Y%m%d-%H%M%S).tar.gz"
  run-as "$PKG" sh -c \
    "test -d '$TRACE_DIR'; test -n \"\$(find '$TRACE_DIR' -maxdepth 1 -type f -name 'trace-*.txt' -print -quit)\"; tar -C '$TRACE_DIR' -cf - ." \
    | gzip -9 > "$output"
  test -s "$output" || fail '추적 파일 수집 결과가 비어 있음'
  sha256sum "$output"
  echo "수집 완료: $output"
}
restore_box64() {
  local backup
  app_exists "$BOX64_REAL" || fail '복원용 box64 백업이 없음'
  backup="$(app_sha "$BOX64_REAL")"
  [ "$backup" = "$ORIGINAL_BOX64_SHA256" ] || fail '복원용 box64 해시가 기준과 다름'
  run-as "$PKG" sh -c \
    "cp -p '$BOX64_REAL' '${BOX64}.new'; chmod 0755 '${BOX64}.new'; mv -f '${BOX64}.new' '$BOX64'; rm -f '$TRACER' '$BOX64_REAL'; rm -rf '$TRACE_DIR/session.lock'"
  [ "$(app_sha "$BOX64")" = "$ORIGINAL_BOX64_SHA256" ] || fail 'box64 원본 복원 검증 실패'
  echo 'v18J 원본 box64로 복원 완료.'
}

case "$MODE" in apply|collect|restore|finish|status) ;;
  *) fail '사용법: bash physical_x11_trace.sh [apply|collect|restore|finish|status]' ;;
esac

need run-as
run-as "$PKG" id >/dev/null 2>&1 || fail '앱 데이터 접근이 차단됨. 디버그 빌드인지 확인 필요'

case "$MODE" in
  status)
    show_status
    ;;
  apply)
    need sha256sum
    [ -f "$SUMS" ] || fail 'SHA256SUMS.txt 없음'
    [ -f "$PAYLOAD/tr_x11_map_watch" ] || fail 'ARM64 추적기 payload 없음'
    [ -f "$PAYLOAD/box64-wrapper" ] || fail 'box64 래퍼 payload 없음'
    (cd "$HERE" && sha256sum -c SHA256SUMS.txt)
    current="$(app_sha "$BOX64")"
    [ "$current" = "$ORIGINAL_BOX64_SHA256" ] || fail '현재 box64가 검증된 v18J 원본과 다름. 적용 중단'
    echo 'Winlator TR Compat를 최근 앱 화면에서도 완전히 종료해.'
    sleep 3
    run-as "$PKG" sh -c \
      "mkdir -p '$TRACE_DIR'; rm -rf '$TRACE_DIR/session.lock'; test -f '$BOX64_REAL' || cp -p '$BOX64' '$BOX64_REAL'"
    [ "$(app_sha "$BOX64_REAL")" = "$ORIGINAL_BOX64_SHA256" ] || fail 'box64 백업 검증 실패'
    stream_install "$PAYLOAD/tr_x11_map_watch" "$TRACER" 0755 "$(expected_sha tr_x11_map_watch)"
    stream_install "$PAYLOAD/box64-wrapper" "$BOX64" 0755 "$(expected_sha box64-wrapper)"
    show_status
    echo '적용 완료. Winlator를 한 번 열고 문제가 보이는 화면에서 30초 이상 기다린 뒤 완전히 종료해.'
    ;;
  collect)
    collect_trace
    ;;
  restore)
    echo 'Winlator TR Compat를 완전히 종료한 상태여야 해.'
    sleep 2
    restore_box64
    ;;
  finish)
    echo 'Winlator TR Compat를 완전히 종료한 상태여야 해.'
    sleep 2
    collect_trace
    restore_box64
    ;;
esac
