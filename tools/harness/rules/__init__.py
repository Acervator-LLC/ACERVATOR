"""Shared archetype rule modules — universal across coding/gui/docs
archetypes (with per-language applicability declared per module).

Introduced 2026-08-01 as v3.23.90 in response to operator's directive
2026-08-01: "Scaffolding-detection should be universal to all
archetypes as should hallucination-detection but slop probably only
applied to coding."

Contract for each module:

    def scan(target: Path, source: str) -> list[Finding]

where Finding matches the schema in tools.harness.coding_archetype.
Each module is language-scoped (returns [] when target.suffix is not
in its supported set) so archetypes can call all modules
indiscriminately without dispatch logic.
"""

from __future__ import annotations

__all__ = ["scaffolding", "hallucination", "slop", "numeric_guard"]
