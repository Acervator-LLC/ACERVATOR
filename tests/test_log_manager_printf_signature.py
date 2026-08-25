"""v3.23.70 — pin test for LogManager printf-style forwarding.

Regression fixture for the shutdown-path crash operator hit at boot
in v3.23.69: the shutdown block introduced in v3.23.59 calls
``log_manager.info("Cancelling %d pending tasks", len(_pending))``,
but ``LogManager.info`` (and warning/error/debug) accepted only one
positional arg — dropping the printf format args and, when the caller
passed any, raising ``TypeError: takes 2 positional arguments but 3
were given``.

Fix: extend the four wrapper methods to accept ``*args, **kwargs`` and
forward to the underlying ``logging.Logger`` method, matching stdlib
semantics.

These tests mirror the exact caller shapes in main.py:1103 / 1111 and
also assert generic *args forwarding.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core.logging_engine import LogManager  # noqa: E402


@pytest.fixture
def lm(tmp_path):
    return LogManager(log_dir=tmp_path)


# ---- Exact shutdown-path shapes ---------------------------------------- #


def test_info_accepts_printf_args_matching_main_py_1103(lm):
    """main.py:1103 — `info("Cancelling %d ... tasks", len(_pending))`.
    Must not raise regardless of arg count."""
    lm.info("Cancelling %d still-pending asyncio tasks", 5)
    lm.info("multi-arg %s -> %d", "asset", 42)


def test_warning_accepts_printf_args_matching_main_py_1111(lm):
    """main.py:1111 — `warning("drain raised: %s", _cancel_exc)`.
    Must not raise regardless of arg count."""
    lm.warning("pending-task drain at shutdown raised: %s", RuntimeError("boom"))


# ---- Symmetry across all four wrappers -------------------------------- #


@pytest.mark.parametrize("method", ["info", "warning", "error", "debug"])
def test_wrapper_forwards_positional_args(lm, method):
    fn = getattr(lm, method)
    fn("single arg")  # 0 extra
    fn("count=%d", 7)  # 1 extra
    fn("%s / %s", "a", "b")  # 2 extra


@pytest.mark.parametrize("method", ["info", "warning", "error", "debug"])
def test_wrapper_forwards_kwargs(lm, method):
    """Stdlib Logger accepts extra=... and exc_info=...; wrapper must too."""
    fn = getattr(lm, method)
    fn("with exc_info", exc_info=False)
    fn("with extra", extra={"custom_field": "x"})
