# Development map, 8 September 2026

Reference. A dated skeleton of this project from 10 April 2026 to today, built
from artefacts rather than from recollection. It is evidence for a later
narrative, not the narrative.

Every row names the artefact that dates it, and says whether the date is
**recorded** — an artefact states it — or **inferred** — no artefact states it,
and code or a file date implies it.

The repository holds only the last three weeks. `git log` on `origin/current`
begins on 18 August 2026, so four months of work arrived as two commits and
carry no per-change history. Those four months are reconstructed below from
seven other sources, and the strongest of the seven is the code itself.

## The seven sources

Each source has a reach and a limit, and the limits decide which rows read
*inferred*.

| Source | Reach | What it cannot do |
| ------ | ----- | ----------------- |
| Version numbers and operator directives written into code comments | 20 April to today | It dates a file, not a decision, and only where somebody wrote the date down |
| The operator's pre-git build archive | 10 to 24 April | It ends on 24 April. It holds builds, not decisions |
| `docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md` | 11 April to 9 June | A summary of conversations this repository does not hold. It names its own gaps |
| The six handoff files at the repository root | 18 April to 3 September | One of them carries 212 dated entries; the other five are single points |
| The dated audit directories inside the first commit | 14 June, 24 July to 15 August | Emptied from the tree on 26 August, restored on 27 August, lost again in a merge on 28 August. Read from the commits |
| `docs-archive/llm-session-history/CHANGELOG-narrative-2026-08-04-to-2026-08-25.md` | 4 to 25 August | Its own window. Dates outside it appear only as citations |
| File names and dates under the runtime directory, and `git log` | 14 April to today, and 18 August to today | A file date is one point and names no decision |

### Checking a source before using it

Three checks were run, and one of them threw a source out.

**The build archive is dated two ways and the two agree.** The folder date of
the earliest build reads 11 April. The newest file stored inside that same
build reads 11 April, 19:19. The archive chronicle's first session stamp reads
11 April, 19:41. Three readings, two sources, one hour. Each build's version
was then read from inside the build rather than from its name, and name and
content agree on every build read.

**The handoff protocol has the same double reading.** The archive chronicle
records it invented and released on 16 April. The archived package that holds
it carries a stored file time of 16 April, 14:59.

**Source-file dates were tried and rejected.** A reading taken in the
operator's own working copy gives five package roots a date of 23 April, which
would place the whole source layout in that week. The same five files in a
fresh checkout of the same commit all read today's date, because a checkout
writes them. The date is a fact about one disk, not about the project, so no
row below rests on one.

## Coverage

| Span | Days | Reconstructed from |
| ---- | ---: | ------------------ |
| 10 to 28 April | 19 | Build archive, archive chronicle, four handoffs, one review, code comments |
| 29 April to 18 May | 20 | Two dated directives in the tree. Sixteen days blank |
| 19 to 25 May | 7 | Handoff 5, archive chronicle, the watchdog's own comments |
| 26 to 29 May | 4 | **Nothing** |
| 30 May to 9 June | 11 | Handoff 5, archive chronicle, code comments. Three days blank |
| 10 to 26 June | 17 | Code comments, three tracked backup files, one test's own record. Eight days blank |
| 27 June to 23 July | 27 | **Nothing** |
| 24 July to 15 August | 23 | Audit directories inside the first commit, plus code comments. One day blank |
| 16 to 17 August | 2 | Handoff 7 |
| 18 August to 8 September | 22 | 1,699 commits, 208 issues |

Sixty-one of those 152 days carry no usable record, and the largest single
blank runs 27 June to 23 July.

---

## Before the first session

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-04-01 | The date the running product treats as the platform launch. Two screens and one fetcher default to it | `src/gui/history_tab.py` line 119 and `src/trading/stone_tablets/fetcher.py` line 36 | recorded |
| 2026-04-10 | The earliest file date the project carries. Every archived build stores the same oldest member, 10 April 18:18 | Stored member times, read from every build in the pre-git archive | recorded |

## 11 to 15 April — five days, seventeen sessions

The archive chronicle closes this era with its own count: seventeen
conversations, about 27 MB of them, five days, 74 Python files, about 34,000
lines. The work ran inside a chat window with no access to the file system, so
each session began by uploading a zip of the code.

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-04-11 | First session. A grid bot, then the Scrumming Bot, then a seven-indicator voting engine, the Phantom Balance idea, a Qt window and a build script | Archive chronicle lines 13 to 26 | recorded |
| 2026-04-11 | The project's first name is not Acervator. Sixteen builds stored this day carry the earlier product name | Build archive, versions 1.2 through 2.0.2 | recorded |
| 2026-04-12 | The exchange connection, through a market library | Archive lines 30 to 42 | recorded |
| 2026-04-12 | The Landing Strip first observed, as tightening candles at a Bollinger edge | Archive lines 78 to 86 | recorded |
| 2026-04-12 | Scrum and fold found inverted and corrected. The archive calls it the most consequential defect in the project | Archive lines 90 to 101 | recorded |
| 2026-04-13 | Equities added beside crypto | Archive lines 134 to 146 | recorded |
| 2026-04-14 | The targeting state machine — search, track, fire. The archive heading calls this the pivotal session | Archive lines 194 to 202 | recorded |
| 2026-04-14 | Position-aware technical analysis | Archive lines 211 to 219 | recorded |
| 2026-04-14 | The Smart Wire, moving realised profit between bots | Archive lines 250 to 263 | recorded |
| 2026-04-14 | The runtime directory's first three folders: journal, logs and recovery | Runtime directory listing | recorded |
| 2026-04-14 | Last build stored under the earlier product name, at 22:03 | Build archive | recorded |
| 2026-04-15 | First build stored under the name Acervator, at 01:35. The rename falls between those two times | Build archive; archive lines 272 to 283 | recorded |
| 2026-04-15 | The code folder keeps the old name after the product changes it. One build in the next two days has a top folder reading Acervator, and the builds after it revert | Top folder names read from each stored build | recorded |
| 2026-04-15 | Every session opens by uploading a zip of the chronicle and the code, because the session cannot read files | Archive lines 424 and 453 to 457 | recorded |

## 16 to 28 April — the protocol era

This is where the method around the work was invented, and the artefacts for it
are unusually good.

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-04-16 | The generational handoff protocol written and released. An archived package holds a 38,903-byte protocol document, a template and two readme files | Build archive package stored 16 April 14:59; archive lines 482 to 487 | recorded |
| 2026-04-16 | Its stated purpose: a fresh session has no memory, so one markdown file at the project root carries the vocabulary and the invariants forward. The name that release gives that file was never committed here and is not in the tree | Readme inside the archived package | recorded |
| 2026-04-16 | The same readme introduces numbered rules — write one whenever a class of silent defect is fixed, and never delete one | Readme inside the archived package | recorded |
| 2026-04-16 | The first numbered rule the chronicle records, written straight after a defect | Archive line 574 | recorded |
| 2026-04-16 | Simulator log folder created under the runtime directory | Runtime directory listing | recorded |
| 2026-04-17 | The rule taxonomy: groups A to F over twenty-seven rules, because an ungrouped list was a load nobody could hold | Archive lines 791 and 813 to 814 | recorded |
| 2026-04-17 | The chronicle rule added, retroactively, making a chronicle entry mandatory at session close | Archive lines 725 to 727 | recorded |
| 2026-04-17 | The development protocol first appears, already named, as a session title. The archive records no session that created it | Archive line 997 | recorded |
| 2026-04-18 | The rules registry becomes a module, every rule locked by default, on the reasoning that a rule accidentally unenforced is worse than one accidentally enforced | Archive lines 861 to 881; `src/core/rule_registry.py` | recorded |
| 2026-04-18 | Handoff 2, at engine version 3.8.0 | `ACERVATOR_HOP2.md` line 4 | recorded |
| 2026-04-19 | The version reads 3.14.0, then 3.19.0, 3.21.0, 3.24.0 and 3.25.0 across twelve hours, then 3.9.0 at 20:15 the same day | Six archived builds, version read from each build's own entry point, ordered by stored file time | recorded |
| 2026-04-19 | Why the number went back | No artefact states it | **inferred** — both handoffs written that day and the next read 3.9.0, so the lower number is the one the project kept |
| 2026-04-19 | Handoffs 3 and 4, at engine version 3.9.0. Both still carry handoff 2's sentence saying two handoffs are complete | `ACERVATOR_HOP3.md` and `ACERVATOR_HOP4.md`, lines 4 and 8 | recorded |
| 2026-04-19 | Historical candle cache created under the runtime directory | Runtime directory listing | recorded |
| 2026-04-20 | Ten named reviewers audit the trading logic. Six call it work in progress; four would not trust capital to it. Live decisions used Bollinger Bands alone, at a fixed two per cent delta, with fifteen bots running | `ACERVATOR_DEPT_LEAD_REVIEW_v3_12_0.md` lines 2, 13 to 26, 199 and 364 to 368 | recorded |
| 2026-04-20 | That review proposes seven rules and none of the numbers survives. The one it proposes first is taken by an unrelated rule the next day | Review lines 335 to 362; `ACERVATOR_HOP5.md` line 3299 | recorded |
| 2026-04-20 | The chronicle found neglected for every release since 19 April, and back-filled in one pass covering twenty-six versions | Archive lines 2141 to 2145 and 2154 to 2162 | recorded |
| 2026-04-20 | The one live technical finding salvaged out of the whole pre-git archive | `docs/engineering-notes/2026-04-20_local_testnet_instances_are_never_shared.md` | recorded |
| 2026-04-21 | Six rules born in one day, on freshness, error grouping, failure counting and handoff discipline | `ACERVATOR_HOP5.md` lines 3763 to 4055 | recorded |
| 2026-04-21 | Seven tabs struck out of the main window. Their names are still assigned to nothing today | Archive chronicle line 5688; `src/gui/main_tabs/retired_tabs.py` | recorded |
| 2026-04-21 | The local chain and the market map cache first written | Runtime directory listing | recorded |
| 2026-04-23 | Two memory records give this day as a ship date, at engine version 3.15.39 | `ACERVATOR_HOP5.md` lines 7425 and 7437 | recorded |
| 2026-04-24 | The last build in the pre-git archive, and handoff 5's last entry before its first blank span | Build archive folder listing; `ACERVATOR_HOP5.md` line 7456 | recorded |
| 2026-04-25 | An operator directive still quoted in the fold arithmetic | `src/trading/otd_math.py` line 6 | recorded |
| 2026-04-26 | An operator directive that timeframe choices must follow what each venue offers, at engine version 3.15.61. It is quoted in two files | `src/exchange/timeframes.py` lines 2 to 6; `src/gui/bot_wizard.py` line 1417 | recorded |
| 2026-04-28 | The archive chronicle's last date before the first blank span | Archive date histogram | recorded |

## 29 April to 18 May — two dated points in twenty days

The archive chronicle jumps this span. Handoff 5 jumps it. The build archive
ended on 24 April. Two comments in the running code are the only evidence.

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-05-06 | A directive that the activity log should raise a warning when it stops spooling | `docs/engineering-notes/2026-08-25_subsystem_capability_matrix.md` line 671 | recorded |
| 2026-05-10 | A directive that anything the venue reports about position health must not be recomputed locally, at engine version 3.16.46. The module it produced is in the tree | `src/exchange/position_health.py` lines 1 to 5 | recorded |
| between 2026-04-26 and 2026-05-10 | The grid bot deleted, at engine version 3.16.0. It is not in the tree, and no commit ever added it. A comment about a removed table is the only record that it existed | `src/gui/live_settings/status_tab.py` lines 113 to 114 | **inferred** — the version sits between two dated versions |
| late April or early May | Per-run log rotation added at engine version 3.18.5, without a cap on how many crash bundles accumulate | `acervator_watchdog.py` lines 373 to 378 | **inferred** — the comment says the bundles built up over weeks before 20 May |

The engine versions 3.16 through 3.19 all belong to this span and the week after
it. Three whole minor series in under three weeks makes it the fastest-moving
stretch in the record, and the least documented.

## 19 May to 9 June

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-05-19 | The record resumes, with a Simulator tab skeleton | `ACERVATOR_HOP5.md` line 7140; archive line 17078 | recorded |
| 2026-05-20 | The log directory reaches about 400 gigabytes and crashes the machine. Three retention limits are written the same day, at engine version 3.19.5, and the cause is named in the comment above them | `acervator_watchdog.py` lines 373 to 391 | recorded |
| 2026-05-20 | The paper-trading state file first written | Runtime directory listing | recorded |
| 2026-05-20 | Twenty entries in one day. A declarative gate-chain framework replaces scattered checks, and twenty-four standing test failures close | `ACERVATOR_HOP5.md` lines 7208 to 7676; archive lines 17217 to 17253 | recorded |
| 2026-05-20 | The Extractor Bot skeleton and its four-state machine | Archive lines 17423 to 17463; `src/trading/extractor_bot.py` | recorded |
| 2026-05-21 | Handoff 5's header stops being rewritten. Its body runs on for another eighty-three entries and nineteen days | `ACERVATOR_HOP5.md` lines 10 and 12 against line 11226 | recorded |
| 2026-05-22 to 05-25 | The densest stretch in the pre-git record: sixty-nine entries in four days | `ACERVATOR_HOP5.md` lines 7991 to 11011 | recorded |
| 2026-05-25 | A directive on bot fitness, at engine version 3.20.35 | `src/gui/live_bot_window.py` lines 338 to 340 | recorded |
| 2026-05-26 to 05-29 | Four days with no entry anywhere | Archive date histogram; handoff 5 entry series | **gap** |
| 2026-05-30 | One entry, closing an arc over the bot configuration | `ACERVATOR_HOP5.md` line 11124 | recorded |
| 2026-06-01 | A capital registry, a trade-grading library and an arbiter across bots | Archive lines 18475 to 18690 | recorded |
| 2026-06-02, 06-03, 06-07 | Three single blank days inside an otherwise continuous run | Archive date histogram | **gap** |
| 2026-06-05 | A fix claimed and then retracted. The first attempt's tests searched the source for words rather than running the code, so they could not see the words were wired to the wrong signal | Archive lines 18605 to 18607 | recorded |
| 2026-06-05 | A web address invented from an email handle, shipped into twenty-five files and one published package | Archive lines 18585 to 18587 | recorded |
| 2026-06-08 | The exchange credential file written | Runtime directory listing | recorded |
| 2026-06-08 | A measurement reported as a negative result, with the number that went backwards stated rather than hidden | Archive lines 18732 to 18734 | recorded |
| 2026-06-09 | A directive to put every log under one labelled root. The module it produced names the four roots it replaced | `src/core/log_paths.py` lines 3 to 31 | recorded |
| 2026-06-09 | Unverified work removed rather than shipped. The removal broke fifty-four tests before it was corrected, and the suite fell by eighty-seven | Archive lines 18795 to 18811 | recorded |
| 2026-06-09 | The last dated entry in both the archive chronicle and handoff 5 | Archive tail; `ACERVATOR_HOP5.md` line 11226 | recorded |

## 10 to 26 June — the code speaks and the documents stop

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-06-10 to 06-13 | The gate log writer stalls for four days. A rename that Windows refuses is the cause, and a test still carries the dates | `tests/test_system_log_bounded.py` lines 199 to 201 | recorded |
| 2026-06-14 | Three interface files copied beside their originals, each backup named for the arc that was open: a swarm arc, a history arc and a privacy arc. All three were tracked in git and were deleted on 22 August | Three backup file names inside commit `6e4f46b8`; `d4d4dde1` | recorded |
| 2026-06-15 | Two recorded buys, later used to test whether candle history could be reproduced | Narrative changelog lines 4195 to 4196 | recorded |
| 2026-06-16 | A directive on the identifier dot and privacy mode in the bot list | `docs/engineering-notes/2026-08-25_subsystem_capability_matrix.md` line 888 | recorded |
| 2026-06-18 | The macOS build description found rotted, after about two months untouched | `tests/test_specs_parity.py` line 5 | recorded |
| 2026-06-18 | A directive that no part of the earlier development protocol is valid or working. Two modules totalling 2,586 lines were built around it and nothing imports either today | `src/core/version_sweep.py`, `src/core/rule_registry.py` | recorded |
| 2026-06-26 | A market's stored candle history begins | `src/trading/stone_tablets/addressing.py` line 46 | recorded |

## 27 June to 23 July — nothing

Twenty-seven days, the largest single blank in the record. No commit, no
handoff, no audit, no runtime file and no dated comment falls inside it.

The record says where it went. The narrative changelog opens by stating that
the changelog was moved under an archive folder during the 3.23 series and never
replaced at the root, so the releases after it shipped with that step skipped.
That archived file was never committed here and is not in the tree. A history
query for it across every branch returns nothing, against the same query for a
known file, which returns its commit.

## 24 July to 15 August — recovered from a commit

The first commit carries a documentation folder that a later commit emptied.
Inside it sit ninety-three dated audit units, one per piece of work, covering
this span day by day. It is the densest record of the pre-git summer.

That folder has an unusual history worth stating plainly. It was emptied on
26 August, restored on 27 August into a different directory, and lost again on
28 August inside two merge commits that reconciled two branches. A plain delete
query does not see the second loss, because the deletion happened in a merge.
Today one pre-August note survives in the tree. The other 115 are readable from
commit `fc0d7788`, which is an ancestor of the current branch.

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-07-24 | The review archetypes tested against a known-good and known-bad pair, judged by two peer reviewers. Three audits that day: the coding archetype, then the interface and documentation archetypes, then a review of which earlier features were worth rebuilding | Three audit folders in `6e4f46b8` and `fc0d7788` | recorded |
| 2026-07-25 | The bot settings and status screens audited field by field, and a replay of year-to-date compounding, at engine version 3.23.23 | Four audit units, and one image whose name carries the version | recorded |
| 2026-07-26 | Nine audits in one day, walking the wizard panels: swarm, tranches, hedge rebalance, circuit breakers, the danger zone, risk controls, the extractor pool | Nine audit files in those commits | recorded |
| 2026-07-27 | Three design proposals: settlement across base currencies, the Market Inspector, and the phantom bots | Three audit files in those commits | recorded |
| 2026-07-28 | A whole-codebase archetype audit, and prior-art research on coordinating bots across base currencies. The module it produced names both documents and its own version, 3.23.47 | `src/exchange/market_pairs_scout.py` lines 8 to 15 | recorded |
| 2026-07-28 | A directive that clicking a symbol should open that venue's chart | `src/exchange/exchange_chart_urls.py` line 4 | recorded |
| 2026-07-30 | A wall of errors begins in the console log. It is still there when it is described five weeks later | Narrative changelog line 1338 | recorded |
| 2026-07-31 | The operator flags a rate saturation against the venue. The ceiling written for it is in the tree | `src/gui/widgets/exchange_tab.py` line 99; `src/exchange/api_load_monitor.py` lines 20 to 21 | recorded |
| 2026-07-31 | Topology proposals designed, at engine version 3.23.67, and the Smart Wire's outflow arithmetic checked. Two data files and one module still cite that design | `src/trading/sector_map.json` line 3; `src/gui/market_inspector_topologies.py` line 6 | recorded |
| 2026-08-01 | Three archetype rules written in one day: hallucination, scaffolding and slop, at engine versions 3.23.90 and 3.23.92. They are in the tree | `dev_harness/harness/rules/__init__.py` line 4; `dev_harness/harness/rules/slop.py` line 5 | recorded |
| 2026-08-01 | The stone tablets rebuilt in the tree, at engine version 3.23.97, after the earlier archive was purged. The runtime folder is created the same day | `src/trading/stone_tablets/__init__.py` lines 3 to 6; runtime directory listing | recorded |
| 2026-08-03 | Orphan reservations quarantined out of the live reservation state | Runtime file names written that day | recorded |
| 2026-08-04 | A full-codebase defect scan, a complexity inventory and a time-and-space audit, in one day | Seven audit files in those commits | recorded |
| 2026-08-05 | The Paper Trader specified as a concept, and a repair method written down | Nine audit files in those commits | recorded |
| 2026-08-06 | Fourteen audits, the heaviest single day in the pre-git record. Their titles are mostly defects and their subject is mostly the tranche lifecycle | Fourteen audit files in those commits | recorded |
| 2026-08-07 | Twenty-four releases in one day, each closing one numbered defect, and an audit titled for the traps that pass a naive test | Narrative changelog lines 2314 to 3485 | recorded |
| 2026-08-09 | Two operator rules land and reshape everything after them: one entity writes arithmetic, one entity writes code and must check all of it | Narrative changelog lines 771 and 833 | recorded |
| 2026-08-10 | The operator's rule against connecting to dead code. One release then deletes 457 lines with no change in behaviour | Narrative changelog lines 696 to 704 | recorded |
| 2026-08-11 | Two trees report the same version and are not the same code. Three releases exist only to close that | Narrative changelog lines 481 to 484 | recorded |
| 2026-08-13 | A prediction written down before the run that would test it | One audit file in those commits | recorded |
| 2026-08-15 | The last dated audit before the move to GitHub | One audit file in those commits | recorded |

## 16 and 17 August — the move

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-08-16 | Handoff 7 rewritten, after the migration to GitHub was performed and verified. It records why the earlier handoffs stopped: append-only, over 100 KB, abandoned | `ACERVATOR_HOP7.md` lines 3 and 6 to 10 | recorded |
| 2026-08-16 | Handoff 7 also carries entries dated 19 August, so it was edited after its own stated rewrite date | `ACERVATOR_HOP7.md` lines 142 and 239 | recorded |

## 18 August to 8 September — git

1,699 commits on `origin/current` across twenty-two consecutive days, no day
missing. Two root commits rather than one: the same message, the same author
and the same second. Every commit of the first days exists twice, once on each
line, and the two were joined on 19 August.

| When | What | Evidence | Confidence |
| ---- | ---- | -------- | ---------- |
| 2026-08-18 | Four months of work arrive as one import: 650 files, 315,743 lines, 239 test files, the four archetypes already built | `6e4f46b8` and its twin `be6aa048` | recorded |
| 2026-08-18 | Nothing dated before 24 July shipped in that import, apart from the three June backup files | Dated file names inside `6e4f46b8` | recorded |
| 2026-08-18 | The version the import carries. A one-line file states the assignment, and that file is not in the tree today | `git show 6e4f46b8:ver.txt` reads 3.25.5, three patches behind the module beside it | recorded |
| 2026-08-19 | The first green release check recorded against a commit rather than a folder | `ACERVATOR_HOP7.md` lines 239 to 243 | recorded |
| 2026-08-19 | A wrapper and a push hook added the same day, after a documentation branch merged on reasoning rather than on measurement. Neither the hook nor its stamp is in the tree | `8abc29c8` | recorded |
| 2026-08-22 | An outside audit files issues 66 to 96, the first review by anyone but the operator and the builder. Its first finding is that the history offers no bisect, blame or revert trail | Issues 66 to 96 | recorded |
| 2026-08-22 | One version, one name. The one-line version file deleted | `8d34036e` | recorded |
| 2026-08-23 | The island tool retired on the operator's ruling that git, branches and issues had replaced it. Neither the tool nor its ledger is in the tree | `3e76e204` | recorded |
| 2026-08-25 | A second engineer's lint and build-service sweep reformats 464 files and moves all testing into the build service | `9510ce6e` | recorded |
| 2026-08-25 | That sweep moved anchors and emptied five test modules. Both were repaired the same day, and the deleted chronicle restored | `87e7ec22` and `032ba3c2` | recorded |
| 2026-08-25 | The Qt-to-React conversion opens as an item and becomes the largest arc in the repository | Issue 128 | recorded |
| 2026-08-25 | The handoff files deleted on the reasoning that they belong to one engineer | `36c2e4f8` | recorded |
| 2026-08-26 | The push hook removed on the reasoning that the build service replaces it. It is not in the tree | `8b7097b7` | recorded |
| 2026-08-26 | The documentation folder emptied: 135 files, 131 of them dated. The commit message calls the folder an invented history with no value | `c932a06e` | recorded |
| 2026-08-27 | The version stops being written and starts being derived from the git tag, or from the value a frozen build baked in | `ef105f55`; `src/_version.py` | recorded |
| 2026-08-27 | The summer audits sorted back into the tree as engineering notes | `fc0d7788` | recorded |
| 2026-08-28 | Those notes lost again, inside two merges reconciling two branches. The loss is invisible to a plain delete query | `5e80a361` and `58b6e77f` | recorded |
| 2026-08-28 | The first version tag in the project's life reads 0.1.0. The number restarts below one, four months after the private ladder passed three | `git tag` | recorded |
| 2026-08-28 | The Electron shell and its boundary to Python. It carries none of the older comment conventions | `21dfbeb6` | recorded |
| 2026-08-28 | The build service is recorded as never having run on the branch the work happens on | Issue 152 | recorded |
| 2026-09-03 | The build service unavailable until 1 October, and a local replacement written | Issue 331 and `e7ee58d6` | recorded |
| 2026-09-03 | The handoff archive restored to the tree, byte for byte | `4520c840` | recorded |
| 2026-09-03 | Handoff drift becomes a measurement rather than a habit | `bce8be05` and `tools/hop_check.py` | recorded |
| 2026-09-03 | Handoff 8 written, closing session 27. Second version tag, 0.2.0 | `576efc9a`; `git tag` | recorded |
| 2026-09-04 | The product manual extracted from its PDF into markdown, then rebuilt back to PDF by a tool that checks its own output | `aea80734` and `cd0563a8` | recorded |
| 2026-09-05 | The heaviest day in the repository: 265 commits | Commit date histogram | recorded |
| 2026-09-06 | 576 test files removed on one branch, on the finding that they read the source of the code under test rather than running it. That branch has not merged into `origin/current` | `05449360`, not an ancestor of `origin/current` | recorded |
| 2026-09-07 | A defect that had been written into a docstring and left in place is removed. Under it, every indicator had been reading a candle window fifty five-minute bars behind the price | `b106df73`; `docs/audits/2026-09-07_ta_window_lag.md` | recorded |
| 2026-09-07 | The Simulator cut back to an empty tab: 103 files, 63,048 lines removed | `e568197b` | recorded |
| 2026-09-08 | The manual PDF built from every page the manifest lists | `a8e7439c` | recorded |

## Spans nothing reconstructs

| Span | Days | What was looked at |
| ---- | ---: | ------------------ |
| 2026-04-29 to 05-05, 05-07 to 05-09, 05-11 to 05-18 | 16 | Archive chronicle and handoff 5 both jump the whole span. Build archive ended 24 April. Two directives inside it are dated, and nothing else |
| 2026-05-26 to 2026-05-29 | 4 | Absent from the archive histogram and from handoff 5's entry series, between two dense weeks |
| 2026-06-02, 06-03, 06-07 | 3 | Single days missing from an otherwise continuous run |
| 2026-06-17, 06-19 to 06-25 | 8 | Between two dated code comments, with nothing in between |
| 2026-06-27 to 2026-07-23 | 27 | The largest blank. The changelog for this period was moved to an archive file that was never committed here, and the audit folders in the first commit begin on 24 July |
| 2026-07-29 | 1 | One day between two dated audits |

## Where the record contradicts itself

Seven disagreements. None is resolved here, because choosing a side would put
an invented fact in the map.

| The disagreement | Side one | Side two |
| ---------------- | -------- | -------- |
| Which session first observed the Landing Strip | The archive's narrative puts it in the fifth session listed, on 12 April | The archive's own formal record calls it session 4 |
| Which session introduced the Phantom Balance | The archive's first-session summary | The archive's formal record calls it session 2 |
| Whether handoff 5 ever existed | Handoff 7 states it was cited for months and never existed | It is in the tree, 11,445 lines, and it was in the very first commit under an archive folder |
| How large the early handoffs grew | Handoff 7 blames a size past 100 KB for killing the format | Handoff 2 is 84 KB and never reached it, and handoff 5 is 712 KB, six times the threshold |
| Which engine version carried protocol release 1.14 | Handoff 5 places it at engine 3.10.1 | The department-lead review places it at engine 3.12.0. Seven releases sit between them and none records a protocol change, so both may hold |
| Whether the pre-git documents are a record at all | Ninety-three dated audit units, each naming files and versions that check out against the code | The commit that emptied them calls the folder an invented history with no value |
| What version the project is on | The running code derives 0.2.0 from the git tag | The imported one-line file read 3.25.5, the narrative changelog reaches 3.27.0, and the operator's own session naming reads 3.25.8 |

Four further oddities are recorded rather than reconciled.

Handoff 5's own header disagrees with its own body, and the file predicts that.
It says the header is rewritten at the end of every release cascade, and that a
reader who finds the header out of step with the last entry should trust the
body. The header says 129 entries; the body carries 212. It says the last thing
landed on 21 May; the body runs to 9 June.

The session numbers are not a clock. Handoff 5's entries run through sessions 18
to 22, then 24, then 26, then jump to 72, then return to 26. Sessions 23 and 25
have no entries at all, although the file refers to an incident in session 25.
Dates order this record; session numbers do not.

Handoff 6 is missing because it never existed. A history query across every
branch for a file of that name returns nothing, against the same query for
handoff 7 returning seven commits. Both later handoffs record that a first draft
of the sixth absorbed the standing queue, reached 2,085 lines and became the
thing it was written to replace. It was discarded before it reached git.

Engine versions 3.21 and 3.22 appear nowhere in the tree. Not one comment names
either. They sit inside the twenty-seven-day blank, and either the series were
skipped or every file touched during them has since been rewritten.

## What this map is not

It is not a history of trading results, and it carries no fill, price, size,
balance or account identifier. It is not a description of the product; the
product manual holds that. It does not decide which side of any disagreement
above is true.

The one claim it makes is that every date in it can be checked against a named
artefact, and that the sixty-one days marked blank are blank in the record, not
in the work.
