"""Control for CHANGE 1: a pytest file whose REAL defects still block.

The test-file exemption removes five rules pytest cannot comply with.
If it removed anything else, this file would pass, and the gate on
test files would be decoration.

Every defect below is a genuine one that a test file CAN and should
avoid:

  * a bare ``try/except/pass`` that swallows the failure the test
    exists to detect (ruff S110)
  * ``random`` seeding the data under test, so a failure is not
    reproducible (ruff S311)
  * a hardcoded credential as a DEFAULT ARGUMENT (bandit B107 -- note
    that S105/S106 ARE exempt and B107 is not, which is the point)
  * a ``NotImplementedError`` stub shipped as if finished (scaffolding)

The asserts themselves are idiomatic pytest and must NOT be counted.
"""
from __future__ import annotations

import random


def connect(host: str = "localhost", token: str = "hunter2-real-token"):
    """Hardcoded credential in a default argument."""
    return f"{host}:{token}"


def build_fixture_rows():
    """Unseeded randomness makes any failure unreproducible."""
    return [random.random() for _ in range(4)]


def pending_helper():
    """A stub shipped as if finished."""
    raise NotImplementedError("wire this up later")


def test_rows_are_bounded():
    """The except/pass turns a real failure into a silent pass."""
    rows = build_fixture_rows()
    try:
        assert all(0.0 <= r <= 1.0 for r in rows)
        assert connect() != ""
    except Exception:
        pass
