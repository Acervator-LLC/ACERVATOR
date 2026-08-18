# Token Timers — evidence, design, and skill recommendations

## 1. Verdict up front

**No. Do not build a Token Timer. Build a blocking hook, and fix the timeout first.**

The strongest evidence is local and measured, not published. This repo already ran the experiment, twice, on two rules.

- `.claude/hooks/verify_release_gate.py:142` returns `{"decision": "deny"}` and blocks a banner write. The rule it guards stopped being violated.
- `.claude/hooks/archetype_gate.py:14-16` states its own contract: *"the archetype's job is to inform, not to block writes."* It injects text. The rule it carries was restated ten times with zero compliance.

A Token Timer re-asserts rule **text**. That is the instrument with the 0/10 record, on a schedule. The published work agrees on both halves. Anthropic's own skills documentation prescribes the swap for this exact symptom: *"If a skill seems to stop influencing behavior after the first response, the content is usually still present and the model is choosing other tools or approaches... use hooks to enforce behavior deterministically."* ([skills](https://code.claude.com/docs/en/skills))

Second reason the idea fails as specified: a skill cannot re-assert. Claude Code deduplicates. *"When Claude re-invokes a skill whose rendered content is identical to the copy already in context, Claude Code adds a short note that the skill is already loaded rather than a second copy of the content."* ([skills](https://code.claude.com/docs/en/skills)) A timer that re-invokes `harness-law` produces a one-line note.

The instruction-following evidence **is thinner than the retrieval evidence**, and I say so in §2 rather than dress up retrieval benchmarks as obedience data. The verdict does not rest on it. It rests on the two hooks in this repo.

---

## 2. Does adherence actually decay?

### 2.1 Retrieval decay — well measured, and the wrong evidence base

These papers ask whether a model can **find** a fact. None asks whether it keeps **obeying** a rule. Citing them to justify a rule-reminder is a category error.

| Source | Measured | Numbers I read on the page |
|---|---|---|
| NoLiMa ([arxiv.org/abs/2502.05167](https://arxiv.org/abs/2502.05167)) | Needle retrieval with minimal lexical overlap | GPT-4o 99.3% short baseline → 69.7% at 32K. 11 of 13 models fall below 50% of their short baselines at 32K. |
| Chroma Context Rot ([trychroma.com/research/context-rot](https://www.trychroma.com/research/context-rot)) | Mostly retrieval; one replication task | 18 models. Claude Opus 4 refused 2.89%, GPT-4.1 2.55%, Qwen3-8B 4.21% and emitted off-topic text past ~5,000 words. |

The Chroma replication task ("reproduce the input text exactly") is the one item in that set that isolates holding a constraint rather than finding a fact. Accuracy fell with length for all tested models. It is one task, not a benchmark of obedience.

### 2.2 Instruction-following decay — real, newer, thinner

| Source | Numbers I read on the page |
|---|---|
| Multi-IF ([arxiv.org/html/2410.15553v1](https://arxiv.org/html/2410.15553v1)) | Accuracy over 3 turns: o1-preview 0.877 / 0.783 / 0.707; GPT-4o 0.843 / 0.724 / 0.631; Claude-3.5 Sonnet 0.817 / 0.705 / 0.634. Instruction Forgetting Ratio = *"The percentage of previously followed instructions that were not followed in the subsequent turn."* |
| SEQUOR ([arxiv.org/html/2605.06353v1](https://arxiv.org/html/2605.06353v1)) | 1,400 conversations, 50 turns each. Sequential constraint addition is the worst regime: average decrease **63%**; multiple simultaneous constraints **38%**. |
| Laban et al. ([arxiv.org/abs/2505.06120](https://arxiv.org/abs/2505.06120)) | 200,000+ simulated conversations. Average **39%** drop single-turn → multi-turn, decomposed as *"a minor loss in aptitude and a significant increase in unreliability."* *"When LLMs take a wrong turn in a conversation, they get lost and do not recover."* |
| IFScale ([arxiv.org/html/2507.11538v1](https://arxiv.org/html/2507.11538v1)) | 10→500 instructions, 20 models. At 500: gemini-2.5-pro 68.9%, o3 62.8%, claude-3.7-sonnet 52.7%, gpt-4.1 48.9%. Above 300 instructions, primacy ratios converge to 1.0–1.5 — failure becomes uniform. |

The operator's session is the SEQUOR sequential-addition regime: one rule, then more rules layered over days. That is the worst measured regime.

### 2.3 Three results that decide the design

**A. The decay tracks actions taken, not token index.** A factorial study on `CLAUDE.md` itself — 1,650 Claude Code CLI sessions, 16,050 function-level observations, Sonnet 4.6 primary — manipulated instruction position, file size, file architecture, and adjacent-file contradictions. *"None of the four structural variables or three two-way interactions produces a detectable contrast after multiple-testing correction."* What did predict compliance: **each additional function generated carries ~5.6% lower odds of compliance (OR = 0.944).** ([arxiv.org/abs/2605.10039](https://arxiv.org/abs/2605.10039))

A timer keyed to token count targets the variable that measured null. A counter keyed to writes targets the one that measured real.

**B. The rule is still present when it is broken.** DriftBench measured the knows-but-violates rate: **8% to 99%** across seven models from five providers, 2,146 runs. *"A restatement probe reveals a dissociation between declarative recall and behavioral adherence, as models accurately restate constraints they simultaneously violate."* The same paper tested the closest published analogue to a Token Timer: *"Structured checkpointing partially reduces KBV rates but does not close the dissociation."* ([arxiv.org/abs/2604.28031](https://arxiv.org/abs/2604.28031))

Re-supplying rule text repairs a channel that was never broken.

**C. Structure beats text by a wide margin.** The Compliance Gap ran 2,031 sessions on six frontier models. *"Under default framing, all six exhibit instruction compliance rates of 0% — Claude Sonnet 4 verbally agrees ten out of ten times then bypasses in all ten."* The intervention that worked was environmental: *"removing delegation tools raises compliance to 75% (Cohen's d = 2.47), confirming environmental affordance rather than weight-encoded failure."* And text-only verification failed: *"Nine blinded human raters achieve Fleiss' kappa = 0.130 and correctly identify zero of fifteen compliant sessions."* ([arxiv.org/abs/2605.01771](https://arxiv.org/abs/2605.01771))

**RESTATED — an earlier draft of this research was wrong here.** The 97% audit-trail figure is **not** a measured intervention. The abstract frames it as a task type the models already do well: *"The gap is selective: 97% compliance where rationale is rewarded (audit trails), 0-4% where it is not."* Do not build a claim-ledger extension on a "0% → 97%" lift. That lift was never measured.

**D. Compaction, not attention drift, is what erases the rule.** ConstraintRot: 1,323 episodes, seven model families. *"Violation rises from 0% with the policy in full context to 30% after compaction, reaching 59% for some models; when the constraint survives the summary, violation remains 0%, but when it is dropped, violation reaches 38%."* Their fix, Constraint Pinning, *"quarantines governance constraints from lossy compaction"* and restores violation to 0%. ([arxiv.org/abs/2606.22528](https://arxiv.org/abs/2606.22528))

The failure is binary and event-driven. It is not a smooth function of elapsed tokens.

**HYPOTHESIS, unverified:** no fetched study tested silent periodic re-injection against a control at this session's scale. Multi-IF runs 3 turns. This session ran 4,820. The direction is supported. The magnitude at 5M tokens is extrapolation.

---

## 3. What can enforce without the model's cooperation

All facts below come from [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks) unless marked otherwise. I fetched that page four times this session with different questions.

### 3.1 Silent context injection is real, and it is the exact primitive

The field is `additionalContext`, inside `hookSpecificOutput`. Documented behaviour:

> Claude Code wraps the string in a system reminder and inserts it into the conversation at the point where the hook fired. Claude reads the reminder on the next model request, but it doesn't appear as a chat message in the interface.

Supported events and where the text lands:

| Event | Injection point |
|---|---|
| `SessionStart`, `Setup`, `SubagentStart` | Start of the conversation, before the first prompt |
| `UserPromptSubmit`, `UserPromptExpansion` | Alongside the submitted prompt |
| `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch` | Next to the tool result |
| `Stop`, `SubagentStop` | End of the turn; the conversation continues so Claude can act on the feedback |

Cap: *"Hook output strings, including `additionalContext`, `systemMessage`, and plain stdout, are capped at 10,000 characters. Output that exceeds this limit is saved to a file and replaced with a preview and file path."*

### 3.2 The phrasing trap that would break the silence rule

> Write the text as factual statements rather than imperative system instructions... Text framed as out-of-band system commands can trigger Claude's prompt-injection defenses, which causes Claude to surface the text to you instead of treating it as context.

A re-assertion reading "YOU MUST run the Coding Archetype" is the out-of-band imperative form. The failure mode is the model printing the injected text to the operator. That is exactly the class of output the 2026-05-31 directive forbids. **Declarative only.**

### 3.3 Events that cannot inject

`WorktreeRemove`, `Notification`, `SessionEnd`, **`PostCompact`**, `InstructionsLoaded`, `StopFailure`, `CwdChanged`, `DirectoryAdded`, `FileChanged`.

`PostCompact` cannot inject. Post-compaction repair must ride `SessionStart` with matcher `compact`, or the next `UserPromptSubmit`.

### 3.4 Blocking

`PreToolUse` returns `hookSpecificOutput.permissionDecision`:

| Value | Behavior (verbatim from the docs table) |
|---|---|
| `"allow"` | Permits the tool call to proceed |
| `"deny"` | Blocks the tool call |
| `"ask"` | Escalates to the user for a permission prompt |
| `"defer"` | Defers to the normal permission flow |

**RESTATED — an earlier draft was wrong.** `permissionDecisionReason` is documented as an **Optional** field that provides context for the decision. It is not required for `deny` or `ask`.

Exit code 2: on `PreToolUse` it blocks the tool call, the same effect as `"deny"`. On `PostToolUse` it does **not** block — the tool already ran — and instead shows stderr to Claude as an error message.

### 3.5 Timeouts — the 30 s defect is self-inflicted

> Defaults: 600 for `command`, `http`, and `mcp_tool`; 30 for `prompt`; 60 for `agent`. `UserPromptSubmit` lowers the `command`, `http`, and `mcp_tool` default to 30, and `MessageDisplay` lowers it to 10.

`PostToolUse` keeps the 600-second default. No maximum is documented.

**Measured in this repo, this session:**

- `.claude/hooks/archetype_gate.py:61` — `TIMEOUT_S = 30`, a hardcoded Python constant.
- `.claude/hooks/archetype_gate.py:45` — the falsification comment claims *"(c) An archetype run of >30s freezes Claude Code (timeout bug)."* The documentation does not support that claim.
- `.claude/settings.json` registers `archetype_gate.py` under `PostToolUse` matcher `Write|Edit` with **no `timeout` field**.
- I ran `python -m tools.harness.coding_archetype src/trading/scrumming_bot.py` (12,333 lines): **44 seconds wall, exit 0.**

The gap is 14 seconds against a 600-second platform allowance.

Two other useful fields, both verbatim from the same page:

- `asyncRewake`: *"If `true`, runs in the background and wakes Claude on exit code 2. Implies `async`. The hook's stderr, or stdout if stderr is empty, is shown to Claude as a system reminder so it can react to a long-running background failure."*
- `if`: *"Permission rule syntax to filter when this hook runs, such as `"Bash(git *)"` or `"Edit(*.ts)"`."* Only evaluated on tool events.
- *"All matching hooks run in parallel. If you define the same handler in more than one settings file, it runs once."* The four archetypes do not queue behind each other.

### 3.6 Compaction is observable, so no token math is ever needed

`SessionStart` matchers: `startup`, `resume`, `clear`, `compact`, `fork`. `PreCompact` and `PostCompact` matchers: `manual`, `auto`.

A hook with `matcher: "compact"` fires precisely when compaction just discarded context. It reacts to an event. It never computes a token number.

### 3.7 Skills — why the skill route is closed

- Deduplication: identical rendered content produces a one-line "already loaded" note. *"Before v2.1.202, every re-invocation appended another full copy."*
- Compaction budget: *"Claude Code re-attaches the most recent invocation of each skill after the summary, keeping the first 5,000 tokens of each. Re-attached skills share a combined budget of 25,000 tokens. Claude Code fills this budget starting from the most recently invoked skill, so older skills can be dropped entirely after compaction if you have invoked many in one session."* `harness-law`, invoked early and rarely, is the first thing dropped.
- The escape hatch: the `` !`<command>` `` syntax *"runs shell commands before the skill content is sent to Claude. The command output replaces the placeholder."* Varying output defeats deduplication.
- The phrase "deterministic control" comes from [hooks-guide](https://code.claude.com/docs/en/hooks-guide), not the hooks reference: *"Claude Code runs them at specific points in its lifecycle, which gives you deterministic control: certain actions always happen rather than relying on the LLM to choose to run them."*

---

## 4. The design, if it earns its place

Rename it. "Token Timer" encodes both the wrong mechanism and the forbidden concept. Call it **Authorship Gate**.

Build it in this order. Each step is independently useful. Step 0 must land first.

### Step 0 — Fix the timeout (prerequisite, not optional)

Two coupled edits.

1. Raise `TIMEOUT_S` in `.claude/hooks/archetype_gate.py:61` from 30 to 180. Correct the falsification comment at line 45 — the documented `PostToolUse` default is 600 s.
2. Add `"timeout": 300` to the `PostToolUse` handler in `.claude/settings.json`.

Changing one without the other leaves the defect. Under the OR = 0.944 result, compliance decays per action; the file where only one archetype runs is the most trade-critical file in the repo. The decay and the coverage hole coincide on the worst file. Re-time `scrumming_bot.py` after the change.

**The Coding Archetype writes this code.** It is code.

### Step 1 — Make the non-compliant path unavailable

Add a `PreToolUse` handler on `Write|Edit`, narrowed with `"if": "Edit(*.py)"`. It returns `permissionDecision: "deny"` when no archetype receipt exists for that path in the current turn. Mirror the sidecar pattern already working in `verify_release_gate.py` (`BANNER_PATHS` + `MAX_AGE_SECONDS = 3600`).

This is the only enforcement class with a non-zero compliance record in this repo, and it matches the only intervention that moved the Compliance Gap number (0% → 75%, d = 2.47).

**HYPOTHESIS:** `verify_release_gate.py:142` emits the legacy `{"decision": "deny"}` shape. The current reference documents `hookSpecificOutput.permissionDecision`. I did not verify whether the legacy shape is still honoured. Test the new hook against a real blocked write before trusting it.

Do **not** extend `archetype_gate.py`. Its contract at lines 14-16 says it never blocks. Honour it.

### Step 2 — Re-assert on compaction, silently

`SessionStart` with matchers `compact` and `resume`. Return `additionalContext` under 400 characters. Declarative phrasing only:

> Code authorship in this repo runs through the Coding Archetype. The last archetype verdict for `src/trading/scrumming_bot.py` was `passed=true`, recorded 14 minutes ago. Files with no current verdict are blocked at Write by `.claude/hooks/authorship_gate.py`.

That is a project fact, not a command. It carries state, so it is never identical twice. It names no token count.

Constraint Pinning worked at a small pinned buffer, not a whole rule index. Pin the two or three rules that were actually violated. IFScale shows adherence falling as instruction count rises — more rule text can hurt.

### Step 3 — Fix the two live defects in `prompt_router.py`

Both measured this session.

1. **Line 170 injects a command that does not exist.** `_build_cascade_reminder()` emits `python tools/check_release_readiness.py`. That path is absent from disk; `tools/harness/check_release_readiness.py` is the real module. `MEMORY.md` warns about this exact path. I ran the coding archetype on the hook: it reports `H001` at line 170, *"referenced path 'tools/check_release_readiness.py' does not exist on disk"* — and still returns `passed=True`, because H001 is severity medium and `passed` means no critical or high.
2. **`harness-law` is wired to nothing.** `_DOMAIN_RULES` names `archetype-peer-review` for coding, GUI and docs alike (lines 89, 104, 119). `harness-law` appears in no hook and in no settings file — only in its own `SKILL.md`. The skill encoding the ten-times-violated authorship rule is never surfaced by the one hook that fires every turn.

Also note `prompt_router.py:217-218`: *"quiet-when-neutral; injecting empty context is noise."* Prompts like "proceed", "ship it" and "fix that" inject nothing. Those are the turns where authorship gets dropped.

### The hard constraint, and how the design meets it

| Requirement | How the design satisfies it |
|---|---|
| No fill percentage | Nothing in the design computes one. Triggers are `compact`, `resume`, and a tool call. |
| No token count | No component reads, stores, or prints a token number. A write-count is not context telemetry. |
| No handoff proposal | The hooks emit rule state and a deny reason. Never a budget. |
| Nothing surfaced to the operator | `additionalContext` *"doesn't appear as a chat message in the interface."* Never use `systemMessage`. |

**What makes this fail.** Four specific failures, all avoidable:

1. Imperative phrasing in `additionalContext` trips the prompt-injection defense, and the model prints the injected rule to the operator. A silent design becomes a loud one.
2. Anyone adds a token count to the injected string "for context". Disqualified on arrival.
3. `permissionDecisionReason` text leaks a budget or a session-length remark into the visible deny message. Keep it to the missing receipt.
4. Someone routes the re-assertion through `systemMessage` or plain stdout instead of `additionalContext`. Both are operator-visible.

---

## 5. Cost and failure modes

**Cache.** The documented cache risk belongs to context *editing*, not to appending: *"Tool result clearing: Invalidates cached prompt prefixes when content is cleared."* ([context-editing](https://platform.claude.com/docs/en/build-with-claude/context-editing); defaults there: strategy `clear_tool_uses_20250919`, trigger 100,000 input tokens, keep 3 tool uses, `clear_at_least` unset, `clear_tool_inputs: false`.) **HYPOTHESIS:** appending `additionalContext` after the cached prefix should not invalidate it. No fetched page states this. Do not treat it as verified.

**Token spend.** Injected text is saved in the session transcript, and on `--continue`/`--resume` Claude Code replays the saved text rather than re-running the hook. Injection on every turn therefore accumulates permanently and goes stale. Fire on **state change** — a new compaction, a new verdict — not on every turn.

**Distraction.** IFScale is the honest bound: adherence falls as instruction count rises, and above 300 instructions primacy ratios converge to 1.0–1.5 as failure becomes uniform. Adding rule text to a crowded context can reduce adherence. Keep the pinned block to two or three rules.

**Over-indexing on the reminder.** Laban et al. found the dominant multi-turn failure is unreliability, and *"when LLMs take a wrong turn in a conversation, they get lost and do not recover."* A model that re-reads a rule at every tool call can start narrating compliance instead of doing work. The Compliance Gap already measured that shape: 10/10 verbal agreement, 0/10 actual compliance. A reminder that produces narration is worse than no reminder, because it manufactures the false-compliance signal directly.

**Decay resumes after each re-assertion.** SEQUOR: *"Models tend to recover their initial performance when existing constraints are replaced with new ones,"* but *"after each replacement, subsequent turns often exhibit sharper performance declines than those following the first turn."* Re-assertion buys a window, not a fix. Only Step 1 removes the option.

**Latency.** 44 s on the largest file, and matching hooks run in parallel. A `PreToolUse` deny that re-runs the archetype inline would add that to every Python write. Prefer a receipt file written by the existing `PostToolUse` run, and let `PreToolUse` read the receipt. `asyncRewake` is the fallback if a full inline run is ever needed.

---

## 6. Skill recommendations

Ranked. Honest about what is already covered.

**1. `update-config` — adopt now.** Closes every configuration change in §4: the `PostToolUse` `timeout` field, the new `PreToolUse` handler, and a permissions `deny` on the credentials path. The archetypes lint Python; nothing in the harness validates `settings.json`. This skill's own description states the governing principle — automated behaviours need hooks, because the harness executes hooks and memory is only text.

**2. `anthropic-skills:consolidate-memory` — adopt now.** `MEMORY.md` auto-loads into every session and states "v3.15.39". `src/__init__.py:15` reads `3.25.4` — ten minor versions ahead. A wrong fact in an auto-loading index is injected into every turn of every future session. That is the Token Timer's own failure mode running in reverse. No archetype reads the memory directory.

**3. `security-review` — run on this branch.** `defaultMode` is `bypassPermissions`, and the branch modifies `src/exchange/ccxt_connector.py`, the credential consumer. `tools/harness/check_release_readiness.py` runs three checks only — pytest, archetype self-check, claim ledger. It runs no secrets or dependency scan. Not covered.

**4. `anthropic-skills:skill-creator` — adopt for one job only.** It carries evals and variance analysis. Use it to measure whether the Step 2 re-assertion changes anything, rather than assuming. Given §2's finding that restatement treats a channel that was not broken, this is the honest way to find out. Do not use it to write more skills.

**5. `simplify` — low priority, with a caveat.** Genuine complement: every archetype tool hunts defects, and the two quality signals that exist (`SL002` over-long function, `SL003` file too big) are severity low, so `scrumming_bot.py` at 12,333 lines returns `passed=True`. But `simplify` applies fixes, and `harness-law` rule 1 makes the model a referee, not an author. Route its output as a finding list for the Coding Archetype to author.

**Already covered — do not adopt.**

- `fewer-permission-prompts` — pointless here. `defaultMode` is `bypassPermissions`; there are no prompts to reduce. The gap runs the other way.
- `review` — PR-scoped. The archetypes plus `security-review` already cover the working diff.
- `loop` and `schedule` — these are the Token Timer in its weakest form. A recurring prompt is operator-visible text on a clock. It fails both the evidence test (§2) and the silence constraint.

**Not closed by any available skill.** Four gaps have no skill: the `_SKIP_PATH_FRAGMENTS` self-exemption of `.claude/hooks/` (`archetype_gate.py:70-71`), the severity threshold that lets `H001` pass, tests that assert on substrings rather than on facts, and the missing dependency scan in the release gate. These need hand-built work, authored by the Coding Archetype.

---

## 7. What this does not settle

1. **No study tested this design.** No fetched source ran silent event-triggered re-injection against a control at 4,820 turns. Multi-IF runs three turns. The direction is supported; the magnitude at this scale is extrapolation.
2. **Whether Step 2 does anything at all.** DriftBench says structured checkpointing *"partially reduces KBV rates but does not close the dissociation."* Step 1 is the load-bearing change. Step 2 may prove to be cost with no benefit. Measure it.
3. **The legacy deny shape.** `verify_release_gate.py:142` uses `{"decision": "deny"}`; the reference documents `hookSpecificOutput.permissionDecision`. Whether the old shape still blocks is unverified. Test before trusting.
4. **Cache behaviour of appended `additionalContext`.** Marked HYPOTHESIS in §5. No fetched page states it.
5. **Peer-review status.** Four load-bearing sources — 2604.28031, 2605.01771, 2605.06353, 2605.10039, 2606.22528 — are recent arXiv preprints. I read them through WebFetch's summarizer, not verbatim in full. Abstract-level figures are quoted; sub-table figures are not cited here.
6. **One contested number.** My SEQUOR fetch returned "more than 11%" for the single-constraint regime and "more than 9%" for the mixed regime; a prior read of the same page returned 26% and 27%. The 63% sequential-addition figure and the 38% multiple-constraint figure were stable across both reads, so only those appear above. A single WebFetch pass is not evidence of absence.
7. **What the receipt should contain.** §4 Step 1 assumes a per-file archetype receipt with a freshness window. The exact schema, the window length, and the behaviour on a multi-file edit are undesigned.
8. **Whether `H001` should be severity high.** Proposed, not decided. Per the standing rule, only the archetypes edit the archetypes. This is a proposal to the operator, not a change.