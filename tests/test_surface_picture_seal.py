"""The stamp that keeps an altered payload out of a parity render.

A failure means a parity test can render a payload it changed itself,
which measures the host's fonts rather than the product.
"""

from __future__ import annotations

import pytest

from tests.fixtures.surface_pictures import sealed, unaltered


def payload():
    """One payload of the shape a surface returns."""
    return {
        "widget": {"style_sheet": "QLabel { color: #00ffcc; }", "modal": True},
        "rows": [["BTC", "$50.0000"], ["ETH", "$12.5000"]],
        "columns": ("Pair", "Ammo"),
        "count": 2,
        "blank": None,
    }


def test_a_sealed_payload_is_returned_unchanged():
    """The seal altered the payload it stamped."""
    original = payload()
    assert sealed(original) is original
    assert original == payload()


def test_an_unaltered_payload_is_accepted():
    """A payload straight off a side was refused."""
    stamped = sealed(payload())
    assert unaltered(stamped) is stamped


def test_a_payload_that_was_never_sealed_is_refused():
    """A payload the test built itself reached a render."""
    with pytest.raises(AssertionError) as reported:
        unaltered(payload())
    assert "never came off" in str(reported.value)


def test_a_changed_top_level_value_is_refused():
    """A changed value at the top level reached a render."""
    stamped = sealed(payload())
    stamped["count"] = 3
    with pytest.raises(AssertionError) as reported:
        unaltered(stamped)
    assert "altered after it came off" in str(reported.value)


def test_a_changed_nested_value_is_refused():
    """A changed value inside a nested cell reached a render."""
    stamped = sealed(payload())
    stamped["rows"][0][1] = "$50.0001"
    with pytest.raises(AssertionError):
        unaltered(stamped)


def test_a_changed_value_inside_a_nested_mapping_is_refused():
    """A changed style sheet inside a nested mapping reached a render."""
    stamped = sealed(payload())
    stamped["widget"]["style_sheet"] = ""
    with pytest.raises(AssertionError):
        unaltered(stamped)


def test_two_swapped_rows_are_refused():
    """A row order the test changed reached a render."""
    stamped = sealed(payload())
    stamped["rows"][0], stamped["rows"][1] = stamped["rows"][1], stamped["rows"][0]
    with pytest.raises(AssertionError):
        unaltered(stamped)


def test_a_dropped_row_is_refused():
    """A row the test removed reached a render."""
    stamped = sealed(payload())
    del stamped["rows"][1]
    with pytest.raises(AssertionError):
        unaltered(stamped)


def test_a_value_replaced_by_one_of_equal_text_length_is_refused():
    """A same-length replacement slipped past the stamp."""
    stamped = sealed(payload())
    stamped["rows"][0][0] = "XRP"
    with pytest.raises(AssertionError):
        unaltered(stamped)


def test_a_value_changed_and_put_back_is_accepted():
    """The stamp reported a payload that carries its sealed content."""
    stamped = sealed(payload())
    was = stamped["count"]
    stamped["count"] = 3
    with pytest.raises(AssertionError):
        unaltered(stamped)
    stamped["count"] = was
    assert unaltered(stamped) is stamped


def test_a_sealed_list_payload_is_accepted_and_a_changed_one_refused():
    """A payload that is a list of lines was not covered by the stamp."""
    lines = sealed(["<span>one</span>", "<span>two</span>"])
    assert unaltered(lines) is lines
    lines[0] = "<span>three</span>"
    with pytest.raises(AssertionError):
        unaltered(lines)


def test_two_payloads_of_different_content_carry_different_stamps():
    """The stamp returns one value whatever payload it is given."""
    from tests.fixtures.surface_pictures import _content_digest

    one = payload()
    other = payload()
    other["count"] = 3
    assert _content_digest(one) != _content_digest(other)
    assert _content_digest(one) == _content_digest(payload())
