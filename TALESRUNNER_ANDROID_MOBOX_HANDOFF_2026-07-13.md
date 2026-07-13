# 테일즈런너 Android 로컬 실행 — Mobox/Box64 작업 인수인계

작성일: 2026-07-13
대상 기기: Samsung Galaxy Z Fold6 / Snapdragon 8 Gen 3
목표: 원격 플레이 없이 Android 기기 안에서 한국 테일즈런너를 로컬 실행

> 새 채팅에서는 이 문서를 먼저 읽고, **마지막 작업 단계부터 이어서 진행**할 것.
> 인증 토큰, 쿠키, 캡처된 원문 URI, 임시 토큰 파일 내용은 절대 요청하거나 공유하지 않는다.
> XIGNCODE 우회·비활성화·인젝션·스푸핑은 하지 않는다. 허용 범위는 Wine/Box64/런타임 호환성 진단과 정상 실행 경로 구성까지다.

---

## 1. 현재 바로 알아야 할 상태

### 현재 실행 중일 수 있는 명령이 오래 걸리는 이유

가장 최근 Wineboot 테스트 명령은 출력 전체를 파일로 리다이렉트한다.

```bash
... >"$OUT" 2>&1
```

그래서 실행 중에는 터미널이 멈춘 것처럼 보일 수 있다. 새 Wine prefix를 만드는 첫 Wineboot는 보통 수십 초에서 수분이 걸릴 수 있고, 현재 명령에는 다음 제한이 있다.

```bash
timeout 180s
```

즉 최대 180초 후에는 종료된다. 실행이 끝나야 `=== 핵심 결과 ===`가 화면에 나온다.

### 가장 최근 확정된 기술적 성과

Android에서는 파일을 `MAP_PRIVATE + RW`로 매핑한 뒤 내용을 수정하고 `RX`로 바꾸는 동작이 다음 오류로 차단된다.

```text
errno=13 (Permission denied)
```

깨끗한 파일 매핑은 `RW -> RX`가 성공하지만, 한 번이라도 수정한 파일 기반 private mapping은 `RW -> RX`가 실패한다.

ARM64 네이티브와 x86-64/Box64 양쪽에서 동일하게 재현됐다.

```text
MODE=CLEAN
MPROTECT=0 errno=0

MODE=DIRTY
MPROTECT=-1 errno=13
```

Wine은 PE DLL을 파일에서 매핑한 뒤 재배치·초기화로 내용을 수정하고 `.text`를 실행 가능하게 바꾸므로, `ntdll.dll` 로딩 시 이 제한에 걸렸다.

이 문제를 해결하기 위해 Box64 `my_mprotect()`에 다음 compatibility fallback을 추가했다.

1. `mprotect(..., PROT_EXEC)`가 `EACCES`로 실패
2. 대상 바이트를 임시 버퍼에 복사
3. 같은 주소를 익명 `RW` 메모리로 `MAP_FIXED` 재매핑
4. 원래 바이트를 복원
5. 익명 메모리에 최종 `RX` 적용

패치 후 재현 테스트가 성공했다.

```text
[BOX64_EXECMOD_FALLBACK] success addr=0x7ffff41000 len=0x74000 prot=0x5

MODE=CLEAN
MPROTECT=0 errno=0 (Success)

MODE=DIRTY
PAGE_MODIFIED=YES
MPROTECT=0 errno=0 (Success)
```

패치 스크립트:

```text
MS0502/codex/BOX64_EXECMOD_PATCH_V3.sh
```

해당 스크립트를 만든 커밋:

```text
e0e0f700e26e35972e9bdc4bb7a8177a437968d4
```

구버전 `BOX64_EXECMOD_PATCH.sh`는 Python 정규식 치환 중 C 문자열의 `\n`을 실제 줄바꿈으로 손상시킨 적이 있으므로 사용하지 않는다. 반드시 `BOX64_EXECMOD_PATCH_V3.sh`만 사용한다.

---

## 2. 전체 목표와 큰 흐름

최종 목표는 다음 순서다.

1. 공식 한국 테일즈런너 파일 확보 및 검증
2. 공식 웹 로그인 흐름을 Android에서 캡처
3. 공식 인증 서버를 통한 일회성 코드 교환과 토큰 갱신
4. Wine 안에서 인증된 정상 게임 실행
5. Wine/Box64 환경에서 게임 및 XIGNCODE 호환성 확인

1~4의 인증·파일 준비는 이미 상당 부분 완료됐다. 현재는 5번을 위해 Mobox/Box64/Wineboot 자체를 정상화하는 단계다.

---

## 3. 공식 게임 파일 상태

공식 한국 테일즈런너 manifest:

```text
https://trdown.rhaon.co.kr/dist_talesrunner/latest.json
```

공식 파일 12개를 다운로드했고 MD5 검증을 통과했다.

Android 저장 경로:

```text
~/storage/downloads/TR_KR_LOCAL/game
```

기존 Winlator 기준 Wine 경로:

```text
D:\TR_KR_LOCAL\game
```

`talesrunner.exe` 자체는 Winlator에서 로딩 화면까지 도달한 적이 있다.

---

## 4. 공식 런처 조사 결과

공식 런처 경로:

```text
C:\Program Files\Blomics\Launcher\Launcher.exe
```

구성:

- x64
- .NET 8
- MAUI/WinUI 3
- Windows App SDK 1.5

Wine 실행 오류:

```text
-2147450743
```

16진수:

```text
0x80008089 CoreClrInitFailure
```

.NET Desktop Runtime을 8.0.4에서 8.0.28로 올려도 해결되지 않았다.

공식 런처 UI 경로는 현재 필수가 아니다. Android URI bridge와 공식 인증 bridge로 인증 흐름을 대체했기 때문이다.

---

## 5. Android URI bridge 및 공식 인증 bridge

Android용 URI bridge APK를 만들었다.

역할:

- Android Chrome에서 `TRLauncher://...` URI 수신
- 선택한 `Download/TR_KR_LOCAL` 아래에 요청 메타데이터 저장

캡처된 URI 구조는 다음과 같다.

- scheme: `trlauncher`
- path segment 길이: `13 / 1 / 36`
- 가운데 segment: `0`
- 마지막 segment: UUID 형태의 일회성 코드

원문 URI나 인증 값은 공유하지 않는다.

공식 인증 bridge 스크립트:

```text
TR_AUTH_BRIDGE.py
```

사용한 공식 endpoint:

```text
https://auth.rhaon.co.kr/token/login
https://auth.rhaon.co.kr/token/refresh
```

정상 성공 출력:

```text
1/3 공식 일회성 코드 교환 중...
2/3 공식 토큰 갱신 중...
3/3 완료
```

공식 인증 교환은 정상 작동한다.

게임 실행 배치 파일:

```text
TR_LOGIN_AND_RUN_FIXED.bat
```

반드시 `FIXED` 버전을 사용한다. 임시 토큰을 읽은 뒤 삭제하도록 되어 있다.

---

## 6. Winlator에서 확인된 XIGNCODE 단계

공식 인증을 통과해 게임을 실행하면 XIGNCODE 단계까지 진행했고 다음 오류가 발생했다.

```text
XIGNCODE ENTER ERROR (E0190204)
```

프로세스 관찰:

- `xldr_TalesRunner_KR_loader_x64.exe` 시작
- 메모리 약 57MB에서 99~105MB까지 증가
- 이후 종료
- 실제 게임 프로세스는 시작되지 않음

XIGNCODE 파일에서 확인된 문자열:

- `DeviceIoControl`
- `NtQueryVirtualMemory`
- `NtReadVirtualMemory`
- `IsWow64Process2`
- `IsDebuggerPresent`
- driver/system path 관련 문자열

주의:

- E0190204의 공식 의미는 확인되지 않았다.
- “커널 드라이버가 반드시 필요하다”라고 단정하지 않는다.
- 우회나 비활성화는 하지 않는다.
- Mobox/PRoot에서도 동일한 단계까지 도달하는지 정상 호환성만 확인한다.

---

## 7. 이미 시험한 Winlator 계열

다음 환경에서 XIGNCODE 단계 또는 유사 실패를 확인했다.

- Winlator 11.1 fresh: 동일 XIGNCODE 단계 실패
- Winlator 10.0 Hotfix: 약 17초 로딩 후 컨테이너 종료
- Winlator 9.0: 더 빠른 실패
- Winlator 8.0 Rev1: 동일
- longjunyu2 Native Glibc 7.1.5: 동일

공식 런처 installer는 Wine에서 다음 오류가 났다.

```text
Runtime error 216 at 00407DFC
```

런처 UI는 현재 인증 bridge 때문에 불필요하다.

---

## 8. Mobox 및 Box64 조사 과정

Mobox 저장소:

```text
olegos2/mobox
```

설치한 Wine:

```text
wine-9.3-vanilla-wow64
```

### 원본 Mobox Box64 문제

초기 오류:

```text
taskset: failed to execute .../box64: Permission denied
```

직접 실행 시:

```text
unexpected e_type: 2
```

원본 Box64는 ELF `ET_EXEC`였다.

### 커스텀 Box64 빌드

Box64 최신 소스를 Debian PRoot에서 빌드했다.

주요 CMake 옵션:

```text
-DARM64=ON
-DBAD_SIGNAL=ON
-DNOLOADADDR=ON
-DCMAKE_BUILD_TYPE=RelWithDebInfo
-DCMAKE_POSITION_INDEPENDENT_CODE=ON
-DCMAKE_C_FLAGS=-fPIE
-DCMAKE_EXE_LINKER_FLAGS=-pie
```

처음에는 TLS 정렬 16 때문에 Android Bionic이 거부했다.

```text
executable's TLS segment is underaligned: alignment is 16, needs at least 64
```

다음 TLS 변수와 CMake 연결을 추가해 TLS alignment를 64로 맞췄다.

```c
__thread __attribute__((aligned(64), visibility("hidden")))
unsigned char box64_android_tls_align;
```

최종 ELF 특성:

```text
Type: DYN (Position-Independent Executable file)
TLS alignment: 0x40
```

Android direct launch에서는 glibc loader 문제가 남았지만, Debian PRoot 내부에서는 정상 동작했다.

```text
Box64 arm64 v0.4.3 862fef5 with Dynarec
```

Wine 실행 확인:

```text
wine-9.3
```

즉 Box64와 Wine 바이너리는 Debian PRoot 안에서 실행 가능하다.

---

## 9. Wineboot가 실패했던 원인 추적

초기 Wineboot 오류:

```text
wine: created the configuration directory ...
err:virtual:map_image_into_view failed to set 60500020 protection on
C:\windows\system32\ntdll.dll section .text, noexec filesystem?

err:virtual:virtual_setup_exception stack overflow ...
WINEBOOT_RESULT=1
```

prefix를 Mobox 경로와 Debian `/root` 양쪽에 만들어도 동일했다. 따라서 prefix 파일 위치 문제는 아니었다.

### 배제된 가설

1. 일반적인 filesystem `noexec`
   - ARM64 네이티브에서 anonymous/file-backed `mprotect` 성공

2. 일반 커널 `mprotect` 차단
   - RW→RX, direct RWX, 고정 주소 모두 성공

3. 32비트 호환 매핑 정책
   - `BOX64_MMAP32=0`에서도 동일 실패

4. high address reserve 정책
   - `BOX64_RESERVE_HIGH=1`에서도 동일 실패

5. Box64 libc wrapper와 raw syscall 자체
   - x86-64 테스트 프로그램을 Box64에서 실행
   - libc `mprotect()`와 raw `syscall(SYS_mprotect)` 모두 clean mapping에서 성공

6. 특정 주소 자체
   - `0x7ffff41000`, 길이 `0x74000`에서 clean mapping 성공

### errno 계측

Box64 `my_mprotect()`에 errno 로그를 추가해 실제 실패를 확인했다.

```text
[BOX64_MPROTECT_FAIL] addr=0x7ffff41000 len=0x74000 prot=0x5 errno=13 (Permission denied)
```

`prot=0x5`는 다음이다.

```text
PROT_READ | PROT_EXEC
```

### 최종 원인 확정 테스트

같은 `ntdll.dll`을 같은 주소에 매핑해 비교했다.

Clean:

```text
RW file mapping -> RX
성공
```

Dirty:

```text
RW file mapping
한 바이트 수정 후 원복
RW -> RX
errno=13
```

ARM64 네이티브와 Box64 양쪽에서 동일했다.

따라서 원인은 Box64 변환 버그가 아니라 Android의 dirty private file mapping exec 전환 제한이다.

---

## 10. 현재 Box64 패치 상태

현재 소스:

```text
/root/box64/src/wrapped/wrappedlibc.c
```

현재 빌드 결과:

```text
/root/box64/build/box64
```

적용 스크립트:

```text
BOX64_EXECMOD_PATCH_V3.sh
```

패치 테스트는 성공했다.

```text
[100%] Built target box64
[BOX64_EXECMOD_FALLBACK] success ...
MODE=DIRTY
MPROTECT=0 errno=0
```

현재 패치는 정상 게임이나 XIGNCODE를 우회하는 것이 아니라 Wine PE loader가 Android 메모리 정책과 호환되도록 파일 기반 dirty mapping을 익명 mapping으로 바꾸는 호환성 패치다.

---

## 11. 지금 실행해야 하는 다음 단계

### 단계 A — 실제 Wineboot 재시험

일반 Termux에서 실행한다.

```bash
pkill -f wineserver 2>/dev/null || true
pkill -f wineboot.exe 2>/dev/null || true

ROOT="$PREFIX/glibc"
XSOCK="$TMPDIR/.X11-unix"
OUT="$HOME/storage/downloads/wineboot_execmod_test.txt"

proot-distro login debian \
  --bind "$ROOT:/opt/mobox" \
  --bind "$XSOCK:/tmp/.X11-unix" \
  -- bash -lc '
BOX=/root/box64/build/box64
WROOT=/opt/mobox/wine-9.3-vanilla-wow64
WINE="$WROOT/bin/wine"

export DISPLAY=:0
export XDG_RUNTIME_DIR=/tmp/runtime-box64
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

export WINEPREFIX=/root/.wine-mobox-execmod
export WINEARCH=win64
export WINEDLLOVERRIDES="winemenubuilder.exe=d"
export WINEDEBUG=err+all

export BOX64_LOG=0
export BOX64_NORCFILES=1
export BOX64_MMAP32=0
export BOX64_PATH="$WROOT/bin"
export BOX64_LD_LIBRARY_PATH="$WROOT/lib/wine/x86_64-unix:$WROOT/lib:$WROOT/lib64:/opt/mobox/lib/x86_64-linux-gnu"

rm -rf "$WINEPREFIX"

timeout 180s "$BOX" "$WINE" wineboot -i
RESULT=$?

echo
echo "WINEBOOT_RESULT=$RESULT"
' >"$OUT" 2>&1

echo "=== 핵심 결과 ==="
grep -E 'BOX64_EXECMOD_FALLBACK|WINEBOOT_RESULT|err:' "$OUT" | tail -n 120

echo
echo "전체 로그: $OUT"
```

### 기대 결과

여러 DLL에서 다음 로그가 반복될 수 있다.

```text
[BOX64_EXECMOD_FALLBACK] success
```

최종 목표:

```text
WINEBOOT_RESULT=0
```

### 오래 걸릴 때

명령이 전체 출력을 파일로 보내므로 실행 중 화면에 아무것도 안 보일 수 있다. 최대 180초 기다린다.

별도 Termux 세션에서 상태를 보고 싶으면:

```bash
tail -f ~/storage/downloads/wineboot_execmod_test.txt
```

---

## 12. Wineboot 결과별 다음 행동

### 경우 1 — `WINEBOOT_RESULT=0`

Wine prefix 초기화 성공이다.

그다음 해야 할 일:

1. 패치된 Box64를 사용한 영구 PRoot launcher 작성
2. Termux:X11은 이미 실행 중인 서버를 그대로 사용
3. Android Downloads를 PRoot 안에 bind
4. Wine prefix의 `dosdevices/d:`를 Downloads 경로에 연결
5. Wine explorer 또는 `cmd.exe`로 기본 GUI/배치 실행 확인
6. 공식 인증 bridge 완료 후 `TR_LOGIN_AND_RUN_FIXED.bat` 실행
7. XIGNCODE 단계가 Winlator와 동일한지 확인

예정 bind 예시:

```bash
--bind "$HOME/storage/downloads:/mnt/downloads"
```

예정 Wine drive 연결 예시:

```bash
ln -sfn /mnt/downloads "$WINEPREFIX/dosdevices/d:"
```

이 두 항목은 아직 실제 최종 launcher로 검증하지 않았다. Wineboot 성공 후 새 채팅에서 경로를 확인하고 적용한다.

### 경우 2 — `WINEBOOT_RESULT=1`이고 기존 ntdll 오류가 사라짐

execmod 문제는 해결됐고 다음 Wine 오류로 진행한 것이다.

해야 할 일:

- 전체 로그에서 첫 번째 새로운 `err:`를 기준으로 진단
- 마지막 수십 줄보다 최초 치명 오류를 우선 확인

명령:

```bash
grep -n 'err:' ~/storage/downloads/wineboot_execmod_test.txt | head -n 50
```

### 경우 3 — 여전히 `ntdll.dll section .text` + `errno=13`

패치된 Box64가 실제 Wine 자식 프로세스에 전달되지 않은 것이다.

확인할 것:

- wine 프로세스가 `/root/box64/build/box64`로 시작됐는지
- `posix_spawn`되는 wineserver/wine 자식도 같은 Box64를 쓰는지
- 소스에 `BOX64_EXECMOD_FALLBACK` marker가 있는지
- 빌드 시각이 최신인지

검사:

```bash
grep -n 'BOX64_EXECMOD_FALLBACK' /root/box64/src/wrapped/wrappedlibc.c
/root/box64/build/box64 --version
```

### 경우 4 — timeout 결과 `124`

180초 안에 Wineboot가 끝나지 않은 것이다.

다음 확인:

```bash
tail -n 200 ~/storage/downloads/wineboot_execmod_test.txt
```

그리고 남은 프로세스:

```bash
ps -ef | grep -E 'wine|wineserver|box64' | grep -v grep
```

무작정 timeout을 늘리지 말고 로그에서 멈춘 위치를 먼저 확인한다.

---

## 13. Wineboot 성공 후 최종 실행 흐름

예정 정상 흐름:

1. Termux:X11 서버 실행 유지
2. Android Chrome에서 공식 테일즈런너 Game Start
3. Android URI bridge가 `TRLauncher://...` 수신
4. Termux에서 공식 인증 bridge 실행

```bash
python ~/storage/downloads/TR_KR_LOCAL/TR_AUTH_BRIDGE.py
```

5. 다음 출력 확인

```text
3/3 완료
```

6. Wine 안에서 실행

```text
D:\TR_KR_LOCAL\TR_LOGIN_AND_RUN_FIXED.bat
```

7. XIGNCODE loader 및 실제 게임 프로세스 관찰

Mobox에서도 Winlator와 같은 `E0190204`에 도달하면, 정상 호환성 경로에서의 재현이 확인된 것이다. 그 이후에도 우회는 하지 않고 진단만 한다.

---

## 14. 보안 및 작업 경계

절대 요청하거나 공유하지 않을 것:

- 원문 `TRLauncher://` URI
- 인증 토큰
- 쿠키
- `trlauncher_request.txt` 원문
- `tr_access_token.tmp` 내용

사용할 파일:

```text
TR_LOGIN_AND_RUN_FIXED.bat
```

사용하지 않을 파일:

```text
이전 구버전 로그인 배치
BOX64_EXECMOD_PATCH.sh 구버전
```

하지 않을 작업:

- XIGNCODE 비활성화
- 코드 인젝션
- 드라이버/환경 스푸핑
- 인증 우회
- 실행 파일 변조를 통한 anti-cheat 회피

허용 작업:

- 공식 파일 검증
- 공식 인증 endpoint 사용
- Wine/Box64 런타임 호환성 수정
- 메모리 매핑 및 프로세스 로그 진단
- 공식 게임 실행 결과 관찰

---

## 15. 새 채팅 시작용 문구

새 채팅에서 다음처럼 시작하면 된다.

```text
GitHub의 MS0502/codex 저장소에 있는
TALESRUNNER_ANDROID_MOBOX_HANDOFF_2026-07-13.md를 읽고,
11번 Wineboot 실제 재시험 결과부터 이어서 진행해줘.
XIGNCODE 우회는 하지 말고 Wine/Box64 정상 호환성 진단만 계속해.
```

현재 가장 먼저 전달해야 할 결과는 다음 둘 중 하나다.

```text
WINEBOOT_RESULT=0
```

또는

```text
~/storage/downloads/wineboot_execmod_test.txt의 핵심 오류 부분
```
