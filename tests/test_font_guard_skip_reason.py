"""A font-state guard skips with a reason that names what the run lacked.

A test that needs glyphs and silently passes without them proves
nothing, so the guard has to say which of the two lending steps was
absent. Each test here drives the real guard over a body that raises,
so a guard that let the body through fails instead of going quiet.
"""

from __future__ import annotations

import pytest

from tests.fixtures import host_fonts


def test_a_run_that_never_asked_for_fonts_is_told_the_flag_is_unset(monkeypatch):
    monkeypatch.delenv(host_fonts.FONT_ENV, raising=False)

    reason = host_fonts.missing_font_source()

    assert host_fonts.FONT_ENV in reason, reason
    assert "1" in reason, reason


def test_a_run_that_asked_but_found_no_font_file_is_told_which_file(monkeypatch):
    monkeypatch.setenv(host_fonts.FONT_ENV, "1")
    monkeypatch.setattr(host_fonts, "lendable_font_file", lambda: None)

    reason = host_fonts.missing_font_source()

    assert "DejaVuSans.ttf" in reason, reason
    assert "matplotlib" in reason, reason


def test_the_real_fonts_guard_skips_with_the_reason_that_names_the_missing_source(
    monkeypatch,
):
    monkeypatch.delenv(host_fonts.FONT_ENV, raising=False)
    monkeypatch.setattr(host_fonts, "load_run_fonts", lambda: False)
    monkeypatch.setattr(host_fonts, "has_real_fonts", lambda: False)

    @host_fonts.skip_unless_real_fonts
    def needs_glyphs():
        raise AssertionError("the guard let a fontless run reach the test body")

    with pytest.raises(pytest.skip.Exception) as skipped:
        needs_glyphs()

    assert host_fonts.FONT_ENV in str(skipped.value), str(skipped.value)


def test_the_no_fonts_guard_skips_saying_how_many_families_the_run_names(monkeypatch):
    monkeypatch.setattr(host_fonts, "load_run_fonts", lambda: False)
    monkeypatch.setattr(host_fonts, "has_real_fonts", lambda: True)
    monkeypatch.setattr(host_fonts, "_families", lambda: ["Arial", "Courier New"])

    @host_fonts.skip_unless_no_fonts
    def needs_box_glyphs():
        raise AssertionError("the guard let a run with fonts reach the test body")

    with pytest.raises(pytest.skip.Exception) as skipped:
        needs_box_glyphs()

    assert "2 families" in str(skipped.value), str(skipped.value)


def test_a_guard_runs_the_body_when_the_run_holds_the_font_state_it_wanted(monkeypatch):
    monkeypatch.setattr(host_fonts, "load_run_fonts", lambda: False)
    monkeypatch.setattr(host_fonts, "has_real_fonts", lambda: True)
    ran = []

    @host_fonts.skip_unless_real_fonts
    def needs_glyphs():
        ran.append(True)

    needs_glyphs()

    assert ran == [True], "the guard skipped a run that held what it asked for"
