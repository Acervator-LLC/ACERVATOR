"""Behaviour of the chart and PDF tokens in ``src.design_system``.

``contrast_ratio`` is driven against the WCAG 2.1 endpoints. ``callout_value``
is driven on a real axes and its drawn text is counted. ``contrast_self_test``
pass marks are encoded to the Windows console codepage.
"""

from __future__ import annotations

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
plt = pytest.importorskip("matplotlib.pyplot")

from src.design_system import (  # noqa: E402
    COLORS,
    bar_h,
    blank_page,
    callout_value,
    contrast_ratio,
    contrast_self_test,
    validate_contrast,
)


def _texts(ax) -> list[str]:
    return [t.get_text() for t in ax.texts]


class TestContrastRatio:
    def test_white_on_black_is_twenty_one_to_one(self):
        assert round(contrast_ratio("#ffffff", "#000000"), 2) == 21.00

    def test_a_colour_on_itself_is_one_to_one(self):
        assert round(contrast_ratio("#ffffff", "#ffffff"), 2) == 1.00

    def test_the_order_of_the_two_colours_does_not_change_the_ratio(self):
        assert contrast_ratio("#1f3a68", "#ffffff") == contrast_ratio(
            "#ffffff", "#1f3a68"
        )

    @pytest.mark.parametrize(
        ("token", "expected"),
        [("rule", 1.48), ("ink_faint", 2.68), ("ink_mute", 5.33)],
    )
    def test_each_token_measures_its_stated_ratio_on_the_page(self, token, expected):
        measured = round(contrast_ratio(COLORS[token], COLORS["bg"]), 2)
        assert measured == expected, f"{token} measures {measured}:1, not {expected}:1"

    def test_the_yellow_series_entry_measures_its_stated_ratio(self):
        assert round(contrast_ratio("#F0E442", COLORS["bg"]), 2) == 1.32


class TestCalloutValue:
    def test_the_value_is_drawn_exactly_once(self):
        fig, ax = blank_page()
        try:
            callout_value(ax, label="ytd scrummed", value="$41,208")
            drawn = _texts(ax)
        finally:
            plt.close(fig)
        assert drawn.count("$41,208") == 1, (
            f"callout_value drew the value {drawn.count('$41,208')} times; "
            f"axes text is {drawn}"
        )

    def test_the_label_and_context_are_drawn_beside_the_value(self):
        fig, ax = blank_page()
        try:
            callout_value(
                ax, label="ytd scrummed", value="$41,208", context="since 1 January"
            )
            drawn = _texts(ax)
        finally:
            plt.close(fig)
        assert "YTD SCRUMMED" in drawn
        assert "since 1 January" in drawn

    def test_the_text_counter_reports_a_repeated_draw(self):
        fig, ax = blank_page()
        try:
            ax.text(0.5, 0.5, "$41,208", transform=ax.transAxes)
            ax.text(0.5, 0.5, "$41,208", transform=ax.transAxes)
            drawn = _texts(ax)
        finally:
            plt.close(fig)
        assert drawn.count("$41,208") == 2


class TestContrastSelfTest:
    def test_every_pass_mark_encodes_on_the_windows_console_codepage(self):
        for name, _hex, _ratio, mark in contrast_self_test():
            mark.encode("cp1252")
            assert mark, f"{name} carries no pass mark"

    def test_the_encoding_check_reports_an_unencodable_mark(self):
        with pytest.raises(UnicodeEncodeError):
            "✓".encode("cp1252")

    def test_every_listed_token_clears_the_floor_and_carries_one_mark(self):
        marks = {name: mark for name, _hex, _ratio, mark in contrast_self_test()}
        assert set(marks) == {
            "ink",
            "ink_strong",
            "ink_mute",
            "accent",
            "win",
            "loss",
            "warn",
            "info",
        }
        assert len(set(marks.values())) == 1, f"a listed token failed: {marks}"

    def test_the_mark_differs_when_a_colour_fails_the_floor(self):
        passing = validate_contrast(COLORS["ink_strong"], COLORS["bg"])[0]
        failing = validate_contrast(COLORS["ink_faint"], COLORS["bg"])[0]
        assert passing is True
        assert failing is False


class TestGuardsRefuse:
    def test_the_large_text_floor_admits_a_colour_the_body_floor_rejects(self):
        assert validate_contrast("#CC79A7", COLORS["bg"], large_text=True)[0] is True
        assert validate_contrast("#CC79A7", COLORS["bg"], large_text=False)[0] is False

    def test_bar_h_draws_no_value_label_without_a_formatter(self):
        fig, ax = blank_page()
        try:
            bar_h(ax, labels=["a", "b"], values=[3.0, 5.0], direct_labels=True)
            drawn = _texts(ax)
        finally:
            plt.close(fig)
        assert drawn == [], f"bar_h drew {drawn} with no label_fmt"

    def test_bar_h_draws_one_value_label_per_bar_with_a_formatter(self):
        fig, ax = blank_page()
        try:
            bar_h(
                ax,
                labels=["a", "b"],
                values=[3.0, 5.0],
                direct_labels=True,
                label_fmt=lambda v: f"{v:.0f}u",
            )
            drawn = _texts(ax)
        finally:
            plt.close(fig)
        assert drawn == ["3u", "5u"], f"bar_h drew {drawn}"

    def test_bar_h_draws_no_value_label_when_direct_labels_is_off(self):
        fig, ax = blank_page()
        try:
            bar_h(
                ax,
                labels=["a"],
                values=[3.0],
                direct_labels=False,
                label_fmt=lambda v: f"{v:.0f}u",
            )
            drawn = _texts(ax)
        finally:
            plt.close(fig)
        assert drawn == [], f"bar_h drew {drawn} with direct_labels off"
