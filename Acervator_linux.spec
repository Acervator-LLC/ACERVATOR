"""PyInstaller spec for Linux x86_64: one ``OUTPUT_NAME`` AppDir per variant."""

import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(SPEC)))

from PIL import Image
from PyInstaller.utils.hooks import collect_submodules

from tools.build_variants import (
    APP_NAME,
    bake_variant_datas,
    requested_variant,
    unique_output_basename,
)
from tools.spec_common import (
    bake_version_datas,
    build_graceful_datas,
    excludes_for,
    hiddenimports_for,
    reachable_only,
    read_acervator_version,
    report_unreachable,
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

TARGET = ("Linux", "x86_64")
HOST = (platform.system(), platform.machine())
if HOST != TARGET:
    refusal = f"Acervator_linux.spec builds on {TARGET}, not on {HOST}"
    raise SystemExit(refusal)

ACERVATOR_VERSION = read_acervator_version(PROJECT_ROOT)
ACERVATOR_VARIANT = requested_variant()
OUTPUT_NAME = unique_output_basename(DISTPATH, ACERVATOR_VERSION, ACERVATOR_VARIANT)

ICON_SOURCE = os.path.join(PROJECT_ROOT, "resources", "icon.ico")
ICON_NAME = APP_NAME.lower()
DESKTOP_ENTRY = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    f"Name={APP_NAME}\n"
    f"Exec={OUTPUT_NAME}\n"
    f"Icon={ICON_NAME}\n"
    "Categories=Office;Finance;\n"
    "Terminal=false\n"
)

report_unreachable(PROJECT_ROOT)

a = Analysis(
    [os.path.join(PROJECT_ROOT, "main.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=(
        build_graceful_datas(PROJECT_ROOT, ACERVATOR_VARIANT)
        + bake_version_datas(PROJECT_ROOT)
        + bake_variant_datas(PROJECT_ROOT, ACERVATOR_VARIANT)
    ),
    hiddenimports=(
        reachable_only(collect_submodules("src"), PROJECT_ROOT)
        + hiddenimports_for("linux")
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes_for(PROJECT_ROOT),
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=OUTPUT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
)

COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=OUTPUT_NAME,
)

APPDIR = os.path.join(DISTPATH, OUTPUT_NAME)
os.symlink(OUTPUT_NAME, os.path.join(APPDIR, "AppRun"))
with Image.open(ICON_SOURCE) as icon:
    icon.save(os.path.join(APPDIR, f"{ICON_NAME}.png"))
DESKTOP_PATH = os.path.join(APPDIR, f"{ICON_NAME}.desktop")
with open(DESKTOP_PATH, "w", encoding="utf-8", newline="\n") as entry:
    entry.write(DESKTOP_ENTRY)
