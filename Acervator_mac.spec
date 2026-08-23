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

The resulting .app is a standard macOS application bundle.
Drag it to /Applications or distribute as a .dmg (see build_mac.sh).

Structural parity with Acervator_win.spec is enforced by
tests/test_specs_parity.py. Both specs must:
  - define _read_acervator_version() and use it to compute ACERVATOR_VERSION
  - define _build_graceful_datas() and pass its return to Analysis(datas=...)
  - list the same ccxt.async_support.<exchange> hiddenimports
  - include 'acervator_watchdog' in hiddenimports
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

PROJECT_ROOT = os.path.dirname(os.path.abspath(SPEC))

block_cipher = None

# ---------------------------------------------------------------------------
# Dynamic version from src/__init__.py (single source of truth)
# ---------------------------------------------------------------------------
def _read_acervator_version(project_root):
    fallback = '3.13.7'
    try:
        with open(os.path.join(project_root, 'src', '__init__.py'), encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('__version__'):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return fallback

ACERVATOR_VERSION = _read_acervator_version(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Graceful datas: skip missing optional paths; probe sadp/ then legacy location
# ---------------------------------------------------------------------------
def _build_graceful_datas(project_root):
    candidates = [
        (os.path.join(project_root, 'src'), 'src'),
        (os.path.join(project_root, 'resources'), 'resources'),
        # data/historical is populated by download_archive.py — optional at build time.
        # If missing, the app falls back to runtime cache + embedded ASSET_PERIODS anchors.
        (os.path.join(project_root, 'data', 'historical'), os.path.join('data', 'historical')),
        # RAIntSimBat engine — Session 21+ location (sadp/) probed first, legacy root as fallback.
        # sadp: R42 (battery engine is the source of truth — must ship whichever path exists)
        (os.path.join(project_root, 'sadp', 'RAIntSimBat'), os.path.join('sadp', 'RAIntSimBat')),
        (os.path.join(project_root, 'RAIntSimBat'), 'RAIntSimBat'),
    ]
    result = []
    for src_path, dest_path in candidates:
        if os.path.isdir(src_path):
            result.append((src_path, dest_path))
        else:
            print(f"  [spec] Skipping missing optional datas path: {src_path}")
    return result

# ---------------------------------------------------------------------------
# Analysis — parity with Acervator_win.spec on hidden imports.
# Only difference: keyring backend swaps Windows -> macOS.
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(PROJECT_ROOT, 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=_build_graceful_datas(PROJECT_ROOT),
    hiddenimports=(
        # Automatically collect ALL src.* submodules — never needs manual updating
        collect_submodules('src')
        + [
        # MEM-219 — self-supervising watchdog module at project root
        'acervator_watchdog',
        'ccxt',
        'ccxt.async_support',
        'ccxt.async_support.binance',
        'ccxt.async_support.coinbase',
        'ccxt.async_support.kraken',
        'ccxt.async_support.kucoin',
        'ccxt.async_support.bybit',
        'ccxt.async_support.okx',
        'ccxt.async_support.gate',       # renamed from gateio in ccxt 4.x
        'ccxt.async_support.bitget',
        'ccxt.async_support.htx',        # renamed from huobi in ccxt 4.x
        'ccxt.async_support.mexc',
        'ccxt.async_support.bitfinex',
        'ccxt.async_support.gemini',
        'ccxt.async_support.poloniex',
        'ccxt.async_support.bitstamp',
        'ccxt.async_support.cryptocom',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'PySide6',
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWebEngineWidgets',
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
        'pandas',
        'numpy',
        'ta',
        'aiohttp',
        'tomli',
        'tomli_w',
        'psutil',    # Nuclear v4 MR — system load sampling (v3.10.5)
        # defusedxml — RSS parsing in src/gui/crypto_news_ticker.py.
        # NOT REQUIRED for collection: measured on PyInstaller 6.22.0,
        # automatic analysis reaches it from the
        # src.gui.crypto_news_ticker graph root that collect_submodules
        # supplies above, and puts all ten defusedxml modules in the
        # PYZ with no entry here and no hook (neither PyInstaller nor
        # pyinstaller-hooks-contrib 2026.6 ships a defusedxml hook).
        # Named anyway, for the same reason PySide6 and pandas are
        # named above though analysis finds them too: its absence is
        # not a degraded ticker but an ImportError at module import.
        # Measured on a control build with defusedxml excluded, the
        # frozen binary raised ModuleNotFoundError from
        # crypto_news_ticker.py at import time.
        # It lives INSIDE the PYZ, not as an _internal/defusedxml
        # folder. Do not read a missing folder as a missing package.
        'defusedxml',
        'defusedxml.ElementTree',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'scipy', 'PIL',
        'IPython', 'jupyter', 'notebook',
        'pytest', 'sphinx', 'setuptools',
    ],
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
    name='Acervator',
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
    icon=os.path.join(PROJECT_ROOT, 'resources', 'icon.icns'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Acervator',
)

# ---------------------------------------------------------------------------
# macOS .app bundle — version driven from ACERVATOR_VERSION (src/__init__.py).
# CFBundleVersion (build number) and CFBundleShortVersionString (marketing
# version) are BOTH populated from the same source; they intentionally match
# for us since we ship a single unified version scheme.
# ---------------------------------------------------------------------------
app = BUNDLE(
    coll,
    name='Acervator.app',
    icon=os.path.join(PROJECT_ROOT, 'resources', 'icon.icns'),
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
