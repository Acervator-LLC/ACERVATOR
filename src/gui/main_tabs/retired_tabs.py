"""Sentinel attributes for the main window's retired tabs.

``RetiredTabsMixin`` carries one method,
``_install_retired_tab_sentinels``, which assigns None to every
attribute whose tab the main window does not build.
"""

from __future__ import annotations


class RetiredTabsMixin:
    """Supplies ``_install_retired_tab_sentinels`` to the main window."""

    def _install_retired_tab_sentinels(self) -> None:
        """Assign None to ``_audio_suite``, ``_analytics_tab`` and the rest.

        ``main_window`` tests ``_risk_tab`` and ``_alerts_tab`` before
        refreshing them.
        """
        # Nothing outside this method reads `_audio_suite`, `_analytics_tab` or
        # `_journal_tab`.
        self._audio_suite = None

        self._analytics_tab = None

        self._journal_tab = None

        # `_risk_tab` and `_alerts_tab` are None while their engines keep running.
        self._risk_tab = None

        self._alerts_tab = None
