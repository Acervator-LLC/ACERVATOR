# Subsystem Capability Matrix — what works, what is half-built, what breaks a rule

**Reference.** This document records a measurement. It does not propose a repair.

Audit date: 2026-08-25. Read-only. No production file was changed. No fix is proposed.

- Repository under audit: clone of `acervator_session27_CLOSE_hop5_v3_25_8` at HEAD `cb58d9d`, branch `current`.
- Clone path: a throwaway clone (`subsys`) outside the repository.
- The only file this audit added is this one.

---

## WHY THIS DOCUMENT EXISTS

Operator, verbatim:

> "We should also start thinking of the Tabs in terms of the Subsystems they represent
> and each Subsystem has features / functions that are 1) working or not working,
> 2) partially or not built at all, and / or 3) non-compliant with canonized rules or
> previously stated design specs. If we do it this way, I will understand what exactly
> you are working on and whether or not we are deviating from the spec."

He also said, in these words, that "[t]here is just too much being lost in translation even
when simple technical English is being used. I need to be able to pair your code with a
given feature / function or design spec." The bracket marks one lowercased letter, so his
sentence reads inside mine. No other word is changed.

Three vocabularies exist today and nothing joins them. The tracker says `#46`. The code
says `fetch_chart_data`. A report says a paragraph of prose. The operator must translate
every time, and he is not a programmer.

**This document gives every feature a stable ID.** The ID is named for what the operator
SEES, never for a class, a file or a function, so it stays the same when the code moves.
From here, a work brief names the ID it touches, a report says "feature `X`: was A, now B,
spec says C", and an issue carries an ID.

---

## THE ANSWER IN NUMBERS

**Ten subsystems. 77 framing features. 299 functions beneath them.**

Read the framing column. It is the number that means something.

| Subsystem | Framing features | Working | Partial | Absent | Rule broken | Functions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trading | 9 | 8 | 1 | 0 | 2 | 50 |
| Market Inspector | 7 | 3 | 1 | 2 | 6 | 33 |
| Bot Swarm | 9 | 3 | 2 | 1 | 6 | 39 |
| Asset Charts | 6 | 3 | 2 | 0 | 2 | 27 |
| History | 6 | 5 | 0 | 0 | 1 | 21 |
| Simulator | 8 | 6 | 1 | 1 | 7 | 74 |
| Console | 5 | 5 | 0 | 0 | **0** | 23 |
| Paper Trader | 9 | 1 | 1 | 7 | 1 | 32 |
| Proof of Accumulation | 9 | 0 | 0 | 9 | 0 | 0 |
| System Status | 9 | 0 | 0 | 9 | 0 | 0 |
| **Total** | **77** | **34** | **8** | **29** | **25** | **299** |

"Working" counts framing features proved to do what they claim. "Partial" means some of it
works. "Absent" means the code is not there. "Rule broken" counts framing features that
break a rule you already stated; the rule is named on every such row.

### The two numbers that explain why work keeps getting lost in translation

Counted over the 317 rows that carry a spec column and a test column:

| Question | Answer |
| --- | ---: |
| How many features have **NO RECORDED SPEC**? | **38** |
| How many have **NO TEST**? | **151** |
| How many have **neither**? | **34** |

**One feature in two has no test.** Its breakage is silent. Nothing in the suite would go
red if it stopped working tomorrow.

**Thirty-four features have neither a spec nor a test.** Nobody wrote down what they should
do, and nothing checks that they still do it. A feature nobody specified is a feature nobody
can call non-compliant, which is why those 34 do not appear in the rule-broken column. They
are not compliant. They are unmeasurable.

Where those 34 sit is itself informative. Ten are in the Console, which is the subsystem
that breaks no rules at all: it does a great deal that nobody ever asked for in writing.
Five are in Paper Trader, and **every one of those five is scaffolding that should be
cleared** — the spec column and the keep-or-clear call agreeing exactly.

### The emitter network, measured across every subsystem

The project's own checker reports **78 pins in source and 78 registry rows, instrument
controls OK, exit 0**. An independent count of the same tree returns 78 and agrees with the
checker exactly; that agreement is the control. Here is where they sit.

| Subsystem | Emitters | Note |
| --- | ---: | --- |
| Simulator | **22** | 14 under one token, 8 under the fleet token, against a specified 40 |
| Trading | 11 | 6 for the tab, 5 for the exchange panels |
| History | 7 | the second-largest set of any tab |
| Asset Charts | 5 | |
| Console | 5 | |
| Bot Swarm | 2 | and no third for the Live layer |
| Paper Trader | 1 | the template every new Paper emitter must match |
| **Market Inspector** | **0** | issue #18 asks for them by name |
| Proof of Accumulation | 0 | |
| System Status | 0 | |
| Engine-level, not a tab | 25 | bot, extractor, ta, tick, ytd, gui, exchange, apitest, instance |

**Two findings sit in that table.** The Market Inspector has no emitters at all, so nothing
it does can be verified from outside itself. And the Simulator's 22 stand against a
specification of 40 — the Simulator section states both readings of that number, because
they are opposite findings and you should settle which 40 you meant.

### The seven findings worth acting on first

1. **The buy-confirmation prompt has never run.** `TRADING/bot-controls/buy-confirmation-prompt` — zero call sites in the repository.
2. **A Paper Swarm Start button says "LIVE" and trades nothing.** `PAPER/swarm-layer/start-button-trades`.
3. **The chart's MACD is numerically wrong** and is the issue #99 defect still alive after the engine was repaired. `ASSET-CHARTS/indicator-overlays/macd`.
4. **Backtest Mode does not exist below its label.** `SIM/backtest-mode/mode-changes-behaviour`.
5. **The Fire button has no test** — the live-money override. `TRADING/bot-controls/fire-button`.
6. **"Cost USD" is neither the venue's cost nor necessarily dollars.** `HISTORY/trade-list/cost-usd-column`.
7. **Both hand-wiring gestures are dead in the view the tab opens in.** `BOT-SWARM/wires-by-hand`.

---

## HOW TO READ THIS — two levels, and you only need the first

Each subsystem is stated at **two levels**. Read level one. Level two is for whoever does
the work.

**Level one — the FRAMING FEATURES.** A handful of rows, never more than about ten. This is
the subsystem. Each has its own ID, its own state and its own verdict. If a framing feature
is red, the subsystem has a problem you can name in one sentence.

**Level two — the FUNCTIONS beneath it.** Each framing feature breaks into the functions
that make it work, with IDs like `SIM/bot-list/target-column`. This is where the exact code
site, the test and the evidence live. A work brief is written from level two. You do not
need to read it.

An earlier draft of this document put all 300-odd functions at level one. That version was
unusable, and the operator said so: "Stating there are 73 already shows how off the rails
things have gotten." He is right. A subsystem described by 73 rows cannot be reasoned
about. A subsystem described by eight can. The count that matters is the framing count.

## HOW TO READ A ROW

| Column | What it means |
| --- | --- |
| **ID** | The stable name. Format `SUBSYSTEM/feature-slug`. Use this in every brief, report and issue. |
| **Feature** | What you see or do, in your words. |
| **Built** | `BUILT` the code is there. `PARTIAL` some of it is there. `ABSENT` none of it is there. |
| **Works** | `WORKING` it does what it claims. `BROKEN` it does not. `UNVERIFIED` nobody has measured it. `UNVERIFIED` is an honest answer and is better than a guess. |
| **Rule** | `COMPLIANT` / `NON-COMPLIANT` / `UNKNOWN` against a rule you already stated. The rule is named in the Spec column. |
| **Code** | The exact place in the code that does it. Not the file — the site. |
| **Spec** | The rule or design statement it serves, and where that is written down. `NO RECORDED SPEC` means nobody ever wrote a rule for it. |
| **Tests** | The test that proves it works. `NO TEST` means its breakage is silent. |
| **Ev** | `[M]` measured by running it. `[T]` a test proves it. `[S]` read in the source only. |

A row with no evidence marker is not admissible. This matrix holds none.

**A note on the Code column, added on re-anchoring.** The Stage 2/3 conversion moved
`src/gui/main_window.py`'s content into `src/gui/main_tabs/` and `src/gui/widgets/` after
this matrix was written, and split `bot_visualizer.py`, `native_chart.py`,
`bot_live_settings.py` and `fleet_replay_panel.py` the same way. Every citation this left
pointing past the end of its named file is marked **stale citation, unverified** rather
than repointed at a guess. The Built/Works/Rule verdict in each such row was not
re-measured either — only the line citation is marked. Re-deriving each one needs the
same site-by-site search this pass gave the rules table, the tab set and the P1.7/#79/
System Status findings above, which were re-verified.

---

## THE RULES THIS MATRIX MEASURES AGAINST

Every rule below is one the operator already stated. Each is quoted from where it is
actually recorded in this repository. No rule here is invented.

| Key | The rule | Where it is recorded |
| --- | --- | --- |
| **R-VENUE** | "Simulator, Paper, and Live Scrumming bots are and must be the same with the exception of their data source. Live is the only one with bidirectional API access since it trades on the exchange." | `docs/engineering-notes/2026-08-25_the_venue_seam.md:10-14` (operator verbatim). Restated in code at `src/simulator/fleet/fleet_replay_controller.py:454`: "Live, Paper and Sim may differ only in where market data comes from." |
| **R-VENUE-2** | "If the bot is not acting like a live trading bot with a different data feed, I do not want to hear about it, because any variation is a violation of the design spec." | `docs/engineering-notes/2026-08-25_the_venue_seam.md:16-18` |
| **R-EXCHANGE** | Operator, 2026-08-22, verbatim: "ANYTHING that induces disagreement with exchange values is broken." Internal ledgers reconcile TO the venue and never override it. | `tests/test_drift_up_adopts_the_exchange.py:9` (operator verbatim). Also `tests/test_sim_bot_agrees_with_its_venue.py:9-11`, `src/core/instance_guard.py:5`. `export_scrumming_state` (`src/trading/scrumming/state_io.py:30`) still omits `_current_holdings` from the exported dict, enforcing the rule; the narrative comment explaining why was removed by a later comment sweep. **`docs/engineering-notes/2026-07-25_bot_details_status_tab/REPORT.md` no longer exists anywhere in the tree.** |
| **R-TRANCHE** | "MERGE, DESPAWN and CLEAR are the only three things that collapse or remove a tranche." Despawn REMOVES; it does not delist. | `src/gui/live_settings/fold_chrome.py:160` and `src/gui/live_settings/settings_tab.py:879` (operator-facing text). Reasoning at `src/gui/live_settings/fold_chrome.py:315` — "the operator's model has exactly three verbs - merge, despawn, clear". |
| **R-INDICATOR** | "Indicator formulae are PUBLISHED. Each indicator has its own discrete maths and is never blended with another's." | `src/trading/ta_engine.py:14-16`, `src/trading/indicators/__init__.py:3-5`, `src/trading/ta_invariants.py:16`. Enforced by `tests/test_one_indicator_per_module.py`. |
| **R-EMITTER** | Every emitter is tracked and declared. A key-name mismatch between producer and consumer is invisible to both sides; only a declared contract makes the gap visible. | `src/core/emit_contracts.py:1-39` (the three failure classes this validates). **The pin registry this rule used to point at is gone.** `docs/EMITTER_IDENTIFICATION.md` and `docs/ITEM_10_EMITTER_NETWORK.md` no longer exist anywhere in the tree — both were removed in the "remove the 'pin' system" commit (`e3054e4`) and its follow-up (`2b01465`, "retire the pin register"). `emit_contracts.py` is a different mechanism: a topic-keyed contract, not a line-numbered pin register. Every citation marked **removed, see R-EMITTER** below named one of these two files. |
| **R-PREDICTION** | "EVERY ROW CARRIES ITS PREDICTION BESIDE ITS OBSERVATION." An island proof is a hypothesis until a live emitter carries the prediction next to the observed value. | `src/core/signal_contract.py:1146` (`emit`, which takes both `actual` and `expected`). Restated at `tests/test_emitter_eviction_and_digest.py:26`. |
| **R-TABS** | The default tab order is Trading, Market Inspector, Bot Swarm, Asset Charts, History, Simulator, Console. | `src/gui/main_tabs/main_window_surface.py:117-125` (`CANONICAL_TAB_ORDER`), pinned by `tests/test_canonical_tab_order.py::test_reorder_produces_canonical_order`. |
| **R-TOOLTIP** | Mouse-over descriptions need a uniform size, Simplified Technical English, a ten-word limit, no missing tooltips, and a three-second delay. | Issue #53 (operator, 2026-08-21). Not yet recorded in code or docs. |
| **R-ONE-INDICATOR-PER-MODULE** | One indicator per module; a module that grows a second indicator or reaches into another's maths fails. | `src/trading/ta_engine.py:18-19`, enforced by `tests/test_one_indicator_per_module.py`. |
| **R-PRIVACY** | The privacy-mask registry covers exactly 19 fields in 5 groups. "Update spec + tests before changing this count." A privacy control must never fail open. | `src/core/privacy_mask_registry.py:5-28` and `:103-105`. |
| **R-PAPER-7** | Paper Trader has seven stated requirements, beginning "Identical to the Trading tab in every way, bar a slightly different colour scheme". | `NO RECORDED SPEC` |
| **R-NO-PIN-NO-RESULT** | A site with no readable result is deliberately NOT an emitter. The absence of an emitter is therefore not automatically a violation. | **removed, see R-EMITTER** |

---

## THE TAB SET, MEASURED

The operator named ten subsystems. The application builds seven tabs.

I parsed `src/gui/main_window.py` for every `addTab` / `insertTab` call made on the main
tab widget. The probe ran through pytest, so `tests/conftest.py` redirected all log writes
away from the operator's live tree.

**Measured result — seven tabs are added.** The Stage 2/3 split moved each tab's
construction into its own mixin in `src/gui/main_tabs/`, and each mixin now calls
`addTab`/`insertTab` directly:

| Tab | Added at |
| --- | --- |
| Trading | `src/gui/main_tabs/trading_tab.py` |
| Asset Charts | `src/gui/main_tabs/charts_tab.py` |
| Bot Swarm | `src/gui/main_tabs/bot_swarm_tab.py` |
| Market Inspector | `src/gui/main_tabs/market_inspector_tab.py` |
| Simulator | `src/gui/main_tabs/simulator_tab.py` |
| History | `src/gui/main_tabs/history_tab.py:34` |
| Console | `src/gui/main_tabs/console_tab.py` |

The construction order is declared once, at `BUILT_TAB_ORDER`
(`src/gui/main_tabs/main_window_surface.py:127-135`), and it still names the same seven
tabs in the same order this table records.

`CANONICAL_TAB_ORDER` now lives at `src/gui/main_tabs/main_window_surface.py:117-125`
(and is re-declared inline for the Qt path at `src/gui/main_window.py:290-297`), and lists
exactly those seven and no others. **Paper Trader, Proof of Accumulation and System
Status add no tab.** The order pin at `tests/test_canonical_tab_order.py` therefore
agrees with the code, and the operator's list of ten is three tabs ahead of the
application.

**CONTROL for this measurement.** The parser filtered on the tab widget, not on the word
`addTab`. Two negative controls ran with it. First, the parser had to find a non-zero
number of sites — a zero would mean the reader is broken, not that the application has no
tabs. Second, the parser had to NOT return `"Get Started"`, a real `addTab` call on a
different widget, now at `src/gui/main_tabs/trading_tab.py:125`. Both controls held then.
A reader that returned zero, or that returned "Get Started", would have been reported as
broken rather than as a finding about the application.

**One condition to record.** The suite's own live-tree guard reported `DEGRADED` on every
run in this audit, because a live `Acervator.exe` process was running and writing to
`~/.acervator_logs`. The guard therefore could not attribute log writes to the test suite
and did not fail them. Nothing in this audit wrote to the live tree, but this audit cannot
prove that from the guard alone. Re-run with Acervator closed for that proof.

---

## WHAT THIS MATRIX DOES NOT COVER — read this before you trust a row

A complete-looking matrix that is partial is the failure this document exists to stop. The
gaps below are what the matrix does not establish.

1. **No live network call was made.** Every statement about how the real Coinbase venue
   behaves rests on the ccxt contract, not on a Coinbase response. This audit ran offline
   and read-only. It never started, stopped or attached to `Acervator.exe`.

2. **Most rows are `[S]`, source reading.** Driving a Qt tab end to end needs a running
   application with live credentials. Where a row could be driven through pytest it was,
   and it carries `[M]` or `[T]`. Where it could not, the Works column says `UNVERIFIED`
   and that is the honest answer, not a soft `WORKING`.

3. **`UNVERIFIED` is not `WORKING`.** A feature marked `UNVERIFIED` may be perfect or may
   be dead. This audit does not know which, and no reader should treat the two as the
   same.

4. **The `ExtractorBot` seam is not enumerated.** It is recorded as not release-ready and
   its rows are absent from the Trading subsystem, as they were absent from the venue-seam
   audit (`docs/engineering-notes/2026-08-25_the_venue_seam.md:578-580`).

5. **`src/stocks/` is out of scope.** It is a separate `BrokerBase` hierarchy, never
   imported, with its own unrelated meaning of the word "paper"
   (`docs/engineering-notes/2026-08-25_the_venue_seam.md:585-586`).

6. **Timing, ordering and concurrency were not compared** between venues beyond what the
   venue-seam audit already recorded.

7. **Granularity is a choice.** A coarser reading merges rows and reports a smaller total.
   A finer reading splits them and reports a larger one. The counts here are defensible at
   this granularity and are not defensible as absolutes. What matters is that the ID SET
   is complete, not that the row count is a particular number.

8. **Compliance is measured against recorded rules only.** Where no rule is recorded, the
   Rule column says `UNKNOWN`, not `COMPLIANT`. A feature nobody specified is a feature
   nobody can call non-compliant. That is why the `NO RECORDED SPEC` count matters.

---

## THE TEST SUITE, MEASURED — the baseline behind every `[T]` row

Every row marked `[T]` rests on a test in this suite. The suite itself was therefore
measured first. A test that does not run proves nothing.

Command: `python -m pytest tests/ -q -p no:cacheprovider -n auto`. Exit code **1**.
Not 139 (SIGSEGV) and not 127 (std::terminate), so the failure summary below is real and
complete.

| Result | Count |
| --- | --- |
| passed | **8,409** |
| failed | 34 |
| errors | 15 |
| skipped | 1 |
| xfailed | 14 |
| wall time | 107.88 s on 24 cores |

**Every one of the 34 failures and 15 errors is a clone artefact, not a product defect.**
They live in exactly four files — `tests/test_hooks.py`, `tests/test_hooks_integration.py`,
`tests/test_release_gate_hook.py` and `tests/test_harness_is_reachable.py`. All four test
the Claude harness, not the trading application, and all four read the `.claude/`
directory. That directory was deliberately untracked in commit `23e5e79`
("chore: untrack .claude so a clone does not inherit the harness hooks"), so a fresh clone
has none. Verified: all four files reference `.claude`, and `.claude/` does not exist in
this clone.

**No test of the trading product failed.** That is the baseline. A `[T]` row in this
matrix means a passing test proves the behaviour today.

**CONTROL for this measurement.** The run produced 34 failures, so the instrument can
report a failure — it is not a reader stuck on green. It also produced 8,409 passes, so it
is not a reader stuck on red. Both directions are demonstrated by the same run.

**A caution the suite does not remove.** A green suite is not a clean codebase.
`docs/engineering-notes/2026-08-24_archetype_census.md` measured **165 of 651 source files failing
their archetype with 1,075 high-severity findings**, while the release gate reported
`[OK] Release-ready`. The gate runs the test suite and then points the audit tool at three
tiny sample files, never at `src/`. "The suite passes" and "the code is sound" are
therefore different claims, and this matrix only supports the first.

---

## PART A — CODE ON DISK THAT IS NOT A FEATURE

Read this section as **cruft to be removed, not as features**. The operator ruled:

> "Nothing exists for them. They are fresh builds."

That ruling covers **Proof of Accumulation** and **System Status**. Code found on disk is
not the subsystem. This section exists only to put a NUMBER in front of the delete-or-keep
decision, on the same principle that removed the grid bot:

> "We have grown beyond it and we do not need souvenirs."

### THE NUMBER

**4,664 lines carry the Proof of Accumulation name. 0 lines carry System Status.**
A further **1,200 lines** of sibling tabs shelved by the same 2026-04-21 decision sit in
the identical state. Counted with `wc -l` on the read-only clone.

| Tier | What it is | Lines |
| --- | --- | ---: |
| 1 — safe-delete orphans | zero importers anywhere in production | **2,942** |
| 2 — plus the competition package | executes at boot, serves no reachable consumer | **5,503** |
| 3 — plus the bridge | `shared_testnet.py`, live but wired to nothing | **5,864** |
| 4 — plus the stock window | orphan in production, one test imports it | **6,517** |

#### Tier 1, the safe-delete list

| File | Lines |
| --- | ---: |
| `src/trading/poa_tournament.py` | 876 |
| `src/gui/testnet_tab.py` | 544 |
| `src/gui/competition_tab.py` | 322 |
| `src/gui/risk_tab.py` | 322 |
| `src/gui/journal_tab.py` | 301 |
| `src/gui/analytics_tab.py` | 294 |
| `src/gui/alerts_tab.py` | 283 |
| **Total** | **2,942** |

Every one of these appears in `main_window.py` only as `self._X_tab = None`. Zero
`addTab`. Zero imports. The positive control for that zero: the same search DOES find
importers for `history_tab` (**stale citation, unverified**) and `bot_visualizer`
(**stale citation, unverified**), both known reachable. The zeros are real, not a broken reader.

`src/trading/poa_tournament.py` is the largest single orphan at 876 lines, has zero
importers anywhere, and — importantly — **was written AFTER the 2026-04-21 shelving
decision**. It has never had a consumer.

### THE FINDING THAT CHANGES THE DECISION

**`src/competition/` is not dead code. It runs on every launch.**

Measured by a pytest probe with a negative control (importing stdlib `json` reported zero
competition modules; the real path reported eight):

- `src/gui/main_window.py:267` calls `SharedTestnetBridge.install_on(self)` inside
  `MainWindow.__init__`.
- That method (`src/gui/shared_testnet.py:174`) imports
  `src.competition.local_testnet`, constructs `LocalTestnet()` and calls `_try_load()`.
- Importing that submodule triggers `src/competition/__init__.py`, which eagerly imports
  **eight modules**, 2,151 of the package's 2,561 lines.
- `LocalTestnet` reads `~/.acervator/testnet_chain.json` at every boot. That file is
  **4,059,629 bytes**, last written **2026-04-21** — the exact day the tab was removed.

The application therefore parses **4 MB of JSON on every launch for a subsystem the
operator has ruled does not exist.** Nothing ever rewrites the file: the write path only fires after a
competition, and `request_competition` has zero live callers.

The accurate description is not "dead code on disk". It is **a live bridge to nothing** —
boot cost and a 4 MB read, with the consumer removed four months ago.

| Package file | Lines | Loads at boot |
| --- | ---: | --- |
| `local_testnet.py` | 662 | yes |
| `competition_engine.py` | 388 | yes |
| `bot_identity.py` | 266 | yes |
| `merkle_log.py` | 244 | yes |
| `token_ledger.py` | 214 | yes |
| `challenge_protocol.py` | 212 | yes |
| `base_config.py` | 210 | no |
| `trophy_generator.py` | 200 | no |
| `season_schedule.py` | 132 | yes |
| `__init__.py` | 33 | yes |
| **Total** | **2,561** | **2,151 of it** |

**A counting caveat, stated so the number is not trusted further than it should be.**
`trophy_generator.py` reads as 200 lines but is **80,537 bytes**, with a longest line of
7,802 characters. It holds minified SVG trophy art. `wc -l` understates that one file by
roughly 40 times. Every other file above is normally formatted, so line counts are honest
for them. The totals in this section undercount `trophy_generator.py`.

### SYSTEM STATUS — measured, nothing on disk

Searching `src/`, `tests/` and `docs/` for `System Status`, `system_status` and
`SystemStatus` returned **two code hits, both unrelated**:
`src/exchange/ccxt_connector.py:167` and **stale citation, unverified**, each holding the
Kraken REST URL for its own system-status endpoint. The second site is now at
`src/gui/main_tabs/api_tester_tab_surface.py:351` and, duplicated for the Qt widget,
`src/gui/widgets/api_tester_tab.py:846-847`; the ccxt_connector.py site is unmoved, now at
`:135`.

**Zero lines of System Status subsystem code exist.** The operator's ruling was confirmed
by measurement, not assumed. Control: the same search returns thousands of hits for
`competition`, so the reader is not stuck on zero.

### AN OPEN ISSUE THAT IS NOW WRONG

**Issue #79 contains a claim that no longer holds.** It states `design_system.py` is
"imported by zero widgets". That is false today: `src/gui/instance_consent_dialog.py:43`
has `from src.gui import design_system as ds`, and that file is reachable from
**stale citation, unverified**.

`src/gui/design_system.py` (256 lines) is **reachable and is NOT cruft.** It is excluded
from every count above. The spirit of #79 survives — one importer across roughly twenty
GUI files — but the literal claim needs correcting before anyone acts on it. Note also
that two files carry the name: `src/gui/design_system.py` (256 lines, Qt tokens) and
`src/design_system.py` (563 lines, matplotlib and PDF tokens). Issue #79 names only the
first.

### THE RECORDED DECISION — P1.7 and MEM-178, written down so it is not rediscovered

**stale citation, unverified**, quoted in full:

    # --- Tab 7: Proof of Accumulation — REMOVED per P1.7 / MEM-178 ---
    # Operator directive 2026-04-21: 7 GUI tabs marked for removal.
    # MEM-034 / ADR-008 (PoA) IP record preserved; only UI surface shelved.
    self._competition_tab = None

    # --- Tab 8: Local Testnet — REMOVED per P1.7 / MEM-178 ---
    # MEM-034 / ADR-008 (PoA) IP record preserved; UI surface shelved.
    # Also removes prior-attempt artifact: duplicate unreachable
    # except clause that was part of a failed earlier removal.
    self._testnet_tab = None

The same banner marks five more tabs in the same block: Audio Suite (`:5506`), Analytics
(`:5509`), Risk (`:5514`), Journal (`:5518`), Alerts (`:5523`).

**P1.7 — the capture, 2026-04-21 15:30 UTC.**
`docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md:5491`. The operator sent a screenshot of
v3.13.7 with seven tabs struck through in red: PoA Network, Testnet, Audio, Analytics,
Risk, Journal, Alerts. His directive: "Keep in memory for completion later."
The capture flagged its own risk:

> "Removing those tabs shelves the user-facing PoA experience but preserves the underlying
> IP record fully — ADR-008 and MEM-034 remain the authoritative patent record. ... The
> IP is patentable regardless of whether the UI currently ships."

**MEM-178 — the execution, 2026-04-21 16:30 UTC.** Chronicle line 5688, one hour later.
The operator: "Previous tab removal instructions have not been followed. They were
attempted but failed." Seven tabs were then removed from `main_window.py` and four from
`stock_main_window.py`. The method is the reason the cruft exists today:

> "Each try/except block to a comment plus `self._X_tab = None`. Preserves downstream
> hasattr/is-None semantics. Underlying managers ... kept intact because background timers
> reference them. Tab widget classes and files untouched; restoration is reverting to
> the original try blocks."

**The decision was this: shelve the UI, keep the files, preserve the IP.** It was deliberate,
dated, and it was the second attempt — the first failed and left a duplicate unreachable
`except` clause behind as evidence.

**Three things that decision did not anticipate, all measured above:**

1. "Files untouched" left 4,664 lines of Proof of Accumulation on disk for four months.
2. The bridge was never unwired. The package still loads eight modules and parses 4 MB at
   every launch, for a consumer that no longer exists.
3. `poa_tournament.py` (876 lines) was written after the shelving and never had an
   importer.

**For the record:** `MEM-178`, `P1.7`, `MEM-034` and `ADR-008` survive in this repository
only as references. This repository holds no `docs/adr/` directory and no primary MEM
text. The
chronicle passages quoted above are the deepest recorded source that exists here.

### BEFORE ANYTHING IS DELETED

Two tests name this code and would need editing first:
`tests/test_acervator_integration.py:48` lists the string `"src.competition"`, and
`tests/test_ivp_empty_state_is_legible.py:346` imports `stock_main_window`. Also
`contracts/deploy.py:41` imports `src/competition/base_config.py` from outside `src/`.
None of this was measured against a deletion; it is predicted breakage, not observed.
---

## THE ID SET JOINS A VOCABULARY THAT ALREADY EXISTS

One naming scheme for subsystems is already in the repository, and the IDs in this matrix
line up with it deliberately. A fourth vocabulary would make the translation problem
worse, not better.

**removed, see R-EMITTER** records a subsystem token and a number for every
emitter in the platform. The operator specified that scheme himself on 2026-08-13:

> "emitter naming convention should be subsystem_number + emitter_ID number + Signal Type."
>
> "ID numbers can be correlated to their names in the markdown and under the forthcoming
> System Status tab where all emitters are organized under their subsystems."

The table below joins the two. Read it as the dictionary between a feature ID in this
matrix and an emitter name in the log.

| This matrix | Emitter token | Emitter number |
| --- | --- | --- |
| `TRADING/...` | `trading` | `12` |
| `MKT-INSPECTOR/...` | `topology` | `09` |
| `BOT-SWARM/...` | `swarm` | `11` |
| `ASSET-CHARTS/...` | `charts` | `13` |
| `HISTORY/...` | `history` | `05` |
| `SIM/...` | `sim` | `06` |
| `CONSOLE/...` | `console` | `14` |
| `PAPER/...` | none yet | none yet |
| `PROOF-OF-ACCUMULATION/...` | none | none |
| `SYSTEM-STATUS/...` | none yet | none yet |

Six further tokens in that register are not tabs and get no feature ID here: `bot` (01),
`extractor` (02), `fleet` (03), `gui` (04), `ta` (07), `tick` (08), `ytd` (10),
`exchange` (15), `apitest` (16) and `instance` (17). They are engine-level, not surfaces
the operator clicks.

**Why this matters for the System Status build.** Issue #34 asks that the tab group
emitter activity "by Subsystem and Tab". The emitter register supplies the subsystem axis
today. This matrix supplies the tab-and-feature axis. Neither one alone answers the
question the tab is meant to answer, and together they do.

---
---

## SUBSYSTEM 1 — TRADING

**Verdict in one line.** The most complete subsystem in the application — seven of its nine
framing features work — but **the safety prompt meant to stop a buy overshooting target has
never once run**, and the Fire button that moves real money on your command has no test at
all.

### Trading — the nine framing features

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `TRADING/bot-list` | The Scrumming and Extractor bot tables and their columns | BUILT | WORKING | COMPLIANT | `main_window.py:1940-1954`, `:2640-2663` | [M] |
| `TRADING/ta-voting-panel` | The Indicator Voting Panel | BUILT | WORKING | COMPLIANT | `indicator_panel.py:3-23` | [M] |
| `TRADING/bot-controls` | New Bot, Start, Pause, Stop, Restart, Delete and Fire | BUILT | **BROKEN** — the buy-confirmation prompt never runs | **NON-COMPLIANT** | `buy_confirmation_dialog.py:8-14` | [S] |
| `TRADING/bot-details` | The per-bot window and its eight pages | BUILT | WORKING | COMPLIANT | **stale citation, unverified** | [T] |
| `TRADING/exchange-panels` | One panel per connected exchange, plus Add Exchange | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [M] |
| `TRADING/header-stat-strip` | Spendable, Scrummed, Folded, Trades, Bots and Errors | PARTIAL | WORKING | COMPLIANT | **stale citation, unverified** | [T] |
| `TRADING/activity-and-api-logs` | The two log panes at the bottom and their Pause buttons | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [M] |
| `TRADING/privacy-controls` | Privacy Mode, the per-number dots and the column headers | BUILT | WORKING | **NON-COMPLIANT** — the button says 18 masks, the registry holds 19 | `src/core/privacy_mask_registry.py:103-105` | [M] |
| `TRADING/emitter-network` | The Trading tab's tracked emitters | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [M] |

**Nine framing features. 8 BUILT, 1 PARTIAL, 0 ABSENT. 8 WORKING, 1 BROKEN. 2
NON-COMPLIANT.**

### Trading — the two findings at framing level

**1. The buy-confirmation prompt has never run.** It is the Yes / No / Skip box that is
supposed to stop a buy pushing a bot over its target. The dialog is built. The broker is
built. The broker is even constructed at startup (**stale citation, unverified**). And the
method that raises the prompt **has zero call sites in the repository**. Its own recorded
contract says the bot's buy path calls it and refuses the buy after sixty seconds
(`buy_confirmation_dialog.py:8-14`). No bot calls it. Every buy proceeds unprompted.

**2. The Fire button has no test.** It is the operator's live-money override. No test in
the whole suite names its handler. The fold-tranche fire path inside Bot Details is tested
heavily; the button on the row is not.

### `TRADING/emitter-network` — measured

**11 of the tree's 78 emitters belong to this tab**: 6 under the `trading` token and 5
under `exchange`, all emitted from `src/gui/main_window.py`. Both sets are registered
(**removed, see R-EMITTER** and `:1646-1651`) and both carry a prediction
beside an observation, verified by paired falsifier tests that inject a defect and require
the emitter to go red.

### Trading — functions beneath each framing feature

#### `TRADING/bot-list`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/bot-list/scrumming-table` | The upper table; your selection survives a refresh | BUILT | WORKING | `main_window.py:1939`, `:2116`, `:1799` | `main_window.py:1940-1954` | `tests/test_exchange_tab_emitters.py::test_a_quiet_refresh_leaves_the_selection_where_it_was` | [M] |
| `TRADING/bot-list/extractor-table` | The lower table, with Pool and Liquid | BUILT | WORKING | `main_window.py:2664`, `:2737`, `:2668-2671` | `main_window.py:2640-2663` | `tests/test_extractor_tranche_listing.py::test_the_extractor_row_has_no_fire_button` | [M] |
| `TRADING/bot-list/ammo-column` | How far the bot is from target, green to sell, red to buy | BUILT | WORKING | `main_window.py:111`, `:72`, call `:2196` | `main_window.py:1985-1988`, `:2151-2170` | `tests/test_ammo_matches_manual_fire_target.py::TestTheArithmeticAgrees::test_display_delta_equals_engine_delta` | [T] |
| `TRADING/bot-list/target-in-btc-and-eth` | Target BTC and Target ETH, with the 24-hour divergence | BUILT | WORKING | `main_window.py:257`, calls `:2234-2242` | `main_window.py:1968-1979` | `tests/test_main_table_denom_cells.py::TestComposeTableTargetDenomCell::test_dash_when_pair_not_listed` | [T] |
| `TRADING/bot-list/symbol-opens-chart` | Clicking the pair opens its chart in your browser | BUILT | WORKING | `main_window.py:2595`, wired `:2054` | `main_window.py:2050-2053` | `tests/test_exchange_chart_urls.py::TestClickHandler::test_click_opens_url_via_webbrowser` | [T] |
| `TRADING/bot-list/refresh-tick` | The tab redraws about every two seconds | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified** | `main_window.py:3267-3280` | `tests/test_exchange_tab_emitters.py::test_the_cadence_declaration_is_what_the_source_does` | [M] |
| `TRADING/bot-list/splitter-layout` | The draggable dividers around the tables | BUILT | UNVERIFIED | **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |

#### `TRADING/ta-voting-panel`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/ta-voting-panel/the-panel` | The panel itself, shared with the Simulator | BUILT | WORKING | **stale citation, unverified**; `indicator_panel.py:744`, `:1063`, `:1810` | `indicator_panel.py:3-23` | `tests/test_voting_panel_fits_its_pane.py::TestTheTradingTabIsUnaffected::test_the_trading_tab_panel_also_fits` | [M] |
| `TRADING/ta-voting-panel/bot-picker` | The "Bot:" dropdown choosing whose indicators you see | BUILT | WORKING | `indicator_panel.py:804-816`, `:1365`, `:1764` | `src/core/privacy_mask_registry.py:83` | `tests/test_ivp_empty_state_is_legible.py::TestForceRefreshIsHonest::test_a_new_bot_gets_a_named_empty_state` | [T] |
| `TRADING/ta-voting-panel/timeframe-lock` | The dropdown stopping trades fighting a higher timeframe | BUILT | UNVERIFIED | `indicator_panel.py:860-880`, `:1354`; consumer **stale citation, unverified** | `indicator_panel.py:869-873` | NO TEST | [S] |
| `TRADING/ta-voting-panel/currency-rate-strip` | The blue BTC and ETH spot line above the columns | BUILT | WORKING | `indicator_panel.py:891-905`, `:1269`; pumped **stale citation, unverified** | `indicator_panel.py:884-890` | `tests/test_indicator_panel_v3_23_50.py::TestLiveRender::test_rate_strip_emits_gwei_not_wei` | [T] |
| `TRADING/ta-voting-panel/empty-state-says-why` | With no reading the panel says why instead of inventing one | BUILT | WORKING | `indicator_panel.py:1399`, `:1415`, `:1523`; cause **stale citation, unverified** | `indicator_panel.py:1404-1412` ("An empty panel is a true statement") | `tests/test_c51_indicator_panel_no_fabrication.py::TestRealBotIsNeverFabricated::test_selecting_a_real_bot_does_not_invent_data` | [T] |

#### `TRADING/bot-controls`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/bot-controls/new-bot-button` | "+ New Bot" on each exchange panel | BUILT | WORKING | `main_window.py:2955-2959`, handler **stale citation, unverified** | `main_window.py:2913-2919` | `tests/test_extractor_requires_parent.py` | [S] |
| `TRADING/bot-controls/creation-wizard` | The window that walks you through making a bot | BUILT | WORKING | `bot_wizard.py:1780`, pages `:96`, `:261`, `:325`, `:541`, `:1599`, `:1662` | `NO RECORDED SPEC` | `tests/test_bot_wizard_accessibility.py::TestBotCreationWizard::test_wizard_builds_every_page` | [T] |
| `TRADING/bot-controls/command-bar` | Start, Pause, Stop, Restart and Delete, with a confirmation | BUILT | WORKING | `main_window.py:3084-3093`, `:3156`, pin `:3234`, **stale citation, unverified**, confirm **stale citation, unverified** | `main_window.py:3179-3243` | `tests/test_exchange_tab_emitters.py::test_a_command_reaches_the_table_the_operator_chose` | [M] |
| `TRADING/bot-controls/fire-button` | The per-row Fire button, and its glow when armed | BUILT | UNVERIFIED | `main_window.py:2366-2396`, `:2615`, **stale citation, unverified**, glow **stale citation, unverified**, **stale citation, unverified** | `docs-archive/llm-session-history/ACERVATOR_HOP5.md:6350` | **NO TEST** | [S] |
| `TRADING/bot-controls/buy-confirmation-prompt` | The Yes / No / Skip box before an overshooting buy | PARTIAL | **BROKEN** — zero call sites | `buy_confirmation_dialog.py:49`, `:92`, `:259`, `:176`; constructed **stale citation, unverified**; **caller: none** | `buy_confirmation_dialog.py:8-14` | NO TEST | [S] |
| `TRADING/bot-controls/start-all-bots` | Start All, Pause All and Stop All for the whole fleet | **ABSENT** | **BROKEN** — dead code, zero callers | **stale citation, unverified**; `start_all_progress_dialog.py:29` | removal recorded at `docs-archive/llm-session-history/ACERVATOR_HOP5.md:6732` | `tests/test_start_all_progress_events.py::test_begin_event_reaches_the_signal` (dialog only) | [S] |
| `TRADING/bot-controls/trade-sound-cues` | Fire on a fill, coins on profit, a drip on a fold, beeps near firing | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified**, dispatched **stale citation, unverified** | **stale citation, unverified** | NO TEST | [S] |

#### `TRADING/bot-details`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/bot-details/the-window` | The Detail button, Prev and Next, and Apply Changes | BUILT | WORKING | **stale citation, unverified**, `:2582`, `:2876`; **stale citation, unverified**, nav **stale citation, unverified**, apply **stale citation, unverified** | `NO RECORDED SPEC` | `tests/test_bot_live_settings_fold_row_admission.py::TestTheDialogOpens::test_no_exception_escapes_the_tab_builder` | [T] |
| `TRADING/bot-details/the-eight-pages` | Status, Settings, Fold Tranches, Stack Tranches, Bot Swarm, Market Inspector, Phantom Bots, Positions Held | BUILT | WORKING | **stale citation, unverified** and the eight builders | **stale citation, unverified** | `tests/test_stack_mode_visible.py::TestStackTranchesTab::test_tab_registered_for_all_scrumming_bots` | [T] |
| `TRADING/bot-details/clear-fold-tranches` | Clear discards queued fold tranches after naming the consequence | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**, settle **stale citation, unverified** | R-TRANCHE at `bot_live_settings.py`, **stale citation, unverified** | `tests/test_clear_fold_tranches.py::TestItDiscardsTheQueue::test_the_report_states_what_was_discarded` | [T] |
| `TRADING/bot-details/despawn-timer-rows` | What the despawn timer would remove, before you arm it | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | R-TRANCHE at **stale citation, unverified** | `tests/test_despawn_window_is_usable.py::test_the_panel_adds_no_removal_button` | [T] |
| `TRADING/bot-details/self-destruct` | The Danger Zone button that makes you type the word | BUILT | UNVERIFIED | **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |

#### `TRADING/exchange-panels`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/exchange-panels/one-panel-per-exchange` | A panel for each connected exchange | BUILT | WORKING | `main_window.py:2899`, **stale citation, unverified**, **stale citation, unverified** | **removed, see R-EMITTER** | `tests/test_trading_tab_emitters.py::test_exchange_tab_routing_is_reported` | [M] |
| `TRADING/exchange-panels/add-exchange` | The Add Crypto Exchange button and its empty-state card | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | **stale citation, unverified** | NO TEST | [S] |
| `TRADING/exchange-panels/data-pull-countdown` | The blue data-pool freshness line | BUILT | WORKING | `main_window.py:2969-2988`, `:3095` | `main_window.py:2961-2968` | `tests/test_data_pool_ohlcv_coalescing.py::test_pull_rate_summary_shape` | [T] |
| `TRADING/exchange-panels/news-ticker` | The scrolling crypto headlines | BUILT | WORKING | `main_window.py:2946-2954`; `crypto_news_ticker.py` | `main_window.py:2941-2946` | `tests/test_crypto_news_ticker.py` | [T] |
| `TRADING/exchange-panels/crypto-stock-toggle` | The button swapping the surface between Crypto and Stock | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**, pin **stale citation, unverified** | **removed, see R-EMITTER** | `tests/test_trading_tab_emitters.py::test_active_layer_alias_is_reported` | [M] |
| `TRADING/exchange-panels/settings-dialog` | File to Settings, the eleven-page settings window | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**; `settings_dialog.py:79-89` | **stale citation, unverified** | `tests/test_c12_settings_roundtrip.py::TestEveryWrittenKeyIsAField::test_no_key_is_written_that_cannot_be_stored` | [T] |
| `TRADING/exchange-panels/status-bar-indicators` | The API load pill and the AI indicator at the window foot | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | **stale citation, unverified** | NO TEST for the pill | [S] |

#### `TRADING/header-stat-strip`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/header-stat-strip/spendable-strip` | Spendable, Realised, Locked, Mature and Exch | PARTIAL | UNVERIFIED — Realised and Mature always read blank | `main_window.py:962`, `:1101`, fed **stale citation, unverified** | **stale citation, unverified** ("No P/L calculation. Realised / Mature pass as None") | NO TEST | [S] |
| `TRADING/header-stat-strip/scrummed-total` | The Scrummed high-score card | BUILT | WORKING | **stale citation, unverified**, update **stale citation, unverified** | `NO RECORDED SPEC` | `tests/test_ytd_scrum_fold_and_errors_reset.py::TestYtdScrumFoldAccumulation::test_sells_land_in_scrummed_buys_in_folded` | [T] |
| `TRADING/header-stat-strip/folded-total` | The Folded high-score card | BUILT | WORKING | **stale citation, unverified**, update **stale citation, unverified** | `docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md:13783-13787` | `tests/test_ytd_scrum_fold_and_errors_reset.py::TestYtdScrumFoldAccumulation::test_quote_to_usd_multiplier_applied` | [T] |
| `TRADING/header-stat-strip/trades-and-bots` | The Trades and Bots cards | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified**, update **stale citation, unverified** | `docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md:14080-14081` | NO TEST | [S] |
| `TRADING/header-stat-strip/errors-card` | The Errors card, and the log it opens | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified**, reset **stale citation, unverified** | **stale citation, unverified** | `tests/test_ytd_scrum_fold_and_errors_reset.py::TestErrorsCardAndResetSourceDiscipline::test_lifetime_qualifier_dropped_from_card_label` | [T] |
| `TRADING/header-stat-strip/profit-loss-card` | The old P/L card | **ABSENT from the screen** | WORKING as a backing value | **stale citation, unverified** (hidden), still updated **stale citation, unverified** | **stale citation, unverified** (operator: "strange numbers I do not understand") | NO TEST | [S] |
| `TRADING/header-stat-strip/hides-on-simulator` | The strip disappears on Simulator and Paper Trader | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified** | **stale citation, unverified** | NO TEST | [S] |

#### `TRADING/activity-and-api-logs`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/activity-and-api-logs/activity-log` | The left log pane | BUILT | WORKING | `main_window.py:364`, **stale citation, unverified**, `:458`, `:507` | `main_window.py:364-376` | `tests/test_c39g_bot_log_reaches_disk.py::TestBotLogReachesDisk::test_a_bot_log_emission_is_written` | [T] |
| `TRADING/activity-and-api-logs/activity-log-pause` | Pause Console, with buffered lines flushed on resume | BUILT | WORKING | **stale citation, unverified**, pin **stale citation, unverified** | **removed, see R-EMITTER** | `tests/test_trading_tab_emitters.py::test_activity_log_pause_is_reported` | [M] |
| `TRADING/activity-and-api-logs/activity-log-watchdog` | A warning in the log when the log itself stops spooling | BUILT | UNVERIFIED | **stale citation, unverified** (60 s timer) | **stale citation, unverified** (operator 2026-05-06) | NO TEST | [S] |
| `TRADING/activity-and-api-logs/api-log` | The right pane showing every API call and its timing | BUILT | WORKING | **stale citation, unverified**, feed **stale citation, unverified**; `src/exchange/api_logger.py` | **stale citation, unverified** | `tests/test_main_window_suppression_repairs.py::test_h6_well_formed_event_is_buffered_quietly` | [T] |
| `TRADING/activity-and-api-logs/api-log-pause` | Pause API Log, with a 2000-line buffer | BUILT | UNVERIFIED | **stale citation, unverified** | R-NO-PIN-NO-RESULT at **removed, see R-EMITTER** | NO TEST | [S] |

#### `TRADING/privacy-controls`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/privacy-controls/privacy-mode-button` | The button that masks everything for screen sharing | BUILT | WORKING | `main_window.py:2927-2940`, `:3421`, pins `:3470`, `:3520` | `src/core/privacy_mask_registry.py:5-28`, `:103-105` | `tests/test_exchange_tab_emitters.py::test_the_button_agrees_with_the_registry` | [M] |
| `TRADING/privacy-controls/button-label-matches-the-registry` | The button's label states what it actually masks | **BROKEN** | **BROKEN** — says 18 masks in 4 groups; the registry holds 19 in 5 | `main_window.py:2927-2940` | `src/core/privacy_mask_registry.py:103-105` | `tests/test_exchange_tab_emitters.py::test_the_button_agrees_with_the_registry` | [M] |
| `TRADING/privacy-controls/privacy-dots` | The small dots hiding one number at a time | BUILT | WORKING | `main_window.py:795`, `:675`, `:1041-1048`, **stale citation, unverified**; `indicator_panel.py:433` | `src/core/privacy_mask_registry.py:5-28` | `tests/test_c03_swarm_rows_and_privacy.py::TestTheMaskingInstrumentWorks::test_the_registry_toggles` | [T] |
| `TRADING/privacy-controls/column-headers` | Click a column header to mask that whole column | BUILT | WORKING | `main_window.py:2062`, `:2079`, map `:2003-2013` | `src/core/privacy_mask_registry.py:73-79` | `tests/test_exchange_tab_emitters.py::test_a_partial_apply_that_leaves_fields_exposed_is_reported` | [M] |

#### `TRADING/emitter-network`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TRADING/emitter-network/trading-pins` | The six Trading-tab emitters | BUILT | WORKING | `src/core/signal_contract.py:720-725`; emitted from `main_window.py` | **removed, see R-EMITTER** | `tests/test_trading_tab_emitters.py` | [M] |
| `TRADING/emitter-network/exchange-pins` | The five exchange-panel emitters | BUILT | WORKING | `src/core/signal_contract.py:735-737` | **removed, see R-EMITTER** | `tests/test_exchange_tab_emitters.py` | [M] |
| `TRADING/emitter-network/pins-can-go-red` | Each emitter can report a failure, not only a success | BUILT | WORKING | paired falsifiers in both test files | R-PREDICTION at `src/core/signal_contract.py:1146` (`emit`, which takes both `actual` and `expected`) | `tests/test_trading_tab_emitters.py::test_a_pause_that_did_not_take_is_reported` | [M] |

### Trading measurement and its control

Ran through pytest, exit code 0: `tests/test_trading_tab_emitters.py` and
`tests/test_exchange_tab_emitters.py` — **60 passed in 11.32 s**.

**Control A — the runner can go red.** A scratch file holding a deliberately false
assertion, run through the identical invocation, returned one failure. The 60 out of 60
green is a real green, not a runner reporting nothing.

**Control B — the instrument can see a broken emitter.** Both files carry paired falsifiers
that inject a defect and require the emitter to go red. All pass, so the green side is
two-sided.

### What the Trading audit did not cover

Nothing was clicked; the eleven unverified functions were read, not watched against a live
fleet. The Extractor bot's venue behaviour is out of scope, as it was in the venue-seam
audit. The Stock wing beyond the toggle and its routing is out of scope. Whether the Fire
button's armed colour matches the bot's real phase at run time was not verified. What the
buy path does instead of calling the confirmation broker was not read.

---

## SUBSYSTEM 2 — MARKET INSPECTOR

**Verdict in one line.** The maths is sound and the topology-proposal half works well, but
the tab is measurably unfinished against its own design document, and **it is the only tab
in the application with no tracked emitters at all**.

### Market Inspector — the seven framing features

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `MKT-INSPECTOR/market-scan` | The scan that pulls candidate markets from your exchanges | BUILT | **BROKEN** — the freshness line reports "No data yet" after a successful scan | **NON-COMPLIANT** | `NO RECORDED SPEC` | [M] |
| `MKT-INSPECTOR/htf-signals-table` | The table of candidate markets and how strong each entry is | PARTIAL | **BROKEN** — the top two strength rungs cannot be reached | **NON-COMPLIANT** | same doc, `:213-232`, `:306-307` | [M] |
| `MKT-INSPECTOR/opposing-pairs-table` | The table of pairs that move against each other | BUILT | WORKING | COMPLIANT | same doc, `:234-247` | [T] |
| `MKT-INSPECTOR/market-picture-panel` | The coloured picture of the market universe on the left | **ABSENT** | **BROKEN** | **NON-COMPLIANT** | same doc, `:302-305` ("retained, operators liked it") | [S] |
| `MKT-INSPECTOR/topology-proposals` | The suggested multi-bot setups on the right | BUILT | WORKING | **NON-COMPLIANT** — the momentum-funnel type is dead and two controls are missing | `NO RECORDED SPEC` | [T] |
| `MKT-INSPECTOR/adopt-and-push` | Turning a proposal into real bots, or pushing it into the Simulator | BUILT | WORKING | **NON-COMPLIANT** — Bot Swarm is never told an adoption happened | same doc, `:175-186`, `:334-336` | [T] |
| `MKT-INSPECTOR/emitter-network` | The tab's tracked emitters | **ABSENT** | **BROKEN** | **NON-COMPLIANT** | issue #18 ("+ emitters") | [M] |

**Seven framing features. 4 BUILT, 1 PARTIAL, 2 ABSENT. 3 WORKING, 4 BROKEN. 6
NON-COMPLIANT.**

### Market Inspector — the three findings at framing level

**1. The freshness line reports "No data yet" after a successful scan.** Measured: the
status line fed a real result of 42 markets from an exchange returned
`'No data yet — press Refresh.'`. Control: the same function, the same object, with the
source set to cache returned `'Snapshot 5 min old · 42 markets'`, so the reader is not
stuck on one string. The cause is a branch mismatch — the status line tests four source
names and the fetcher only ever emits two, neither of them in that list.

**2. The entry-strength ladder cannot climb past its third rung.** Measured: a scan with
the two timeframes the fetcher supplies scored the low rung at 0.35. Control: the identical
fixture with a monthly timeframe added scored the medium rung at 0.6. The ladder works; the
shipped feed cannot reach it, because the score gates its two top rungs on three timeframes
and the fetcher builds only daily and weekly.

**3. This tab has no emitters.** Zero emit calls across all four of its source files, and
the emitter register holds no Market Inspector subsystem at all. Issue #18 asks for them by
name. **Of the tree's 78 emitters, this tab owns 0.**

### Market Inspector — functions beneath each framing feature

#### `MKT-INSPECTOR/market-scan`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MKT-INSPECTOR/market-scan/refresh-button` | The Refresh button | BUILT | WORKING | `market_inspector.py:122-131`, `::_start_fetch:301` | design doc `:308` | `tests/test_market_inspector_refresh_cadence.py::test_the_refresh_button_forces_the_network_through_every_hop` | [T] |
| `MKT-INSPECTOR/market-scan/freshness-line` | The grey line saying how old the data is and where it came from | BUILT | **BROKEN** | `market_inspector.py::_status_line:374-390` | design doc `:310` | NO TEST | [M] |
| `MKT-INSPECTOR/market-scan/cadence-hold` | The scan is reused for 15 minutes rather than re-hitting the venue | BUILT | WORKING | `market_inspector_fetcher.py:258-281`, `:38` | design doc `:310-311` | `tests/test_market_inspector_refresh_cadence.py::test_a_result_with_data_is_cached_and_served_inside_the_window` | [T] |
| `MKT-INSPECTOR/market-scan/universe-choice` | Top-volume dollar pairs, stablecoins excluded | BUILT | UNVERIFIED | `market_inspector_fetcher.py::_pick_universe:85-125`, `:62-70`, `:37` | design doc `:205-211` | NO TEST | [S] |
| `MKT-INSPECTOR/market-scan/every-exchange` | The scan reads every exchange you have connected | BUILT | UNVERIFIED | `market_inspector_fetcher.py:289-326`; roster `src/exchange/ccxt_connector.py:130-146` | `NO RECORDED SPEC` | NO TEST | [S] |
| `MKT-INSPECTOR/market-scan/include-active-markets` | The "Include active markets" tickbox | BUILT | WORKING | `market_inspector.py:133-141`, `:370-372`, `:405-406` | design doc `:249-255` | NO TEST | [S] |
| `MKT-INSPECTOR/market-scan/include-stablecoins` | An "Include stablecoins" tickbox | **ABSENT** | **BROKEN** | no site | design doc `:308` | NO TEST | [S] |
| `MKT-INSPECTOR/market-scan/timeframe-tickboxes` | The Daily, Weekly and Monthly tickboxes | **ABSENT** | **BROKEN** | no site | design doc `:308-309` | NO TEST | [S] |

#### `MKT-INSPECTOR/htf-signals-table`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MKT-INSPECTOR/htf-signals-table/the-table` | The table of candidate markets | BUILT | WORKING | `market_inspector.py:151-164`, `:409-428` | design doc `:306-307` | `tests/test_market_inspector.py::TestScanUniverseE2E::test_end_to_end_records_scan_ts` | [T] |
| `MKT-INSPECTOR/htf-signals-table/daily-and-weekly-columns` | Band position and squeeze, per timeframe | BUILT | WORKING | `market_inspector.py::_fmt_tf_state:74-80`; `src/trading/market_inspector.py::_analyze_tf:129-172` | design doc `:215-221`; R-INDICATOR | `tests/test_market_inspector.py::TestPerTfAnalysis::test_upper_extreme_detected` | [T] |
| `MKT-INSPECTOR/htf-signals-table/monthly-column` | A Monthly column beside Daily and Weekly | **ABSENT** | **BROKEN** | no site; the fetcher builds only daily and weekly at `market_inspector_fetcher.py:163-179` | design doc `:213`; constant `src/trading/market_inspector.py:44` | `tests/test_market_inspector.py::TestConstants::test_timeframes_are_d_w_m` pins three, the data path supplies two | [M] |
| `MKT-INSPECTOR/htf-signals-table/entry-strength-ladder` | How strong an entry the tab calls a market | PARTIAL | **BROKEN** — top two rungs unreachable | `src/trading/market_inspector.py::_score_market:174-245` | design doc `:222-232` | `tests/test_market_inspector.py::TestScoreMarket::test_three_lower_plus_tightening_gives_high` passes on a three-timeframe fixture only | [M] |
| `MKT-INSPECTOR/htf-signals-table/signal-colour-cue` | Green, red and amber on each signal word | BUILT | UNVERIFIED | `market_inspector.py::_signal_color:59-71` | design doc `:303-305` | NO TEST | [S] |
| `MKT-INSPECTOR/htf-signals-table/already-trading-marker` | The Active column marking markets a bot already trades | BUILT | WORKING | `market_inspector.py::update_active_symbols:203-214`; caller **stale citation, unverified** | design doc `:251-255` | `tests/test_market_inspector.py::TestScoreMarket::test_active_flag_preserved` | [T] |

#### `MKT-INSPECTOR/opposing-pairs-table`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MKT-INSPECTOR/opposing-pairs-table/the-table` | The 30-day opposing-pairs table | BUILT | WORKING | `market_inspector.py:167-180`, `:431-449`; `src/trading/market_inspector.py::_find_opposing_pairs:272-306` | design doc `:234-247` | `tests/test_market_inspector.py::TestOpposingPairs::test_pair_in_window_kept` | [T] |
| `MKT-INSPECTOR/opposing-pairs-table/correlation-maths` | The correlation number itself | BUILT | WORKING | `src/trading/market_inspector.py::_pearson:247-260`, `::_returns:262-270` | design doc `:239` ("real Pearson, not the current momentum-spread proxy"); R-INDICATOR | `tests/test_market_inspector.py::TestPearson::test_perfect_negative` | [T] |

#### `MKT-INSPECTOR/topology-proposals`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MKT-INSPECTOR/topology-proposals/proposal-cards` | The list of suggested setups | BUILT | WORKING | `market_inspector_topologies.py::_ProposalCard:227-295`, `::_render:518-534` | topology design `:194-226` | `tests/test_topology_proposals_gui.py::test_empty_source_shows_placeholder` | [T] |
| `MKT-INSPECTOR/topology-proposals/refresh-proposals` | The Refresh proposals button | BUILT | WORKING | `market_inspector_topologies.py:332-336`, `::refresh:376-394`; source `main_window.py::_build_topology_proposals` | topology design `:252-257` | `tests/test_topology_proposals_gui.py::test_refresh_swallows_source_exception` | [T] |
| `MKT-INSPECTOR/topology-proposals/auto-refresh` | Proposals refresh themselves every ten minutes | BUILT | UNVERIFIED | `market_inspector_topologies.py:49`, `:364-367` | topology design `:215`, `:256` | NO TEST | [S] |
| `MKT-INSPECTOR/topology-proposals/momentum-funnel` | Momentum-funnel suggestions | PARTIAL | **BROKEN** — the correlations map is built empty and never filled | **stale citation, unverified**; defect admitted at **stale citation, unverified** | topology design `:36-57` | `tests/test_topology_proposals.py::test_momentum_funnel_finds_correlated_cluster` passes on a map the tab never supplies | [S] |
| `MKT-INSPECTOR/topology-proposals/type-filter` | The Archetype dropdown on the proposals header | **ABSENT** | **BROKEN** | no site | topology design `:201` | NO TEST | [S] |
| `MKT-INSPECTOR/topology-proposals/collapsible-card` | Card details hidden until you open the caret | **ABSENT** | **BROKEN** — the caret is a static glyph | `market_inspector_topologies.py:256` | topology design `:222` | NO TEST | [S] |
| `MKT-INSPECTOR/topology-proposals/dismiss-for-a-day` | Dismiss hides a proposal for 24 hours, across restarts | BUILT | WORKING | `market_inspector_topologies.py:288-293`, `:419-432`, `:455-495`, `:497-508`; wiring **stale citation, unverified** | topology design `:333` | `tests/test_topology_dismiss_persistence.py::TestDismissalSurvivesRestart::test_a_fresh_pane_reloads_the_dismissal` | [T] |
| `MKT-INSPECTOR/topology-proposals/split-view-drag` | The draggable divider between tables and proposals | BUILT | UNVERIFIED | `market_inspector.py:101-102`, `:194-200` | topology design `:219` | NO TEST | [S] |

#### `MKT-INSPECTOR/adopt-and-push`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MKT-INSPECTOR/adopt-and-push/preview-window` | The Preview window showing what a proposal would create | BUILT | WORKING | `market_inspector_topologies.py::TopologyPreviewDialog:74-224` | topology design `:161-192` | `tests/test_topology_proposals_gui.py::test_dialog_adopt_click_emits_proposal` | [T] |
| `MKT-INSPECTOR/adopt-and-push/adopt-button` | Adopt turns a proposal into real bots and wires | BUILT | WORKING | `market_inspector_topologies.py:208-224`; `main_window.py::_adopt_topology_proposal` | topology design `:175-186`, `:334-336` ("Never skip the preview modal") | `tests/test_topology_proposals_gui.py::test_orchestrator_emits_wire_created_per_wire` | [T] |
| `MKT-INSPECTOR/adopt-and-push/warns-about-existing-wires` | Adopt lists the wire rates it will change first | BUILT | WORKING | **stale citation, unverified** | operator directive quoted at **stale citation, unverified** | `tests/test_c06c_topology_adopt_transaction.py::TestAdoptAppliesTheWholeTopology::test_the_change_is_disclosed_before_it_is_applied` | [T] |
| `MKT-INSPECTOR/adopt-and-push/undo-snapshot` | Adopt saves the old wiring to a file first | BUILT | WORKING | `main_window.py::_snapshot_wires_for_adopt` | **stale citation, unverified** | `tests/test_c06c_topology_adopt_transaction.py::TestSnapshotAndOrphans::test_the_snapshot_captures_the_pre_adopt_wires` | [T] |
| `MKT-INSPECTOR/adopt-and-push/adoption-announcement` | Bot Swarm is told an adoption happened | **ABSENT** | **BROKEN** — specified three times, emitted nowhere | no site; the handler emits only one wire topic per wire at **stale citation, unverified** | topology design `:184-186`, `:270-272`, `:317` | NO TEST | [M] |
| `MKT-INSPECTOR/adopt-and-push/push-into-simulator` | A proposal's shape can be pushed into a Simulator run | BUILT | WORKING | `market_inspector.py::current_topology_proposals:261-286`; wiring **stale citation, unverified** | `NO RECORDED SPEC` | `tests/test_nuclear_receives_topology_injections.py` | [T] |
| `MKT-INSPECTOR/adopt-and-push/push-into-paper` | The same push into a Paper run | **ABSENT** | **BROKEN** | no site — **stale citation, unverified** | issue #18 | NO TEST | [S] |
| `MKT-INSPECTOR/adopt-and-push/per-bot-view` | The Market Inspector page inside a single bot's window | BUILT | UNVERIFIED | `market_inspector.py::build_per_bot_view:451-557` | design doc `:313-320` | NO TEST | [S] |

#### `MKT-INSPECTOR/emitter-network`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MKT-INSPECTOR/emitter-network/any-pin-at-all` | The tab reports what it did | **ABSENT** | **BROKEN** — zero emit calls in all four source files | no site | issue #18; register **removed, see R-EMITTER** holds no Market Inspector subsystem | NO TEST | [M] |

---

## SUBSYSTEM 3 — BOT SWARM

**Verdict in one line.** The wiring half of this tab is the best-tested surface in the
application, but **both ways the tab tells you to wire bots by hand are dead in the view it
opens in**, and the Live layer — the one that would show your real bots — crashes on its
first call and has no caller at all.

### Bot Swarm — the eight framing features

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/bot-list` | The default list, one row per bot, with its money columns | BUILT | **BROKEN** — Inflow and Outflow show year-to-date totals, not wire flow | **NON-COMPLIANT** | `bot_visualizer.py:1236-1240`, **stale citation, unverified** | [S] |
| `BOT-SWARM/locust-grid` | The animated swarm picture | BUILT | WORKING | COMPLIANT | `bot_visualizer.py:1371-1378` | [T] |
| `BOT-SWARM/wires-by-hand` | Drag to connect, right-click to disconnect, set the rate | PARTIAL | **BROKEN** in the default view | **NON-COMPLIANT** | header prompt `bot_visualizer.py:1283-1285` | [T] |
| `BOT-SWARM/quick-connect` | Tick sources, tick destinations, Connect or Disconnect | BUILT | WORKING | COMPLIANT | `tests/test_c05_quick_routing_mass_ops.py:59` | [T] |
| `BOT-SWARM/wire-persistence` | Wires drawn last session come back, and a shortfall is reported | BUILT | WORKING | COMPLIANT | `bot_visualizer.py:1466-1472`, **stale citation, unverified** | [T] |
| `BOT-SWARM/live-swarm-layer` | Status rows for your real running bots | **ABSENT** | **BROKEN** — raises on its first call | **NON-COMPLIANT** | `NO RECORDED SPEC` | [M] |
| `BOT-SWARM/simulator-swarm-layer` | Status rows while a Simulator run is going | PARTIAL | **BROKEN** — rows never clear, Stop All misses them | **NON-COMPLIANT** | same plan, `:123-126` | [T] |
| `BOT-SWARM/paper-swarm-layer` | Status rows for Paper bots | BUILT | **BROKEN** — Start says LIVE and trades nothing | **NON-COMPLIANT** | **stale citation, unverified** | [M] |
| `BOT-SWARM/emitter-network` | The tab's tracked emitters | PARTIAL | WORKING | **NON-COMPLIANT** — the Live layer has none | **removed, see R-EMITTER** | [M] |

**Nine framing features. 6 BUILT, 2 PARTIAL, 1 ABSENT. 3 WORKING, 5 BROKEN. 6
NON-COMPLIANT.**

### Bot Swarm — the three findings at framing level

**1. Drag-to-connect and right-click-to-disconnect are dead in the default view.** The tab
header prompts "Drag between bots to connect" and "Right-click wire to disconnect". Both
work only through the wire canvas, and that canvas is hidden unless you switch to Grid. The
list overlay is click-through. **The default view is List.** A pin already records the
condition:
`tests/test_c04_wire_canvas_geometry.py::TestDefaultViewIsUsable::test_canvas_is_hidden_on_the_default_view`.

**2. Issue #25 reproduced by execution.** Calling the live-run registration on a
constructed tab raised an attribute error at **stale citation, unverified**. Control: the sim-run
registration on the *same instance* returned a working handle. The tab constructs
correctly; only the Live entry point is dead. Its container was removed in Session 26 by a
comment saying the shims "will be deleted in Session 27" — they were not. Zero callers
exist, which is why nobody has seen the crash.

**3. Inflow and Outflow show the wrong numbers.** The columns read the year-to-date folded
and scrummed totals, not wire flow. The code admits it in its own comment. The test that
covers them pins that the values differ per bot, not that they mean what the header says.

### `BOT-SWARM/emitter-network` — measured

**2 of the tree's 78 emitters belong to this tab**, both under the `swarm` token, both
emitted from `bot_visualizer.py`. One registers a Simulator row, one registers a Paper row.
**No third emitter exists for the Live layer**, and the register records no third
(**removed, see R-EMITTER**). Both existing emitters are good ones: each
reads the row back out of its layer's store rather than echoing its own argument, so a row
landing in the wrong layer is caught.

### Bot Swarm — functions beneath each framing feature

#### `BOT-SWARM/bot-list`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/bot-list/rows` | One row per bot | BUILT | WORKING | `bot_swarm_list.py::BotListView:119-240`; built `bot_visualizer.py:1411-1437` | `bot_visualizer.py:1236-1240` | `tests/test_bot_swarm_list.py::TestHeadlessRender::test_list_populates_rows_and_bot_ids` | [T] |
| `BOT-SWARM/bot-list/ticker-column` | The Ticker column | BUILT | WORKING | `bot_swarm_list.py:57`, `:67-69`, `:172` | `bot_swarm_list.py:57-69` | `tests/test_bot_swarm_list.py::TestSchema::test_column_layout` | [T] |
| `BOT-SWARM/bot-list/inflow-outflow-columns` | The Inflow and Outflow dollar columns | PARTIAL | **BROKEN** | `bot_visualizer.py::_refresh_bot_list_rows` | defect admitted at **stale citation, unverified** | `tests/test_c03_swarm_rows_and_privacy.py::TestInflowOutflowReachTheRows::test_per_bot_values_are_distinct` pins distinctness only | [S] |
| `BOT-SWARM/bot-list/percent-out-column` | How much profit a bot exports | BUILT | WORKING | `bot_swarm_list.py:60`, `:198`; computed **stale citation, unverified** | **stale citation, unverified** | `tests/test_bot_swarm_list.py::TestHeadlessRender::test_outflow_pct_color_ramp` | [T] |
| `BOT-SWARM/bot-list/lane-columns` | The eight lanes where wires are drawn | BUILT | WORKING | `bot_swarm_list.py:50-63`, `:74-116` | `bot_swarm_list.py:50` ("per operator: 8 connector nodes/row") | `tests/test_bot_swarm_list.py::TestLaneAllocator::test_overlapping_wires_get_separate_lanes` | [T] |
| `BOT-SWARM/bot-list/exchange-filter` | Narrow the swarm to one venue | BUILT | WORKING | `bot_visualizer.py:1322-1332`, **stale citation, unverified**, **stale citation, unverified** | `bot_visualizer.py:1322-1324` | `tests/test_c03_swarm_rows_and_privacy.py::TestExchangeIdComesFromStatus::test_the_filter_selects_on_it` | [T] |
| `BOT-SWARM/bot-list/view-switcher` | The List and Grid dropdown | BUILT | WORKING | `bot_visualizer.py:1343-1354`, **stale citation, unverified** | `bot_visualizer.py:1407-1410` | `tests/test_c04_wire_canvas_geometry.py::TestDefaultViewIsUsable::test_the_default_view_is_the_list` | [T] |
| `BOT-SWARM/bot-list/privacy-controls` | The identifier dot and the Privacy Mode button | BUILT | WORKING | `bot_visualizer.py:1294-1302`, **stale citation, unverified**, `:1313-1320`, **stale citation, unverified** | `bot_visualizer.py:1287-1312` (operator 2026-06-16) | `tests/test_c03_swarm_rows_and_privacy.py::TestPrivacyCoversTheListView::test_rows_carry_a_masked_symbol` | [T] |
| `BOT-SWARM/bot-list/empty-message` | "No active bots. Start bots to see visualizations." | BUILT | WORKING | `bot_visualizer.py:1402-1405`, restored **stale citation, unverified** | `NO RECORDED SPEC` | `tests/test_c10_swarm_clears_on_last_delete.py::TestUpdateBotsClearsOnEmpty::test_an_empty_list_removes_every_widget` | [T] |

#### `BOT-SWARM/locust-grid`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/locust-grid/the-picture` | The animated swarm | BUILT | WORKING | `bot_visualizer.py::BotNodeWidget:263-772`, grid `:1393-1405` | `bot_visualizer.py:1371-1378` | `tests/test_c10_swarm_clears_on_last_delete.py::TestUpdateBotsClearsOnEmpty::test_bots_render_first` | [T] |
| `BOT-SWARM/locust-grid/animation` | The movement of the locusts and the wire pulses | BUILT | UNVERIFIED | `bot_visualizer.py::_animate`, timer `:1725-1727` | `NO RECORDED SPEC` | `tests/test_bot_visualizer_b0_red.py::TestNoGlobalPseudoRandom::test_start_phase_stays_inside_its_declared_range` | [T] |
| `BOT-SWARM/locust-grid/theme-picker` | The Theme dropdown | BUILT | UNVERIFIED | `bot_visualizer.py:1334-1340`, **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |

#### `BOT-SWARM/wires-by-hand`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/wires-by-hand/drag-to-connect` | Drag from one bot to another | PARTIAL | **BROKEN** in the default view | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified**; canvas hidden `:1711-1717`; overlay click-through `bot_swarm_list.py:262` | `bot_visualizer.py:1283-1285` | `tests/test_c04_wire_canvas_geometry.py::TestDefaultViewIsUsable::test_canvas_is_hidden_on_the_default_view` | [T] |
| `BOT-SWARM/wires-by-hand/right-click-disconnect` | Right-click a wire to remove it | PARTIAL | **BROKEN** in the default view | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | `bot_visualizer.py:1284-1285` | `tests/test_c06b_wire_removal_confirmation.py::TestEveryRemovalIsGuarded::test_the_extractor_finds_the_removals` | [T] |
| `BOT-SWARM/wires-by-hand/rate-dialog` | The Configure Profit Wire box | BUILT | UNVERIFIED | `bot_visualizer.py::_show_wire_config` | `bot_visualizer.py:1283-1285` | NO TEST | [S] |
| `BOT-SWARM/wires-by-hand/removal-confirmation` | Every removal asks first, and defaults to No | BUILT | WORKING | `bot_visualizer.py::_confirm_wire_removal` | `tests/test_c06b_wire_removal_confirmation.py:57` | `tests/test_c06b_wire_removal_confirmation.py::TestTheDialogDefaultsToSafety::test_default_button_is_No` | [T] |
| `BOT-SWARM/wires-by-hand/opacity-slider` | The Wires opacity slider | BUILT | WORKING | `bot_visualizer.py:1356-1367`, **stale citation, unverified**; applied `bot_swarm_list.py:288-292` | `bot_visualizer.py:1241-1244` | NO TEST | [S] |

#### `BOT-SWARM/quick-connect`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/quick-connect/source-and-destination-lists` | The two tick lists | BUILT | WORKING | `bot_visualizer.py:813-823`, `:854-864`, `:900-957` | `bot_visualizer.py:788-811` (the operator's annotated geometry) | `tests/test_c05_scope_list_stability.py::TestCheckedSetsSurviveRebuild::test_checked_sources_survive` | [T] |
| `BOT-SWARM/quick-connect/rate-box` | The Rate box between them | BUILT | UNVERIFIED | `bot_visualizer.py:834-849` | tooltip `bot_visualizer.py:846-848` | NO TEST | [S] |
| `BOT-SWARM/quick-connect/connect-button` | Wire every ticked source to every ticked destination | BUILT | WORKING | `bot_visualizer.py:873-878`, `:1059-1135` | `tests/test_c05_quick_routing_mass_ops.py:59` | `tests/test_c05_quick_routing_mass_ops.py::TestMassOperationsAreConfirmed::test_no_mutation_runs_without_a_confirmation` | [T] |
| `BOT-SWARM/quick-connect/disconnect-buttons` | Disconnect the ticked pairs, or disconnect everything | BUILT | WORKING | `bot_visualizer.py:880-893`, `:1136-1194`, `:1195-1223`, **stale citation, unverified** | **stale citation, unverified** | `tests/test_c05_quick_routing_mass_ops.py::TestMassOperationsAreConfirmed::test_confirmation_defaults_to_No` | [T] |
| `BOT-SWARM/quick-connect/no-silent-refusals` | A refused action always says why | BUILT | WORKING | `bot_visualizer.py::QuickRoutingMatrix._reject:1011-1025` | `tests/test_c05_quick_routing_mass_ops.py:99` | `tests/test_c05_quick_routing_mass_ops.py::TestNoRejectionIsSilent::test_the_silence_detector_actually_detects_silence` | [T] |

#### `BOT-SWARM/wire-persistence`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/wire-persistence/restored-on-launch` | Wires come back when the app opens | BUILT | WORKING | `bot_visualizer.py::_hydrate_smart_wire_routes_from_disk`, called `:1473-1482` | `bot_visualizer.py:1466-1472` | `tests/test_bot_visualizer_h4_wire_hydration.py::TestTheReturnedCountIsTheEventsDelivered::test_the_real_bus_delivers_exactly_the_returned_count` | [T] |
| `BOT-SWARM/wire-persistence/shortfall-warning` | A warning when fewer wires are drawn than the file holds | BUILT | WORKING | `bot_visualizer.py::_report_wire_hydration_shortfall` | **stale citation, unverified** | `tests/test_bot_visualizer_h4_wire_hydration.py::TestTheShortfallIsStated::test_the_record_states_painted_of_total` | [T] |

#### `BOT-SWARM/live-swarm-layer`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/live-swarm-layer/status-rows` | A status row per running real-money bot | **ABSENT** | **BROKEN** — raises on the first call; zero callers | `bot_visualizer.py::register_live_run`; container removed at `:1371-1379` | **stale citation, unverified** | NO TEST | [M] |
| `BOT-SWARM/live-swarm-layer/registration-pin` | A tracked emitter for the live row, as Sim and Paper have | **ABSENT** | **BROKEN** | no site — the sim and paper registrations do emit, at `:2224` and `:2315` | register **removed, see R-EMITTER** records no third | NO TEST | [M] |

#### `BOT-SWARM/simulator-swarm-layer`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/simulator-swarm-layer/rows-appear` | Rows appear while a run is going | BUILT | WORKING | `bot_visualizer.py::register_sim_run:2177-2236`, `::update_sim_run:2238-2250`; driver `simulator_tab/nuclear_mode_panel.py:636` | `NO RECORDED SPEC` | `tests/test_swarm_registration_emitters.py::test_each_layer_registration_emits_once` | [T] |
| `BOT-SWARM/simulator-swarm-layer/rows-clear-on-stop` | Rows go away when the run stops | **ABSENT** | **BROKEN** — stop only restyles and writes "DONE" | `bot_visualizer.py::stop_sim_run`; the only remover is called from re-registration at `:2188` | same plan, `:125` (recorded as failing) | NO TEST | [S] |
| `BOT-SWARM/simulator-swarm-layer/stop-all-button` | The Stop All button | BUILT | **BROKEN** — misses the run-driven rows | `bot_visualizer.py:1573-1578` | same plan, `:126` (recorded as failing) | NO TEST | [S] |
| `BOT-SWARM/simulator-swarm-layer/add-sim-bot-row` | The "+ Add Sim Bot" button and its Run control | BUILT | **BROKEN** — starts no engine | `bot_visualizer.py::_create_sim_bot_row:1729-1849`, `::_toggle_run:1819-1842` | same plan, `:128` | NO TEST | [S] |
| `BOT-SWARM/simulator-swarm-layer/summary-bar` | Bots running, total profit, trades | PARTIAL | **BROKEN** — aggregate trades is a literal | `bot_visualizer.py::_update_sim_summary` | same plan, `:124` | NO TEST | [S] |

#### `BOT-SWARM/paper-swarm-layer`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/paper-swarm-layer/the-tab` | The Paper Swarm sub-tab | BUILT | WORKING | `bot_visualizer.py:1580-1674` | concept spec req3, req4 | NO TEST | [M] |
| `BOT-SWARM/paper-swarm-layer/add-a-paper-bot` | "+ Add Paper Bot" makes a row | BUILT | WORKING | `bot_visualizer.py::_create_paper_bot_row:1851-1976` | `NO RECORDED SPEC` | NO TEST | [M] |
| `BOT-SWARM/paper-swarm-layer/start-button-trades` | Pressing Start makes it trade | BUILT | **BROKEN** — says LIVE, attaches nothing | `bot_visualizer.py:1943-1966` | concept spec req2 | NO TEST | [M] |
| `BOT-SWARM/paper-swarm-layer/row-per-session` | A row per running paper session | BUILT | WORKING (no producer) | **stale citation, unverified** — zero production callers | concept spec req3 | `tests/test_swarm_registration_emitters.py::test_the_row_lands_in_the_layer_it_was_addressed_to` | [T] |
| `BOT-SWARM/paper-swarm-layer/summary-bar` | Total Capital, Net PnL, Active Bots | PARTIAL | **BROKEN** — net profit is a literal | `bot_visualizer.py::_update_paper_summary` | `NO RECORDED SPEC` | NO TEST | [M] |

#### `BOT-SWARM/emitter-network`

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BOT-SWARM/emitter-network/sim-registration-pin` | The Simulator-row emitter | BUILT | WORKING | `bot_visualizer.py:2224` | **removed, see R-EMITTER** | `tests/test_swarm_registration_emitters.py::test_each_layer_registration_emits_once` | [T] |
| `BOT-SWARM/emitter-network/paper-registration-pin` | The Paper-row emitter | BUILT | WORKING | `bot_visualizer.py` | **removed, see R-EMITTER** | `tests/test_swarm_registration_emitters.py::test_the_row_lands_in_the_layer_it_was_addressed_to` | [T] |
| `BOT-SWARM/emitter-network/pins-read-the-store-back` | Each emitter reads the row out of its layer rather than echoing its argument | BUILT | WORKING | `bot_visualizer.py:2222-2232`, rationale `:2211-2221` | R-PREDICTION | `tests/test_swarm_registration_emitters.py::test_a_misrouted_row_is_reported` | [M] |

### Market Inspector and Bot Swarm measurements, with controls

Every run used pytest, offscreen, cache writing disabled. No exit code was 139 or 127.

| Measurement | Control | Exit | Result |
| --- | --- | ---: | --- |
| Two Market Inspector test files | The same runner produced real failures in the three probes below, so a pass is a decision and not silence | 0 | 34 passed |
| Five topology test files | as above | 0 | 70 passed |
| Eleven Bot Swarm test files | as above | 0 | 116 passed |
| Three Nuclear topology-injection files | as above | 0 | 31 passed |
| Feed the freshness line a real 42-market result | The same function with the source set to cache returned a different, correct string | 1 | Reported "No data yet" |
| Call the live-run registration on a constructed tab | The sim-run registration on the same instance returned a working handle | 1 | Raised, reproducing issue #25 |
| Score a market with the two timeframes the fetcher supplies | The identical fixture with a third timeframe scored a higher rung | 1 | Capped at the low rung |

### What these two audits did not cover

Nothing was clicked. The locust drawing routine and the wire-canvas painting routine were
read for masking and colour only, not audited as drawings. The four topology detectors were
audited as the tab uses them, not as maths. The ticker source behind the proposals was
treated as a black box. Issue #63 was mapped, not investigated: fifteen exchanges are
declared and the fetcher does loop every connected one, but the other fourteen adapters
were not checked.

---

## SUBSYSTEM 4 — ASSET CHARTS

**Verdict in one line.** The chart draws, and the pair now follows a bot's symbol change —
that repair holds, measured. But **the chart computes its own indicator maths instead of
drawing the Voting Panel's, and three of the six indicators it draws are numerically
wrong**, which is the exact disagreement issue #55 warned about.

### Asset Charts — the six framing features

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `ASSET-CHARTS/the-chart` | The candle chart itself, with its title and volume | BUILT | WORKING | COMPLIANT | `main_window.py:1163-1165` | [T] |
| `ASSET-CHARTS/candle-feed` | Where the candles come from, and the source line | BUILT | UNVERIFIED | UNKNOWN | `main_window.py:1163-1165` ("Exchange, then CoinGecko, then Cache") | [S] |
| `ASSET-CHARTS/indicator-overlays` | The indicators drawn over and under the price | PARTIAL | **BROKEN** — three of six are wrong, three of the panel's six are missing | **NON-COMPLIANT** (R-INDICATOR) | issue #55; `src/trading/indicators/__init__.py:3-5` | [M] |
| `ASSET-CHARTS/bot-annotations` | Where this bot bought and sold, and the lines it will not cross | BUILT | UNVERIFIED | COMPLIANT | `main_window.py:1318-1322` (operator 2026-04-24, "where soldiers are on the battlefield") | [T] |
| `ASSET-CHARTS/chart-navigation` | One chart at a time, prev and next, crosshair, zoom and pan | PARTIAL | **BROKEN** — every bot gets its own panel; no prev/next row | **NON-COMPLIANT** | issue #55 | [M] |
| `ASSET-CHARTS/emitter-network` | The tab's tracked emitters | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [T] |

**Six framing features. 4 BUILT, 2 PARTIAL, 0 ABSENT. 3 WORKING, 2 BROKEN, 1 UNVERIFIED. 2
NON-COMPLIANT.**

### Asset Charts — the three findings at framing level

**1. Issue #46 is repaired, measured not assumed.** `tests/test_asset_chart_symbol_change.py`
— 9 passed, exit 0. The test reads the consumer, not the argument: it asks which pair the
fetcher was handed and which candles reached the widget. The repair moves five things
together on a symbol change — the stored symbol, the throttle, the header, the candles and
the trade markers — and the file's own controls refuse a vacuous pass. **Two things remain
open**: the stored exchange id does not move when the symbol moves
(`main_window.py:1243` written create-only, read at `:1587-1589`), and whether the
application permits a symbol change in place is still unestablished.

**2. Three of the chart's indicators disagree with the engine, and one is the issue #99
defect still alive.** Measured on a 200-bar seeded tape with both sides fed the same bars:

| Indicator | Verdict |
| --- | --- |
| Bollinger Bands | bit-identical to the engine |
| Ichimoku Tenkan and Kijun | bit-identical to the engine |
| MACD | **diverges** — at bar 11 the chart shows `101.903` where the engine has `102.061` |
| Stochastic RSI | **diverges** — the chart stores a bare raw stochastic; the published indicator has a smoothed `%K` and `%D`, and the chart draws neither |
| Vortex | **diverges** — a different epsilon, and no halt guard |

MACD is the same defect as issue #99, which is closed against the engine and was never
repaired in the chart: the chart seeds both moving averages at the first close and
back-fills every leading index, where the published formula seeds with a simple average and
has no value at all before its period. The chart therefore paints 25 manufactured values
and a signal line computed on them. **That breaks R-INDICATOR directly.**

**CONTROL for that measurement.** The comparator was proved able to answer both ways on the
same tape: it joined two equal numbers (the Bollinger middle band against the engine's
simple average, bit-identical) and separated two numbers differing in the last bit. The
divergences are findings about the code, not about the reader.

**3. Three of the Voting Panel's six indicators are not on the chart at all.** Issue #55
names Bollinger Bands, Vortex, MACD, ADX, KER and RSI. The first three are drawn. **ADX,
KER and RSI have no series and no toggle**, and neither do Supertrend and Z-Score, which
the panel also carries. And the chart exposes ten setter methods, **none of which accepts an
indicator value** — the only path is internal recomputation, which is what #55 asked to
remove.

### Asset Charts — functions beneath each framing feature

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ASSET-CHARTS/the-chart/a-chart-per-bot` | A chart appears when a bot starts, and goes when it stops | BUILT | WORKING | `main_window.py:1225-1249`, `:1444-1448` | `NO RECORDED SPEC` | `tests/test_asset_charts_emitters.py::test_panel_mounting_is_reported` | [T] |
| `ASSET-CHARTS/the-chart/extractor-bots-excluded` | Extractor bots get no chart | BUILT | WORKING | `main_window.py:1206-1209`, `:1219-1221`, `:1573-1580` | `main_window.py:1198-1204` | `tests/test_asset_charts_emitters.py::test_a_panel_the_fetch_loop_skips_forever_is_reported` | [T] |
| `ASSET-CHARTS/the-chart/price-in-the-title` | The pair, the live price and the bot state across the top | BUILT | UNVERIFIED | `main_window.py:1305-1306`; **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |
| `ASSET-CHARTS/the-chart/volume-strip` | The volume bars under the price | BUILT | UNVERIFIED | **stale citation, unverified**, default on at `:151` | `NO RECORDED SPEC` | NO TEST | [S] |
| `ASSET-CHARTS/candle-feed/pair-follows-symbol` | When a bot changes pair, its chart follows | BUILT | WORKING | `main_window.py:1287-1303` | issue #46; restated at `main_window.py:1268-1288` | `tests/test_asset_chart_symbol_change.py::test_the_fetch_target_follows_the_bots_symbol` | [M] |
| `ASSET-CHARTS/candle-feed/exchange-id-follows-symbol` | The exchange the chart fetches from follows too | **BROKEN** | **BROKEN** — written create-only, never moved | `main_window.py:1243`, read `:1587-1589` | issue #46 | NO TEST | [S] |
| `ASSET-CHARTS/candle-feed/source-order` | Exchange first, then CoinGecko, then the cache | BUILT | UNVERIFIED | `chart_data.py:133-181`, `:207-250` | `main_window.py:1163-1165` | NO TEST | [S] |
| `ASSET-CHARTS/candle-feed/source-and-error-line` | The grey line saying which source drew this, or what failed | BUILT | WORKING | `native_chart.py:252-258`, **stale citation, unverified**; `main_window.py:1657-1668` | **removed, see R-EMITTER** | `tests/test_asset_charts_emitters.py::test_a_panel_left_showing_candles_by_an_empty_fetch_is_reported` | [T] |
| `ASSET-CHARTS/candle-feed/timeframe-picker` | The timeframe box, and an immediate re-fetch | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**; `main_window.py:1505-1541` | **removed, see R-EMITTER** | `tests/test_asset_charts_emitters.py::test_timeframe_rearm_is_reported` | [T] |
| `ASSET-CHARTS/candle-feed/hidden-charts-keep-fetching` | Charts you are not looking at still call the exchange | BUILT | WORKING | `main_window.py:1571`, driven from **stale citation, unverified** and **stale citation, unverified** | issue #55 names this open and unowned: "the operator's call" | `tests/test_asset_charts_emitters.py::test_panel_freshness_is_reported` | [T] |
| `ASSET-CHARTS/candle-feed/nuclear-synthetic-feed` | Nuclear Mode can push made-up candles onto a chart | BUILT | UNVERIFIED | `main_window.py:1710-1770` | `main_window.py:1722-1723` | `tests/test_asset_charts_emitters.py::test_a_panel_the_fetch_loop_skips_forever_is_reported` | [T] |
| `ASSET-CHARTS/indicator-overlays/bollinger-bands` | Bollinger Bands over the candles | BUILT | WORKING | `native_chart.py:264-271`, toggle **stale citation, unverified** | R-INDICATOR | NO TEST | [M] |
| `ASSET-CHARTS/indicator-overlays/ichimoku-cloud` | The Ichimoku cloud | BUILT | WORKING | `native_chart.py:370-391`, shift `:1034-1048` | R-INDICATOR; engine `src/trading/indicators/ichimoku.py:60-66` | NO TEST | [M] |
| `ASSET-CHARTS/indicator-overlays/macd` | The MACD panel under the price | BUILT | **BROKEN** — manufactured leading values | `native_chart.py:272-288`, `:322-336` | R-INDICATOR; published seed at `src/trading/indicators/helpers.py:24-47`; issue #99 | NO TEST | [M] |
| `ASSET-CHARTS/indicator-overlays/vortex` | The Vortex panel | BUILT | **BROKEN** — different epsilon, no halt guard | `native_chart.py:297-321` | R-INDICATOR; engine `src/trading/indicators/vortex.py:57-113` | NO TEST | [M] |
| `ASSET-CHARTS/indicator-overlays/stochastic-rsi` | The Stochastic-RSI panel | PARTIAL | **BROKEN** — draws neither line the published indicator defines | `native_chart.py:337-368` | R-INDICATOR; engine `src/trading/indicators/stochastic_rsi.py:35-110` | NO TEST | [M] |
| `ASSET-CHARTS/indicator-overlays/missing-voting-indicators` | ADX, RSI, KER, Supertrend and Z-Score on the chart | **ABSENT** | **BROKEN** | no site; the panel's list is at `indicator_panel.py:486-499` | issue #55 ("all indicators from the Indicator Voting Panel loaded and properly visualized") | NO TEST | [M] |
| `ASSET-CHARTS/indicator-overlays/renders-what-the-panel-computes` | The chart draws the panel's numbers rather than its own | **ABSENT** | **BROKEN** — ten setters, none takes an indicator value | `native_chart.py:260-391` | issue #55 section 3 ("or the two will disagree on screen") | NO TEST | [M] |
| `ASSET-CHARTS/indicator-overlays/slingshot-and-bullseye` | The Sling and BBull buttons | PARTIAL | **BROKEN** — placeholder paint | **stale citation, unverified**, `:1140`, `:1201` | **stale citation, unverified** ("final visual specs are still queued for Wave 2") | NO TEST | [S] |
| `ASSET-CHARTS/bot-annotations/trade-markers` | Where this bot bought and sold | BUILT | WORKING | `main_window.py:1325-1340`; `native_chart.py:397-432` | `main_window.py:1318-1322` | `tests/test_asset_chart_symbol_change.py::test_the_old_pairs_trade_markers_do_not_survive_the_change` | [T] |
| `ASSET-CHARTS/bot-annotations/tranche-floor-lines` | Lines showing where the bot will not fold below | BUILT | UNVERIFIED | `main_window.py:1417-1440`; `native_chart.py:433-443` | `main_window.py:1418` | NO TEST | [S] |
| `ASSET-CHARTS/bot-annotations/target-balance-lines` | The anchor line and the ceiling line | BUILT | UNVERIFIED | `main_window.py:1385-1394`; `native_chart.py:452-464` | issue #106; reasoning `main_window.py:1359-1384` ("the drawn line must be the enforced line") | NO TEST | [S] |
| `ASSET-CHARTS/bot-annotations/fire-armed-glow` | The glow when auto-fire would fire right now | BUILT | UNVERIFIED | `main_window.py:1400-1410`; `native_chart.py:465-480` | `main_window.py:1396-1399` (same data the Fire button reads) | NO TEST | [S] |
| `ASSET-CHARTS/chart-navigation/one-chart-at-a-time` | The tab shows one chart, not a stack | **ABSENT** | **BROKEN** — three bots produced three mounted panels | `main_window.py:1176-1187`, `:1225-1249` | issue #55 ("Must now display only one chart at a time") | [M] |
| `ASSET-CHARTS/chart-navigation/prev-next-with-the-ticker` | Blue prev and next arrows with the pair between them | **ABSENT** | **BROKEN** — zero buttons anywhere on the tab | no site; the pattern to reuse is at `bot_live_settings.py:540-566` | issue #55 | NO TEST | [M] |
| `ASSET-CHARTS/chart-navigation/crosshair-zoom-pan` | Crosshair readout, wheel zoom, drag pan, double-click reset | BUILT | UNVERIFIED | `native_chart.py:530-577`, `:578-602`, `:603-609`, `:610-647`, `:484-529` | `NO RECORDED SPEC` | NO TEST | [S] |
| `ASSET-CHARTS/emitter-network/chart-pins` | The five chart emitters | BUILT | WORKING | 5 pins emitted from `main_window.py` | **removed, see R-EMITTER** | `tests/test_asset_charts_emitters.py` | [T] |

**`ASSET-CHARTS/emitter-network` measured: 5 of the tree's 78 emitters, all under the
`charts` token, all emitted from `main_window.py`.**

---

## SUBSYSTEM 5 — HISTORY

**Verdict in one line.** The trade list comes from the venue itself, which is exactly right,
and it is the second-best-tested tab in the application — but **the "Cost USD" column is not
the venue's number and is not necessarily dollars**, and that breaks the rule the operator
states most firmly.

### History — the six framing features

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `HISTORY/trade-list` | The list of executed trades, straight from the exchange | BUILT | WORKING | **NON-COMPLIANT** — one money column is recomputed and mislabelled | R-EXCHANGE; `history_tab.py:27` | [T] |
| `HISTORY/filters` | Date range, exchange, symbol, buy or sell, Apply and Reset | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [T] |
| `HISTORY/trade-explanations` | The grade, the gate lights, the vote, and the hover text | BUILT | WORKING | COMPLIANT | `history_tab.py:8-14` | [T] |
| `HISTORY/paging-and-export` | Prev and Next, the page counter, and Export CSV | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [T] |
| `HISTORY/feeds-the-simulator` | A refresh hands the Simulator its year-to-date ticks | BUILT | UNVERIFIED | COMPLIANT | `history_tab.py:15-18`; **stale citation, unverified** | [T] |
| `HISTORY/emitter-network` | The tab's tracked emitters | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [T] |

**Six framing features. 6 BUILT, 0 PARTIAL, 0 ABSENT. 5 WORKING, 0 BROKEN, 1 UNVERIFIED. 1
NON-COMPLIANT.**

### History — the finding at framing level

**The "Cost USD" column is not the venue's cost and is not necessarily dollars.**
`history_helpers.py:146` discards the venue's own cost field and writes amount multiplied by
price. `history_tab.py:306` then labels that column **"Cost USD"** and `:779-782` prefixes it
with a dollar sign. For any pair not quoted in dollars, the operator is shown a
quote-currency figure under a dollar heading. The same recomputed number is summed into the
buy and sell totals on the summary line (`:944-951`) and written to the export file as a
dollar column (`:1251`). This is the rule the operator states most plainly — "ANYTHING that
induces disagreement with exchange values is broken" — and it is a display that disagrees.

### History — functions beneath each framing feature

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `HISTORY/trade-list/from-the-exchange` | The list is the venue's own fill record | BUILT | WORKING | `history_helpers.py:236-296`, `:202-215` | R-EXCHANGE; `history_tab.py:27` | `tests/test_history_helpers.py::test_paginated_fetch_recovers_full_history` | [T] |
| `HISTORY/trade-list/the-table` | The thirteen-column list | BUILT | WORKING | `history_tab.py:294-316`, `:756-800` | **removed, see R-EMITTER** | `tests/test_history_tab_emitters.py::test_the_table_draws_a_full_page_and_a_short_last_page` | [T] |
| `HISTORY/trade-list/cost-usd-column` | The money column and the dollar sign on Price | BUILT | **BROKEN** | `history_helpers.py:146`, header `history_tab.py:306`, render `:779-782` | R-EXCHANGE | NO TEST | [S] |
| `HISTORY/trade-list/summary-line` | "N of M trades, buys, sells, fetched N seconds ago" | BUILT | **BROKEN** — sums the same recomputed number under a dollar sign | `history_tab.py` | R-EXCHANGE | NO TEST | [S] |
| `HISTORY/trade-list/which-bot-made-it` | The Bot column naming the bot behind each fill | BUILT | WORKING | `history_tab.py:92-148`; `history_helpers.py:299-318` | `NO RECORDED SPEC` | NO TEST | [S] |
| `HISTORY/trade-list/only-live-bots` | Simulator fills never appear here | PARTIAL | WORKING | `history_helpers.py:159-166`, `:168-235` | `NO RECORDED SPEC` | NO TEST | [S] |
| `HISTORY/trade-list/busy-bar-and-timeout` | The spinner, and the sixty-second give-up message | BUILT | UNVERIFIED | `history_tab.py:356-360`, `:392-396`, `:505-513` | `NO RECORDED SPEC` | NO TEST | [S] |
| `HISTORY/filters/refresh-button` | Refresh pulls fresh history from every active exchange | BUILT | WORKING | `history_tab.py:277-281`, `:190-193`, `:371-420` | **removed, see R-EMITTER** | `tests/test_history_tab_emitters.py::test_the_fetch_pin_reports_the_rows_that_landed` | [T] |
| `HISTORY/filters/refreshes-on-tab-open` | Opening History pulls history without pressing anything | BUILT | UNVERIFIED | **stale citation, unverified** | `history_tab.py:21`; wiring note **stale citation, unverified** | NO TEST | [S] |
| `HISTORY/filters/date-range` | From and To, defaulting to the launch date | BUILT | UNVERIFIED | `history_tab.py:225-243`, filter `:639-646` | `history_tab.py:8` | `tests/test_history_helpers.py::test_default_start_date_is_2026_04_01` | [T] |
| `HISTORY/filters/exchange-symbol-and-side` | Show one exchange, one pair, or only buys or sells | BUILT | WORKING | `history_tab.py:245-262`, `:650-655` | **removed, see R-EMITTER** | `tests/test_history_tab_emitters.py::test_every_retained_row_matches_the_selected_filters` | [T] |
| `HISTORY/filters/apply-button` | Apply narrows the list, and fetches first if nothing is loaded | BUILT | WORKING | `history_tab.py:618-641` | `history_tab.py:619-632` (operator 2026-05-31: Apply produced "0 of 0 trades" forever) | `tests/test_history_tab_emitters.py::test_every_retained_row_matches_the_selected_filters` | [T] |
| `HISTORY/filters/reset-button` | Reset puts every filter back | BUILT | UNVERIFIED | `history_tab.py:727-737` | `NO RECORDED SPEC` | NO TEST | [S] |
| `HISTORY/trade-explanations/grade-column` | The A-to-F letter on each trade | BUILT | WORKING | `history_tab.py`, render `:792-810` | `history_tab.py:791-795` (read-only, "never feeds back into trading decisions") | `tests/test_history_grade_ordering.py::TestGradeUsesTheRealTimeAxis` | [T] |
| `HISTORY/trade-explanations/gates-column` | What was armed or blocked at trade time | BUILT | UNVERIFIED | `history_tab.py`; `history_helpers.py:363-392` | `history_tab.py` (operator 2026-08-08: it "should align with gate row indicators found in the Simulator") | `tests/test_history_helpers.py::test_gate_cell_text_compact` | [T] |
| `HISTORY/trade-explanations/voting-column` | What the Voting Panel said at the moment of the trade | BUILT | UNVERIFIED | `history_tab.py`; `history_helpers.py:394-423` | `history_tab.py:10-14` | `tests/test_history_helpers.py::test_voting_cell_text_compact` | [T] |
| `HISTORY/trade-explanations/hover-text` | Hovering a cell explains the blockers, the vote or the letter | BUILT | WORKING | `history_tab.py:809`, `:311-329`; builders `history_helpers.py:529-583` | `history_tab.py:9-14`. R-TOOLTIP (issue #53) not measured here | `tests/test_history_helpers.py::test_gate_tooltip_lists_scrum_and_fold_blockers` | [T] |
| `HISTORY/paging-and-export/paging` | Prev, Next and the page counter, 100 trades a page | BUILT | WORKING | `history_tab.py:335-352`, `:739-748` | **removed, see R-EMITTER** | `tests/test_history_tab_emitters.py::test_a_page_beyond_the_last_is_clamped_and_still_agrees` | [T] |
| `HISTORY/paging-and-export/export-csv` | Export the filtered view to a file | BUILT | WORKING | `history_tab.py` | **removed, see R-EMITTER** | `tests/test_history_tab_emitters.py::test_the_csv_holds_every_row_that_was_exported` | [T] |
| `HISTORY/feeds-the-simulator/hands-over-ytd` | A refresh hands the Simulator its year-to-date ticks | BUILT | UNVERIFIED | `history_tab.py:167`, `:495-502`; wiring **stale citation, unverified** | `history_tab.py:15-18`; operator report at **stale citation, unverified** | `tests/test_history_helpers.py::test_history_tab_has_history_refreshed_signal` | [T] |
| `HISTORY/emitter-network/history-pins` | The seven History emitters | BUILT | WORKING | 7 pins across `history_tab.py` and `src/exchange/ccxt_connector.py` | **removed, see R-EMITTER** | `tests/test_history_tab_emitters.py` | [T] |

**`HISTORY/emitter-network` measured: 7 of the tree's 78 emitters, under the `history`
token. This is the second-largest emitter set of any tab.**

---

## SUBSYSTEM 7 — CONSOLE

**Verdict in one line.** The best-behaved subsystem in the application — every framing
feature is built, none is broken, and **zero rules are broken**. Its weakness is that ten of
its functions have no recorded spec, so most of what it does was never asked for in writing.

### Console — the five framing features

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `CONSOLE/system-message-tail` | The top pane, where every system message scrolls past | BUILT | WORKING | COMPLIANT | **stale citation, unverified** | [T] |
| `CONSOLE/signals-pane` | The lower pane, showing each emitter's expected and actual | BUILT | WORKING | COMPLIANT | R-EMITTER; operator directive at **stale citation, unverified** | [T] |
| `CONSOLE/pause` | One Pause press quiets both panes so an error can be read | BUILT | WORKING | COMPLIANT | operator directive at **stale citation, unverified**; issue #49 | [T] |
| `CONSOLE/console-health-report` | The Console reports on itself every five seconds | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [T] |
| `CONSOLE/emitter-network` | The tab's tracked emitters | BUILT | WORKING | COMPLIANT | **removed, see R-EMITTER** | [T] |

**Five framing features. 5 BUILT, 0 PARTIAL, 0 ABSENT. 5 WORKING, 0 BROKEN. 0
NON-COMPLIANT.**

### Console — the finding at framing level

**The Console tails two different things, and only one of them is tracked.** The top pane is
a raw logging tail attached to the root logger at debug level
(**stale citation, unverified**) — untracked and undeclared. The lower pane is the tracked
emitter network, read through the signal sink (**stale citation, unverified**). That is a
correct design and worth recording plainly, because the question "does the Console show the
emitter network or a separate log stream?" has one answer per pane. **Issues #48 and #49 are
both repaired**, proved by 38 tests at exit 0: the gap marker is drawn above the records it
describes, and the Pause flag is now assigned exactly once in the whole tree.

### Console — functions beneath each framing feature

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CONSOLE/system-message-tail/the-pane` | Every system message scrolls past | BUILT | WORKING | **stale citation, unverified**, attached **stale citation, unverified** | **stale citation, unverified** | `tests/test_console_tab_emitters.py::test_a_resume_delivers_every_buffered_line` | [T] |
| `CONSOLE/system-message-tail/colour-by-severity` | Warnings amber, errors red, debug grey | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |
| `CONSOLE/system-message-tail/indicator-highlight` | Indicator-panel lines stand out | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |
| `CONSOLE/system-message-tail/scrollback-limit` | The pane keeps the last 2,000 lines | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified** | **removed, see R-EMITTER** | `tests/test_console_tab_emitters.py::test_a_resume_the_pane_cap_eats_is_reported` | [T] |
| `CONSOLE/system-message-tail/follows-the-newest-line` | It scrolls with the newest line unless you scrolled up | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |
| `CONSOLE/system-message-tail/clear-button` | Clear empties the pane | BUILT | UNVERIFIED | **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |
| `CONSOLE/system-message-tail/safe-from-worker-threads` | Messages from background threads do not crash the window | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified** | **stale citation, unverified** (the crash record) | NO TEST | [S] |
| `CONSOLE/system-message-tail/search-the-log` | Find a word in the console | **ABSENT** | UNVERIFIED | no site | `NO RECORDED SPEC` | NO TEST | [M] |
| `CONSOLE/system-message-tail/filter-by-severity` | Show only warnings and errors | **ABSENT** | UNVERIFIED | no site | `NO RECORDED SPEC` | NO TEST | [M] |
| `CONSOLE/system-message-tail/copy-or-save` | Copy a line out, or save the pane to a file | **ABSENT** | UNVERIFIED | no site | `NO RECORDED SPEC` | NO TEST | [M] |
| `CONSOLE/signals-pane/the-pane` | Name, expected and actual, for each emitter | BUILT | WORKING | **stale citation, unverified**, drain **stale citation, unverified**, timer **stale citation, unverified** | R-EMITTER; operator directive **stale citation, unverified** | `tests/test_console_tab_emitters.py::test_records_rendered_is_reported` | [T] |
| `CONSOLE/signals-pane/pass-fail-marks` | Each line carries a pass mark, a fail mark or a dash | BUILT | WORKING | **stale citation, unverified** | R-PREDICTION at `src/core/signal_contract.py:1146` (`emit`, which takes both `actual` and `expected`) | `tests/test_console_tab_emitters.py::test_the_marker_cannot_be_misread_as_a_record` | [T] |
| `CONSOLE/signals-pane/gap-marker` | A visible notice when a burst was stepped over | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified** | issue #48, option 2 ("keep the skip and report it") | `tests/test_console_tab_emitters.py::test_a_live_burst_draws_the_gap_it_stepped_over` | [T] |
| `CONSOLE/signals-pane/newest-200-per-tick` | Under a burst only the newest 200 are drawn | BUILT | WORKING | **stale citation, unverified** | issue #48 ("the fix is not 'render everything'") | `tests/test_console_tab_emitters.py::test_records_the_slice_threw_away_after_the_watermark_moved_are_reported` | [T] |
| `CONSOLE/signals-pane/kept-on-disk` | Nothing is lost; the signals are on disk as well | BUILT | UNVERIFIED | `src/core/signal_contract.py` sink; stated at **stale citation, unverified** | R-EMITTER | NO TEST | [S] |
| `CONSOLE/signals-pane/drag-the-divider` | The splitter between the two panes | BUILT | UNVERIFIED | **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |
| `CONSOLE/pause/pause-button` | Pause stops the console so an error can be read | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | operator directive **stale citation, unverified** (2026-04-28) | `tests/test_console_tab_emitters.py::test_a_pause_quiets_the_signals_pane_as_well_as_the_log` | [T] |
| `CONSOLE/pause/quiets-both-panes` | One press quiets the log pane and the signals pane | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**, gate **stale citation, unverified** | issue #49; docstring **stale citation, unverified** | `tests/test_console_tab_emitters.py::test_the_flag_the_drain_reads_is_assigned_exactly_once_in_the_tree` | [T] |
| `CONSOLE/pause/buffered-count` | "PAUSED, N buffered" ticking beside the button | BUILT | UNVERIFIED | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [S] |
| `CONSOLE/pause/buffer-cap` | A long pause holds 5,000 lines, then says how many it dropped | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified**, **stale citation, unverified** | **removed, see R-EMITTER** | `tests/test_console_tab_emitters.py::test_the_buffer_cap_adds_the_notice_line_to_what_the_resume_owes` | [T] |
| `CONSOLE/pause/resume-delivers-the-backlog` | Un-pausing pours the held lines back | BUILT | WORKING | **stale citation, unverified** | **removed, see R-EMITTER** | `tests/test_console_tab_emitters.py::test_a_resume_delivers_every_buffered_line` | [T] |
| `CONSOLE/console-health-report/self-report` | The Console reports on itself every five seconds | BUILT | WORKING | **stale citation, unverified**, **stale citation, unverified** | **removed, see R-EMITTER** | `tests/test_console_tab_emitters.py::test_a_drain_that_stopped_is_reported` | [T] |
| `CONSOLE/emitter-network/console-pins` | The five Console emitters | BUILT | WORKING | 5 pins emitted from `main_window.py` | **removed, see R-EMITTER** | `tests/test_console_tab_emitters.py` — 38 passed, exit 0 | [T] |

**`CONSOLE/emitter-network` measured: 5 of the tree's 78 emitters, under the `console`
token.**

### Asset Charts, History and Console measurements, with controls

Every run used pytest, offscreen. No exit code was 139 or 127.

| Measurement | Exit | Result |
| --- | ---: | --- |
| Issue #46 is repaired | 0 | 9 passed |
| Asset Charts emitters | 0 | 15 passed |
| History emitters | 0 | 23 passed |
| History helpers | 0 | 15 passed |
| History grading | 0 | 12 passed |
| Console emitters (issues #48 and #49) | 0 | 38 passed |
| Tab order | 0 | 4 passed |
| Engine indicator digests | 0 | 40 passed |
| One indicator per module | 0 | 131 passed |
| **Chart maths against engine maths** | **1** | **5 failed, 4 passed** |
| **The tab against issue #55** | **1** | **4 failed, 1 passed** |

**CONTROL for the green runs.** The instrument is two-sided within the same session: the
last two probes ran through the identical harness and produced failures, so the green
results above are not a reader stuck on green. The symbol-change file carries its own
controls — one refuses a reset that did not happen, another refuses a panel that stopped
fetching — so a vacuous pass is excluded.

**CONTROL for the chart-maths probe.** One control compares the chart's Bollinger middle
band against the engine's simple average and requires them bit-identical; another separates
two values differing in the last bit. The comparator can answer both ways on this tape.

**CONTROL for the issue #55 probe.** One control walked the tab and found three timeframe
boxes. A walk that found nothing would have been a broken reader, not an empty tab.

### What these three audits did not cover

Nothing was launched and nothing was clicked. No network call was made, so the CoinGecko
fallback and the venue trade fetch were never exercised against a real venue. No painting
was verified: the chart's paint routine is 1,080 lines, and every "drawn" claim rests on the
paint branch existing with a non-empty data series behind it. The Ichimoku backward
displacement is stored but the paint was not confirmed to apply it. Tooltip compliance
(issue #53) was not measured on any of the three tabs.

**One condition to record.** The live-tree guard reported DEGRADED on every run, because a
live application was running and writing its own logs. Nothing in this audit wrote to the
live tree, and the redirects were confirmed installed, but the guard could not attribute the
writes and did not fail them. Re-run with the application closed for that proof.

---

## SUBSYSTEM 6 — SIMULATOR

**Verdict in one line.** Five of the operator's eight framing features work. **Backtest
Mode does not exist below its label**, the two playback windows are built but break the
restructure he specified, and the emitter network holds **22 of the 40 emitters** his spec
names.

### Simulator — the eight framing features

The operator named these eight himself. They are the subsystem.

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `SIM/bot-list` | Bot List | BUILT | WORKING | **NON-COMPLIANT** — the table it replaces was never removed, so both are on screen | issue #59 zone 1 | [M] |
| `SIM/ta-voting-panel` | TA Indicator Voting Panel | BUILT | WORKING | **NON-COMPLIANT** — fed 300 candles where Live gets 100 | `simulator_tab.py:363-375`; issue #119 | [M] |
| `SIM/vwap-playback` | VWAP PlayBack Window | BUILT | WORKING | **NON-COMPLIANT** — no thirty-frame playback, no prev/next ticker row | issue #59 zone 2 | [M] |
| `SIM/tablet-candle-playback` | Stone Tablet Candle PlayBack Window | BUILT | WORKING | **NON-COMPLIANT** — shares one widget with the VWAP window; no thirty-frame playback | issue #59 zone 3 | [M] |
| `SIM/validation-mode` | Validation Mode | BUILT | WORKING | **NON-COMPLIANT** — 22 seam violations sit inside it | `simulator_tab.py:155-180`; issues #117-#127 | [M] |
| `SIM/backtest-mode` | Backtest Mode | **ABSENT** | **BROKEN** | **NON-COMPLIANT** | `simulator_tab.py:163-171` | [M] |
| `SIM/nuclear-mode` | Nuclear Mode | BUILT | WORKING | COMPLIANT | `NO RECORDED SPEC` | [M] |
| `SIM/emitter-network` | Emitter Network — 40 emitters, standardized build, initial implementation | PARTIAL | WORKING | **NON-COMPLIANT** — 22 of 40 | **removed, see R-EMITTER** | [M] |

**Eight framing features. 6 BUILT, 1 PARTIAL, 1 ABSENT. 6 WORKING, 1 BROKEN. 7
NON-COMPLIANT.**

### Simulator — the two findings at framing level

**1. Backtest Mode is a label with nothing behind it.** The mode dropdown offers
Validation, Looping Back Test and Nuclear. Choosing a mode hands it to a method on the
panel, behind a guard that first checks the method exists (`simulator_tab.py:807-809`).
**That method is defined nowhere in the source tree or the test tree.** The guard is
therefore always false and the call never happens. Validation and Backtest route to the
same page and run identical code. Only the grey hint line differs. Measured by exhaustive
tree search; control, the same search does find the methods next to it.

**2. The emitter network is 22 where the spec says 40.** Measured below.

### `SIM/emitter-network` — measured against the operator's 40

The project's own checker reports the whole tree: **78 pins in source, 78 registry rows,
"instrument controls OK", exit 0**. My independent count of the same tree also returns 78,
and it agrees with the checker exactly — that agreement is the control. My first pass
returned 77; rather than report it, I found the one pin declared outside the main contract
file and reconciled to 78. A count that cannot reconcile with the project's own instrument
is not evidence.

Of those 78, the Simulator owns **22**. Both of its tokens live entirely inside
`src/gui/simulator_tab/`, which is what makes them the Simulator's and not another
subsystem's.

| Token | Pins | Where they live |
| --- | ---: | --- |
| `sim` | 14 | `simulator_tab.py`, `fleet/fleet_replay_panel.py`, `fleet/fleet_replay_controller.py` |
| `fleet` | 8 | `fleet/bot_state_loader.py`, `fleet/fleet_replay_controller.py` |
| **Simulator total** | **22** | |

**Against the operator's spec of 40, the Simulator is 18 short.** Two readings of that
number are possible and both should be said plainly.

*The Simulator's own share is 22 of a specified 40.* That is the reading his framing
feature invites, and on it the network is a bit over half built.

*The number 40 may have meant the whole tree.* **removed, see R-EMITTER** is titled
"Item 10 — Simulator Emitter Network" and its first row records "10.0 COUNT — shipped, 40
emitters, counter proven four ways". At the time that was written, 40 was the count of
**every** emitter in the platform, not the Simulator's share. On that reading the network
did not fall short — **it grew to 78, nearly double the number in the spec, and no
document records the decision to grow it.**

Either way there is a finding, and they are opposite findings, so the operator should
settle which 40 he meant. **An emitter network that drifted from its specification in an
unrecorded direction is the same class of problem as a subsystem described by 73
features.** Item 10 is recorded as OPEN: sub-item 10.3 phase 2 is not done, 10.4 is not
done, and 10.5 has not started, with "six tabs have zero emitters" noted against it.

"Standardized build" and "initial implementation" are spec language, and both refer to real
documents. The naming convention, the five-field pin name and the register of every ID are
at **removed, see R-EMITTER**; the work order, the twelve-row spec and the unit
sequence are at **removed, see R-EMITTER**.

### Simulator — functions beneath each framing feature

This is the level a work brief is written from. The operator does not need to read it.

#### `SIM/bot-list` — Bot List

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/bot-list/trading-tab-clone` | It is the Trading tab's own table, not a copy | BUILT | WORKING | `simulator_tab.py::mount_bot_status_table:624`, host `:222-236`, called `:311` | issue #59 zone 1 | `tests/test_sim_bot_area.py::TestItIsTheTradingTabsTable::test_it_is_the_very_same_class_main_window_uses` | [M] |
| `SIM/bot-list/legacy-fleet-table` | The old three-column fleet table the clone replaces | BUILT | **BROKEN** — never removed, both are on screen | `fleet_replay_panel.py:122`, built `:294-307` | issue #59 zone 1 | NO TEST | [M] |
| `SIM/bot-list/active-bot-dropdown` | The "Active simulator bots" dropdown | BUILT | WORKING | `simulator_tab.py:229-236`, `::refresh_active_bot_roster:725` | `simulator_tab.py:216-221` | `tests/test_sim_bot_area.py::TestTheActiveBotDropdown::test_it_and_the_table_are_built_from_one_source` | [M] |
| `SIM/bot-list/bot-detail-dialog` | Clicking a row opens that bot's settings | BUILT | UNVERIFIED | `simulator_tab.py::_on_sim_bot_detail:676` | issue #59 zone 1 | NO TEST | [S] |
| `SIM/bot-list/live-bots-unreachable` | A Simulator screen can never open a live bot | BUILT | WORKING | `simulator_tab.py:676-694` | `simulator_tab.py:679-682` | NO TEST | [S] |
| `SIM/bot-list/fire-button-disabled` | Fire is greyed out on every Simulator row | BUILT | WORKING | `simulator_tab.py::_disable_fire_buttons:700` | `simulator_tab.py:653-663` | NO TEST | [S] |
| `SIM/bot-list/load-live-fleet` | The "Load live fleet" button | BUILT | WORKING | `fleet_replay_panel.py:231-239`, `::_on_load_clicked:425` | `NO RECORDED SPEC` | `tests/test_feature1_fleet_load_emitters.py` | [M] |
| `SIM/bot-list/fleet-is-bot-state-only` | Bots come only from the saved bot state, never invented | BUILT | WORKING | `fleet/bot_state_loader.py`; fallback `simulator_tab.py` | `simulator_tab.py:851-864` (operator: "claims its the live one but it does not match. Its fake.") | `tests/test_build_sim_bot_id_remap.py::TestTheIdIsThePersistedOne::test_every_sim_bot_carries_its_persisted_id` | [M] |
| `SIM/bot-list/smart-wires-import` | The fleet's Smart Wires load with the bots | BUILT | WORKING | `fleet_replay_panel.py:151-153` | `nuclear_mode_panel.py:375-378` | `tests/test_build_sim_smart_wires.py::TestTheWiresActuallyRoute::test_a_source_bot_resolves_its_outgoing_wire` | [M] |
| `SIM/bot-list/spawn-drift-report` | The log says what changed since the last Load | BUILT | WORKING | `fleet_replay_panel.py:616-640` | `fleet_replay_panel.py:600-604` | `tests/test_sim_spawn_drift.py::test_changed_live_source_is_detected` | [M] |
| `SIM/bot-list/simulator-bot-state-file` | A simulator bot-state file beside the live one | BUILT | WORKING | `fleet/simulator_bot_state.py::save_sim_state`; call `fleet_replay_panel.py:632` | `fleet_replay_panel.py:600-607` | `tests/test_sim_spawn_drift.py::test_identical_reload_reports_no_drift` | [M] |
| `SIM/bot-list/per-symbol-trade-counts` | The "Sim Trades" number on each row | BUILT | WORKING | **stale citation, unverified** | **stale citation, unverified** | `tests/test_the_simulator_records_the_fill_it_filled.py::TestTheFillReachesTheProgressCounters::test_per_symbol_trade_count_names_every_symbol_that_filled` | [M] |
| `SIM/bot-list/stat-strip` | The ten-field stat strip across the top | BUILT | WORKING | `sim_stat_strip.py:54-103`; feed `fleet_replay_panel.py:1709-1812` | `sim_stat_strip.py:14-17` | `tests/test_sim_visual_decoupling.py::test_stat_fields_cover_every_strip_slot` | [M] |

#### `SIM/ta-voting-panel` — TA Indicator Voting Panel

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/ta-voting-panel/is-the-trading-tabs-panel` | It is the Trading tab's panel, not a copy | BUILT | WORKING | `simulator_tab.py:376` mounts `indicator_panel.py::IndicatorVotingPanel` | `simulator_tab.py:363-375` | NO TEST | [S] |
| `SIM/ta-voting-panel/candle-count-matches-live` | It sees the same history Live sees | **BROKEN** | **BROKEN** — 300 candles against Live's 100 | `indicator_panel.py:898`, `:1406` | issue #119 (seam H1) | NO TEST | [S] |
| `SIM/ta-voting-panel/gate-lights` | Ten labelled gate lights per bot | BUILT | WORKING | `fleet/sim_visuals.py:360`, orders `:168-199`, paint `:498-552` | `NO RECORDED SPEC` | `tests/test_sim_chart_marker_anchoring.py::test_clear_gates_still_clears_the_blockers` | [M] |
| `SIM/ta-voting-panel/gate-status-pane` | The Gate Status pane, bottom right | BUILT | WORKING | `simulator_tab.py:596-618`; owner `fleet_replay_panel.py:129-146` | `fleet_replay_panel.py:117-121` | `tests/test_sim_chart_marker_anchoring.py::test_ls_led_is_cleared` | [M] |
| `SIM/ta-voting-panel/expand-button` | The Expand button on each half of the panel | BUILT | WORKING | `simulator_tab.py:426-437`; `sim_visuals.py:43` | `NO RECORDED SPEC` | `tests/test_sim_visuals_expand_reentrancy.py` | [M] |

#### `SIM/vwap-playback` — VWAP PlayBack Window

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/vwap-playback/price-against-vwap` | Historical price drawn against position VWAP | BUILT | WORKING | `fleet/sim_visuals.py:555` | issue #59 zone 2 | `tests/test_sim_visual_decoupling.py::test_producer_returns_plain_data` | [M] |
| `SIM/vwap-playback/one-chart-at-a-time` | Only one chart plays back at a time | BUILT | WORKING | `simulator_tab.py:464-474`, `::_on_chart_bot_changed:932` | issue #59 zone 2; `simulator_tab.py:455-462` | NO TEST | [S] |
| `SIM/vwap-playback/thirty-frames-a-second` | Smooth thirty-frame playback | **ABSENT** | **BROKEN** | no site — timers run at `fleet_replay_panel.py:1691` (500 ms) and `:1704` (250 ms) | issue #59 zone 2 | NO TEST | [M] |
| `SIM/vwap-playback/prev-next-ticker-row` | Prev and Next arrows with the ticker-pair selector | **ABSENT** | **BROKEN** | no site anywhere under `src/gui/simulator_tab/` | issue #59 zone 4 | NO TEST | [M] |

#### `SIM/tablet-candle-playback` — Stone Tablet Candle PlayBack Window

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/tablet-candle-playback/candles-play-back` | Stone Tablet candles play back on the chart | BUILT | WORKING | `fleet/sim_visuals.py` | issue #59 zone 3 | `tests/test_sim_chart_marker_anchoring.py::test_the_panel_appends_before_it_marks` | [M] |
| `SIM/tablet-candle-playback/own-window` | It is its own window, separate from the VWAP one | **PARTIAL** | **BROKEN** — one widget serves both | `fleet/sim_visuals.py` | issue #59 zone 3 | NO TEST | [M] |
| `SIM/tablet-candle-playback/trade-markers` | Candles carrying a trade are marked | BUILT | WORKING | `sim_visuals.py::mark_trade:739`, `::clear_markers:770` | issue #59 zone 3 | `tests/test_sim_chart_marker_anchoring.py::test_a_marked_candle_is_never_decimated_away` | [M] |
| `SIM/tablet-candle-playback/history-shading` | Shading starts where the documented history starts | BUILT | WORKING | `sim_visuals.py::set_ytd_start:725`, `:653`, `:731` | `sim_visuals.py:731` | NO TEST | [S] |
| `SIM/tablet-candle-playback/no-future-prices` | The replay never serves a price from the future | BUILT | WORKING | `fleet/candle_series.py`; the tape cursor in `tablet_backend.py` | `fleet/candle_series.py` | `tests/test_sim_causality_no_future_prices.py::TestNoCandleIsServedFromTheFuture` | [M] |
| `SIM/tablet-candle-playback/no-synthetic-fallback` | A symbol with no tablet is skipped, never faked | BUILT | WORKING | `fleet_replay_panel.py:1336-1337` | `fleet_replay_panel.py:1336` | NO TEST | [M] |
| `SIM/tablet-candle-playback/coverage-report` | How many candles each symbol supplied, and the shortfall | BUILT | WORKING | `fleet_replay_panel.py:1326-1346`, `:1387-1391` | `fleet_replay_panel.py:1268-1272` | NO TEST | [S] |

#### `SIM/validation-mode` — Validation Mode

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/validation-mode/start-replay` | The "Start Replay" button | BUILT | WORKING | `fleet_replay_panel.py:321-327`, `::_on_start_clicked:1229` | `NO RECORDED SPEC` | `tests/test_a_simulator_replay_fires_a_trade.py::TestASimulatorReplayFiresATrade::test_the_replay_actually_played_candles` | [M] |
| `SIM/validation-mode/stop-replay` | The Stop button | BUILT | WORKING | `fleet_replay_panel.py:328-336`, `::_on_stop_clicked:2165` | `fleet_replay_panel.py:330-333` | `tests/test_fleet_replay_panel_state_machine.py::TestStopReportsFailure::test_the_happy_path_still_requests_stop` | [M] |
| `SIM/validation-mode/reset` | The Reset button, which asks before discarding a run | BUILT | WORKING | `fleet_replay_panel.py:252-256`, `::_confirm_reset:902` | `fleet_replay_panel.py:196-201` | `tests/test_fleet_replay_panel_state_machine.py::TestResetConfirmsWhenARunIsInFlight::test_it_asks_before_discarding_a_running_replay` | [M] |
| `SIM/validation-mode/start-refuses-a-second-run` | Start refuses while a replay is running, and says why | BUILT | WORKING | `fleet_replay_panel.py:1234-1247`, `:860`, `::_status_error:847` | `fleet_replay_panel.py:1230-1243` | `tests/test_fleet_replay_panel_state_machine.py::TestStartIsNotReentrant::test_a_second_start_while_running_is_refused` | [M] |
| `SIM/validation-mode/bots-initialise` | The simulated bots reach a running state | BUILT | WORKING | `fleet/fleet_replay_controller.py::_build_sim`; venue `src/exchange/tablet_backend.py:102` | issue #31 | `tests/test_a_simulator_replay_fires_a_trade.py::TestSimBotsInitialise::test_every_sim_bot_reaches_the_initialised_state` | [M] |
| `SIM/validation-mode/replay-fires-trades` | The replay actually fires trades | BUILT | WORKING | `fleet_replay_controller.py`; `tablet_backend.py` | issue #109 | `tests/test_a_simulator_replay_fires_a_trade.py::TestASimulatorReplayFiresATrade::test_the_replay_fires_at_least_one_trade` | [M] |
| `SIM/validation-mode/fills-are-recorded` | Every fill lands in the tape ledger and the run log | BUILT | WORKING | `tablet_backend.py:299`; reader `fleet_replay_controller.py:1418-1432` | issue #110 | `tests/test_the_simulator_records_the_fill_it_filled.py::TestTheFillReachesTheRunLog::test_the_row_carries_the_symbol_side_amount_and_price` | [M] |
| `SIM/validation-mode/venue-refuses-unfundable-order` | The sim venue refuses an order the wallet cannot fund | BUILT | WORKING | `src/exchange/tablet_backend.py` | issues #111 and #111A | `tests/test_sim_bot_agrees_with_its_venue.py::TestTheBackendRefusesTheWayAVenueRefuses::test_an_unfundable_buy_raises_instead_of_returning_an_order` | [M] |
| `SIM/validation-mode/lotless-bot-opens-locked` | A bot holding no lot opens with a locked position | BUILT | WORKING | `fleet_replay_controller.py:436-472`, `:1203-1245` | issue #111B | `tests/test_lotless_sim_bots_open_with_a_locked_side.py::TestFleetSizeStopsMattering::test_the_wallet_does_not_leave_the_last_bot_short` | [M] |
| `SIM/validation-mode/wallet-seed` | The wallet is seeded from the fleet's own targets | BUILT | WORKING | `fleet_replay_controller.py:878-936`, `:995` | seam group H | `tests/test_lotless_sim_bots_open_with_a_locked_side.py::TestFleetSizeStopsMattering::test_the_wallet_does_not_leave_the_last_bot_short` | [M] |
| `SIM/validation-mode/fee-matches-the-venue` | A market order is charged the taker rate | **BROKEN** | **BROKEN** — charged the maker rate | `tablet_backend.py` fee path | issue #121 (seam F1) | NO TEST | [S] |
| `SIM/validation-mode/replay-progress` | Candles, percent, trades, exceptions, rate and time left | BUILT | WORKING | `fleet_replay_panel.py:311-316`, `::_refresh_progress:2196` | **stale citation, unverified** | `tests/test_a_simulator_replay_fires_a_trade.py::TestASimulatorReplayFiresATrade::test_the_replay_actually_played_candles` | [M] |
| `SIM/validation-mode/parity-report` | The simulator-against-live trade comparison | BUILT | WORKING | `fleet_replay_panel.py::_run_parity_comparison`; `src/trading/stone_tablets/parity_harness.py::compare_trades` | `NO RECORDED SPEC` | `tests/test_fleet_replay_panel_state_machine.py::test_the_panel_measures_parity_against_the_tape_s_own_fills` | [M] |
| `SIM/validation-mode/parity-skipped-warning` | "This run is synthetic and is NOT comparable to live" | BUILT | WORKING | `fleet_replay_panel.py::_note_parity_state` | **stale citation, unverified** | `tests/test_fleet_replay_panel_state_machine.py::TestParitySkipIsReported::test_the_status_names_it_when_ytd_is_empty` | [M] |
| `SIM/validation-mode/soft-start-cap` | The soft-start date cap announced in the log | BUILT | WORKING | `fleet_replay_panel.py::_compute_soft_start:1166`, applied `:1305-1315` | `fleet_replay_panel.py:1303-1309` | NO TEST | [S] |
| `SIM/validation-mode/full-evaluation-toggle` | The "Full evaluation" checkbox | BUILT | UNVERIFIED | `fleet_replay_panel.py:271-283` | `fleet_replay_panel.py:258-269` | NO TEST | [S] |
| `SIM/validation-mode/fetch-ytd` | The "Fetch YTD" button | BUILT | UNVERIFIED | `fleet_replay_panel.py:241-251`, `::_on_fetch_ytd_clicked:974` | `fleet_replay_panel.py:167-177` | NO TEST | [S] |
| `SIM/validation-mode/simulator-log` | The Simulator Log pane and its Pause button | BUILT | WORKING | `simulator_tab.py:569-586`, `:554-566` | `simulator_tab.py:518-521` | `tests/test_simulator_log_merge.py::TestBothStreamsAreRecorded::test_the_two_streams_stay_distinguishable` | [M] |
| `SIM/validation-mode/run-folders` | A run folder per replay, pruned so it cannot grow forever | BUILT | WORKING | `src/trading/sim_run_log.py:92-97`, `::_apply_retention:394` | `sim_run_log.py:20-31`, `:128-149` | `tests/test_sim_run_log_retention.py::test_the_policy_bounds_the_same_fixture` | [M] |
| `SIM/validation-mode/never-touches-live` | The run log refuses to attach to a live bot | BUILT | WORKING | `sim_run_log.py:520-546` | `sim_run_log.py:531` | `tests/test_sim_run_log.py::test_refuses_to_attach_to_live_bot_bus` | [M] |
| `SIM/validation-mode/data-validation-halt` | The Simulator halts when its data cannot be trusted | **ABSENT** | **BROKEN** — zero importers outside the test tree | `src/trading/sim_validation_guard.py:1` | `sim_validation_guard.py:1` | `tests/test_sim_validation_guard.py` exercises dead code | [M] |

#### `SIM/backtest-mode` — Backtest Mode

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/backtest-mode/mode-is-selectable` | The mode appears in the dropdown | BUILT | WORKING | `simulator_tab.py:187-200`, `:759-772` | `simulator_tab.py:150-153` | NO TEST | [M] |
| `SIM/backtest-mode/mode-changes-behaviour` | Choosing it makes the Simulator behave differently | **ABSENT** | **BROKEN** — the method it calls is defined nowhere | `simulator_tab.py:807-809` | `simulator_tab.py:163-171` | NO TEST | [M] |
| `SIM/backtest-mode/mode-hint-line` | The grey line saying what this mode collects | BUILT | WORKING | `simulator_tab.py:202-206`, `:798-806` | `simulator_tab.py:155-180` | NO TEST | [S] |

#### `SIM/nuclear-mode` — Nuclear Mode

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/nuclear-mode/panel` | The Nuclear Mode page | BUILT | WORKING | `nuclear_mode_panel.py:99`; page 1 of `simulator_tab.py:307` | `NO RECORDED SPEC` | `tests/test_nuclear_panel_drives_v2.py::TestThePanelStillBuilds::test_it_constructs_headlessly` | [M] |
| `SIM/nuclear-mode/runs-the-looped-controller` | It runs the looped fleet controller, not the old scout | BUILT | WORKING | `nuclear_mode_panel.py:48-50`, `:449`; `nuclear_fleet_controller.py:233` | `nuclear_mode_panel.py:4-8` | `tests/test_nuclear_panel_drives_v2.py::TestItConstructsTheFleetController::test_it_constructs_v2_not_v1` | [M] |
| `SIM/nuclear-mode/old-scout-retired` | The old one-tape scout is gone from the live path | ABSENT | WORKING (retired on purpose) | `nuclear_controller.py:52` — zero importers outside the test tree | `nuclear_mode_panel.py:4-8`; seam row A3 | `tests/test_nuclear_panel_drives_v2.py::TestTheAsyncLifecycleIsHonoured::test_v1_start_is_not` | [M] |
| `SIM/nuclear-mode/fleet-preview` | The fleet preview line and "Reload fleet" | BUILT | WORKING | `nuclear_mode_panel.py:185-198`, `::_rescan_cache:369` | `nuclear_mode_panel.py:375-378` | `tests/test_nuclear_panel_drives_v2.py::TestThePanelStillBuilds::test_it_reads_the_real_fleet` | [M] |
| `SIM/nuclear-mode/cycle-controls` | The cycle-length and max-cycles spinners | BUILT | WORKING | `nuclear_mode_panel.py:223-240` | `NO RECORDED SPEC` | NO TEST | [S] |
| `SIM/nuclear-mode/market-noise` | "Vary market structure per cycle" | BUILT | WORKING | `nuclear_mode_panel.py:242-251`; `nuclear_fleet_controller.py:548` | `simulator_tab.py:176-180` | `tests/test_nuclear_cycle_noise.py::TestTheInstrumentWorks::test_the_amplitude_is_in_the_declared_band` | [M] |
| `SIM/nuclear-mode/never-writes-the-tablets` | Nuclear never modifies the Stone Tablets | BUILT | WORKING | `nuclear_fleet_controller.py:548` (noise applied to a copy) | `nuclear_mode_panel.py:246-250` | `tests/test_nuclear_cycle_noise.py::TestTheStoneTabletsAreNeverWrittenOver` | [M] |
| `SIM/nuclear-mode/load-oscillation` | "Oscillate system load" | BUILT | WORKING | `nuclear_mode_panel.py:252-263`; `nuclear_fleet_controller.py:418-420` | `NO RECORDED SPEC` | `tests/test_nuclear_fleet_controller.py::test_sensor_matches_what_the_oscillator_actually_calls` | [M] |
| `SIM/nuclear-mode/start-and-stop` | The Start Scout and Stop buttons | BUILT | WORKING | `nuclear_mode_panel.py:266-289`, `::_on_start_clicked:419`, `::_on_stop_clicked:526` | `nuclear_mode_panel.py:422-425`; `nuclear_fleet_controller.py:447` | `tests/test_nuclear_stop_is_responsive.py::TestTheLifecycleApiThePanelCalls::test_stop_and_request_stop_agree` | [M] |
| `SIM/nuclear-mode/live-status` | The sixteen-field live status readout | BUILT | WORKING | `nuclear_mode_panel.py:56-83`, `::_refresh_status:715` | `nuclear_mode_panel.py:296-305` | `tests/test_nuclear_panel_drives_v2.py::TestTheStatusRowsActuallyGetFilled::test_every_declared_row_is_populated` | [M] |
| `SIM/nuclear-mode/drives-the-swarm` | Nuclear drives the Simulator Bot Swarm rows | BUILT | WORKING | `simulator_tab.py::set_swarm_getter`; wired **stale citation, unverified** | `simulator_tab.py` | `tests/test_nuclear_drives_the_sim_swarm.py::TestTheSeamIsActuallyWired` | [M] |
| `SIM/nuclear-mode/topology-injection` | Nuclear stresses the Market Inspector's proposals | BUILT | WORKING | `simulator_tab.py::set_topology_getter`; wired **stale citation, unverified** | `simulator_tab.py` | `tests/test_nuclear_receives_topology_injections.py::TestTheStressPathNeverAdoptsLiveBots` | [M] |
| `SIM/nuclear-mode/coverage-report` | The feature-coverage report at the end of a soak | BUILT | WORKING | `nuclear_fleet_controller.py:422-427`; `src/trading/nuclear_verification.py` | `nuclear_verification.py:3-8` | NO TEST | [S] |
| `SIM/nuclear-mode/cache-helper` | The helper the panel told you to run when the cache was empty | **ABSENT** | **BROKEN** — resolves a path that does not exist; zero importers | `populate_nuclear_cache.py:57-63` | `NO RECORDED SPEC` | NO TEST | [M] |

#### `SIM/emitter-network` — Emitter Network

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SIM/emitter-network/sim-pins` | The Simulator's own emitters | BUILT | WORKING | 14 pins across `simulator_tab.py`, `fleet/fleet_replay_panel.py`, `fleet/fleet_replay_controller.py` | **removed, see R-EMITTER** | `tests/test_feature1_fleet_load_emitters.py` | [M] |
| `SIM/emitter-network/fleet-pins` | The fleet loader's emitters | BUILT | WORKING | 8 pins across `fleet/bot_state_loader.py`, `fleet/fleet_replay_controller.py` | **removed, see R-EMITTER** | `tests/test_feature1_fleet_load_emitters.py` | [M] |
| `SIM/emitter-network/count-matches-the-spec` | The network holds the number the spec names | **PARTIAL** | **BROKEN** — 22 against a specified 40 | measured across `src/` | **removed, see R-EMITTER** | NO TEST — the whole-tree checker was retired with the pin register | [M] |
| `SIM/emitter-network/every-pin-has-a-row` | Every emitter is in the register and every register row has an emitter | **ABSENT** | **BROKEN** — the pin register and its checker were both removed; `src/core/emit_contracts.py` is the current mechanism and it keys on topic, not on a pin row | no site | **removed, see R-EMITTER** | `tests/test_emit_contracts.py` | [M] |
| `SIM/emitter-network/pins-carry-a-prediction` | Each emitter reports its prediction beside what it observed | BUILT | WORKING | `src/core/signal_contract.py:1146` (`emit`, which takes both `actual` and `expected`) | R-PREDICTION | `tests/test_emitter_eviction_and_digest.py` | [T] |
| `SIM/emitter-network/operation-duration` | Each emitter records how long its operation took | **PARTIAL** | **BROKEN** — 0 of 40 carry one | item 10.3 phase 2, not done | `docs/engineering-notes/2026-08-19_emitter_duration_classification.md` | NO TEST | [S] |
| `SIM/emitter-network/every-emitter-proved` | Each emitter is verified against the spec | **ABSENT** | **BROKEN** — item 10.4 not done | no site | **removed, see R-EMITTER** row 10.4 | NO TEST | [S] |

### Simulator measurements and controls

Every run used pytest, offscreen, in a scratchpad copy of the clone, so the read-only clone
gained no cache files. Every run loaded the suite's own `conftest.py`. **918 tests passed
and none failed** across five batches. Every exit code was read; none was 139 or 127.

**CONTROL — the instrument can fail.** One assertion in `tests/test_sim_bot_area.py:157`
was changed by a single token. Exit 0 became exit 1 with a named failure. Reverting
restored exit 0. A green run from these files is therefore a claim about the code, not
about the runner.

**Two further controls are built into the suite and passed.** One exists because a fleet
that refused every trade would satisfy the other assertions vacuously. The other proves
that the failure the boot armour is meant to survive is a real failure.

**CONTROL for the emitter count.** My independent count reconciles exactly with the
project's own checker at 78. My first pass returned 77 and was not reported until the
missing pin was found. A count that disagrees with the project's instrument is not
evidence.

### A contradiction with the ground truth, resolved by measurement

**I was told the Nuclear controllers were "v1 reachable and single-tape, v2 unreachable and
looped". Measured, it is the other way round.** The looped fleet controller is the
reachable one, and `tests/test_nuclear_panel_drives_v2.py` pins that and passes. The
single-tape controller has zero importers outside the test tree. The venue-seam audit
agrees with this measurement, not with the brief I was given.

**A second correction, and it favours the code.** The venue-seam audit was written at
commit `a51756b`. This clone is at `cb58d9d`, three commits later, and the difference is
the repair for issue #111B. The audit's row H4 verdict — a violation, open — is therefore
**stale**, and its line citations for the wallet seeding no longer resolve; that code moved
from `:830-841` to `:878-936`. The underlying fact survives: the wallet is still seeded at
the sum of the fleet's targets with no fee headroom. The consequence is gone, because no
bot has to buy its whole position at open any more.

### What the Simulator audit did not cover

No window was rendered and no screenshot taken, so layout, styling and the
frames-a-second question are judged from source and timer constants rather than from
pixels. The chart painting code was never executed. "Fetch YTD" was never clicked. The
bot-detail dialog was never opened against a simulated bot. The Stone Tablets storage and
fetcher are consumed here but belong to their own subsystem.

---

## SUBSYSTEM 8 — PAPER TRADER

**Verdict in one line.** You said it "may have some stuff but its not working or finished",
and that is right — **zero of the 23 items in your own approved design document are built** —
but one thing will surprise you: a "Paper Swarm" tab is on screen in the running
application today, and its Start button turns a row to **"LIVE"** while attaching no venue
and placing no order.

### Paper Trader — the eight framing features

Framed to match the Simulator's shape, because the rule is that the two differ only in where
their data comes from.

| ID | Framing feature | Built | Works | Rule | Spec | Ev |
| --- | --- | --- | --- | --- | --- | --- |
| `PAPER/the-tab` | The Paper Trader tab itself | **ABSENT** | ABSENT | COMPLIANT (gated, not overdue) | design §4.1:120; issue #19 | [M] |
| `PAPER/bot-list` | A bot list like the Trading tab's | **ABSENT** | ABSENT | COMPLIANT (gated) | design §4.1:120-138 | [M] |
| `PAPER/ta-voting-panel` | The same Indicator Voting Panel | **ABSENT** | ABSENT | COMPLIANT (gated) | design :134; R-VENUE | [S] |
| `PAPER/real-time-data-feed` | Live exchange prices, in real time | **ABSENT** | ABSENT | COMPLIANT (gated) | concept spec req2; issue #19 | [S] |
| `PAPER/paper-venue` | Fake fills against real prices, with real fees | **ABSENT** | ABSENT | COMPLIANT (gated) | design §4.2:153-190 | [M] |
| `PAPER/paper-wallet` | One paper balance all paper bots draw from | **ABSENT** | ABSENT | COMPLIANT (gated) | design §4.3:192-213 | [M] |
| `PAPER/paper-logs` | Its own activity log and its own state file | **ABSENT** | ABSENT | COMPLIANT (gated) | design :137-138, :248-249 | [M] |
| `PAPER/swarm-layer` | Paper rows inside the Bot Swarm tab | BUILT | **BROKEN** — Start says LIVE and trades nothing | **NON-COMPLIANT** | concept spec req3, req4 | [M] |
| `PAPER/emitter-network` | Tracked emitters for Paper | PARTIAL | WORKING | COMPLIANT | issue #19; **removed, see R-EMITTER** | [T] |

**Nine framing features. 1 BUILT, 1 PARTIAL, 7 ABSENT. 1 WORKING, 1 BROKEN, 7 ABSENT. 1
NON-COMPLIANT.**

### Paper Trader — the three findings at framing level

**1. A surface says LIVE and trades nothing.** `bot_visualizer.py:1943-1966`. Press Start on
a paper bot row and the code sets the row running and writes "LIVE" into the status label.
Measured at that same moment: the venue handle stays empty, the price stays a dash, the
profit-and-loss stays a dash. **This is the exact shape of the mess this document exists to
stop repeating, and it should be deleted before the next Paper attempt begins**, so nobody
mistakes it for a working paper bot.

**2. Zero of 23 approved design items are built.** The design document of 2026-05-19 names
files, classes, method signatures and a ship gate. None of the five ship-gate conditions is
met.

**3. A live source comment cites a document at a path that never existed.**
**stale citation, unverified** points at the design document under `docs/audits/`. Searching the whole
git history for that path returns nothing. **Control**: the same query for a document that
does exist returns its commit, so the reader works. The document is real and survives in a
session-25 close package, but twenty-three approved requirements sat unbuilt behind a
citation nobody could follow.

### The spec mapping — why the SPEC column earns its place

| # | Design item | Code behind it |
| --- | --- | --- |
| D1 | The tab, splitter layout identical to Trading | **none** |
| D2 | One paper tab per configured real exchange | **none** |
| D3 | The crypto and stock paper stack | **partial, inert** |
| D4 | A paper exchange panel | **none** |
| D5 | A paper indicator voting panel | **none** |
| D6 | A paper activity log on a paper event bus | **none** |
| D7 | A paper API interaction log | **none** |
| D8 | A paper balance widget, editable per currency | **none** |
| D9 | A "Mirror Live Bots to Paper" button | **none** |
| D10 | A paper venue: real reads, synthetic fills | **none** |
| D11 | A choice of how a paper order fills | **none** |
| D12 | A shared, thread-safe paper wallet | **none** |
| D13 | Snapshot real balances as paper starting funds | **none** |
| D14 | A paper Market Inspector sub-tab | **none** |
| D15 | Nine source files under a paper tab directory | **0 of 9 present** |
| D16 | A paper state file that survives a restart | **none** |
| D17 | A paper log directory | **none** |
| D18 | Real connector for authentication, wrapped by the paper venue | **none** |
| D19 | Its own bus, log manager, bot manager, wire manager, state manager, inspector | **none of the six** |
| D20 | Shared settings, keyring and data pool | exist for Live, no paper consumer |
| D21 | The live header strip hidden on the Paper tab | **built but unreachable** |
| D22 | An inline ten-field stat strip | **none** |
| D23 | Ship gate: make a paper bot, run it, see fills, balance moves, log writes | **0 of 5 met** |

**One rule exists only in memory.** "Paper budget = total target balance of paper bots,
doubled." Searching `docs/` and `src/` returns zero hits. If the memory holding it is lost,
the rule is lost.

### Paper Trader — functions beneath each framing feature

| ID | Function | Built | Works | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `PAPER/the-tab/tab-exists` | The Paper Trader tab in the tab bar | ABSENT | ABSENT | none — four sentinels at **stale citation, unverified** | design §4.1:120; issue #19 | NO TEST | [M] |
| `PAPER/the-tab/looks-like-trading` | A clone of Trading in a slightly different colour | ABSENT | ABSENT | none | design §4.1:120-138 | NO TEST | [M] |
| `PAPER/the-tab/header-strip-hides` | The live header strip must not show over paper | BUILT | **BROKEN** (unreachable) | **stale citation, unverified** | design §0a dec.5:20 | NO TEST | [M] |
| `PAPER/the-tab/own-stat-strip` | An inline ten-field stat strip bound to paper | ABSENT | ABSENT | none | design §0a dec.6:21 | NO TEST | [S] |
| `PAPER/the-tab/crypto-equity-wing-swap` | The paper stack follows the Crypto and Stock switch | BUILT | **BROKEN** (dead branches) | **stale citation, unverified**, **stale citation, unverified** | `NO RECORDED SPEC` | NO TEST | [M] |
| `PAPER/the-tab/launcher-claim` | The launcher's "Paper Trading Support" bullet | BUILT | **BROKEN** (never renders) | `src/gui/launcher.py:165` — zero importers | `NO RECORDED SPEC` | NO TEST | [M] |
| `PAPER/bot-list/bots-from-a-fleet-load` | Paper bots come only from a fleet load of bot state | ABSENT | ABSENT | none | issue #19 | NO TEST | [S] |
| `PAPER/bot-list/own-bot-manager` | Paper bots live in their own manager | ABSENT | ABSENT | none | design §6:501 | NO TEST | [S] |
| `PAPER/bot-list/mirror-live-bots` | Mirror the real trading tab into a safe environment | ABSENT | ABSENT | none | design :148-151 | NO TEST | [S] |
| `PAPER/ta-voting-panel/same-panel-as-live` | The same panel Live and the Simulator use | ABSENT | ABSENT | none | design :134; R-VENUE | NO TEST | [S] |
| `PAPER/real-time-data-feed/live-prices` | Trades in real time against live exchange data | ABSENT | ABSENT | none | concept spec req2 | NO TEST | [S] |
| `PAPER/real-time-data-feed/simulator-continues-as-paper` | A Simulator back-test continues as a Paper instance | ABSENT | ABSENT | none | concept spec §3a | NO TEST | [S] |
| `PAPER/paper-venue/fake-fills` | Only pretends to trade, using fake funds | ABSENT | ABSENT | none | design §4.2:153-190 | NO TEST | [M] |
| `PAPER/paper-venue/fill-model-choice` | How a paper order fills | ABSENT | ABSENT | none | design :184-190 | NO TEST | [S] |
| `PAPER/paper-venue/fees-charged` | Paper trades pay the real fee | ABSENT | ABSENT | none | concept spec §5 Q2 | NO TEST | [S] |
| `PAPER/paper-venue/paper-mode-value` | A Paper setting a bot can be in | ABSENT | ABSENT | none — bot modes are Scrumming and Extractor only | seam row A1; concept spec req1 | NO TEST | [M] |
| `PAPER/paper-venue/same-trading-logic` | The same trading logic and bot list as Live | ABSENT | ABSENT | none to compare | R-VENUE at `fleet_replay_controller.py:453-454` | NO TEST | [S] |
| `PAPER/paper-venue/equity-paper-trader` | A Paper Trader for stocks | ABSENT | ABSENT | `stock_main_window.py:361-368` imports a module that does not exist; that window is constructed nowhere | design :133 | NO TEST | [M] |
| `PAPER/paper-venue/broker-paper-endpoint` | Paper trading through the equity broker | BUILT | UNVERIFIED | `src/stocks/alpaca_connector.py:23`, `:63-81` — zero importers | `NO RECORDED SPEC` | NO TEST | [M] |
| `PAPER/paper-wallet/shared-balance` | One paper balance all paper bots draw from | ABSENT | ABSENT | none | design §4.3:192-213 | NO TEST | [M] |
| `PAPER/paper-wallet/starting-funds-editable` | Set the starting paper funds yourself | ABSENT | ABSENT | none | design :141-146 | NO TEST | [S] |
| `PAPER/paper-wallet/budget-is-double-the-target` | The paper budget is twice the total target balance | ABSENT | ABSENT | none | **recorded nowhere in the repository** | NO TEST | [M] |
| `PAPER/paper-logs/activity-log` | Its own paper activity log | ABSENT | ABSENT | none | design :137-138, :249 | NO TEST | [M] |
| `PAPER/paper-logs/state-survives-restart` | The paper wallet survives reopening the app | ABSENT | ABSENT | none | design :146, :248 | NO TEST | [M] |
| `PAPER/paper-logs/isolated-from-live-state` | Paper never touches live state, bus or capital registry | ABSENT | ABSENT | none | design §6:497-513 | NO TEST | [S] |
| `PAPER/swarm-layer/the-tab` | The Paper Swarm sub-tab | **BUILT** | **WORKING** | `bot_visualizer.py:1580-1675` | concept spec req3, req4 | NO TEST | [M] |
| `PAPER/swarm-layer/add-a-paper-bot` | "+ Add Paper Bot" makes a row | **BUILT** | **WORKING** | `bot_visualizer.py::_create_paper_bot_row:1851-1976` | `NO RECORDED SPEC` | NO TEST | [M] |
| `PAPER/swarm-layer/start-button-trades` | Pressing Start makes it trade | BUILT | **BROKEN** — says LIVE, attaches nothing | `bot_visualizer.py:1943-1966` | concept spec req2 | NO TEST | [M] |
| `PAPER/swarm-layer/row-per-session` | A live row for each running paper session | **BUILT** | **WORKING** (no producer) | **stale citation, unverified** — zero production callers | concept spec req3 | `tests/test_swarm_registration_emitters.py::test_the_row_lands_in_the_layer_it_was_addressed_to` | [T] |
| `PAPER/swarm-layer/portfolio-summary` | Total Capital, Net PnL and Active Bots | PARTIAL | **BROKEN** — net profit is a literal, and adding a row does not refresh it | `bot_visualizer.py::_update_paper_summary` | `NO RECORDED SPEC` | NO TEST | [M] |
| `PAPER/swarm-layer/market-inspector-pushes-here` | Market Inspector pushes topologies and opposing trades to Paper | ABSENT | ABSENT | the adopt handler at **stale citation, unverified** has no Paper destination | concept spec req5; issue #18 | NO TEST | [S] |
| `PAPER/emitter-network/run-registration-pin` | The tracked emitter recording a paper run starting | **BUILT** | **WORKING** | `bot_visualizer.py`; declared `signal_contract.py:719` | issue #19; **removed, see R-EMITTER** | `tests/test_swarm_registration_emitters.py::test_each_layer_registration_emits_once` | [T] |

**`PAPER/emitter-network` measured: 1 of the tree's 78 emitters. It is a good one** — it
reads the row back out of its layer's store rather than echoing its own argument, and it was
hardened after a measured blinding. Issue #19 requires every new Paper emitter to meet that
standard; one already does, and it is the template.

### Foundation or scaffolding — what the next attempt should start from

**347 lines of Paper-named code exist; 280 of them are code rather than blanks or comments.**

**KEEP — foundation, about 158 code lines, all display layer with no engine behind any of
it.** The swarm row interface (**stale citation, unverified**, about 70 lines) is the only
Paper code with tests, and they are good tests with two-sided controls. The tracked emitter
above. The Paper Swarm tab shell (`bot_visualizer.py:1580-1675`, about 82 lines), which
renders, is reachable, and already accepts rows from the first item. A future Paper engine
plugs a producer into this seam and rewrites none of it.

**CLEAR — scaffolding, about 122 code lines.** The mock bot row and its Start toggle
(`bot_visualizer.py:1851-1976`, about 105 lines) is the largest Paper block in the tree and
the one that says LIVE; its pair list is a hardcoded eight-item dropdown, its data-source
dropdown offers three sources none of which is a configured Acervator exchange, and a
hand-typed row contradicts the settled rule that paper bots come only from a fleet load.
Finishing it means deleting all three decisions first. Then the portfolio summary
(six lines, two defects), the four sentinels and both dead wing branches (about ten lines,
neither branch can ever execute), the broken equity import (seven lines, doubly dead — two
earlier documents record it as a live crash and it is not), and the launcher's Paper claim
(one line, in a module with zero importers).

**LEAVE ALONE.** **stale citation, unverified** names Paper Trader in the isolated-tabs set; the
Simulator half of that set works and the Paper string is a harmless forward reference. Also
leave the equity broker package alone; it is a separate hierarchy with a different meaning
of the word.

**The call: start the engine from nothing, start the display from the three keepers.** Every
Paper row that has neither a spec nor a test is scaffolding, and nothing with a real spec
behind it is scaffolding. The spec column and the keep-or-clear call agree exactly.

### Paper measurements and controls

Eleven measurements ran through pytest, exit code 0, offscreen, from a scratchpad probe with
a conftest that loads the clone's own verbatim, so the log redirects applied without writing
into the clone.

| Measurement | Control | Result |
| --- | --- | --- |
| Log redirects active | Assert the crash root is under Temp and not the live log tree | Redirect confirmed |
| Import the paper tab module | The sibling simulator tab module does import | Not found; control loaded |
| Are the nine specified paper files present | The same reader counts the simulator tab's files | 0 of 9; control 9 |
| Bot mode members | Assert a known member is visible | Scrumming and Extractor; no Paper |
| Paper Swarm sub-tab exists | Assert a title that should not exist is not found | Three sub-tabs, one is Paper Swarm |
| Does Start attach a venue | The summary total does move on an explicit refresh | Status LIVE, venue empty, price blank |
| Does net profit compute | Total Capital does track the entered figure | Total tracks; net profit is a literal |
| Paper tab registered in the main window | The same reader finds the Simulator's registration | Zero Paper registration lines |
| Are the sentinels reassignable | The same reader finds a real assignment at `:5389` | One assignment, and it is empty |
| Is the equity import a live crash | The reader can see an unguarded import elsewhere | Wrapped in a try block; logs a warning |
| Design-doc path in git history | The same query for a document that exists returns a commit | The cited path never existed |

**A caveat that is not removed.** The live-tree guard reported DEGRADED, because a live
application was running and writing its own logs. The probe declares no logger and opens no
file for writing, and the redirect check passed. But that run does not verify isolation, and
this document does not claim it does.

### What the Paper audit did not cover

The application was never launched; every measurement built the widget in isolation. Only
one of nine archive copies of the design document was read, so a newer approved revision, if
one exists, was not compared. The claim that no deprecated Paper source file exists across
159 release archives was inherited, not re-measured. No parity comparison of trading logic
was possible, because no Paper logic exists to compare.

---

## SUBSYSTEM 9 — PROOF OF ACCUMULATION (fresh build)

**Verdict in one line.** Nothing exists, by the operator's ruling — and the finding that
matters is that **nothing was ever specified either**: seven of its nine features have no
recorded spec anywhere in the repository, so the next build starts from a blank page rather
than from a document.

The code on disk is inventoried in Part A above and is not a feature here. Every row is
`ABSENT` and every Code cell reads `none`.

**The spec column is the whole finding.** This repository holds no `docs/adr/` directory, no primary
memo text, and no design document for Proof of Accumulation anywhere in this repository.
What survives is 4,664 lines of code and a *reference* to a patent record. The feature
names below are reconstructed from code labels and audit prose, and they are marked `[M]`
because they are an auditor's inference rather than the operator's own words.

**Compare that with System Status below, which has a real written spec in issue #34.** A
fresh build with a written spec is trackable from day one. A fresh build without one is
not. That asymmetry is the strongest argument for writing the Proof of Accumulation spec
before any code is written.

| ID | Feature | Built | Works | Rule | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `PROOF-OF-ACCUMULATION/bot-identity` | A bot proves which bot it is before it competes | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [M] |
| `PROOF-OF-ACCUMULATION/tamper-proof-trade-log` | A trade record nobody can alter after the fact | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [S] |
| `PROOF-OF-ACCUMULATION/head-to-head-match` | Bots compete on accumulation and one is ranked first | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [M] |
| `PROOF-OF-ACCUMULATION/season-schedule` | Competition runs in numbered seasons | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [M] |
| `PROOF-OF-ACCUMULATION/token-award` | A competition earns a token, against a supply cap | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [M] |
| `PROOF-OF-ACCUMULATION/leaderboard` | You see where your bots rank against the field | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [M] |
| `PROOF-OF-ACCUMULATION/trophy-artwork` | A visual award for a placing, with rarity tiers | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [M] |
| `PROOF-OF-ACCUMULATION/network-connection` | A real competition needs a connection and mutual authentication | ABSENT | ABSENT | UNKNOWN | none | `NO RECORDED SPEC` | NO TEST | [M] |
| `PROOF-OF-ACCUMULATION/patent-record-intact` | The intellectual-property record survives the shelving | ABSENT | ABSENT | UNKNOWN | none | **stale citation, unverified**; chronicle 5512-5516 | NO TEST | [S] |

---

## SUBSYSTEM 10 — SYSTEM STATUS (fresh build)

**Verdict in one line.** Nothing exists — measured, two search hits and both are a Kraken
web address — but unlike Proof of Accumulation this subsystem **has a real written spec**
in issue #34, with three ordered units, a three-state health model and two named blockers.

Every row is `ABSENT` and every Code cell reads `none`. Nine of the nine rows carry a
recorded spec, which makes this the best-specified unbuilt subsystem in the application.

| ID | Feature | Built | Works | Rule | Code | Spec | Tests | Ev |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SYSTEM-STATUS/the-tab-itself` | "A new System Status tab that is fed by and displays the emitter network activity divided up by Subsystem and Tab" | ABSENT | ABSENT | UNKNOWN | none | issue #34 unit 17.3 | NO TEST | [S] |
| `SYSTEM-STATUS/health-colour-per-subsystem` | "The health of each subsystem as indicated by its respective emitter set" — green in spec and on time, yellow for warnings and slow-downs, red for crashes, hangs and threshold breaches | ABSENT | ABSENT | UNKNOWN | none | issue #34 health table ("Do not invent a score, a percentage or a fourth state") | NO TEST | [S] |
| `SYSTEM-STATUS/the-snapshot-report` | "A normal operational report or feed against which the entire system properly can be snapshot" | ABSENT | ABSENT | UNKNOWN | none | issue #34 unit 17.2 | NO TEST | [S] |
| `SYSTEM-STATUS/matching-log-format` | "Emitter logs should be formatted to match" the report | ABSENT | ABSENT | UNKNOWN | none | issue #34 unit 17.1 | NO TEST | [S] |
| `SYSTEM-STATUS/group-by-subsystem-and-tab` | Activity grouped on two axes, by subsystem and by tab | ABSENT | ABSENT | UNKNOWN | none | issue #34 ("Two axes, not one"); **removed, see R-EMITTER** supplies one axis, this matrix the other | NO TEST | [S] |
| `SYSTEM-STATUS/hang-detection` | A hung subsystem emits nothing, and "the absence is the signal" | ABSENT | ABSENT | UNKNOWN | none | issue #34 ("RED cannot be computed yet"); hard-blocked on issue #14 | NO TEST | [S] |
| `SYSTEM-STATUS/watchdog-feed-moves-here` | "Watchdog status feed, currently under console, will migrate to the system status tab" | ABSENT | ABSENT | UNKNOWN | none | issue #34 (operator 2026-08-13) | NO TEST | [S] |
| `SYSTEM-STATUS/emitter-id-to-name` | "ID numbers can be correlated to their names ... under the forthcoming System Status tab where all emitters are organized under their subsystems" | ABSENT | ABSENT | UNKNOWN | none | issue #34; **removed, see R-EMITTER** | NO TEST | [S] |
| `SYSTEM-STATUS/logs-correlate-to-emitters` | "This should be shaped around the Emitter Network against which other logs can be correlated" | ABSENT | ABSENT | UNKNOWN | none | issue #34 (operator 2026-08-14) | NO TEST | [S] |

**Two blockers recorded in issue #34, carried forward here so they are not rediscovered.**
Issue #14 (emitter staleness) is a **hard prerequisite** for hang detection, not a parallel
item — without it, red cannot be computed at all. And six tabs still have zero emitters, so
the grouping feature is bounded by emitter coverage on the day it is built.

---

## THE 43 OPEN ISSUES, MAPPED TO FEATURES

`gh issue list --state open --limit 400` returns **43**. Every one lands against a feature
or is marked cross-cutting. Three findings come out of this mapping and are stated after the
table.

### Issues that map to a feature

| Issue | Feature it belongs to |
| --- | --- |
| #2 Emitter Network, resume TIME and PROVE | `SIM/emitter-network` (and every other subsystem's emitter row) |
| #18 Topology and opposing-trade push, plus emitters | `MKT-INSPECTOR/adopt-and-push`, `MKT-INSPECTOR/emitter-network`, `PAPER/swarm-layer/market-inspector-pushes-here` |
| #19 Paper Trader build-out | every `PAPER/` framing feature |
| #23 Market Inspector, finish the build-out | `MKT-INSPECTOR/market-scan/freshness-line`, `.../include-stablecoins`, `.../timeframe-tickboxes`, `MKT-INSPECTOR/htf-signals-table/monthly-column`, `.../entry-strength-ladder`, `MKT-INSPECTOR/market-picture-panel` |
| #25 The Live swarm layer has no container | `BOT-SWARM/live-swarm-layer/status-rows` — **reproduced by execution** |
| #34 System Status tab | every `SYSTEM-STATUS/` feature |
| #44 Comments citing wrong line numbers | `TRADING/` (the file is `main_window.py`) — documentation, not behaviour |
| #46 A chart keeps fetching the old pair | `ASSET-CHARTS/candle-feed/pair-follows-symbol` — **repaired, measured**; `.../exchange-id-follows-symbol` remains open |
| #55 Asset Charts restructure | `ASSET-CHARTS/chart-navigation/one-chart-at-a-time`, `.../prev-next-with-the-ticker`, `ASSET-CHARTS/indicator-overlays/missing-voting-indicators`, `.../renders-what-the-panel-computes` |
| #59 Simulator tab restructure | `SIM/bot-list/legacy-fleet-table`, `SIM/vwap-playback/thirty-frames-a-second`, `.../prev-next-ticker-row`, `SIM/tablet-candle-playback/own-window` |
| #63 Multi-exchange API verification | `MKT-INSPECTOR/market-scan/every-exchange`, `TRADING/exchange-panels/one-panel-per-exchange` |
| #75 Near-duplicate fleet and nuclear simulator | `SIM/nuclear-mode` |
| #107 Detonation can fire twice across a restart | `TRADING/bot-controls` (bot logic; dormant by your own deferral) |
| #111 A Sim bot is not a Live bot on another feed | `SIM/validation-mode` — parent of the seam work |
| #117 The venue seam, 45 violations | every NON-COMPLIANT `SIM/` row |
| #118 Order writes, 11 violations | `SIM/validation-mode/venue-refuses-unfundable-order`, `.../replay-fires-trades`, `.../fills-are-recorded`, `.../wallet-seed` |
| #119 Wrappers: 100 candles against 300 | `SIM/ta-voting-panel/candle-count-matches-live`, `SIM/bot-list/stat-strip`, `SIM/validation-mode/parity-report` |
| #120 Market metadata, precision means two things | `SIM/validation-mode/venue-refuses-unfundable-order` |
| #121 A taker order charged the maker rate | `SIM/validation-mode/fee-matches-the-venue` |
| #122 Two exception vocabularies | `SIM/validation-mode/replay-progress`, `.../start-replay` |
| #123 The bot takes a sim flag, so it is not the same code | `SIM/validation-mode/simulator-log`, `SIM/ta-voting-panel/gate-lights`, `SIM/nuclear-mode/coverage-report` |
| #124 Zero spread, one book level | `SIM/tablet-candle-playback/candles-play-back`, `SIM/vwap-playback/price-against-vwap` |
| #125 Venue topology, and Paper does not exist | `PAPER/paper-venue/paper-mode-value`, `SIM/nuclear-mode/old-scout-retired` |
| #126 Connect never runs, markets never populate | `SIM/validation-mode/start-replay`, `.../bots-initialise`, `.../fetch-ytd` |
| #127 A one-sided venue callback | `SIM/validation-mode/fills-are-recorded`, `SIM/bot-list/per-symbol-trade-counts` |

### Issues that are genuinely cross-cutting

These belong to no single feature, and saying so is the honest answer rather than forcing a
row.

| Issue | What it cuts across |
| --- | --- |
| #26 Retroactive adversarial oversight | process, not product |
| #38 182 files stored with the wrong line endings | the whole repository |
| #53 Mouse-over descriptions, full audit | **every tab.** Measured: 297 tooltip sites across the source, the heaviest being 82 in the bot settings window, 67 in the wizard, 49 in the main window |
| #71 A 15,220-line bot file | code structure |
| #72 An 8,243-line main window file | code structure |
| #73 Four more oversized files | code structure |
| #76, #77, #78, #79 Reimplemented helpers | code structure. **Note: #79's claim that the design-token file has zero importers is now false** — see Part A |
| #80, #81 Session-chronicle and audit-directory bloat | the repository |
| #86 A top-level directory shadowing the standard library | the repository |
| #90 Manual processes documented only in prose | process |
| #91, #112, #113, #114 No continuous integration, lint, branch protection | build and release |

### Three findings from the mapping

**1. Two tabs have no open issue at all.** **History** and **Console** carry zero. Both are
also the two best-tested tabs in the application, so the absence is probably real rather
than neglect — but this audit found a rule breach in History that nobody has filed: the
`Cost USD` column. **That is an unfiled defect in a subsystem everyone believes is finished.**

**2. Proof of Accumulation has no issue and no spec.** It has 4,664 lines of code on disk,
no open issue, and no written specification anywhere in the repository. It is the only
subsystem in that position.

**3. Every issue mapped.** None was left with nowhere to go.

---

## THE ID INDEX

Every ID in this document, one per line, grouped by subsystem. Paste any of these into a
work brief, a report or an issue. A framing feature is marked with a bullet; its functions
are indented beneath it.

**77 framing features. 299 functions. 376 IDs in total.**

### Trading — 9 framing, 50 functions

```
TRADING/bot-list
    TRADING/bot-list/scrumming-table
    TRADING/bot-list/extractor-table
    TRADING/bot-list/ammo-column
    TRADING/bot-list/target-in-btc-and-eth
    TRADING/bot-list/symbol-opens-chart
    TRADING/bot-list/refresh-tick
    TRADING/bot-list/splitter-layout
TRADING/ta-voting-panel
    TRADING/ta-voting-panel/the-panel
    TRADING/ta-voting-panel/bot-picker
    TRADING/ta-voting-panel/timeframe-lock
    TRADING/ta-voting-panel/currency-rate-strip
    TRADING/ta-voting-panel/empty-state-says-why
TRADING/bot-controls
    TRADING/bot-controls/new-bot-button
    TRADING/bot-controls/creation-wizard
    TRADING/bot-controls/command-bar
    TRADING/bot-controls/fire-button
    TRADING/bot-controls/buy-confirmation-prompt
    TRADING/bot-controls/start-all-bots
    TRADING/bot-controls/trade-sound-cues
TRADING/bot-details
    TRADING/bot-details/the-window
    TRADING/bot-details/the-eight-pages
    TRADING/bot-details/clear-fold-tranches
    TRADING/bot-details/despawn-timer-rows
    TRADING/bot-details/self-destruct
TRADING/exchange-panels
    TRADING/exchange-panels/one-panel-per-exchange
    TRADING/exchange-panels/add-exchange
    TRADING/exchange-panels/data-pull-countdown
    TRADING/exchange-panels/news-ticker
    TRADING/exchange-panels/crypto-stock-toggle
    TRADING/exchange-panels/settings-dialog
    TRADING/exchange-panels/status-bar-indicators
TRADING/header-stat-strip
    TRADING/header-stat-strip/spendable-strip
    TRADING/header-stat-strip/scrummed-total
    TRADING/header-stat-strip/folded-total
    TRADING/header-stat-strip/trades-and-bots
    TRADING/header-stat-strip/errors-card
    TRADING/header-stat-strip/profit-loss-card
    TRADING/header-stat-strip/hides-on-simulator
TRADING/activity-and-api-logs
    TRADING/activity-and-api-logs/activity-log
    TRADING/activity-and-api-logs/activity-log-pause
    TRADING/activity-and-api-logs/activity-log-watchdog
    TRADING/activity-and-api-logs/api-log
    TRADING/activity-and-api-logs/api-log-pause
TRADING/privacy-controls
    TRADING/privacy-controls/privacy-mode-button
    TRADING/privacy-controls/button-label-matches-the-registry
    TRADING/privacy-controls/privacy-dots
    TRADING/privacy-controls/column-headers
TRADING/emitter-network
    TRADING/emitter-network/trading-pins
    TRADING/emitter-network/exchange-pins
    TRADING/emitter-network/pins-can-go-red
```

### Market Inspector — 7 framing, 33 functions

```
MKT-INSPECTOR/market-scan
    MKT-INSPECTOR/market-scan/refresh-button
    MKT-INSPECTOR/market-scan/freshness-line
    MKT-INSPECTOR/market-scan/cadence-hold
    MKT-INSPECTOR/market-scan/universe-choice
    MKT-INSPECTOR/market-scan/every-exchange
    MKT-INSPECTOR/market-scan/include-active-markets
    MKT-INSPECTOR/market-scan/include-stablecoins
    MKT-INSPECTOR/market-scan/timeframe-tickboxes
MKT-INSPECTOR/htf-signals-table
    MKT-INSPECTOR/htf-signals-table/the-table
    MKT-INSPECTOR/htf-signals-table/daily-and-weekly-columns
    MKT-INSPECTOR/htf-signals-table/monthly-column
    MKT-INSPECTOR/htf-signals-table/entry-strength-ladder
    MKT-INSPECTOR/htf-signals-table/signal-colour-cue
    MKT-INSPECTOR/htf-signals-table/already-trading-marker
MKT-INSPECTOR/opposing-pairs-table
    MKT-INSPECTOR/opposing-pairs-table/the-table
    MKT-INSPECTOR/opposing-pairs-table/correlation-maths
MKT-INSPECTOR/market-picture-panel
MKT-INSPECTOR/topology-proposals
    MKT-INSPECTOR/topology-proposals/proposal-cards
    MKT-INSPECTOR/topology-proposals/refresh-proposals
    MKT-INSPECTOR/topology-proposals/auto-refresh
    MKT-INSPECTOR/topology-proposals/momentum-funnel
    MKT-INSPECTOR/topology-proposals/type-filter
    MKT-INSPECTOR/topology-proposals/collapsible-card
    MKT-INSPECTOR/topology-proposals/dismiss-for-a-day
    MKT-INSPECTOR/topology-proposals/split-view-drag
MKT-INSPECTOR/adopt-and-push
    MKT-INSPECTOR/adopt-and-push/preview-window
    MKT-INSPECTOR/adopt-and-push/adopt-button
    MKT-INSPECTOR/adopt-and-push/warns-about-existing-wires
    MKT-INSPECTOR/adopt-and-push/undo-snapshot
    MKT-INSPECTOR/adopt-and-push/adoption-announcement
    MKT-INSPECTOR/adopt-and-push/push-into-simulator
    MKT-INSPECTOR/adopt-and-push/push-into-paper
    MKT-INSPECTOR/adopt-and-push/per-bot-view
MKT-INSPECTOR/emitter-network
    MKT-INSPECTOR/emitter-network/any-pin-at-all
```

### Bot Swarm — 9 framing, 39 functions

```
BOT-SWARM/bot-list
    BOT-SWARM/bot-list/rows
    BOT-SWARM/bot-list/ticker-column
    BOT-SWARM/bot-list/inflow-outflow-columns
    BOT-SWARM/bot-list/percent-out-column
    BOT-SWARM/bot-list/lane-columns
    BOT-SWARM/bot-list/exchange-filter
    BOT-SWARM/bot-list/view-switcher
    BOT-SWARM/bot-list/privacy-controls
    BOT-SWARM/bot-list/empty-message
BOT-SWARM/locust-grid
    BOT-SWARM/locust-grid/the-picture
    BOT-SWARM/locust-grid/animation
    BOT-SWARM/locust-grid/theme-picker
BOT-SWARM/wires-by-hand
    BOT-SWARM/wires-by-hand/drag-to-connect
    BOT-SWARM/wires-by-hand/right-click-disconnect
    BOT-SWARM/wires-by-hand/rate-dialog
    BOT-SWARM/wires-by-hand/removal-confirmation
    BOT-SWARM/wires-by-hand/opacity-slider
BOT-SWARM/quick-connect
    BOT-SWARM/quick-connect/source-and-destination-lists
    BOT-SWARM/quick-connect/rate-box
    BOT-SWARM/quick-connect/connect-button
    BOT-SWARM/quick-connect/disconnect-buttons
    BOT-SWARM/quick-connect/no-silent-refusals
BOT-SWARM/wire-persistence
    BOT-SWARM/wire-persistence/restored-on-launch
    BOT-SWARM/wire-persistence/shortfall-warning
BOT-SWARM/live-swarm-layer
    BOT-SWARM/live-swarm-layer/status-rows
    BOT-SWARM/live-swarm-layer/registration-pin
BOT-SWARM/simulator-swarm-layer
    BOT-SWARM/simulator-swarm-layer/rows-appear
    BOT-SWARM/simulator-swarm-layer/rows-clear-on-stop
    BOT-SWARM/simulator-swarm-layer/stop-all-button
    BOT-SWARM/simulator-swarm-layer/add-sim-bot-row
    BOT-SWARM/simulator-swarm-layer/summary-bar
BOT-SWARM/paper-swarm-layer
    BOT-SWARM/paper-swarm-layer/the-tab
    BOT-SWARM/paper-swarm-layer/add-a-paper-bot
    BOT-SWARM/paper-swarm-layer/start-button-trades
    BOT-SWARM/paper-swarm-layer/row-per-session
    BOT-SWARM/paper-swarm-layer/summary-bar
BOT-SWARM/emitter-network
    BOT-SWARM/emitter-network/sim-registration-pin
    BOT-SWARM/emitter-network/paper-registration-pin
    BOT-SWARM/emitter-network/pins-read-the-store-back
```

### Asset Charts — 6 framing, 27 functions

```
ASSET-CHARTS/the-chart
    ASSET-CHARTS/the-chart/a-chart-per-bot
    ASSET-CHARTS/the-chart/extractor-bots-excluded
    ASSET-CHARTS/the-chart/price-in-the-title
    ASSET-CHARTS/the-chart/volume-strip
ASSET-CHARTS/candle-feed
    ASSET-CHARTS/candle-feed/pair-follows-symbol
    ASSET-CHARTS/candle-feed/exchange-id-follows-symbol
    ASSET-CHARTS/candle-feed/source-order
    ASSET-CHARTS/candle-feed/source-and-error-line
    ASSET-CHARTS/candle-feed/timeframe-picker
    ASSET-CHARTS/candle-feed/hidden-charts-keep-fetching
    ASSET-CHARTS/candle-feed/nuclear-synthetic-feed
ASSET-CHARTS/indicator-overlays
    ASSET-CHARTS/indicator-overlays/bollinger-bands
    ASSET-CHARTS/indicator-overlays/ichimoku-cloud
    ASSET-CHARTS/indicator-overlays/macd
    ASSET-CHARTS/indicator-overlays/vortex
    ASSET-CHARTS/indicator-overlays/stochastic-rsi
    ASSET-CHARTS/indicator-overlays/missing-voting-indicators
    ASSET-CHARTS/indicator-overlays/renders-what-the-panel-computes
    ASSET-CHARTS/indicator-overlays/slingshot-and-bullseye
ASSET-CHARTS/bot-annotations
    ASSET-CHARTS/bot-annotations/trade-markers
    ASSET-CHARTS/bot-annotations/tranche-floor-lines
    ASSET-CHARTS/bot-annotations/target-balance-lines
    ASSET-CHARTS/bot-annotations/fire-armed-glow
ASSET-CHARTS/chart-navigation
    ASSET-CHARTS/chart-navigation/one-chart-at-a-time
    ASSET-CHARTS/chart-navigation/prev-next-with-the-ticker
    ASSET-CHARTS/chart-navigation/crosshair-zoom-pan
ASSET-CHARTS/emitter-network
    ASSET-CHARTS/emitter-network/chart-pins
```

### History — 6 framing, 21 functions

```
HISTORY/trade-list
    HISTORY/trade-list/from-the-exchange
    HISTORY/trade-list/the-table
    HISTORY/trade-list/cost-usd-column
    HISTORY/trade-list/summary-line
    HISTORY/trade-list/which-bot-made-it
    HISTORY/trade-list/only-live-bots
    HISTORY/trade-list/busy-bar-and-timeout
HISTORY/filters
    HISTORY/filters/refresh-button
    HISTORY/filters/refreshes-on-tab-open
    HISTORY/filters/date-range
    HISTORY/filters/exchange-symbol-and-side
    HISTORY/filters/apply-button
    HISTORY/filters/reset-button
HISTORY/trade-explanations
    HISTORY/trade-explanations/grade-column
    HISTORY/trade-explanations/gates-column
    HISTORY/trade-explanations/voting-column
    HISTORY/trade-explanations/hover-text
HISTORY/paging-and-export
    HISTORY/paging-and-export/paging
    HISTORY/paging-and-export/export-csv
HISTORY/feeds-the-simulator
    HISTORY/feeds-the-simulator/hands-over-ytd
HISTORY/emitter-network
    HISTORY/emitter-network/history-pins
```

### Simulator — 8 framing, 74 functions

```
SIM/bot-list
    SIM/bot-list/trading-tab-clone
    SIM/bot-list/legacy-fleet-table
    SIM/bot-list/active-bot-dropdown
    SIM/bot-list/bot-detail-dialog
    SIM/bot-list/live-bots-unreachable
    SIM/bot-list/fire-button-disabled
    SIM/bot-list/load-live-fleet
    SIM/bot-list/fleet-is-bot-state-only
    SIM/bot-list/smart-wires-import
    SIM/bot-list/spawn-drift-report
    SIM/bot-list/simulator-bot-state-file
    SIM/bot-list/per-symbol-trade-counts
    SIM/bot-list/stat-strip
SIM/ta-voting-panel
    SIM/ta-voting-panel/is-the-trading-tabs-panel
    SIM/ta-voting-panel/candle-count-matches-live
    SIM/ta-voting-panel/gate-lights
    SIM/ta-voting-panel/gate-status-pane
    SIM/ta-voting-panel/expand-button
SIM/vwap-playback
    SIM/vwap-playback/price-against-vwap
    SIM/vwap-playback/one-chart-at-a-time
    SIM/vwap-playback/thirty-frames-a-second
    SIM/vwap-playback/prev-next-ticker-row
SIM/tablet-candle-playback
    SIM/tablet-candle-playback/candles-play-back
    SIM/tablet-candle-playback/own-window
    SIM/tablet-candle-playback/trade-markers
    SIM/tablet-candle-playback/history-shading
    SIM/tablet-candle-playback/no-future-prices
    SIM/tablet-candle-playback/no-synthetic-fallback
    SIM/tablet-candle-playback/coverage-report
SIM/validation-mode
    SIM/validation-mode/start-replay
    SIM/validation-mode/stop-replay
    SIM/validation-mode/reset
    SIM/validation-mode/start-refuses-a-second-run
    SIM/validation-mode/bots-initialise
    SIM/validation-mode/replay-fires-trades
    SIM/validation-mode/fills-are-recorded
    SIM/validation-mode/venue-refuses-unfundable-order
    SIM/validation-mode/lotless-bot-opens-locked
    SIM/validation-mode/wallet-seed
    SIM/validation-mode/fee-matches-the-venue
    SIM/validation-mode/replay-progress
    SIM/validation-mode/parity-report
    SIM/validation-mode/parity-skipped-warning
    SIM/validation-mode/soft-start-cap
    SIM/validation-mode/full-evaluation-toggle
    SIM/validation-mode/fetch-ytd
    SIM/validation-mode/simulator-log
    SIM/validation-mode/run-folders
    SIM/validation-mode/never-touches-live
    SIM/validation-mode/data-validation-halt
SIM/backtest-mode
    SIM/backtest-mode/mode-is-selectable
    SIM/backtest-mode/mode-changes-behaviour
    SIM/backtest-mode/mode-hint-line
SIM/nuclear-mode
    SIM/nuclear-mode/panel
    SIM/nuclear-mode/runs-the-looped-controller
    SIM/nuclear-mode/old-scout-retired
    SIM/nuclear-mode/fleet-preview
    SIM/nuclear-mode/cycle-controls
    SIM/nuclear-mode/market-noise
    SIM/nuclear-mode/never-writes-the-tablets
    SIM/nuclear-mode/load-oscillation
    SIM/nuclear-mode/start-and-stop
    SIM/nuclear-mode/live-status
    SIM/nuclear-mode/drives-the-swarm
    SIM/nuclear-mode/topology-injection
    SIM/nuclear-mode/coverage-report
    SIM/nuclear-mode/cache-helper
SIM/emitter-network
    SIM/emitter-network/sim-pins
    SIM/emitter-network/fleet-pins
    SIM/emitter-network/count-matches-the-spec
    SIM/emitter-network/every-pin-has-a-row
    SIM/emitter-network/pins-carry-a-prediction
    SIM/emitter-network/operation-duration
    SIM/emitter-network/every-emitter-proved
```

### Console — 5 framing, 23 functions

```
CONSOLE/system-message-tail
    CONSOLE/system-message-tail/the-pane
    CONSOLE/system-message-tail/colour-by-severity
    CONSOLE/system-message-tail/indicator-highlight
    CONSOLE/system-message-tail/scrollback-limit
    CONSOLE/system-message-tail/follows-the-newest-line
    CONSOLE/system-message-tail/clear-button
    CONSOLE/system-message-tail/safe-from-worker-threads
    CONSOLE/system-message-tail/search-the-log
    CONSOLE/system-message-tail/filter-by-severity
    CONSOLE/system-message-tail/copy-or-save
CONSOLE/signals-pane
    CONSOLE/signals-pane/the-pane
    CONSOLE/signals-pane/pass-fail-marks
    CONSOLE/signals-pane/gap-marker
    CONSOLE/signals-pane/newest-200-per-tick
    CONSOLE/signals-pane/kept-on-disk
    CONSOLE/signals-pane/drag-the-divider
CONSOLE/pause
    CONSOLE/pause/pause-button
    CONSOLE/pause/quiets-both-panes
    CONSOLE/pause/buffered-count
    CONSOLE/pause/buffer-cap
    CONSOLE/pause/resume-delivers-the-backlog
CONSOLE/console-health-report
    CONSOLE/console-health-report/self-report
CONSOLE/emitter-network
    CONSOLE/emitter-network/console-pins
```

### Paper Trader — 9 framing, 32 functions

```
PAPER/the-tab
    PAPER/the-tab/tab-exists
    PAPER/the-tab/looks-like-trading
    PAPER/the-tab/header-strip-hides
    PAPER/the-tab/own-stat-strip
    PAPER/the-tab/crypto-equity-wing-swap
    PAPER/the-tab/launcher-claim
PAPER/bot-list
    PAPER/bot-list/bots-from-a-fleet-load
    PAPER/bot-list/own-bot-manager
    PAPER/bot-list/mirror-live-bots
PAPER/ta-voting-panel
    PAPER/ta-voting-panel/same-panel-as-live
PAPER/real-time-data-feed
    PAPER/real-time-data-feed/live-prices
    PAPER/real-time-data-feed/simulator-continues-as-paper
PAPER/paper-venue
    PAPER/paper-venue/fake-fills
    PAPER/paper-venue/fill-model-choice
    PAPER/paper-venue/fees-charged
    PAPER/paper-venue/paper-mode-value
    PAPER/paper-venue/same-trading-logic
    PAPER/paper-venue/equity-paper-trader
    PAPER/paper-venue/broker-paper-endpoint
PAPER/paper-wallet
    PAPER/paper-wallet/shared-balance
    PAPER/paper-wallet/starting-funds-editable
    PAPER/paper-wallet/budget-is-double-the-target
PAPER/paper-logs
    PAPER/paper-logs/activity-log
    PAPER/paper-logs/state-survives-restart
    PAPER/paper-logs/isolated-from-live-state
PAPER/swarm-layer
    PAPER/swarm-layer/the-tab
    PAPER/swarm-layer/add-a-paper-bot
    PAPER/swarm-layer/start-button-trades
    PAPER/swarm-layer/row-per-session
    PAPER/swarm-layer/portfolio-summary
    PAPER/swarm-layer/market-inspector-pushes-here
PAPER/emitter-network
    PAPER/emitter-network/run-registration-pin
```

### Proof of Accumulation — 9 framing, 0 functions

```
PROOF-OF-ACCUMULATION/bot-identity
PROOF-OF-ACCUMULATION/tamper-proof-trade-log
PROOF-OF-ACCUMULATION/head-to-head-match
PROOF-OF-ACCUMULATION/season-schedule
PROOF-OF-ACCUMULATION/token-award
PROOF-OF-ACCUMULATION/leaderboard
PROOF-OF-ACCUMULATION/trophy-artwork
PROOF-OF-ACCUMULATION/network-connection
PROOF-OF-ACCUMULATION/patent-record-intact
```

### System Status — 9 framing, 0 functions

```
SYSTEM-STATUS/the-tab-itself
SYSTEM-STATUS/health-colour-per-subsystem
SYSTEM-STATUS/the-snapshot-report
SYSTEM-STATUS/matching-log-format
SYSTEM-STATUS/group-by-subsystem-and-tab
SYSTEM-STATUS/hang-detection
SYSTEM-STATUS/watchdog-feed-moves-here
SYSTEM-STATUS/emitter-id-to-name
SYSTEM-STATUS/logs-correlate-to-emitters
```
