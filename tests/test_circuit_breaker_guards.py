"""Drive each circuit-breaker guard to both of its values.

``is_call_allowed``, ``_breaker_disabled`` and ``_is_transient_error`` each
decide whether an exchange call is attempted or counted. ``_open_breaker``
builds the refusing side for ``is_call_allowed``.
"""

from __future__ import annotations

import pytest

from src.exchange.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    _breaker_disabled,
    _is_transient_error,
    reset_for_test,
)

ENV = "ACERVATOR_BREAKER_DISABLE"


class InsufficientFunds(Exception):
    """A logic error the operator fixes, named the way ccxt names it."""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Leave no breaker registry and no ``ENV`` value behind."""
    monkeypatch.delenv(ENV, raising=False)
    reset_for_test()
    yield
    reset_for_test()


def _open_breaker() -> CircuitBreaker:
    """A ``CircuitBreaker`` driven OPEN by one transient failure."""
    breaker = CircuitBreaker("BTC/USD", failure_threshold=1, cooldown_seconds=600.0)
    breaker.record_failure(TimeoutError("read timed out"))
    assert breaker.stats.state is BreakerState.OPEN, "the breaker refused to open"
    return breaker


def test_a_closed_breaker_allows_a_call():
    breaker = CircuitBreaker("BTC/USD")
    assert breaker.is_call_allowed() is True


def test_an_open_breaker_refuses_a_call():
    assert _open_breaker().is_call_allowed() is False


def test_the_disable_variable_makes_an_open_breaker_allow_again(monkeypatch):
    breaker = _open_breaker()
    monkeypatch.setenv(ENV, "1")
    assert breaker.is_call_allowed() is True


def test_breaker_disabled_is_false_without_the_variable():
    assert _breaker_disabled() is False


def test_breaker_disabled_is_true_for_each_accepted_word(monkeypatch):
    for word in ("1", "true", "YES", "on"):
        monkeypatch.setenv(ENV, word)
        assert _breaker_disabled() is True, word


def test_a_transient_error_raises_the_consecutive_count():
    breaker = CircuitBreaker("BTC/USD", failure_threshold=5)
    assert _is_transient_error(TimeoutError("read timed out")) is True
    breaker.record_failure(TimeoutError("read timed out"))
    assert breaker.stats.consecutive_failures == 1
    assert breaker.stats.total_failures == 1


def test_a_logic_error_raises_only_the_total():
    breaker = CircuitBreaker("BTC/USD", failure_threshold=1)
    assert _is_transient_error(InsufficientFunds("balance too low")) is False
    breaker.record_failure(InsufficientFunds("balance too low"))
    assert breaker.stats.consecutive_failures == 0
    assert breaker.stats.total_failures == 1
    assert breaker.stats.state is BreakerState.CLOSED


def test_a_lapsed_cooldown_reports_half_open():
    breaker = CircuitBreaker("BTC/USD", failure_threshold=1, cooldown_seconds=0.0)
    breaker.record_failure(TimeoutError("read timed out"))
    assert breaker.state() is BreakerState.HALF_OPEN
    assert breaker.is_call_allowed() is True
