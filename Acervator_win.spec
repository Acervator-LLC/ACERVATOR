# -*- mode: python ; coding: utf-8 -*-
"""
Acervator_win.spec — PyInstaller spec for Windows
==========================================================
Produces: dist/Acervator/Acervator.exe

Build command (run on Windows):
    pip install pyinstaller PySide6 ccxt cryptography keyring pandas numpy ta tomli_w aiohttp certifi requests reportlab pillow
    pyinstaller Acervator_win.spec

The resulting .exe is a standalone Windows application.
No NSIS, no separate installer — the dist/ folder IS the application.
Optionally zip dist/Acervator/ for distribution.
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Project root is where this spec file lives
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
# Collect all source modules
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
        'keyring.backends.Windows',
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
# Package into a single directory
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
    upx=True,
    console=False,                      # Windowed application — no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    icon=os.path.join(PROJECT_ROOT, 'resources', 'icon.ico'),
    version_info={
        'CompanyName': 'Quantum Trading Systems',
        'FileDescription': f'Acervator v{ACERVATOR_VERSION}',
        'FileVersion': '1.1.0.0',
        'InternalName': 'Acervator',
        'OriginalFilename': 'Acervator.exe',
        'ProductName': 'Acervator',
        'ProductVersion': '1.1.0',
    } if os.path.exists(os.path.join(PROJECT_ROOT, 'resources', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Acervator',
)
