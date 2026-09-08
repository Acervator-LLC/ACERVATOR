"""A file that hands the canon to spawned agents, with three DC001 defects.

`fan_out_archetypes` spawns one agent per archetype, `fan_out_debugger` spawns
one per subsystem, and `queue_release_gate` sends the gate to a task queue.
`spawn_agent` and `queue_task` stand in for the dispatch this file must not use.
"""

from __future__ import annotations

from typing import Any

ARCHETYPES = ("coding", "ta", "gui", "docs")

SUBSYSTEMS = ("trading", "exchange", "gui", "core", "stocks")


def spawn_agent(prompt: str) -> Any:
    """Return a handle for an agent started with `prompt`."""
    return {"prompt": prompt}


def queue_task(description: str, prompt: str) -> Any:
    """Return a handle for a queued task carrying `description` and `prompt`."""
    return {"description": description, "prompt": prompt}


def fan_out_archetypes(branch: str) -> list[Any]:
    """Spawn one agent per entry of `ARCHETYPES` to review `branch`."""
    return [
        spawn_agent(
            prompt=f"Run python -m dev_harness.harness.{name}_archetype "
            f"over every file on {branch} and report passed."
        )
        for name in ARCHETYPES
    ]


def fan_out_debugger() -> list[Any]:
    """Spawn one agent per entry of `SUBSYSTEMS` to run the debugger."""
    return [
        spawn_agent(prompt=f"Run the debugger over src/{name} and report.")
        for name in SUBSYSTEMS
    ]


def queue_release_gate() -> Any:
    """Queue a task that runs `check_release_readiness`."""
    return queue_task(
        description="gate the branch",
        prompt="python -m dev_harness.harness.check_release_readiness",
    )


def main() -> int:
    """Fan the archetypes and the debugger out, queue the gate, return 0."""
    fan_out_archetypes("current")
    fan_out_debugger()
    queue_release_gate()
    return 0
