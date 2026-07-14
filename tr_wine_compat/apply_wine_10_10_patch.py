#!/usr/bin/env python3
from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_wine_10_10_patch.py WINE_SOURCE_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    native = root / "dlls/ntdll/unix/security.c"
    wow64 = root / "dlls/wow64/security.c"

    replace_once(
        native,
        "        0,    /* TokenIsRestricted */\n        0     /* TokenProcessTrustLevel */\n",
        "        0,    /* TokenIsRestricted */\n        0,    /* TokenProcessTrustLevel */\n        sizeof(DWORD) /* TokenPrivateNameSpace */\n",
    )
    replace_once(
        native,
        "    if (class < MaxTokenInfoClass) len = info_len[class];\n",
        "    if (class < ARRAY_SIZE(info_len)) len = info_len[class];\n",
    )
    replace_once(
        native,
        "    case TokenLinkedToken:\n",
        "    case TokenPrivateNameSpace:\n"
        "        /* A normal desktop process token is not in a private namespace. */\n"
        "        if (!info) return STATUS_ACCESS_VIOLATION;\n"
        "        *(DWORD *)info = 0;\n"
        "        TRACE(\"QueryInformationToken( ..., TokenPrivateNameSpace, ...) returning FALSE\\n\");\n"
        "        break;\n\n"
        "    case TokenLinkedToken:\n",
    )
    replace_once(
        wow64,
        "    case TokenIsAppContainer:  /* ULONG */\n        /* nothing to map */\n",
        "    case TokenIsAppContainer:  /* ULONG */\n"
        "    case TokenPrivateNameSpace:  /* ULONG */\n"
        "        /* nothing to map */\n",
    )

    print("Wine 10.10 TokenPrivateNameSpace compatibility patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
