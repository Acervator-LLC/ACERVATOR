# Coding Archetype — Multi-Agent Simulated Test

**Date**: 2026-07-24
**Author**: Claude (session 27)
**Purpose**: Prove or falsify that the first re-created agent archetype (built per the updated SKILL.md) works as an initial design.

---

## What was built

`tools/harness/coding_archetype.py` — a single class `CodingArchetype` that:

1. Takes a `Path` (file or directory) to review.
2. Subprocess-invokes three established, installed third-party tools:
   - **mypy** (PEP 484 type checking)
   - **bandit 1.9.4** (Python security lint)
   - **vulture 2.16** (dead-code detection)
3. Parses each tool's output into normalized `Finding` objects with `severity ∈ {critical, high, medium, low, info}`.
4. Aggregates into an `ArchetypeReport` with `passed` (bool: True iff no high/critical), `by_tool` count, `by_severity` count, and the full findings list.

**Design decisions:**
- No dependency on any `sadp/` or `sadp2/` module. The archetype is self-contained under `tools/harness/`.
- Tools are called as subprocesses, not imported. A tool crash or version change does not take down the archetype.
- Each tool's output is parsed with a per-tool regex or JSON reader; no shared “universal parser.”
- The severity map is documented in the class body — I did NOT invent severity levels, I mapped tool-native levels to a normalized set.

**FALSIFICATION**: this design is wrong if (a) the tools are not actually installed (report will list them as `missing`), (b) any tool's output format changes and the parser stops matching (findings drop to zero on the known-bad fixture), or © the subprocess exits non-zero for reasons unrelated to findings (I catch and log, not silently pass).

---

## Ground truth — the test fixtures

Two Python files in `fixtures/`, each with a hand-labeled defect list:

- `known_good.py` — clean code, docstrings on every function, full type hints, no security issues. Ground truth = 0 defects.
- `known_bad.py` — five deliberately-introduced defects with labels in the module docstring:
  - **D1**: `import subprocess` unused → expected caught by Vulture
  - **D2**: local variable `unused_local = 42` → expected caught by Vulture (confidence-dependent)
  - **D3**: `def broken_types(x, y):` missing type hints → expected caught by Mypy
  - **D4**: `DB_PASSWORD = "hunter2"` hardcoded credential → expected caught by Bandit (B105)
  - **D5**: `assert n > 0` used as runtime check → expected caught by Bandit (B101)

---

## Test methodology

Three independent reviewers, same two fixtures, judgments compared to ground truth:

1. **CodingArchetype** (deterministic, tool-based) — the code we built.
2. **Peer Reviewer A** — Claude subagent (`Agent(subagent_type="general-purpose")`), instructed to review from judgment only, no tool invocation. 400-word cap, structured JSON output.
3. **Peer Reviewer B** — second Claude subagent, launched in parallel with A, no shared context, same instructions.

Multi-agent aspect: A and B were launched with a single message containing two `Agent` tool calls, so they ran concurrently on different worker sessions. Neither could see the other's findings or the archetype's findings.

Full transcripts saved at `raw/`:
- `archetype_known_good.json`
- `archetype_known_bad.json`
- `peer_reviewer_A.md`
- `peer_reviewer_B.md`

---

## Results

### Recall on known_bad.py (5 ground-truth defects)

| Defect | CodingArchetype | Peer Reviewer A | Peer Reviewer B |
|---|---|---|---|
| D1 unused_import | ✓ vulture / high | ✓ medium | ✓ medium |
| D2 unused_variable | ✗ **MISS** | ✓ low | ✓ low |
| D3 missing_type_hints | ✗ **MISS** | ✓ medium | ✓ medium |
| D4 hardcoded_password | ✓ bandit B105 / low | ✓ high | ✓ high |
| D5 assert_for_security | ✓ bandit B101 / low | ✓ high | ✓ high |
| **Recall** | **3/5 (60%)** | **5/5 (100%)** | **5/5 (100%)** |

### Precision on known_good.py

| Reviewer | Total findings | High/critical | False positives on ground truth |
|---|---|---|---|
| CodingArchetype | 0 | 0 | 0 |
| Peer Reviewer A | 2 (both low) | 0 | 0 |
| Peer Reviewer B | 3 (all low) | 0 | 0 |

No reviewer produced a high-severity false positive on the clean fixture.

### Findings on known_bad the archetype could NOT produce (semantic / judgment)

Both peer reviewers surfaced defects the mechanical archetype has no way to see:
- **Missing docstrings** on `broken_types`, `check_positive`, `entry`, `main` (both reviewers).
- **Untyped `x + y` silently accepts strings/lists** — latent type-confusion bug (Reviewer B).
- **Bare `AssertionError` with no message** — poor diagnostics (Reviewer B).
- **Module-level `DB_PASSWORD` widens credential blast radius** to any importer (both reviewers, phrased differently).
- **Fixture-pair style inconsistency** — `from __future__ import annotations` present in good, absent in bad (both reviewers).

### Severity divergence

Bandit's default output ranks the hardcoded password (D4) and assert-as-security-check (D5) as **low** severity. Both human-equivalent peer reviewers ranked them **high**. This is a real disagreement worth surfacing: bandit's raw severities under-classify well-known security anti-patterns, and if we ship the archetype with bandit's severities unremapped, real security issues will not trip the `passed=False` gate.

---

## Detailed reasoning — what the test proves

1. **The archetype's core design works.** It ran end-to-end on both fixtures, all three tools were `ok` in tool_availability, findings were structured and correctly serialized to JSON, and the pass/fail gate correctly fired (`passed=true` on good, `passed=false` on bad).

2. **The archetype has real, measurable recall gaps.** 60% recall on a hand-crafted fixture is honest evidence of the harness's limitations — specifically:
   - Mypy in default config does NOT flag missing type hints. To catch D3, invoke mypy with `--disallow-untyped-defs` or an equivalent strict-mode flag.
   - Vulture is stronger on unused imports/classes than unused function locals. Its default confidence threshold missed D2. This is a known behavior of Vulture, not a bug in the archetype's use of it.
   - These are configuration gaps in the archetype, not fundamental limits of the tools.

3. **Multi-agent addition materially improves recall.** Reviewer A and B independently reached 100% recall on ground truth, plus surfaced 4-5 semantic findings the mechanical archetype cannot see. This is direct empirical evidence that a two-layer archetype (mechanical + LLM peer review) covers strictly more failure modes than either alone.

4. **The two independent reviewers agree.** A and B independently caught the same 5 ground-truth defects and largely the same semantic extras. Their agreement is evidence that the peer-review signal is not agent-luck-of-the-draw — it's a reliable class of finding an LLM reviewer can produce.

5. **Style-preference noise is present in LLM output.** Both reviewers flagged docstring gaps and print-vs-logger preferences on the clean file. If the archetype uses LLM peer review as a hard gate, findings would need to be filtered by severity (only `high` blocks; `low`/`medium` are advisory).

---

## What this does NOT prove

- **The archetype is production-ready.** It's a first cut with documented recall gaps.
- **The archetype catches real hallucinations.** Semantic hallucination detection is not what the three underlying tools do. That would require RAGAS/DeepEval/Guardrails AI (which are NOT installed, per the SKILL Tool Integration Report).
- **The archetype works on non-Python content.** Only Python fixtures were tested.
- **The peer-review LLMs are cheap.** Each subagent used ~38K tokens (~76K total). Scaling to 400-file corpora as we did with the SADP quarantine sweep would be materially more expensive.

---

## Concrete gaps found (would need fixing before shipping)

1. **Mypy invocation** should include `--disallow-untyped-defs --disallow-incomplete-defs` when strict type discipline is required. Currently uses defaults, which are permissive.
2. **Bandit severity remapping** — the archetype should upgrade B105 (hardcoded password) and B101 (assert-for-security) from bandit's `LOW` to at least `HIGH` in the archetype's normalized severity space. Otherwise `passed=True` returns for a file with a hardcoded password.
3. **Vulture confidence threshold** for unused locals is a known weakness; either invoke with `--min-confidence 60` and accept more noise, or document that unused-locals detection is out-of-scope.
4. **No prose linting yet.** For a full harness we'd add Ruff (formatting) and pytest execution (behavioral). Both are noted in the SKILL as installable but not covered by this archetype.

---

## Verdict

The initial design **works structurally** — it invokes real installed tools, parses their output correctly, correctly separates clean from dirty code, and produces a deterministic pass/fail gate. The multi-agent test **confirms** the mechanical archetype is insufficient on its own for high-recall coverage; a layered design that adds LLM peer review would materially improve recall on both known-defect classes and unknown-defect semantic classes.

**Recommendation**: proceed to a second archetype (GUI or Documentation) using the same pattern (subprocess-invoke real installed tools, normalize findings, aggregate report). Fix the three archetype config gaps above before treating any archetype's `passed=True` as a green gate.

---

## Raw evidence

- `raw/archetype_known_good.json` — full archetype output on clean fixture
- `raw/archetype_known_bad.json` — full archetype output on dirty fixture
- `raw/peer_reviewer_A.md` — full Reviewer A transcript
- `raw/peer_reviewer_B.md` — full Reviewer B transcript
- `fixtures/known_good.py` — clean fixture with docstring stating ground truth = 0 defects
- `fixtures/known_bad.py` — dirty fixture with docstring listing the 5 labeled defects (D1–D5)

To reproduce:
```
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_good.py
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_bad.py
```
