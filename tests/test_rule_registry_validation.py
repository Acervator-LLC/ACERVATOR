"""``RuleRegistry._validate_rule`` against the ids ``RULE_META`` declares."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.rule_registry import RULE_META, VALID_RULES, RuleRegistry


def _registry(tmp_path: Path) -> RuleRegistry:
    return RuleRegistry(path=tmp_path / "rules.json")


def test_every_rule_in_the_metadata_is_accepted(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    for rule in RULE_META:
        assert reg.is_locked(rule) is True, f"{rule} was rejected or not locked"


def test_the_rejection_names_the_highest_rule_the_registry_knows(
    tmp_path: Path,
) -> None:
    reg = _registry(tmp_path)
    highest = max(VALID_RULES, key=lambda r: int(r[1:]))
    with pytest.raises(ValueError) as excinfo:
        reg.is_locked("R999")
    message = str(excinfo.value)
    assert highest in message, (
        f"rejection message {message!r} does not name {highest}, the highest id "
        f"in RULE_META, so it under-reports what the registry accepts"
    )


def test_an_id_above_the_metadata_is_rejected(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(ValueError):
        reg.is_locked("R999")


def test_a_bare_number_is_read_as_a_rule_id(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    assert reg.is_locked("1") is True
