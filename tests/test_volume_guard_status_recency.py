"""``VolumeGuard.get_status`` counts recent executions by when they finished.

``ExecutionReport.execution_time_ms`` is how long a call took, not when it ran,
so the recency window reads ``completed_at``.
"""

from __future__ import annotations

import time

from src.trading.volume_guard import ExecutionReport, VolumeGuard


def _report(strategy: str, completed_at: float | None = None) -> ExecutionReport:
    """An ExecutionReport that took 42 ms, stamped now unless told otherwise."""
    report = ExecutionReport(
        success=True,
        symbol="BONK/USD",
        side="sell",
        requested_amount=1000.0,
        executed_amount=1000.0,
        chunks_planned=3,
        chunks_executed=3,
        avg_fill_price=0.0000031,
        estimated_slippage_pct=0.4,
        actual_slippage_pct=0.3,
        total_quote=0.0031,
        execution_time_ms=42.0,
        strategy=strategy,
    )
    if completed_at is not None:
        report.completed_at = completed_at
    return report


def test_a_report_finished_now_counts_as_recent():
    guard = VolumeGuard()
    guard._execution_history.append(_report("iceberg_3"))

    status = guard.get_status()

    assert status["recent_executions"] == 1, status
    assert status["iceberg_executions"] == 1, status


def test_a_report_finished_over_an_hour_ago_is_not_recent():
    guard = VolumeGuard()
    guard._execution_history.append(
        _report("iceberg_3", completed_at=time.time() - 3601)
    )

    status = guard.get_status()

    assert status["total_executions"] == 1, status
    assert status["recent_executions"] == 0, status
    assert status["iceberg_executions"] == 0, status


def test_a_single_strategy_report_is_not_counted_as_an_iceberg():
    guard = VolumeGuard()
    guard._execution_history.append(_report("single"))

    status = guard.get_status()

    assert status["recent_executions"] == 1, status
    assert status["iceberg_executions"] == 0, status
