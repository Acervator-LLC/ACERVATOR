"""Every module_held keeps its lock loop alive through a Windows pending-delete refusal."""

import importlib
import os

import pytest

MODULES = [
    "tests.test_react_bot_live_settings",
    "tests.test_react_bot_visualizer",
    "tests.test_react_crypto_news_ticker",
    "tests.test_react_dashboard_stat_card",
    "tests.test_react_exchange_tab",
    "tests.test_react_quick_routing",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_held_acquires_after_one_permission_error(name, monkeypatch):
    mod = importlib.import_module(name)
    real_open = os.open
    calls = {"n": 0}

    def flaky(path, flags, *rest):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, flags, *rest)

    monkeypatch.setattr(os, "open", flaky)
    entered = False
    with mod.module_held():
        entered = True
    assert entered, f"{name}.module_held never yielded after one PermissionError"
    assert (
        calls["n"] >= 2
    ), f"{name}.module_held did not retry: {calls['n']} os.open call(s)"


@pytest.mark.parametrize("name", MODULES)
def test_module_held_gives_up_when_every_attempt_is_refused(name, monkeypatch):
    mod = importlib.import_module(name)

    def always_refused(path, flags, *rest):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(os, "open", always_refused)
    with pytest.raises(AssertionError, match="stayed taken"):
        with mod.module_held(attempts=3):
            pass
