"""Adds the two order checks that tell a published list from a bag walk."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "tests" / "test_react_design_system.py"

ANCHOR = "def test_a_token_is_reached_by_name_and_not_by_position("

ADDED = '''
def test_a_number_like_token_name_keeps_its_position(js: JsRuntime):
    """A bag walk puts a number-like name first, so this position proves the
    order came from the list."""
    payload = bridge_payload()
    payload["group_members"]["spacing"] = ["SPACE_XS", "7", "SPACE_S"]
    payload["tokens"]["7"] = dss.SPACE_XS
    payload["token_names"] = list(dss.TOKEN_NAMES) + ["7"]
    js.load(payload, SHADOW_COLOUR)
    names = js.ask("declarationNames")
    assert names[0] != "7", f"a number-like name reached the front: {names[:4]}"
    assert names.index("7") == names.index("SPACE_XS") + 1
    assert js.ask("value", "7") == f"{dss.SPACE_XS}px"


def test_a_token_that_renders_nothing_keeps_its_place_in_the_order(js: JsRuntime):
    """A name is published in order whether or not it renders, so the order
    is the surface list and not a walk of what rendered."""
    js.load(bridge_payload())
    names = js.ask("declarationNames")
    assert names == published_order()
    assert len(names) == len(dss.TOKEN_NAMES)
    for name in dss.SHADOW_NAMES:
        assert name in names
        assert js.ask("value", name) is None


'''


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    if ANCHOR not in source:
        print("MISSED the anchor")
        return
    TARGET.write_text(
        source.replace(ANCHOR, ADDED + ANCHOR, 1), encoding="utf-8", newline=""
    )
    print("added two order checks")


if __name__ == "__main__":
    main()
