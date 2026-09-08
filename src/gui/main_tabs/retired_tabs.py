"""Sentinel attributes for the main window's retired tabs.

``RetiredTabsMixin`` carries one method,
``_install_retired_tab_sentinels``, which assigns None to every
attribute whose tab the main window does not build.
"""

from __future__ import annotations


class RetiredTabsMixin:
    """Supplies ``_install_retired_tab_sentinels`` to the main window."""

    def _install_retired_tab_sentinels(self) -> None:
        """Assign None to ``_competition_tab``, ``_testnet_tab`` and the rest.

        ``main_window`` tests ``_analytics_tab``, ``_risk_tab``,
        ``_journal_tab`` and ``_alerts_tab`` before refreshing them.
        """
        # Nothing outside this method reads the `_multi_scale_` names,
        # `_competition_tab`, `_testnet_tab` or `_audio_suite`.
        self._multi_scale_stack = None
        self._multi_scale_crypto = None
        self._multi_scale_equity = None
        self._multi_scale_paper = None

        self._competition_tab = None

        self._testnet_tab = None

        self._audio_suite = None

        # `_analytics_tab`, `_risk_tab`, `_journal_tab` and `_alerts_tab`
        # are None while their engines keep running.
        self._analytics_tab = None

        self._risk_tab = None

        self._journal_tab = None

        self._alerts_tab = None
