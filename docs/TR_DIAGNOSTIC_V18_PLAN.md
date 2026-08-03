# TalesRunner Diagnostic v18

## 목적

현재 한국판 `trgame.exe`를 기준으로 단 한 번의 공식 실행을 관찰한다. 다음을 증거로 남긴다.

- 실행 직전 `trgame.exe` SHA-256 검증
- 공식 `talesrunner.exe → xldr_TalesRunner_KR_loader_x64.exe → trgame.exe` 경로 유지
- WELLBIA 로그 원본의 실행 전후 바이트 수집
- 가능한 경우 Winlator UID에서 관련 프로세스의 `/proc/<pid>/maps` 수집
- 텍스트 결과의 인증키·토큰 자동 제거
- 업로드 가능한 단일 ZIP 생성

## 고정 기준

```text
trgame.exe
size: 48,007,528
sha256: 35403c283d7a2e28cc9bffc833bf14742c482c742d51760ac52b02a8fced5e61
```

해시가 다르면 수집기는 실행을 중단한다. 다른 게임 빌드 결과를 v16/v17과 잘못 비교하지 않기 위한 fail-closed 조건이다.

## 구성

- Android 동반 앱: 수집기 파일 배치, Termux 실행 요청, Winlator 실행
- Termux 수집기: 해시 검증, 기기·패키지 정보, 선택적 `run-as` 프로세스 맵, 결과 정리·비밀값 제거·ZIP 생성
- Wine 내부 BAT: 기존 공식 로그인 BAT 호출 전후의 WELLBIA 로그와 Windows 프로세스 목록 수집
- GitHub Actions: debug APK 빌드 및 SHA-256 artifact 발행

## 예상 사용자 조작

1. APK에서 `수집기 파일 설치`
2. APK에서 `Termux 수집 시작`
3. Winlator에서 공유 폴더의 `TR_DIAG_V18_WINDOWS.bat` 한 번 실행
4. Termux가 만든 ZIP 업로드

Termux 외부 실행이 차단돼 있으면 `~/.termux/termux.properties`의 `allow-external-apps=true` 설정과 Android의 `RUN_COMMAND` 권한이 필요하다.

## 제한

- 설치된 Winlator가 `debuggable=false`이면 Android의 `run-as`를 통한 프로세스 맵은 수집할 수 없다. 이 경우에도 Wine 내부 BAT가 WELLBIA 로그 원본을 공유 저장소로 복사한다.
- 이 도구는 AppSign/XIGNCODE/Wellbia를 비활성화·위조·우회하지 않는다.
- 로그인 정보나 임시 인증값은 결과 ZIP에 보존하지 않는다.
