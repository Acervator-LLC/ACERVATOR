"""Sentinel attributes for the main window's removed tabs."""

from __future__ import annotations


class RetiredTabsMixin:
    """Assigns None for every tab whose GUI surface was removed."""

    def _install_retired_tab_sentinels(self) -> None:
        """Assign the None sentinels legacy code paths still read."""
        # Paper Trader still pending Phase E. Sentinel-None
        # preserved for any legacy code path that references the
        # attribute during the transition.
        self._paper_trader = None
        self._paper_trader_stack = None
        self._paper_trader_crypto = None
        self._paper_trader_equity = None

        # --- Tab 6c: Multi-Scale Paper Trader — REMOVED v3.16.28 ---
        # Operator directive 2026-05-05: "The multi-scale paper tab
        # can be removed. The Paper Trader Tab must feature all
        # strategies features and therefore having two different
        # paper trader tabs is redundant."
        #
        # The MultiScalePaperTab module is deleted from the GUI
        # surface. Strategy-feature parity (every strategy live-
        # tradeable in paper-mode) is now the Paper Trader tab's
        # responsibility. Sentinel attrs preserved as None so any
        # legacy code path that still references _multi_scale_*
        # degrades gracefully instead of AttributeError-ing.
        self._multi_scale_stack = None
        self._multi_scale_crypto = None
        self._multi_scale_equity = None
        self._multi_scale_paper = None

        # --- Tab 7: Proof of Accumulation — REMOVED per P1.7 / MEM-178 ---
        # Operator directive 2026-04-21: 7 GUI tabs marked for removal.
        # MEM-034 / ADR-008 (PoA) IP record preserved; only UI surface shelved.
        self._competition_tab = None

        # --- Tab 8: Local Testnet — REMOVED per P1.7 / MEM-178 ---
        # MEM-034 / ADR-008 (PoA) IP record preserved; UI surface shelved.
        # Also removes prior-attempt artifact: duplicate unreachable
        # except clause that was part of a failed earlier removal.
        self._testnet_tab = None

        # --- Bot Swarm injection into live tabs — DELETED (C11,
        #     v3.24.55, operator decision 2026-08-07: delete) ---
        #
        # Two calls to `set_bot_viz`, a method with ZERO definitions
        # anywhere in the repo. Both sat in `try/except Exception:
        # pass`, so the `_simulator` one raised AttributeError into
        # a bare except on EVERY boot and nothing ever said so
        # (NF-162). The `_paper_trader` one was structurally
        # unreachable (NF-109): `_paper_trader`,
        # `_paper_trader_stack`, `_paper_trader_crypto` and
        # `_paper_trader_equity` are assigned None above and never
        # assigned anything else in this module, so the reassign-
        # ments in the view-mode handlers can only ever copy None
        # into None.
        #
        # DELETED rather than implemented. `_bot_viz` is a live
        # `BotVisualizationTab`; giving SimulatorTab a reference to
        # it would inject a live GUI object into the sim surface —
        # a sim<->live bridge, which is a standing prohibition. The
        # Simulator's other injection points (`set_bot_manager`,
        # `set_connectors_getter`, `set_async_loop`) were each a
        # deliberate decision; this one was never built, only
        # called.
        #
        # Recorded here rather than silently removed so C49, which
        # makes this wire-or-delete judgement systematically, can
        # reconsider it with the reasoning intact.

        # --- Audio Suite — REMOVED per P1.7 / MEM-178 ---
        self._audio_suite = None

        # --- Analytics Dashboard — REMOVED per P1.7 / MEM-178 ---
        # Underlying AnalyticsEngine (self._analytics) kept intact —
        # referenced by background timer snapshot code.
        self._analytics_tab = None

        # --- Risk Management — REMOVED per P1.7 / MEM-178 ---
        # Underlying RiskManager kept intact — used by background timer.
        self._risk_tab = None

        # --- Trade Journal — REMOVED per P1.7 / MEM-178 ---
        # Underlying TradeJournal / ReconciliationEngine / CrashRecovery
        # kept intact — used for trade persistence.
        self._journal_tab = None

        # --- Alerts & Notifications — REMOVED per P1.7 / MEM-178 ---
        # Underlying NotificationManager kept intact.
        self._alerts_tab = None
