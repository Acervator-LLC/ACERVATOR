"""v3.23.50 — pin tests for the Indicator Voting Panel layout
optimisation (operator directive 2026-07-28).

Locks:
  1. gwei-per-dollar / gwei-per-cent derivation in CurrencyRateMonitor.
  2. Rate-strip formatter emits "gwei" (not "wei") and integer-with-commas.
  3. Bar-chart paintEvent no longer draws per-bar % labels above bars
     — asserted by grepping the source for the retired code block.
  4. Bar-chart no longer uses table column positions for alignment
     — asserted by grepping the source for the retired code path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.currency_rate_monitor import (  # noqa: E402
    CurrencyRateMonitor,
    CurrencyRates,
    WEI_PER_GWEI,
    WEI_PER_ETH,
)

# -----------------------------------------------------------------
# 1. gwei derivation math
# -----------------------------------------------------------------


class TestGweiDerivation:
    def test_wei_per_gwei_constant(self):
        assert WEI_PER_GWEI == 10**9

    def test_gwei_computed_when_eth_present(self):
        mon = CurrencyRateMonitor()
        snap = mon.update_from_prices(50_000.0, 3000.0)
        # wei_per_dollar = 1e18 / 3000 ≈ 3.333e14
        # gwei_per_dollar = wei_per_dollar / 1e9 ≈ 333_333
        assert snap.gwei_per_dollar == pytest.approx(
            WEI_PER_ETH / 3000.0 / WEI_PER_GWEI, rel=1e-6
        )
        assert snap.gwei_per_dollar == pytest.approx(333_333.333, rel=1e-4)

    def test_gwei_per_cent_is_hundredth_of_dollar(self):
        mon = CurrencyRateMonitor()
        snap = mon.update_from_prices(50_000.0, 3000.0)
        assert snap.gwei_per_cent == pytest.approx(snap.gwei_per_dollar * 0.01)

    def test_gwei_zero_when_eth_zero(self):
        mon = CurrencyRateMonitor()
        snap = mon.update_from_prices(50_000.0, 0.0)
        assert snap.gwei_per_dollar == 0.0
        assert snap.gwei_per_cent == 0.0

    def test_snapshot_default_values(self):
        r = CurrencyRates()
        assert r.gwei_per_dollar == 0.0
        assert r.gwei_per_cent == 0.0

    def test_operator_scenario_1888_usd_eth(self):
        """Operator's actual screenshot had ETH ≈ $1,887.97 producing
        the offending '5.297e+14 wei/$' readout. Confirm the new gwei
        rendering is ~530,000 gwei/$ — integer with commas."""
        mon = CurrencyRateMonitor()
        snap = mon.update_from_prices(63_835.55, 1887.97)
        # 1e18 / 1887.97 / 1e9 ≈ 529,669  (well under 530,000)
        assert 529_000 < snap.gwei_per_dollar < 530_000
        assert f"{snap.gwei_per_dollar:,.0f}" == "529,669"


# -----------------------------------------------------------------
# 2. paintEvent source discipline (retired features stay retired)
# -----------------------------------------------------------------


class TestPaintEventDiscipline:
    """We can't easily assert Qt paint output from a headless test, but
    we CAN assert the retired code paths have not returned. The
    module's source is the source of truth for these disciplines."""

    def _src(self) -> str:
        p = REPO / "src" / "gui" / "indicator_panel.py"
        return p.read_text(encoding="utf-8")

    def test_per_bar_percent_label_removed(self):
        src = self._src()
        # The retired snippet was:
        #   p.drawText(QRectF(label_x, y - 14, label_w, 13),
        #              Qt.AlignCenter, f"{conf:.0%}")
        # We assert neither of the two-together fragments remains in
        # the bar-chart paintEvent region.
        assert 'f"{conf:.0%}"' not in src, (
            "Per-bar % label above each bar has returned — operator "
            "directive 2026-07-28 required removal (visual redundancy)."
        )

    def test_use_cols_alignment_restored(self):
        """v3.23.53 — bar chart alignment to table columns was
        RESTORED per operator directive 2026-07-28: 'columns should
        always fit under and never exceed the width of their
        respective readouts'. Assert paint-time branch + sync
        helper are present."""
        src = self._src()
        assert "use_cols = (" in src, (
            "Bar-chart column-alignment branch is missing — needed "
            "so bar[i] centers under table-column[i+1]."
        )
        assert (
            "def _sync_bars_for" in src
        ), "Per-mini-panel sync helper _sync_bars_for missing."


# -----------------------------------------------------------------
# 3. Live-render smoke — panel instantiates, layout is well-formed
# -----------------------------------------------------------------


class TestLiveRender:
    """Headless-Qt smoke. Skipped when PySide6 isn't importable."""

    def test_layout_has_bar_chart_with_stretch(self):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.indicator_panel import IndicatorVotingPanel, ConfidenceBarsWidget

        panel = IndicatorVotingPanel()
        # v3.23.52 — bars live inside mini-panel containers now, so
        # walk findChildren rather than direct children.
        found = panel.findChildren(ConfidenceBarsWidget)
        assert len(found) == 2, (
            "IndicatorVotingPanel must contain exactly TWO "
            "ConfidenceBarsWidget instances (one per mini-panel), "
            f"found {len(found)}."
        )

    def test_rate_strip_emits_gwei_not_wei(self):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.indicator_panel import IndicatorVotingPanel

        panel = IndicatorVotingPanel()
        mon = CurrencyRateMonitor()
        snap = mon.update_from_prices(63_835.55, 1887.97)
        panel.update_currency_rates(snap)
        text = panel._rate_strip.text()
        assert "gwei" in text, f"Rate strip should mention 'gwei' (got: {text!r})"
        assert "wei" not in text.replace(
            "gwei", ""
        ), f"Rate strip should not use raw 'wei' — only 'gwei'. Got: {text!r}"
        # Should have integer-with-commas: like "529,661 gwei"
        assert (
            "529,669 gwei" in text
        ), f"Expected 529,669 gwei/$ integer readout, got: {text!r}"

    def test_data_row_height_is_legible(self):
        """v3.23.50.1 — the row-height floor must be ≥ 28 px so the
        data row can display arrows + percentage text. Regression
        pin against the initial v3.23.50 bug where setFixedHeight
        ran before cells populated and clipped the row to a sliver."""
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.indicator_panel import IndicatorVotingPanel

        panel = IndicatorVotingPanel()
        panel.resize(950, 720)
        vhdr = panel._table.verticalHeader()
        # Floor at 28 px per row — populated cells always render fully.
        assert vhdr.defaultSectionSize() >= 28, (
            f"Row default size {vhdr.defaultSectionSize()} < 28 — "
            "data row will clip its arrow/percentage content, "
            "regressing the invisible-sliver bug from v3.23.50."
        )
        assert vhdr.minimumSectionSize() >= 28, (
            f"Row min size {vhdr.minimumSectionSize()} < 28 — "
            "even if user resizes, cell content can be clipped."
        )

    def test_bars_center_under_their_table_columns(self):
        """v3.23.53 — for each indicator bar in each mini-panel, the
        bar's centre must sit within ±3 px of the table-column
        centre above it, AND the bar's width must not exceed the
        column's width. Operator directive 2026-07-28: 'columns
        should always fit under and never exceed the width of
        their respective readouts'."""
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        _app = QApplication.instance() or QApplication([])
        from src.gui.indicator_panel import IndicatorVotingPanel

        panel = IndicatorVotingPanel()
        panel.resize(950, 780)
        # Minimum fake TF payload — signals list is enough to
        # trigger update_data's populate path.
        fake = {
            "5m": {
                "bullish": 3,
                "bearish": 5,
                "neutral": 4,
                "net_score": -1.0,
                "confidence": 0.10,
                "signals": [
                    {
                        "indicator": k,
                        "direction": "NEUTRAL",
                        "confidence": 0.2,
                        "details": {},
                    }
                    for k in (
                        "bollinger_bands",
                        "vortex",
                        "macd",
                        "stochastic_rsi",
                        "ichimoku",
                        "volume",
                        "slingshot",
                        "adx",
                        "supertrend",
                        "zscore",
                        "kaufman_er",
                        "rsi",
                    )
                ],
            }
        }
        panel.update_data(fake, symbol="TEST/USD")
        panel.show()
        _app.processEvents()
        _app.processEvents()  # drain the QTimer.singleShot(0)

        def _check(row_name, table, bars, first_indicator_col=1, last_indicator_col=6):
            hdr = table.horizontalHeader()
            for col in range(first_indicator_col, last_indicator_col + 1):
                hdr_x = hdr.sectionPosition(col)
                hdr_w = hdr.sectionSize(col)
                hdr_center = hdr_x + hdr_w / 2
                bx, bw = bars._col_positions[col]
                bar_center = bx + bw / 2
                dx = abs(bar_center - hdr_center)
                assert dx < 3, (
                    f"{row_name} col {col} bar mis-centered by {dx:.1f}px "
                    f"(header_center={hdr_center}, bar_center={bar_center})"
                )
                assert bw <= hdr_w + 1, (
                    f"{row_name} col {col} bar cell width {bw}px "
                    f"exceeds header width {hdr_w}px "
                    f"(operator directive: columns must not exceed readout width)."
                )

        _check("Row A", panel._table_a, panel._conf_bars_a)
        _check("Row B", panel._table_b, panel._conf_bars_b)

    def test_two_symmetric_mini_panels_present(self):
        """v3.23.52 — panel must expose _table_a, _table_b,
        _conf_bars_a, _conf_bars_b (each is one half of the two
        symmetrical rows). Guards against a regression to the
        single-table layout."""
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.indicator_panel import IndicatorVotingPanel

        panel = IndicatorVotingPanel()
        for attr in ("_table_a", "_table_b", "_conf_bars_a", "_conf_bars_b"):
            assert hasattr(panel, attr), (
                f"IndicatorVotingPanel missing {attr!r} — "
                "the two-row symmetrical split has regressed."
            )
        # Row A has 10 cols: TF + 6 indicators + Net + CompNet + Conf
        assert panel._table_a.columnCount() == 10, (
            f"Row A table col count = {panel._table_a.columnCount()}, "
            "expected 10 (TF + 6 indicators + Net + CompNet + Conf)."
        )
        # Row B has 7 cols: TF + 6 indicators
        assert panel._table_b.columnCount() == 7, (
            f"Row B table col count = {panel._table_b.columnCount()}, "
            "expected 7 (TF + 6 indicators)."
        )
