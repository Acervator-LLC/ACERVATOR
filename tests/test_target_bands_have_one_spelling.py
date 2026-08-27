"""The dashboard reads the tick's bands; it does not restate them.

Issue #128 R2. Two thresholds decide whether a position counts as ON
TARGET, and each was written out twice:

    park band    max(target * 0.001, 0.01)   tick(), and the Ammo cell
    Manual Fire  max(target * 0.01,  0.01)   _execute_manual_rebalance,
                                             and the Ammo cell again

The cell exists to say what the tick and the Fire button are about to
do. A cell that computes the threshold itself can say SCRUM while the
tick is parked, and the operator finds that out by pressing the button.
Both engine sites and the cell now call ``src/trading/target_bands.py``.

WHAT A FAILURE HERE MEANS. Either a band literal came back into one of
the three call sites, or the cell's colour stopped matching the
territory the tick would read on the same numbers -- which is the
display lying about a live-money decision.

THE DOMAIN IS SWEPT, NOT TABULATED. Both decisions turn on a
threshold, so a hand-written row set would encode the same mental
model as the code. The sweep walks each band edge in single cents and
in ULPs across five target scales, including the operator's own
sub-dollar ones where the $0.01 floor is what binds rather than the
percentage.
"""

from __future__ import annotations

import ast
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.target_bands import (  # noqa: E402
    AT_TARGET_PCT,
    BAND_FLOOR_USD,
    MANUAL_FIRE_PCT,
    at_target_dust_band,
    manual_fire_dust_band,
    manual_fire_will_noop,
    target_territory,
)

#: Sub-dollar through institutional. 8.0 is where the $0.01 floor stops
#: binding on the Manual Fire band; 10.0 is where it stops binding on
#: neither -- both edges are inside the sweep on purpose.
TARGETS = (0.03, 0.11, 1.0, 8.0, 10.0, 47.13, 100.0, 12500.0)


def _method_source(name: str) -> str:
    import src.trading.scrumming_bot as sb

    text = Path(sb.__file__).read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.walk(ast.parse(text))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return ast.get_source_segment(text, node) or ""


def test_the_tick_calls_the_band_and_spells_none_of_its_own():
    body = _method_source("tick")
    assert "at_target_dust_band(self._target_balance)" in body
    assert "* 0.001" not in body, "a park-band literal is back in tick()"


def test_manual_fire_calls_the_band_and_spells_none_of_its_own():
    body = _method_source("_execute_manual_rebalance")
    assert "manual_fire_dust_band(self._target_balance)" in body
    assert "* 0.01" not in body, "a Manual Fire band literal is back in the engine"


def test_the_ammo_cell_calls_the_band_and_spells_none_of_its_own():
    import src.gui.table_cells as cells

    text = Path(cells.__file__).read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.walk(ast.parse(text))
        if isinstance(n, ast.FunctionDef) and n.name == "_compose_ammo_cell"
    )
    body = ast.get_source_segment(text, node) or ""
    assert "target_territory(" in body
    assert "manual_fire_dust_band(" in body
    assert "* 0.001" not in body, "a park-band literal is back in the cell"
    assert "_MANUAL_FIRE_DUST_PCT," not in body


def test_the_bands_are_the_published_percentages_at_every_scale():
    """Both formulae, swept, including where the floor binds."""
    for target in TARGETS:
        assert at_target_dust_band(target) == max(
            target * AT_TARGET_PCT, BAND_FLOOR_USD
        )
        assert manual_fire_dust_band(target) == max(
            target * MANUAL_FIRE_PCT, BAND_FLOOR_USD
        )
        # Manual Fire's band is never the narrower of the two, which is
        # the whole reason the cell warns.
        assert manual_fire_dust_band(target) >= at_target_dust_band(target)


def _cell_colour(position_value: float, target: float) -> str:
    from src.gui.table_cells import _compose_ammo_cell

    # holdings x price x qrate == position_value, so the cell computes
    # the same exposure the tick does.
    return _compose_ammo_cell(0.0, 1.0, position_value, 1.0, target)["color"]


def test_the_cell_colour_matches_the_tick_territory_across_the_band_edge():
    """THE CROSS-WITNESS, ON THE THRESHOLD ITSELF.

    Two independent paths -- the engine's ``target_territory`` and the
    rendered cell colour -- read on the same numbers, walked across
    both sides of the park band in cents and in ULPs.
    """
    from src.gui.table_cells import _AMMO_FOLD, _AMMO_NEUTRAL, _AMMO_SCRUM

    expected = {"scrum": _AMMO_SCRUM, "fold": _AMMO_FOLD, "at_target": _AMMO_NEUTRAL}
    checked = 0
    for target in TARGETS:
        band = at_target_dust_band(target)
        offsets = [
            0.0,
            band,
            -band,
            math.nextafter(band, math.inf),
            math.nextafter(band, -math.inf),
            -math.nextafter(band, math.inf),
            -math.nextafter(band, -math.inf),
        ]
        offsets += [band * k for k in (0.5, 0.999, 1.001, 2.0, 10.0)]
        offsets += [-band * k for k in (0.5, 0.999, 1.001, 2.0, 10.0)]
        offsets += [c / 100.0 for c in range(-25, 26)]
        for offset in offsets:
            position = target + offset
            if position <= 0:
                continue  # the empty-position branch, not a band decision
            assert (
                _cell_colour(position, target)
                == expected[target_territory(position, target)]
            ), (target, offset)
            checked += 1
    assert checked > 400, f"the sweep collapsed to {checked} points"


def test_the_cell_no_op_warning_matches_the_engine_refusal():
    """Same sweep, the Manual Fire band, and the one display-only rule.

    ``manual_fire_will_noop`` is the engine's refusal. The cell adds
    ``0 < abs(delta)`` because a bot exactly on target has nothing to
    fire, so a warning there would be noise rather than a surprise.
    """
    from src.gui.table_cells import _compose_ammo_cell

    checked = 0
    for target in TARGETS:
        band = manual_fire_dust_band(target)
        for offset in [0.0, band, -band, band * 1.001, -band * 1.001] + [
            c / 100.0 for c in range(-30, 31)
        ]:
            position = target + offset
            if position <= 0:
                continue
            cell = _compose_ammo_cell(0.0, 1.0, position, 1.0, target)
            engine = manual_fire_will_noop(position, target)
            delta = cell["delta"]
            assert cell["manual_fire_noop"] == (engine and delta != 0.0), (
                target,
                offset,
            )
            checked += 1
    assert checked > 400, f"the sweep collapsed to {checked} points"
