"""Structural parity pin — Acervator_win.spec vs Acervator_mac.spec.

Reason this exists: on 2026-06-18 we found the mac spec had rotted for
~2 months. It called `_build_graceful_datas()` and `ACERVATOR_VERSION`
without defining either, so PyInstaller would abort with `NameError`
before producing anything. The Windows spec had both — the two files
had drifted silently because no test compared them.

These pins are static (regex + AST-free string checks). They do NOT
run PyInstaller. They catch the drift class where one spec grows a
required helper or hidden import and the other spec doesn't.

If a legitimate divergence is needed (e.g., mac ships extra frameworks
Windows can't), add it here as an explicit `# platform-only:` allowance
so the reason is recorded.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WIN_SPEC = REPO / "Acervator_win.spec"
MAC_SPEC = REPO / "Acervator_mac.spec"


@pytest.fixture(scope="module")
def win_src() -> str:
    return WIN_SPEC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def mac_src() -> str:
    return MAC_SPEC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Both files must exist
# ---------------------------------------------------------------------------


class TestSpecsExist:
    def test_win_spec_present(self):
        assert WIN_SPEC.is_file(), f"missing {WIN_SPEC}"

    def test_mac_spec_present(self):
        assert MAC_SPEC.is_file(), f"missing {MAC_SPEC}"

    def test_build_mac_script_present(self):
        assert (REPO / "build_mac.sh").is_file(), "build_mac.sh missing"


# ---------------------------------------------------------------------------
# Both specs must define + use the same version-reading helper
# ---------------------------------------------------------------------------


class TestVersionHelper:
    def test_win_defines_read_version(self, win_src):
        assert "def _read_acervator_version" in win_src

    def test_mac_defines_read_version(self, mac_src):
        assert "def _read_acervator_version" in mac_src, (
            "mac spec must define _read_acervator_version like the win spec — "
            "otherwise ACERVATOR_VERSION references will NameError at build."
        )

    def test_win_assigns_acervator_version(self, win_src):
        assert re.search(r"^ACERVATOR_VERSION\s*=", win_src, re.MULTILINE)

    def test_mac_assigns_acervator_version(self, mac_src):
        assert re.search(
            r"^ACERVATOR_VERSION\s*=", mac_src, re.MULTILINE
        ), "mac spec must assign ACERVATOR_VERSION at module scope."

    def test_mac_uses_acervator_version_in_bundle(self, mac_src):
        """The BUNDLE section must populate CFBundleVersion and
        CFBundleShortVersionString from ACERVATOR_VERSION (not a
        hardcoded literal like '1.1.0')."""
        assert "CFBundleVersion" in mac_src
        assert "CFBundleShortVersionString" in mac_src
        # Both should reference ACERVATOR_VERSION, not a literal
        assert re.search(
            r"CFBundleVersion['\"]\s*:\s*ACERVATOR_VERSION", mac_src
        ), "CFBundleVersion must be ACERVATOR_VERSION, not a hardcoded literal"
        assert re.search(
            r"CFBundleShortVersionString['\"]\s*:\s*ACERVATOR_VERSION", mac_src
        ), "CFBundleShortVersionString must be ACERVATOR_VERSION"

    def test_mac_bundle_version_arg_uses_acervator_version(self, mac_src):
        """BUNDLE(version=...) must be ACERVATOR_VERSION, not a literal."""
        m = re.search(r"BUNDLE\((.*?)\)\s*\Z", mac_src, re.DOTALL)
        assert m, "could not locate BUNDLE(...) block"
        bundle = m.group(1)
        assert re.search(
            r"version\s*=\s*ACERVATOR_VERSION", bundle
        ), "BUNDLE(version=...) must be ACERVATOR_VERSION."
        assert not re.search(
            r"version\s*=\s*['\"]\d+\.\d+\.\d+['\"]", bundle
        ), "BUNDLE(version=...) must not use a hardcoded version literal."


# ---------------------------------------------------------------------------
# Both specs must define + use the same datas helper
# ---------------------------------------------------------------------------


class TestGracefulDatasHelper:
    def test_win_defines_graceful_datas(self, win_src):
        assert "def _build_graceful_datas" in win_src

    def test_mac_defines_graceful_datas(self, mac_src):
        assert (
            "def _build_graceful_datas" in mac_src
        ), "mac spec must define _build_graceful_datas like the win spec."

    def test_win_calls_graceful_datas(self, win_src):
        assert "_build_graceful_datas(PROJECT_ROOT)" in win_src

    def test_mac_calls_graceful_datas(self, mac_src):
        assert "_build_graceful_datas(PROJECT_ROOT)" in mac_src

    def test_both_probe_raintsimbat(self, win_src, mac_src):
        """RAIntSimBat parity — both specs must probe the sadp-relocated
        path first then fall back to the root-level legacy path."""
        for label, src in [("win", win_src), ("mac", mac_src)]:
            assert (
                "RAIntSimBat" in src
            ), f"{label} spec must reference RAIntSimBat datas"
            assert (
                "sadp" in src
            ), f"{label} spec must probe the sadp/ location before legacy"


# ---------------------------------------------------------------------------
# Hidden-imports parity (excluding the intentional platform difference)
# ---------------------------------------------------------------------------


# The single legitimate platform difference: keyring backend.
_PLATFORM_ONLY = {"keyring.backends.Windows", "keyring.backends.macOS"}


def _extract_hiddenimports(src: str) -> set[str]:
    """Pull every quoted string that appears inside the Analysis(...)
    call's `hiddenimports=(...)` argument."""
    # Grab the hiddenimports=(...) block (it wraps a tuple with a
    # list concat, so we take the outer parenthesized region).
    m = re.search(
        r"hiddenimports=\(\s*(?:# .*\n\s*)*collect_submodules\(['\"]src['\"]\)\s*\+\s*\[(.*?)\]",
        src,
        re.DOTALL,
    )
    assert m, "could not locate hiddenimports=(collect_submodules('src') + [...]) block"
    block = m.group(1)
    return set(re.findall(r"['\"]([A-Za-z0-9_.]+)['\"]", block))


class TestHiddenImports:
    def test_win_uses_collect_submodules(self, win_src):
        assert "collect_submodules('src')" in win_src

    def test_mac_uses_collect_submodules(self, mac_src):
        assert "collect_submodules('src')" in mac_src

    def test_hiddenimports_match_ignoring_platform(self, win_src, mac_src):
        win_imports = _extract_hiddenimports(win_src)
        mac_imports = _extract_hiddenimports(mac_src)

        # Strip the platform-specific keyring backend from each.
        win_common = win_imports - _PLATFORM_ONLY
        mac_common = mac_imports - _PLATFORM_ONLY

        only_win = win_common - mac_common
        only_mac = mac_common - win_common
        assert not only_win, (
            f"win-only hiddenimports (must be added to mac spec or "
            f"whitelisted here): {sorted(only_win)}"
        )
        assert not only_mac, (
            f"mac-only hiddenimports (must be added to win spec or "
            f"whitelisted here): {sorted(only_mac)}"
        )

    def test_watchdog_present_both(self, win_src, mac_src):
        """MEM-219 — self-supervising watchdog module. Must ship in both."""
        assert "acervator_watchdog" in win_src
        assert "acervator_watchdog" in mac_src, (
            "acervator_watchdog missing from mac spec — watchdog would be "
            "silently dropped from the .app bundle."
        )

    def test_win_uses_windows_backend(self, win_src):
        assert "keyring.backends.Windows" in win_src

    def test_mac_uses_macos_backend(self, mac_src):
        assert "keyring.backends.macOS" in mac_src


# ---------------------------------------------------------------------------
# Excludes parity
# ---------------------------------------------------------------------------


def _extract_excludes(src: str) -> set[str]:
    m = re.search(r"excludes=\[(.*?)\]", src, re.DOTALL)
    assert m, "excludes=[...] block missing"
    return set(re.findall(r"['\"]([A-Za-z0-9_.]+)['\"]", m.group(1)))


class TestExcludes:
    def test_excludes_match(self, win_src, mac_src):
        w = _extract_excludes(win_src)
        m = _extract_excludes(mac_src)
        assert w == m, (
            f"excludes lists must match. win-only={sorted(w-m)}, "
            f"mac-only={sorted(m-w)}"
        )


# ---------------------------------------------------------------------------
# Entry point parity
# ---------------------------------------------------------------------------


class TestEntryPoint:
    def test_both_use_main_py(self, win_src, mac_src):
        for label, src in [("win", win_src), ("mac", mac_src)]:
            assert (
                "'main.py'" in src or '"main.py"' in src
            ), f"{label} spec must build from main.py"
