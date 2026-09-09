# Market Inspector Tab

Reference. The higher-timeframe scanner and the topology proposal pane.
First step of [the promotion pipeline](promotion-pipeline.md).

## What builds it

`MarketInspectorTabMixin._build_market_inspector_tab` in
`src/gui/main_tabs/market_inspector_tab.py` constructs the tab and wires its
three injection points before adding it to the row.

The tab splits horizontally. The left half holds the scanner, the right half
holds the proposal cards inside the Bot Swarm Topologies zone, which is one of
the three zones that side carries.

## The six zones

The screen draws six zones, three down each side: ATA-SMP, Opposing Trades and
Multi-Exchange Arbitrage on the left, and ATA-SMP Ready to Send, Bot Swarm
Topologies and Phantom Bot HTF Signals on the right. Every zone shows one entry
at a time, with a left arrow, a right arrow and a line saying which entry is on
screen out of how many the zone holds. Clicking the entry opens it, and the
expansion names the test, the window, the result and why that answer let the
entry through. One implementation serves all six, and the proposals pane draws
through the same one. The record is
`tests/debug_reports/2026-09-06_topology_list.md`.

`src/gui/main_tabs/market_inspector_surface.py` — the three right-side zones

```python
def right_zone_rows(run: Any, bucket: Any = None) -> list:
    """The three right-side zones as key, title and status, in screen order."""
```

The Qt build gives every zone a `ProposalStepper`. The two web hosts give every
zone a `ZoneStepper`. Both are written from one description of the zone, so a
zone's lines are decided in one place and a second copy cannot drift from the
first.

`src/gui/market_inspector.py` — the Qt widget every zone uses

```python
class ProposalStepper(QWidget):
    """One zone's entries shown one at a time, with arrows and a expansion.
```

## Left half: the scanner

A filter row carries a Refresh button and an "Include active markets"
checkbox. The default hides the markets already under a bot, which keeps the
table on entry opportunities.

`HTF Signals` lists one row per market: Asset, Signal, Score, Daily, Weekly,
Active.

`Opposing Pairs (cointegration, Engle-Granger + Johansen, p<=0.05)` lists Long
side, Short side, Method, Window, Statistic, Correlation and the combined score.
The 30-day Pearson coefficient raises a candidate and no longer decides one.

## Where the analysis happens

`MarketInspector` in `src/trading/market_inspector.py` owns the maths. One
method drives the whole pipeline and keeps the results on the analyzer.

`src/trading/market_inspector.py` — `MarketInspector.scan_universe`

```python
def scan_universe(
    self,
    candles_by_symbol_by_tf: dict,
    active_symbols: set,
    closes_by_symbol: dict,
) -> None:
```

Two steps run under it.

| Step | Produces |
| ---- | -------- |
| `_analyze_tf` | One `TimeframeAnalysis` per timeframe |
| `_score_market` | One `MarketSignal` per market |

The pairing is a separate step. It enumerates every long against every short
and keeps the cointegrated ones. A thirty-day return correlation sitting in the
configured negative window raises a candidate, and the cointegration test then
decides it.

`src/trading/market_inspector.py` — `MarketInspector._find_opposing_pairs`

```python
def _find_opposing_pairs(self, signals: list, closes_by_symbol: dict) -> list:
    """Enumerate long × short candidates; keep the cointegrated ones.

    The 30-day return correlation raises a candidate and no longer decides
    it: ``cointegration_test`` runs on the full close series and a pair it
    refuses never reaches the table.
    """
    longs = [s for s in signals if s.direction == "long" and s.score >= 0.3]
    shorts = [s for s in signals if s.direction == "short" and s.score >= 0.3]
```

The correlation raises a candidate and no longer decides one. Every pair the
screen shows has also passed a test for a long-run equilibrium, because two
markets can move opposite each other for a year with no relationship holding
between them. The test is cointegration in both of its standard forms, taken
from statsmodels, and a pair passes only when both reject the null of no
cointegration: Engle-Granger at a significance of 0.05, and Johansen above its
ninety-five per cent critical value for rank zero. The window is 365 daily
closes and a pair with fewer than 120 is not tested and not shown. Opposing
Pairs therefore carries seven columns today: Long side, Short side, Method,
Window, Statistic, Correlation and Score. The numbers are recorded in
`tests/debug_reports/2026-09-06_stageC_cointegration.md`.

`src/trading/pair_selection.py` — what a pair has to clear

```python
WINDOW_BARS = 365
MIN_OBSERVATIONS = 120
SIGNIFICANCE = 0.05
```

One analyzer instance serves two readers. `get_shared_inspector` returns it,
the tab owns the fetch cycle and writes into it, and the per-bot Market
Inspector page in the Bot Details dialog reads back out of it through
`build_per_bot_view`. One analyzer, two readers, no second copy of the score.

## Fetching

`set_exchange_source` binds a connectors getter and the application scheduler,
so the tab always sees the current connector dict rather than a snapshot taken
at build time.

The fetch serves its last network result while that result stays young enough,
and the Refresh button passes a flag that goes to the network regardless.

`src/exchange/market_inspector_fetcher.py` — `fetch_htf_universe`

```python
async def fetch_htf_universe(
    exchange_connectors: dict,
    active_symbols: Optional[set] = None,
    top_n: int = DEFAULT_TOP_N,
    progress_cb=None,
    force_network: bool = False,
    min_refresh_s: float = DEFAULT_MIN_REFRESH_S,
) -> FetchResult:
```

Three helpers do the work inside it.

| Helper | What it does |
| ------ | ------------ |
| `_pick_universe` | Ranks each connector's bulk tickers by 24-hour quote volume |
| `_fetch_one_symbol` | Pulls per-symbol OHLCV on the connector's single-worker executor |
| `_resample_daily_to_weekly` | Derives the weekly series on the client when the venue lists no weekly timeframe |

## What a scan reports

An empty table can mean three different things. The note under it says which:

- no scan has run yet
- a scan is running
- a scan finished and found nothing

Before this, all three looked the same. An empty table gave no sign of which one
it was, so a tab that was working looked exactly like a tab that was broken.

`src/gui/market_inspector.py` — `_empty_table_text`

```python
def _empty_table_text(scan_state: str, noun: str) -> str:
    """The sentence an empty table carries for one scan state.

    ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` and ``SCAN_FINISHED`` each get
    their own wording, so the three never read alike.
    """
    if scan_state == SCAN_RUNNING:
        return f"Scanning for {noun}…"
    if scan_state == SCAN_FINISHED:
        return f"Scan finished. No {noun} found."
    return f"No scan yet. Press Refresh to look for {noun}."
```

`scan_state` reports the same three states to the renderer. The React side draws
the note under the table, the same way the tab does.

The scan also writes to the log. It writes one line when it starts and one line
when it finishes.

The start line names two things: whether Refresh forced the scan, and how many
exchange connectors it reached.

The finish line names four things: how many markets the scan covered, how many
signals and pairs it scored, how long it took, and where the data came from.

The finish line is always written. A scan that scored nothing still writes one.
That is what makes a quiet market different from a scan that never ran.

Each line also goes on the event bus as a record other parts of the platform can
read.

| Topic | Carries |
| ----- | ------- |
| `market_inspector.scan_started` | forced, connector count, active symbols |
| `market_inspector.scan_finished` | market count, duration, signals, pairs, source, error |

Both topics are declared in `src/core/emit_contracts.py`. A topic declared there
is a tracked emitter, and a run that never fires it is reported.

## Right half: topology proposals

`MarketInspectorTopologies` in `src/gui/market_inspector_topologies.py` renders
one card per proposal and opens a preview dialog on Preview.

`current_topology_proposals` answers two different things. It answers `None`
when the right pane never built or refused the read, and a list when the pane
answered, so an empty list means the pane holds no proposals. It answered an
empty list for both before, which is what made a scan that found nothing read
like a pane that was never there. The reader in the Simulator tab passes the
same two answers on rather than flattening them.

`src/gui/market_inspector.py` — the two answers a reader gets

```python
def current_topology_proposals(self) -> "list | None":
    """The proposals on display, for a simulator to read and wire.

    ``None`` says the right pane never built or refused the read,
    and a list says the pane answered. An empty list therefore
    means the pane holds no proposals, which no caller can
    confuse with a pane that is not there.
    """
```

The engine behind the cards takes a plain dictionary, which keeps it free of
any exchange or bot-manager coupling. It unions the detectors, drops
overlapping proposals by asset and caps the result.

`src/trading/topology_proposals.py` — `detect_all_topologies`

```python
def detect_all_topologies(
    context: dict[str, Any],
    cap: int = PROPOSAL_CAP,
) -> list[dict[str, Any]]:
    """Union every detector's proposals, dedupe them and cap at ``cap``.
```

Four detectors feed it.

| Detector | Shape |
| -------- | ----- |
| `detect_momentum_funnel` | Correlated cluster, leader into laggers |
| `detect_mean_reversion_pair` | Anti-correlated pair, wired both ways |
| `detect_sector_cluster` | Same-sector star, hub into spokes |
| `detect_distance_to_band` | One asset, scrum-deep into fold-deep |

Two helpers read from disk under `src/trading/`. `suggested_target_usd` sizes
each proposed bot from the asset target defaults, and the sector map names each
asset's sector.

## Dismissal

Dismissing a card hides it for a day. The write-through never raises, because
losing a dismissal is a nuisance and taking down the pane is not.

`src/gui/market_inspector_topologies.py` — `_persist_dismissed`

```python
def _persist_dismissed(self) -> None:
    """Best-effort write-through. Never raises: losing a
    dismissal is a nuisance, taking down the pane is not."""
    if self._dismiss_store is None:
        return
    try:
        self._dismiss_store.set(DISMISS_SETTINGS_KEY, dict(self._dismissed))
```

That write fails on every call today, because the key it writes is not one the
settings schema declares. The pane logs the failure and carries on, so the
dismissed count reads zero on every launch. Issue #424 carries it.

`set_dismiss_store` hands the pane the settings manager it persists through.
The pane never resolves settings itself.

## Adopt

The pane emits an adopt request and the window handles it. The handler counts
the new bots and their combined budget, asks which of the proposed wires
already exist and would change, and shows all of it before anything is created.

`src/gui/main_window.py` — `_adopt_topology_proposal`

```python
def _adopt_topology_proposal(self, proposal: dict) -> None:
    """Confirm, open the wizard for each new bot, then emit `wire.created`."""
```

An adopt that aborts part way calls `_report_adopt_orphans`, which names the
bot ids it created and left unwired.

The per-bot page is drawn from one description as well. `per_bot_view` reads
the shared analyzer and returns the whole screen as values: the rows, the
groups, the words, the colours and the layout numbers. The Qt side draws them
as widgets and the React side draws them as elements, where the React side drew
a Python error message before. The record is
`tests/debug_reports/2026-09-06_unit12_market_inspector_tab.md`.

`src/gui/main_tabs/market_inspector_tab_surface.py` — `per_bot_view`

```python
def per_bot_view(bot: Any) -> dict:
    """The per-bot Market Inspector screen as values, read off the shared
    analyzer's most recent scan.
```

## ATA-SMP

The eight phases sit outside the screen. Phases one to three and phase eight run
in `src/trading/ata_spm.py`, and phases four to seven run in
`src/trading/ata_spm_push.py`. The screen reads what they produce and draws it;
it computes none of it. Seven push targets ship, and adding one is adding a row,
because no phase names a target.

`src/trading/ata_spm_push.py` — the names every screen reads

```python
TARGET_NAMES = tuple(one.name for one in PUSH_TARGETS)
```

The rules each platform publishes are recorded in
[the push target rules](../../audits/2026-09-06_ata_platform_rules.md). The
narrative for the whole screen is on [the tabs page](../08-tabs.md).

## Exchange comparison arbitrage

`src/trading/arbitrage.py` holds the cross-exchange price monitor and its
spread tracking. No module under `src/` imports it. The tab draws a
Multi-Exchange Arbitrage zone, and that zone draws no arbitrage panel: it names
the venues in reach and stops there. The first two proposal forms are on screen;
the third is not.

In development.

## Bridge

Three methods serve this screen, and the renderer modules carry the matching
names.

| Bridge method | Serves |
| ------------- | ------ |
| `market_inspector.state` | The scanner and its two tables |
| `market_inspector_tab.state` | The per-bot page in the Bot Details dialog |
| `market_inspector_topologies.state` | The proposal cards |

## Updates

What the screen is sits above. How it got there sits below, in order.

Each entry carries the date, the time, the issues it addressed and a short
phrase. Every date and time is read off the commit or the issue comment that
carries the change, never off the day the entry was written. An entry with no
artefact behind it says so and gives no time.

`.claude/rules/documentation.md` bans item numbers in documentation. The
operator's directive of 2026-09-08 amends that rule for this header alone, and
his newest word governs.

## 2026-09-06 18:26 - #407 - six zones, three down each side

The screen stopped being two panes with tables in them. Six zones now sit three
down each side. ATA-SPM, Opposing Trades and Multi-Exchange Arbitrage run down
the left. ATA-SPM Ready to Send, Bot Swarm Topologies and Phantom Bot HTF
Signals run down the right. One function names each side in screen order, so a
zone cannot appear on one host and go missing on the other.

`src/gui/main_tabs/market_inspector_surface.py` — the three left-side zones

```python
def left_module_rows(
    run: Any,
    scan_state: Any,
    pair_count: Any,
    connectors: Any,
    sector_count: Any = 0,
) -> list:
    """The three left-side regions as key, title and status, in screen order."""
```

Every zone works the same way. It shows one entry at a time, with a left arrow,
a right arrow and a line saying which entry is on screen out of how many the
zone holds. An arrow press wraps at both ends, so the last entry steps forward
to the first.

`src/gui/main_tabs/market_inspector_surface.py` — what one arrow press does

```python
def step_to(at: Any, total: Any, by: Any) -> int:
    """The entry index one arrow press moves to, wrapping at both ends."""
```

Clicking the entry opens it. The open entry drops its method line and its hint,
because the four expanded lines already say the same things, so every zone's
open entry takes one height whatever buttons it carries. The four lines are the
test, the window, the result, and why that answer let the entry through.

`src/gui/main_tabs/market_inspector_surface.py` — the four names an open entry
carries

```python
DETAIL_TEST_NAME = "Test"
DETAIL_WINDOW_NAME = "Window"
DETAIL_RESULT_NAME = "Result"
DETAIL_REASON_NAME = "Why it is here"
```

A zone holding nothing keeps its waiting sentence as the headline and still
reports a position of "0 of 0". An empty zone therefore reads as a state rather
than as a zone that failed to draw. Each zone says something different while it
waits.

| Zone | What its line says while it holds nothing |
| ---- | ---------------------------------------- |
| ATA-SPM | "No sector added. Name one and press Scan Now." |
| Opposing Trades | The scan state: not asked, running, or finished and empty |
| Multi-Exchange Arbitrage | The venues in reach, or that no exchange source is wired |
| ATA-SPM Ready to Send | "No run yet. Nothing to approve." |
| Bot Swarm Topologies | The proposal pane, which carries its own status line |
| Phantom Bot HTF Signals | "Phantom Bot source not wired." |

Phantom Bot HTF Signals is the renamed zone, and its line is fixed today.
Nothing feeds it. The zone is named, sized and drawn, and the row that builds it
writes the same sentence on every call, so no Phantom Bot reaches it yet.

`src/gui/main_tabs/market_inspector_surface.py` — the row that never varies

```python
[PHANTOM_HTF_ZONE, PHANTOM_HTF_GROUP_TITLE, PHANTOM_HTF_UNWIRED_TEXT],
```

## 2026-09-06 21:07 - #407 - the sector row, Scan Now, and the phase readbacks

The ATA-SPM zone grew a control row. It carries a sector field, an asset-class
box, four timeframe check boxes and a Scan Now button. The operator names a
sector, ticks the timeframes he wants, and presses Scan Now. Every asset the
sector holds is charted and run through the twelve voters.

`src/gui/main_tabs/market_inspector_surface.py` — the button and what it says

```python
SCAN_NOW_LABEL = "Scan Now"
SCAN_NOW_TOOLTIP = (
    "Scan this sector now on the timeframes ticked beside it, without "
    "waiting for a rotation."
)
```

The asset class sets which four timeframes the check boxes offer. Crypto is the
fast set. Stocks, metals, derivatives and forex share the slower one.

`src/trading/ata_spm.py` — the two sets

```python
CRYPTO_TIMEFRAMES = ("5m", "1h", "1d", "1w")
SLOWER_TIMEFRAMES = ("1h", "1d", "1w", "1M")
```

Only crypto has a sector map in the tree. Every other class answers no assets,
and the zone then names the source it is waiting for rather than showing an
empty scan. The map itself is the hand-typed one the topology detectors read.

`src/gui/main_tabs/market_inspector_surface.py` — the one class with a map

```python
def sector_assets(sector: Any, asset_class: Any) -> list:
    """The assets one named sector holds, read from the shipped sector map.

    Only ``ata_spm.CLASS_CRYPTO`` has a map in the tree, so every other
    class answers none and the zone names the source it waits for.
    """
```

Scan Now adds the typed sector when it is new, then runs the phases that read
price data. The expanded entry names each phase back with what it produced, so
a run can be read without opening a log.

`src/trading/ata_spm.py` — the phases one press runs

```python
def run(
    sectors: Any,
    asset_source: Optional[Callable] = None,
    candle_source: Optional[Callable] = None,
    engine: Optional[VotingEngine] = None,
    message_format: Optional[str] = None,
    clock: Optional[Callable] = None,
) -> AtaSpmRun:
    """Phases one, two, three and eight in order, as one ``AtaSpmRun``."""
```

Eight phases carry a post from a sector name to a published call. Two modules
hold them. The screen computes none of it and draws what they answer.

| Phase | Module | What it produces |
| ----- | ------ | ---------------- |
| 1 Evaluate | `ata_spm.evaluate` | One scan per sector, per ticked timeframe |
| 2 Identify | `ata_spm.identify` | The votes carrying a reversal, strongest first |
| 3 Pull | `ata_spm.pull` | The chart, its bands, and one message per confirming voter |
| 4 Format | `ata_spm_push.format_post` | One post per push target |
| 5 Distribute | `ata_spm_push.distribute` | One delivery record per post |
| 6 Ready to Send | `ata_spm_push.ReadyToSend` | The bucket the operator approves from |
| 7 Follow-Up | `ata_spm_push.FollowUpWatch` | What the market did after a published call |
| 8 Timeframes | `ata_spm.agreement_for` | Every timeframe the asset voted on, and their verdict |

A run answers a phase readback line for each of them. The readback names the
sectors scanned, the reversal calls found, and the charts pulled.

`src/trading/ata_spm.py` — the line a finished run leaves

```python
PHASE_RUN_FORMAT = "{phase}: {sectors} sector(s), {calls} call(s), {pulls} chart(s)"
```

## 2026-09-06 23:08 - #407 - Ready to Send, Post Selected, Post All and Full Auto

Nothing leaves the machine without an act. Phase four formats a post per target
and drops it into the Ready to Send bucket, where it waits. The operator
approves or declines each one, and no button sends a declined post.

`src/gui/main_tabs/market_inspector_surface.py` — the five buttons the bucket
carries

```python
APPROVE_LABEL = "Approve"
DECLINE_LABEL = "Decline"
POST_SELECTED_LABEL = "Post Selected"
POST_ALL_LABEL = "Post All"
FULL_AUTO_LABEL = "Send Bucket Full Auto"
```

Post Selected sends the post on screen. Post All sends every approved post. Send
Bucket Full Auto releases approved posts with no further click. All three obey
one ceiling, counted over the hour ending now.

`src/trading/ata_spm_push.py` — the ceiling every send route obeys

```python
def allows(self, now: float, ceiling: Any) -> bool:
    """Whether one more post fits under ``ceiling`` at ``now``."""
    limit = int(ceiling or NO_CEILING_SET)
    if limit <= NO_CEILING_SET:
        return False
    return self.sent_within_hour(now) < limit
```

The ceiling starts unset, and an unset ceiling releases nothing. That is the
safe default: a fresh install cannot publish until the operator sets a number,
and the refusal says which of the two reasons held the post.

`src/trading/ata_spm_push.py` — the two refusals a held post reports

```python
NO_CEILING_TEXT = "Max posts per hour is unset. Nothing leaves."
RATE_HELD_TEXT = "{sent} post(s) sent this hour, ceiling {ceiling}."
```

The Settings button swaps the zone for a settings page and back. Four settings
sit there, each one read by a phase, and under them one credential row per push
target.

| Setting | Which phase reads it |
| ------- | -------------------- |
| Max posts per hour | The send ceiling above |
| Max supporting indicators | Phase four, capping the evidence lines drawn |
| Confirmation share % | Phase seven, sizing the target a call must reach |
| Standardised message text | Phase three, wording each indicator message |

Save credentials encrypts every typed credential into the same vault the venue
keys use, then clears what was typed. A credential row reports held or not
held. No typed value reaches a view model, a render or a log.

`src/trading/ata_spm_push.py` — what a credential row publishes

```python
CREDENTIAL_HELD_TEXT = "held"
CREDENTIAL_MISSING_TEXT = "not held"
```

## 2026-09-07 00:16 - #407 - Refresh, renamed

The topology pane's button read "Refresh proposals". It reads "Refresh" now, and
the pane is inside the Bot Swarm Topologies zone, whose title already says what
is being refreshed.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — the label and what
it does

```python
REFRESH_TEXT = "Refresh"
REFRESH_TOOLTIP = "Rerun topology detectors on current market state."
```

## 2026-09-07 03:59 - #407 - the follow-up post and the timeframe vote

Phase seven watches a call after it is published and posts what happened. Three
outcomes exist. A call is confirmed, failed, or still open.

`src/trading/ata_spm_push.py` — the three verdicts

```python
OUTCOME_CONFIRMED = "confirmed"
OUTCOME_FAILED = "failed"
OUTCOME_OPEN = "open"
```

The target a call has to reach is a share of the run from the call's close to
the Bollinger midline, and the midline is recomputed on every candle after the
call rather than frozen at it. The share is the confirmation share setting. A
share of zero sets no target, and the follow-up says so instead of claiming a
result.

`src/trading/ata_spm.py` — the moving target phase seven measures against

```python
def midline_after(candles: Any, at: Any) -> list:
    """The Bollinger middle band at every candle after index ``at``.

    ``BollingerBands`` computes its published band on each window, so the
    target phase seven measures against moves with the market.
    """
```

Phase eight answers whether the other timeframes agree with the call. It walks
every vote the same asset produced in the run, names the direction each one
read, and lists the timeframes that read the opposite. A neutral vote is
neither agreement nor contradiction.

`src/trading/ata_spm.py` — the three verdicts phase eight can write

```python
AGREEMENT_AGREED_TEXT = "Every timeframe agrees."
AGREEMENT_SINGLE_TEXT = "Only one timeframe voted."
AGREEMENT_CONTRADICTED_FORMAT = "Contradicted on {labels}."
```

Phase eight also caps a scan. Each sector takes only as many timeframes as the
rounds so far show will fit inside one candle of the shortest timeframe the
class scans. The rest are recorded as deferred and named on the zone, so a
shortened scan is visible rather than silent.

## 2026-09-07 07:29 - #407 - seven push targets and the ceiling each publishes

Seven targets ship. Adding one is adding a row: no phase names a target, and the
Settings credential list is built from the same rows, so a new row appears on
the settings page with no screen edit.

| Target | Body ceiling | Title ceiling | Counted in |
| ------ | ------------ | ------------- | ---------- |
| X | 280 | none | Weighted characters |
| Instagram | 2200 | none | Characters |
| LinkedIn | 3000 | none | Characters |
| TikTok | 4000 | 90 | UTF-16 runes |
| Facebook | none published | none | Characters |
| Threads | 500 | none | UTF-8 with emoji |
| Reddit | 40000 | 300 | Characters |

Every number came off the platform's own documentation, read on 2026-09-06 and
2026-09-07, and each one is cited on its own page. Where a platform publishes no
number, the row records that rather than carrying a guess.

[The push target rules](../../audits/2026-09-06_ata_platform_rules.md) — one
section per target, with the page each number came from

```
Facebook   body ceiling: no number published
           the row carries NO_LIMIT_PUBLISHED, and phase four applies none
```

The fixed header ships on every artefact the run composes. No caller supplies it
and no caller can remove it. It is 144 characters, and on X it takes over half
the budget.

`src/trading/ata_spm_push.py` — the header that cannot be dropped

```python
FIXED_HEADER = (
    "This is not investment advice. It is a demonstration of Ekthelius's "
    "proprietary TA engine housed in the Acervator governance execution "
    "platform."
)
```

Phase four holds each body under its target's ceiling. It drops evidence lines,
longest first, and never the header. A body that still will not fit says by how
much it missed rather than truncating the header to force it in.

`src/trading/ata_spm_push.py` — what the fitter drops, and what it will not

```python
def fit_to_target(ranked: Any, target: Any) -> tuple:
```

Two platforms named in the issue are not rows, and both were removed for the
same reason: a rendered chart has no route in. TradingView publishes an idea
through its website and states that it has no API for it. The YouTube upload
endpoint accepts video only.

**Where the issue and the code disagree, the code is right.** Issue #407's
comment of 2026-09-07 records "The formatter applies no per-target ceiling and
never did. The truncation rule is recorded and not built." That was true when it
was written. Every target row now carries its own `body_limit`, and phase four
applies it through `fit_to_target`. The comment is stale and the ceilings are
built.

## 2026-09-07 10:16 - #407 - the voting panel, the gate chain, and the two distances

ATA-SMP carries its own Indicator Voting Panel. It is a clone of the live one,
drawn inside an open entry, and it reads only the markets ATA-SMP scanned. No
live bot's market reaches it, and it reaches no live bot.

`src/gui/main_tabs/market_inspector_surface.py` — the panel and what feeds it

```python
def voting_panel(pull: Any) -> Optional[dict]:
    """The Indicator Voting Panel one scanned asset carries, as its rows.

    The rows are the timeframes ATA-SMP read for this asset alone, and
    every cell is drawn from ``indicator_panel_surface``.
    """
```

The live trade gates also run over the scanned prices. Both chains the bots
build are evaluated, unchanged, against a context filled from one market's
candles and its voting summary. Nothing on the live path changes: the bots build
the only two contexts inside their own tick, and this is a third caller.

`src/trading/ata_gate_scan.py` — both live chains, over scanned prices

```python
readings = read_chain(build_scrumming_scrum_chain(), context) + read_chain(
    build_scrumming_fold_chain(), context
)
```

Twenty-two gates run across the two chains. Sixteen decide from price and
settings alone. Six need a position the scan does not hold, and the scan never
invents one. Four of the six stand down by name, and two publish a distance
instead of a verdict.

`src/trading/ata_gate_scan.py` — the six, split by what a scan can honestly say

```python
NOT_APPLICABLE_GATES = (
    "delta_positive",
    "interval",
    "tranches_queued",
    "smart_ceiling",
)
HYPOTHETICAL_GATES = ("hysteresis_scrum", "hysteresis_fold")
```

The four stood-down gates appear in the expansion by name, marked as not run,
each with the reason. A reader sees that the gate exists, that it did not run,
and why. That is the point: a post must never imply a gate latched when no gate
ran.

`src/trading/ata_gate_scan.py` — the reason each stood-down gate publishes

```python
NOT_APPLICABLE_REASONS = {
    "delta_positive": "a scan holds nothing, and no surplus exists to test",
    "interval": "the same surplus, and a scan holds none of it",
    "tranches_queued": "a scan has no fold queue",
    "smart_ceiling": "a scan holds nothing, and any ceiling test passes",
}
```

Opposing Trade Distance is the second of the two numbers the expansion carries.
It is one sum: the bot's scrumming interval percentage plus its trading fee
percentage, clamped between 0 and 50. It is a formula over settings, so a scan
computes it exactly as a bot does.

`src/trading/otd_math.py` — the whole formula

```python
total = float(interval_pct) + float(fee_pct)
return max(OTD_MIN_PCT, min(OTD_MAX_PCT, total))
```

The two hysteresis gates feed on it. Each runs against a hypothetical entry at
the scanned price and publishes the price a reversal would have to reach, with
no verdict attached. At the instant of the scan the pivot equals the price, so
both sides would refuse; the number is the reading, and the refusal is not.

`src/trading/ata_gate_scan.py` — what a hypothetical row prints

```python
HYPOTHETICAL_FORMAT = (
    "entry at ${price:.8f} would need ${required:.8f}, "
    "{distance:.2f}% away; no gate ran"
)
```

Landing Strip is the first of the two. The band-proximity detector reads whether
price has sat against a Bollinger band for a run of candles, and it answers a
side. An upper strip is a sell reversal and a lower strip is a buy reversal. The
side and the candle count are both published on the expanded line beside the
distance.

`src/gui/main_tabs/market_inspector_surface.py` — the line carrying both numbers

```python
GATE_DISTANCE_FORMAT = "opposing trade distance {pct:.2f}% · landing strip {strip}"
```

A second strip detector runs inside the gate scan and feeds the confidence floor
rather than the direction. It lowers the floor the TA consensus must clear, in
the same way the live tick lowers it, so the scan and a bot judge a market at
one bar. The one term a scan loses is the band-priority favour, which arms only
on a signed delta, so a scan reads at a stricter floor than a bot holding a
position.

A chart with too few candles produces no gate scan at all. The floor is 30
candles, and the line says so rather than reporting an empty result as a clean
one.

`src/gui/main_tabs/market_inspector_surface.py` — the sentence a short chart
carries

```python
NO_GATE_TEXT = "No gate ran. The chart carried too few candles."
```

The counts sit at the head of the expansion, so a reader sees how much of the
chain actually decided before reading any single row.

`src/gui/main_tabs/market_inspector_surface.py` — the count line

```python
GATE_COUNT_FORMAT = (
    "{ran} of {total} gate(s) ran · {latched} latched · {blocked} blocked "
    "· {stood_down} did not run"
)
```

Which gates transpose, and why each one does, is measured field by field in
[the gate transposition page](../../audits/2026-09-07_gate_transposition.md).

## 2026-09-08 - #407 - Push to Sim, Paper and Live is not built

This entry carries no time. No commit implements it, so there is nothing to read
a time from.

The operator named a push from Opposing Trades and from Topologies to the
Simulator, to the Paper Trader and to Live. No such control exists on either
zone today. Adopt is the only control on this screen that creates anything, and
it creates live bots through the wizard.

A simulator can read the proposals on display, and that is a read with no write
behind it. It wires nothing and it starts nothing.

`src/gui/main_tabs/market_inspector_surface.py` — the read that exists instead

```python
def current_topology_proposals(self) -> Optional[list]:
    """The proposals on display, for a simulator to read.

    ``None`` says the right pane never built or refused the read, and
    a list says the pane answered, so an empty pane and an absent one
    never look alike to a caller.
    """
```

Nothing reports a push to a target that is not built, because nothing pushes.
The Paper Trader and the Simulator are both named on
[the promotion pipeline page](promotion-pipeline.md), which is where a push from
this screen would land.

In development.

## 2026-09-08 13:30 - #407 - the called markets the Charts tab keeps watching

Reaching Ready to Send now does a second thing. Beside waiting for approval, the
market joins a list the Charts tab keeps, so the operator can watch a called
market long after the post about it has gone or been declined.

The board answers one row per market, never one per post. A market called on two
timeframes is still one market being watched, and the row carries the timeframes
it was called on and the vote of the most recent call.

`src/trading/ata_spm_push.py` — the row the Charts tab reads

```python
@dataclass(frozen=True)
class WatchedMarket:
    """One market on the ATA-SMP chart list, and the call that queued it."""

    symbol: str
    vote: str = VOTE_NEITHER
    timeframes: tuple = ()
```

Three places hold a called market and the board reads all three, oldest first:
the calls phase seven has already settled, the calls it is still watching, and
the posts sitting in the bucket now. That is why filling the bucket from a new
scan does not drop an older market from the chart list.

`src/trading/ata_spm_push.py` — one set, read by phase seven and by the Charts tab

```python
    def watched_markets(self) -> list:
        """One ``WatchedMarket`` per market that reached Ready to Send.

        The bucket is the trigger and ``follow_up`` keeps a market listed
        after ``load_run`` replaces the bucket, so the Charts tab and phase
        seven read one set. The newest call's vote wins.
        """
```

Phase seven used to remember only the key of a call it had settled, which was
enough to stop watching it twice and not enough to name it later. It now keeps
the call itself, so a settled market can still be listed with its ticker, its
timeframe and its vote. The settled calls are read in key order, so the list
comes back in the same order every time.

The screen hands that reader to the Charts tab when it is built. Nothing is
copied across, so the two screens cannot disagree about which markets are
called. What the Charts tab does with the list is on
[the Charts tab page](asset-charts.md).

`src/gui/market_inspector.py` — what this screen offers the Charts tab

```python
def watched_markets(self) -> list:
    """The markets ATA-SMP has called, for the Charts tab's second list.

    ``PushBoard.watched_markets`` is the one set phase seven also reads.
    """
    return self._push_board.watched_markets()
```

**Figures.** This page carries no figure. The zones it describes are unchanged
by this entry, and the second reader it adds draws on another screen.

## 2026-09-08 15:20 - #407 - phase three draws the chart the post carries

Phase three used to answer a data record: the ticker, the timeframe, the bar
count, the band values and a list of confirming sentences. There was no
picture, so the post's caption captioned nothing. It now draws that chart and
writes it as a PNG, and the pull carries the file.

`src/trading/ata_spm.py` — the picture the pull now holds

```python
@dataclass
class ChartPull:
    """The chart one reversal call was made on, and its confirming messages.

    ``image`` is that chart rendered to a PNG, which the post's caption
    captions.
    """
```

The picture is drawn by the Charts tab's own renderer. No second drawing
engine was written for posts, because two engines drift apart and only one of
them is the screen the operator watches. What changed in the renderer is that
its drawing state and its paint routine moved out of the window into a plain
object, `ChartPainter`. The Charts tab's chart is that object with a window
around it, and a post image is that object with a picture file around it.

`src/gui/native_chart.py` — one paint routine, two places to send it

```python
        def paint_to(self, p: QPainter, w: int, h: int) -> None:
            """Draw the whole chart onto ``p`` over a ``w`` by ``h`` area.

            The painter's device is the caller's: a widget from ``paintEvent``
            and a ``QImage`` from ``render_chart_png``.
            """
```

The split was forced by where a scan runs. Pressing Scan Now hands the work to
a background worker so the screen keeps drawing, and the drawing toolkit will
not build a window on a background worker. Driven, it does not raise an error
that could be caught; it kills the program. A picture file has no such rule,
so the post image is drawn straight onto the file and no window is made.

`src/gui/market_inspector.py` — the worker the scan runs on

```python
            self._scan_thread = threading.Thread(
                target=self._compute_scan,
                args=(settings.message_format, settings.max_supporting_indicators),
                name=ATA_SCAN_THREAD_NAME,
                daemon=True,
            )
```

The indicators on the picture are the ones that voted for the call, not the
ones the Charts tab happens to have switched on. Each overlay in the chart's
registry now names the voter it draws, so the picture is chosen by the vote.

`src/gui/native_chart.py` — the overlay names its voter

```python
    ChartOverlay(
        key="bb",
        label="BB",
        colour_field="chart_band",
        pane=PRICE_PANE,
        occludes=False,
        draw="_draw_bollinger",
        tooltip="Bollinger Bands (20, 2σ) with cloud fill",
        voter="bollinger_bands",
    ),
```

**Max supporting indicators** on the settings page decides how many of them are
drawn. It was already the cap on how many confirming sentences a post carries,
and it is now the same cap on the chart. No second setting was added. Set to
one, the picture carries the Bollinger bands alone; left unset, it carries
every confirming voter the renderer has an overlay for.

A confirming voter with no overlay cannot be drawn, and the picture says so in
its header line rather than passing over it. Z-Score and RSI are the two that
vote and have no overlay today.

`src/gui/native_chart.py` — what reached the picture and what did not

```python
@dataclass
class ChartImage:
    """One rendered chart on disk, and what the renderer could not draw.

    ``drawn`` and ``undrawn`` name voters: ``undrawn`` holds the ones no
    overlay draws and the ones ``max_overlays`` cut.
    """
```

The files are kept outside the repository, in `~/.acervator_ata_posts`, beside
the other runtime folders and inside none of them. One file is written per
asset, per timeframe, per last bar. Nothing removes them yet.

`src/trading/ata_post_paths.py` — the one place the folder is named

```python
ATA_POST_ROOT: Path = Path.home() / ".acervator_ata_posts"
```

Nothing sends the picture. The sender is handed the whole post, so the file
travels with the text, and no sender reaches a platform. The Ready to Send
zone draws the text and does not show the picture.

**Figures.** This page carries no figure, and this entry adds none: a rendered
chart is produced output and is not kept in the repository. The picture drawn
by the run behind this entry measured 1200 by 372 pixels and carried 7126
distinct colours, against 17 for the same chart drawn with no candles. Its
readings are in
[the debug report](../../../tests/debug_reports/2026-09-08_ata_post_image.md).

## 2026-09-08 15:30 - #407 - the post picture folder has a ceiling

Every scan wrote a picture and nothing ever took one away. One picture measured
121044 bytes. A scan across sectors on four timeframes, repeated as bars close,
reaches gigabytes on the machine the operator trades from, and nobody would
notice until the disk did.

The folder now keeps the newest picture of each market and removes the older
ones. A market is one asset on one timeframe, so gold on the hourly chart and
gold on the daily chart are two markets and each keeps its own newest picture.

The number is not a preference. It is what the posting side can actually reach.
Phase four looks up one chart per market and keeps the last one, and the Ready
to Send list is rebuilt from scratch on every scan. Nothing in the application
can name an older picture, so nothing loses one.

`src/trading/ata_post_paths.py` — how many stay, and why that number

```python
#: ``ata_spm_push.format_run`` keys its pulls by symbol and timeframe, last
#: write winning, so one image per market is every image a post can name.
POST_IMAGES_KEPT_PER_MARKET = 1
```

The follow-up post was the thing to check before setting any ceiling, because a
ceiling that throws away a picture a follow-up still needs is worse than no
ceiling. It does not need one. Phase seven reads the chart again from the market
data, never from the folder, and the post it writes is text: the original
headline, the outcome, and the evidence behind it. Driven over three called
markets, phase seven settled all three and composed twenty-one follow-up posts
across the push targets. None of them carried a picture.

`src/trading/ata_spm_push.py` — phase seven asks the market, not the folder

```python
    def check(self, candle_source: Any, share_pct: Any) -> list:
        """Read each watched call's chart again and answer what happened to it.

        A settled call stops being watched and an open one stays, so no call
        is posted on twice.
        """
```

The clearing happens on the same press that draws a picture. Scan Now runs the
three phases, phase three writes the file, and the folder is trimmed
immediately afterwards, so it is never larger than one scan's worth of pictures
plus the newest of every market scanned before.

`src/trading/ata_spm.py` — the picture is written, then the folder is trimmed

```python
    path = ata_post_paths.post_image_path(vote.symbol, vote.timeframe, stamp)
    image = render_chart_png(
        held,
        vote.symbol,
        timeframe_label(vote.timeframe),
        path,
        voters=[one.indicator for one in confirming_signals(vote)],
        max_overlays=int(max_supporting_indicators or NO_INDICATOR_CAP),
    )
    ata_post_paths.prune_post_images(path)
    return image
```

**It says what it took.** Deleting the operator's files quietly is not
acceptable, so every trim writes one line naming how many pictures went, how
many bytes came back, how many stayed, and how many the machine would not let
go of.

`src/trading/ata_post_paths.py` — the line every trim writes

```python
PRUNE_LOG = (
    "ATA post store: removed %d image(s), reclaimed %d byte(s), kept %d, refused %d"
)
```

**It cannot reach anything else.** It reads one folder, the one its own file
names, and it goes no deeper. A file whose name a post picture could not have
produced is not touched: three such files sat in the folder through a whole
driven run and all three were still there at the end. The state folder, the log
folder, the recorded market data and the paper ledger were counted before the
run and after it and did not move, and the settings file hashed the same both
times.

**A picture being written is never taken.** The protection is the operating
system's own refusal, not a check that could be wrong. Driven with a picture
held open, the deletion was refused, the file survived, and the trim reported it
as refused. The same file went on the next press, once the handle had closed.

Driven over three markets with nine older pictures planted, the folder went from
twelve files to six, and the three pictures the run had just drawn were the
three that stayed. A second press on unchanged bars removed nothing.

```
                        files      bytes
before the first scan      12        174
after the first scan        6     478068
after a later scan          6     441483
after an unchanged scan     6     441483
```

**Figures.** This page carries no figure and this entry adds none. The folder is
outside the repository and a rendered chart is produced output, so neither is
kept here. The readings behind every number above are in
[the debug report](../../../tests/debug_reports/2026-09-08_ata_post_pruning.md).

## 2026-09-08 17:24 - #407 - the organization link, and the chart that says why

Two things changed. Every post now carries a link to the Acervator-LLC page on
GitHub. The chart a post carries now states the call and shows what each voter
read.

**The link is one string in one place.** One routine writes every piece of post
text. It puts the fixed header on top, the evidence under it, and the link at
the bottom. No caller supplies the link and no caller can remove it. The body,
the caption, the thread root and the title all carry it, on every target.

`src/trading/ata_spm_push.py` — the link, written once

```python
def compose(lines: Any) -> str:
    """``FIXED_HEADER`` over ``lines`` over ``ORGANIZATION_URL``.

    ``fit_to_target`` drops ``lines`` to reach a ceiling and reaches neither
    ``FIXED_HEADER`` nor ``ORGANIZATION_URL``.
    """
```

**The link costs characters, and each target has its own ceiling.** X counts a
web address as 23 characters whatever its real length. The other targets count
every character in it. Where a post no longer fits, the evidence gives way and
the link stays. The longest indicator sentence goes first, then the next
longest, and the post says how many sentences were left out.

The numbers below are one run on a recorded Amazon daily chart. Measured is the
post body in the unit that target counts in.

| target | ceiling | counted in | before the link | with the link | sentences dropped |
|---|---|---|---|---|---|
| X | 280 | weighted characters | 272 | 246 | 7 |
| Instagram | 2200 | characters | 727 | 760 | 0 |
| LinkedIn | 3000 | characters | 711 | 744 | 0 |
| TikTok | 4000 | UTF-16 runes | 765 | 798 | 0 |
| Facebook | none published | characters | 765 | 798 | 0 |
| Threads | 500 | UTF-8 emoji units | 470 | 431 | 4 |
| Reddit | 40000 | characters | 765 | 798 | 0 |

No target is over its ceiling. X keeps the ticker, the direction, and the note
that the evidence was cut. That is all 280 characters hold once the fixed
header and the link are on the post.

**The chart now states the call.** The renderer takes the direction the vote
named and one sentence per confirming voter. It is the same renderer the Charts
tab draws with, and a chart given no call takes neither.

`src/gui/native_chart.py` — the direction and the readings the picture takes

```python
        def set_call(self, direction: str, readings=()) -> None:
            """Take one reversal direction and one reading line per voter.

            ``readings`` are ``(voter, text)`` pairs and ``_draw_call`` paints
            them under the time axis.
            """
```

**Three marks, and each one is earned.** A badge in the top right names the
direction. A dashed rule and a triangle mark the last bar, which is the bar the
vote was made on. A strip under the time axis carries one row per confirming
voter: a square in the colour of the line that drew that voter, and the
sentence phase three wrote for it. Nothing is drawn that a voter did not read.

A voter with no line on the chart still gets a row, in the dim colour, and the
header line names it. ADX and Supertrend were the two on this run.

`src/gui/native_chart.py` — where the marks go

```python
        def _draw_call(self, ctx, h: int) -> None:
            """Draw the reversal badge, the call bar mark and the voter strip.

            The bar marked is the last candle, which is the bar the direction
            ``set_call`` took was voted on.
            """
```

**The Charts tab is unchanged.** A chart with no call set draws no badge, no
bar mark and no strip, and keeps the height it had before. The same recorded
tape drawn both ways measured 344 pixels tall with no call and 390 with one.

**Figures.** This page carries no figure and this entry adds none. A rendered
chart is produced output and is not kept in the repository. The picture drawn
by the run behind this entry measured 1200 by 478 pixels and 164,402 bytes,
carried 14,062 distinct colours, and 90.53% of its pixels are not its
commonest colour. Its readings are in
[the debug report](../../../tests/debug_reports/2026-09-08_ata_post_link_and_chart.md).

Back to [the subsystem index](README.md).
