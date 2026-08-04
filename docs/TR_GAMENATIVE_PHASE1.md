# TalesRunner GameNative Phase 1 — container stability baseline

## Decision

The primary Android execution platform moves from the custom Winlator APK line to a pinned GameNative source baseline.

This phase does not attempt to run TalesRunner and does not replace the proven Winlator v16 diagnostic evidence. It produces a separately installable GameNative diagnostic APK for physical-device stability testing before any Wine runtime migration.

## Source pin

- upstream repository: `utkarshdalal/GameNative`
- exact commit: `78e9343e1699fe6eeb1156aab69fb6498fd33083`
- upstream version at the pin: `1.1.1`
- target flavor/build type: `modernDebug`
- diagnostic application ID: `app.gamenative.trdiag`
- diagnostic display name: `TR Native Phase 1`

The workflow fetches the exact commit directly and fails closed if `HEAD` differs.

## Inherited evidence, not re-proved here

The existing Winlator diagnostic line remains the comparison baseline:

- v16 / PR #7: official `talesrunner.exe → xldr → trgame.exe` process-chain and lifetime evidence;
- v18J / PR #18: Android native-wrapper dependency closure evidence;
- Wine 11.14 / PR #20: coherent single-source Wine build and ARM64 runtime-gate work.

No conclusion from those branches is silently promoted to GameNative. Phase 2 must reproduce the v16 process behavior on GameNative before Wine 11.14 is introduced.

## Phase 1 modifications

The patcher makes only application-shell changes:

1. changes the Android application ID so it installs beside normal GameNative and all Winlator packages;
2. changes the visible app name to `TR Native Phase 1` in every localized `app_name` resource;
3. adds `BuildConfig.TR_DIAGNOSTIC_BUILD=true`;
4. disables PostHog setup and Play Integrity warm-up only in this diagnostic build;
5. embeds an immutable JSON provenance asset in the APK;
6. adds a unit test proving the diagnostic build flag is enabled.

## Explicit non-changes

Phase 1 does not:

- replace or patch Wine, Proton, FEX, Box64, DXVK, VKD3D, ImageFS or UbuntuFS;
- add TalesRunner files, launch credentials, authentication tokens or game binaries;
- alter Wellbia, XIGNCODE, AppSign, `.xem`, `xhunter1.sys`, device names, services, drivers or IOCTL results;
- fabricate a Windows kernel device or report a security check as successful;
- import an existing Winlator prefix or container.

## CI gates

The build workflow must prove:

- exact GameNative commit pin;
- patcher syntax validity;
- expected and bounded changed-file set;
- no runtime or security-related path was touched;
- GameNative `modernDebug` unit tests pass;
- a `modernDebug` APK builds;
- output metadata reports `app.gamenative.trdiag`;
- the APK contains `assets/tr_native_phase1.json` with unchanged Wine/TalesRunner/XIGNCODE flags;
- APK SHA-256, patch report and complete source diff are published together.

## Physical Z Fold6 gate

Use a fresh installation and do not import old containers for the first run.

Required observations:

1. create three fresh containers;
2. close and reopen each container at least three times;
3. perform twenty rapid folder transitions in the Wine file manager;
4. copy, rename, refresh and delete non-sensitive test files;
5. keep the Wine desktop open for five minutes;
6. switch to another Android app and return ten times;
7. fold and unfold the device during an idle desktop session;
8. record any app crash, ANR, missing file refresh, desktop restart or container corruption.

Phase 1 passes only if the app is materially more stable than the current Winlator experience. Passing this gate says nothing about TalesRunner or XIGNCODE compatibility.

## Next phase after the device gate

Phase 2 will port the low-load v16 observation surface and the same Wine 10.10 baseline into GameNative. The required causal comparison is:

```text
Winlator v16 + Wine 10.10
versus
GameNative Phase 2 + the same Wine 10.10 baseline
```

The expected comparison points are process creation order, process lifetime, exit code, service/driver attempts, `xhunter1` device-open results and redacted Wellbia log bytes. Wine 11.14 work starts only after that baseline is reproduced.
