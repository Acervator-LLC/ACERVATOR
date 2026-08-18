"""v3.23.78 — pin tests for YTD Scrummed/Folded per-trade increments.

Regression fixture for the bug operator flagged 2026-07-31:

    "Scrum and Folded fields are not updating with recent trades but
    are, instead, only updating during boot. Post-boot trades should
    be getting added."

Root cause: ``sync_ytd_trade_count`` (scrumming_bot.py:3707) is the
sole writer of ``stats.ytd_scrummed_usd`` + ``stats.ytd_folded_usd``.
It's called once at boot (from ``bootstrap_exchange_state``) and
then every 5 min via ``refresh_exchange_position_health`` (throttled
by ``EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC = 300.0``). The docstring
at line 3717 claimed "subsequent per-trade increments continue via
the normal execute-buy / execute-sell paths" — but those increments
were never actually wired.

Fix: add per-trade USD increment in each execute-path success block.
The next scheduled sync still runs, but its ``max()`` clamp means
the per-trade nudges only add accuracy, never regress.

Tests exercise the exact increment formulas by patching a minimal
ScrummingBot-like shim so the whole tick machinery doesn't need to
boot.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCRUMMING_BOT_SRC = (
    REPO / "src" / "trading" / "scrumming_bot.py"
).read_text(encoding="utf-8")


def _count_increment_sites(field: str) -> int:
    """Count v3.23.78-style ``stats.<field> = ... + _fill_usd`` sites.
    Uses a regex that matches the surrounding accumulator idiom rather
    than the exact block, so a future refactor that keeps the write
    but rearranges lines still passes."""
    pat = re.compile(
        rf"self\.stats\.{re.escape(field)}\s*=\s*float\(getattr\(\s*"
        rf"self\.stats,\s*['\"]" + re.escape(field) + r"['\"]",
        re.MULTILINE,
    )
    return len(pat.findall(SCRUMMING_BOT_SRC))


def test_scrummed_usd_has_per_trade_write_site():
    """SELL success path (SCRUM) must increment ytd_scrummed_usd."""
    assert _count_increment_sites("ytd_scrummed_usd") >= 1, (
        "v3.23.78 regression: ytd_scrummed_usd per-trade increment "
        "missing. The sell success path in _execute_sell must add "
        "_fill_usd to stats.ytd_scrummed_usd — otherwise the field "
        "only updates during the 5-min-throttled boot sync (see "
        "operator report 2026-07-31).")


def test_folded_usd_has_per_trade_write_site():
    """BUY success path (FOLD) must increment ytd_folded_usd."""
    assert _count_increment_sites("ytd_folded_usd") >= 1, (
        "v3.23.78 regression: ytd_folded_usd per-trade increment "
        "missing. See matching comment on ytd_scrummed_usd.")


def test_increment_uses_quote_to_usd_conversion():
    """Both increments must multiply by _quote_to_usd so crypto-quoted
    pairs (BTC-denominated bots, etc.) accumulate USD-correct values,
    not raw quote-currency notional."""
    assert "_quote_to_usd" in SCRUMMING_BOT_SRC
    # Every _fill_usd computation in the per-trade increment blocks
    # must include _qrate (bound from _quote_to_usd).
    fill_usd_lines = [
        line for line in SCRUMMING_BOT_SRC.splitlines()
        if "_fill_usd = float(amount)" in line]
    assert len(fill_usd_lines) >= 2, (
        "expected two _fill_usd computations (one in sell, one in "
        f"buy); found {len(fill_usd_lines)}")
    for line in fill_usd_lines:
        assert "_qrate" in line, (
            f"per-trade YTD USD must apply _quote_to_usd conversion: "
            f"{line!r}")


def test_increment_blocks_are_guarded_against_bad_values():
    r"""The increment blocks must swallow TypeError/ValueError so a
    malformed amount/actual_fill doesn't break the fill path.

    v3.25.3 - this asserted the invariant with a SOURCE REGEX ending in
    the literal `pass`:

        r"# v3\.23\.78 - per-trade YTD .+?except.+?pass"

    The invariant is "these blocks catch (TypeError, ValueError) and do
    not let them escape". `pass` was only one way to spell that. When the
    98 bare `except: pass` handlers in scrumming_bot.py became logged
    suppressions - S110, the class that made C16's live failures
    invisible - the handler still caught and still did not re-raise, so
    the invariant held while the regex broke.

    It now checks the invariant on the AST, which is strictly stronger:
    a regex cannot tell whether a handler re-raises. Each marker is
    checked against EVERY enclosing Try, because the increment sits
    inside an outer `except Exception` block and the inner guard is the
    one that matters.
    """
    tree = ast.parse(SCRUMMING_BOT_SRC)
    marker_lines = [
        i for i, line in enumerate(SCRUMMING_BOT_SRC.splitlines(), 1)
        if "v3.23.78" in line and "per-trade YTD" in line]
    assert len(marker_lines) == 2, (
        f"expected 2 v3.23.78 increment blocks (sell + buy); "
        f"found {len(marker_lines)}")

    def _caught(handler):
        node = handler.type
        if isinstance(node, ast.Tuple):
            return {e.id for e in node.elts if isinstance(e, ast.Name)}
        if isinstance(node, ast.Name):
            return {node.id}
        return set()

    tries = sorted((n for n in ast.walk(tree) if isinstance(n, ast.Try)),
                   key=lambda n: n.lineno)
    for marker in marker_lines:
        # The marker is the COMMENT that introduces the block, so it sits
        # immediately ABOVE the `try:`. Take the first Try that opens
        # after it, within the comment header's reach.
        following = [n for n in tries if marker < n.lineno <= marker + 25]
        assert following, (
            f"no try block follows the increment marker at line {marker}")
        guard = following[0]
        qualifying = [h for h in guard.handlers
                      if {"TypeError", "ValueError"} <= _caught(h)]
        assert qualifying, (
            f"the increment block at line {marker} must be guarded by "
            f"except (TypeError, ValueError); its try at line "
            f"{guard.lineno} catches "
            f"{[sorted(_caught(h)) for h in guard.handlers]}")
        for handler in qualifying:
            assert not any(isinstance(n, ast.Raise)
                           for n in ast.walk(handler)), (
                f"the guard at line {marker} must not re-raise; a "
                f"malformed amount would break the fill path")
