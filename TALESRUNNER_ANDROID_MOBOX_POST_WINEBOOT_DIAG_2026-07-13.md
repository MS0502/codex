# 테일즈런너 Android Mobox — Wineboot 실제 재시험 후속 진단

작성일: 2026-07-13  
대상: Galaxy Z Fold6 / Termux + Debian PRoot + custom Box64 + Wine 9.3 wow64

## 작업 경계

이 문서는 Wine/Box64의 정상 호환성만 진단한다.

- XIGNCODE 비활성화·우회·인젝션·스푸핑을 하지 않는다.
- 인증 우회나 실행 파일 변조를 하지 않는다.
- 공식 게임 실행 경로에 도달하기 전 Wine/Box64/Termux:X11 런타임을 정상화한다.

## 11번 실제 Wineboot 재시험 결과

입력 로그: `wineboot_execmod_test.txt`

확인된 결과:

```text
wine: created the configuration directory '/root/.wine-mobox-execmod'
...
wine: configuration in L"root/.wine-mobox-execmod" has been updated.
...
bash: line 24: 20677 Killed timeout 180s "$BOX" "$WINE" wineboot -i

WINEBOOT_RESULT=137
```

추가 집계:

```text
BOX64_EXECMOD_FALLBACK success: 456회
기존 ntdll.dll section .text / errno=13: 재발 없음
기존 virtual_setup_exception stack overflow: 재발 없음
```

### 판정

1. Android dirty private file mapping 실행 전환 문제를 처리하는 Box64 execmod fallback은 실제 Wine 자식 프로세스들에도 적용됐다.
2. 기존 Wine PE loader의 `ntdll.dll .text` 실패는 해소됐다.
3. prefix는 `configuration ... has been updated`까지 기록됐으므로, 새 prefix를 다시 삭제하고 `wineboot -i`를 반복할 단계가 아니다.
4. `137`은 `128 + SIGKILL(9)`이다. 일반적인 `timeout` 만료 결과 `124`와 다르다. 로그만으로 원인이 OOM/Android LMKD/수동 종료 중 무엇인지 확정할 수는 없지만, Wineboot 자체의 기존 논리 오류 코드 `1`로 보지 않는다.
5. prefix 갱신 후 정상적인 wineserver 종료까지 완료됐는지는 아직 확인되지 않았다.

## 현재 분리해야 할 문제

### A. Headless Wine core

기존 prefix를 유지한 채 다음이 0으로 끝나는지 확인한다.

```text
wine cmd /c ver
```

이 단계가 성공하면 Wine server, registry, PE loader의 최소 경로는 작동하는 것이다.

### B. Termux:X11 연결

로그에는 다음 오류가 반복됐다.

```text
nodrv_CreateWindow
Make sure that your X server is running and that $DISPLAY is set correctly.
```

가능성은 분리해서 확인해야 한다.

- Android 쪽 `$TMPDIR/.X11-unix/X0` 소켓 부재
- PRoot의 `/tmp/.X11-unix/X0` bind 실패
- Termux:X11 서버가 종료된 상태
- Wine X11 driver 또는 그 종속 라이브러리 로드 실패

### C. ARM64 네이티브 라이브러리

Box64가 다음 네이티브 라이브러리를 찾지 못했다.

```text
libfreetype.so.6       14회
libcups.so.2            5회
libgstreamer 계열       각 2회
libglib/libgobject      각 2회
libdbus-1.so.3          1회
libSDL2-2.0.so.0        1회
libusb-1.0.so.0         1회
```

`wineusb` 시작 실패는 `libusb-1.0.so.0` 부재와 직접 연결돼 있다. FreeType 부재는 Wine의 글꼴 및 GUI 초기화에 영향을 줄 수 있다. 다만 패키지 이름은 Debian 릴리스에 따라 `t64` 전환 여부가 다를 수 있으므로, 먼저 현재 `/etc/os-release`와 `apt-cache policy`를 수집한 뒤 설치한다.

### D. SIGKILL 원인

후속 스크립트는 다음을 수집한다.

- 실행 전후 `/proc/meminfo`
- 남아 있는 Wine/Box64 프로세스와 RSS/VSZ
- 접근 가능할 경우 `dmesg`의 OOM/SIGKILL 단서
- headless/GUI 각각의 종료 코드

## 다음 실행 파일

저장소 루트의 다음 파일을 사용한다.

```text
MOBOX_WINE_POSTBOOT_DIAG.sh
```

이 스크립트는 다음 원칙을 지킨다.

- `/root/.wine-mobox-execmod`를 삭제하지 않는다.
- 게임 또는 XIGNCODE를 실행하지 않는다.
- 패키지를 자동 설치하지 않는다.
- Wine core와 X11을 따로 시험한다.
- 종료 후 남은 wineserver만 정리한다.
- 전체 로그를 Android Downloads에 저장한다.

출력 파일:

```text
~/storage/downloads/mobox_wine_postboot_diag.txt
```

## 결과 판정표

### `HEADLESS_RESULT=0`

Wine core 최소 경로 성공. 다음 판단은 GUI 결과와 누락 라이브러리다.

### `HEADLESS_RESULT=137`

경량 명령에서도 외부 SIGKILL이 재현된 것이다. 메모리/프로세스 스냅샷을 우선 분석한다. prefix를 재생성하지 않는다.

### `HEADLESS_RESULT=124`

60초 동안 종료되지 않았다. 로그의 마지막 실행 프로세스와 wineserver 상태를 분석한다.

### `HEADLESS_OLD_NTDLL_COUNT` 또는 `GUI_OLD_NTDLL_COUNT`가 1 이상

execmod 패치가 해당 자식 실행 경로에 전달되지 않은 것이다. 사용된 Box64 경로와 자식 실행 방식을 다시 추적한다.

### `X11_SOCKET=missing`

Wine 문제가 아니라 Termux:X11 서버 또는 bind 단계부터 수정한다.

### `X11_SOCKET=present`, `GUI_NODRV_COUNT`가 1 이상

소켓은 연결됐지만 Wine X11 driver가 로드되지 않은 것이다. 네이티브 라이브러리 설치/로더 경로를 우선 수정한다.

### `GUI_RESULT=124`, `GUI_NODRV_COUNT=0`

가상 데스크톱 프로세스가 정상적으로 열린 채 25초 제한에 걸렸을 가능성이 높다. Termux:X11 화면 표시 여부와 함께 판단한다.

## 다음 단계 제한

이 진단이 통과하기 전에는 다음을 하지 않는다.

- prefix 재삭제 및 반복 Wineboot
- 공식 게임 실행
- XIGNCODE 관련 변경
- 누락 라이브러리의 무차별 설치

후속 로그에서 headless 성공, X11 연결, 필수 라이브러리 상태가 확인되면 영구 PRoot launcher와 Downloads `D:` 연결 단계로 진행한다.
