# Winlator TR Compat v17 한국·태국 런타임 A/B 실행 절차

## 목적

동일한 APK, 공식 Winlator 11.1 Wine 10.10 기준선, Box64 설정, 새 prefix와 진단 수준에서 공식 한국판과 공식 태국판의 런타임 차이를 분리한다.

이 빌드는 게임·XIGNCODE·인증 파일을 수정하지 않으며, `xhunter1` 장치 응답이나 보안 결과를 위조하지 않는다.

## 고정 폴더

```text
한국: /storage/emulated/0/Download/TR_KR_LOCAL
태국: /storage/emulated/0/Download/TR_TH_LOCAL

Wine:
D:\TR_KR_LOCAL
D:\TR_TH_LOCAL
```

두 지역 파일을 서로 복사하거나 한 폴더에 혼합하지 않는다.

## 컨테이너

한국과 태국에 각각 새 컨테이너를 만든다. 두 컨테이너는 다음 설정을 동일하게 유지한다.

```text
Wine: v12 공식 Wine 10.10 기준선
Windows version: Windows 10
Box64 preset: 동일 값
그래픽 드라이버와 DX wrapper: 동일 값
CPU affinity: 동일 값
WINEESYNC=0
WINEFSYNC=0
```

기존 한국 v16 컨테이너를 태국 시험에 재사용하지 않는다.

## 실행 순서

1. v17 APK 설치 후 한국용 새 컨테이너를 만든다.
2. 한국 공식 실행 배치를 한 번 실행한다.
3. 오류 창이나 종료가 확인되면 10초 정도 기다린 뒤 진단 ZIP을 보존한다.
4. ZIP 이름을 `TR_DIAG_v17_REGION_AB_KR.zip`으로 복사한다.
5. 태국용 새 컨테이너를 만든다.
6. 태국 공식 런처 또는 공식 실행 진입점을 실행한다.
7. 로그인 없이 xldr 초기화까지 진행된다면 그 단계만으로도 1차 비교 자료가 된다.
8. 오류 창이나 종료가 확인되면 10초 정도 기다린 뒤 진단 ZIP을 보존한다.
9. ZIP 이름을 `TR_DIAG_v17_REGION_AB_TH.zip`으로 복사한다.

인증 토큰, 쿠키, 로그인 문자열은 채팅이나 GitHub에 올리지 않는다.

## 수집 파일

```text
/storage/emulated/0/Documents/Winlator/TR_DIAG_v17_REGION_AB.zip
```

ZIP 내부 핵심 파일:

```text
startup_trace.txt
process_lifetime.txt
module_maps.txt
xign_fingerprint.txt
wellbia_lowload.txt
```

## 1차 비교 항목

```text
talesrunner.exe 생성 시각
xldr 생성 시각과 파일명
trgame.exe 생성 시각
각 프로세스 종료 시각과 exit code
self terminate 여부
\\.\xhunter1 조회와 반환 상태
x3/xcorona/xmag/xnina 매핑 여부
서비스·드라이버 생성 또는 로드 시도
WELLBIA 로그 생성 시각·크기·오류 키워드
화면에 표시된 오류 코드
```

## 해석

- 태국판도 한국판과 거의 같은 시간과 종료 코드로 끝나면 공통 Wine 환경 또는 공통 `xhunter1` 의존 가능성이 커진다.
- 태국판의 trgame가 더 오래 생존하거나 `xhunter1` 조회 패턴이 다르면 지역별 XIGNCODE 모듈·정책 차이가 강한 단서다.
- 태국판만 서비스나 드라이버 등록을 시도하면 설치·패처 사전 프로비저닝 차이를 우선 조사한다.
- 태국판이 xldr 또는 trgame에 도달하지 못하면 인증·런처 진입 차이와 보호 초기화 차이를 분리해 해석한다.
