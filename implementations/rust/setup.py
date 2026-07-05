#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path


APP_NAME = "Nozzle Filament Validator Post-Processor"
BIN_NAME = "nvf_postprocessor"
DESKTOP_ID = "nvf-postprocessor"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and install the Rust NVF post-processor.")
    parser.add_argument("--debug", action="store_true", help="Build the debug binary instead of release.")
    parser.add_argument("--build-only", action="store_true", help="Only build, do not install.")
    parser.add_argument("--install-dir", help="Override the platform default install directory.")
    args = parser.parse_args()

    rust_dir = Path(__file__).resolve().parent
    implementations_dir = rust_dir.parent
    profile = "debug" if args.debug else "release"

    build(rust_dir, args.debug)
    binary = built_binary(rust_dir, profile)
    if not binary.exists():
        raise FileNotFoundError(f"Expected build output was not found: {binary}")

    if args.build_only:
        print_setup_instructions(binary)
        return 0

    installed_binary = install(implementations_dir, binary, args.install_dir)
    print_setup_instructions(installed_binary)
    return 0


def build(rust_dir: Path, debug: bool) -> None:
    command = ["cargo", "build"]
    if not debug:
        command.append("--release")
    print(f"Building Rust app with: {' '.join(command)}")
    subprocess.run(command, cwd=rust_dir, check=True)


def built_binary(rust_dir: Path, profile: str) -> Path:
    suffix = ".exe" if platform.system() == "Windows" else ""
    return rust_dir / "target" / profile / f"{BIN_NAME}{suffix}"


def install(implementations_dir: Path, binary: Path, override: str | None) -> Path:
    system = platform.system()
    if system == "Darwin":
        return install_macos(implementations_dir, binary, override)
    if system == "Windows":
        return install_windows(implementations_dir, binary, override)
    return install_linux(implementations_dir, binary, override)


def install_linux(implementations_dir: Path, binary: Path, override: str | None) -> Path:
    home = Path.home()
    bin_dir = Path(override).expanduser() if override else home / ".local" / "bin"
    app_binary = bin_dir / BIN_NAME
    applications_dir = home / ".local" / "share" / "applications"
    settings_path = bin_dir / "nfvsettings.json"

    bin_dir.mkdir(parents=True, exist_ok=True)
    applications_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, app_binary)
    app_binary.chmod(app_binary.stat().st_mode | 0o755)
    install_linux_icons(implementations_dir, home)
    settings_path.touch(exist_ok=True)

    desktop_file = applications_dir / f"{DESKTOP_ID}.desktop"
    desktop_file.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name={APP_NAME}",
                f"Exec={quote(str(app_binary))} %f",
                f"Icon={DESKTOP_ID}",
                "Terminal=false",
                "Categories=Utility;",
                "MimeType=text/x-gcode;",
                "",
            ]
        )
    )
    desktop_file.chmod(desktop_file.stat().st_mode | 0o755)
    maybe_add_path_hint(bin_dir)
    print(f"Installed Linux desktop entry: {desktop_file}")
    return app_binary


def install_macos(implementations_dir: Path, binary: Path, override: str | None) -> Path:
    requested = Path(override).expanduser() if override else Path("/Applications")
    applications_dir = requested if can_write_dir(requested) else Path.home() / "Applications"
    app_dir = applications_dir / f"{APP_NAME}.app"
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    app_binary = macos_dir / BIN_NAME

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, app_binary)
    app_binary.chmod(app_binary.stat().st_mode | 0o755)
    write_rounded_icon_png(icon_png(implementations_dir), resources_dir / "icon.png", 512)
    create_macos_icns(icon_png(implementations_dir), resources_dir / "AppIcon.icns")
    (macos_dir / "nfvsettings.json").touch(exist_ok=True)
    (contents / "Info.plist").write_text(macos_info_plist())
    print(f"Installed macOS app bundle: {app_dir}")
    return app_binary


def install_windows(implementations_dir: Path, binary: Path, override: str | None) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    default_dir = Path(local_app_data) / APP_NAME if local_app_data else Path.home() / APP_NAME
    install_dir = Path(override).expanduser() if override else default_dir
    install_dir.mkdir(parents=True, exist_ok=True)
    app_binary = install_dir / f"{BIN_NAME}.exe"
    shutil.copy2(binary, app_binary)
    write_rounded_icon_png(icon_png(implementations_dir), install_dir / "icon.png", 512)
    create_windows_ico(icon_png(implementations_dir), install_dir / "icon.ico")
    (install_dir / "nfvsettings.json").touch(exist_ok=True)
    (install_dir / "setup-postprocessor-rust.bat").write_text(
        "@echo off\n"
        "echo Postprocessor setup complete.\n"
        "echo.\n"
        "echo Enter the following in your slicer's post processor section:\n"
        "echo.\n"
        f'echo "{app_binary}"\n'
    )
    maybe_create_windows_start_menu_entry(app_binary)
    print(f"Installed Windows files: {install_dir}")
    return app_binary


def maybe_create_windows_start_menu_entry(app_binary: Path) -> None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    programs.mkdir(parents=True, exist_ok=True)
    command_file = programs / f"{APP_NAME}.cmd"
    command_file.write_text(f'@echo off\nstart "" "{app_binary}"\n')
    print(f"Installed Start Menu command: {command_file}")


def icon_png(implementations_dir: Path) -> Path:
    return implementations_dir / "python" / "icon.png"


def install_linux_icons(implementations_dir: Path, home: Path) -> None:
    for size in (16, 32, 48, 64, 128, 256, 512):
        icon_dir = home / ".local" / "share" / "icons" / "hicolor" / f"{size}x{size}" / "apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        write_rounded_icon_png(icon_png(implementations_dir), icon_dir / f"{DESKTOP_ID}.png", size)


def create_macos_icns(source_png: Path, icns_path: Path) -> None:
    stale_iconset = icns_path.with_suffix(".iconset")
    if stale_iconset.exists():
        shutil.rmtree(stale_iconset)

    icon = make_rounded_icon(source_png, 1024)
    icon.save(icns_path)


def create_windows_ico(source_png: Path, ico_path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_rounded_icon(source_png, size) for size in sizes]
    images[-1].save(ico_path, sizes=[(size, size) for size in sizes], append_images=images[:-1])


def write_rounded_icon_png(source_png: Path, output: Path, size: int) -> None:
    make_rounded_icon(source_png, size).save(output)


def make_rounded_icon(source_png: Path, size: int):
    from PIL import Image, ImageDraw

    source = Image.open(source_png).convert("RGBA")
    width, height = source.size
    crop_size = min(width, height)
    left = (width - crop_size) // 2
    top = (height - crop_size) // 2
    image = source.crop((left, top, left + crop_size, top + crop_size))
    image = image.resize((size, size), Image.Resampling.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(size * 0.225)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(image)
    canvas.putalpha(mask)
    return canvas


def macos_info_plist() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>{BIN_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>com.nozzlefilamentvalidator.postprocessor</string>
  <key>CFBundleName</key>
  <string>{APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>{APP_NAME}</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon.icns</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
</dict>
</plist>
"""


def can_write_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".nvf_write_test"
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False


def maybe_add_path_hint(bin_dir: Path) -> None:
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if str(bin_dir) not in path_entries:
        print(f"Note: add {bin_dir} to PATH if your slicer cannot find {BIN_NAME}.")


def print_setup_instructions(binary: Path) -> None:
    print()
    print("Postprocessor setup complete.")
    print()
    print("Enter the following in your slicer's post processor section:")
    print()
    print(quote(str(binary)))


def quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)
