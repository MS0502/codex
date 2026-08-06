# XIGNCODE static/runtime boundary — 2026-08-06

## Scope and safety

This report records structural PE metadata and observed Wine API/file activity. It does not decrypt, unpack, patch, bypass, or fabricate any protected module, driver, service, device, IOCTL, authentication result, or security result.

## Input set

Archive SHA-256:

`3eb242228f46a33170ba366bfc61eb5c7d726034547f6b8c8c848a11ce97fa5a`

Files:

| File | Size | SHA-256 | Top-level classification |
|---|---:|---|---|
| `xldr_TalesRunner_KR_loader_x64.exe` | 12,061,984 | `d899b5a9ffc95333f1646cf79717577c7d28195857720553e0f65017ab3578f6` | x86-64 PE GUI image |
| `x3_x64.xem` | 6,413,392 | `76dbe22218bbc8d9239d54848ee9c86fe045fbc4e5cd3fc361f0488c872fc632` | x86-64 PE DLL |
| `xcorona_x64.xem` | 7,156,336 | `f761111aa587107c528707a518f8a6c9fbb874d6229700d34a43f994abec0753` | x86-64 PE DLL |
| `xmag_x64.xem` | 12,144,640 | `f92310a0a67795f1438ecb13e51710886f3e815fb5820c4ad987418e0ab7a902` | non-PE data at offset zero |
| `xnina_x64.xem` | 1,667,072 | `62bc825d8d0b2f6efe3164b283cdcd8038368ae2801c89ec461fd9b2dd8d79e7` | non-PE data at offset zero |

## Validated embedded-PE scan

A candidate was accepted only when all of the following held:

1. `MZ` at the candidate offset;
2. in-range DOS `e_lfanew`;
3. `PE\0\0` at the calculated offset;
4. valid PE32 or PE32+ optional-header magic;
5. plausible section count and section table;
6. every raw section range inside the containing file.

Results:

| File | Valid PE candidates |
|---|---:|
| `xldr_TalesRunner_KR_loader_x64.exe` | 1, at offset 0 |
| `x3_x64.xem` | 1, at offset 0 |
| `xcorona_x64.xem` | 2: top-level x64 DLL and a protected 32-bit GUI image at `0x38b24` |
| `xmag_x64.xem` | 0 |
| `xnina_x64.xem` | 0 |

Raw counts of the byte strings `MZ` or `PE\0\0` are therefore not evidence of embedded driver images.

## Service-control capability present in `x3_x64.xem`

The normal PE import table of `x3_x64.xem` includes:

- `OpenSCManagerW`
- `CreateServiceW`
- `OpenServiceW`
- `OpenServiceA`
- `StartServiceW`
- `ControlService`
- `QueryServiceStatusEx`
- `AdjustTokenPrivileges`
- service-registry creation/query/write functions
- `CreateFileW`, `WriteFile`, temporary/system-directory and setup-device APIs

This proves that the x3 module contains or links to general service-management capability. It does not prove which service it manages or that it contains a driver payload.

## v29 runtime correlation

The authenticated v29 trace showed:

- `x3_x64.xem` file access or mapping: 0
- `xcorona_x64.xem` file access or mapping: 0
- `xmag_x64.xem` file access or mapping: 0
- `xnina_x64.xem` file access or mapping: 0
- protected-service `CreateService/OpenService/StartService`: 0
- protected-driver `ZwLoadDriver/DriverEntry/IoCreateDevice`: 0
- `\\??\\xhunter1` open attempts: present
- game process later exits with `-1`

Wine's normal service and native-driver loading traces were active and successfully recorded the standard Wine drivers, so the absence above is not caused by a disabled trace channel.

## Exact boundary

The service-management code statically present in `x3_x64.xem` did not execute in the observed launch because the x3 image was never opened or mapped. The observed loader path directly attempted to open an already-existing device object and then launched the game image.

This report does **not** claim why the closed-source loader omitted x3. Candidate explanations remain unproven until module-loading, version/environment queries, and service calls are correlated in one focused trace.
