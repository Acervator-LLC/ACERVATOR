# Market Inspector — Cross-Market Topology Proposals

Reference specification (Diataxis: reference). Design spec.
Version at write: v3.23.66. Consumer: v3.23.67+ implementation
cascades. Author: Claude Opus 4.7. Reviewer: operator
(Ekthelius).

## 1  Problem

The Market Inspector currently populates the left half of the tab
with two tables: `HTF Signals` (higher-timeframe entry candidates)
and `Opposing Pairs (30-day Pearson)` (negatively-correlated
assets). The right half is empty (operator screenshot 2026-07-31
with red rectangle over the void).

Operator directive 2026-07-31: extend the Market Inspector to
identify cross-market topologies that can be fed into and adopted
by the Bot Swarm. Topology proposals appear on the right side of
the tab. Operator flagged this as needing significant pre-design.

## 2  Vocabulary

| Term         | Meaning                                                                                             |
|--------------|-----------------------------------------------------------------------------------------------------|
| Topology     | A candidate arrangement of bots + wires inferred from current market state                          |
| Archetype    | A named topology pattern with a specific detection heuristic (e.g. momentum funnel, mean-reversion) |
| Proposal     | One instance of an archetype filled in with specific asset tickers + suggested wire pcts            |
| Adopt        | Operator action that converts a proposal into real bots + wires in the Bot Swarm                    |
| Preview      | The confirmation modal that shows exactly what will be created before any live changes fire        |

## 3  Topology archetype catalogue

Four archetypes ship in v1. Each has a name, a shape, a detection
heuristic, and its own default wire percentages.

### 3.1  Momentum funnel

**Shape**: N bots on strongly-correlated assets (Pearson ≥ 0.75
over 30 days). Wires flow from the highest-24h-volume asset (the
leader) to each of the smaller lagger assets.

**Rationale**: correlated assets tend to move together on a lag.
The leader's scrum profit feeds ammo to the laggers so they can
fold at the coming dip and rebuild their positions.

**Wire defaults**: leader → each lagger at `20 %` (so 3 laggers →
60 % total outbound from leader).

**Detection heuristic**:
1. From the scout snapshot, take all pairs where quote ∈
   `{USD, USDC}`.
2. Compute pairwise 30-day Pearson correlation of daily closes.
3. Cluster with correlation ≥ 0.75.
4. Within each cluster, rank by 24h `baseVolume` desc; the top
   volume is the leader.
5. Emit one proposal per cluster of size ≥ 3.

### 3.2  Mean-reversion pair

**Shape**: 2 bots on strongly *anti*-correlated assets (Pearson ≤
-0.60). Wires flow bidirectionally at `25 %` each.

**Rationale**: when one moves up the other tends to move down.
Each scrum on the up-mover funds the fold on the down-mover.

**Wire defaults**: 25 % ↔ 25 %.

**Detection heuristic**:
1. From the existing Opposing Pairs table (already 30-day
   Pearson computed there).
2. Take rows where Pearson ≤ -0.60.
3. Filter to pairs where both assets have `baseVolume ≥ $1M`
   (liquidity gate — avoid dead pairs).
4. Emit one proposal per surviving pair.

### 3.3  Sector cluster

**Shape**: 4–6 bots on assets within the same sector (L2 tokens,
DEXs, memes, etc.). Wires form a star: the highest-volume member is
the hub; each spoke asset receives at `15 %` from the hub.

**Rationale**: sector cohorts often move together on narrative
flow. The largest-liquidity member is usually the sector's momentum
signal; smaller sector members lag.

**Wire defaults**: hub → each spoke at `15 %`.

**Detection heuristic**:
1. Source is the active/selected exchange's `fetch_markets`
   response (via `MarketPairsScout`) — never scan for hypothetical
   pairs that may not be listed on the exchange.
2. Load `src/trading/sector_map.json` — a hand-curated map
   `{asset_symbol: sector_tag}` covering assets the operator's
   exchange typically lists. Assets absent from the map are
   skipped for sector-cluster detection.
3. Intersect: only consider assets that appear both in the
   exchange market list AND in the sector map.
4. For each sector with ≥ 4 surviving assets, take the top-6-by-
   24h-baseVolume subset.
5. Highest-24h-volume = hub; others = spokes.
6. Emit one proposal per sector.

### 3.4  Distance-to-band spread

**Shape**: 2 bots on the same asset, one currently deep in Scrum
territory (high position vs target), the other currently deep in
Fold territory (low position). Wire from Scrum-deep bot to
Fold-deep bot at `30 %`.

**Rationale**: this is intra-asset rather than cross-asset. The
Scrum-deep bot has surplus profit forming; the Fold-deep bot needs
ammo for its next buy. Direct handoff avoids the round-trip through
compound growth.

**Wire defaults**: source → target at `30 %`.

**Detection heuristic**:
1. Iterate the operator's active bots (via BotManager, not the
   scout).
2. Compute per bot: `distance_to_target_pct = (position_val -
   target) / target × 100`.
3. Bucket into `deep_scrum` (dist ≥ +10 %) and `deep_fold` (dist
   ≤ -10 %).
4. Emit one proposal per (deep_scrum, deep_fold) pair that shares
   the same target asset.

## 4  Proposal data structure

Uniform shape across all archetypes. Serialised as a `dict`
because the Adopt handoff crosses process/thread boundaries.

```python
Proposal = {
    "id": str,                    # stable across scan refreshes
    "archetype": str,             # "momentum_funnel" | "mean_reversion_pair" |
                                  # "sector_cluster" | "distance_to_band"
    "title": str,                 # one-line human-readable summary
    "created_ts": float,          # epoch seconds (for staleness UI)
    "score": float,               # archetype-specific fitness [0, 100]
    "assets": list[str],          # e.g. ["ETH", "ARB", "OP"]
    "bots": list[{                # existing OR proposed-new bots
        "asset": str,             # target asset
        "quote": str,             # USD/USDC (may differ per bot)
        "symbol": str,            # e.g. "ETH/USD"
        "existing_bot_id": str,   # empty when a new bot needs to be created
        "role": str,              # "leader" | "lagger" | "hub" | "spoke" |
                                  # "scrum_deep" | "fold_deep" | "peer_a" | "peer_b"
        "suggested_target_usd": float,  # from asset_target_defaults.json;
                                        # $25 fallback when asset absent
    }],
    "wires": list[{               # exactly the wires the Adopt handoff creates
        "source_asset": str,      # matches one of `assets`
        "target_asset": str,
        "pct": float,             # 0..100, the operator's Rate spinbox equiv
        "rationale": str,         # short "why this wire" line for the preview modal
    }],
    "adopt_notes": list[str],     # e.g. "Requires 2 new bots (ARB, OP) — target $200 each"
}
```

## 5  Preview → Confirm → Auto-wire hand-off contract

Adopt flow when the operator clicks "Adopt" on a proposal card:

1. Modal `TopologyPreviewDialog` opens showing:
   - Title + archetype badge
   - Left column: the ASSETS list with each bot's role + status
     (`EXISTING` in green, `WILL CREATE` in amber)
   - Right column: the WIRES list — one row per proposed wire
     with source, target, pct, and rationale text
   - "New bot creation summary" line at the bottom (e.g. "This
     adoption creates 2 new bots at $200 each = $400 target
     capital.")
   - Two buttons: `Cancel` (default focus) and `Adopt`
2. On `Adopt` click:
   - For each proposed bot with empty `existing_bot_id`: open the
     Bot Wizard programmatically pre-filled with the suggested
     symbol + target; the operator confirms each bot creation.
     (Cancel at any wizard step aborts the entire adoption — no
     partial state.)
   - After all bots exist: for each wire in the proposal, call
     `SmartWireManager.set_wire(source_bot_id, target_bot_id, pct)`
     using the resolved bot ids.
   - Emit a `topology.adopted` event on the bus carrying the
     proposal id, so the Bot Swarm tab refreshes its wire
     display immediately.
3. On `Cancel`: no state change. The proposal card remains on the
   right pane; operator can re-open the preview later.

**Never**: skip the preview modal. Never adopt via right-click,
double-click, or any single-action shortcut. The preview modal is
the operator's last guard against a bad proposal.

## 6  Right-pane layout

```
Market Inspector Tab
┌────────────────────────────────────────┬───────────────────────────────────┐
│ LEFT (existing v3.23.62)               │ RIGHT (new v3.23.67)              │
│                                        │                                   │
│ [Refresh] [Include active markets]     │ [Refresh proposals] [Archetype ▾] │
│                                        │                                   │
│ HTF Signals                            │ Topology Proposals                │
│ ┌────────────────────────────────┐    │ ┌───────────────────────────────┐│
│ │ # Asset Signal Score Daily …    │    │ │ ▸ Momentum funnel: ETH → …    ││
│ │ 1 LIGHTER WATCHLIST 0.15 …      │    │ │   score 82  •  3 assets       ││
│ └────────────────────────────────┘    │ │   [Preview] [Dismiss]         ││
│                                        │ ├───────────────────────────────┤│
│ Opposing Pairs (30-day Pearson)        │ │ ▸ Mean-rev pair: BTC ↔ …      ││
│ ┌────────────────────────────────┐    │ │   score 74  •  2 assets       ││
│ │ Long side | Short side | corr …│    │ │   [Preview] [Dismiss]         ││
│ └────────────────────────────────┘    │ │                               ││
│                                        │ └───────────────────────────────┘│
│                                        │                                   │
│                                        │ Auto-refresh: every 10 min        │
└────────────────────────────────────────┴───────────────────────────────────┘
```

Left/right split via `QSplitter` (default 50/50, operator draggable).

Each proposal card:
- Collapsible caret so the details are hidden by default
- Score badge (color ramp: cyan ≥ 80, amber ≥ 50, grey below)
- `[Preview]` button (opens the modal — same modal as the Adopt
  flow, but Preview may be triggered without commitment)
- `[Dismiss]` button (marks this proposal id as suppressed for 24 h)

## 7  Integration points

Concrete files + functions.

### 7.1  New pure runtime module

**`src/trading/topology_proposals.py`** — one function per archetype
+ a top-level `detect_all_topologies(context) -> list[Proposal]`
that fans out and collects. `context` is a dict of the inputs each
detector needs:

```python
context = {
    "scout": get_scout(),                       # MarketPairsScout snapshot
    "opposing_pairs": [...],                    # from existing Opposing Pairs runtime
    "bot_manager": bot_mgr,                     # for the distance-to-band detector
    "sector_map": {...},                        # cached CoinGecko categories
    "now": time.time(),
}
```

Detectors return `list[Proposal]`. The top-level function unions,
de-duplicates by asset overlap, ranks by `score` desc, caps at 20.

### 7.2  New GUI module

**`src/gui/market_inspector_topologies.py`** — the right-pane
widget. Renders the proposals list, hosts the `[Refresh proposals]`
button, wires up the auto-refresh QTimer at 10 min cadence, and
opens `TopologyPreviewDialog` on `[Preview]`.

`TopologyPreviewDialog` is a separate class in the same file for
tests + reusability.

### 7.3  Bot Swarm hand-off

**`src/trading/smart_wire.py`** — add `set_wire(source_id,
target_id, pct: float)` as the atomic "create-or-update a wire"
primitive if it doesn't already exist (v3.15.68's `_wires` dict is
already mutated in place, but the adoption path needs a single
call it can invoke without knowing the internal representation).

**`src/gui/main_window.py`** — subscribe to `topology.adopted`
event so the Bot Swarm tab (`BotVisualizationTab`) can call its
existing wire-repaint path.

### 7.4  Market Inspector tab layout change

**`src/gui/market_inspector.py`** — swap the existing single-widget
layout for a `QSplitter(Qt.Horizontal)` with the current content on
the left and the new `MarketInspectorTopologies` widget on the
right.

## 8  Pin-test table

Twelve tests locked in the implementation cascade (v3.23.67).

| # | Test name                                        | Surface                       | Expected                                             |
|---|--------------------------------------------------|-------------------------------|------------------------------------------------------|
| 1 | `test_momentum_funnel_detector_finds_cluster`    | Pure detector                 | 3-asset cluster with corr 0.8+ → 1 proposal          |
| 2 | `test_momentum_funnel_ranks_by_volume`           | Pure detector                 | Highest volume in cluster becomes the leader         |
| 3 | `test_momentum_funnel_skips_clusters_below_3`    | Pure detector                 | 2-asset cluster produces no proposal                 |
| 4 | `test_mean_reversion_uses_opposing_pairs`        | Pure detector                 | Feeds off precomputed opposing-pair table            |
| 5 | `test_mean_reversion_liquidity_gate`             | Pure detector                 | Skips pairs with volume < $1M                        |
| 6 | `test_sector_cluster_star_from_highest_cap`      | Pure detector                 | Hub = highest cap; spokes = rest                     |
| 7 | `test_distance_to_band_pairs_deep_scrum_to_fold` | Pure detector                 | Cross-bot handoff proposal fires                     |
| 8 | `test_proposal_dedup_across_archetypes`          | Top-level orchestrator        | Same-asset overlaps collapsed by score              |
| 9 | `test_proposal_shape_matches_spec_§4`            | Schema pin                    | All required keys present + types                    |
| 10| `test_preview_dialog_blocks_adopt_on_cancel`     | Qt (headless smoke)           | Cancel → no calls to `set_wire` / no bot creation    |
| 11| `test_adopt_flow_calls_set_wire_per_wire`        | Qt (headless smoke)           | Confirm → N `set_wire` calls in proposal order       |
| 12| `test_dismiss_suppresses_for_24h`                | Widget state                  | Dismissed proposal id doesn't re-render for 24 h     |

## 9  Cascade sequence

Splitting Piece 3 into three implementable cascades so each ships
green.

- **v3.23.67 — Topology detectors + Proposal schema.** No GUI.
  New `src/trading/topology_proposals.py`, pin tests 1-9 from § 8.
  Ships without any operator-visible change; provides the pure
  data pipeline for the GUI.
- **v3.23.68 — Right-pane widget + preview modal.** New
  `src/gui/market_inspector_topologies.py`, `TopologyPreviewDialog`.
  Splitter layout on Market Inspector tab. Right pane populates
  from v3.23.67 detectors. `[Preview]` opens the modal but the
  `Adopt` button is disabled — safe to eyeball proposals without
  risk of accidental bot creation.
- **v3.23.69 — Adopt hand-off wired live.** Enable the `Adopt`
  button. Call the Bot Wizard for new bots. Call `set_wire` after
  all bots exist. Emit `topology.adopted`. Pin tests 10-12.

Each cascade passes green suite + release gate before the next
starts.

## 10  Decisions (operator answers, 2026-07-31)

1. **Sector data source**: use the active/selected exchange's
   `fetch_markets` API (via `MarketPairsScout`). No hypothetical-
   pair scans. Sector tagging via a local hand-curated
   `sector_map.json`; assets absent from the map are skipped for
   sector-cluster detection.
2. **Suggested target USD for new bots**: `$25` default, per-asset
   override map at `src/trading/asset_target_defaults.json`
   (checked-in, operator-editable). Missing entries fall back to
   `$25`.
3. **Dismiss expiry**: 24 h.
4. **Auto-adoption gate**: NONE. Preview modal mandatory for every
   adoption. (Sim-based preview deferred — the current sim engine
   is broken; the static preview modal per § 5 is what ships.)
5. **Proposal cap of 20**: accepted.

## 11  Sign-off gate — CLOSED 2026-07-31

Cleared. Operator answers locked in § 10; four archetypes in § 3
approved as-drafted. Implementation cascades v3.23.67-69 proceed
inline; each cascade must still satisfy `gui_archetype` +
`docs_archetype` + `check_release_readiness.py` before shipping.
