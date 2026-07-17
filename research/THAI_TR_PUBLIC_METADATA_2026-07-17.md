# Thai TalesRunner public client metadata — 2026-07-17

## Scope

This report uses only current public packages linked by the official Thai publisher download page. Packages were downloaded and extracted without execution. No game, XIGNCODE, `.xem`, `.sys`, or executable binaries were committed or uploaded; only metadata reports were retained.

## Official source packages

- Mini client entry: `https://talesrunner.gg/download-Minizip`
  - Final CDN object: `https://cdn.talesrunner.gg/setup/zip/Mini_Talesrunner1.5.zip`
  - Size: `84,089,526` bytes
  - SHA-256: `fc6775b12cb5a218d3241cbb0aa8ce09b6c614c76ccfc4d5294828615d15c0c2`
- Installer entry: `https://talesrunner.gg/download-fullclient`
  - Final CDN object: `https://cdn.talesrunner.gg/setup/installer/Talesrunner_TH_260225_Minimum_ver1.5.msi`
  - Size: `86,110,208` bytes
  - SHA-256: `d2e044f9ca065fb15152bf84b36634a7200de4c5228f81713ad5b24ef597cf02`
  - MSI last-saved timestamp: `2026-02-25 05:55:42 UTC`
  - MSI template: `x64;1033`

## Thai 2026 XIGNCODE inventory from official Mini Zip

| File | Size | SHA-256 | Architecture / metadata |
|---|---:|---|---|
| `x3.xem` | 3,730,408 | `b421f4ed073f686128d283c35cd40744f2aa625020fc8706e7236b63498b23c8` | x86, FileVersion `2024.4.24.220`, ProductVersion `3.5.0.63` |
| `x3_x64.xem` | 6,426,912 | `6a8e373d7c10060f8612bb0f9a0d13a1c3de73ebd9b73f89d50df30ce673fad7` | x64, FileVersion `2024.4.24.220`, ProductVersion `3.5.0.63` |
| `xcorona.xem` | 6,529,880 | `798b1568e6ce197071b771fe897870c04bddf75279382ec00f7cc9128f330de8` | x86, FileVersion `2024.4.24.220`, ProductVersion `5.0.0.0` |
| `xcorona_x64.xem` | 6,973,552 | `f082c98677ea4b6a2088fb74906ab798e1d9ad58c51f66d783bcdfaa599526b7` | x64, FileVersion `2024.4.24.220`, ProductVersion `5.0.0.0` |
| `xcorona_arm64.xem` | 12,389,160 | `e49c7c79a6612acd2f47929a89cb66c4ae847705f042d1bb6c0205188e0d7062` | ARM64, FileVersion `2024.4.24.220`, ProductVersion `5.0.0.0` |
| `xnina.xem` | 1,777,664 | `59e781ef16cfdb01f79d34291045c80358eda2de9e2da8593be9a1802cbdb56d` | x86 data/protected module |
| `xnina_x64.xem` | 2,031,616 | `6dcf873c19259ee8da533bef1a604f728812ed5cc9de288bb37368ba1ed5dae0` | x64 data/protected module |
| `xldr_TalesRunner_TH_loader_x64.exe` | 12,104,544 | `1c173d8e6490f81b35f0c199195cd0ef6ef88ecf5a0671d03e9dca92f0aa0ad9` | x64, FileVersion `2025.3.27.39`, ProductVersion `5.0.0.1` |

The Thai loader is described as `Wellbia.com Security Loader`, original filename `wldr.exe`, and is signed by Wellbia.com Co., Ltd. The extracted Thai package contains no `xmag*.xem` file.

## Thai game executables

- `talesrunner.exe`
  - Size: `3,615,080`
  - SHA-256: `4a01ba06f9a381b5340aeff59f913a132f7fa30e8d6048e64eab95c331b7e014`
  - x64, FileVersion/ProductVersion `3.6.0.12`
  - Rhaon signature timestamp: `2025-10-13 05:05:12 UTC`
- `trgame.exe`
  - Size: `29,231,464`
  - SHA-256: `af47fbdd4fa332d2d76124f8a82f192987a5e3c78c77b967cb8e9b3732ffa9dc`
  - x64, FileVersion/ProductVersion `1.1.336.1`
  - Description: `Talesrunner R181914`
  - Rhaon signature timestamp: `2026-02-12 06:51:02 UTC`

## Comparison with the user's current Korean client

| Module | Korean client | Thai 2026 client | Match |
|---|---|---|---|
| `x3_x64.xem` | 6,413,392 bytes, `76dbe22218bbc8d9239d54848ee9c86fe045fbc4e5cd3fc361f0488c872fc632` | 6,426,912 bytes, `6a8e373d7c10060f8612bb0f9a0d13a1c3de73ebd9b73f89d50df30ce673fad7` | No |
| `xcorona_x64.xem` | 7,156,336 bytes, `f761111aa587107c528707a518f8a6c9fbb874d6229700d34a43f994abec0753` | 6,973,552 bytes, `f082c98677ea4b6a2088fb74906ab798e1d9ad58c51f66d783bcdfaa599526b7` | No |
| `xnina_x64.xem` | 1,667,072 bytes, `62bc825d8d0b2f6efe3164b283cdcd8038368ae2801c89ec461fd9b2dd8d79e7` | 2,031,616 bytes, `6dcf873c19259ee8da533bef1a604f728812ed5cc9de288bb37368ba1ed5dae0` | No |
| game-specific loader | `xldr_TalesRunner_KR_loader_x64.exe`, 12,061,984 bytes, `d899b5a9ffc95333f1646cf79717577c7d28195857720553e0f65017ab3578f6` | `xldr_TalesRunner_TH_loader_x64.exe`, 12,104,544 bytes, `1c173d8e6490f81b35f0c199195cd0ef6ef88ecf5a0671d03e9dca92f0aa0ad9` | No |
| additional policy module | Korean has `xmag_x64.xem`, 12,144,640 bytes, `f92310a0a67795f1438ecb13e51710886f3e815fb5820c4ad987418e0ab7a902` | Thai package has no `xmag*.xem` | Different |
| 32-bit companion modules | Not present in current Korean fingerprint | Thai has `x3.xem`, `xcorona.xem`, `xnina.xem` | Different |
| ARM64 companion module | Not present in current Korean fingerprint | Thai has `xcorona_arm64.xem` | Different |

## Evidence-based interpretation

1. The current Thai and Korean distributions do not use the same XIGNCODE file set or the same game-specific loader binary.
2. The Thai package is not merely the Korean package with another launcher or language. Its XIGNCODE module composition and hashes are materially different.
3. A Thai Winlator success case therefore cannot yet be attributed to one Wine setting alone. The Thai game-specific XIGNCODE profile/module generation is a plausible causal difference.
4. Foreign `.xem` or loader files must not be copied into the Korean client. They are game/region-specific, signed, hash-checked, and likely tied to server-side policy.
5. The highest-value safe next comparison is runtime A/B logging of the unmodified official Thai client against the unmodified Korean client under the same Wine/Box64 environment, recording only process/module/file/service/device outcomes and exit codes.
6. Public searching has not yet produced a reliable, reproducible Thai Winlator success log that identifies the exact client build, Wine build, settings, and whether the user reached an authenticated game session. That success claim remains unverified until such evidence is located or reproduced.
