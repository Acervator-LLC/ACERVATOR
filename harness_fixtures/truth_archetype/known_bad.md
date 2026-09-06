# Bot Swarm conversion — Explanation

Ground truth: this file carries one planted defect per rule. `TruthArchetype`
MUST report T001, T002, T003, T004, T005 and T006 on it, and the CLI MUST exit
1. A run that exits 0 here means the instrument is blind and every other verdict
it gives is void.

## What landed

The Bot Swarm panel renders the whole fleet.

The conversion is complete: the manifest lists every tab.

Every check passed.

## Anchors

The panel is built in `src/gui/main_tabs/bot_swarm_panel_v9.py`, and its entry
point is `scrum_fold_teleport_handler`.

Issue #9998 tracks the remaining work, and #195 is open against it.

`dev_harness/harness/report.py` holds 99999 lines.

## Scope

The Simulator is finished, and the Paper Trader is wired to it.

`TruthArchetype` MUST also report T007 here. The one cited number that exists
in this repository is 195, and that item names neither subject.
