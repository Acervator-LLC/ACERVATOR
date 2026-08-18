# SADP — Novel Features Worth Rebuilding

**Date**: 2026-07-24
**Context**: Operator's directive: “No element of SADP should be considered valid or working at this point.” This report treats SADP the failed system as a source of *conceptual patterns*, not working code. The question: which of those concepts are genuinely novel — not already provided by Claude Code primitives, not forbidden by operator directive, and not made redundant by the external-tool harness now in place — such that they'd be worth rebuilding on top of the established-tools foundation?

**FALSIFICATION**: this report is wrong if (a) any “KEEP” recommendation duplicates a Claude Code native primitive I've overlooked, (b) any “REJECT” recommendation discards something the operator has since re-endorsed, or © the “novelty” claim for a rebuild can be satisfied by an existing pip-installable tool I didn't check.

---

## Scoring rubric

Each SADP feature is evaluated on four axes:

1. **Novel?** — Not already provided by Claude Code, git, pytest, or an established tool.
2. **Allowed?** — Not forbidden by explicit operator directive.
3. **Empirical value?** — Would rebuilding produce measurable behavior change vs. the current state?
4. **Cost to rebuild?** — How much code + coordination.

Verdict: **REBUILD** (all 4 favorable), **KEEP AS-IS** (already covered), **MAYBE** (mixed signals), or **REJECT** (fails one or more axes hard).

---

## REBUILD — high value, novel, empirically distinguishable

### 1. Persistent Subagent Team (Archetypes + Leads)

- **What it was**: Named domain specialists (`archetype_coding_engineering`, `lead_correctness`, etc.) that accumulate calibration + knowledge across sessions.
- **Novel?** YES. Claude Code's `Agent` tool spawns fresh subagents each call; there's no built-in persistent-identity mechanism.
- **Allowed?** YES.
- **Empirical value?** PROVEN in this session — three archetypes (Coding, GUI, Docs) built and passed multi-agent tests. Two-layer design (mechanical tool + LLM peer) demonstrably improved recall vs single-layer.
- **Cost?** LOW — pattern already established. Formalize `tools/harness/*_archetype.py` + reusable peer-review prompts stored as project skills.
- **Rebuild plan**: 
  - Codify the archetype/peer-review template as a reusable skill under `.claude/skills/archetype-peer-review/`.
  - Store per-archetype “calibration” as a Markdown file the peer-review prompt can inject (currently the prompt is inline).
  - Ship a small `spawn_reviewers(archetype_name, targets)` wrapper so any archetype run can trigger its 2-reviewer test with one call.

### 2. Claim Ledger (structural show-don't-tell)

- **What it was**: Every claim Claude made was logged with a status: `open` / `verified` / `refuted`. Nothing could close until verified.
- **Novel?** YES. Claude Code has no built-in claim-tracking; falsification is a discipline, not a mechanism.
- **Allowed?** YES.
- **Empirical value?** HIGH — directly addresses the operator's “trust is gone” concern by making unverified claims impossible to hide. This is the concrete instrument for the “show, don't tell” directive.
- **Cost?** MEDIUM — needs a `docs/audits/CLAIMS.jsonl` schema, a pre-cascade grep that fails if `status="open"` claims remain, and discipline to log every claim.
- **Rebuild plan**:
  - `tools/harness/claim_ledger.py` with `log_claim(text, evidence_needed) -> claim_id` and `verify(claim_id, evidence)`.
  - Pre-cascade hook in `check_release_readiness.py` that greps for open claims in the working session's audit dir.
  - Add “log claim” as a template step in every archetype's output.

### 3. Falsification Statement Discipline (in output templates)

- **What it was**: Every finding, decision, or claim shipped with a `FALSIFICATION:` line stating what would prove it wrong.
- **Novel?** PARTIAL. The discipline exists in this session (every archetype report has it). The novelty is *making it structural* — a fixed template field that must be filled.
- **Allowed?** YES.
- **Empirical value?** PROVEN — every audit report in `docs/audits/2026-07-24_*/` includes a FALSIFICATION line, and the discipline forces me to think about disproof rather than rhetorical assertion.
- **Cost?** LOW — codify the template in the archetype output schema and in the peer-review prompt.
- **Rebuild plan**: Update each `tools/harness/*_archetype.py` to add a `falsification` field to `ArchetypeReport`. Prompt archetypes to fill it based on the tool outputs.

---

## KEEP AS-IS — SADP had it, we already have real working replacements

### Ground-truth fixture discipline (positive + negative fixtures per check)
Present in every archetype: `known_good.*` + `known_bad.*` with labeled defects. Directly rebuilt by the current harness.

### Version Bump Cascade (R51 VBC) — the release gate
`tools/check_release_readiness.py` already exists and is real (thin shim → `sadp._tools.check_release_readiness`). Keep the tool, drop the SADP branding.

### Session-open orientation
Claude Code's CLAUDE.md + auto-memory + the `acervator` skill cover this. HOP5 is oversized but functional via `hop_open.py` tail excerpts.

---

## MAYBE — rebuild only when a concrete need surfaces

### 1. Numbered episodic memory (MEM-###) schema
- **Was**: `MEM-559` etc., a linear-numbered log of decisions.
- **Native alternative**: Claude Code auto-memory files with content-based keys.
- **Rebuild trigger**: If the operator wants a stable citable index for cross-document references (Part 8 PDF cites “MEM-559”). If not, native memory covers it.

### 2. Rule dependency graph
- **Was**: `depends_on: [R6, R43]` in `RULE_REGISTRY.json`.
- **Novel angle**: applies to tool configuration too (e.g., mypy strict mode depends on ruff being configured for the same type-hint style).
- **Rebuild trigger**: When a config change breaks a downstream tool silently. Not currently observed.

### 3. Universal Harness Capability Matrix (cross-LLM portability)
- **Was**: table of which SADP rules work under which model provider.
- **Rebuild trigger**: Only if you decide to run archetypes against non-Claude models (Ollama, GPT, Gemini). Currently no such need.

### 4. Fictional-archetype “Department Leads” (Part 6 PDF style)
- **Was**: personified archetypes as mnemonic aids.
- **Purely cosmetic** — no functional value beyond engagement. Rebuild only if the operator specifically wants the manual voice.

---

## REJECT — redundant with native tooling OR forbidden by operator

### 1. Token Timers / STM loops / RCN context footers
**Forbidden** by explicit operator directive (2026-05-31, re-asserted 2026-06-13): "DO NOT emit `⟦ctx …⟧` footers. Ever." Do not rebuild.

### 2. HOP Protocol as a full session-boundary handoff document
Claude Code's transcript-file access + auto-memory + skill loading covers the same use case at 1% of the size. The 724 KB HOP5 file is symptomatic of the old flow, not a design to preserve. Keep the concept of a lightweight session anchor (already in the `acervator` skill); reject the maximalist HOP5 pattern.

### 3. CODEBASE_EDIT_LOG.jsonl
`git log` + `git blame` do this natively and are the authoritative source. The JSONL log was a redundant parallel record that drifted.

### 4. ANCHORS system (session-start knowledge anchors)
`CLAUDE.md` + `.claude/skills/*/SKILL.md` do this natively. Adding a third layer (`ANCHORS.md`) was pure overhead.

### 5. RULE_REGISTRY.json + SPEC-CORE.md governance
Per operator directive: SADP was performative. The behavioral disciplines that mattered (parity across parallel implementations, cold-read before fix, falsification, no bridges sim↔live) are all captured in the current `acervator` skill as prose guidance. The 3,208-line SPEC-CORE and 77-entry RULE_REGISTRY were the failure mode, not the value.

---

## Concrete rebuild queue (if operator approves)

Ordered by empirical value / cost ratio:

| # | Item | Effort | Value |
|---|---|---|---|
| 1 | Add `falsification` field to `ArchetypeReport` schema; require in output template | 30 min | HIGH — pins the discipline structurally |
| 2 | Build `tools/harness/claim_ledger.py` + pre-cascade check | 2 hr | HIGH — closes the “unverified claim” loophole |
| 3 | Codify archetype/peer-review as a reusable skill under `.claude/skills/archetype-peer-review/` | 1 hr | MEDIUM — makes the pattern discoverable and repeatable |
| 4 | Store per-archetype calibration prompts as Markdown files (instead of inline in prompts) | 1 hr | MEDIUM — separates the calibration data from the wrapper code |
| 5 | Add duplicate-heading rule (DOC004) to docs archetype's structure checker | 15 min | LOW — closes the 20% recall gap surfaced in today's test |
| 6 | Add semantic-signal-wiring rule to GUI archetype | 45 min | LOW — closes the gap where reviewers found inert widgets |

Items 1-3 are the highest-leverage rebuilds. Item 6 already has a matching finding in today's report. Items 4-5 are cleanup.

**No item requires re-importing anything from `sadp/` or `sadp2/`.** The rebuilds live under `tools/harness/` and `.claude/skills/`, with zero coupling to the deprecated code.

---

## Verdict

Three SADP concepts are worth rebuilding: **persistent subagent team** (proven this session), **claim ledger** (directly addresses the operator's trust concern), and **falsification statement in output template** (already practiced, just needs codifying). Everything else is either already covered by Claude Code + git + established tools, or explicitly forbidden.

The rebuild is ~4 hours of work total, entirely under `tools/harness/` and `.claude/skills/`, no cascade required until the operator wants to ship.

Ready for the operator's call on which items (if any) to build next.
