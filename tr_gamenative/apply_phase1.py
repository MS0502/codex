#!/usr/bin/env python3
"""Apply the TalesRunner GameNative phase-1 diagnostic branding and safety patch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

EXPECTED_GAMENATIVE_COMMIT = "78e9343e1699fe6eeb1156aab69fb6498fd33083"
APPLICATION_ID = "app.gamenative.trdiag"
DISPLAY_NAME = "TR Native Phase 1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_first(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"{label}: anchor not found")
    return text.replace(old, new, 1)


def verify_source(root: Path) -> str:
    required = [
        root / "app/build.gradle.kts",
        root / "app/src/main/java/app/gamenative/PluviaApp.kt",
        root / "app/src/main/res/values/strings.xml",
        root / "gradlew",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"GameNative source is incomplete: {missing}")

    git_dir = root / ".git"
    if not git_dir.exists():
        raise RuntimeError("GameNative checkout must retain .git for source-pin verification")
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if head != EXPECTED_GAMENATIVE_COMMIT:
        raise RuntimeError(
            f"unexpected GameNative HEAD: {head}; expected {EXPECTED_GAMENATIVE_COMMIT}"
        )
    return head


def patch_gradle(root: Path) -> Path:
    path = root / "app/build.gradle.kts"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'applicationId = "app.gamenative"',
        f'applicationId = "{APPLICATION_ID}"',
        label="applicationId",
    )
    text = replace_once(
        text,
        '        buildConfigField("boolean", "MODERN_XR", "false")\n',
        '        buildConfigField("boolean", "MODERN_XR", "false")\n'
        '        buildConfigField("boolean", "TR_DIAGNOSTIC_BUILD", "true")\n',
        label="diagnostic build flag",
    )
    text = replace_first(
        text,
        '            signingConfig = signingConfigs.getByName("debug")\n',
        '            signingConfig = signingConfigs.getByName("debug")\n'
        '            versionNameSuffix = "-trdiag-p1"\n',
        label="debug version suffix",
    )
    path.write_text(text, encoding="utf-8")
    return path


def patch_application_startup(root: Path) -> Path:
    path = root / "app/src/main/java/app/gamenative/PluviaApp.kt"
    text = path.read_text(encoding="utf-8")
    old = '''        // Initialize PostHog Analytics
        val postHogConfig = PostHogAndroidConfig(
            apiKey = BuildConfig.POSTHOG_API_KEY,
            host = BuildConfig.POSTHOG_HOST,
        ).apply {
            /* turn every event into an identified one */
            personProfiles = PersonProfiles.ALWAYS
        }
        PostHogAndroid.setup(this, postHogConfig)
        com.posthog.PostHog.register("build_flavor", BuildConfig.FLAVOR)

        if (PrefManager.usageAnalyticsEnabled) {
            com.posthog.PostHog.capture(
                event = "\\$set",
                properties = mapOf(
                    "\\$set" to mapOf("recommendation_enabled" to PrefManager.showRecommendations),
                ),
            )
        }

        PlayIntegrity.warmUp(this)
'''
    new = '''        if (!BuildConfig.TR_DIAGNOSTIC_BUILD) {
            // Initialize PostHog Analytics only in normal GameNative builds.
            val postHogConfig = PostHogAndroidConfig(
                apiKey = BuildConfig.POSTHOG_API_KEY,
                host = BuildConfig.POSTHOG_HOST,
            ).apply {
                personProfiles = PersonProfiles.ALWAYS
            }
            PostHogAndroid.setup(this, postHogConfig)
            com.posthog.PostHog.register("build_flavor", BuildConfig.FLAVOR)

            if (PrefManager.usageAnalyticsEnabled) {
                com.posthog.PostHog.capture(
                    event = "\\$set",
                    properties = mapOf(
                        "\\$set" to mapOf("recommendation_enabled" to PrefManager.showRecommendations),
                    ),
                )
            }

            PlayIntegrity.warmUp(this)
        } else {
            Timber.i("[TR Native Phase 1] External analytics and Play Integrity warm-up disabled")
        }
'''
    text = replace_once(text, old, new, label="diagnostic startup isolation")
    path.write_text(text, encoding="utf-8")
    return path


def patch_display_names(root: Path) -> list[Path]:
    changed: list[Path] = []
    pattern = re.compile(r'<string name="app_name">.*?</string>')
    for path in sorted((root / "app/src/main/res").glob("values*/strings.xml")):
        text = path.read_text(encoding="utf-8-sig")
        updated, count = pattern.subn(
            f'<string name="app_name">{DISPLAY_NAME}</string>', text, count=1
        )
        if count != 1:
            raise RuntimeError(f"{path}: expected one app_name resource, found {count}")
        path.write_text(updated, encoding="utf-8")
        changed.append(path)
    if not changed:
        raise RuntimeError("no localized strings.xml files were patched")
    return changed


def add_diagnostic_assets(root: Path, source_head: str) -> list[Path]:
    asset_path = root / "app/src/main/assets/tr_native_phase1.json"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset = {
        "phase": 1,
        "purpose": "GameNative container stability baseline before TalesRunner runtime migration",
        "gamenative_commit": source_head,
        "application_id": APPLICATION_ID,
        "display_name": DISPLAY_NAME,
        "analytics_enabled": False,
        "play_integrity_warmup_enabled": False,
        "wine_runtime_changed": False,
        "talesrunner_changed": False,
        "xigncode_changed": False,
        "security_result_fabricated": False,
    }
    asset_path.write_text(json.dumps(asset, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    test_path = root / "app/src/test/java/app/gamenative/TrDiagnosticBuildConfigTest.kt"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(
        '''package app.gamenative

import org.junit.Assert.assertTrue
import org.junit.Test

class TrDiagnosticBuildConfigTest {
    @Test
    fun diagnosticBuildFlagIsEnabled() {
        assertTrue(BuildConfig.TR_DIAGNOSTIC_BUILD)
    }
}
''',
        encoding="utf-8",
    )
    return [asset_path, test_path]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    root = args.source_root.resolve()
    source_head = verify_source(root)
    changed: list[Path] = []
    changed.append(patch_gradle(root))
    changed.append(patch_application_startup(root))
    changed.extend(patch_display_names(root))
    changed.extend(add_diagnostic_assets(root, source_head))

    report = {
        "schema": 1,
        "phase": 1,
        "gamenative_commit": source_head,
        "application_id": APPLICATION_ID,
        "display_name": DISPLAY_NAME,
        "modified_files": [
            {
                "path": str(path.relative_to(root)),
                "sha256": sha256_file(path),
            }
            for path in sorted(set(changed))
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
