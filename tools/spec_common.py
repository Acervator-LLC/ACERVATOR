"""Shared PyInstaller spec content for Acervator_win.spec and Acervator_mac.spec.

``COMMON_HIDDENIMPORTS`` and ``EXCLUDES`` hold the names both spec files pass to
PyInstaller, and ``hiddenimports_for`` adds the one ``KEYRING_BACKENDS`` entry
that is per-platform. ``read_acervator_version`` and ``bake_version_datas``
resolve the version and write it under ``BAKE_SUBDIR`` for the bundle to carry.
``datas_candidates`` ships ``renderer_candidate`` in every variant, because the
Status tab reads ``panel_host.js`` from it under both, and adds
``shell_candidates`` to a ``REACT`` build alone. Nothing here imports
PyInstaller, so the module imports on a machine that has none.
"""

from __future__ import annotations

import os

from src._variant import REACT, normalise
from src._version import BAKED_FILENAME, UNKNOWN_VERSION, resolve_version

FALLBACK_VERSION = UNKNOWN_VERSION

# Regenerable and gitignored; `bake_version_datas` writes nothing into src/.
BAKE_SUBDIR = os.path.join("build", "version")

DESKTOP_DIRNAME = "desktop"
SHELL_RENDERER = "renderer"
SHELL_FILES: tuple[str, ...] = ("main.js", "preload.js", "package.json")

# npm writes this; a clone without `npm install` has the shell and no runtime.
ELECTRON_RUNTIME = os.path.join("node_modules", "electron", "dist")


def read_acervator_version(project_root: str) -> str:
    """Return what ``resolve_version`` answers for the tree at ``project_root``."""
    return resolve_version(project_root)


def bake_version_datas(project_root: str) -> list[tuple[str, str]]:
    """Write ``read_acervator_version`` under ``BAKE_SUBDIR`` and return its pair.

    The destination is ``src``, where ``src/_version.py`` reads ``BAKED_FILENAME``.
    """
    out_dir = os.path.join(project_root, BAKE_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, BAKED_FILENAME)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(read_acervator_version(project_root) + "\n")
    return [(out_path, "src")]


def renderer_candidate(project_root: str) -> tuple[str, str]:
    """The (source, destination) pair of ``SHELL_RENDERER``, which every variant ships.

    ``src/gui/react_main_window.py`` reads ``panel_host.js`` from this folder
    under the bundle root, for the Status tab in both variants.
    """
    desktop = os.path.join(project_root, DESKTOP_DIRNAME)
    return (
        os.path.join(desktop, SHELL_RENDERER),
        os.path.join(DESKTOP_DIRNAME, SHELL_RENDERER),
    )


def shell_candidates(project_root: str) -> list[tuple[str, str]]:
    """Every (source, destination) pair the Electron shell needs beyond ``renderer_candidate``.

    ``SHELL_FILES`` keep the layout ``DESKTOP_DIRNAME`` has on disk, and
    ``ELECTRON_RUNTIME`` carries the electron executable; a ``REACT`` build
    ships them and no other variant does.
    """
    desktop = os.path.join(project_root, DESKTOP_DIRNAME)
    pairs = [(os.path.join(desktop, name), DESKTOP_DIRNAME) for name in SHELL_FILES]
    pairs.append(
        (
            os.path.join(desktop, ELECTRON_RUNTIME),
            os.path.join(DESKTOP_DIRNAME, ELECTRON_RUNTIME),
        )
    )
    return pairs


def datas_candidates(project_root: str, variant: str) -> list[tuple[str, str]]:
    """Every (source, destination) pair a ``variant`` build would ship.

    Every variant ships three directories and ``renderer_candidate``; ``REACT``
    adds ``shell_candidates``, and every other variant returns those four alone.
    """
    pairs = [
        (os.path.join(project_root, "src"), "src"),
        (os.path.join(project_root, "resources"), "resources"),
        # download_archive.py populates data/historical; a build without it works.
        (
            os.path.join(project_root, "data", "historical"),
            os.path.join("data", "historical"),
        ),
        renderer_candidate(project_root),
    ]
    if normalise(variant) == REACT:
        pairs.extend(shell_candidates(project_root))
    return pairs


def build_graceful_datas(project_root: str, variant: str) -> list[tuple[str, str]]:
    """Return the ``datas_candidates`` pairs for ``variant`` whose source exists.

    A missing source is printed and skipped; PyInstaller aborts on one it keeps.
    """
    result = []
    for src_path, dest_path in datas_candidates(project_root, variant):
        if os.path.exists(src_path):
            result.append((src_path, dest_path))
        else:
            print(f"  [spec] Skipping missing optional datas path: {src_path}")
    return result


# A dropped name here fails the frozen application at run time, not the build.
COMMON_HIDDENIMPORTS: tuple[str, ...] = (
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
    # No file in src/, tools/ or main.py imports pandas or ta; numpy is imported.
    "pandas",
    "numpy",
    "ta",
    "aiohttp",
    # `src/core/settings.py` imports tomli only in the tomllib ImportError arm.
    "tomli",
    "tomli_w",
    "psutil",
    # `src/gui/crypto_news_ticker.py` raises ImportError without defusedxml.
    # The frozen build keeps it inside the PYZ, not as an _internal folder.
    "defusedxml",
    "defusedxml.ElementTree",
)

# keyring chooses its backend at run time from what it can import.
KEYRING_BACKENDS: dict[str, str] = {
    "windows": "keyring.backends.Windows",
    "macos": "keyring.backends.macOS",
}


def hiddenimports_for(platform: str) -> list[str]:
    """``COMMON_HIDDENIMPORTS`` plus the ``KEYRING_BACKENDS`` entry for ``platform``.

    Raises ``ValueError`` on a platform ``KEYRING_BACKENDS`` does not name.
    """
    try:
        backend = KEYRING_BACKENDS[platform]
    except KeyError:
        raise ValueError(
            f"unknown spec platform {platform!r}; "
            f"expected one of {sorted(KEYRING_BACKENDS)}"
        ) from None
    return [*COMMON_HIDDENIMPORTS, backend]


# Passed to PyInstaller by both spec files. A name here must not appear in
# pyproject.toml `dependencies`; `pair_selection.py` imports scipy, so it does not.
EXCLUDES: tuple[str, ...] = (
    "tkinter",
    "matplotlib",
    "PIL",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "sphinx",
    "setuptools",
)
