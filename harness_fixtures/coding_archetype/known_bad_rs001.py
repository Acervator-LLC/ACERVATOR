"""A restore storing a saved choice with no test, with two RS001 findings.

`bot_from_record` returns `scrum_target_mode` inline and `import_bot_state`
returns it through `_mode`. Neither carries an `in` test.
"""

from __future__ import annotations

import sys
from typing import Any

RAMP_SEARCH = "search"


def bot_from_record(record: dict[str, Any]) -> str | None:
    """Return the `scrum_target_mode` the `saved` section of `record` holds."""
    saved = record.get("saved", {})
    return (
        str(saved["scrum_target_mode"])
        if saved.get("scrum_target_mode") is not None
        else None
    )


def import_bot_state(data: dict[str, Any]) -> str:
    """Return the `scrum_target_mode` `data` holds, defaulted to `RAMP_SEARCH`."""
    mode = str(data.get("scrum_target_mode", RAMP_SEARCH))
    return mode


def main() -> int:
    """Print what `bot_from_record` and `import_bot_state` read, and return 0."""
    print(bot_from_record({"saved": {"scrum_target_mode": "fire"}}))
    print(import_bot_state({"scrum_target_mode": "fire"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
