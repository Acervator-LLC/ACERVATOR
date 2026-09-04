# Paper Trader Tab

Reference. The third step of [the promotion pipeline](promotion-pipeline.md).
No module implements it.

## The measurement

`git log --all --diff-filter=ADR --name-only` lists every path added,
deleted or renamed in every commit reachable from every ref. Two paths in
that list carry the word `paper`, and both name markdown documents under
`docs/`. No module, no test, no renderer file.

The same query returns modules, a renderer file and four tests for
`history_tab`, which proves it finds files that existed. The empty result
is a statement about the tree, not about the query.

## What stands in its place

`RetiredTabsMixin._install_retired_tab_sentinels` in
`src/gui/main_tabs/retired_tabs.py` assigns `None` to `_paper_trader` and
to three sibling attributes. Nothing in that module assigns them anything
else, so a legacy code path that reads one gets `None` rather than an
`AttributeError`.

Two places already expect the tab. `_on_main_tab_changed` in
`src/gui/main_window.py` lists "Paper Trader" beside "Simulator" as an
isolated tab, and `ISOLATED_TABS` in
`src/gui/main_tabs/header_strip_surface.py` carries the same pair. The
header strip will hide itself the day the tab arrives.

`CANONICAL_TAB_ORDER` in `src/gui/main_window.py` names seven tabs, and
Paper Trader is not among them.

## The Paper Swarm sub-tab is chrome

The Bot Swarm tab adds a third sub-tab labelled Paper Swarm.
`_create_paper_bot_row` in `src/gui/bot_visualizer.py` appends a row dict
to `_paper_bots`; the row's Start button flips a `running` flag and
relabels itself. `_paper_bots` is read nowhere outside that one module,
and only to count the active rows for a summary label. No bot is
constructed, no feed is attached and no order is recorded.

## What the step is, when it lands

Real time is its defining property. The Simulator replays stored candles
as fast as the machine allows; Paper takes the live feed at the speed the
market delivers it.

Live, Paper and the Simulator differ in one thing only: where the data
comes from. The trading logic stays one body of pure code that all three
call. Only the stateful shells fork, which is what keeps a paper run from
holding a live object.

The paper budget is twice the dollar target, so a bot has room to fold
without the exercise ending on the first dip.

Paper sits behind two gates. The Simulator must first reproduce the gate
latches, and Nuclear Mode must survive its loops. Neither is earned yet,
which is why the step is not built.

## The Paper Trade History Tab

The manual's part list names a second History tab reading a paper trade
log. The same query above finds no such module either. `HistoryTab` in
`src/gui/history_tab.py` reads live venue history alone.

Back to [the subsystem index](README.md).
