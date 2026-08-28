"""A file with FIVE deliberately-introduced code-quality defects.

Ground truth — each defect is labeled with the tool expected to
catch it:

  D1  unused_import          line 14    Vulture
  D2  unused_variable        line 22    Vulture (confidence-dependent)
  D3  missing_type_hints     line 21    Mypy
  D4  hardcoded_password     line 17    Bandit (B105)
  D5  assert_for_security    line 27    Bandit (B101)

The archetype MUST catch D1, D3, D4, D5 (well-established rule hits).
Vulture's D2 detection is confidence-dependent; if it drops below
threshold, that is a known limitation to document, not a bug in
the archetype.
"""
import subprocess  # D1 unused_import — Vulture should flag


DB_PASSWORD = "hunter2"  # D4 hardcoded_password — Bandit B105 should flag


def broken_types(x, y):  # D3 missing_type_hints — Mypy should flag
    unused_local = 42  # D2 unused_variable — Vulture flags at 60%+ confidence
    return x + y


def check_positive(n: int) -> int:
    assert n > 0  # D5 assert_for_security — Bandit B101 should flag
    return n * 2


def entry() -> None:
    print(broken_types(1, 2))
    print(check_positive(3))


if __name__ == "__main__":
    entry()
