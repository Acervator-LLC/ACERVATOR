"""Band scaling for a micro-cap asset, driven through band_program.

``price_rows`` reads the price polyline y-coordinates out of the program
``band_program`` returns. Each test feeds ``PriceVwapModel`` a series at one
price level and asserts how many separate rows the band resolves.
"""

from __future__ import annotations

from src.gui.main_tabs import sim_visuals_surface as surface

PAIR = "BONK/USD"
BONK_PRICE = 3.1e-06
BTC_PRICE = 70000.0
WIDTH_PX = 640
POINTS = 20


def build(price: float, span: float) -> surface.PriceVwapModel:
    """Return a model holding POINTS ticks rising from price across span."""
    model = surface.PriceVwapModel()
    model.set_symbols([PAIR])
    for index in range(POINTS):
        model.append_tick(PAIR, price + span * index / (POINTS - 1), 1.0)
    return model


def price_rows(model: surface.PriceVwapModel) -> set:
    """Return the distinct y values the price polyline draws for PAIR."""
    rows = set()
    for step in surface.band_program(model, WIDTH_PX):
        if step["op"] == surface.LINE and step["pen"] == surface.CHART_PRICE_COLOUR:
            rows.add(step["line"][1])
            rows.add(step["line"][3])
    return rows


def test_a_moving_micro_cap_price_resolves_more_than_one_band_row():
    rows = price_rows(build(BONK_PRICE, BONK_PRICE * 2e-5))
    assert len(rows) > 1, (
        f"a rising BONK series at {BONK_PRICE} collapsed to {len(rows)} row(s); "
        "the band floor outranked the real span"
    )


def test_a_moving_micro_cap_price_resolves_as_many_rows_as_a_large_cap():
    small = price_rows(build(BONK_PRICE, BONK_PRICE * 2e-5))
    large = price_rows(build(BTC_PRICE, BTC_PRICE * 2e-5))
    assert len(large) > 1, f"the large-cap control drew {len(large)} row(s)"
    assert len(small) == len(large), (
        f"the same shape drew {len(small)} rows at BONK scale and "
        f"{len(large)} rows at BTC scale; the band is not scale free"
    )


def test_a_flat_series_draws_one_row_without_dividing_by_zero():
    rows = price_rows(build(BONK_PRICE, 0.0))
    assert len(rows) == 1, f"a flat series drew {len(rows)} rows, expected 1"
