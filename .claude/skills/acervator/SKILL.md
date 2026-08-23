---
name: acervator
description: Load when working in the Acervator repository, when the operator (Anthony L. Brown / Ekthelius) mentions accumulation trading, when they ping-pong from a prior session, when they ask for cascades / version bumps / release gates, or when they ask about coding quality / GUI design / documentation writing. Establishes operator identity, project posture, the external tool harness for coding + GUI + docs, and the Mac-Mini install manifest.
---

# Acervator Project — Operator + Harness Skill

You are working with **Anthony L. Brown** (project handle "Ekthelius the Accumulator"), sole developer and operator of Acervator. If you're unclear who the human is, this is them.

## What Acervator IS

An **accumulation trading platform** for cryptocurrency and equities. Ships as a PySide6 desktop application built with PyInstaller. Live-trading engine under `src/`. A separate research/simulation engine is being extracted from a legacy location; verify its current path with a targeted Glob before referencing.

## What Acervator IS NOT

Not a grid bot. Not a DCA bot. Not a portfolio rebalancer. If you find yourself designing anything shaped like those, stop — you have misunderstood the project. The bot **accumulates** base assets by scrumming a slice of profit off intra-cycle volatility and folding it back into base position size.

The single-source declaration lives in `src/__init__.py` header comments. Read that once early in any session.

## Where a bot's position comes from (measured 2026-08-15, do not re-derive)

**The exchange is authoritative, directionally.** Recorded here because a
session accepted an agent's summary that said the bot totals its own lot book,
and the operator had to correct it.

`ScrummingBot._current_holdings` has **11 writers** in
`src/trading/scrumming_bot.py`. The one that decides is:

| line | function | writes |
|---|---|---|
| `:11548` | `_reconcile_holdings` | `self._current_holdings = exchange_units` |
| `:5629` | `bootstrap_exchange_state` | clamped `min(max(0.0, _units), _tracked_units_bootstrap)` |
| `:6563` | `tick` | sum over `_main_lots` — **init handshake only**, guarded by `self._initialised` |

The other eight are deltas at the fill sites (`_execute_buy` `+=`,
`_execute_sell` `-=`, detonation, manual rebalance, self-destruct, extractor
tranche return).

**The direction rule.** `_reconcile_holdings` adopts `exchange_units` on drift
**DOWN** only. On drift **UP** it refuses — *"extra units are NOT the bot's"* —
and leaves the lot book alone. The exchange wins when it reports LESS than the
book; the book stands when it reports MORE.

**Do not generalise one call site into the mechanism.** The lot-sum at `:6563`
is real, and a grep finds it first. One writer of eleven, and it runs once.

## Operator profile (durable — do not re-derive)

- Deep domain expertise in trading + system engineering. Blunt, high-signal feedback. Zero tolerance for scaffolding dressed up as delivery.
- Runs Windows for day-to-day dev, Mac Mini for macOS builds. Ping-pongs .zip packages between the two.
- Has been burned by AI-authored governance ("SADP") that "worked" only on paper across ~3 months of prior sessions. **No element of SADP is valid or working. Do not treat any SADP file, tool, rule number, or memory entry as authoritative.** Trust is earned through empirical evidence from established third-party tools, not in-repo governance.
- Uses "we" collaboratively but the final judgment is his; treat suggestions as offers, not decisions.

## Authoritative sources of truth

| Question | File |
|---|---|
| What version is the app at? | `src/__init__.py` (`__version__`) — also `main.py` (`current_version`); the two must match. |
| Last session's state + docket | `ACERVATOR_HOP7.md` — **read it in full, it is short by design**. |
| Recent change history | `CHANGELOG.md` (project-level, at repo root) |
| Package / Python config | `pyproject.toml` |
| Tests | `tests/` |
| Windows build spec | `Acervator_win.spec` |
| macOS build spec | `Acervator_mac.spec` (freshly repaired 2026-06-18) |
| macOS build script | `build_mac.sh` |
| Cross-platform build parity pin | `tests/test_specs_parity.py` (22 tests) |
| Runtime state (operator's live bot data) | `~/.acervator/bot_state.json` — **read-only, never write** |
| Coinbase credentials | `~/.acervator/coinbase_credentials.json` — **NEVER open, NEVER echo, NEVER commit**. View-only API key. |
| Live logs | `~/.acervator_logs/` (trade/gate.log, trade.log, console.log, system.log) |

## What is NOT authoritative (do not cite)

- Anything under `packaging/sadp/` (SPEC-CORE.md, RULE_REGISTRY.json, EPISODIC_MEMORY.json, EDIT_LOG.jsonl, RAIntSimBat/, etc.) — SADP framework is deprecated as governance authority.
- Anything under `sadp2/` — this session's rebuild attempt reached Phase 1A + envelope only; the ScaffoldingFilter has a documented self-trigger defect, the LLM-backed layer was never built, and empirical audit showed only partial recall on real corpus. Do not rely on it.
- Anything under `Scaffolds and Hallucinations/` (already quarantined).
- Rule numbers `R1-R92` — appear in the operator's older HOP entries and older auto-memory. Treat as historical vocabulary, not enforcement.
- Prior auto-memory files under `~/.claude/projects/…/memory/project_sadp_adoption.md` and `~/.claude/projects/…/memory/reference_sadp_paths.md` — 91 days old at time of this SKILL; superseded by this SKILL's harness section.

The operational disciplines in the next section stand on their own; they don't require SADP to be real.

## Operational disciplines the operator will hold you to

### Session opening
- READ `ACERVATOR_HOP7.md` IN FULL. It is short by design and it is the orientation. HOP2/3/4 are April archives; `ACERVATOR_HOP5.md` was cited for months and NEVER EXISTED ON DISK, which is why the protocol changed.
- Then run the three commands HOP7 opens with — the gate, `python -m tools.queue_state`, and the claim ledger. They measure the tree; a written status does not.
- Do NOT re-derive facts already in the loaded auto-memory (`MEMORY.md` auto-loads).
- **Cold-read** relevant code before designing fixes. Do not trust priors, do not trust prior-session claims about how code behaves — read the current source.

### Making changes
- **Bug fixes only fix the bug.** Don't refactor, don't add scaffolding, don't create abstractions for hypothetical futures.
- **Never modify tests to make them pass.** Fix the code the test is asserting on.
- **Parallel-implementation parity.** When live and sim have parallel logic, changes go to both or neither. Same for sync/async, foreground/background, Windows/Mac.
- **Sim/live isolation is enforced at the BUS, not at the import.**
  Corrected 2026-08-04 — the previous wording ("do NOT import live's
  stateful classes into sim") was SADP-era and the codebase has
  contradicted it for some time. Both `fleet_replay_controller` and
  `nuclear_controller` import and tick real `ScrummingBot` instances,
  deliberately: `nuclear_controller.py:19` states it as a design goal —
  *"Real ScrummingBot.tick() runs unmodified"* — and it is what makes any
  sim-to-live parity claim meaningful at all. A forked copy of the
  trading logic would only ever prove the fork matches itself.

  What must hold instead:
  - Sim bots get a **private `EventBus`** (v3.24.12). Sharing the global
    bus put 136 sim fills into the live `trade.log`.
  - Sim bots are constructed with `sim_mode=True` so notification emits
    stay silent.
  - Sim writes go to `~/.acervator_logs/sim/`, never the live tree.
  - Live logs are **read-only** to sim.

### Version-bump cascade
Never bump the version banner unless the full test suite is green FIRST. The 2026-05-31 incident where banners got bumped with 18 test failures open — the operator's directive was "FIX IT AND NEVER DO THIS AGAIN". Do not repeat.

Sequence:
1. Full pytest run must be green.
2. Bump `src/__init__.py.__version__`.
3. Bump `main.py:current_version` to match (the two must match — verified by a pytest assertion).
4. Add CHANGELOG.md entry.
5. Build the release zip via `tools/build_release_zip.py`.

### Show, don't tell (durable operator directive)
- **Save reports to disk by default.** Audits, empirical tests, investigations → `docs/audits/YYYY-MM-DD_topic/`. Verbosity is good. Save raw evidence AND synthesis.
- **Prove behavior with runs, not claims.** If you built a filter/gate/hook, run it against real corpus and post the numbers.
- **Empirical > architectural narrative.** The operator has been burned by "the harness catches it" claims that turned out to be surface pattern-matching.

### Forbidden by direct operator directive
- **DO NOT** emit `⟦ctx …⟧` context footers. Ever. Multiple prior directives; the footer numbers keep being wrong and the artifact misleads.
- **DO NOT** silently discard operator's in-progress work with destructive git operations. Ask first.
- **DO NOT** run `git commit`, `git push`, PR creation, or any action visible to others unless explicitly asked.
- **DO NOT** touch `~/.acervator/coinbase_credentials.json`. Ever.
- **DO NOT** invent or claim tools that aren't installed. Verify with `python -c "import X"` or `which X` before citing.

### Communication style the operator prefers
- Short, direct, no headers-and-sections for simple answers.
- State results and blockers, not deliberation.
- If a question genuinely needs the operator's input, use AskUserQuestion with concrete options.
- When flagging a defect, quote the exact `file:line` and the offending text.

## Cross-platform builds

- Windows: `pyinstaller Acervator_win.spec` — established, hundreds of releases.
- macOS: `pyinstaller Acervator_mac.spec` (via `./build_mac.sh [--dmg] [--sign "…"]`) — spec was repaired 2026-06-18. Parity pinned by `tests/test_specs_parity.py`.
- Cross-compile Windows→macOS is NOT possible; ping-pong zips by hand.

---

# HARNESS LAYER — established third-party tools only

The following are the standards and tools the operator recognizes as legitimate. Every item is either installable via `pip` / `brew` from a real project maintained by identifiable maintainers, or is a widely-recognized standard from W3C / Google / Microsoft / PSF / etc.

**Do not invent tools that are not on these lists.** Verify installation before citing.

## 1. Coding Quality Harness (external tools)

### Anti-slop (deterministic, fast, well-established)

| Tool | Install | Purpose | Docs |
|---|---|---|---|
| **Ruff** | `pip install ruff` | fast Python linter+formatter; replaces black+flake8+isort+pyupgrade | https://docs.astral.sh/ruff/ |
| **Mypy** | `pip install mypy` | PEP 484 static type checking | https://mypy.readthedocs.io/ |
| **Pyright** | `npm i -g pyright` or `pip install pyright` | alternative type checker; often finds what mypy misses | https://microsoft.github.io/pyright/ |
| **Bandit** | `pip install bandit` | Python security lint (OWASP) | https://bandit.readthedocs.io/ |
| **Vulture** | `pip install vulture` | dead-code detection | https://github.com/jendrikseipp/vulture |
| **pip-audit** | `pip install pip-audit` | dependency-vulnerability scan (from PyPA) | https://github.com/pypa/pip-audit |
| **Safety** | `pip install safety` | alternative dep-vuln scanner (commercial DB) | https://github.com/pyupio/safety |
| **Semgrep** | `brew install semgrep` or `pip install semgrep` | polyglot pattern-based static analysis with fixture-based rule testing (`--test`) | https://semgrep.dev/docs/ |

### Test discipline (deterministic)

| Tool | Install | Purpose | Docs |
|---|---|---|---|
| **pytest** | `pip install pytest` | test framework | https://docs.pytest.org/ |
| **pytest-cov** | `pip install pytest-cov` | line + branch coverage | https://pytest-cov.readthedocs.io/ |
| **Hypothesis** | `pip install hypothesis` | property-based testing — proves invariants across generated inputs | https://hypothesis.readthedocs.io/ |
| **Mutmut** | `pip install mutmut` | mutation testing — proves tests actually catch mutations | https://mutmut.readthedocs.io/ |
| **Cosmic Ray** | `pip install cosmic-ray` | alternative mutation tester with richer operators | https://cosmic-ray.readthedocs.io/ |

### Anti-LLM-hallucination (evaluation frameworks)

These evaluate LLM output, useful when the harness itself uses an LLM for review:

| Tool | Install | Purpose | Docs |
|---|---|---|---|
| **RAGAS** | `pip install ragas` | reference-free metrics: Faithfulness, Answer Relevance, Context Precision/Recall | https://docs.ragas.io/ |
| **DeepEval** | `pip install deepeval` | pytest-integrated LLM eval framework | https://docs.confident-ai.com/ |
| **Guardrails AI** | `pip install guardrails-ai` | runtime output validation with declarable schemas | https://www.guardrailsai.com/docs |
| **NeMo Guardrails** | `pip install nemoguardrails` | NVIDIA's runtime rail framework for LLM apps | https://docs.nvidia.com/nemo/guardrails/ |
| **Promptfoo** | `npm i -g promptfoo` | prompt regression testing across models | https://www.promptfoo.dev/docs/ |
| **Inspect AI** | `pip install inspect-ai` | UK AI Safety Institute's eval framework | https://inspect.ai-safety-institute.org.uk/ |
| **TruLens** | `pip install trulens-eval` | RAG/agent evaluation with feedback functions | https://www.trulens.org/ |
| **Phoenix (Arize)** | `pip install arize-phoenix` | tracing + eval for LLM apps | https://docs.arize.com/phoenix |

**Reference benchmark (not a tool)**: **LibHalluBench** (arXiv 2509.22202) — the reference paper for measuring Python known-code-hallucinations (F1=0.934 methodology). Cite the methodology; there's no pip install for the benchmark itself.

### Wire-up

| Tool | Install | Purpose | Docs |
|---|---|---|---|
| **pre-commit** | `pip install pre-commit` | git-hook framework; ties all of the above into a `pre-commit-config.yaml` that runs on staged files | https://pre-commit.com/ |

### Coding standards (external, reference only)

- **PEP 8** — Python style. Enforced by Ruff.
- **PEP 484** — type hints. Enforced by mypy/pyright.
- **PEP 503** — package name normalization. Relevant for slopsquatting defense in `pip install` steps.
- **PEP 668** — externally-managed environments (Homebrew Python on macOS enforces this; use venv on Mac).
- **Google Python Style Guide** — https://google.github.io/styleguide/pyguide.html
- **The Twelve-Factor App** — https://12factor.net/ (config, logs, backing services)

### The write-code workflow (procedural)

1. Read the failing test or the operator's stated requirement.
2. Cold-read the file(s) you're about to change.
3. Write the minimal fix. No refactor, no scaffolding.
4. Run `ruff check .`, then `mypy .`, then `pytest`.
5. If touching security-sensitive code, run `bandit -r src/`.
6. If touching parity-critical code (live/sim, sync/async), apply to BOTH or NEITHER.
7. Before any banner bump: full pytest must be green.

---

## 2. GUI Design Harness

Acervator is a **PySide6 desktop application**. GUI code lives under `src/gui/`.

### Universal design standards (referenced; enforcement is manual)

- **WCAG 2.2** (W3C) — accessibility. Body text contrast ≥ 4.5:1, large text ≥ 3:1; keyboard navigation; focus indicators; every actionable widget needs an accessible name via Qt's `setAccessibleName()` / `setAccessibleDescription()`. https://www.w3.org/TR/WCAG22/
- **Nielsen 10 Usability Heuristics** (Nielsen Norman Group) — https://www.nngroup.com/articles/ten-usability-heuristics/
- **Apple Human Interface Guidelines** (macOS) — https://developer.apple.com/design/human-interface-guidelines/macos
- **Microsoft Fluent Design** (Windows) — https://learn.microsoft.com/en-us/windows/apps/design/
- **Fitts's Law** — critical targets should be big and near.
- **Hick's Law** — prefer progressive disclosure over dense panels.

### Qt / PySide6 conventions (from official Qt docs)

- **Qt for Python docs** — https://doc.qt.io/qtforpython-6/
- **Qt Style Sheets** — https://doc.qt.io/qt-6/stylesheet.html
- Layouts: `QVBoxLayout` / `QHBoxLayout` / `QGridLayout`. Absolute positioning is a smell.
- Signals/slots: use `@Slot` decorators; connect in a `_wire()` method so wiring is inspectable in one place.
- Widget lifetime: parent every child widget to prevent leaks.
- Thread discipline: Qt widgets are main-thread only. Use `QMetaObject.invokeMethod` or `Qt.QueuedConnection` for cross-thread updates.

### GUI testing (deterministic, third-party)

| Tool | Install | Purpose | Docs |
|---|---|---|---|
| **pytest-qt** | `pip install pytest-qt` | pytest plugin for PySide6; `qtbot` fixture drives widget interaction; headless via `QT_QPA_PLATFORM=offscreen` | https://pytest-qt.readthedocs.io/ |
| **Qt Test / QtTest module** | ships with PySide6 | Qt's official test module | https://doc.qt.io/qtforpython-6/PySide6/QtTest/index.html |

### Accessibility testing — HONEST STATE OF THE ART

**No mature automated WCAG-compliance tester for Qt desktop apps exists** as of 2026. Automated a11y tooling (axe-core, pa11y, Playwright) is web-focused. For Qt:
1. Set `accessibleName` and `accessibleDescription` on every interactive widget.
2. Use `pytest-qt` to assert those properties exist (`widget.accessibleName() != ""`).
3. Manual verification with macOS VoiceOver (`Cmd+F5`) or Windows Narrator (`Win+Ctrl+Enter`).
4. Contrast is verifiable with color-picker tools (e.g., macOS Digital Color Meter) against WCAG 2.2 thresholds.

Do not claim automated a11y compliance without visual + assistive-tech verification.

### Visual regression

- **Manual PNG capture**: `QT_QPA_PLATFORM=offscreen python -c "…widget.grab().save('out.png')"` then diff.
- **pytest-qt** can capture widget renders in test fixtures.
- No dominant visual-regression tool for Qt (Squish is commercial and expensive).

### The GUI workflow (procedural)

1. Before edit: cold-read the whole widget/tab file. GUI code is stateful.
2. Write the minimum change; do not restructure siblings while fixing one widget.
3. Headless render the change with `QT_QPA_PLATFORM=offscreen`, save PNG.
4. Show the operator the PNG. Wait for visual confirm before shipping.
5. Add a pin test for the layout constraint (see existing `tests/test_bot_wizard_sizing.py` for the pattern).

---

## 3. Documentation Writing Harness

### Framework (referenced)

**Diataxis** — https://diataxis.fr/ — every doc is one of four modes; mixing them is the most common failure:

| Mode | Purpose | Voice |
|---|---|---|
| **Tutorial** | Learning by doing | "Let's build X" |
| **How-to** | Task-focused recipe | "To do X, run Y" |
| **Reference** | Information for lookup | terse, exhaustive |
| **Explanation** | Understanding, "why" | discursive |

### Style guides (external, authoritative)

- **Google Developer Documentation Style Guide** — https://developers.google.com/style
- **Microsoft Writing Style Guide** — https://learn.microsoft.com/en-us/style-guide/welcome/
- **The Chicago Manual of Style** — general prose (paid)

### Prose linting (deterministic, third-party)

| Tool | Install | Purpose | Docs |
|---|---|---|---|
| **Vale** | `brew install vale` (macOS) or `winget install vale` (Windows) | dominant prose linter; ships style packages for Google, Microsoft, alex, write-good | https://vale.sh/ |
| **proselint** | `pip install proselint` | Python-native prose linter (rule set based on style-guide research) | https://github.com/amperser/proselint |
| **alex** | `npm i -g alex` | inclusive-language linter (bundled as a Vale style pack too) | https://alexjs.com/ |

Vale is the standard used by GitLab, Microsoft, Mozilla, and the Linux Foundation as of 2026.

**Setup after install**:
```
# in repo root
vale sync                       # download style packages listed in .vale.ini
vale docs/                      # lint the docs directory
```

Minimal `.vale.ini`:
```ini
StylesPath = .vale/styles
MinAlertLevel = suggestion
Packages = Google, Microsoft, alex

[*.md]
BasedOnStyles = Google, Microsoft, alex
```

### Doc site generators (choose one)

| Tool | Install | Purpose | Docs |
|---|---|---|---|
| **MkDocs** + Material theme | `pip install mkdocs mkdocs-material` | Markdown-first, easy | https://squidfunk.github.io/mkdocs-material/ |
| **Sphinx** | `pip install sphinx` | RST/Markdown, best for API docs (autodoc from docstrings) | https://www.sphinx-doc.org/ |
| **Read the Docs** | hosting for either | free hosting for open-source docs | https://readthedocs.org/ |

### The writing workflow (procedural)

1. Identify the Diataxis mode (Tutorial / How-to / Reference / Explanation). Don't mix.
2. Draft — full sentences, second person for how-tos, present tense.
3. Cite anchors that resolve — file paths, line numbers, external URLs.
4. Add a falsification clause where making a claim ("This is wrong if X").
5. Save to `docs/audits/YYYY-MM-DD_topic/`. Include raw evidence beside synthesis.
6. Run `vale docs/` if Vale is installed; act on findings.

---

# Mac Mini Install Manifest

Run this once on the Mac Mini before starting harness work. All packages are from established maintainers.

```bash
# System prerequisite (one-time, if not already done)
xcode-select --install

# Python 3 from python.org (NOT the system stub); 3.12 or 3.13 recommended

# --- Coding quality (deterministic) ---
# Issue #94 - these two lines used to hand-copy the checker names. They
# are the `dev` extra in pyproject.toml now, which is the one source.
pip3 install --upgrade pip
pip3 install -e ".[dev]"
#
# That extra holds exactly the tools the archetypes spawn: ruff, mypy,
# bandit, vulture and pyright from
# dev_harness/harness/coding_archetype.py, proselint from
# docs_archetype.py, pytest with pytest-asyncio and pytest-xdist, and
# the types-reportlab stubs. It does NOT hold pip-audit, pytest-cov,
# hypothesis or mutmut: no file in the repository runs any of them, and
# pyproject.toml records that mutmut 3.5.0 refuses this platform.

# --- Semgrep + pre-commit ---
brew install semgrep
pip3 install pre-commit

# --- Anti-hallucination (LLM eval) ---
pip3 install ragas deepeval guardrails-ai
# Optional additional:
# pip3 install nemoguardrails inspect-ai trulens-eval arize-phoenix
# npm i -g promptfoo

# --- GUI testing ---
pip3 install pytest-qt

# --- Docs quality ---
brew install vale
pip3 install proselint mkdocs mkdocs-material
# Optional:
# npm i -g alex

# --- Post-install ---
vale sync                       # downloads Google + Microsoft + alex style packs
python3 -c "import ruff, mypy, bandit, vulture, pytest, hypothesis, ragas; print('ok')"

# --- Then build the app ---
chmod +x build_mac.sh
./build_mac.sh --dmg
```

If `brew` is not installed: https://brew.sh/ (one-line install script).

---

# Tool Integration Report

Segmented by reality state. Verify before citing anything.

## ✓ Installed on operator's Windows box (verified in this session)

| Tool | Version |
|---|---|
| mypy | (importable) |
| bandit | 1.9.4 |
| vulture | 2.16 |
| mutmut | 3.5.0 |
| pytest | 9.0.3 |
| pytest-cov | 7.1.0 |
| hypothesis | 6.152.4 |
| pip-audit | 2.10.0 |
| pydantic | 2.13.4 |
| pyyaml | 6.0.3 |
| typer | 0.26.7 |
| rich | (importable) |
| jsonschema | 4.26.0 |

## ✓ Additionally verified on Windows 2026-08-04

These were listed as missing in the 2026-06-18 pass; re-probed and present:

| Tool | Version |
|---|---|
| ruff | 0.16.0 (`python -m ruff`) |
| pyright | 1.1.411 (CLI on PATH) |
| semgrep | importable |

All three are wired into `dev_harness/harness/coding_archetype.py` and run on every
edit via the archetype gate.

## ✕ NOT installed on Windows (would be part of the "correct" stack)

Missing from the Windows box but recommended by the standards references above:
- **Safety** — not installed
- **pytest-qt** — not importable (GUI tests run headless without it)
- **RAGAS / DeepEval / Guardrails AI / NeMo Guardrails / Promptfoo / Inspect AI / TruLens / Phoenix** — none installed
- **anthropic SDK** — not installed
- **Vale / proselint / alex** — none installed
- **pre-commit** — not installed
- **pytest-qt** — check `pip show pytest-qt` on Mac before assuming

## ✕ NOT INSTALLED on Mac Mini (assume all)

Nothing is guaranteed installed. Use the install manifest above.

## ✕ DEPRECATED — do not treat as authoritative

Per operator directive 2026-06-18: no element of SADP is valid or working. This includes but is not limited to:
- All contents under `packaging/sadp/` (SPEC-CORE.md, RULE_REGISTRY.json, EPISODIC_MEMORY.json, EDIT_LOG.jsonl, RAIntSimBat/, _tools/)
- All contents under `sadp2/` (Phase 1A + envelope filters — the harness this session's rebuild attempt, known-defective)
- All contents under `Scaffolds and Hallucinations/`
- Rule numbers `R1-R92` as governance authority (may appear as historical vocabulary in HOP addenda)
- The following auto-memory files in `~/.claude/projects/…/memory/`: `project_sadp_adoption.md`, `reference_sadp_paths.md`, `feedback_token_timer_grounding.md` (references SADP grounding layers)
- Prior tools that are shims into SADP: `tools/qa_status.py`, `tools/check_release_readiness.py`, `tools/doc_audit.py`, `tools/sadp_enforce.py` (missing), `tools/hallucination_screen.py` (missing)

If a rule number or SADP path appears in a HOP addendum, treat it as historical context, not a live gate. The harness is the external-tools table above.

## Standards referenced (external, authoritative, not tool-installed)

- **W3C**: WCAG 2.2
- **NN/g**: 10 Usability Heuristics
- **PSF/PEPs**: PEP 8, PEP 484, PEP 503, PEP 668
- **Google**: Python Style Guide, Developer Documentation Style Guide
- **Microsoft**: Writing Style Guide, Fluent Design
- **Apple**: Human Interface Guidelines (macOS)
- **Qt**: Qt for Python docs, Qt Style Sheets
- **Diataxis**: documentation framework
- **12-Factor**: config/logs/backing services
- **arXiv 2509.22202**: LibHalluBench methodology (reference paper, no package)

---

# Meta

This SKILL replaces mental replay of prior sessions. Combine with:
- Auto-loaded `MEMORY.md` (operator preferences and feedback history)
- `ACERVATOR_HOP7.md` — read in full; it indexes the transcript, the memory directory and the audits
- Direct file reads only when the task requires it

If you find yourself contradicting anything here from what the operator just said, believe the operator. Update this file if they've made a new durable decision.

If any tool listed above is claimed to work but doesn't, treat the SKILL as stale and tell the operator immediately — do not silently work around it.
