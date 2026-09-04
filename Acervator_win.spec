# -*- mode: python ; coding: utf-8 -*-
"""
Acervator_win.spec — PyInstaller spec for Windows
==========================================================
Produces: dist/Acervator/Acervator.exe

Build command (run on Windows):
    pip install $(python -m tools.deps requirements build)
    pyinstaller Acervator_win.spec

Issue #94 - that first command used to be a hand-copied list of 14
package names written out in this docstring. It was one of eight such
lists and it agreed with none of the others. pyproject.toml is the one
source now, and tools/deps.py reads it. Do not write a package name
back into this file.

Issue #87 - everything this file used to share with Acervator_mac.spec
now lives in tools/spec_common.py: the version reader, the datas
builder, the hidden-import list and the excludes list. What is left
below is per-platform and nothing else. Do not copy a shared value back
into this file; change it in tools/spec_common.py and both platforms
follow.

The resulting .exe is a standalone Windows application.
No NSIS, no separate installer — the dist/ folder IS the application.
Optionally zip dist/Acervator/ for distribution.
"""

import os
import sys

# Project root is where this spec file lives
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
    windows_file_version,
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
# already in dist rather than replacing it. The operator runs builds from
# dist and keeps several side by side; a rebuild must never remove or
# overwrite a bundle a live process may hold open.
OUTPUT_NAME = unique_output_basename(DISTPATH, ACERVATOR_VERSION, ACERVATOR_VARIANT)

ICON_PATH = os.path.join(PROJECT_ROOT, 'resources', 'icon.ico')

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
    hiddenimports=collect_submodules('src') + hiddenimports_for('windows'),
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
# Package into a single directory
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
    upx=True,
    console=False,                      # Windowed application — no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    icon=ICON_PATH,
    # Every field here is derived. FileVersion and ProductVersion are
    # numeric-only Windows resource fields, so they carry the leading
    # numbers of the resolved version and drop any local segment after
    # the '+'. They used to read a literal '1.1.0', which made Explorer's
    # Properties pane and FileDescription report two different versions
    # for the same executable.
    version_info={
        'CompanyName': 'Quantum Trading Systems',
        'FileDescription': f'Acervator v{ACERVATOR_VERSION} ({ACERVATOR_VARIANT})',
        'FileVersion': windows_file_version(ACERVATOR_VERSION),
        'InternalName': OUTPUT_NAME,
        'OriginalFilename': f'{OUTPUT_NAME}.exe',
        'ProductName': 'Acervator',
        'ProductVersion': windows_file_version(ACERVATOR_VERSION),
    } if os.path.exists(ICON_PATH) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=OUTPUT_NAME,
)
