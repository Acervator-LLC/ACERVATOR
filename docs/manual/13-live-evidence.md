# The Year-to-Date Record and Exchange Test Coverage

Reference. What reads the venue's own trade record, and how far the tests
around the exchange integration reach, measured rather than asserted.

[Part 9](10-live-trade-history.md) holds the fill record itself: its row counts,
its fills per asset, the VWAP charts, the trade grading and the gate logs. This
part covers the readers of that record and the exchange code beneath them.

The record is the operator's own venue export, and this repository holds no copy
of it. The tree tracks no spreadsheet file at all, and of every path any commit
has ever added, deleted or renamed, two carry a spreadsheet suffix and both are
function-complexity inventories.

```
git ls-files "*.csv" "*.xlsx"                   nothing tracked

git log --all --diff-filter=ADR --name-only     every path the history touched
    docs/audits/2026-08-04_function_complexity_inventory.csv
    docs/engineering-notes/2026-08-04_function_complexity_inventory.csv
```

## The venue holds the authority

The reconciliation walk refills a bot's counters from the venue rather than from
the bot's own ledger. It walks the venue's own trade call for the bot's symbol in
30-day windows from a fixed anchor, pages a fixed number of rows at a time, and
de-duplicates by trade id across the windows. Each unique sell adds quantity
times price to a year-to-date scrummed sum; each unique buy adds to a folded sum.

```python
YTD_TRADE_ANCHOR_UTC = 1_775_001_600.0      # src/trading/scrumming/reconciliation.py
YTD_TRADE_PAGE_LIMIT = 500
YTD_TRADE_MAX_PAGES = 40

async def sync_ytd_trade_count(self) -> Optional[int]:
    """Walk ``get_my_trades`` in 30-day windows from the YTD anchor."""
```

| Field the walk writes | Value written |
| --- | --- |
| `stats.total_trades` | `max` of the persisted count, the previous exchange count, and the count just walked |
| `stats.exchange_trade_count` | the same value |
| `stats.ytd_scrummed_usd` | `max` of the persisted sum and the walked sell sum |
| `stats.ytd_folded_usd` | `max` of the persisted sum and the walked buy sum |
| `stats.exchange_data_fresh_ts` | the clock reading at the end of the walk |

Every counter write takes a `max`, so a walk raises a counter toward the venue
and never lowers one. Three paths leave the persisted counters alone and answer
nothing: a raise inside the walk, an absent exchange, and an exchange that does
not serve the trade call. Eight checks drive it against a stubbed exchange — one
pins the anchor, three drive those three paths, two pin that the count never
falls, and two walk a paged, duplicated window set.

```python
def test_anchor_is_2026_04_01_utc(self): ...        # tests/test_ytd_trade_sync.py
def test_single_page_under_limit(self): ...
def test_chunked_window_walk_dedupes_by_id(self): ...
def test_never_lowers_persisted_count(self): ...
def test_does_not_toggle_downward_when_prev_exchange_higher(self): ...
def test_returns_none_when_no_exchange(self): ...
def test_returns_none_when_method_missing(self): ...
def test_returns_none_on_api_exception(self): ...
```

The loop stops after twelve windows. Twelve 30-day windows reach 360 days past
the anchor, the furthest forward one sync can carry.

The fleet aggregator sums those per-bot fields across every bot. Its two headline
fields carry the year-to-date sum whenever that sum exceeds zero, and fall back
to the platform-run accumulator otherwise. Two further fields carry the two
figures apart, so a reader who wants one of them can have it unmixed.

```python
def get_aggregate_stats(self) -> dict:      # src/trading/container/aggregation.py
    return {
        "total_scrummed_usd": ...,          # year-to-date, else the run accumulator
        "total_folded_usd": ...,            # the same rule
        "total_scrummed_usd_ytd": round(total_scrummed_ytd, 4),
        "total_scrummed_usd_lifetime": round(total_scrummed, 4),
    }
```

## Readers of the record

| Reader | Input | Output |
| --- | --- | --- |
| `sync_ytd_trade_count` (`src/trading/scrumming/reconciliation.py`) | `get_my_trades` pages from the venue | the five `stats` fields above |
| `fetch_all_history_chunked` (`src/exchange/history_helpers.py`) | venue trades for every exchange and symbol a bot manager exposes | one row dict per fill, for the History tab |
| `compare_trades` (`src/trading/stone_tablets/parity_harness.py`) | live fills and Simulator fills | a `ParityReport` of matched, live-only and sim-only trades, paired inside `DEFAULT_TOLERANCE_S` of 300 seconds |
| `ytd_compounding_replay` (`dev_harness/harness/`) | the operator's export, read offline | an upper bound on what the surplus-drain formula would have added to each bot's target |

The Fleet Replay panel imports the parity comparison and records every call under
a feature name. The telemetry behind that name counts calls, skips and exceptions
per feature, and flags by name any feature that was never called.

```python
TELEMETRY_PARITY = "sim.parity.compare_trades"      # src/gui/main_tabs/fleet_replay_panel_surface.py

class FeatureCounter: ...       # src/core/feature_telemetry.py
class FeatureTelemetry: ...
def get_telemetry() -> FeatureTelemetry: ...
```

## The connectors

Three classes subclass `ExchangeInterface`. The interface declares seventeen
members, sixteen of them abstract. The seventeenth is the venue trade call, and
it carries a body that raises until a subclass overrides it.

```python
class ExchangeInterface(ABC):       # src/exchange/base.py
    async def get_my_trades(...):   # the one non-abstract member, raises NotImplementedError
```

| Implementation | Module | Reaches |
| --- | --- | --- |
| `CCXTConnector` | `src/exchange/ccxt_connector.py` | any venue id in `SUPPORTED_EXCHANGES`, through ccxt; or a backend passed to `attach_backend` |
| `FleetSimExchange` | `src/simulator/fleet/sim_exchange.py` | stored `CandleSeries` rows over real symbols; no venue |
| `NuclearSimExchange` | `src/simulator/nuclear_sim_exchange.py` | synthetic `TAPEA`/`TAPEB` tapes; no venue |

One connector method names the fifteen ccxt members a backend must serve, marks
the connector connected and drops the rate-limit interval to zero. The Stone
Tablet backend is such a backend: it answers those members from tablet rows
instead of the network, and the replay controller attaches it to a real
connector, so a replay runs the connector's own normalisation and fee code.

```python
def attach_backend(self, backend: Any) -> None:     # src/exchange/ccxt_connector.py
    """Serve every ccxt call from *backend* and mark the connector connected.

    *backend* must provide the fifteen ccxt members reached through ``_ex``:
    fetch_ohlcv, fetch_ticker, fetch_tickers, fetch_balance, create_order,
    cancel_order, fetch_order, fetch_open_orders, fetch_my_trades,
    fetch_order_book, markets, market, precisionMode, amount_to_precision
    """

class TabletBackend: ...        # src/exchange/tablet_backend.py
```

The venue registry carries its own status sets, all in `ccxt_connector.py`.

| Set | Count |
| --- | --- |
| `SUPPORTED_EXCHANGES` | 15 |
| `PREFLIGHT_URLS` | 15 |
| `PASSPHRASE_EXCHANGES` | 3 |
| `US_IP_BLOCKED_EXCHANGES` | 2 |
| `US_ACCOUNT_RESTRICTED_EXCHANGES` | 2 |
| `VERIFIED_EXCHANGES` | 1 |

One function turns those sets into the picker text a user sees. A blocked venue
is labelled as blocked, any other unverified venue is labelled untested, and a
venue needing a passphrase says so. Driven over the whole registry, fourteen of
the fifteen labels carry a caveat and one does not.

```python
def exchange_label(exchange_id: str) -> str:        # src/exchange/ccxt_connector.py
    """Return the picker label for *exchange_id*, carrying its status notes."""
    label = exchange_id.capitalize()
    notes: list[str] = []
    if exchange_id in US_IP_BLOCKED_EXCHANGES:
        notes.append("blocked from US")
    elif exchange_id not in VERIFIED_EXCHANGES:
        notes.append("untested")
    if exchange_id in PASSPHRASE_EXCHANGES:
        notes.append("passphrase required")
    if notes:
        label += f" ({', '.join(notes)})"
    return label
```

Fifteen checks cover those sets. One resolves every registry id to an importable
ccxt class through the connector's own resolver. One requires an https pre-flight
URL for every supported id. One pins the verified set to a single member. One
reads the label of every registry id against the rule above.

```python
def resolve_ccxt_class(...): ...        # src/exchange/ccxt_connector.py
                                        # tests/test_exchange_registry.py, fifteen checks
```

The exchange package holds 23 modules beside its package initialiser. Twenty sit
inside the static import closure of the entry point, which reaches 213
first-party modules and leaves 130 source modules outside it.

```
src/exchange/       23 modules, 20 inside the entry point's import closure
    api_docs            outside
    history_surface     outside
    market_data         outside
```

## What the exchange tests exercise

| Measurement | Count |
| --- | --- |
| test files under `tests/` | 535 |
| of those, naming `src.exchange` | 70 |
| `test_*` callables in those 70 files | 2,080 |

Sixteen of the seventeen interface members appear in at least one of those 70
files. The seventeenth, the asset logo lookup, appears in none.

```
member                  files naming it
    exchange_id             28
    connect                 22
    place_order              9
    get_ticker               7
    get_asset_logo_url       0
```

The same 70 files reach some modules far more than others, and leave five of the
23 with no test importing them at all.

```
module                  files importing it
    ccxt_connector          20
    base                    14
    currency_rate_monitor    7
    history_helpers          7
    history_read_contract    7
    tablet_backend           7

    api_docs                 0
    chart_data               0
    crypto_assets            0
    idempotency              0
    position_health          0
```

## How a test stands in for a venue

No test opens a socket to an exchange and none carries a credential. Each check
measures the shape of a call and the code around it, never a venue's answer.
Five stand-ins do that work.

| Stand-in | Where | Replaces |
| --- | --- | --- |
| a fake `ccxt` module put into `sys.modules` | 2 of the 70 files | the venue library, sync and async support both |
| an emptied `PREFLIGHT_URLS` | `tests/test_connect_does_not_block_calling_thread.py` | the pre-flight HTTP call inside `sync_connect` |
| a `socket.socket.connect` that raises | 19 test files | the wire itself, for the whole file |
| `tests/fixtures/venue_precision_metadata.json` | `tests/test_venue_precision_is_decimal_places.py` | published market metadata for 13 venues, captured from a public `load_markets` with no credential |
| `TabletBackend` | `src/exchange/tablet_backend.py` | the ccxt surface beneath a real connector |

The fixture covers 13 of the 15 registry ids. The two ids missing from it are
the pair in `US_IP_BLOCKED_EXCHANGES`, which refused the address the capture ran
from.

The credential file name appears in the test tree three times, across two
modules. Each of the three is a check that a tool raises rather than opening such
a file, and each builds its target under a temporary path. One of them, the
parametrised refusal over the runtime directories, sits beside a positive control
that lets a path outside them through.

```
coinbase_credentials    3 occurrences under tests/
    tests/test_capture_live_baseline.py
    tests/test_migration_verifier.py
```

## The four refusals around an exchange call

| Refusal | Where | What it turns away |
| --- | --- | --- |
| live-tree guard | `tests/conftest.py` | a suite run that created a path under `~/.acervator` or `~/.acervator_logs`, or changed anything under the Stone Tablet archive |
| `safe_urlopen` and `SafeRequest` | `src/core/safe_url.py` | a URL whose scheme is outside http and https, by policy at construction and at open, and by an opener carrying no file, ftp or data handler |
| `_redact` | `src/exchange/api_logger.py` | a param whose key holds any of nine credential substrings, swapping a mask in before `record` stores the entry |
| `guarded_place_order` | `src/trading/bot_container.py` | an order whose amount is not a finite positive number, at the single point every engine order passes through |

Each of the four carries checks that drive it to the refusal itself, so a green
run says the refusal still fires.

- `_live_roots` is injectable, so `tests/test_live_tree_guard.py` drives the
  guard against temporary roots across 22 checks. Two of them replay the two
  isolation breaches this project has shipped: a telemetry file created in the
  live tree, and a reservation-state autosave.
- `tests/test_safe_url_scheme_policy.py` holds 40 checks, splitting the policy
  half from the transport half because either can fail alone.
- The redaction checks name 13 credential field spellings that must come back
  masked, five benign fields that must come back unchanged as the positive
  control, and read the emitted log line for any param value — with a control
  proving the same handler sees a value placed in a benign field. One substring
  covers two credential spellings at once.
- Two modules call the venue's order method directly: the bot container, inside
  the guard itself, and the volume guard the container dispatches to. Ten sites
  across three trading modules call the guard, and no other route out exists.
  Five checks cover it: one drives unusable amount shapes into a recorder
  standing where the exchange stands, one drives a real amount through as the
  positive control, and three more pin the text of the refusal and which check
  turns an undersized order back.

The modules on each side of the last two, and the one substring that covers two
spellings:

```
tests/test_api_logger_redaction.py      "sign" masks signature and CB-ACCESS-SIGN
                                        the control places a value in reason

exchange.place_order called by      src/trading/bot_container.py
                                    src/trading/volume_guard.py
guarded_place_order called by       src/trading/scrumming/execution.py
                                    src/trading/scrumming_bot.py
                                    src/trading/extractor_bot.py
                                    ten sites, no other route out
tests/test_u6_venue_amount_gate.py      five checks
```

## The simulation battery

The venue record above is live money. Beside it sits a second body of evidence
that is not live at all: a battery of simulated runs, measured on an earlier
release, which is where the platform's headline win rate comes from. It is set
down here as the record of that run, with what this repository can and cannot
show about it stated beside it.

The battery covered 738 simulations, spanning 27 portfolio configurations,
capital from $400 up to $100K, six two-year historical periods — including the
2020 COVID crash, the 2021 ATH bubble and the 2022 brutal bear — and the
venue's fee tiers from VIP-0 through VIP-3. Parameters were identical
throughout, with no optimization per asset.

| Measurement | Result |
| ----------- | ------ |
| Win rate | 715 of 738, 96.9% |
| Total advantage against buying and holding | +$78.0B |
| Canonical 39-sim battery | 39 of 39, 100% |
| Historical 2020 to 2022, 39 sims | 39 of 39, 100%, +$3.16M total advantage |
| Capital scaling, 156 sims | 156 of 156, 100%, superlinear at $100K |
| Bear regime stability, 9 sims | $4,262 to $4,427 total, 4% CV |
| Profitable fee ceiling | up to 0.50% roundtrip |

The 23 runs that are not wins are concentrated in extreme single-asset bear
conditions, with 2022-class drawdowns of 64% to 94%, at the smallest capital
levels. Losses in those cases are marginal: $10 to $157 on $400 deployments.
The record makes no claim to win in a catastrophic single-asset collapse.

Six competing strategies were run over the same canonical 39 cases.

| Strategy compared against | Battery wins |
| ------------------------- | -----------: |
| Passive hold | 39 of 39, 100% |
| DCA weekly | 39 of 39, 100% |
| DCA daily | 39 of 39, 100% |
| Grid trading | 39 of 39, 100% |
| SMA 50/200 cross | 37 of 39, 94.9% |
| RSI mean-reversion | 35 of 39, 89.7% |

**This repository holds nothing behind those numbers.** No file in the tree
carries the per-run rows, and no commit on any branch ever added one. The
figures above are a record, not a measurement anything here reproduces.

**The Simulator tab did not produce them and could not.** It is not built, and
issue #117 carries its rebuild. Nothing a reader can run in this product today
re-derives the table above.

The queries, and the control that proves they can find a file:

```
git ls-files                                            no battery file in the tree
git log --all --diff-filter=ADR --name-only             no commit ever added one

git log --all --diff-filter=ADR --name-only -- generate_essay_ja.py
                                                        one commit, so the walk works
```

The third query is the control. The same walk over every branch does find a file
that once existed and is gone, so the empty answer above is a fact about the
battery and not about the query.

## Where a figure and a run carry less than they read

Two current-state findings bear on how a reader should take the numbers above.

**The header counters and their tooltips name different figures.** The header
cells read the two headline fields out of the fleet snapshot, and that snapshot
fills both from the year-to-date sum whenever the sum exceeds zero. The tooltips
beside them describe a cumulative total “since the platform run started” that
“resets to $0.00 only on a fresh process start” — the lifetime accumulator, which
the same snapshot carries separately and neither cell reads. The card and the
tooltip describe two different figures.

```
src/gui/main_tabs/header_strip_surface.py   counter_cells reads
                                                total_scrummed_usd
                                                total_folded_usd
src/gui/main_tabs/header_strip.py           the tooltips describe
                                                total_scrummed_usd_lifetime
```

**A Simulator run exercises an injected capital registry, not the live one.** The
bot constructor takes a capital registry parameter. The two Simulator
construction sites pass one; the three live sites pass none, and the reservation
mixin then falls back to the process-wide registry. The sell path refuses an
amount above the effective available quantity, but that pre-check sits inside a
`try` whose handler logs at debug level and continues, so a raise there lets the
sell proceed. A Simulator run says nothing about which registry a live bot
resolves, and nothing about what follows when that resolution raises.

```
ScrummingBot.__init__(..., capital_registry=None)   src/trading/scrumming_bot.py

passes one      src/simulator/fleet/fleet_replay_controller.py
                src/simulator/nuclear_controller.py

passes none     src/gui/main_window.py
                src/gui/live_bot_window.py
                src/trading/container/restore.py

falls back      _crr in src/trading/scrumming/capital_reservation_mixin.py
the pre-check   effective_available, inside a try in
                src/trading/scrumming/execution.py
```
