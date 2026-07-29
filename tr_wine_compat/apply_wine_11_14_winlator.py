#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

EXPECTED_HEAD = "1012f3d99507b80d4869eabf0853567660a7ecbb"
MONITOR_COMPAT_ANCHOR = "'timeout 90 /work/wine-stage/opt/wine/bin/wineboot -u': 'timeout --signal=TERM --kill-after=10 300 /work/wine-stage/opt/wine/bin/wineboot -u'"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one anchor, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def validate_source(root: Path) -> None:
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != EXPECTED_HEAD:
        raise RuntimeError(f"unexpected Wine source head: {head}")

    required = {
        "server/request.c": [
            "#ifdef __ANDROID__  /* there's no /tmp dir on Android */",
            'if (asprintf( &base_dir, "/tmp/.wine-%u", getuid() ) == -1)',
        ],
        "dlls/ntdll/unix/server.c": [
            "#ifdef __ANDROID__  /* there's no /tmp dir on Android */",
            'asprintf( &dir, "/tmp/.wine-%u/server-%llx-%llx"',
        ],
        "dlls/nsiproxy.sys/nsi.c": [
            "#if defined(HAVE_LINUX_RTNETLINK_H) || defined(__APPLE__)",
        ],
        "dlls/ntdll/unix/security.c": [
            "        0     /* TokenProcessTrustLevel */",
            "    if (class < MaxTokenInfoClass) len = info_len[class];",
            "    case TokenLinkedToken:\n",
        ],
        "dlls/wow64/security.c": [
            "    case TokenIsAppContainer:  /* ULONG */\n",
        ],
        "dlls/winex11.drv/window.c": [
            "    data->managed = is_window_managed( data->hwnd, SWP_NOACTIVATE, FALSE );\n"
            "    mask = get_window_attributes( data, &attr ) | CWOverrideRedirect;\n"
            "    attr.override_redirect = !data->managed;\n",
            "    data->desired_state.rect = data->current_state.rect;\n",
        ],
    }
    for rel, needles in required.items():
        text = (root / rel).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                raise RuntimeError(f"source anchor missing in {rel}: {needle}")


def patch_wineserver_paths(root: Path) -> None:
    request = root / "server/request.c"
    client = root / "dlls/ntdll/unix/server.c"

    request_old = "\n".join([
        "#ifdef __ANDROID__  /* there's no /tmp dir on Android */",
        "    if (asprintf( &base_dir, \"%s/.wineserver\", config_dir ) == -1)",
        "        fatal_error( \"out of memory\\n\" );",
        "#else",
        "    if (asprintf( &base_dir, \"/tmp/.wine-%u\", getuid() ) == -1)",
        "        fatal_error( \"out of memory\\n\" );",
        "#endif",
    ])
    request_new = "\n".join([
        "/* Winlator runs the glibc Wine build inside an Android app sandbox. */",
        "    if (asprintf( &base_dir, \"%s/.wineserver\", config_dir ) == -1)",
        "        fatal_error( \"out of memory\\n\" );",
    ])

    client_old = "\n".join([
        "#ifdef __ANDROID__  /* there's no /tmp dir on Android */",
        "    asprintf( &dir, \"%s/.wineserver/server-%llx-%llx\", config_dir, (unsigned long long)dev, (unsigned long long)ino );",
        "#else",
        "    asprintf( &dir, \"/tmp/.wine-%u/server-%llx-%llx\", getuid(), (unsigned long long)dev, (unsigned long long)ino );",
        "#endif",
    ])
    client_new = "\n".join([
        "/* Match the Android-safe wineserver location under WINEPREFIX. */",
        "    asprintf( &dir, \"%s/.wineserver/server-%llx-%llx\", config_dir, (unsigned long long)dev, (unsigned long long)ino );",
    ])

    replace_once(request, request_old, request_new)
    replace_once(client, client_old, client_new)


def patch_android_nsi(root: Path) -> None:
    nsi = root / "dlls/nsiproxy.sys/nsi.c"
    replace_once(
        nsi,
        "#if defined(HAVE_LINUX_RTNETLINK_H) || defined(__APPLE__)",
        "/* Android app sandboxes reject the Linux multicast netlink bind.\n"
        " * Enumeration stays active; asynchronous notifications use Wine's\n"
        " * existing unsupported path instead of reporting fake success. */\n"
        "#if defined(__APPLE__)",
    )


def patch_token_private_namespace(root: Path) -> None:
    security = root / "dlls/ntdll/unix/security.c"
    wow64 = root / "dlls/wow64/security.c"

    replace_once(
        security,
        "        0     /* TokenProcessTrustLevel */",
        "        0,    /* TokenProcessTrustLevel */\n"
        "        sizeof(DWORD) /* TokenPrivateNameSpace */",
    )
    replace_once(
        security,
        "    if (class < MaxTokenInfoClass) len = info_len[class];",
        "    if (class < ARRAY_SIZE(info_len)) len = info_len[class];",
    )
    replace_once(
        security,
        "    case TokenLinkedToken:\n",
        "    case TokenPrivateNameSpace:\n"
        "        /* Native Windows reports FALSE for an ordinary desktop token. */\n"
        "        if (!info) return STATUS_ACCESS_VIOLATION;\n"
        "        *(DWORD *)info = 0;\n"
        "        TRACE(\"TokenPrivateNameSpace returning FALSE\\n\");\n"
        "        break;\n\n"
        "    case TokenLinkedToken:\n",
    )
    replace_once(
        wow64,
        "    case TokenIsAppContainer:  /* ULONG */\n",
        "    case TokenIsAppContainer:  /* ULONG */\n"
        "    case TokenPrivateNameSpace:  /* ULONG */\n",
    )


def patch_override_redirect_creation(root: Path) -> None:
    window = root / "dlls/winex11.drv/window.c"
    replace_once(
        window,
        "    data->managed = is_window_managed( data->hwnd, SWP_NOACTIVATE, FALSE );\n"
        "    mask = get_window_attributes( data, &attr ) | CWOverrideRedirect;\n"
        "    attr.override_redirect = !data->managed;\n",
        "    /*\n"
        "     * Creating the X window with override-redirect already enabled can\n"
        "     * leave Winlator's shell child permanently unmapped. Create it as\n"
        "     * managed first, then decide the unmanaged state after creation.\n"
        "     * This follows the Wine MR7181 fix for failed window remapping.\n"
        "     */\n"
        "    data->managed = TRUE;\n"
        "    mask = get_window_attributes( data, &attr );\n",
    )
    replace_once(
        window,
        "    data->desired_state.rect = data->current_state.rect;\n\n"
        "    x11drv_xinput2_enable( data->display, data->whole_window );",
        "    data->desired_state.rect = data->current_state.rect;\n\n"
        "    if (!is_window_managed( data->hwnd, SWP_NOACTIVATE, FALSE )) data->managed = FALSE;\n\n"
        "    x11drv_xinput2_enable( data->display, data->whole_window );",
    )


def validate_patched(root: Path) -> None:
    checks = {
        "server/request.c": ["%s/.wineserver"],
        "dlls/ntdll/unix/server.c": ["%s/.wineserver/server-%llx-%llx"],
        "dlls/ntdll/unix/security.c": [
            "case TokenPrivateNameSpace:",
            "ARRAY_SIZE(info_len)",
            "sizeof(DWORD) /* TokenPrivateNameSpace */",
        ],
        "dlls/wow64/security.c": ["case TokenPrivateNameSpace:  /* ULONG */"],
        "dlls/winex11.drv/window.c": [
            "This follows the Wine MR7181 fix for failed window remapping.",
            "data->managed = TRUE;",
            "if (!is_window_managed( data->hwnd, SWP_NOACTIVATE, FALSE )) data->managed = FALSE;",
        ],
    }
    for rel, needles in checks.items():
        text = (root / rel).read_text(encoding="utf-8")
        if "/tmp/.wine-%u" in text:
            raise RuntimeError(f"legacy wineserver path remains in {rel}")
        for needle in needles:
            if needle not in text:
                raise RuntimeError(f"patched anchor missing in {rel}: {needle}")

    nsi_text = (root / "dlls/nsiproxy.sys/nsi.c").read_text(encoding="utf-8")
    if "#if defined(HAVE_LINUX_RTNETLINK_H) || defined(__APPLE__)" in nsi_text:
        raise RuntimeError("Linux rtnetlink notification path remains enabled")

    window_text = (root / "dlls/winex11.drv/window.c").read_text(encoding="utf-8")
    old_creation = (
        "mask = get_window_attributes( data, &attr ) | CWOverrideRedirect;\n"
        "    attr.override_redirect = !data->managed;"
    )
    if old_creation in window_text:
        raise RuntimeError("override-redirect is still enabled during X window creation")


def install_ci_wrappers() -> None:
    github_path = os.environ.get("GITHUB_PATH")
    if not github_path:
        return

    bindir = Path.cwd() / ".tr-ci-bin"
    bindir.mkdir(exist_ok=True)

    objdump_wrapper = bindir / "x86_64-w64-mingw32-objdump"
    objdump_wrapper.write_text("#!/bin/sh\nexec objdump \"$@\"\n", encoding="utf-8")
    objdump_wrapper.chmod(objdump_wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    docker_wrapper = bindir / "docker"
    docker_wrapper.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"${1:-}\" = run ] && [ -f build-wine.sh ]; then\n"
        "  python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "path = Path('build-wine.sh')\n"
        "text = path.read_text(encoding='utf-8')\n"
        "replacements = {\n"
        "    'rm -rf /work/wine-build /work/wine-stage /work/native-prefix': 'rm -rf /work/wine-build /work/wine-stage /tmp/native-prefix',\n"
        "    'export WINEPREFIX=/work/native-prefix': 'export WINEPREFIX=/tmp/native-prefix',\n"
        "    'timeout 90 /work/wine-stage/opt/wine/bin/wineboot -u': \"/bin/sh -c '/work/wine-stage/opt/wine/bin/wineboot --init & wineboot_pid=$!; ready=0; for _ in $(seq 1 300); do if [ -s \\\"$WINEPREFIX/system.reg\\\" ] && /work/wine-stage/opt/wine/bin/wine cmd /c ver > /work/native-wineboot-readiness.log 2>&1; then ready=1; break; fi; if ! kill -0 \\\"$wineboot_pid\\\" 2>/dev/null; then wait \\\"$wineboot_pid\\\"; exit $?; fi; sleep 1; done; if [ \\\"$ready\\\" -ne 1 ]; then kill \\\"$wineboot_pid\\\" 2>/dev/null || true; wait \\\"$wineboot_pid\\\" 2>/dev/null || true; exit 124; fi; kill \\\"$wineboot_pid\\\" 2>/dev/null || true; wait \\\"$wineboot_pid\\\" 2>/dev/null || true'\",\n"
        "}\n"
        "for old, new in replacements.items():\n"
        "    count = text.count(old)\n"
        "    if count != 1:\n"
        "        raise SystemExit(f'expected one CI harness anchor, found {count}: {old}')\n"
        "    text = text.replace(old, new, 1)\n"
        "path.write_text(text, encoding='utf-8')\n"
        "PY\n"
        "fi\n"
        "exec /usr/bin/docker \"$@\"\n",
        encoding="utf-8",
    )
    docker_wrapper.chmod(docker_wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    with Path(github_path).open("a", encoding="utf-8") as stream:
        stream.write(str(bindir.resolve()) + "\n")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_wine_11_14_winlator.py WINE_SOURCE_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    validate_source(root)
    patch_wineserver_paths(root)
    patch_android_nsi(root)
    patch_token_private_namespace(root)
    patch_override_redirect_creation(root)
    validate_patched(root)
    install_ci_wrappers()

    subprocess.run(["git", "-C", str(root), "diff", "--check"], check=True)
    report = "\n".join([
        f"wine_head={EXPECTED_HEAD}",
        "wine_version=11.14",
        "server_base=WINEPREFIX/.wineserver",
        "nsi_linux_notification=disabled_without_faking_success",
        "token_private_namespace=desktop_false_for_x64_and_wow64",
        "x11_create_override_redirect=deferred_after_creation_mr7181",
        "native_ci_prefix=/tmp/native-prefix",
        "native_ci_wineboot_mode=readiness_gated_init",
        "native_ci_wineboot_timeout=300_seconds",
        "xshape=disabled_at_configure_time",
        "security_bypass=none",
        "",
    ])
    Path("wine-11.14-winlator-patch-report.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
