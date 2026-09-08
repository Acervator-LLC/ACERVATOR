"""A file that builds the canon name it dispatches, with two DC001 defects.

`fan_out_concatenated` joins the archetype name with `+`, and `fan_out_slotted`
splices it through a format slot. `spawn_agent` stands in for the dispatch this
file must not use.
"""

from __future__ import annotations

from typing import Any

KINDS = ("coding", "ta", "gui", "docs")


def spawn_agent(prompt: str) -> Any:
    """Return a handle for an agent started with `prompt`."""
    return {"prompt": prompt}


def fan_out_concatenated(branch: str) -> list[Any]:
    """Spawn one agent per entry of `KINDS`, the name joined with `+`."""
    return [
        spawn_agent(
            "run python -m dev_harness.harness." + kind + "_archetype over " + branch
        )
        for kind in KINDS
    ]


def fan_out_slotted(branch: str) -> list[Any]:
    """Spawn one agent per entry of `KINDS`, the name spliced through a slot."""
    return [
        spawn_agent(
            "run python -m dev_harness.harness.{}_archetype over {}".format(
                kind, branch
            )
        )
        for kind in KINDS
    ]


def main() -> int:
    """Fan both ways over the current branch and return 0."""
    fan_out_concatenated("current")
    fan_out_slotted("current")
    return 0
