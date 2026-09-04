# -*- mode: python ; coding: utf-8 -*-
"""
Acervator_mac.spec — PyInstaller spec for macOS
========================================================
Produces: dist/Acervator.app

Build command (run on macOS):
    pip install $(python -m tools.deps requirements build)
    pyinstaller Acervator_mac.spec

Issue #94 - that first command used to be a hand-copied list of 14
package names written out in this docstring. It was one of eight such
lists and it agreed with none of the others. pyproject.toml is the one
source now, and tools/deps.py reads it. Do not write a package name
back into this file.

Issue #87 - this file used to hold its own copy of the version reader,
the datas builder, the hidden-import list and the excludes list, and a
regex test kept the two copies in step. All four now live once, in
tools/spec_common.py. What is left below is per-platform and nothing
else: the .icns icon, UPX off, the codesign hooks and the BUNDLE. Do
not copy a shared value back into this file.

The resulting .app is a standard macOS application bundle.
Drag it to /Applications or distribute as a .dmg (see build_mac.sh).
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

# PyInstaller EXECS a spec file, it does not import it, so the project
# root is not on sys.path by the time this line runs. Put it there
# before importing the shared module. If the import below fails, the
# build stops here with an ImportError — which is the safe failure. A
# spec that quietly lost half its hidden imports would build clean and
# then fail on the operator's machine at run time.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyInstaller.utils.hooks import collect_submodules  # noqa: E402

from tools.build_variants import (  # noqa: E402
    bake_variant_datas,
    requested_variant,
    unique_output_basename,
)
from tools.spec_common import (  # noqa: E402
    EXCLUDES,
    bake_version_datas,
    build_graceful_datas,
    hiddenimports_for,
    read_acervator_version,
)

block_cipher = None

ACERVATOR_VERSION = read_acervator_version(PROJECT_ROOT)
ACERVATOR_VARIANT = requested_variant()

# The output carries the version and the variant, and steps past a name
# already in dist rather than replacing it, so builds accumulate.
OUTPUT_NAME = unique_output_basename(DISTPATH, ACERVATOR_VERSION, ACERVATOR_VARIANT)

ICON_PATH = os.path.join(PROJECT_ROOT, 'resources', 'icon.icns')

# ---------------------------------------------------------------------------
# Collect all source modules.
# collect_submodules('src') stays HERE and not in tools/spec_common.py so
# that the shared module never has to import PyInstaller.
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(PROJECT_ROOT, 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=(
        build_graceful_datas(PROJECT_ROOT)
        + bake_version_datas(PROJECT_ROOT)
        + bake_variant_datas(PROJECT_ROOT, ACERVATOR_VARIANT)
    ),
    hiddenimports=collect_submodules('src') + hiddenimports_for('macos'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=list(EXCLUDES),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ---------------------------------------------------------------------------
# Build the .app bundle
# ---------------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=OUTPUT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                          # UPX not standard on macOS
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,                   # Builds for current arch (arm64 or x86_64)
    codesign_identity=None,             # Set via: --codesign-identity "Developer ID..."
    entitlements_file=None,
    icon=ICON_PATH,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=OUTPUT_NAME,
)

# ---------------------------------------------------------------------------
# macOS .app bundle — version driven from ACERVATOR_VERSION (src/__init__.py).
# CFBundleVersion (build number) and CFBundleShortVersionString (marketing
# version) are BOTH populated from the same source; they intentionally match
# for us since we ship a single unified version scheme.
#
# bundle_identifier is the last artefact of the old project name. Issue #70
# deliberately did NOT change it: on macOS this value IS the installed-app
# identity, so changing it makes an installed build look like a different
# application to Launch Services, the keychain and the sandbox container.
# It stays until the operator decides otherwise.
# ---------------------------------------------------------------------------
app = BUNDLE(
    coll,
    name=f'{OUTPUT_NAME}.app',
    icon=ICON_PATH,
    bundle_identifier='com.quantumtrader.app',
    version=ACERVATOR_VERSION,
    info_plist={
        'CFBundleName': 'Acervator',
        'CFBundleDisplayName': 'Acervator',
        'CFBundleVersion': ACERVATOR_VERSION,
        'CFBundleShortVersionString': ACERVATOR_VERSION,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
        'NSRequiresAquaSystemAppearance': False,    # Supports dark mode
        'LSApplicationCategoryType': 'public.app-category.finance',
        'NSHumanReadableCopyright': '(c) 2025 Anthony L. Brown',
    },
)
