"""Source-of-truth pins for the Bot Details Status tab fields.

Locks the P1/P2/P3 fixes from the 2026-07-25 Status tab audit:
  P1 — active_buy_orders + active_sell_orders are populated from
       exchange.get_open_orders in refresh_exchange_position_health.
  P2 — Unrealised P/L computation prefers stats.cost_basis_total_exchange
       when it's fresh; falls back to internal _main_lots otherwise.
  P3 — get_status returns stats.total_trades from exchange_trade_count
       when the exchange refresh has landed.

These are AST/source-shape tests so they don't require a running Qt
app, a live exchange, or a fully-constructed bot. They pin the
STRUCTURE of the fix so a future refactor can't silently regress the
audit findings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRUMMING = REPO / "src" / "trading" / "scrumming_bot.py"
CONTAINER = REPO / "src" / "trading" / "bot_container.py"
CONTAINER_PKG = REPO / "src" / "trading" / "container"


@pytest.fixture(scope="module")
def scrumming_source() -> str:
    return SCRUMMING.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def container_source() -> str:
    parts = [CONTAINER.read_text(encoding="utf-8", errors="replace")]
    parts += [
        p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(CONTAINER_PKG.glob("*.py"))
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# P1 — active_buy_orders / active_sell_orders populated by exchange refresh
# ---------------------------------------------------------------------------


class TestP1_ActiveOrdersWired:
    def test_get_open_orders_called_in_scrumming_bot(self, scrumming_source):
        assert "get_open_orders" in scrumming_source, (
            "scrumming_bot.py must call exchange.get_open_orders to "
            "populate active_buy_orders / active_sell_orders"
        )

    def test_active_buy_orders_assigned(self, scrumming_source):
        assert "self.stats.active_buy_orders =" in scrumming_source, (
            "self.stats.active_buy_orders must be assigned somewhere; "
            "otherwise the field is dead and the Status tab shows 0 forever"
        )

    def test_active_sell_orders_assigned(self, scrumming_source):
        assert "self.stats.active_sell_orders =" in scrumming_source

    def test_open_orders_pull_scoped_to_this_symbol(self, scrumming_source):
        """The get_open_orders call MUST pass self.config.symbol so we
        only count orders for THIS bot's pair. A global fetch would
        conflate every bot on the same exchange."""
        # Simple substring check for the composed form
        assert (
            "get_open_orders(\n                        self.config.symbol)"
            in scrumming_source
            or "get_open_orders(self.config.symbol)" in scrumming_source
        ), (
            "get_open_orders must be called with self.config.symbol to "
            "scope the count to THIS bot's trading pair"
        )

    def test_open_orders_pull_side_filters(self, scrumming_source):
        """The count must filter by OrderSide.BUY / OrderSide.SELL, not
        raw string comparison — string comparison is fragile against
        connector-side casing drift."""
        # Locate the buy count line
        assert "_OS.BUY" in scrumming_source
        assert "_OS.SELL" in scrumming_source


# ---------------------------------------------------------------------------
# P2 — Unrealised P/L prefers exchange cost basis
# ---------------------------------------------------------------------------


class TestP2_UnrealisedCostBasisFromExchange:
    def test_uses_cost_basis_total_exchange_when_available(self, scrumming_source):
        """The Unrealised P/L compute path must reference
        cost_basis_total_exchange, not just the internal _main_lots sum."""
        # Find the unrealised_pnl assignment block
        assert (
            "self.stats.unrealised_pnl = _market_value - _cost_basis"
            in scrumming_source
        )
        # ... and that block must consider the exchange value first
        assert "cost_basis_total_exchange" in scrumming_source

    def test_fallback_to_main_lots_preserved(self, scrumming_source):
        """The fallback to internal _main_lots must still exist so
        freshly-started bots don't show a 0 cost basis before the first
        exchange refresh (which is 5min-throttled)."""
        assert '"initial_buy_price"' in scrumming_source
        assert "_main_lots" in scrumming_source


# ---------------------------------------------------------------------------
# P3 — get_status prefers exchange_trade_count
# ---------------------------------------------------------------------------


class TestP3_GetStatusPrefersExchangeTradeCount:
    def test_get_status_references_exchange_trade_count(self, container_source):
        """bot_container.py get_status must use exchange_trade_count for
        the 'total_trades' key when it's fresh."""
        assert '"total_trades"' in container_source
        # Locate the total_trades line — it must reference both
        # exchange_trade_count AND fall back to total_trades
        assert "exchange_trade_count" in container_source
        assert "exchange_data_fresh_ts" in container_source

    def test_get_status_fallback_to_local_counter(self, container_source):
        """The fallback path must still return self.stats.total_trades
        so bots without any exchange refresh yet still show a count."""
        # Both symbols must appear in the file
        assert "self.stats.total_trades" in container_source


# ---------------------------------------------------------------------------
# Regression pin — dataclass fields must still exist
# ---------------------------------------------------------------------------


class TestBotStatsSchema:
    """If someone removes active_buy_orders / active_sell_orders from
    BotStats, the P1 fix breaks silently at runtime. Pin the fields."""

    def test_stats_has_active_order_fields(self, container_source):
        assert "active_buy_orders: int" in container_source
        assert "active_sell_orders: int" in container_source

    def test_stats_has_exchange_fields(self, container_source):
        assert "realized_pnl_exchange: float" in container_source
        assert "avg_entry_exchange: float" in container_source
        assert "cost_basis_total_exchange: float" in container_source
        assert "fees_paid_exchange: float" in container_source
        assert "exchange_trade_count: int" in container_source
        assert "exchange_data_fresh_ts: float" in container_source


# ---------------------------------------------------------------------------
# v3.23.25 — market_check_interval retirement (Settings § 1 audit 2026-07-25)
# ---------------------------------------------------------------------------


class TestMarketCheckIntervalRetired:
    """market_check_interval was a dead field: declared, passed at
    construction, restored on save, exposed as a Settings widget — but
    NO runtime code ever read it. Operator directive 2026-07-25:
    remove entirely. These pins keep it gone."""

    def test_field_not_declared_on_botconfig(self, container_source):
        """The dataclass must not re-acquire market_check_interval."""
        # Tolerate the removal-note comment; reject any 'name: type' form
        import re

        assert not re.search(
            r"^\s*market_check_interval\s*:\s*int", container_source, re.MULTILINE
        ), "market_check_interval field re-appeared on BotConfig"

    def test_field_not_in_scrumming_only_allowlist(self, container_source):
        """The kwarg allowlist must not include it."""
        import re

        m = re.search(
            r"_BOT_CONFIG_SCRUMMING_ONLY_FIELDS.*?frozenset\(\s*\{(.*?)\}\s*\)",
            container_source,
            re.DOTALL,
        )
        assert m, "SCRUMMING_ONLY_FIELDS allowlist not found"
        assert '"market_check_interval"' not in m.group(1), (
            "market_check_interval re-appeared in the SCRUMMING_ONLY_FIELDS "
            "allowlist — will silently accept the dead kwarg again."
        )

    def test_no_widget_in_settings_tab(self):
        """The Check Interval QSpinBox must not exist in the Settings tab
        _create_settings_tab method."""
        p = REPO / "src" / "gui" / "bot_live_settings.py"
        src = p.read_text(encoding="utf-8", errors="replace")
        # Grab _create_settings_tab body
        i = src.find("def _create_settings_tab")
        assert i > 0
        # Search inside that method (a few thousand chars is enough)
        body = src[i : i + 40000]
        assert (
            "setValue(cfg.market_check_interval)" not in body
        ), "Check Interval widget still populates from cfg.market_check_interval"
        assert (
            '_mark_changed("market_check_interval"' not in body
        ), "Check Interval widget still emits mark_changed with the retired key"

    def test_no_main_window_restore_reference(self):
        """The main_window.py restore path must not pass "
        market_check_interval" as a kwarg to make_bot_config."""
        p = REPO / "src" / "gui" / "main_window.py"
        src = p.read_text(encoding="utf-8", errors="replace")
        # Reject the literal restore-kwarg form
        assert '"market_check_interval": config.get(' not in src, (
            "main_window.py restore path still emits market_check_interval "
            "as a kwarg — will raise TypeError against the new BotConfig."
        )

    def test_no_bot_container_restore_reference(self, container_source):
        assert '"market_check_interval": cfg.get(' not in container_source, (
            "bot_container.py restore path still emits market_check_interval "
            "as a kwarg — will raise TypeError against the new BotConfig."
        )
