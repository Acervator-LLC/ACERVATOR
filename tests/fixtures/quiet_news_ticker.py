"""A news strip that reaches no network, and the fixture that installs it.

``CryptoNewsTicker.start()`` opens ten RSS feeds on a QThread that is
built with NO PARENT, so destroying the widget leaves the fetch running.
The thread then outlives its own test and shares the process with every
test that follows it, including tests of other files. Any test that
builds an ``ExchangeTab`` or a ``MainWindow`` reaches that class, so
each one installs this stand-in in its place.

    from tests.fixtures.quiet_news_ticker import quiet_news_ticker

``fetch_threads_running`` reports how many news fetch threads are alive
in this process. It is the positive control for the fixture: it reads
above zero on a run that builds the real strip, and zero on a run that
installs this one.

FALSIFICATION
=============
Wrong if (a) ``ExchangeTab`` stops resolving ``CryptoNewsTicker`` off
the module at build time, when patching the module attribute installs
nothing and the real strip runs anyway, or (b) ``_LIVE_WORKERS`` stops
holding a fetch thread for the whole of its life, when
``fetch_threads_running`` under-reports and its zero states nothing.
"""

from __future__ import annotations

import pytest

STARTS: list = []


def quiet_ticker_class():
    """The stand-in class, built on the same base as the real strip."""
    from PySide6.QtWidgets import QWidget

    class QuietNewsTicker(QWidget):
        """A news strip that opens no socket and starts no thread."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Crypto News Ticker")

        def start(self):
            STARTS.append(1)

        def stop(self):
            pass

    return QuietNewsTicker


def install_quiet_ticker(monkeypatch):
    """Put the stand-in in place of the real strip and return it."""
    from src.gui import crypto_news_ticker

    stand_in = quiet_ticker_class()
    monkeypatch.setattr(crypto_news_ticker, "CryptoNewsTicker", stand_in)
    STARTS.clear()
    return stand_in


@pytest.fixture
def quiet_news_ticker(monkeypatch):
    """Install the stand-in for one test and hand the class back."""
    yield install_quiet_ticker(monkeypatch)


def fetch_threads_running() -> int:
    """How many news fetch threads are running in this process."""
    from src.gui.crypto_news_ticker import _LIVE_WORKERS

    live = 0
    for thread in list(_LIVE_WORKERS):
        try:
            if thread.isRunning():
                live += 1
        except RuntimeError:
            continue
    return live
