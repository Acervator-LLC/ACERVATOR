# Concept document — part 5 of 7

This part carries sections 4 and 5 in full, plus two passages that left the body
when his rulings of 2026-09-09 and 2026-09-10 took the space. The body carries the
rules. This part carries the measured inventories and the layout research a
builder needs.

| Section | What it is |
| ------- | ---------- |
| 2, the layout research | why one zone can carry the action and the map, and how forty participants a page stay legible |
| 3, the naming | one line for every class name, and why the names sit beside the existing vocabulary |
| **4. The trading profile as RPG metrics** | every field the conversion reads, measured |
| **5. Trade action to RPG action** | the three fill-time events, the action table, and the three gaps in the seam |

Nothing here is changed from the body it left. The same marks apply: HIS,
MEASURED, DECIDED, PROPOSED.

---

## 2. The tab — the layout research

These three passages sat in the body. They moved here when his rulings of 2026-09-09 and 2026-09-10 took the space, and nothing in them is changed.

### The Player window carries two jobs

**HIS.** *"Players appear taking actions as individuals or groups. This area
also displays the dungeon maps for the crawl and raid event types."*

**PROPOSED.** The answer turns on the dungeon's shape, not on the layout. Two
precedents show why.

A linear dungeon needs only a small map. Darkest Dungeon keeps its map in one
corner of the action view, and it can, because every corridor joins exactly two
rooms, has no corners, and every room matches every other in size. A map of that
shape stays readable at a small size.

A free-form dungeon needs a large map. Etrian Odyssey gave the map its own
screen so the player could map and act at once. Single-screen games of that kind
make the player toggle instead, and the commentary on those games agrees:
raising the map, reading it and lowering it is the worse experience.

Two of his four modes need no map at all. Monster Smash, individual and team, is
an arena. Only the Dungeon Crawl and the Raid carry a map.

**PROPOSED.** One zone can do both jobs, on one condition.

```
PROPOSED — the Player window, two modes in one zone

Monster Smash, 1a and 1b     all action, no map rail
Dungeon Crawl and Raid       action at full size, map as an inset rail
the condition                the generative dungeon is a linear room graph
```

The map rail sits along one edge and shows the room chain, the party's position
and which rooms the party has cleared. It never needs to be large, for the same
reason Darkest Dungeon's does not.

**If he wants a free-form dungeon instead, one zone cannot do both**, and saying
otherwise would be wrong. The alternative is a map mode that takes the whole
Player window, with the action reduced to a single banner line while the map is
up. That mode is the worse of the two, because the player loses the action view
at the exact moment of a move. That is the trade, stated plainly, and the
dungeon's shape is the decision that settles it. It is
Choice 4, in part 6.

### One hundred and twenty participants, legible

**HIS.** *"It must sharply display up to 120 participants for the largest
events, through a multi-page structure of 40 per page."*

Forty is not an arbitrary page size. Forty is the standard raid roster, and the
standard arrangement inside it is eight groups of five. Guides written for
players state the structure plainly: design the interface around forty frames in
eight groups.

Two rules come out of the same guides. Colour by role or class, because colour
carries awareness across a large field at a glance. And scale the tile down as
the count climbs, so every tile stays on screen rather than crowding the action.

**PROPOSED.** The page size is his. The arrangement inside it follows the
standard, because the standard already suits exactly this count.

```mermaid
flowchart TB
    subgraph P["Party window — page 1 of 3, 40 participants"]
        direction TB
        subgraph R1["upper row"]
            direction LR
            G1["group 1<br/>5 rows"]
            G2["group 2<br/>5 rows"]
            G3["group 3<br/>5 rows"]
            G4["group 4<br/>5 rows"]
        end
        subgraph R2["lower row"]
            direction LR
            G5["group 5<br/>5 rows"]
            G6["group 6<br/>5 rows"]
            G7["group 7<br/>5 rows"]
            G8["group 8<br/>5 rows"]
        end
    end
    PAGER["pager: 1 · 2 · 3"]
    P --> PAGER
```

Three pages of forty cover his one hundred and twenty. Each page is one raid's
worth, so a page boundary falls where a real group boundary already falls.

One advantage is worth spending deliberately. His Party window is the lower half
of the tab, not a corner of an action view. Each tile therefore gets far more
room than a game's raid frame gets. That room goes into the health bar, not into
extra fields.

### What a participant row shows, and what drops

**PROPOSED.** Four things survive at every density, ranked. The list is short on
purpose.

```
PROPOSED — what a participant row always carries

1  health bar       the one element that never shrinks
2  role colour      Salt, Sulphur or Mercury, as the fill colour
3  name             truncated, never wrapped
4  one mark slot    the single most urgent state, and nothing else
```

As the count climbs from six to forty, four things drop, in this order.

```
PROPOSED — the drop order

dropped first   the resource bar
then            the numeric health beside the bar
then            the class sigil, leaving only the role colour
last            the second mark slot
```

The health bar is never one of them. A roster that cannot report health has
stopped being a roster.

### The three zones as one picture

**HIS** for the arrangement, **PROPOSED** for the labels on the data.

```mermaid
flowchart TB
    subgraph TOP[" "]
        direction LR
        PW["PLAYER WINDOW — larger<br/>action from trade.filled<br/>map rail for crawl and raid"]
        ES["ENEMY SCREEN — square<br/>all enemies, animated<br/>takes damage from a SELL"]
    end
    PARTY["PARTY WINDOW — the lower half<br/>8 groups of 5, 40 a page, 3 pages<br/>health from target_balance and delta"]
    TOP --> PARTY
```

---

## 3. The classes — the vocabulary already taken, and the naming

### The hermetic vocabulary the platform already carries

**MEASURED.** Two hermetic axes already have owners, and neither is free for a
class name.

The five trophy tiers hold the four-colour alchemical path. Each drawing letters
its own stage across the face, and the epigraph runs around the ring.

`src/competition/trophy_generator.py` — `generate_trophy`'s stage map

```python
    stages = {
        "Harvest": "NIGREDO",
        "Gold Fold": "ALBEDO",
        "Bear Slayer": "CITRINITAS",
        "Grand Accumulator": "RUBEDO",
        "Ekthelius": "UNIO MYSTICA",
```

The price record holds the tablet. The historical price store is the Stone
Tablets, and a second tablet tree holds the Portfolio Battery's history.

`src/trading/stone_tablets/ra_paths.py` — the two roots

```python
_RA_ROOT: Path = Path.home() / ".acervator_ra_tablets"

RA_STONE_TABLETS_DIR: Path = _RA_ROOT
```

### The axis this array uses

**MEASURED.** Nothing in the tree uses the seven classical planets or their
metals. A search of every Python file under `src/` for the seven planet names
returns five hits, and not one of them is Acervator vocabulary: three name the
JUP token, two name Cardano's consensus in an asset description.

```
$ grep -rniE "\b(mercury|saturn|jupiter|venus|mars|azoth|ouroboros|trismegistus)\b" src/ --include=*.py
src/exchange/chart_data.py:67:    "JUP": "jupiter-exchange-solana",
src/exchange/crypto_assets.py:162: ... "using the Ouroboros Proof of Stake "
src/exchange/crypto_assets.py:168: consensus="Ouroboros Proof of Stake",
src/exchange/crypto_assets.py:457:        "Jupiter",
src/exchange/crypto_assets.py:458:        "jupiter-exchange-solana",
```

One line for each name.

| Class | Why that name |
| ----- | ------------- |
| Lead Ward | Saturn's quality is “chiefly to cool”; lead is the heaviest of the seven and the metal people hide behind |
| Tin Bulwark | Jupiter is a “temperate active force”; tin is the coat that keeps iron from rusting, so it guards another metal |
| Iron Edge | Mars is “chiefly to dry and to burn”; iron is the weapon metal |
| Solar Lance | The Sun is “heating and … drying”; gold cannot corrode, so the strike never blunts |
| Copper Conduit | Venus “chiefly humidifies” and counts as a beneficent planet; copper conducts, so one heal passes along a chain |
| Silver Mirror | The Moon's “power consists of humidifying”, and it shines by reflection; silver reflects |
| Quicksilver Draught | Mercury is “of common influence, productive either of good or evil” and “absorptive of moisture”; quicksilver is the only liquid metal |

Two Tanks, two Damage and three Healers.

### Why these names sit beside the existing ones

**PROPOSED.** Three reasons these names fit the tree's own vocabulary.

The shape matches. Stone Tablets pairs a concrete noun with a plain noun. Every
class name here does the same, and so do the five tier names — Harvest, Gold
Fold, Bear Slayer, Grand Accumulator, Ekthelius.

The register matches. No Latin reaches the screen. The Latin stays where it
already sits, on the trophy faces.

No class shares a stem with a tier. Gold Fold is a tier name, so the Sun's class
takes the planet's adjective instead of its metal. That is the only place a
metal steps aside, and collision is the reason, not taste.

### How the array serves independent levelling

**HIS.** From the 2026-09-07 brainstorm:

> each class levels independently … XP gained per action during a PoA event,
> with bonuses for efficacy and accuracy … no limit on how many classes a
> participant uses, but focus yields more power

**PROPOSED.** Three properties of this array serve that, and none of them needs
a tuning number.

Seven closes the set. The classical planets have numbered seven since antiquity,
so the tradition fixes the breadth ceiling. The array never needs extending, and
nobody has to invent an arbitrary eighth name.

Covering all three roles costs at least three classes, because the roles split
two, two and three. Spreading therefore costs something before any curve touches
it.

Efficacy and accuracy are separate numbers the platform already computes, and
they come from separate fields. Section 4 names them. Repeating one kind of
action cannot farm a bonus drawn from two independent readings.

### The alchemical colour stages are already spoken for

**MEASURED.** The trophy generator letters the five award tiers with the
four-colour path, so no class name may take one.

```
src/competition/trophy_generator.py:243-247
    "Harvest": "NIGREDO"
    "Gold Fold": "ALBEDO"
    "Bear Slayer": "CITRINITAS"
    "Grand Accumulator": "RUBEDO"
    "Ekthelius": "UNIO MYSTICA"
```

---

## 4. The trading profile as RPG metrics

**HIS.** From the 2026-09-09 tab layout:

> Players can be attacked. They do not lose money. Everything from the trading
> profile is converted or abstracted into RPG metrics. Players hold health pools
> based on character class, gear and level, following classic RPG structures.

### What the platform measures today

**MEASURED.** Five files hold every number this conversion needs.

`src/trading/container/config.py` — `BotStats`, the per-bot runtime figures

```python
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    total_scrummed_usd: float = 0.0
    total_folded_usd: float = 0.0
    ytd_scrummed_usd: float = 0.0
    ytd_folded_usd: float = 0.0
    verify_clean: int = 0
    verify_adjusted: int = 0
    verify_canceled: int = 0
    verify_samples: int = 0
    consecutive_errors: int = 0
    total_errors: int = 0
    realized_pnl_exchange: float = 0.0  # FIFO-matched realized P/L
    avg_entry_exchange: float = 0.0  # weighted-avg cost basis
    cost_basis_total_exchange: float = 0.0  # qty x avg_entry
    cash_balance_usd: float = 0.0
    standing_surplus_usd: float = 0.0
```

`src/trading/gate_chain.py` — `GateContext`, the distance from the dollar line

```python
    delta: float  # current_value - target_balance
    delta_pct: float  # |delta| / target_balance × 100
```

`src/trading/scrumming/snapshots.py` — `_compounding_snapshot`, the target and
how far it has grown

```python
            snap["target_balance"] = round(target, 6)
            snap["anchor_target_balance"] = round(anchor, 6)
            # Positive => target has grown above anchor via compounding.
            snap["accrued_growth_usd"] = round(target - anchor, 6)
            snap["max_target_growth_pct"] = growth_pct
            snap["cycle_growth_budget_usd"] = round(anchor * growth_pct / 100.0, 6)
```

`src/trading/trade_grader.py` — `TradeGrade`, four sub-scores per trade, each in
the range nought to one

```python
    execution_score: Optional[float]
    timing_score: Optional[float]
    strategic_score: Optional[float]
    outcome_score: Optional[float]
    overall: str
    overall_numeric: float
    execution_bps: Optional[float] = None
    mfe_pct: Optional[float] = None
    mae_pct: Optional[float] = None
    sb_improvement: Optional[float] = None
```

`src/trading/indicators/types.py` — `VotingSummary`, the consensus of twelve
voters

```python
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    net_score: float = 0.0  # Positive = bullish consensus
    consensus_confidence: float = 0.0  # 0.0 - 1.0
```

That twelve comes from a measurement, not from recall. Running the real module
reports it.

```
$ python -c "from src.trading.ta_engine import DEFAULT_WEIGHTS; print(len(DEFAULT_WEIGHTS))"
12
```

### The conversion

**PROPOSED**, from the fields above. The health pool comes from the dollar
target the whole engine defends, not from profit and loss. That satisfies his
rule directly: a player below the line carries a wound, and a player loses no
money by sitting below it.

```
PROPOSED — health, from the target and the distance from it

maximum health          target_balance
base health             anchor_target_balance
health from levelling   accrued_growth_usd      (target minus anchor)
gain cap per level      cycle_growth_budget_usd, max_target_growth_pct
current health          target_balance + delta
wound depth, percent    delta_pct
```

The target grows as folds land, capped per cycle. The pool therefore already
rises through play and already has a ceiling on how fast. That is a levelling
curve the engine computes today.

```
PROPOSED — the rest of the conversion

damage dealt          ytd_scrummed_usd, and the fill's usd on a SELL
healing done          ytd_folded_usd, and the fill's usd on a BUY
heal pending          fold_count, fold_total_usd
accuracy              execution_score, with execution_bps as the reading
efficacy              timing_score, outcome_score, strategic_score
overall grade         overall_numeric, and overall as the letter
critical hit          consensus_confidence at or above a threshold
fumble                verify_adjusted, verify_canceled, consecutive_errors
resource pool         standing_surplus_usd, cash_balance_usd
what stopped a hit    ChainResult.blocked, the nineteen gate labels
```

Scrum is damage and fold is healing. That is not a convenience. His award rule
is most damage done or most healed, and the two halves of the cycle are the two
award axes, so the game's scoreboard and the platform's scoreboard carry one
number each.

### What the design wants and the code does not carry

**MEASURED.** Seven things the design needs have no field anywhere in `src/`.
Saying so is the honest answer. Assuming a field is not.

```
absent — no field under src/ holds any of these

experience points      a level        a character class
gear, or any item      an enemy       a threat or aggro value
a guild
```

The search can report. The same case-insensitive pattern that returns nothing
for experience points and gear returns nine hits for the word inventory and two
for NFT, so the pattern is not blind.

```
$ grep -rniE "\b(xp|experience|char_level|player_level|gear|loot|inventory)\b" src/ --include=*.py
  9 matches, every one the word "inventory" in another meaning
$ grep -rniE "\bnft\b|\bloot\b" src/ --include=*.py
  2 matches, neither a loot field
```

Trophies are the one exception, and they are awards rather than gear. Five
drawings exist, one per tier, picked by name.

`src/competition/season_schedule.py` — the tier key the drawings use

```python
TIER_BY_NAME = {t.name: t for t in RARITY_TIERS}
```

Class, level and gear are therefore new state. The design should not pretend
otherwise. They belong in one new record per participant, and nothing in the
trading profile should stand in for them.

---

## 5. Trade action to RPG action

### The three events that fire after every fill

**MEASURED.** Three bus topics fire together on every filled scrum and every
filled fold. Between them they carry the damage, the accuracy, the critical
reading and the gate verdict, so one subscriber can drive the whole screen.

`src/trading/scrumming/execution.py` — the fold path, the three calls in order

```python
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                data={
                    "type": _fold_label,
                    "side": "BUY",
                    "amount": fill_amount,
                    "price": fill_price,
                    "usd": fill_amount * fill_price,
                    "profit": _growth_applied,
                    "operator_initiated": _operator_initiated,
                },
            )
            self._emit_voting_panel_snapshot_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD")
            )
            self._emit_gate_decision_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD")
            )
```

The gate emitter carries the health numbers as well as the blockers. Its payload
includes both snapshots.

`src/trading/scrumming/snapshots.py` — `_emit_gate_decision_at_fire`

```python
                scrum_blockers=list(self._last_gate_state.get("scrum_blockers") or []),
                fold_blockers=list(self._last_gate_state.get("fold_blockers") or []),
                tranche_snapshot=self._tranche_snapshot(),
                compounding_snapshot=self._compounding_snapshot(),
```

### The action table

**MEASURED.** The trade vocabulary is a declared tuple of ten, read off the emit
sites.

`src/core/emit_contracts.py` — `TRADE_TYPES`

```python
TRADE_TYPES: tuple[str, ...] = (
    "SCRUM",
    "FOLD",
    "CARTRIDGE_SCRUM",
    "CARTRIDGE_FOLD",
    "ENTRY",
    "HEDGE",
    "DIST",
    "AUTO_DETONATION",
    "SELF_DESTRUCT",
    "MANUAL_TRANCHE_FOLD",
)
```

**PROPOSED.** One on-screen action for each, triggered by the type field of a
`trade.filled` event.

| Trade type | Side | What the Player window would show |
| ---------- | ---- | --------------------------------- |
| SCRUM | SELL | A strike on the enemy, sized by the fill's dollars |
| FOLD | BUY | A heal on the player, sized by the fill's dollars |
| CARTRIDGE_SCRUM | SELL | A strike from a loaded magazine, one of a queued set |
| CARTRIDGE_FOLD | BUY | A heal from a loaded magazine |
| ENTRY | BUY | The player steps onto the field |
| HEDGE | either | A ward goes up; no damage and no heal |
| DIST | SELL | A strike that takes no loot; the surplus leaves the field |
| AUTO_DETONATION | SELL | A finishing blow; the excess rides in the profit field |
| SELF_DESTRUCT | SELL | The player leaves the field |
| MANUAL_TRANCHE_FOLD | BUY | A heal the operator casts by hand; the operator-initiated flag is true |

Three further on-screen events come from the other two topics.

```
PROPOSED — actions that are not a fill

a critical hit       consensus_confidence, off bot.voting_panel_snapshot
a blocked swing      a gate name in scrum_blockers or fold_blockers
a healed wound       delta rising toward nought across two gate events
```

### Three gaps in this seam

**MEASURED.** The live trading path does not reach the competition engine today,
and a builder needs to know exactly where it stops.

Nothing outside the package calls the engine's recording method. Two callers
exist, both inside one demo run.

```
$ grep -rn "record_trade" src/ tests/ main.py --include=*.py
src/competition/competition_engine.py:161:    def record_trade(
src/competition/local_testnet.py:735:                    engine.record_trade(
src/competition/local_testnet.py:743:                    engine.record_trade(
src/trading/analytics_engine.py:90:    def record_trade(self, trade: TradeRecord)
src/core/version_sweep.py:1433: a regex naming the method, not a call
```

The same search over a name in wide use returns fourteen references, so it
reports when there is something to report.

```
$ grep -rn "TokenLedger" src/ tests/ --include=*.py | wc -l
14
```

The two vocabularies differ in size. The competition record takes four role
values; the bus carries ten trade types. An adapter has to map ten onto four, or
the four have to widen.

`src/competition/bot_identity.py` — `TradeRecord`'s role field

```python
    role: str  # "SCRUM" | "FOLD" | "HEDGE" | "INIT"
```

Four different classes answer to the name `TradeRecord`. Whichever file the
adapter lands in, it must say which one it means.

```
$ grep -rn "^class TradeRecord" src/ --include=*.py
src/competition/bot_identity.py:43
src/trading/analytics_engine.py:20
src/trading/live_monitor.py:20
src/trading/trade_grader.py:19
```

The platform emits one of the three fill-time topics without declaring it. Six
topics carry a contract; the voting snapshot is not among them, so nothing pins
its payload shape.

```
$ python -c "from src.core.emit_contracts import CONTRACTS; print([c.topic for c in CONTRACTS])"
['trade.filled', 'bot.gate_decision', 'pnl.event', 'ta.voting',
 'market_inspector.scan_started', 'market_inspector.scan_finished']
```
