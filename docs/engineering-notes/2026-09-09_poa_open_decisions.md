# PoA — the open decisions, decided

Reference. Every decision below is taken. Each carries the reason, the source or
the property it was chosen to produce, the rule of his it was checked against,
and one line on what a participant with a hundred times another's Quintessence
gains from it.

Two marks separate the kinds of number.

```
TAKEN FROM A SOURCE   a published document states it; the document is named
CHOSEN                no source states it; the property it produces is named
```

One thing stays his, and it sits at the end. The custody question that was the
second one is answered by his own rulings of today, so it appears as decided
work inside section 15 rather than as a recommendation.

---

## 1. The eligibility reading — both conditions required

**Decided: a market rewards Quintessence only while it is inside the top 20 by
volume on that exchange AND the project is at least six months old.**

His sentence reads, in strict grammar, as either-sufficient. "Will not occur
outside of A or B" means it occurs inside A or B. His clause B, "have been not
been listed for less than six months", resolves to "listed at least six months".
The literal reading therefore admits a market that is top 20 but three weeks old,
and also a market that is four years old and almost untraded.

His purpose refuses both of those. An obscure pump has two halves. It is thinly
traded, and it is recent. Either-sufficient catches one half and lets the other
through in each direction. Both-required is the only reading that refuses a new
listing that climbed the table on its own pump, and the only one that refuses an
old micro-cap with no real depth.

Both-required is also the safe direction. It can refuse a market that should have
paid. It can never pay a market that should have been refused. That matches the
ruling already recorded in this issue for a missing age: refuse, because refusing
cannot be gamed by withholding data.

The age input is a real field and it is nullable.

```
CoinGecko /api/v3/coins/{id}   genesis_date : string, nullable
src/exchange/market_data.py    calls /api/v3/coins/markets
src/exchange/chart_data.py     calls /api/v3/coins/{cg_id}/ohlc
```

No call site in `src/` reaches the coin-detail endpoint today. The mapping it
needs is resolved — `crypto_assets.py` carries a CoinGecko id per asset.

**Source:** CHOSEN reading, from his stated purpose. The nullable field is TAKEN
FROM A SOURCE — the CoinGecko API reference for `/coins/{id}`.

**Checked against:** Quintessence only from PoA activity; organically
competitive at every level. Both-required narrows the reward surface to markets
with real depth and real history, so a market cannot be manufactured to pay.

**Whale test:** a participant with a hundred times the Quintessence gains
nothing. The rule names markets, not holders, and it removes the cheapest market
to manufacture.

---

## 2. The distil rate — one Quintessence for one dollar of exchange fee, before the grade curve

**Decided: the headline rate is 1 Quintessence per 1 USD of exchange fee paid on
a certified trade. The grade curve and the market allotment bound it. No second
scaling constant.**

The rate is 1:1 because every bound that matters already exists in his own
design. A certified trade's award is bounded five times over.

```
the market allotment   sized to that market's volume at activation
one allotment          one per participant per activation period
the share ceiling       at most x% of that market's pool (decision 3)
the candle cooldown     never fewer than 3 candles, longer for a larger award
the grade curve          the award is curved by the Trade Grading system
```

A sixth constant on top of five bounds would be an unanchored coefficient. It
would have no source, no domain proof, and nothing to hold it still.

The effective rate is far below 1:1. The grade curve multiplies the award by a
number in `[0.0, 1.0]`, and a wash trade scores near the bottom of that range.
The grading bands are measured.

```
src/trading/trade_grader.py:175  _letter_from_numeric
  A+  >= 0.93    A  >= 0.85    B  >= 0.70
  C   >= 0.55    D  >= 0.40    F  below
```

At a grade-neutral mean near 0.5, the cap of 33,000,000 Quintessence mints out
against roughly 66,000,000 USD of aggregate certified fees. That is the stated
consequence of 1:1 and it is checkable. If he wants minting to last longer, the
lever already exists in the tree rather than needing invention.

```
src/competition/season_schedule.py
  INITIAL_REWARD = 500_000      DECAY_FACTOR = 0.85
  MIN_SEASON_REWARD = 100
  season_reward(season)         geometric decay, floored
  cumulative_supply(through)    clamped at TOTAL_SUPPLY_CAP
```

### What has to be built to carry it

The platform cannot answer "how much fee has this bot ever paid". Four facts,
all measured.

**The only fee total falls.** `BotStats.fees_paid_exchange` is re-derived, not
accumulated.

```
src/trading/container/config.py:691   fees_paid_exchange: float = 0.0
src/trading/scrumming/reconciliation.py:63
    _trades = await self.exchange.get_my_trades(self.config.symbol, limit=500)
src/trading/scrumming/reconciliation.py:72
    self.stats.fees_paid_exchange = float(_ph.fees_paid_total)
```

`compute_position_health` computes the total from that bounded list. Past 500
trades the figure drops, because older fills leave the window. A Quintessence
rate reading it would pay twice for the same fill and then stop paying.

**Half of every cycle records no fee.** A fold is a buy. The venue-fee capture
discards a buy.

```
src/trading/scrumming/execution.py:216  _record_venue_fee
    _side_txt = str(getattr(_side, "value", _side) or "").lower()
    if _side_txt != "sell":
        self._last_sell_venue_fee = None
        return
```

**The pattern for a monotonic total already exists.** The year-to-date walk
pages the venue, de-duplicates by trade id, and takes the maximum of the
persisted and the counted value.

```
src/trading/scrumming/reconciliation.py:136
    YTD_TRADE_PAGE_LIMIT = 500        YTD_TRADE_MAX_PAGES = 40
src/trading/scrumming/reconciliation.py:139  sync_ytd_trade_count
    30-day windows from YTD_TRADE_ANCHOR_UTC, _seen_ids de-duplication,
    accumulates _ytd_scrum_usd and _ytd_fold_usd
```

A lifetime certified-fee total follows that shape, in the same walk, with the
same maximum-of-two guard. That guard is what makes it monotonic by
construction rather than by hope.

**Nothing can spend it.** `src/competition/` declares no debit-family method at
all.

```
def debit | def spend | def deduct | def withdraw | def transfer
  occurrences in src/competition/ : 0
TokenLedger methods: award, balance, awards, total_minted, remaining_ever,
  season_minted, leaderboard, supply_summary, save, load, _event_id
```

A fee paid in the base currency also needs a USD conversion. The reconciliation
code already carries a quote-to-USD rate for exactly that reason.

**Source:** CHOSEN rate, to produce a figure a participant can state without a
table — a dollar of fees, a Quintessence — and to avoid a sixth unanchored
constant. The 0.60% fee anchor is TAKEN FROM A SOURCE: Coinbase Advanced
publishes 0.40% maker and 0.60% taker at the entry volume tier, and
`BotConfig.trading_fee_pct` defaults to 0.6.

**Checked against:** Quintessence only from PoA activity; reward play not
position; never destroyed. A rate on fees paid is a rate on real trading done.

**Whale test:** a participant with a hundred times the Quintessence gains
nothing from the rate. The rate is the same for everyone, and the five bounds
above cut a large participant's share of any one market before the rate does.

---

## 3. The share ceiling — 5%

**Decided: one participant takes at most 5% of a market's Quintessence pool in
one activation period.**

Five per cent means at least twenty distinct participants must earn from a
market before its allotment can be exhausted. That keeps his third end condition
reachable. His rule ends an activation on expiry, on volume, or when the
allotment is exhausted — and a ceiling set too low makes the third one
unreachable, so every activation would end on the clock and the mechanism would
lose a third of its shape.

A ceiling set too high does the opposite. At 25%, four participants empty a
market. At 50%, two. Neither is a contest.

The ceiling composes correctly across markets. A participant drawing from five
activated markets takes at most 5% of each pool, which is 5% of their sum — not
25%. One number therefore bounds one market and the whole window, and no second
global cap is needed.

**Source:** CHOSEN, to produce a minimum of twenty earners per exhausted market
while keeping the exhausted end condition reachable. The number should be
re-derived once the live count of participants per market is measurable; the
measurement that would revise it is the distinct certified participants per
activation window.

**Checked against:** organically competitive at every level; reward play not
position; no gate behind a pay wall. A ceiling refuses capture without refusing
entry.

**Whale test:** a participant with a hundred times the Quintessence takes the
same 5% as anyone else. The ceiling is the single strongest anti-whale term in
the award path, because it is absolute rather than proportional.

---

## 4. Markets per window — five of the twenty eligible, and yes, a participant may draw from several

**Decided: a rotation activates five markets per exchange per window. One
participant may earn from every activated market they trade.**

Five of twenty sets the blanket-farming cost ratio at 4:1. A participant who
cannot see the rotation must trade all twenty eligible markets to cover five
that pay. That is the ratio this issue already said a design naming this
mechanism has to state rather than assert.

Fewer activated markets raise the ratio and shrink the reward surface. Three of
twenty gives 6.7:1, and with a 5% ceiling only sixty participant-slots exist per
window across the whole exchange. Five gives one hundred slots and a ratio that
still makes blanket coverage expensive.

Multi-market drawing is allowed because refusing it would punish the platform's
own shape. Bots and their wires, ledgers and tranches all load from one fleet
state, and the fleet runs many markets at once. Refusing multi-market draw would
make a large fleet earn like a single bot, and running many markets is capital at
risk and work done — it is play, not position. The 5% ceiling is per market and
composes, so allowing it costs nothing in concentration.

**Source:** CHOSEN, to produce a 4:1 blanket-coverage cost and one hundred
participant-slots per exchange per window at the 5% ceiling.

**Checked against:** organically competitive at every level; reward play not
position. Covering five markets well is harder than covering one well, so the
ceiling still has to be earned five times.

**Whale test:** a participant with a hundred times the Quintessence can cover
all five markets, and gains at most 5% of the window's emission — the same
fraction a participant who covers one market well takes of that market. Capital
buys presence, not share.

---

## 5. The Gold Fold and Bear Slayer lifetime caps — 100,000 and 10,000

**Decided: Gold Fold 100,000 ever. Bear Slayer 10,000 ever. Both enforced in the
contract that mints the NFT.**

Bear Slayer is not a new number. The tree already declares it.

```
src/competition/season_schedule.py  RARITY_TIERS
  Harvest            max_ever = None     base_value =     10
  Gold Fold          max_ever = None     base_value =     50
  Bear Slayer        max_ever = 10_000   base_value =    100
  Grand Accumulator  max_ever =  1_000   base_value =    500
  Ekthelius          max_ever =     21   base_value = 10_000
```

It is enforced off-chain only, counted from an in-process list.

```
src/competition/token_ledger.py:123
    if tier.max_ever is not None:
        tier_minted = sum(1 for e in self._events if e.tier_name == tier.name)
        if tier_minted >= tier.max_ever:
            raise OverflowError(...)
```

Gold Fold is the one genuinely missing number, and the tree's own ladder sets it.
The declared caps step by a factor near ten: 21, then 1,000, then 10,000. The
next step is 100,000, and it leaves Harvest as the only uncapped tier — which is
exactly what he said, caps on every tier except the lowest.

### A correction to the premise, and it changes where the caps must live

`seasonMinted` is not absent. It is written once and read nowhere on-chain.

```
contracts/CompetitionRegistry.sol:66   mapping(uint256 => uint256) public seasonMinted;
contracts/CompetitionRegistry.sol:303  seasonMinted[c.season] += tokenAmount;
```

No `require` compares it to a budget. The comment above it delegates the check to
Python, and `TokenLedger.award` does perform it. The season budget is therefore
real and lives off-chain, where it binds the Python ledger and not the chain.

The sharper finding is where the two existing caps sit. They are enforced in the
registry, and the NFT contract lets the owner mint around them.

```
contracts/CompetitionRegistry.sol:44  MAX_EKTHELIUS         = 21
contracts/CompetitionRegistry.sol:45  MAX_GRAND_ACCUMULATOR = 1_000
contracts/CompetitionRegistry.sol:289 require(mintedEkthelius < MAX_EKTHELIUS, ...)
contracts/CompetitionRegistry.sol:293 require(mintedGrandAccumulator < MAX_GRAND_ACCUMULATOR, ...)
contracts/ACRV.sol:56                 require(msg.sender == registry, ...)
contracts/AcervatorTrophy.sol:102     require(msg.sender == registry
                                              || msg.sender == owner(), ...)
```

The two declared caps therefore bound the token award inside
`CompetitionRegistry.adjudicate`, and bound nothing in the trophy itself. The
owner can mint a twenty-second Ekthelius trophy directly. A cap enforced in a
different contract from the one that mints is not a cap on the mint.

Both new caps therefore go into the trophy contract as constants beside a counter
per tier, and the owner bypass comes out. That is the same change the governance
section calls for on every other privileged function.

**Source:** Bear Slayer 10,000 is TAKEN FROM the tree — `RARITY_TIERS` already
declares it, so adopting it removes a disagreement rather than adding a number.
Gold Fold 100,000 is CHOSEN, to continue the factor-of-ten ladder the three
declared caps already form and to leave the lowest tier as the only uncapped one.

**Checked against:** his own statement that the trophies carry supply caps
excluding the lowest tier. Five tiers, four caps, Harvest open.

**Whale test:** a participant with a hundred times the Quintessence gains
nothing. Trophy tiers are won on percentile rank in a competition field, and
`RarityTier.qualifies` reads a rank, never a balance.

---

## 6. Where the Quint Wallet sits — a panel over the party window, with the balance always on screen

**Decided: two parts. A persistent Quintessence balance readout in the party
window's header, visible at all times. The full wallet as a panel that opens over
the party window, and over nothing else.**

Not a fourth zone. His layout fixes a ratio — the enemy screen is square, and the
player window is larger than the enemy screen because it carries trading action
translated to RPG action. A fourth zone takes space from one of those three and
breaks a constraint he stated.

Not a tab mode. Elite Events spend Quintessence per action, so a participant
needs the balance while the fight is live. A mode that replaces the tab hides the
fight at the moment the balance matters most.

The party window is the right host for three reasons from his own spec. It is
already paginated at forty per page, so it already owns a header with page
controls and a panel is one more page class in a zone that already switches. Its
content is a list, and a wallet holding Quintessence, trophies and loot is a
list. And it is the only zone with no live animation to occlude.

Overlaying an inventory on the lower interface band while the action view stays
live is a convention many group RPG interfaces share — bag and character panels
that open over the lower screen edge rather than replacing the scene appear in
World of Warcraft, Diablo and Final Fantasy XIV alike. The shared property is
that the fight never leaves view.

**Source:** CHOSEN placement, derived from his three stated zone constraints. The
overlay-not-replace shape is the convention named above.

**Checked against:** one PoA tab and only one. A panel and a header readout add no
surface.

**Whale test:** a participant with a hundred times the Quintessence sees the same
panel. Placement awards nothing.

---

## 7. Can a guild hold Quintessence — yes, as a spending treasury only

**Decided: a guild holds a Quintessence treasury. It can be filled two ways and
spent one way.**

```
filled by   the transfer skill, from a member, paying the bleed
filled by   the guild's own event awards
spent on    action costs for guild members, inside an event
never       paid out to a member's personal wallet
```

A guild is already an account-holding entity in his design. Guild membership
locks and stakes PoA tokens by rank, so a guild already holds something that a
member cannot freely withdraw. A Quintessence treasury is the same shape applied
to the second asset, not a new kind of thing.

The treasury exists because his action-budget ruling needs a third party. His
words name the politics as the point — a higher-ranking member persuading a
fellow member to use an expensive skill. With no treasury the only possible
payers are two individuals, and the negotiation is bilateral. A treasury is the
thing a guild can argue about, and arguing about it is the mechanism.

The two guards are what keep it from becoming a concentration vehicle. Every unit
entering a treasury pays the transfer bleed, so funding a guild is taxed at the
moment it is attempted. And no path runs from the treasury back to a personal
wallet, so a guild cannot be used to store a large holding or to buy loyalty with
a payout.

A treasury is a held address. The conservation law keeps three buckets and gains
no fourth.

```
wallets + held addresses + the platonic == total ever distilled <= 33,000,000
```

**Source:** CHOSEN, derived from his guild-rank staking rule and his action-budget
ruling. The two guards are CHOSEN, to produce a guild account that can pay for
play and cannot store wealth.

**Checked against:** reward play not position; never destroyed; no gate behind a
pay wall. A treasury pays for actions, never for admission.

**Whale test:** a participant with a hundred times the Quintessence can fund a
guild treasury and pays the bleed on every unit moved, and can never get a unit
back out to a wallet. The treasury converts a holding into spent actions, which
is the opposite of concentration.

---

## 8. Who pays a persuaded cast — the actor, with an optional treasury underwrite the actor must accept

**Decided: the participant whose character performs the action pays for it. A
guild officer may commit treasury funds to cover it, and the actor must accept
that commitment before the action runs. The requester never pays.**

His own sentence decides the default. He writes that higher-ranking members must
navigate politics and relationship to convince fellow members **to use** the
expensive skill. The member uses it. A cast the user does not pay for needs no
convincing, so a requester-pays rule deletes the mechanism he described in the
same sentence that described it.

The treasury underwrite is what keeps an expensive action reachable without
removing the negotiation. It takes two acts by two people — an officer commits,
the actor accepts — so the conversation still happens, and it now has a second
subject: whose money.

A resource one member spends while the whole group benefits is a shape many group
RPG systems share. A healer's mana, a tank's cooldown and a support player's
consumables are all paid by one player and enjoyed by the party, and in every one
of them the spender is the one who decides.

**Source:** TAKEN FROM his sentence — "convince fellow members to use expensive
skills" names the actor as the spender. The underwrite is CHOSEN, to produce a
reachable high-cost action that still requires two people to agree.

**Checked against:** organically competitive at every level, applied inside a
team. The cost stays on the table.

**Whale test:** a participant with a hundred times the Quintessence can
underwrite other members' casts and cannot force one — the actor must accept, and
the actor's performance is what the redistribution pays. Buying a guild's actions
funds other people's scores.

---

## 9. The Action Budget Curve — five bands, a hundred to one

**Decided: five bands, priced from 0.001 to 0.100 Quintessence, a cheapest-to-
dearest ratio of 100:1.**

```
band   cost     what sits in it
x1     0.001    move, switch weapon, take an item from a bag
x3     0.003    a basic attack, a basic heal
x10    0.010    a class ability on a cooldown
x30    0.030    a group-wide ability, a threat move across the field
x100   0.100    a multi-turn spell, and the decisive tactics beside it
```

Five bands, because the action economies of published tabletop systems settle at
three to five distinct action classes for the same reason — a participant has to
hold the whole list in their head during a turn. Pathfinder Second Edition uses
three actions plus a reaction; the earlier Pathfinder and Dungeons and Dragons
shape is a move plus a standard plus a full-round action spanning both; the
Unchained revision allows up to three acts combinable into advanced ones. The
shared property is a small closed set with a clear cheapest and a clear dearest,
and multi-turn casting as the top cost.

The ratio is 100:1 and not larger because the answer must sometimes be yes. At
100:1 a participant who moves two hundred times in an event spends 0.2
Quintessence, and one decisive cast costs 0.1. The cast is worth arguing about
and it is not ruinous. At 1000:1 a single cast costs five events of movement, so
the answer is always no, and a negotiation with a foregone conclusion is not a
negotiation.

Each band is roughly three times the one below it. That is the same geometric
spacing the trophy caps use and the skill curve uses, so the design carries one
spacing convention instead of three.

The per-event arithmetic is the check that matters.

```
200 x1 + 60 x3 + 20 x10 + 5 x30 + 2 x100
  = 0.200 + 0.180 + 0.200 + 0.150 + 0.200
  = 0.93 Quintessence for one full Elite Event
```

Against the 1:1 distil rate, a participant paying 30 to 60 USD of exchange fees
in a week funds thirty to sixty Elite Events, and 75% of the spend returns by
performance. That is affordable, which is his rule, and it is the arithmetic that
makes the rest of the economy hold together.

**Source:** CHOSEN numbers. The five-band count and the cheap-move, dear-multi-
turn-cast shape are TAKEN FROM the published action economies named above. The
100:1 ratio is CHOSEN, to produce a decisive action that costs about half an
event's movement — arguable, not prohibitive.

**Checked against:** no gate behind a pay wall; affordable fees; organically
competitive at every level. A participant can act continuously without running
dry.

**Whale test:** a participant with a hundred times the Quintessence can take the
dearest action far more often. What that buys is bounded by the event's own
action economy — a turn holds a fixed number of actions, and 75% of every unit
spent returns by performance, so spending more funds the better players.

---

## 10. What "significant" means — the top 20% by lifetime Quintessence distilled, among participants active in the last 90 days

**Decided: Elite Event entry opens to a participant in the top 20% by lifetime
Quintessence distilled, measured against every participant who certified at least
one graded trade in the preceding 90 days.**

Three choices, each with a reason.

**Lifetime distilled, not the current balance.** Elite Events spend Quintessence
per action. A balance test would remove Elite eligibility from the participant
who plays Elite Events, which is self-defeating. Lifetime distilled only rises,
is earned solely by certifying real trades, and is untouched by spending.

**Active in 90 days, not all holders.** An all-holders population includes
dormant accounts. Dormant accounts never grow their figure, so as time passes
they sink to the bottom of the distribution and drag the 20% threshold down with
them. The gate would loosen every year without anyone deciding to loosen it. The
event's own entrants cannot be the population, because the population would then
be defined by who already got in.

**Twenty per cent, not one.** Elite Events carry lower entry fees and per-action
spending. They are built to be played, not to be a closed room. The tree's own
rank ladder puts its broadest tier at 50% and Gold Fold at 10%, so 20% is the
band between broad and rare in a vocabulary the code already uses.

```
src/competition/season_schedule.py  RarityTier.rank_pct_max
  Harvest 0.50   Bear Slayer 0.25   Gold Fold 0.10
  Grand Accumulator 0.01   Ekthelius 0.001
```

**Source:** CHOSEN percentile and population, to produce a gate that a steady
trader clears and a dormant account does not, and that does not drift as
33,000,000 mints out. The percentile band is TAKEN FROM the tree's own
`rank_pct_max` ladder.

**Checked against:** reward play not position; no gate behind a pay wall. A
percentile on earned activity is a measure of play. It cannot be bought, because
the figure it reads comes only from certified trades.

**Whale test:** a participant with a hundred times the Quintessence is in the top
20%, and so is every participant who has traded steadily for a few months. The
gate is a floor, not a ranking, and inside the event the action budget and the
performance redistribution decide the outcome.

---

## 11. The loot rarity scale — five tiers from the twelve gates, weights falling to one in two hundred

**Decided: five tiers, named for five of the twelve gates of the Great Work, in
their published order.**

```
tier           gate   base weight   Elite weight
CALCINATION      1        60.0%         55.0%
PUTREFACTION     5        25.0%         22.9%
SUBLIMATION      8        11.0%         10.1%
FERMENTATION     9         3.5%         10.5%
EXALTATION      10         0.5%          1.5%
```

Both columns total 100.0%. The Elite column multiplies the two rarest weights by
three and renormalises the rest in proportion, which is his rule for the Elite
variant — rarity and drop rate both rise to higher quality and more powerful
items.

Five tiers with colour-coded names and weights falling by roughly a factor of
two to three per tier, with a sub-percent top tier, is the convention across loot
systems rather than any one game's table. The Diablo and Borderlands lineage
runs white, green, blue, purple, orange; the common, uncommon, rare, epic,
legendary naming appears widely; and the published top-tier figures sit in the
same band, with Borderlands 4 shiny items at 0.3% and boss legendary rates raised
from 3% to 10% as a deliberately boosted case. The shared property is a tail thin
enough that the top tier is an event.

### The names were checked for collision, not assumed free

Every candidate was counted across `src/`, `contracts/` and `docs/`.

```
CALCINATION   0 files      SEPARATION    5 files   <- rejected
PUTREFACTION  0 files      CONJUNCTION   3 files   <- rejected
SUBLIMATION   0 files      MULTIPLICATION 2 files  <- rejected
FERMENTATION  0 files      PROJECTION    2 files   <- rejected
EXALTATION    0 files
```

`separation` is already a quantity inside the Vortex indicator, and `conjunction`
already means a boolean AND in the engine's own comments. Two spellings of one
word is the defect those rejections avoid. Distillation was rejected for a
different reason: a bot already distils Quintessence, so the verb is taken.

The five chosen names collide with nothing else either. They are not the four
colour stages that letter the trophy tiers, not the seven planetary class names,
and not Gold Fold.

**Source:** the names and their order are TAKEN FROM a published source — George
Ripley, *The Compound of Alchemy* (1471), the twelve gates, in the order the text
gives them: Calcination, Solution, Separation, Conjunction, Putrefaction,
Congelation, Cibation, Sublimation, Fermentation, Exaltation, Multiplication,
Projection. The weights are CHOSEN, to produce a factor-of-two-to-three fall per
tier and a top tier at one in two hundred, inside the published band above.

**Checked against:** no gate behind a pay wall; reward play not position. Loot
comes from dice rolls, his own rule, and the Elite table is reached by the
earned percentile in decision 10.

**Whale test:** a participant with a hundred times the Quintessence rolls on the
same table. Holding changes no weight. The Elite table is reached by lifetime
distilled, which is a record of trading, not a balance.

---

## 12. Does loot share the trophy contract — no. Its own contract, multi-token, with the shared helpers factored into a library

**Decided: loot gets its own ERC-1155 contract. The metadata helpers come out of
the trophy contract into a library both use.**

### Why sharing fails, measured

**The mint signature is competition-shaped and fixed.**

```
contracts/AcervatorTrophy.sol:134  mint(
    recipient, tier, tierEmoji, season, competitionId,
    rank, fieldSize, advantageBps, marketRegime, merkleRoot )
```

Every one of those parameters is written into the trophy metadata struct. None of
them is a loot concept. Loot needs rarity, item statistics, bonuses and stacking.
A struct in a deployed non-upgradeable contract cannot gain a field, so carrying
loot here means encoding item data inside the competition strings.

```
contracts/AcervatorTrophy.sol:44   struct TrophyMetadata
  tier, tierEmoji, season, competitionId, rank, fieldSize,
  advantageBps, marketRegime, merkleRoot, botWallet, mintedAt
```

**One image per tier, by construction.**

```
contracts/AcervatorTrophy.sol:148
    require(bytes(_tierSvgB64[tier]).length > 0,
            "Trophy: SVG not uploaded for this tier");
```

The file's own header states that each trophy of the same tier is visually
identical and metadata differentiates them. Generative loot with deep RPG
functions is the opposite case.

**The owner can mint around the caps.** The trophy's gate accepts the owner; the
token's gate does not.

```
contracts/ACRV.sol:56             require(msg.sender == registry, ...)
contracts/AcervatorTrophy.sol:102 require(msg.sender == registry || msg.sender == owner(), ...)
```

Putting loot behind that modifier puts loot behind that bypass.

**One correction to the premise.** The artwork is not a constant set at
deployment. It is a mutable mapping an owner can rewrite at any time.

```
contracts/AcervatorTrophy.sol:64   mapping(string => string) private _tierSvgB64;
contracts/AcervatorTrophy.sol:115  function setTierSvg(...) external onlyOwner
```

That makes sharing cheaper than the premise suggested, and it makes the contract
worse on a different axis: the art of an awarded trophy can be changed after the
award. It is one more privileged function for the governance section to remove.

### What each option costs

```
share           no new deployment; loot inherits the competition struct, the
                one-image-per-tier rule, the owner mint bypass, and a single
                token-id space in which tokensOfOwner cannot tell loot from
                a trophy
extend          Solidity cannot add storage to a deployed contract, so a
                subclass is a new deployment — identical deploy cost to a new
                contract, saving only the re-writing of tokenURI and its
                string helpers
own contract    one more deployment and one more address the wallet reads;
                the helpers move to a library both contracts import
```

Extending and writing a new contract cost the same deployment. The only saving
from inheritance is code that belongs in a library anyway.

ERC-1155 rather than ERC-721 because loot is generative, tradable, and many
participants will hold identical common items. The standard states the case
directly: a single deployed contract may hold "any combination of fungible
tokens, non-fungible tokens or other configurations (e.g. semi-fungible tokens)",
each token id carrying "its own metadata, supply and other attributes", with
batch transfer saving transaction cost. A common drop is fungible with itself. An
ERC-721 mints a distinct token id for every copy, which is the expensive shape
for exactly the tier that drops 55 to 60 per cent of the time.

**Source:** the contract facts are MEASURED at the lines above. ERC-1155's
suitability is TAKEN FROM a published source — EIP-1155, abstract and motivation.

**Checked against:** never destroyed; no gate behind a pay wall. A separate
contract changes no supply rule and gates nothing.

**Whale test:** a participant with a hundred times the Quintessence gains nothing
from the contract layout. Loot is tradable by his rule either way.

---

## 13. The skill growth curve — ten levels, a cost multiplier of 2.5 per level, progress counted in quality-weighted uses

**Decided: every skill has ten levels. Level one costs one unit of progress;
each level costs 2.5 times the one below. A use contributes its own quality, in
`[0.0, 1.0]`, not a flat one. Effect rises by 0.1 per level, so a maxed skill is
twice an untrained one.**

```
level   cost of that level   cumulative
 1             1.0                1.0
 2             2.5                3.5
 5            39.1               64.2
 8           610.4            1,016.0
10         3,814.7            6,356.7
```

Level ten alone is 60% of the lifetime cost. Topping out takes about 6,357
quality-weighted uses.

### The shape, and the mechanism he corrected

He named Eve Online, so the shape is his reference. A compounding curve whose
last level costs many times the first is what long-horizon progression systems
share, and three of them state it in published numbers.

```
Eve Online        250, 1,415, 8,000, 45,255, 256,000 cumulative skill points
                  for levels I-V at rank 1 — a constant step of about 5.66,
                  so the last level is 82% of the skill's whole cost
RuneScape         floor(L + 300 * 2^(L/7)) summed and divided by four; the
                  requirement doubles about every seven levels, level 99
                  totals 13,034,431 experience, and level 92 is about half
                  of that total
EverQuest         a hard-coded multiplier of 3.1 at levels 61 and above
```

The convention is a constant multiplier, applied per level or per band, with the
tail holding most of the total. A multiplier of 2 puts the last level at half the
lifetime cost, which is RuneScape's level-92 property expressed as a doubling.
2.5 puts it at 60%.

**Eve trains on elapsed time and he has said through use.** The shape therefore
transfers and the mechanism does not. The unit of progress here is a counted use,
never a duration, and a clock-based curve would contradict his own sentence.

Quality-weighting the use is what stops repetition from being the strategy. His
class experience already carries bonuses for efficacy and accuracy, so a skill
use contributing its own quality is consistent rather than new, and it means a
thousand sloppy uses are worth less than two hundred good ones.

The effect spread is deliberately small against the cost. A maxed skill at 2.0x
an untrained one, across a ladder costing 6,357 uses, keeps breadth viable while
satisfying his rule that focus yields more power — twice in one skill beats 1.1
times in ten.

**Source:** the shape and the constant-multiplier convention are TAKEN FROM the
three published curves above. Ten levels, the 2.5 multiplier and the 0.1 effect
step are CHOSEN, to produce a final level holding 60% of the lifetime cost, a
ladder of roughly 6,357 quality-weighted uses, and a 2.0x spread from bottom to
top.

**Checked against:** reward play not position; no gate behind a pay wall.
Progress comes only from doing the thing.

**Whale test:** a participant with a hundred times the Quintessence gains nothing.
A level costs counted uses and Quintessence cannot buy a use.

---

## 14. The bleed rate, the transfer duration, and how the platonic redistributes

**Decided, three parts.**

```
bleed        8% of the amount at skill level 1, falling linearly to 4% at
             level 10
duration     hours = amount / (10 x skill level), minimum one hour, and one
             transfer in flight per participant
respawn      bled units join the next activation's market allotments and are
             awarded by the same certified-trade mechanism, curved by grade
```

### The bleed

A single-digit percentage sink on a transfer, reducible by a skill, is the
convention across player-driven virtual economies. Two published cases bracket
the band.

```
Eve Online            sales tax from 7.5%, reducible to 3.37% through the
                      Accounting skill; broker fee of 0.5% to a sink on
                      Upwell structures
World of Warcraft     a flat 5% auction house cut on the sale price
```

Eight per cent falling to four sits inside that band at both ends and halves
across the ladder, which is what Eve's skill reduction does. It never reaches
zero, so concentration is always taxed.

The self-taxing property is the part worth stating. The only way to reduce the
bleed is to raise the transfer skill, and the skill grows through use, and every
use is a transfer that bleeds. Climbing the ladder is paid for in bled
Quintessence. A participant cannot buy a cheaper bleed.

### The duration

Linear in the amount and inverse in the level, with one transfer in flight at a
time.

```
1,000 Quintessence at level 1    100 hours     over four days
1,000 Quintessence at level 10    10 hours
```

The single-slot rule is what closes the split attack. Without it, a participant
splits a large transfer into many small parallel ones and the duration term does
nothing. With it, splitting changes nothing at all, because the slot serialises
them and the total time is the same. That closes the hole with a rule rather than
with an exponent nobody could anchor.

The effect he asked for follows: nobody arms themselves just before an event,
because the transfer cannot complete inside the window.

### The respawn

Bled units return through the mechanism that already exists. They are added to
the next activation's market allotments and awarded for certified trades, curved
by the Trade Grading system, bounded by the one-allotment rule and the 5% ceiling.

That keeps his own ruling intact. Redistribution is by performance, never by
spend, and it reads the same numbers the awards already read rather than
introducing a third scale.

The sender is not excluded from the respawn. Excluding them would be a special
case that invites evasion through a second identity, and their recovery is
bounded twice over — by the 5% share ceiling and by their own trade grades. The
bleed is a tax paid to everyone, and everyone includes the payer at everyone's
rate.

The platonic is the third bucket, so the conservation law is exact and complete.

```
wallets + held addresses + the platonic == total ever distilled <= 33,000,000
```

A verifier omitting the platonic reports a shortfall that is not a defect.

**Source:** the bleed band is TAKEN FROM the two published transaction sinks
above; the skill-reducible shape is Eve Online's Accounting mechanic. The 8%-to-4%
pair, the duration function and the single-slot rule are CHOSEN, to produce a
transfer that is always taxed, cannot be sped up by splitting, and cannot be
completed inside an event window.

**Checked against:** never destroyed — a bleed despawns transferable units and
reduces no supply; reward play not position; organically competitive at every
level.

**Whale test:** a participant with a hundred times the Quintessence pays eight per
cent to move it, cannot move it faster by splitting it, and funds everyone else's
allotment when they try. Concentration is taxed at the moment it is attempted,
and the tax is paid to the other participants.

---

## 15. Governance — equal votes, a tiered franchise, and migration rather than a proxy

His ruling: *"No, vote efficacy is not weighted by Quint amount held."* Holdings
decide which issue levels a holder may vote on, never how much a vote weighs.
And: *"PoA should be a self-certifying, socio-economic organic system that lives
after my hands after the first nodes connect on a live net."*

### The admin surface today, measured

Every privileged function in the three contracts.

```
ACRV.sol                 Ownable, Pausable. Owner set to the deployer at :48.
                         pause() :111   unpause() :112   both onlyOwner
                         _update :116 carries whenNotPaused
AcervatorTrophy.sol      Ownable. Owner set to the deployer at :87.
                         setTierSvg :115 onlyOwner — rewrites any tier's art
                         onlyRegistry :102 accepts the owner, so the owner can
                         mint any tier directly
CompetitionRegistry.sol  Ownable, ReentrancyGuard. Owner set at :126.
                         setPriceFeed :137   openCompetition :165
                         activateCompetition :205   closeForSubmission :216
                         adjudicate :280   advanceSeason :350
                         cancelCompetition :356     all onlyOwner
```

Three facts follow. Two of them come from published documentation rather than
from the tree.

Three of the library's own published behaviours decide what those functions
reach. Each is quoted from the OpenZeppelin version 5 documentation. None of
these names belongs to this tree; the library is an unresolved import here.

```
ERC20 update hook    "Transfers a value amount of tokens from from to to, or
                     alternatively mints (or burns) if from (or to) is the
                     zero address" — minting and transferring both route
                     through the one hook
Ownable transfer     immediate, with no acceptance step. The two-step
                     extension is a separate contract: "the new owner must
                     call acceptOwnership in order to replace the old one"
Ownable renounce     "Leaves the contract without owner. It will not be
                     possible to call onlyOwner functions."
```

One pause therefore freezes every holder and the award path together, because
both travel through the same hook. The key moves in one call, to an address that
never confirms it can receive it. And renouncing while paused makes the freeze
permanent and unrepairable.

Fourteen privileged functions across the three contracts, and `adjudicate` alone
means the owner decides every award. None of them serves a mechanism in his
design. Distribution and reclaim are protocol mechanics, and removing these
powers costs him nothing he has asked for.

### The ladder, and the standards behind it

Three published documents carry the conventions. Each was read rather than
recalled.

**Semantic Versioning 2.0.0** classifies a change by what it breaks. Clause 6:
PATCH “MUST be incremented if only backward compatible bug fixes are
introduced”. Clause 7: MINOR, “if new, backward compatible functionality is
introduced to the public API”. Clause 8: MAJOR, “if any backward incompatible
changes are introduced to the public API”.

**EIP-1** sorts proposals by how much of the system they reach: Standards Track
with the categories Core, Networking, Interface and ERC, plus Meta and
Informational. Core covers “improvements requiring a consensus fork”. Interface
covers “language-level standards like method names and contract ABIs”.
Informational “describes a design issue, or provides general guidelines or
information ... but does not propose a new feature”, and a reader may disregard
it.

**BIP-2** gives the same three-way split — Standards Track, Informational,
Process — and, more usefully, escalates the **acceptance bar with the reach of
the change**. A soft fork needs a documented miner majority. A hard fork needs
broader economic adoption by merchants and holders actually transacting under the
new rules. A peer-services change needs 1% of public listening nodes for a
month. An API change needs two independent compatible implementations. That is
the published precedent for tiering the bar rather than the weight, which is what
he asked for.

**CVSS version 4.0** supplies the severity scale, Table 22: None 0.0, Low 0.1 to
3.9, Medium 4.0 to 6.9, High 7.0 to 8.9, Critical 9.0 to 10.0.

The ladder runs four levels. Security classifies across them rather than beside
them.

```
level            what sits at it                              holding  quorum  approval  delay
L1 INFORMATIONAL a manual page, a published figure that            1 Q     10%    simple    none
                 binds nothing
L2 PATCH         a backward-compatible fix that changes no        25 Q     20%    simple    2 days
                 rule a holder relies on
L3 INTERFACE     a backward-compatible addition: a new event      75 Q     30%    60%       7 days
                 type, a new loot tier, a market on the
                 eligible list
L4 CORE          any change to a rule a holder relies on:        150 Q     40%    67%      30 days
                 the cap, the distil rate, the bleed, the
                 share ceiling, the redistribution basis,
                 the contract set
```

Quorum is a fraction of eligible voters at that level, never of supply, because
every vote counts the same.

Security is a severity, not a level. A Low or Medium finding is repaired at L2. A
High or Critical finding usually changes a rule a holder relies on, so its repair
is L4. A fifth level for security would overlap the four and leave the
classification ambiguous.

### The thresholds, and the arithmetic

His constraint: a participant active under PoA for six months to a year reaches
the highest level.

The distilling-rate assumption is decision 2 above — 1 Quintessence per USD of
exchange fee, about 0.5 effective after the grade curve.

```
a modest single-bot participant
  8 fills a week at 300 USD notional        = 2,400 USD a week
  at the 0.60% entry taker fee              = 14.40 USD of fees a week
  at ~0.5 effective Quintessence per dollar = ~7.2 Quintessence a week
  six months                                = ~190 Quintessence
  one year                                  = ~375 Quintessence
```

L4 at 150 is reached inside six months by that participant, and inside a year by
someone at half that rate. Both ends of his window clear it.

The thresholds survive heavy play, which is the test that matters.

```
distilled                        ~31 Quintessence a month
Elite spend, 30 events a month    ~30 Quintessence gross
returned at 75% by performance    ~22.5 back for an average performer
net spend                         ~7.5 a month
balance growth                    ~23.5 a month
```

A participant playing thirty Elite Events a month still crosses 150 in under
seven months. The action budget in decision 9 is what makes that true: play costs
little enough that the franchise is never the thing at risk.

### Two gates, two purposes — his design, written out

His two rules together produce a separation worth stating as a design rather
than leaving a builder to infer it.

```
holdings in circulation   decide which issue levels a holder may vote on
event participation       decides whether a holder's vote is live at all
```

Stake in the outcome, and presence in the world. Neither gate is a weighting.

**Trading does not preserve a vote.** His words: *"Only PoA event anchored
transactions prevent dormancy. They must live and be active in the PoA world."* A
participant who certifies trades for a year, distils a large balance and never
enters an event qualifies on holdings for the highest tier and still holds no
live vote. The trading side funds the world and the playing side governs it.
That follows from his sentence, and it is intended rather than a problem — it is
recorded here because a builder who misses it will quietly let trading count.

### Dormancy — the franchise holds at the wallet's maximum and resynchronizes downward

His mechanism: *"Need a mechanism where voting rights are preserve at Max Quint
Wallet level for a given period that only diminishes if transactions stop
happening against the given address."*

And his clarification, which prevents a defect: *"The decay is only relative to
the gap that exists between the actual Quint balance of a given address and the
level required to participate in a given vote. It is a decay from a previous
point down to whatever the current balance is but no Quint moves as a result of
this mechanism. It is simply a slow resychronization between realities in order
to preserve authority for the most active participants."*

Spending costs no franchise. Dormancy does. A participant who spends heavily on
Elite Events keeps their standing because they keep acting in events; a holder
who sits still loses standing over time. Position decays, participation holds.

**Two quantities, separate rules.** Conflating them is the failure mode.

```
balance          real Quintessence, moved only by distilling, spending,
                 transfer, the platonic bleed and respawn
franchise level  the remembered maximum, converging toward balance on
                 dormancy, moving nothing
```

**No Quintessence moves during a resynchronization. This is his rule.** An
implementation that expressed the decay as a slash, a burn or a transfer would
break the three-bucket conservation law and contradict indestructibility in one
stroke.

**Two invariants, and both belong to the contracts work.** Each is a property
`forge` invariant testing can hold at every block rather than a claim anyone has
to trust.

```
wallets + held addresses + the platonic == total ever distilled <= 33,000,000
franchise level >= current balance, for every address, always
```

Decay runs the first of the pair down to the second and stops there. A franchise
level below the balance is a defect. Quintessence moving during a decay is a
worse one.

His phrase is the right description and belongs in the text. The mechanism is **a
slow resynchronization between realities**: the memory of what an address held
yields gradually to what it holds now, and event activity keeps the memory alive.

**The decay floor is the address's actual current balance. Closed, confirmed by
him.** Decaying to zero would strip a long-absent holder of any vote. Decaying to
their real holdings returns them to what they actually hold, which is what a
system with no memory would have given them in the first place.

### What counts as event anchored

**Recommended: acting inside an event.** One qualifying action taken within a PoA
event — an attack, a heal, a cast, a tactic, a movement — refreshes the address's
activity clock. Entry alone does not. Completion is not required.

Entry alone fails, because Elite Events carry lower entry fees by his own rule,
so a dormant holder would pay a small fee, idle through the event and keep the
franchise for nothing. That rewards the appearance of activity.

Completion fails in the other direction. An event that is cancelled, or that a
participant leaves for a reason outside their control, would cost them activity
they had genuinely spent.

**The cost of acting-inside:** the activity clock needs an event-scoped action
record per participant, which the action budget already has to produce in order
to charge per action. The record exists for billing; dormancy reads the same
record. The cost is one timestamp per address, written by the action path.

Receiving a redistribution also counts, because the 75% return at the end of an
Elite Event is paid only to participants, so receiving one is proof of having
been in one.

**A transfer does not qualify. Settled by his rule** — a transfer is not event
anchored, and no reading of his sentence makes it so. His transfer mechanism
already carries its own costs through the skill gate, the guild restriction, the
duration and the platonic bleed, and none of those is a reason to let it buy a
vote.

### The analogue family, and it is not a game

Standing contingent on continued participation rather than on a balance at a
moment is an established convention in proof-of-stake networks. Two published
cases exhibit it.

```
Ethereum         the inactivity leak. Ethereum's own documentation: "If the
                 consensus layer has gone more than four epochs without
                 finalizing, an emergency protocol called the 'inactivity
                 leak' is activated", and "the stake belonging to the
                 inactive validators gradually bleed away", creating "a
                 strong incentive for inactive validators to reactivate as
                 soon as possible"
Cosmos SDK       the x/slashing module. SignedBlocksWindow and
                 MinSignedPerWindow define a rolling uptime requirement;
                 a validator missing more than the allowance is jailed for
                 DowntimeJailDuration and must unjail to return
```

The shared property is a rolling window, an erosion of standing for absence, and
a defined path back. PoA's version differs in one way that matters and is worth
naming: both of those cases move real value, through a leak or a slash. His does
not. The franchise level moves and the balance does not.

### The three numbers, and they are his

```
the hold period       how long the maximum stands before dormancy can begin
the inactivity window how long without an event-anchored action counts as dormant
the decay rate        how fast the franchise level converges on the balance
```

Suggested values, derived from his own six-month-to-a-year constraint and the
same distilling-rate assumption as the thresholds above.

```
hold period        90 days from the last event-anchored action
inactivity window  90 days, the same figure — the maximum stands for the window
                   and resynchronization begins the day after it lapses
decay rate         1/90th of the gap per day, so a full resynchronization
                   takes 90 days from the moment it begins
```

The arithmetic behind the figures:

```
a participant reaches L4 at 150 Quintessence in ~6 months (above)
90 + 90 = 180 days of total absence to resynchronize fully
that is the same 6 months it took to earn the level
```

Losing a level takes as long as earning it took. A participant who plays once a
quarter never resynchronizes at all. A participant gone half a year returns to
their real holdings, which is exactly where a memoryless system would have put
them.

### Sybil resistance, because equal votes makes it the attack

One vote each means the cheapest attack is many identities. The certification
socket is the defence: an identity's holding comes from Quintessence distilled by
certified trades, and a certified trade costs a real exchange fee. A second
identity at L4 costs another 150 Quintessence of distilling, which is another six
months of real fees, and it needs its own event-anchored activity to stay live.
Splitting a holding across ten identities buys ten L1 votes, not ten L4 votes,
because the threshold is per identity.

```
src/competition/bot_identity.py        252 lines, sign_trade and verify_trade
src/competition/merkle_log.py          251 lines, MerkleTradeLog.append refuses
                                       a wrong competition, a wrong bot and a
                                       bad signature
src/competition/challenge_protocol.py  229 lines
```

One correction found while counting those: this issue's body and several of its
comments state 285 lines for the identity module. Recounted on
`origin/current` today it holds 252. The other two figures stand. The body
belongs to another unit this session, so the number is corrected here rather
than there.

### The security path — and my research does not support the shape I was asked to test

I was asked whether a shorter delay with a higher quorum is the convention for a
security tier. **It is not.** The convention across comparable systems is a
privileged group with a fast path.

```
Arbitrum DAO      a Security Council; a 9-of-12 council action bypasses the
                  L2 timelock, the withdrawal delay and the L1 timelock
                  entirely, and can upgrade with no delay
Compound lineage  the Governor Bravo shape separates standard from emergency
                  proposals; emergency proposals bypass the timelock and
                  usually carry a shorter voting period, and a Guardian or
                  emergency multisig holds the exclusive right to create one
```

The honest report is that the industry answer is a trusted council, and his
principle forbids a unilateral key. The reconciliation that keeps both:

```
an elected halt council    3 of 5, elected by the same equal-vote franchise
it can do one thing        halt the affected mechanism
it can never              change a rule, move Quintessence, mint, or alter art
the halt expires           automatically after 7 days
renewal                    needs an L2 vote, never the same council again
the repair                 runs at L2 or L4 by CVSS severity, on the normal clock
```

A halt moves nothing and changes nothing, so it reverses nothing — the property
he objected to losing. The halt buys the time the normal route needs. An L4
repair still takes thirty days, and a live exploit stops on day one rather than
day thirty. The expiry is what stops a halt becoming the permanent freeze he
objected to: if the council vanishes, the system self-heals.

**The alternative is accepting that a live exploit runs for the full delay.**
That is the cost of having no fast path at all, and it belongs in the open rather
than hidden behind the design.

### The upgrade shape — migration by vote, not a proxy

**Decided: every deployed contract stays immutable. A change that cannot be made
by parameter is made by deploying a new contract and migrating holders to it, on
an L4 vote.**

```
a proxy            one address for ever, the logic replaceable. A passed L4
                   vote could replace every rule including the cap, which is
                   the reversibility he objected to. The EEA specification
                   states that a set of contracts following a proxy pattern
                   "cannot be considered immutable", that certification of a
                   proxy "does not apply to the internal logic" of the
                   execution contract, and that each new execution contract
                   needs its own certification
migration by vote  each deployment immutable and verifiable for ever. The cost
                   is that holders must act: anyone who does not migrate is
                   left on the old contract
```

The carry-across rule, because a migration is a supply event for a capped asset:

```
the new contract mints only against units locked in the old contract's
migration address, one for one
the new contract's cap is set to the old contract's total ever distilled at
the migration block, never to 33,000,000 afresh
the old migration address is a held address; the units in it are retired
```

The live total therefore never rises, and the law keeps three buckets.

```
wallets + held addresses + the platonic == total ever distilled <= 33,000,000
```

A governance contract holds no Quintessence, so it adds no fourth bucket.
Confirmed.

The vote source is the supported path rather than bespoke code. The governance
framework reads weight through an interface rather than off a balance, so an
equal-vote source with a tiered franchise and a dormancy clock can implement it.

```
OpenZeppelin version 5 governance documentation
  "GovernorVotes: Extracts voting weight from an IVotes contract"
  the Governor is therefore token-agnostic
```

### Every governance default, and what happens if it is wrong with nobody able to intervene

```
L4 threshold of 150 too high    the core franchise is too small; only an L4
                               vote can lower it, and the people it excludes
                               are the ones who would vote to. It locks.
L4 threshold too low           core rules change too easily; an L4 vote can
                               raise it, so this error is self-correcting.
                               Err low, not high.
quorum of 40% at L4            if turnout never reaches it, no core change
                               ever passes and the contracts are frozen as
                               deployed. An L3 vote cannot fix an L4 quorum.
                               The most dangerous default on the list.
approval of 67% at L4          a persistent 60/40 split deadlocks core
                               changes for ever. Survivable: the system keeps
                               running on the rules it has.
30-day L4 delay                a needed change takes a month. Survivable, and
                               the halt council covers the emergency case.
the dormancy rate and window   bounded, see below.
the event-anchored definition  a definition set too narrowly disenfranchises
                               ordinary players, and once they are
                               disenfranchised they cannot vote to widen it.
                               Acting-inside is the widest of the three
                               candidates for that reason.
the halt council's 7-day       if too short, a halt lapses before the repair
expiry                         vote completes and the exploit resumes. If too
                               long, a captured council freezes the mechanism
                               for a week. Seven days covers an L2 repair and
                               not an L4 one, which is why an L4 repair needs
                               a renewal vote.
migration rather than a proxy  a flaw in a deployed contract cannot be
                               patched, only migrated from, and holders who
                               do not migrate are stranded.
```

**The dormancy rate, corrected.** An earlier reading of this mechanism had a fast
decay rate disenfranchising ordinary players who could then never vote to widen
it. **With the floor at the address's actual balance, that no longer holds.** The
worst case is a holder falling to their real holdings, which is what a system
with no memory would have given them anyway. Nobody lands below their real
position. A wrong rate therefore costs patience, not franchise — and that is the
difference his floor ruling makes.

The two defaults that can still deadlock the system with no path out are the L4
threshold and the L4 quorum. Both belong at the low end of any range he is
comfortable with, because raising them later is always possible and lowering them
may not be.

### The standard to classify against

**EEA EthTrust Security Levels, with the SWC Registry as a cross-reference
only.** The registry states its own position: its content “has not been
thoroughly updated since 2020”, it is “known to be incomplete and may contain
errors as well as crucial omissions”, new entries are no longer added, and it
points readers to the EthTrust specification as the maintained guidance. All of
its weaknesses were folded into EthTrust version 1 in August 2022, and version 2
followed in December 2023.

EthTrust is also the right standard for this question, because it addresses admin
powers and upgradeability directly. It grades at three levels, `[S]`, `[M]` and
`[Q]`, with access control and upgrade patterns as explicit requirements, and it
treats a proxy set as not immutable.

SWC identifiers stay useful for cross-referencing a finding a reader already
knows by number. They are not the classification.

---

## The one thing still his

**Whether an outside firm reviews the contracts before mainnet.** It is a spend
and it stays his decision. My recommendation is stronger than it was this
morning, and for his own reason.

He wrote that PoA has to live past his hands once the first nodes connect on a
live net. Under the decisions above, a deployed contract is immutable, and a
correction needs a vote that takes thirty days and a quorum that may never
assemble. No owner can step in, and that is the point.

A review before deployment is therefore not a cost to weigh against a benefit.
It is the only opportunity to find a flaw while fixing one is still cheap. After
deployment the cheapest available repair is a migration that strands every holder
who does not act.

The tooling does not substitute for it. `forge` fuzzing and invariant testing can
hold the three-bucket conservation law and the franchise invariant at every
block, and that is worth doing for its own sake. Static and symbolic analysers
find known weakness classes. None of them finds a flaw in what a contract is
**for**, and “cannot have any gaps” is a bar about purpose as much as about code.

One prerequisite blocks all of it and is already recorded in this issue: no
toolchain resolves the OpenZeppelin imports, so the three contracts have never
been compiled, and every analyser worth running needs a successful compile first.

---

## What I could not research

**The manipulation protection on the Exchange Participation Layer beyond the
rotation.** It sits on his owed list and it was not in my fourteen. No published
source answers it, because it depends on what an exchange would agree to run.

**A live participant count per market.** Decisions 3 and 4 are sized against it
and it does not exist yet, because no participant has ever certified a trade. The
5% ceiling and the five-market window are chosen to produce stated properties and
should be re-derived from the first live season's distinct certified participants
per activation window.

**The CoinGecko public rate limit.** The coin-detail page states a 30-second
cache and no rate-limit figure. The limit belongs to the project-age unit, which
has to confirm it before a design depends on the endpoint.

---

## 16. The Exchange Participation Layer — exclusion only, and the hole that opens

This section answers the first entry under "What I could not research" above and
supersedes it. That entry stands as written, because it was true when written.

HIS RULE: *"The layer does not allow for direct rotation control. It only allows
market exclusion from the volume-based rotation list."*

An exchange may remove its own markets from the volume-based rotation list. It
cannot add a market, cannot choose which market rotates, and cannot time a
rotation. The power is subtractive and nothing else.

### Subtraction becomes selection, and the size of it is arithmetic

MINE. Decision 4 draws a fixed five markets from the top twenty eligible. With a
fixed draw and a finite pool, removing markets raises the odds on every market
left. An exchange wanting rewards on one book does not add it. It removes the
others.

Each row is the chance that any one surviving market is drawn in a window.

```
excluded   pool   drawn   chance per surviving market
   0        20      5                25.0%
   5        15      5                33.3%
   8        12      5                41.7%
  10        10      5                50.0%
  13         7      5                71.4%
  14         6      5                83.3%
  15         5      5               100.0%
  19         1      1               100.0%
```

Excluding fifteen of twenty makes the draw certain. Excluding nineteen makes one
named market certain.

Two properties break at once, not one. His rotation conceals which markets pay,
and that concealment is what defeats targeted farming. At a pool of five every
participant knows the answer, so the exclusion power destroys both the
concentration bound and the concealment in the same act.

### Three closures, and all three are needed

MINE.

**Scale the draw with the pool.** The draw becomes one quarter of the eligible
pool, rounded up, never fewer than one. That holds decision 4's ratio at every
pool size rather than only at twenty.

```
pool  20   drawn 5   chance 25.0%
pool  16   drawn 4   chance 25.0%
pool  13   drawn 4   chance 30.8%
pool  12   drawn 3   chance 25.0%
pool  10   drawn 3   chance 30.0%
pool   7   drawn 2   chance 28.6%
pool   5   drawn 2   chance 40.0%
pool   1   drawn 1   chance 100.0%
```

Scaling alone does not close the hole. At a pool of one the draw is still
certain, because a quarter of one rounds up to one.

**A minimum eligible pool of twelve.** Below twelve eligible markets the exchange
draws nothing at all that window. With scaling in place and a floor at twelve,
the worst chance any market can reach is 30.8%, at a pool of thirteen. Against
100% with no closure, that is the measured size of the repair.

A floor of twelve lets an exchange exclude at most eight of its twenty. That is
enough room to remove a market it has a real reason to remove, and not enough to
choose the winner.

The floor alone is also insufficient. With the draw fixed at five, a pool held at
exactly twelve gives 41.7% per market — a 1.67 times concentration gain over the
unexcluded 25%. Scaling is what removes that.

**An exclusion takes effect at a season boundary only.** Delay alone closes
nothing about concentration, because a permanent exclusion set concentrates just
as well as a timed one. It closes a different attack: an exclusion filed against
a live window, once the exchange can see how trading is going.

### The season boundary exists, and its shape suits this better than a calendar

MEASURED. A season is an integer counter, advanced by a call. No date, duration
or calendar field exists anywhere in the schedule module.

```
src/competition/season_schedule.py:17   GENESIS_SEASON = 1
src/competition/season_schedule.py      no date, duration, days, start, end or
                                        calendar field — 0 occurrences
contracts/CompetitionRegistry.sol:62    uint256 public currentSeason = 1;
contracts/CompetitionRegistry.sol:350   function advanceSeason() external onlyOwner
                                            currentSeason++;
```

The boundary is an event rather than a date, and the call that fires it is
privileged. Under section 15 that privilege becomes a vote. An exchange therefore
cannot predict when its own exclusion will take effect, which is a stronger
property than any fixed calendar would give.

### What exclusion costs the exchange, and why the brake is not enough

MINE. A market excluded from the rotation earns its traders no Quintessence, so
an exchange that excludes heavily makes itself less attractive to trade on. That
is a real cost and it is the natural brake.

It does not suffice, for two reasons.

The exchange keeps its fee income either way. Quintessence is distilled from fees
the exchange has already collected, so a trade on an excluded market still pays
the venue its fee and simply awards the trader nothing. Exclusion removes a
participant's reward, never the exchange's revenue.

And the brake can invert. An exchange that concentrates the rotation on one book
funnels every PoA trader into that book, which deepens it. The self-harm
argument assumes the exchange loses volume. Concentration is how it would gain
volume.

A brake that the actor can turn into an incentive is not a brake. The three
closures above are structural and do not depend on the exchange's preferences.

**Source:** HIS RULE for exclusion-only. The arithmetic is MINE and derived from
decision 4's own numbers. The three closures are CHOSEN: scaling to hold the 4:1
ratio at every pool size, the floor of twelve to cap the worst per-market chance
at 30.8%, and the season boundary to stop an exclusion being timed against a live
window.

**Checked against:** organically competitive at every level; reward play not
position; Quintessence only from PoA activity. An exchange steering where
Quintessence lands is position, and the same shape as a participant steering it.

**Whale test, one line each.** Scaling: a large participant gains nothing,
because the draw shrinks with the pool rather than the odds rising. The floor: a
large participant gains nothing, and an exchange cannot hand one a certain
market. The season boundary: a large participant gains nothing, because the
window an exclusion lands in is not predictable by anyone.

---

## What an outside review reviews, given that changes are voted

He asked the question and it deserves a plain answer rather than a decision.

A vote decides whether to **adopt** a change. A review establishes whether the
code **does what it claims**. Those are different questions and neither answers
the other. Holders voting on a proposal are not reading Solidity, and approving a
proposal establishes nothing about whether it carries a reentrancy hole.

The specific case is narrower than the general one, and it is the reason the
recommendation is about one deployment rather than all of them.

**The genesis contracts exist before anyone can vote at all.** No holders exist
until the first nodes connect, so nobody can govern the first deployment into
existence. Every later change passes through his vote. The first one cannot.
Under immutability, a flaw there is permanent and unreachable by the governance
he has designed.

**The recommendation therefore applies to the genesis deployment specifically.**
Later migrations can have review written into the proposal process by the holders
themselves — a rule that an L4 proposal touching the contract set carries a
review before it reaches a vote. That part he can delegate to the system. The
first one he cannot, because the system does not exist yet to delegate it to.

The decision stays his.
