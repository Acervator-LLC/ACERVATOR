---
name: acervator
description: The address book. Where every fact about this product lives — the manual page, the issue, or the skill. Load it to find the source, never to learn the fact.
---

# Acervator — the address book

**This file holds no facts about the product.** It holds addresses. A fact read
here instead of at its address is a second grounding point, and a second
grounding point drifts. Read the address.

Operator, 2026-09-06: *"You ground to Issues and the Product Manual ONLY."*

Three sources, and nothing else:

```
the issue           what the work is        gh issue view <n>
the Product Manual  what the product is     docs/manual/
the skills          how the work is done    loaded by name
```

Skill: `ground-to-issue-and-manual` states the rule this file obeys.

## Who

Anthony L. Brown, project handle **Ekthelius the Accumulator**, sole owner and
sole operator. He directs the product and he does not read code. Bring him what
works, what matches the specification, and what is worth doing.

## The Product Manual — what the product is

| page | what it addresses |
|---|---|
| `docs/manual/README.md` | the manual's own map |
| `docs/manual/03-executive-summary.md` | what the platform is |
| `docs/manual/04-manual-parts.md` | how the manual is organised |
| `docs/manual/05-novel-concepts.md` | the concepts this product invented, PhantomBots among them |
| `docs/manual/06-trading-tab.md` | the Live tab and the hedge |
| `docs/manual/07-indicators.md` | every indicator, and the gate chain |
| `docs/manual/08-tabs.md` | the tab set, and the table of every converted file |
| `docs/manual/09-updates-and-versioning.md` | versions and the release cascade |
| `docs/manual/10-live-trade-history.md` | the trade record |
| `docs/manual/11-hop-protocol-and-rules-registry.md` | the handoff protocol |
| `docs/manual/12-adr-index-and-glossary.md` | decisions and vocabulary |
| `docs/manual/13-live-evidence.md` | evidence from live running |
| `docs/manual/14-development-chronicle.md` | the history |
| `docs/manual/FIGURES.md` | the figures the manual embeds |

One page per tab:

| tab | page |
|---|---|
| Charts | `docs/manual/08-tabs/asset-charts.md` |
| Swarm | `docs/manual/08-tabs/bot-swarm.md` |
| Console | `docs/manual/08-tabs/console.md` |
| History | `docs/manual/08-tabs/history.md` |
| Inspector | `docs/manual/08-tabs/market-inspector.md` |
| Paper | `docs/manual/08-tabs/paper-trader.md` |
| the portfolio panels | `docs/manual/08-tabs/portfolio-panels.md` |
| the promotion pipeline | `docs/manual/08-tabs/promotion-pipeline.md` |
| Accumulation | `docs/manual/08-tabs/proof-of-accumulation.md` |
| Settings | `docs/manual/08-tabs/settings.md` |
| Sim | `docs/manual/08-tabs/simulator.md` |
| Status | `docs/manual/08-tabs/system-status.md` |
| the tab index | `docs/manual/08-tabs/README.md` |

**The table of every converted file lives in `docs/manual/08-tabs.md`**, one row
per file, with its module, its bridge method, its manifest entry, whether it
registers, whether it ships, and whether it renders. `python -m tools.conversion_table`
rewrites its cells from the shipped bundle.

## The issues — what the work is

**The audits, one row per item:**

| issue | what it covers |
|---|---|
| #23 | the second build variant, file by file, with the six questions answered under each |
| #665 | Settings, one unit per setting |
| #319 | comment compliance across the whole tree |
| #412 | the manual's own producers, then anchoring and extending it |

**Settings and what they reach:** #441, #423, #436, #419, #409, #432, #336

**The Extractor:** #438, #437, #421

**Capital and reservation:** #427, #400

**The trading engine:** #367, #429, #428, #435, #408, #538, #404, #398, #406, #344

**Screens:** #407, #290, #313, #306, #272, #415, #417, #424, #425, #420, #300

**The harness and the gates:** #584, #580, #574, #564, #562, #552, #541, #416, #403, #401, #325, #327

**Larger arcs:** #571 Stocks Mode · #433 the four unbuilt concepts · #413 a redacted manual · #431 the VWAP figures · #410 the page-fault rate · #305 the build's unreachable assets

`gh issue list --state open` is the live list. This table is an index, not a
census.

## The skills — how the work is done

Loaded by name. 31 of them under `dev_harness/skills/`, mirrored to the user's
own directory, and the two copies must match.

**Read these before working:** `ground-to-issue-and-manual` · `harness-law` ·
`ocir` · `w5h` · `hyper-refocus` · `canonized-code-testing` ·
`file-passes-only` · `no-detours`

**Read these when the work calls for them:** `archetype-peer-review` ·
`branch-discipline` · `issue-authoring` · `unit-decomposition` ·
`two-sided-control` · `reachability-first` · `truth-check` ·
`found-it-own-it` · `debugging` · `job-watch` · `close-package` ·
`hop-protocol` · `log-pruning` · `prompt-distillation` ·
`manual-is-the-map` · `widest-true-reading` · `anti-claudism`

**Writing:** `simple-technical-english` · `docs-narrative` ·
`descriptive-comments-only` · `variable-naming-precision` · `ta-canon`

## Where the running program keeps its own state

| what | where |
|---|---|
| the saved fleet | `~/.acervator/bot_state.json` — read only, never write |
| the credentials | `~/.acervator/coinbase_credentials.json` — never open |
| the logs | `~/.acervator_logs/` |

`src/core/log_paths.py` is the one module that decides those locations.

## Where the build is decided

| what | where |
|---|---|
| the two entry points he double-clicks | `React_BUILD.py`, `Qt_BUILD.py` |
| what they call | `tools/build_launcher.py` |
| what that runs | `build_windows.ps1` |
| the specifications | `Acervator_win.spec`, `Acervator_mac.spec` |
| the variant names | `src/_variant.py` |
| the version | derived from the git tag, through `src/_version.py` |

**He builds from the Desktop copy of the repository, not this one.** After every
merge that copy is pulled and those two entry points are run there.

## What this file must never become

A place to learn a fact. Every table above is an address. When an address is
wrong, that is a finding: name the line and what the running program did
instead, and correct the address here.

## Falsification

This file is wrong if any address in it does not resolve, or if a reader can
learn a product fact from it without opening the page it points at.
