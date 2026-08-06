#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_v29_patch as base

REVISION = "v29-korean-env-anchor-2"


def patch_activity(root: Path) -> None:
    activity = root / "app/src/main/java/com/winlator/XServerDisplayActivity.java"
    base.replace_once(
        activity,
        "import com.winlator.core.TrCompatNtKernelPatcher;\n",
        "import com.winlator.core.TrCompatNtKernelPatcher;\nimport com.winlator.core.TrCompatKoreanSupport;\n",
    )
    base.replace_once(
        activity,
        '''            TrCompatNtKernelPatcher.apply(this, rootFS);\n            trTrace("NTOSKRNL_PATCH_RETURN");\n''',
        '''            TrCompatKoreanSupport.apply(this, rootFS);\n            trTrace("KOREAN_SUPPORT_RETURN");\n            TrCompatNtKernelPatcher.apply(this, rootFS);\n            trTrace("NTOSKRNL_PATCH_RETURN");\n''',
    )

    # v15 and later deliberately force both Wine synchronization backends off.
    # Insert the locale immediately before that exact, already-validated block
    # instead of expecting the untouched upstream WINEESYNC default.
    base.replace_once(
        activity,
        '''            envVars.put("WINEESYNC", "0");\n            envVars.put("WINEFSYNC", "0");\n''',
        '''            if (!envVars.has("LANG")) envVars.put("LANG", "ko_KR.UTF-8");\n            if (!envVars.has("LC_ALL")) envVars.put("LC_ALL", "ko_KR.UTF-8");\n            trTrace("KOREAN_ENV LANG="+envVars.get("LANG")+" LC_ALL="+envVars.get("LC_ALL"));\n            envVars.put("WINEESYNC", "0");\n            envVars.put("WINEFSYNC", "0");\n''',
    )

    text = activity.read_text(encoding="utf-8")
    for marker in (
        "TrCompatKoreanSupport.apply(this, rootFS)",
        'envVars.put("LANG", "ko_KR.UTF-8")',
        'envVars.put("LC_ALL", "ko_KR.UTF-8")',
        'envVars.put("WINEESYNC", "0")',
        'envVars.put("WINEFSYNC", "0")',
    ):
        if text.count(marker) != 1:
            raise RuntimeError(f"{REVISION}: expected one activity marker: {marker}")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: apply_v29_patch_v2.py WINLATOR_APP_DIR COMPONENT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    component_dir = Path(sys.argv[2]).resolve()

    ntoskrnl_hash = base.install_ntoskrnl_asset(root, component_dir)
    locale_hash = base.build_korean_locale_asset(root)
    base.update_ntoskrnl_patcher(root, ntoskrnl_hash)
    base.write_korean_support(root)
    patch_activity(root)
    base.patch_metadata_and_diagnostics(root)
    base.write_report(root, ntoskrnl_hash, locale_hash)

    print(
        f"Applied {REVISION}: ntoskrnl={ntoskrnl_hash} locale={locale_hash}; "
        "existing forced sync behavior retained."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
