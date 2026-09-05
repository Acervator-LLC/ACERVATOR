"""``ExtractorBot._usd_per_base_rate`` holds dollars for one base unit.

``_assert_rate_is_usd_per_base`` pins the direction of ``_base_to_usd``,
``_usd_to_base`` and ``set_initial_chunk_rate`` at runtime.
``_ReciprocalExtractor`` fails those same assertions.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.trading.bot_container import BotConfig, BotMode
from src.trading.extractor_bot import ExtractorBot

ETH_USD = 3421.75
CHUNK_USD = 100.0
HEDGE_USD = 40.0


def _config() -> BotConfig:
    """An EXTRACTOR ``BotConfig`` on ETH sized at ``CHUNK_USD`` and ``HEDGE_USD``."""
    return BotConfig(
        exchange_id="test-exchange",
        base_currency="ETH",
        target_asset="ALT",
        mode=BotMode.EXTRACTOR,
        extractor_chunk_size_usd=CHUNK_USD,
        extractor_hedge_budget_usd=HEDGE_USD,
    )


class _ReciprocalExtractor(ExtractorBot):
    """An ``ExtractorBot`` reading ``_usd_per_base_rate`` as base units for one dollar."""

    def _usd_to_base(self, usd: float) -> float:
        return float(usd) * float(self._usd_per_base_rate)

    def _base_to_usd(self, base: float) -> float:
        if self._usd_per_base_rate <= 0:
            return 0.0
        return float(base) / float(self._usd_per_base_rate)

    def set_initial_chunk_rate(self, usd_per_base: float) -> None:
        super().set_initial_chunk_rate(usd_per_base)
        self._chunk_size_base = self._chunk_size_usd * usd_per_base
        self._chunk_free_base = self._chunk_size_base
        self._hedge_free_base = self._hedge_budget_usd * usd_per_base


def _stub_registry(monkeypatch) -> None:
    """Replace ``capital_reservation.get_registry`` with a token-returning double."""
    registry = MagicMock()
    registry.reserve.return_value = "token-for-the-direction-test"
    monkeypatch.setattr(
        "src.trading.capital_reservation.get_registry", lambda: registry
    )


@pytest.fixture
def ebot(monkeypatch) -> ExtractorBot:
    _stub_registry(monkeypatch)
    return ExtractorBot(_config(), MagicMock())


@pytest.fixture
def flipped(monkeypatch) -> _ReciprocalExtractor:
    _stub_registry(monkeypatch)
    return _ReciprocalExtractor(_config(), MagicMock())


def _assert_rate_is_usd_per_base(bot: ExtractorBot, usd_per_base: float) -> None:
    """Assert ``bot`` reads ``usd_per_base`` as the dollar price of one base unit.

    Covers ``_base_to_usd``, ``_usd_to_base``, ``_chunk_size_base`` and
    ``_hedge_free_base``.
    """
    assert bot._base_to_usd(1.0) == pytest.approx(usd_per_base), (
        f"one base unit must convert to {usd_per_base} dollars, "
        f"got {bot._base_to_usd(1.0)}"
    )
    assert bot._usd_to_base(usd_per_base) == pytest.approx(1.0), (
        f"{usd_per_base} dollars must buy one base unit, "
        f"got {bot._usd_to_base(usd_per_base)}"
    )
    assert bot._chunk_size_base == pytest.approx(CHUNK_USD / usd_per_base), (
        f"a ${CHUNK_USD} pool at ${usd_per_base} per base unit holds "
        f"{CHUNK_USD / usd_per_base} units, got {bot._chunk_size_base}"
    )
    assert bot._hedge_free_base == pytest.approx(HEDGE_USD / usd_per_base), (
        f"a ${HEDGE_USD} hedge at ${usd_per_base} per base unit holds "
        f"{HEDGE_USD / usd_per_base} units, got {bot._hedge_free_base}"
    )


def test_set_initial_chunk_rate_reads_its_argument_as_dollars_per_base_unit(ebot):
    """``set_initial_chunk_rate(ETH_USD)`` leaves every conversion at ``ETH_USD``."""
    ebot.set_initial_chunk_rate(ETH_USD)

    _assert_rate_is_usd_per_base(ebot, ETH_USD)


def test_one_base_unit_converts_to_the_rate_in_dollars(ebot):
    """``_base_to_usd`` scales up when one base unit costs more than one dollar."""
    ebot.set_initial_chunk_rate(ETH_USD)

    assert ebot._base_to_usd(1.0) == pytest.approx(ETH_USD)
    assert ebot._base_to_usd(2.5) == pytest.approx(2.5 * ETH_USD)


def test_a_dollar_amount_equal_to_the_rate_buys_one_base_unit(ebot):
    """``_usd_to_base`` scales down when one base unit costs more than one dollar."""
    ebot.set_initial_chunk_rate(ETH_USD)

    assert ebot._usd_to_base(ETH_USD) == pytest.approx(1.0)
    assert ebot._usd_to_base(CHUNK_USD) == pytest.approx(CHUNK_USD / ETH_USD)


def test_the_chunk_holds_the_dollar_pool_divided_by_the_rate(ebot):
    """``_chunk_size_base`` is ``CHUNK_USD`` over ``ETH_USD``, never the product."""
    ebot.set_initial_chunk_rate(ETH_USD)

    assert ebot._chunk_size_base == pytest.approx(CHUNK_USD / ETH_USD)
    assert ebot._chunk_size_base != pytest.approx(CHUNK_USD * ETH_USD)
    assert ebot._chunk_free_base == pytest.approx(ebot._chunk_size_base)


def test_the_hedge_reserve_converts_in_the_same_direction(ebot):
    """``_hedge_free_base`` is ``HEDGE_USD`` over ``ETH_USD``."""
    ebot.set_initial_chunk_rate(ETH_USD)

    assert ebot._hedge_free_base == pytest.approx(HEDGE_USD / ETH_USD)


def test_update_usd_per_base_rate_moves_the_conversion_the_same_way(ebot):
    """``update_usd_per_base_rate`` leaves ``_base_to_usd`` reading dollars per unit."""
    ebot.set_initial_chunk_rate(ETH_USD)
    later = ETH_USD * 1.05

    accepted, why = ebot.update_usd_per_base_rate(later)

    assert accepted is True, why
    assert ebot._base_to_usd(1.0) == pytest.approx(later)
    assert ebot._usd_to_base(later) == pytest.approx(1.0)


def test_a_reciprocal_reading_fails_the_same_assertions(flipped):
    """``_ReciprocalExtractor`` raises ``AssertionError`` out of the shared check."""
    flipped.set_initial_chunk_rate(ETH_USD)

    with pytest.raises(AssertionError):
        _assert_rate_is_usd_per_base(flipped, ETH_USD)


def test_every_limb_of_the_shared_check_separates_the_two_readings(flipped):
    """Each quantity ``_assert_rate_is_usd_per_base`` reads differs under the flip."""
    flipped.set_initial_chunk_rate(ETH_USD)

    assert flipped._base_to_usd(1.0) == pytest.approx(1.0 / ETH_USD)
    assert flipped._usd_to_base(ETH_USD) == pytest.approx(ETH_USD * ETH_USD)
    assert flipped._chunk_size_base == pytest.approx(CHUNK_USD * ETH_USD)
    assert flipped._hedge_free_base == pytest.approx(HEDGE_USD * ETH_USD)
