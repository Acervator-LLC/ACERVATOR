"""A restore testing every saved choice it stores, with no RS001 finding.

`import_bot_state` tests `mode` against `RAMP_MODES` and `side` against
`TARGET_SIDES`. `engine_mode` reads `config`, which holds no saved document.
"""

from __future__ import annotations

import sys
from typing import Any

RAMP_SEARCH = "search"
RAMP_TRACK = "track"
RAMP_FIRE = "fire"
RAMP_MODES = (RAMP_SEARCH, RAMP_TRACK, RAMP_FIRE)
TARGET_SIDES = ("upper", "lower")
SCRUMMING_MODE = "scrumming"


def import_bot_state(data: dict[str, Any]) -> tuple[str, str | None]:
    """Return the `scrum_target_mode` and `scrum_target_side` `data` holds."""
    mode = str(data.get("scrum_target_mode", RAMP_SEARCH))
    if mode not in RAMP_MODES:
        mode = RAMP_SEARCH
    side = str(data.get("scrum_target_side", ""))
    return (mode, side if side in TARGET_SIDES else None)


def engine_mode(config: dict[str, Any]) -> str:
    """Return the engine `mode` `config` holds, defaulted to `SCRUMMING_MODE`."""
    return str(config.get("mode") or SCRUMMING_MODE)


def main() -> int:
    """Print what `import_bot_state` and `engine_mode` read, and return 0."""
    saved = {"scrum_target_mode": "fire", "scrum_target_side": "upper"}
    print(import_bot_state(saved))
    print(engine_mode({"mode": SCRUMMING_MODE}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
