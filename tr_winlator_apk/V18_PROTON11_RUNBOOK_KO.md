# Winlator TR Compat v18 Proton Wine 11 통합 실행 절차

## 목적

공식 Winlator 11.1 앱 구조와 기존 별도 패키지/rootfs 경로 보정을 유지하면서 `/opt/wine` 전체를 하나의 Proton Wine 11 x86_64 배포 트리로 교체해 한국 테일즈런너 실행을 비교한다.

이 빌드는 `ntdll`, `wow64`, `wineserver`, `ntoskrnl`, `winedevice` 및 Wine DLL을 같은 배포 트리에서 사용한다. 게임 파일, 로그인 정보, XIGNCODE 모듈, `xhunter1` 장치 응답 또는 보안 결과는 수정하지 않는다.

## 설치 전

1. 기존 TR Compat의 필요한 진단 ZIP과 화면 캡처를 Download에 보존한다.
2. v18 APK의 SHA256을 확인한다.
3. 기존 TR Compat 앱을 삭제한 뒤 v18을 새로 설치한다. 기존 앱 데이터 위에 덮어쓰지 않는다.
4. 공식 Winlator 앱은 삭제하지 않는다.

## 새 컨테이너

다음 설정으로 `TR_KR_V18` 새 컨테이너를 만든다.

- Wine: Wine 11.0 (Custom)
- Windows: Windows 10
- 해상도: 1280×1024
- Graphics: Turnip + Gladio
- DX Wrapper: DXVK + VKD3D
- Audio: ALSA
- Startup Selection: Essential
- Box64 Preset: Intermediate
- CPU: CPU0–CPU7

기존 v12/v17 컨테이너를 가져오거나 복제하지 않는다.

## 실행

1. 컨테이너를 완전히 종료한 상태에서 다시 연다.
2. 컨테이너가 열린 뒤 가능한 한 바로 한국판 로그인·실행 배치 `TR_LOGIN_AND_RUN_FIXED.bat`를 실행한다.
3. 오류창, XIGNCODE 화면 또는 아무 반응이 없는 상태를 캡처한다.
4. 게임 프로세스가 종료된 것으로 보인 뒤 30초 기다린다.

## 로그 보존

Termux에서 실행한다.

```bash
cp /storage/emulated/0/Documents/Winlator/TR_DIAG_v18_PROTON11.zip \
   /storage/emulated/0/Download/TR_DIAG_v18_PROTON11_KR.zip

ls -lh /storage/emulated/0/Download/TR_DIAG_v18_PROTON11_KR.zip
sha256sum /storage/emulated/0/Download/TR_DIAG_v18_PROTON11_KR.zip
```

파일이 없으면 다음으로 위치를 확인한다.

```bash
find /storage/emulated/0/Documents/Winlator -maxdepth 2 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' | sort
```

## 판정 기준

v12 공식 Wine 10.10 기준선과 비교한다.

- `talesrunner.exe → xldr → trgame.exe` 생성 여부
- XIGNCODE UI 또는 오류 코드 표시 여부
- `trgame.exe` 생존 시간과 종료 코드 변화
- 서비스·드라이버 초기화 경로 진입 여부
- Wine 런타임 자체의 시작 실패 여부

한국 파일만 사용한다. 태국 파일이나 다른 게임의 XIGNCODE 파일을 복사하지 않는다.
