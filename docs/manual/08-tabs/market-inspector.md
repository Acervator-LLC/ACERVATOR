# Market Inspector Tab

Reference. The higher-timeframe scanner and the topology proposal pane.
First step of [the promotion pipeline](promotion-pipeline.md).

## What builds it

`MarketInspectorTabMixin._build_market_inspector_tab` in
`src/gui/main_tabs/market_inspector_tab.py` constructs the tab and wires its
three injection points before adding it to the row.

The tab splits horizontally. The left half holds the scanner, the right half
holds the proposal cards.

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

`Opposing Pairs (30-day Pearson)` lists Long side, Short side, Correlation and
the combined score.

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
and keeps the ones whose thirty-day return correlation sits in the configured
negative window.

`src/trading/market_inspector.py` — `MarketInspector._find_opposing_pairs`

```python
def _find_opposing_pairs(self, signals: list, closes_by_symbol: dict) -> list:
    """Enumerate long × short candidates; keep pairs whose 30-day
    return correlation sits in the configured negative window."""
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
spread tracking. No module under `src/` imports it, and the tab draws no
arbitrage panel. The first two proposal forms are on screen; the third is not.

In development.

## Bridge

Three methods serve this screen, and the renderer modules carry the matching
names.

| Bridge method | Serves |
| ------------- | ------ |
| `market_inspector.state` | The scanner and its two tables |
| `market_inspector_tab.state` | The per-bot page in the Bot Details dialog |
| `market_inspector_topologies.state` | The proposal cards |

Back to [the subsystem index](README.md).
