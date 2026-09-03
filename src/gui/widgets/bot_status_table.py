"""Scrumming-bot dashboard table and its column specification."""

from __future__ import annotations

import logging

from ...core.privacy_mask_registry import (
    get_privacy_mask_registry,
    mask_or,
)

from .. import design_system as ds
from ..table_cells import (
    _ammo_price_pool,
    _compose_ammo_cell,
    _compose_table_target_denom_cell,
    _fresh_display_price,
)

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import QPushButton, QTableWidgetItem
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    from . import ColumnSpec, ColumnarTableWidget
    from .bot_selection import _reanchor_bot_selection, _select_row_for_bot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Bot Status Table - clickable rows
    # ---------------------------------------------------------------
    # MEM-236 — columns after operator redesign:
    #   Removed: "State" (redundant with color-coded Mode)
    #   Removed: "Extended" (grid-bot only, always 0 for scrumming)
    #   Added:   "Fire" (Manual Fire button per row)
    # MEM-247 — column swap (Session 26 operator directive):
    #   "P/L" replaced with "Target" (shows configured Target Balance)
    #   "Price" replaced with "Ammo" (abs of target delta; green when
    #   delta>0 meaning Scrum territory / sell surplus, red when delta<0
    #   meaning Fold territory / buy deficit).
    # v3.18.6 — Removed: "Exchange" column. Every row in a given
    #   ExchangeTab is, by construction, on that tab's exchange — the
    #   column was repeating the same value on every row. The tab
    #   label at the top of the QTabWidget already disambiguates.
    # v3.23.49 — Target BTC / Target ETH inserted after Target USD
    # (operator directive 2026-07-28). Fire moved 6→8; Detail 7→9.
    SCRUMMING_COLUMNS = ColumnSpec(
        labels=(
            "Bot ID",
            "Symbol",
            "Mode",
            "Trades",
            "Target",
            "Target BTC",
            "Target ETH",
            "Ammo",
            "Fire",
            "",
        ),
        tooltips={
            0: "Unique identifier for this bot instance",
            1: "Trading pair (Target Asset / Base Currency)",
            2: (
                "Trading mode + current state.\n"
                "Green = RUNNING · Amber = PAUSED · Gray = IDLE/STOPPED\n"
                "Red = ERROR · Orange = COOLDOWN · Cyan = STARTING"
            ),
            3: "Total number of executed buy and sell trades",
            4: "Target Balance — the operator-set balance this bot trades\n"
            "relative to. Hard-capped per MEM-246 Phase B.",
            5: (
                "Target Balance denominated in BTC (target USD ÷ BTC/USD spot).\n"
                "Suffix Δ = 24h % change of <target>/BTC minus 24h % of "
                "<target>/USD.\n"
                "Positive Δ (green) = BTC-quoted pair cheaper in USD terms than USD-quoted.\n"
                "Blank when pair unlisted on this exchange or target is BTC itself."
            ),
            6: (
                "Target Balance denominated in ETH (target USD ÷ ETH/USD spot).\n"
                "Suffix Δ = 24h % change of <target>/ETH minus 24h % of "
                "<target>/USD.\n"
                "Positive Δ (green) = ETH-quoted pair cheaper in USD terms than USD-quoted.\n"
                "Blank when pair unlisted on this exchange or target is ETH itself."
            ),
            7: (
                "Ammo — distance of current position value from Target.\n"
                "Green = surplus above target (Scrum territory, next action = SELL).\n"
                "Red = deficit below target (Fold territory, next action = BUY).\n"
                "Neutral grey = within dust band around target (no action pending)."
            ),
            8: "Manual Fire — force immediate scrum/fold evaluation on next tick",
            9: "Click for full bot detail and status explanation",
        },
        fixed_widths={
            8: ds.TABLE_COL_FIRE_W,
            9: ds.TABLE_COL_DETAIL_W,
        },
    )

    class BotStatusTable(ColumnarTableWidget):
        COLUMN_SPEC = SCRUMMING_COLUMNS
        COLUMNS = SCRUMMING_COLUMNS.labels
        COLUMN_TOOLTIPS = SCRUMMING_COLUMNS.tooltips

        # MEM-236 — Mode cell color mapping. Mirrors the state_colors dict
        # that used to live in the State column. Readable on dark background.
        STATE_COLORS = {
            "running": QColor(ds.SUCCESS),
            "idle": QColor(ds.CARD_METRIC_LABEL),
            "paused": QColor(ds.WARNING),
            "error": QColor(ds.ERROR),
            "cooldown": QColor(ds.WARNING_STRONG),
            "stopped": QColor(ds.TEXT_MUTED),
            "starting": QColor(ds.STATE_STARTING),
        }

        # v3.23.7 — Privacy field id per column. Maps the 7 maskable
        # columns to their registry field ids. Columns 6 (Fire button)
        # and 7 (Detail button) are wired too: Fire masks to "****"
        # text on the button face; Detail is not maskable.
        PRIVACY_FIELD_BY_COL = {
            0: "bot_table.bot_id",
            1: "bot_table.symbol",
            2: "bot_table.mode",
            3: "bot_table.trades",
            4: "bot_table.target",
            5: "bot_table.target",  # target_btc reuses target mask
            6: "bot_table.target",  # target_eth reuses target mask
            7: "bot_table.ammo",
            8: "bot_table.fire",
        }

        def __init__(self, on_bot_clicked=None, on_fire_clicked=None, parent=None):
            super().__init__(parent=parent)
            self._on_bot_clicked = on_bot_clicked
            self._on_fire_clicked = on_fire_clicked
            self._bot_ids = []

            # Last payload seen, so a header-dot toggle repopulates
            # without refetching from the bot manager.
            self._last_statuses: list = []

            # Clicking a maskable column header toggles that column's
            # privacy mask. The Detail column has none and keeps its
            # sort-only behaviour.
            self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

            # Symbol cell (col 1) is a hyperlink to the pair's chart on
            # the bot's exchange.
            self.cellClicked.connect(self._on_cell_clicked)

            # Replaces every header item, so it must follow the base's
            # tooltip pass.
            self._refresh_header_dots()

        # ----- v3.23.7 -----
        def _on_header_clicked(self, col: int) -> None:
            """Toggle the mask for this column's field id, then
            re-populate the table to apply the new state."""
            field_id = self.PRIVACY_FIELD_BY_COL.get(col)
            if not field_id:
                return  # Detail column (col 7) — no mask.
            try:
                reg = get_privacy_mask_registry()
                reg.set_masked(field_id, not reg.is_masked(field_id))
            except Exception:  # R28-OK
                return
            self._refresh_header_dots()
            # Re-populate cells with current statuses so mask_or runs
            # against the new state.
            if self._last_statuses:
                self.update_bots(self._last_statuses)

        def _refresh_header_dots(self) -> None:
            """Paint each maskable column's header with a dot prefix:
            ● (red) for REVEALED, ○ (open circle) for MASKED. Header
            text becomes ``● Bot ID`` / ``○ Bot ID`` etc."""
            try:
                reg = get_privacy_mask_registry()
            except Exception:
                return
            for col, base_label in enumerate(self.COLUMNS):
                field_id = self.PRIVACY_FIELD_BY_COL.get(col)
                if not field_id:
                    self.setHorizontalHeaderItem(col, QTableWidgetItem(base_label))
                    continue
                masked = reg.is_masked(field_id)
                # Visible glyph: ● (filled) = revealed, ○ (hollow) = masked
                glyph = "○" if masked else "●"
                item = QTableWidgetItem(f"{glyph} {base_label}")
                tip = self.COLUMN_TOOLTIPS.get(col, "")
                state_tip = (
                    f"\n\nPrivacy: {'MASKED' if masked else 'REVEALED'} "
                    f"(field {field_id}).\n"
                    "Click this header to toggle."
                )
                item.setToolTip((tip + state_tip).strip())
                self.setHorizontalHeaderItem(col, item)

        # v3.20.5 — Extractor rendering moved to a dedicated
        # ExtractorBotTable class (operator directive 2026-05-23:
        # two-stacked-tables UX). This class now handles SCRUMMING
        # only; ExchangeTab pre-filters by mode before calling
        # update_bots(). The old `_render_extractor_row` helper +
        # `EXTRACTOR_POOL_COLORS` dict moved verbatim into
        # ExtractorBotTable so the pool-color tooltip continues to
        # work in the new home. Numeric-only Pool/Liquid values
        # (no "Chunk:" prefix, no "free / deployed" suffix) per
        # operator's same-day directive.

        def update_bots(self, bot_statuses: list[dict]) -> None:
            # v3.23.7 — remember last payload so header-dot toggle can
            # re-render without refetching from the bot manager.
            self._last_statuses = list(bot_statuses)
            # issue #51 -- READ THE BOT UNDER THE HIGHLIGHT BEFORE THE
            # REWRITE. Once `setRowCount` and `setItem` have run there
            # is no way back from a row index to the bot that was on
            # it. Restored by `_reanchor_bot_selection` at the end of
            # this method.
            _selected_before = self.get_selected_bot_id()
            self.setRowCount(len(bot_statuses))
            self._bot_ids = []
            for row, status in enumerate(bot_statuses):
                stats = status.get("stats", {})
                bid = status.get("bot_id", "")
                self._bot_ids.append(bid)
                state = status.get("state", "")
                mode = status.get("mode", "")
                # v3.20.5 — Extractor branch removed. ExchangeTab now
                # pre-filters statuses by mode and routes Extractors
                # to ExtractorBotTable. Any non-SCRUMMING status that
                # reaches this point is a routing bug — log + skip
                # rather than try to render in the wrong column shape.
                if mode != "scrumming":
                    import logging as _l

                    _l.getLogger(__name__).warning(
                        "BotStatusTable.update_bots received non-scrumming "
                        "status (mode=%r bot=%r) — should have been routed "
                        "to ExtractorBotTable. Skipping row.",
                        mode,
                        bid[:8] if bid else "?",
                    )
                    continue
                # MEM-247 — Target + Ammo (Session 26 operator directive).
                # Target = operator-set balance this bot trades relative to.
                # Ammo = abs(position_value - target); sign drives color:
                #   delta > dust  → green (Scrum territory, sell surplus)
                #   delta < -dust → red   (Fold territory, buy deficit)
                #   |delta| <= dust → neutral (no action pending)
                # v3.24.53 — the Ammo must be measured against the target
                # the ENGINE will re-zero to, not the operator's config
                # input.
                #
                # This read `status["target_balance"]`, which is
                # `config.target_balance` — frozen, and not moved by
                # compounding. `_execute_manual_rebalance` sizes its
                # trade from `self._target_balance`, the LIVE grown
                # value. So the Ammo showed the distance to one target
                # while Manual Fire re-zeroed to another, and the trade
                # differed from the readout by exactly the accrued
                # growth.
                #
                # Operator-reported as "strange, intermittent and hard to
                # explain amounts". Intermittent is the tell: measured
                # 2026-08-06, 26 of 35 bots had accrued growth and were
                # mismatched, 9 had none and behaved perfectly. Largest
                # gap CAP/USD $5.41 on a $50 target — 10.83%.
                #
                # Falls back to the config value when the live key is
                # absent, so a bot type that does not export it renders
                # exactly as before rather than reading 0.
                target_val = float(
                    status.get("live_target_balance", status.get("target_balance", 0.0))
                    or status.get("target_balance", 0.0)
                    or 0.0
                )
                # MEM-248 Ammo rogue-number rewrite. Operator caught the
                # previous fix HIDING real exposure: an XRP bot that held
                # 104.8 XRP (≈$149.85 — deep Scrum territory) rendered as
                # Ammo $0.00 "at center line" because stats.position_value
                # hadn't been written by the tick loop yet. Lesson: never
                # infer "at center line" from a stale stats field. Compute
                # position fresh from current_holdings × current_price. If
                # either component is missing, show a forthright "pending"
                # marker — do NOT silently report $0.
                stats_pv = float(stats.get("position_value", 0.0))
                holdings = float(status.get("current_holdings", 0.0))
                # v3.24.xx — prefer the shared pool's ticker for DISPLAY.
                # stats.current_price only refreshes on an ungated tick
                # (``ScrummingBot.tick``, ``src/trading/scrumming_bot.py``),
                # measured at 60s on 29 bots and
                # 300s on 6, while this cell repaints every 2s. The bulk
                # refresher keeps the pool warm at ~5s. Display only --
                # the trading path still reads stats.current_price.
                cur_price, _price_age = _fresh_display_price(
                    _ammo_price_pool(),
                    str(status.get("exchange", "") or ""),
                    str(status.get("symbol", "") or ""),
                    float(stats.get("current_price", 0.0)),
                )
                # v3.15.55 — quote→USD multiplier (operator directive
                # 2026-04-25: crypto-quoted pairs like BTC/ETH must
                # evaluate Target Balance in USD even though trades
                # execute in base currency). For USD-quoted pairs the
                # bot exports 1.0 here, so the math is unchanged.
                qrate = float(status.get("quote_to_usd", 1.0) or 1.0)
                _ammo = _compose_ammo_cell(
                    stats_pv,
                    holdings,
                    cur_price,
                    qrate,
                    target_val,
                    price_age_s=_price_age,
                )
                ammo_color = QColor(_ammo["color"])
                ammo_tip = _ammo["tip"]
                ammo_text = _ammo["text"]

                # MEM-250: Ammo + Target are DISTANCE-FROM-ZERO magnitudes.
                # Color already encodes direction (green=Scrum, red=Fold), so
                # no ± sign on the numbers — redundant noise. Target is always
                # positive by definition; also rendered unsigned for visual
                # consistency.
                def _mag(v: float) -> str:
                    return f"${abs(v):,.4f}"

                target_text = _mag(target_val) if target_val > 0 else "---"
                # v3.23.49 — Target BTC / Target ETH cell text + color.
                # Reads from MarketPairsScout + CurrencyRateMonitor.
                # Blank for self-reference (BTC bot → no Target BTC row)
                # or when pair not listed on this exchange.
                symbol = status.get("symbol", "") or ""
                base_asset = symbol.split("/")[0].upper() if "/" in symbol else ""
                exchange_id = status.get("exchange", "") or ""
                target_btc_text, target_btc_color = _compose_table_target_denom_cell(
                    "BTC", base_asset, exchange_id, target_val
                )
                target_eth_text, target_eth_color = _compose_table_target_denom_cell(
                    "ETH", base_asset, exchange_id, target_val
                )
                # v3.23.49 — columns: BotID, Symbol, Mode, Trades,
                # Target USD, Target BTC, Target ETH, Ammo, Fire, Detail.
                # v3.23.7 — each maskable cell passes through mask_or().
                # The Fire button text is masked separately below (see
                # ``fire_btn.setText`` block) because it's a widget, not
                # a QTableWidgetItem.
                items = [
                    mask_or(bid, "bot_table.bot_id"),
                    mask_or(status.get("symbol", ""), "bot_table.symbol"),
                    mask_or(mode, "bot_table.mode"),
                    mask_or(str(stats.get("total_trades", 0)), "bot_table.trades"),
                    mask_or(target_text, "bot_table.target"),
                    mask_or(target_btc_text, "bot_table.target"),
                    mask_or(target_eth_text, "bot_table.target"),
                    mask_or(ammo_text, "bot_table.ammo"),
                    "",  # Fire button placeholder (col 8)
                    "",  # Detail button placeholder (col 9)
                ]
                for col, text in enumerate(items):
                    if col in (8, 9):
                        continue  # Buttons handled below
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    # v3.18.6 — coin logo on Symbol column (idx 1 after
                    # Exchange removal).
                    if col == 1 and text:
                        try:
                            base = text.split("/")[0] if "/" in text else text
                            from ..bot_wizard import _get_coin_icon

                            icon = _get_coin_icon(base, 18, download=False)
                            if icon:
                                item.setIcon(icon)
                        except Exception:  # noqa: S110
                            pass
                        # v3.23.54 — Symbol cell becomes a hyperlink
                        # to the pair chart on the bot's exchange.
                        # Store (exchange_id, raw_symbol) in UserRole
                        # so _on_cell_clicked can build the URL. Style
                        # as underlined cyan when a chart URL is
                        # available; leave uncolored when not.
                        try:
                            from ...exchange.exchange_chart_urls import (
                                chart_url as _chart_url,
                            )

                            _url = _chart_url(
                                exchange_id, status.get("symbol", "") or ""
                            )
                            if _url:
                                from PySide6.QtCore import Qt as _Qt

                                item.setData(_Qt.UserRole, _url)
                                item.setForeground(QColor(ds.TEXT_INFO_SOFT))
                                _f = item.font()
                                _f.setUnderline(True)
                                item.setFont(_f)
                                item.setToolTip(
                                    f"Open chart on {exchange_id} "
                                    f"in default browser: {_url}"
                                )
                        except (
                            Exception
                        ) as _chart_url_exc:  # noqa: BLE001 - chart-URL best-effort
                            # DEBUG: cosmetic only. The cell keeps its
                            # plain text and stays un-clickable; no data
                            # the operator trades on is lost. Log the
                            # exception alone — the status dict is what
                            # may be malformed, so touching it here
                            # would let the handler raise in turn.
                            logger.debug(
                                "Chart-URL decoration skipped: %s: %s",
                                type(_chart_url_exc).__name__,
                                _chart_url_exc,
                            )
                    # v3.18.6 — color-code Mode cell (col 2 after Exchange
                    # removal) based on bot state.
                    if col == 2:
                        color = self.STATE_COLORS.get(state, QColor(ds.TEXT_HIGH))
                        item.setForeground(color)
                        # Tooltip on the cell shows the actual state text
                        item.setToolTip(
                            f"Mode: {mode}\nState: {state.upper() if state else 'UNKNOWN'}"
                        )
                    # v3.23.49 — Target BTC / Target ETH cell coloring
                    # (cols 5, 6). Colour comes from _compose_table_...
                    # (green on positive Δ, red on negative, grey when
                    # divergence < 0.1 % or when the cell is blank).
                    if col == 5:
                        item.setForeground(QColor(target_btc_color))
                    if col == 6:
                        item.setForeground(QColor(target_eth_color))
                    # v3.23.49 — Ammo cell coloring shifted from col 5 → 7
                    # after Target BTC + Target ETH inserted. Green/red/
                    # neutral driven by delta sign.
                    if col == 7:
                        item.setForeground(ammo_color)
                        item.setToolTip(ammo_tip)
                    self.setItem(row, col, item)

                # MEM-236 — Fire button (col 7). Scrumming bots only;
                # grid bots show a disabled placeholder.
                # MEM-239 + MEM-241 — styling hierarchy based on
                # (armed_action, scrum_target_mode):
                #
                #   Disabled                                → gray
                #   armed_action == "scrum"                 → red glow  (sell to rebalance)
                #   armed_action == "fold"                  → green glow (buy to rebalance)
                #   scrum_phase == "fire" but within dust   → amber glow (organic approach, no rebalance need)
                #   scrum_phase == "track"                  → amber text (aiming)
                #   scrum_phase == "search" / None          → subdued red text (idle)
                #
                # MEM-241: Manual Fire is a rebalance-to-target; the
                # button's fill color tells the operator what direction
                # the rebalance will take BEFORE they click.
                scrum_phase = status.get("scrum_target_mode")
                armed_action = status.get("armed_action")
                # MEM-244 — Risk Control readings for tooltip + visual cues
                ceiling_enabled = status.get("position_ceiling_enabled", False)
                ceiling_ratio = status.get("ceiling_ratio")
                ceiling_usd = status.get("position_ceiling_usd")
                fold_taper = status.get("fold_rate_taper", 1.0)
                detonation_enabled = status.get("detonation_enabled", False)
                detonation_tf = status.get("detonation_timeframe", "1d")
                # Fold is hard-stopped when ceiling enabled AND ratio >= 1.0
                fold_blocked_by_ceiling = (
                    ceiling_enabled
                    and ceiling_ratio is not None
                    and ceiling_ratio >= 1.0
                )
                # v3.23.7 — Fire button face passes through mask_or so
                # the "Fire" word becomes "****" when bot_table.fire is
                # masked. The button stays clickable — masking is a
                # display concern, not a permission gate.
                fire_btn = QPushButton(mask_or("Fire", "bot_table.fire"))
                fire_btn.setFixedHeight(22)
                # v3.20.62 — bug-3 fix: prevent Fire-button focus
                # from triggering QTableWidget auto-scroll. When a
                # cell widget grabs focus, Qt's autoScroll calls
                # ensureVisible() which jumps the table. NoFocus
                # blocks the focus grab entirely. Operator-reported.
                fire_btn.setFocusPolicy(Qt.NoFocus)
                is_scrumming = mode == "scrumming"
                is_active = state in ("running", "paused")
                fire_btn.setEnabled(is_scrumming and is_active)
                if is_scrumming and is_active:
                    # Helper to apply a glow effect with a given color.
                    def _apply_glow(color_hex: str) -> None:
                        try:
                            from PySide6.QtWidgets import QGraphicsDropShadowEffect
                            from PySide6.QtGui import QColor as _QC

                            glow = QGraphicsDropShadowEffect(fire_btn)
                            glow.setColor(_QC(color_hex))
                            glow.setBlurRadius(18)
                            glow.setOffset(0, 0)
                            fire_btn.setGraphicsEffect(glow)
                            try:
                                _root = self.window()
                                if hasattr(_root, "_register_fire_glow"):
                                    _root._register_fire_glow(glow)
                            except Exception:  # noqa: S110
                                pass
                        except Exception:  # noqa: S110
                            pass

                    # MEM-244 — Build a tooltip suffix summarizing risk
                    # controls. Appended to whatever base tooltip the
                    # armed/phase branch sets below.
                    def _risk_suffix() -> str:
                        parts = []
                        if ceiling_enabled and ceiling_ratio is not None:
                            pct = ceiling_ratio * 100
                            if fold_blocked_by_ceiling:
                                parts.append(
                                    f"\n\n⚠ CEILING REACHED "
                                    f"({pct:.1f}% of ${ceiling_usd:.2f}) — "
                                    f"fold hard-stopped, scrum only."
                                )
                            elif ceiling_ratio >= 0.5:
                                parts.append(
                                    f"\n\n⚠ Approaching ceiling "
                                    f"({pct:.1f}% of ${ceiling_usd:.2f}) — "
                                    f"fold rate tapered to {fold_taper*100:.0f}%."
                                )
                            else:
                                parts.append(
                                    f"\n\nCeiling: {pct:.1f}% of "
                                    f"${ceiling_usd:.2f} "
                                    f"(fold rate: {fold_taper*100:.0f}%)."
                                )
                        if detonation_enabled:
                            parts.append(
                                f"\nDetonation armed: monitoring "
                                f"{detonation_tf.upper()} for BULLISH "
                                f"auto-harvest."
                            )
                        return "".join(parts)

                    if armed_action == "scrum":
                        # v3.16.16 — visual disambiguation. Per the
                        # 2026-04-30 conversation, the button needs to
                        # distinguish "auto would fire NOW" (solid) from
                        # "manual override available, auto blocked"
                        # (outline). Read from get_status_dict()["auto_fire"].
                        _af = status.get("auto_fire", {}) or {}
                        _auto_armed_scrum = bool(_af.get("scrum_armed", False))
                        _scrum_blockers = list(_af.get("scrum_blockers", []) or [])
                        if _auto_armed_scrum:
                            # Solid red fill — auto-fire would fire NOW.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.TEXT_MAX}; font-weight: bold; "
                                f"background-color: {ds.MAIN_ALERT_SURFACE}; "
                                f"border: 1px solid {ds.ERROR};"
                            )
                            _apply_glow(ds.ERROR)
                            fire_btn.setToolTip(
                                "ARMED for SCRUM (auto would fire). "
                                "Holdings above target; all gates clear. "
                                "Clicking fires a MARKET sell to "
                                "rebalance back to target." + _risk_suffix()
                            )
                        else:
                            # Outline only — manual override available
                            # but auto-fire is blocked by ≥1 gate.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.ERROR}; font-weight: bold; "
                                "background-color: transparent; "
                                f"border: 1px dashed {ds.ERROR};"
                            )
                            # No glow — visually quieter so operator
                            # sees the difference at a glance.
                            _blockers_text = (
                                "\nBlocked by: " + ", ".join(_scrum_blockers)
                                if _scrum_blockers
                                else ""
                            )
                            fire_btn.setToolTip(
                                "Manual SCRUM override available — "
                                "delta > 0 but auto-fire blocked. "
                                "Clicking fires a MARKET sell sized to "
                                "rebalance back to target (bypasses "
                                "auto's TA/BB/HTF gates)."
                                + _blockers_text
                                + _risk_suffix()
                            )
                    elif armed_action == "fold":
                        # v3.16.16 — visual disambiguation (mirror of
                        # SCRUM side above).
                        _af = status.get("auto_fire", {}) or {}
                        _auto_armed_fold = bool(_af.get("fold_armed", False))
                        _fold_blockers = list(_af.get("fold_blockers", []) or [])
                        if fold_blocked_by_ceiling:
                            # Ceiling already gives this its own visual.
                            # Keep the existing muted-green dashed style.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.TEXT_NEUTRAL}; font-weight: bold; "
                                f"background-color: {ds.STATE_ENGAGED_DIM}; "
                                f"border: 1px dashed {ds.CARD_METRIC_LABEL};"
                            )
                            _apply_glow(ds.STATE_ENGAGED_GLOW)
                            fire_btn.setToolTip(
                                "Fold would be armed, but POSITION "
                                "CEILING has been reached. Fold is "
                                "hard-stopped. Manual Fire will still "
                                "attempt to rebalance (operator "
                                "override bypasses the ceiling)." + _risk_suffix()
                            )
                        elif _auto_armed_fold:
                            # Solid green — auto-fire FOLD would fire NOW.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.TEXT_MAX}; font-weight: bold; "
                                f"background-color: {ds.STATE_ENGAGED}; "
                                f"border: 1px solid {ds.STATE_ARMED};"
                            )
                            _apply_glow(ds.STATE_ARMED)
                            fire_btn.setToolTip(
                                "ARMED for FOLD (auto would fire). "
                                "Holdings below target; all gates clear. "
                                "Clicking fires a MARKET buy to "
                                "rebalance back to target." + _risk_suffix()
                            )
                        else:
                            # Outline only — manual override available
                            # but auto-fire is blocked.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.STATE_ARMED}; font-weight: bold; "
                                "background-color: transparent; "
                                f"border: 1px dashed {ds.STATE_ARMED};"
                            )
                            _blockers_text = (
                                "\nBlocked by: " + ", ".join(_fold_blockers)
                                if _fold_blockers
                                else ""
                            )
                            fire_btn.setToolTip(
                                "Manual FOLD override available — "
                                "delta < 0 but auto-fire blocked. "
                                "Clicking fires a MARKET buy sized to "
                                "rebalance back to target (bypasses "
                                "auto's TA/BB/MEM-171 gates)."
                                + _blockers_text
                                + _risk_suffix()
                            )
                    elif scrum_phase == "fire":
                        # Organic fire approach but delta is within
                        # the dust band — no rebalance needed. Amber
                        # glow keeps it visible but distinct from
                        # rebalance-armed.
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.TEXT_ON_LIGHT}; font-weight: bold; "
                            f"background-color: {ds.WARNING}; "
                            f"border: 1px solid {ds.STATE_PENDING};"
                        )
                        _apply_glow(ds.STATE_PENDING)
                        fire_btn.setToolTip(
                            "Organic FIRE phase — bot at band but "
                            "holdings within dust band of target. "
                            "Clicking has no effect." + _risk_suffix()
                        )
                    elif scrum_phase == "track":
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.WARNING}; font-weight: bold;"
                        )
                        fire_btn.setToolTip(
                            "TRACKING — bot detected band approach. "
                            "Fire is available but bot is within dust "
                            "band; rebalance would be a no-op."
                        )
                    else:
                        # SEARCH / idle — subdued red
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.ERROR}; font-weight: bold;"
                        )
                        fire_btn.setToolTip(
                            "Bot within dust band of target. "
                            "Manual Fire would be a no-op."
                        )
                else:
                    fire_btn.setStyleSheet(
                        "font-size: 10px; padding: 1px 6px; color: "
                        f"{ds.TEXT_PLACEHOLDER};"
                    )
                    if not is_scrumming:
                        fire_btn.setToolTip("Manual Fire is scrumming-only.")
                    else:
                        fire_btn.setToolTip(
                            f"Bot is {state}; start or resume to enable Fire."
                        )
                fire_btn.clicked.connect(lambda _checked, b=bid: self._on_fire(b))
                self.setCellWidget(row, 8, fire_btn)  # v3.23.49 — col 6→8

                # Detail button (col 7) — unchanged semantic; col index
                # shifted from 8→7 by v3.18.6 Exchange removal.
                detail_btn = QPushButton("Detail")
                detail_btn.setFixedHeight(22)
                detail_btn.setStyleSheet("font-size: 10px; padding: 1px 6px;")
                detail_btn.setToolTip(
                    "View full bot status, configuration, and error details"
                )
                detail_btn.clicked.connect(lambda _checked, b=bid: self._on_detail(b))
                self.setCellWidget(row, 9, detail_btn)  # v3.23.49 — col 7→9

            # issue #51 -- the highlight follows the BOT, not the row.
            _reanchor_bot_selection(self, _selected_before, self._bot_ids)

        def _on_detail(self, bot_id: str) -> None:
            # issue #52 -- SELECT THE ROW FIRST, THEN OPEN THE DIALOG.
            # The selection is what `ExchangeTab._cmd` reads, and
            # `self._on_bot_clicked` runs `MainWindow._on_bot_clicked`,
            # whose `dlg.exec()` is a modal loop that does not return
            # until the operator closes the dialog. Selecting after it
            # would leave the highlight -- and every command the
            # operator can press -- pointing at the previous row for as
            # long as the dialog stands open.
            _select_row_for_bot(self, bot_id, self._bot_ids)
            if self._on_bot_clicked:
                self._on_bot_clicked(bot_id)

        def _on_cell_clicked(self, row: int, col: int) -> None:
            """v3.23.54 — Symbol column click opens the chart URL
            (if the exchange is in the registry) in the operator's
            default browser. Any other column is a no-op here."""
            if col != 1:
                return
            item = self.item(row, col)
            if item is None:
                return
            from PySide6.QtCore import Qt as _Qt

            url = item.data(_Qt.UserRole)
            if not url:
                return
            try:
                import webbrowser

                webbrowser.open(str(url), new=2)
            except Exception as _wb_exc:  # noqa: BLE001 - best-effort
                logger.warning("Chart URL open failed for %r: %s", url, _wb_exc)

        def _on_fire(self, bot_id: str) -> None:
            """MEM-236 — Manual Fire button click handler."""
            if self._on_fire_clicked:
                self._on_fire_clicked(bot_id)

        def get_selected_bot_id(self) -> str:
            # v3.20.65 fix: gate on actual selection state, not just
            # currentRow(). Qt's clearSelection() empties selectedItems()
            # but leaves currentRow() pointing at the previously-focused
            # row, which made this method return stale bot ids after
            # the sibling table claimed selection. Pre-fix this was
            # the second half of the operator-reported Extractor
            # selection hijack — _cmd() resolution branch ran but
            # this method still returned the stale Scrumming row's
            # bot id (MEM-411).
            if not self.selectedItems():
                return ""
            row = self.currentRow()
            if 0 <= row < len(self._bot_ids):
                return self._bot_ids[row]
            return ""
