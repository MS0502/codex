#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

PROTON_SHA = "d2bedfad453584d05308f5e3e1f9657e3f0f71d3"
WINE_SHA = "81d78e4f3ea8ce868d775021fdc9f90122dc1a6b"


def replace_exact(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proton_root", type=Path)
    args = parser.parse_args()
    proton = args.proton_root.resolve()
    wine = proton / "wine"

    request = wine / "server/request.c"
    client = wine / "dlls/ntdll/unix/server.c"
    nsi = wine / "dlls/nsiproxy.sys/nsi.c"
    makefile = proton / "Makefile.in"

    request_old = "\n".join([
        '#ifdef __ANDROID__  /* there\'s no /tmp dir on Android */',
        '    if (asprintf( &base_dir, "%s/.wineserver", config_dir ) == -1)',
        '        fatal_error( "out of memory\\n" );',
        '#else',
        '    if (asprintf( &base_dir, "/tmp/.wine-%u", getuid() ) == -1)',
        '        fatal_error( "out of memory\\n" );',
        '#endif',
    ])
    request_new = "\n".join([
        '/* Winlator glibc build runs inside the Android app sandbox. */',
        '    if (asprintf( &base_dir, "%s/.wineserver", config_dir ) == -1)',
        '        fatal_error( "out of memory\\n" );',
    ])
    replace_exact(request, request_old, request_new, "wineserver base path")

    client_old = "\n".join([
        '#ifdef __ANDROID__  /* there\'s no /tmp dir on Android */',
        '    asprintf( &dir, "%s/.wineserver/server-%llx-%llx", config_dir, (unsigned long long)dev, (unsigned long long)ino );',
        '#else',
        '    asprintf( &dir, "/tmp/.wine-%u/server-%llx-%llx", getuid(), (unsigned long long)dev, (unsigned long long)ino );',
        '#endif',
    ])
    client_new = "\n".join([
        '/* Match the Android-safe wineserver location under WINEPREFIX. */',
        '    asprintf( &dir, "%s/.wineserver/server-%llx-%llx", config_dir, (unsigned long long)dev, (unsigned long long)ino );',
    ])
    replace_exact(client, client_old, client_new, "Wine client server path")

    replace_exact(
        nsi,
        '#if defined(HAVE_LINUX_RTNETLINK_H) || defined(__APPLE__)',
        '#if defined(__APPLE__)  /* Android sandbox denies NETLINK_ROUTE multicast bind. */',
        "nsiproxy notification backend",
    )

    old_args = "\n".join([
        'WINE_AUTOCONF_ARGS = \\',
        '  --enable-werror \\',
        '  --with-mingw=$(MINGW_TYPE) \\',
        '  --disable-tests',
    ])
    profile = [
        '--without-capi', '--without-cups', '--without-dbus', '--without-ffmpeg',
        '--without-gphoto', '--without-gstreamer', '--without-gssapi', '--without-krb5',
        '--without-netapi', '--without-opencl', '--without-oss', '--without-pcap',
        '--without-pcsclite', '--without-piper', '--without-sane', '--without-sdl',
        '--without-udev', '--without-usb', '--without-v4l2', '--without-vosk',
        '--without-wayland', '--without-xshape',
    ]
    new_lines = [
        'WINE_AUTOCONF_ARGS = \\',
        '  --enable-werror \\',
        '  --with-mingw=$(MINGW_TYPE) \\',
        '  --disable-tests \\',
    ]
    for index, option in enumerate(profile):
        suffix = ' \\' if index != len(profile) - 1 else ''
        new_lines.append(f'  {option}{suffix}')
    replace_exact(makefile, old_args, "\n".join(new_lines), "Proton Wine configure profile")

    all_text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (request, client))
    if "/tmp/.wine-%u" in all_text:
        raise RuntimeError("legacy /tmp wineserver path remains")
    if nsi.read_text(encoding="utf-8").count("#if defined(__APPLE__)  /* Android sandbox") != 1:
        raise RuntimeError("nsiproxy sandbox patch missing")
    make_text = makefile.read_text(encoding="utf-8")
    for option in profile:
        if make_text.count(option) != 1:
            raise RuntimeError(f"configure option missing or duplicated: {option}")

    report = "\n".join([
        f"proton={PROTON_SHA}", f"wine={WINE_SHA}",
        "wineserver_base=WINEPREFIX/.wineserver",
        "nsiproxy_linux_notifications=disabled",
        "profile=" + " ".join(profile), "",
    ])
    Path("v18i-proton-source-profile.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
