"""Shared PyInstaller spec content for Acervator_win.spec and Acervator_mac.spec.

Issue #87 — the two spec files were about 90 percent the same text. Both
defined ``_read_acervator_version`` and ``_build_graceful_datas`` with
identical bodies, and both carried the same 40-name ``hiddenimports``
list and the same 9-name ``excludes`` list. A hand-maintained test,
``tests/test_specs_parity.py``, compared the two files with regular
expressions to keep them in step. That test could only report drift
AFTER it happened, and only in the shapes somebody had written a pin for.

The two lists now exist once, here. The spec files hold only what is
genuinely per-platform: the keyring backend, the icon, UPX, the Windows
``version_info`` resource, and the macOS ``BUNDLE``.

WHY THIS MODULE DOES NOT IMPORT PyInstaller
===========================================
``collect_submodules('src')`` stays in each spec file, where PyInstaller
is guaranteed to be present. This module is therefore importable by the
test suite on a machine with no PyInstaller installed, and the parity
test that reads it costs milliseconds instead of parsing spec text with
regular expressions. Its only non-stdlib import is ``src._version``,
which is stdlib-only itself.

WHY THE PACKAGE NAMES HERE ARE NOT A DEPENDENCY LIST
====================================================
Issue #94 made ``pyproject.toml`` the one source for what pip installs.
The names below are NOT that. A ``hiddenimport`` is a MODULE name handed
to PyInstaller's graph analysis, and it is frequently a submodule
(``ccxt.async_support.kraken``,
``cryptography.hazmat.primitives.kdf.pbkdf2``) that no dependency list
can name. Do not read this as an install list and do not add one here.
"""

from __future__ import annotations

import os

from src._version import BAKED_FILENAME, UNKNOWN_VERSION, resolve_version

# What a tree that answers nothing resolves to. One constant, shared with
# the package, so the build and the application cannot disagree about what
# "no version" looks like.
FALLBACK_VERSION = UNKNOWN_VERSION

# Where the resolved version is written before it is handed to PyInstaller.
# build/ is regenerable and gitignored; nothing is written into src/.
BAKE_SUBDIR = os.path.join("build", "version")


def read_acervator_version(project_root: str) -> str:
    """Return the version resolved for the tree at ``project_root``.

    Derived from the git tag, not from any literal. Neither spec reads
    ``pyproject.toml``, which declares the version ``dynamic``.
    """
    return resolve_version(project_root)


def bake_version_datas(project_root: str) -> list[tuple[str, str]]:
    """Write the resolved version to disk and return its PyInstaller pair.

    A bundle carries no ``.git``, so the version has to travel as a file.
    The destination is ``src``, where ``src/_version.py`` looks for it.
    """
    out_dir = os.path.join(project_root, BAKE_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, BAKED_FILENAME)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(read_acervator_version(project_root) + "\n")
    return [(out_path, "src")]


def datas_candidates(project_root: str) -> list[tuple[str, str]]:
    """Every (source, destination) pair a build would ship, present or not.

    Separated from :func:`build_graceful_datas` so a test can inspect the
    intended set without needing the optional directories to exist on the
    machine running the test.
    """
    return [
        (os.path.join(project_root, "src"), "src"),
        (os.path.join(project_root, "resources"), "resources"),
        # data/historical is populated by download_archive.py — optional
        # at build time. If missing, the app falls back to the runtime
        # cache plus the embedded ASSET_PERIODS anchors.
        (
            os.path.join(project_root, "data", "historical"),
            os.path.join("data", "historical"),
        ),
        # RAIntSimBat engine — Session 21+ location (sadp/) probed first,
        # legacy root as fallback. The battery engine is the source of
        # truth, so the build must ship whichever path exists.
        (
            os.path.join(project_root, "sadp", "RAIntSimBat"),
            os.path.join("sadp", "RAIntSimBat"),
        ),
        (os.path.join(project_root, "RAIntSimBat"), "RAIntSimBat"),
    ]


def build_graceful_datas(project_root: str) -> list[tuple[str, str]]:
    """Return the datas pairs whose source directory exists.

    A missing optional path is printed and skipped. PyInstaller aborts on
    a datas entry that points at nothing, and three of the five entries
    are optional, so the skip is what lets a fresh clone build at all.

    KNOWN AND NOT FIXED HERE (issue #82): the first pair ships the WHOLE
    ``src`` directory, so any file under ``src/`` reaches the bundle
    whether git tracks it or not. Measured 2026-08-23 on the operator's
    tree: 276 files under ``src``, 166 of them tracked; the other 110 are
    ``__pycache__`` bytecode. Narrowing this means replacing the directory
    pair with an explicit per-file list, which changes what ships, and
    that needs a build on both platforms to verify. It belongs to
    issue #82.
    """
    result = []
    for src_path, dest_path in datas_candidates(project_root):
        if os.path.isdir(src_path):
            result.append((src_path, dest_path))
        else:
            print(f"  [spec] Skipping missing optional datas path: {src_path}")
    return result


# Hidden imports
#
# Every name here is load-bearing until a build proves otherwise. A
# dropped hiddenimport does not fail the build; it fails the frozen
# application at run time, on the operator's machine. Add freely, remove
# only with a control build behind you.

COMMON_HIDDENIMPORTS: tuple[str, ...] = (
    # MEM-219 — self-supervising watchdog module at project root.
    "acervator_watchdog",
    "ccxt",
    "ccxt.async_support",
    "ccxt.async_support.binance",
    "ccxt.async_support.coinbase",
    "ccxt.async_support.kraken",
    "ccxt.async_support.kucoin",
    "ccxt.async_support.bybit",
    "ccxt.async_support.okx",
    "ccxt.async_support.gate",  # renamed from gateio in ccxt 4.x
    "ccxt.async_support.bitget",
    "ccxt.async_support.htx",  # renamed from huobi in ccxt 4.x
    "ccxt.async_support.mexc",
    "ccxt.async_support.bitfinex",
    "ccxt.async_support.gemini",
    "ccxt.async_support.poloniex",
    "ccxt.async_support.bitstamp",
    "ccxt.async_support.cryptocom",
    "cryptography",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "PySide6",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWebEngineWidgets",
    "keyring",
    "keyring.backends",
    # pandas and ta: measured 2026-08-23, no file in src/, tools/,
    # main.py or acervator_watchdog.py imports either one. numpy IS
    # imported. All three stay because removing a hiddenimport is only
    # safe behind a control build on BOTH platforms, and issue #87 could
    # build Windows only. Reported, not changed.
    "pandas",
    "numpy",
    "ta",
    "aiohttp",
    # tomli: src/core/settings.py:32 imports it, but only in the
    # ``except ImportError`` arm under ``import tomllib``. pyproject.toml
    # sets requires-python >= 3.11 and tomllib is stdlib from 3.11, so
    # that arm is unreachable on every supported interpreter. Kept for
    # the same reason as pandas: no build proved its removal safe.
    "tomli",
    "tomli_w",
    "psutil",  # Nuclear v4 MR — system load sampling (v3.10.5)
    # defusedxml — RSS parsing in src/gui/crypto_news_ticker.py.
    # NOT REQUIRED for collection: measured on PyInstaller 6.22.0,
    # automatic analysis reaches it from the src.gui.crypto_news_ticker
    # graph root that collect_submodules supplies, and puts all ten
    # defusedxml modules in the PYZ with no entry here and no hook
    # (neither PyInstaller nor pyinstaller-hooks-contrib 2026.6 ships a
    # defusedxml hook). Named anyway, for the same reason PySide6 is
    # named though analysis finds it too: its absence is not a degraded
    # ticker but an ImportError at module import. Measured on a control
    # build with defusedxml excluded, the frozen binary raised
    # ModuleNotFoundError from crypto_news_ticker.py at import time.
    # It lives INSIDE the PYZ, not as an _internal/defusedxml folder.
    # Do not read a missing folder as a missing package.
    "defusedxml",
    "defusedxml.ElementTree",
)

# The one legitimate per-platform hidden import. keyring picks its
# backend at run time from what it can import, so the frozen application
# must carry the backend for the platform it was frozen on.
KEYRING_BACKENDS: dict[str, str] = {
    "windows": "keyring.backends.Windows",
    "macos": "keyring.backends.macOS",
}


def hiddenimports_for(platform: str) -> list[str]:
    """Return the hidden imports for ``platform``: ``windows`` or ``macos``.

    Raises on an unknown platform rather than answering the common list.
    A spec that silently lost its keyring backend would build clean and
    then fail to reach the operator's stored credentials.
    """
    try:
        backend = KEYRING_BACKENDS[platform]
    except KeyError:
        raise ValueError(
            f"unknown spec platform {platform!r}; "
            f"expected one of {sorted(KEYRING_BACKENDS)}"
        ) from None
    return [*COMMON_HIDDENIMPORTS, backend]


# Excludes — identical on both platforms.
EXCLUDES: tuple[str, ...] = (
    "tkinter",
    "matplotlib",
    "scipy",
    "PIL",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "sphinx",
    "setuptools",
)
