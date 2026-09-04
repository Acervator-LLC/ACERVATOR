"""Shared PyInstaller spec content for Acervator_win.spec and Acervator_mac.spec.

``COMMON_HIDDENIMPORTS``, ``EXCLUDES`` and ``KEYRING_BACKENDS`` hold the names
both spec files import. ``datas_candidates`` and ``build_graceful_datas`` pair
source directories to bundle destinations. ``bake_version_datas`` writes the
``read_acervator_version`` string under ``BAKE_SUBDIR``.
"""

from __future__ import annotations

import os

from src._version import BAKED_FILENAME, UNKNOWN_VERSION, resolve_version

# What read_acervator_version answers for a tree with no version tag and no baked file.
FALLBACK_VERSION = UNKNOWN_VERSION

# bake_version_datas writes here; build/ is gitignored and nothing lands in src/.
BAKE_SUBDIR = os.path.join("build", "version")


def read_acervator_version(project_root: str) -> str:
    """Return what ``resolve_version`` answers for the tree at ``project_root``.

    ``resolve_version`` derives it from the nearest git version tag.
    """
    return resolve_version(project_root)


def bake_version_datas(project_root: str) -> list[tuple[str, str]]:
    """Write ``read_acervator_version`` under ``BAKE_SUBDIR`` and return its datas pair.

    The pair's destination is ``src``, where ``BAKED_FILENAME`` is read back.
    """
    out_dir = os.path.join(project_root, BAKE_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, BAKED_FILENAME)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(read_acervator_version(project_root) + "\n")
    return [(out_path, "src")]


def datas_candidates(project_root: str) -> list[tuple[str, str]]:
    """Return every (source, destination) pair a build would ship, present or not.

    ``build_graceful_datas`` narrows this list to the directories that exist.
    """
    return [
        (os.path.join(project_root, "src"), "src"),
        (os.path.join(project_root, "resources"), "resources"),
        # data/historical is written by download_archive.py and is in no commit.
        (
            os.path.join(project_root, "data", "historical"),
            os.path.join("data", "historical"),
        ),
        # Neither RAIntSimBat path is in any commit; build_graceful_datas skips both.
        (
            os.path.join(project_root, "sadp", "RAIntSimBat"),
            os.path.join("sadp", "RAIntSimBat"),
        ),
        (os.path.join(project_root, "RAIntSimBat"), "RAIntSimBat"),
    ]


def build_graceful_datas(project_root: str) -> list[tuple[str, str]]:
    """Return the ``datas_candidates`` pairs whose source directory exists.

    A missing directory is printed and skipped; the first pair ships all of ``src``.
    """
    result = []
    for src_path, dest_path in datas_candidates(project_root):
        if os.path.isdir(src_path):
            result.append((src_path, dest_path))
        else:
            print(f"  [spec] Skipping missing optional datas path: {src_path}")
    return result


# A name missing here fails the frozen application at run time, not at build time.
COMMON_HIDDENIMPORTS: tuple[str, ...] = (
    # acervator_watchdog.py sits at the repo root, outside collect_submodules('src').
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
    # No module in src/, tools/, main.py or acervator_watchdog.py imports pandas or ta.
    "pandas",
    "numpy",
    "ta",
    "aiohttp",
    # src/core/settings.py names tomli only in the ImportError arm under tomllib.
    "tomli",
    "tomli_w",
    "psutil",
    # src/gui/crypto_news_ticker.py raises ImportError at module import without it.
    "defusedxml",
    "defusedxml.ElementTree",
)

# keyring picks its backend at run time from whichever one it can import.
KEYRING_BACKENDS: dict[str, str] = {
    "windows": "keyring.backends.Windows",
    "macos": "keyring.backends.macOS",
}


def hiddenimports_for(platform: str) -> list[str]:
    """Return ``COMMON_HIDDENIMPORTS`` plus the ``KEYRING_BACKENDS`` entry named.

    Raises ``ValueError`` for a ``platform`` ``KEYRING_BACKENDS`` does not hold.
    """
    try:
        backend = KEYRING_BACKENDS[platform]
    except KeyError:
        raise ValueError(
            f"unknown spec platform {platform!r}; "
            f"expected one of {sorted(KEYRING_BACKENDS)}"
        ) from None
    return [*COMMON_HIDDENIMPORTS, backend]


# Both specs exclude these; matplotlib is here and src/design_system.py imports it.
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
