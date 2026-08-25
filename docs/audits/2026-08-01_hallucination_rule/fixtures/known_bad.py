"""Fixture: ground-truth hallucination defects.

Ground truth:
    D1 (H001, medium) — reference to src/trading/nonexistent.py    line ~14
    D2 (H001, medium) — reference to docs/audits/2020-01-01_.../fake.md line ~15
    D3 (H002, low)    — reference to sadp/ (retired subsystem)      line ~18
    D4 (H002, low)    — reference to RAIntSimBat/ (retired)         line ~19
    D5 (H003, medium) — import from src.trading.hallucinated_module line ~25
    D6 (H003, medium) — import src.nonexistent.thing                line ~26
"""

from __future__ import annotations

# D1: See src/trading/nonexistent.py for the pattern.
# D2: Per docs/audits/2020-01-01_missing/fake.md, the flow is X.

# Historical context:
# D3: Formerly lived in sadp/RAIntSimBat/sim_bot.py.
# D4: The RAIntSimBat/ battery is retired.


# The imports below don't resolve.
# D5:
from src.trading.hallucinated_module import fake_symbol  # noqa

# D6:
import src.nonexistent.thing  # noqa


def use_it() -> None:
    fake_symbol()
    src.nonexistent.thing  # noqa
