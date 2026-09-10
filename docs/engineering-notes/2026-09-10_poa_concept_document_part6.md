# Concept document — part 6 of 7

This part carries the long form of the rules the body states, and the nine choices
with every option and what it costs.

The body gives each rule and the reason for it. This part gives the rest: the
published source behind every borrowed number, the arithmetic that sized every
chosen one, the measured code, and one line per decision on what a participant
with a hundred times another's Quintessence gains from it.

| What is here | Body section it belongs to |
| ------------ | -------------------------- |
| The tab, the classes and the skill curve, in full | 2, 3 |
| The modes, the Elite variant and the turn, in full | 6 |
| The Quintessence economy, in full | 13 |
| Governance, in full | 14 |
| The Exchange Participation Layer and the persistent world, in full | 15, 16 |
| The nine choices, with every option and its cost | the choices |

Two marks separate the kinds of number inside a DECIDED rule.

```
TAKEN FROM A SOURCE   a published document states it; the document is named
CHOSEN                no source states it; the property it produces is named
```

---

## 2 and 3 — the tab and the classes, in full

The body carries each rule in short form. These are the same passages at full length.

### The Quint Wallet sits over the party window

**DECIDED**, two parts. A Quintessence balance readout lives in the party
window's header and stays visible at all times. The full wallet opens as a panel
over the party window, and over nothing else.

Not a fourth zone. His layout fixes a ratio — the enemy screen is square, and the
player window is larger than it because it carries trading action translated to
RPG action. A fourth zone takes space from one of the three and breaks a
constraint he stated.

Not a tab mode. Elite Events spend Quintessence per action, so a participant
needs the balance while the fight is live. A mode that replaces the tab hides the
fight at the moment the balance matters most.

The party window is the right host for three reasons drawn from his own spec. It
already paginates at forty a page, so it already owns a header with page
controls, and a panel is one more page class in a zone that already switches. Its
content is a list, and a wallet holding Quintessence, trophies and loot is a
list. And it is the only zone with no live animation to occlude.

Overlaying an inventory on the lower band while the action view stays live is a
convention many group RPG interfaces share. Bag and character panels that open
over the lower screen edge rather than replacing the scene appear in World of
Warcraft, Diablo and Final Fantasy XIV alike. The shared property is that the
fight never leaves view.

### Actions play back theatrically as blocks fill

**HIS.** *"Blockchain syncs actions in theatric playback blocks within the PoA
tab as blocks are filled."*

A chain cannot render a live animation, and sixty players acting inside one
minute cannot be drawn as it happens. Committing actions and playing back a
filled block separates the pace of the chain from the pace of the spectacle. The
enemy screen and the player window can then be as dramatic as the art allows
without either waiting on the other.

It also means a participant acts on the previous block's outcome rather than the
current one. That is the position a trader is in, so the constraint reads as
theme rather than as latency.

**PROPOSED.** The design owes one answer here: what the player window shows while
a block fills. If playback trails the live candle, the screen shows the previous
turn while the current one is being decided.

### Where the persistent world is seen is open

**HIS** for the constraint, and the answer is his.

The three zones are all event-shaped. The Quint Wallet was the first thing that
fitted none of them, and a panel answered it. A persistent world of towns, cities
and life-skilling is much larger than a panel, and it needs somewhere to be seen.

The constraint he set stands: one PoA tab, and only one. Section 10 carries the
world itself.

### Every skill levels through use

**HIS.**

> "All skills have levels that grow through use. Skills should be intelligently
> capped but be extremely difficult to top out while also growing slowly. I am
> thinking about growth curves similar to Eve Online."

This reaches past the class array. A skill is a system, not a property of a
class, and the transfer skill in section 7 is one member of it.

**DECIDED.** Every skill has ten levels. Level one costs one unit of progress,
and each level costs 2.5 times the one below. A use contributes its own quality,
in the range nought to one, rather than a flat one. Effect rises by 0.1 a level,
so a maxed skill is twice an untrained one.

```
level   cost of that level   cumulative
 1             1.0                1.0
 2             2.5                3.5
 5            39.1               64.2
 8           610.4            1,016.0
10         3,814.7            6,356.7
```

Level ten alone is 60% of the lifetime cost, and topping out takes about 6,357
quality-weighted uses.

A compounding curve whose last level costs many times the first is what
long-horizon progression systems share, and three of them state it in published
numbers. Eve Online's five levels at rank one cost 250 to 256,000 cumulative
skill points, a constant step near 5.66, so the last level is 82% of the whole.
RuneScape's requirement doubles about every seven levels, and level 92 is about
half of level 99's total. EverQuest hard-codes a multiplier of 3.1 above level
61. The convention is a constant multiplier with the tail holding most of the
total.

**Eve trains on elapsed time and he has said through use.** The shape therefore
transfers and the mechanism does not. The unit of progress here is a counted use,
never a duration, because a clock-based curve would contradict his own sentence.

Quality-weighting the use stops repetition from being the strategy. His class
experience already carries bonuses for efficacy and accuracy, so a skill use
carrying its own quality is consistent rather than new, and a thousand sloppy
uses are worth less than two hundred good ones.

The effect spread is deliberately small against the cost. A maxed skill at twice
an untrained one, across a ladder costing 6,357 uses, keeps breadth viable while
satisfying his rule that focus yields more power. Twice in one skill beats 1.1
times in ten.

---

## 6 — the modes, the Elite variant and the turn, in full

### A turn is a candle

**HIS.**

> "PoA - Game turns are aligned to 1m candles for Elite Events and 5m candles for
> non-Elite Events and players must act within these windows or lose their actions
> for a given turn. New players can enter midturn but do not get a fresh turn
> timer because the market moves nonstop in real time. Candles are windows of
> opportunity. Take it lose it. Helps anchor PoA in the trading world as well."

```
Elite events      one turn per 1m candle
non-Elite events  one turn per 5m candle
missed window     the actions for that turn are lost
joining midturn   no fresh timer; the entrant takes what is left of the candle
```

The clock is the market's, not the game's. Turns are therefore globally
synchronised: every participant in an event shares one boundary, and no
per-player timer exists to drift or to be gamed. A turn cannot be paused,
extended or negotiated, because the candle closes whether or not anyone acted.

Elite runs five times faster than non-Elite, which sharpens the other three Elite
differences rather than sitting beside them.

**This settles two numbers elsewhere in the design.** The cooldown after a
Quintessence award is measured in candles and never fewer than three, so it is
three minutes in an Elite event and fifteen in a non-Elite one. Nobody should
later convert it into a fixed number of seconds. And an expensive multi-turn cast
now has a concrete meaning: it occupies more than one candle.

**PROPOSED.** The design owes two answers here. Which market's candles an event
runs on — the market the event is anchored to, or one reference market for every
event. And whether a guild can negotiate an expensive cast inside sixty seconds.
An Elite turn gives them one minute, which may be deliberate pressure and may
make the negotiation impossible. That one is his, and it is worth taking
knowingly.

### Who may enter an Elite Event

**DECIDED.** Entry opens to a participant in the top 20% by lifetime Quintessence
distilled, measured against every participant who certified at least one graded
trade in the preceding 90 days.

Three parts, each with a reason.

**Lifetime distilled, never the current balance.** Elite Events spend
Quintessence per action, so a balance test would remove Elite eligibility from
the participant who plays Elite Events. Lifetime distilled only rises, comes only
from certified trades, and spending does not touch it.

**Active in 90 days, not all holders.** Dormant accounts never grow their figure,
so as time passes they sink to the bottom of the distribution and drag the
threshold down. The gate would loosen every year with nobody deciding to loosen
it. The event's own entrants cannot be the population either, because the
population would then be defined by who already got in.

**Twenty per cent, not one.** Elite Events carry lower entry fees and per-action
spending, so they exist to be played rather than to be a closed room.

**MEASURED.** The percentile band comes from the tree's own rank ladder rather
than from nothing.

`src/competition/season_schedule.py` — `RarityTier.rank_pct_max`

```python
    Harvest 0.50   Bear Slayer 0.25   Gold Fold 0.10
    Grand Accumulator 0.01   Ekthelius 0.001
```

Twenty per cent is the band between broad and rare in a vocabulary the code
already uses.

### The Action Budget Curve — five bands, a hundred to one

**DECIDED.** Five bands, priced from 0.001 to 0.100 Quintessence.

```
band   cost     what sits in it
x1     0.001    move, switch weapon, take an item from a bag
x3     0.003    a basic attack, a basic heal
x10    0.010    a class ability on a cooldown
x30    0.030    a group-wide ability, a threat move across the field
x100   0.100    a multi-turn spell, and the decisive tactics beside it
```

Five bands, because the action economies of published tabletop systems settle at
three to five distinct action classes for the same reason: a participant has to
hold the whole list in their head during a turn. Pathfinder Second Edition uses
three actions plus a reaction. The earlier Pathfinder and Dungeons and Dragons
shape is a move plus a standard plus a full-round action spanning both. The shared
property is a small closed set with a clear cheapest and a clear dearest, and
multi-turn casting as the top cost.

The ratio is a hundred to one and no larger, because the answer must sometimes be
yes. At that ratio a participant who moves two hundred times in an event spends
0.2 Quintessence, and one decisive cast costs 0.1 — worth arguing about, and not
ruinous. At a thousand to one a single cast costs five events of movement, so the
answer is always no, and a negotiation with a foregone conclusion is not a
negotiation.

Each band is roughly three times the one below it, which is the same geometric
spacing the trophy caps and the skill curve use. The design carries one spacing
convention rather than three.

The per-event arithmetic is the check that matters.

```
200 x1 + 60 x3 + 20 x10 + 5 x30 + 2 x100
  = 0.200 + 0.180 + 0.200 + 0.150 + 0.200
  = 0.93 Quintessence for one full Elite Event
```

Against the flat distil rate, a participant paying 30 to 60 USD of exchange fees
in a week funds thirty to sixty Elite Events, and 75% of the spend returns by
performance. That is affordable, which is his rule, and it is the arithmetic that
holds the rest of the economy together.

### Who pays a persuaded cast

**DECIDED.** The participant whose character performs the action pays for it. A
guild officer may commit treasury funds to cover it, and the actor must accept
that commitment before the action runs. The requester never pays.

His own sentence decides the default. He writes that higher-ranking members must
navigate politics and relationship to convince fellow members **to use** the
expensive skill. The member uses it. A cast the user does not pay for needs no
convincing, so a requester-pays rule would delete the mechanism he described in
the sentence that described it.

The treasury underwrite keeps an expensive action reachable without removing the
negotiation. It takes two acts by two people — an officer commits, the actor
accepts — so the conversation still happens, and it gains a second subject: whose
money.

A resource one member spends while the whole group benefits is a shape many group
RPG systems share. A healer's mana, a tank's cooldown and a support player's
consumables are all paid by one player and enjoyed by the party, and in every one
the spender decides.

### Redistribution is by performance, never by spend

**HIS.** Seventy-five per cent of total spent Quintessence returns to
participants at the end of an Elite Event.

**DECIDED.** The pot divides on a normalised performance score. It never divides
on Quintessence spent. The remainder rests on-chain as the reserve that keeps
events fundable once the cap is reached.

Dividing by spend would pay the largest holder the largest return and make
spending its own reward. Dividing by performance makes a large spender fund the
better players, which is the property the whole anti-whale design wants.

---

## 13. The Quintessence economy — in full

Every number in this section was open this morning. All of them are now set. The
long evidence for each one — the published source, the arithmetic and the
anti-whale test — sits in the three decision comments of 2026-09-09 and
2026-09-10, which stay below as the provenance.

### The distil rate — one Quintessence for one dollar of exchange fee

**DECIDED.** A certified trade distils 1 Quintessence for each 1 USD of exchange
fee it pays. The grade curve and the market allotment bound it. No second
constant scales it.

The rate is flat because five bounds already stand between a fill and an award.

```
the market allotment   sized to that market's volume at activation
one allotment          one per participant per activation period
the share ceiling      at most 5% of that market's pool
the candle cooldown    never fewer than three candles
the grade curve        the award is multiplied by the trade grade, 0.0 to 1.0
```

A sixth constant on top of five bounds would have no source and nothing to hold
it still. The effective rate is far below one to one, because a wash trade
scores near the bottom of the grade range.

**MEASURED.** The grade bands are declared in the grader.

`src/trading/trade_grader.py` — `_letter_from_numeric`

```python
    A+  >= 0.93    A  >= 0.85    B  >= 0.70
    C   >= 0.55    D  >= 0.40    F  below
```

At a grade-neutral mean near 0.5, the cap of 33,000,000 mints out against
roughly 66,000,000 USD of aggregate certified fees. That is the stated
consequence of the flat rate, and it is checkable.

**MEASURED.** The platform cannot answer how much fee a bot has ever paid, so
the rate needs a lifetime total built. Three facts say why.

`src/trading/container/config.py` and `src/trading/scrumming/reconciliation.py`
— the only fee total is re-derived from a bounded window, so it falls

```python
    fees_paid_exchange: float = 0.0
    YTD_TRADE_PAGE_LIMIT = 500
    YTD_TRADE_MAX_PAGES = 40
```

`src/trading/scrumming/execution.py` — `_record_venue_fee` discards a buy, so
half of every cycle records no fee

```python
        _side_txt = str(getattr(_side, "value", _side) or "").lower()
        if _side_txt != "sell":
            self._last_sell_venue_fee = None
            return
```

The monotonic pattern already exists beside it. `sync_ytd_trade_count` pages the
venue, de-duplicates by trade id and keeps the larger of the persisted and the
counted value. A lifetime certified-fee total follows that shape, in the same
walk, with the same guard.

### Eligibility — both conditions are required

**DECIDED.** A market rewards Quintessence only while it sits inside the top 20
by volume on that exchange **and** its project is at least six months old.

His sentence reads in strict grammar as either-sufficient. That reading admits a
market that is top 20 and three weeks old, and also a market four years old with
almost no depth. An obscure pump has two halves — thin trading and recency — and
either-sufficient lets one half through in each direction.

Both-required is also the safe direction. It can refuse a market that should
have paid. It can never pay a market that should have been refused. That matches
the ruling already recorded here for a missing age: refuse, because refusing
cannot be gamed by withholding data.

```
DECIDED — the eligibility test
top 20 by volume on that exchange        AND
project age at least six months          AND
the market is inside the live rotation
```

### Five markets a window, and a participant may draw from several

**DECIDED.** A rotation activates five markets per exchange per window. One
participant may earn from every activated market they trade.

Five of twenty sets the blanket-farming cost at four to one. A participant who
cannot see the rotation must trade all twenty eligible markets to cover the five
that pay. Three of twenty would raise the ratio to 6.7 and leave only sixty
participant-slots per window at the share ceiling; five gives one hundred.

Multi-market drawing is allowed because refusing it would punish the platform's
own shape. Bots and their wires, ledgers and tranches all load from one fleet
state, and a fleet runs many markets at once. Running many markets is capital at
risk and work done, so it is play rather than position. The share ceiling is per
market and composes, so allowing it costs nothing in concentration.

### The share ceiling — five per cent

**DECIDED.** One participant takes at most 5% of a market's Quintessence pool in
one activation period.

Five per cent means at least twenty distinct participants must earn from a
market before its allotment can be exhausted. That keeps his third end condition
reachable: an activation ends on expiry, on volume, or on exhaustion, and a
ceiling set too low makes exhaustion unreachable. At 25% four participants empty
a market. At 50%, two.

The ceiling composes across markets. A participant drawing from five activated
markets takes at most 5% of each pool, which is 5% of their sum. One number
therefore bounds one market and the whole window, and no second global cap is
needed.

The number should be re-derived once the distinct certified participants per
activation window can be counted. No participant has certified a trade yet.

### Quintessence is transferable, under four terms

**HIS, and it closes the highest-value open question in this design.**

> "Quint is transferable between players via a specific skill isolated to common
> Guild members, takes significant time to complete based on amount and skill
> level, and has a negative effect of 'bleeding' quint back into the 'platonic'
> where it can be respawned and redistributed to other PoA participants."

```
gated by a skill    one specific skill, never a wallet function
guild members only  common members of the same guild
slow                duration scales with the amount and the skill level
lossy               part bleeds into the pleroma
```

Each term closes a route a whale would use. A skill gate means the buyer must
have invested in the skill. Guild membership means a social relationship rather
than a market. Duration scaling with the amount means nobody arms themselves
just before an event. The bleed means every transfer leaks value out of the two
parties and back to everyone else.

Concentration is therefore taxed at the moment it is attempted, and the tax is
paid to the other participants.

### The bleed, the duration, and the respawn

**DECIDED**, three parts.

```
bleed      8% of the amount at skill level 1, falling linearly to 4% at level 10
duration   hours = amount / (10 x skill level), minimum one hour, and one
           transfer in flight per participant
respawn    bled units join the next activation's market allotments and are
           awarded by the same certified-trade mechanism, curved by grade
```

A single-digit percentage sink on a transfer, reducible by a skill, is the
convention across player-driven virtual economies. Eve Online charges sales tax
from 7.5% reducible to 3.37% through a skill; World of Warcraft takes a flat 5%
of an auction sale. Eight falling to four sits inside that band at both ends,
halves across the ladder, and never reaches zero, so concentration is always
taxed.

The bleed is self-taxing. The only way to reduce it is to raise the transfer
skill, the skill grows through use, and every use is a transfer that bleeds.
Climbing the ladder is paid for in bled Quintessence, and nobody can buy a
cheaper bleed.

The single-slot rule closes the split attack. Without it a participant splits a
large transfer into many small parallel ones and the duration term does nothing.
With it, splitting changes nothing, because the slot serialises them.

```
1,000 Quintessence at skill level 1     100 hours, over four days
1,000 Quintessence at skill level 10     10 hours
```

The sender is not excluded from the respawn. Excluding them would be a special
case that invites a second identity, and their recovery is already bounded twice
— by the share ceiling and by their own trade grades.

### The conservation law has three buckets

**DECIDED.** The pleroma is a third place Quintessence can be, so the invariant
a contract audit holds gains a term.

```
wallets + held addresses + the pleroma == total ever distilled <= 33,000,000
```

Still exact, still checkable at every block, and now complete. A verifier that
omits the pleroma reports a shortfall that is not a defect.

A bleed despawns transferable units and reduces no supply. The word is already
this project's own: despawn removes, beside merge and clear, and it does not
delist.

### The trophy tier caps, and where they must live

**DECIDED.** Gold Fold 100,000 ever. Bear Slayer 10,000 ever. Both enforced in
the contract that mints the trophy.

**MEASURED, and this corrects the premise the owed list carried.** Bear Slayer is
not a missing number. The Python already declares it, and the ledger already
enforces it.

`src/competition/season_schedule.py` — `RARITY_TIERS`, every tier declares
`max_ever`

```python
    Harvest            max_ever=None     base_value=    10
    Gold Fold          max_ever=None     base_value=    50
    Bear Slayer        max_ever=10_000   base_value=   100
    Grand Accumulator  max_ever=1_000    base_value=   500
    Ekthelius          max_ever=21       base_value=10_000
```

`src/competition/token_ledger.py` — `TokenLedger.award` refuses a mint past any
declared cap, counted from an in-process list

```python
        if tier.max_ever is not None:
            tier_minted = sum(1 for e in self._events if e.tier_name == tier.name)
            if tier_minted >= tier.max_ever:
                raise OverflowError(...)
```

Python caps three tiers, not two. The two-tier reading is true of the Solidity
and false of the Python.

`contracts/CompetitionRegistry.sol` — the Solidity declares exactly two

```solidity
    uint256 public constant MAX_EKTHELIUS         = 21;
    uint256 public constant MAX_GRAND_ACCUMULATOR = 1_000;
```

Gold Fold is the one genuinely missing number, and the tree's own ladder sets it.
The declared caps step by a factor near ten — 21, then 1,000, then 10,000 — so
the next step is 100,000, and that leaves Harvest as the only uncapped tier.
That is what he asked for: caps on every tier except the lowest.

**MEASURED.** The two existing caps sit in the wrong contract. The registry
holds them, and the trophy contract lets the owner mint around them.

`contracts/AcervatorTrophy.sol` and `contracts/ACRV.sol` — the trophy gate
accepts the owner, the token gate does not

```solidity
    require(msg.sender == registry || msg.sender == owner(), ...);   // trophy
    require(msg.sender == registry, "ACRV: caller is not the registry");
```

A cap enforced in a different contract from the one that mints is not a cap on
the mint. Both new caps therefore go into the trophy contract as constants
beside a per-tier counter, and the owner bypass comes out.

### A guild holds a spending treasury

**DECIDED.** A guild holds a Quintessence treasury. It can be filled two ways
and spent one way.

```
filled by   the transfer skill, from a member, paying the bleed
filled by   the guild's own event awards
spent on    action costs for guild members, inside an event
never       paid out to a member's personal wallet
```

A guild is already an account-holding entity in his design, because guild
membership locks and stakes PoA tokens by rank. A Quintessence treasury applies
the same shape to the second asset.

The treasury exists because his action-budget ruling needs a third party. His
words name the politics as the point — a higher-ranking member persuading a
fellow member to use an expensive skill. With no treasury the negotiation is
bilateral. A treasury is the thing a guild can argue about.

Two guards keep it from becoming a concentration vehicle. Every unit entering a
treasury pays the transfer bleed, and no path runs from the treasury back to a
personal wallet. A treasury is a held address, so the conservation law keeps
three buckets and gains no fourth.

### Loot — five rarity tiers from the twelve gates

**DECIDED.** Five tiers, named for five of the twelve gates of the Great Work,
in the order George Ripley's *The Compound of Alchemy* gives them.

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
variant: rarity and drop rate both rise.

**MEASURED.** Every candidate name was counted across the tree before it was
chosen. Four were rejected on collision.

```
CALCINATION   0 files      SEPARATION     5 files   <- rejected
PUTREFACTION  0 files      CONJUNCTION    3 files   <- rejected
SUBLIMATION   0 files      MULTIPLICATION 2 files   <- rejected
FERMENTATION  0 files      PROJECTION     2 files   <- rejected
EXALTATION    0 files
```

`separation` is already a quantity inside the Vortex indicator and `conjunction`
already means a boolean AND in the engine. Distillation was rejected for a
different reason: a bot already distils Quintessence, so the verb is taken.

The five chosen names collide with nothing else either. They are not the four
colour stages on the trophy faces, not the seven planetary class names, and not
Gold Fold.

### Loot takes its own contract

**DECIDED.** Loot gets its own ERC-1155 contract. The metadata helpers come out
of the trophy contract into a library both use.

**MEASURED.** Sharing fails for three reasons, each read off the file.

`contracts/AcervatorTrophy.sol` — the mint signature and the metadata struct are
competition-shaped, and a deployed struct cannot gain a field

```solidity
    mint(recipient, tier, tierEmoji, season, competitionId,
         rank, fieldSize, advantageBps, marketRegime, merkleRoot)
```

One image per tier is structural: the mint refuses a tier whose art is not
uploaded, and the file states that trophies of one tier are visually identical.
Generative loot is the opposite case. And the owner bypass above would extend to
loot.

Extending the trophy contract costs the same deployment as writing a new one,
because Solidity cannot add storage to a deployed contract. The only saving from
inheritance is code that belongs in a library anyway.

ERC-1155 rather than ERC-721 because a common drop is fungible with itself.
EIP-1155 states the case: one contract may hold fungible, non-fungible and
semi-fungible tokens, each id carrying its own metadata and supply, with batch
transfer. An ERC-721 mints a distinct id per copy, which is the expensive shape
for the tier that drops 55 to 60 per cent of the time.

**MEASURED, one correction to the premise.** The trophy art is not a constant
set at deployment. It is a mutable mapping the owner can rewrite at any time, so
the art of an awarded trophy can change after the award.

`contracts/AcervatorTrophy.sol` — `setTierSvg` writes `_tierSvgB64`

```solidity
    mapping(string => string) private _tierSvgB64;
    function setTierSvg(string calldata tier, string calldata svgBase64)
```

That is one more privileged function for the governance section to remove.

---

The body carries section 14 in short form. This is the whole of it.

## 14. Governance — in full

**HIS, two rulings that set the whole shape.**

> "No, vote efficacy is not weighted by Quint amount held."

> "PoA should be a self-certifying, socio-economic organic system that lives
> after my hands after the first nodes connect on a live net."

A holding decides which issue levels a holder may vote on. It never decides how
much a vote weighs. Every vote counts the same.

### The admin surface today

**MEASURED.** Fourteen privileged functions stand across the three contracts,
and `adjudicate` alone lets the owner decide every award.

```
ACRV.sol                 Ownable, Pausable; pause and unpause are onlyOwner,
                         and the token's update hook carries whenNotPaused
AcervatorTrophy.sol      Ownable; setTierSvg rewrites any tier's art, and the
                         registry gate also accepts the owner, so the owner can
                         mint any tier directly
CompetitionRegistry.sol  Ownable, ReentrancyGuard; setPriceFeed,
                         openCompetition, activateCompetition,
                         closeForSubmission, adjudicate, advanceSeason and
                         cancelCompetition are all onlyOwner
```

Three of the library's published behaviours decide what those functions reach.
The OpenZeppelin version 5 documentation states each one. None of these names
belongs to this tree, because the library is an unresolved import here.

```
ERC20 update hook   minting, burning and transferring all route through the
                    one hook
Ownable transfer    immediate, with no acceptance step; the two-step variant
                    is a separate contract
Ownable renounce    "Leaves the contract without owner. It will not be
                    possible to call onlyOwner functions."
```

One pause therefore freezes every holder and the award path together. The key
moves in one call to an address that never confirms it can receive it. And
renouncing while paused makes the freeze permanent.

None of those powers serves a mechanism in his design. Distribution and reclaim
are protocol mechanics, so removing the powers costs him nothing he asked for.

### The four levels

**DECIDED.** A holding buys access to a level, never weight inside it. Three
published documents set the ladder's shape: Semantic Versioning sorts a change
by what it breaks, EIP-1 sorts a proposal by how much of the system it reaches,
and BIP-2 raises the acceptance bar with the reach of the change rather than the
weight of a voter.

```
level             what sits at it                          holding  quorum  approval  delay
L1 INFORMATIONAL  a manual page, a figure that binds           1 Q     10%   simple    none
                  nothing
L2 PATCH          a backward-compatible fix that changes      25 Q     20%   simple    2 days
                  no rule a holder relies on
L3 INTERFACE      a backward-compatible addition: a new       75 Q     30%   60%       7 days
                  event type, a new loot tier, a market
                  on the eligible list
L4 CORE           any change to a rule a holder relies       150 Q     40%   67%      30 days
                  on: the cap, the distil rate, the
                  bleed, the share ceiling, the
                  redistribution basis, the contract set
```

Quorum is a fraction of eligible voters at that level, never of supply, because
every vote counts the same.

Security is a severity rather than a level. CVSS version 4.0 sets the scale, and
a Low or Medium finding repairs at L2 while a High or Critical one usually
changes a rule a holder relies on, so its repair runs at L4. A fifth level for
security would overlap the four and leave the classification ambiguous.

### The thresholds, and his six-month test

**DECIDED.** His constraint is that a participant active under PoA for six
months to a year reaches the highest level. At the flat distil rate, a modest
single-bot participant clears it.

```
8 fills a week at 300 USD notional        = 2,400 USD a week
at the 0.60% entry taker fee              =  14.40 USD of fees a week
at ~0.5 effective Quintessence per dollar =   ~7.2 Quintessence a week
six months                                =  ~190 Quintessence
one year                                  =  ~375 Quintessence
```

L4 at 150 arrives inside six months for that participant, and inside a year for
someone at half the rate. Both ends of his window clear it.

The thresholds also survive heavy play, which is the test that matters. A
participant playing thirty Elite Events a month nets about 23.5 Quintessence a
month of balance growth after the 75% return, and still crosses 150 in under
seven months. The action budget is what makes that true: play costs little
enough that the franchise is never the thing at risk.

### Two gates, two purposes

**HIS.** Two rules of his produce a separation worth stating rather than leaving
a builder to infer it.

```
holdings in circulation   decide which issue levels a holder may vote on
event participation       decides whether a holder's vote is live at all
```

> "Only PoA event anchored transactions prevent dormancy. They must live and be
> active in the PoA world."

Trading does not preserve a vote. A participant who certifies trades for a year,
distils a large balance and never enters an event qualifies on holdings and
holds no live vote. The trading side funds the world and the playing side
governs it. That follows from his sentence, and a builder who misses it will
quietly let trading count.

### Dormancy resynchronizes the franchise downward

**HIS**, mechanism and clarification both.

> "Need a mechanism where voting rights are preserve at Max Quint Wallet level
> for a given period that only diminishes if transactions stop happening against
> the given address."

> "The decay is only relative to the gap that exists between the actual Quint
> balance of a given address and the level required to participate in a given
> vote. It is a decay from a previous point down to whatever the current balance
> is but no Quint moves as a result of this mechanism. It is simply a slow
> resychronization between realities in order to preserve authority for the most
> active participants."

Spending costs no franchise. Dormancy does. Two quantities carry separate rules,
and conflating them is the failure mode.

```
balance          real Quintessence, moved by distilling, spending, transfer,
                 the pleroma bleed and respawn
franchise level  the remembered maximum, converging toward balance on
                 dormancy, moving nothing
```

**No Quintessence moves during a resynchronization, and that is his rule.** An
implementation that expressed the decay as a slash, a burn or a transfer would
break the three-bucket conservation law and contradict indestructibility in one
stroke.

Two invariants belong to the contracts work, and `forge` invariant testing can
hold each at every block.

```
wallets + held addresses + the pleroma == total ever distilled <= 33,000,000
franchise level >= current balance, for every address, always
```

**The decay floor is the address's actual current balance, and he confirmed it.**
Decaying to zero would strip a long-absent holder of any vote. Decaying to their
real holdings returns them to what a system with no memory would have given them.

**DECIDED**, three numbers, derived from his own six-month-to-a-year constraint.

```
hold period        90 days from the last event-anchored action
inactivity window  90 days; the maximum stands for the window, and
                   resynchronization begins the day after it lapses
decay rate         one ninetieth of the gap a day, so a full
                   resynchronization takes 90 days once it begins
```

Losing a level therefore takes as long as earning it took: 180 days of total
absence against the six months that earned L4. A participant who plays once a
quarter never resynchronizes at all.

### What counts as event anchored

**DECIDED: acting inside an event.** One qualifying action inside a PoA event —
an attack, a heal, a cast, a tactic, a movement — refreshes the address's
activity clock. Entry alone does not. Completion is not required.

Entry alone fails because Elite Events carry lower entry fees by his own rule, so
a dormant holder could pay a small fee, idle through the event and keep the
franchise for nothing. Completion fails in the other direction: a cancelled event
would cost a participant activity they genuinely spent.

The clock costs one timestamp per address. The action budget already has to
record an event-scoped action per participant in order to charge for it, so
dormancy reads a record that exists for billing.

Receiving a redistribution also counts, because the 75% return pays participants
only, so receiving one proves presence. A transfer does not qualify, because no
reading of his sentence makes a transfer event anchored.

Standing contingent on continued participation rather than on a balance at a
moment is an established convention in proof-of-stake networks. Ethereum's
inactivity leak bleeds an inactive validator's stake away until finality
returns; the Cosmos SDK slashing module jails a validator that misses more than
its allowance of a rolling window. PoA's version differs in one way worth
naming: both of those move real value, and his moves none.

### Sybil resistance, because equal votes makes it the attack

One vote each means the cheapest attack is many identities. The certification
socket is the defence. An identity's holding comes only from Quintessence
distilled by certified trades, and a certified trade costs a real exchange fee.
A second identity at L4 costs another 150 Quintessence of distilling, which is
another six months of real fees, and it needs its own event-anchored activity to
stay live. Splitting a holding across ten identities buys ten L1 votes, not ten
L4 votes, because the threshold is per identity.

**MEASURED**, today, on `origin/current`.

```
src/competition/bot_identity.py        252 lines; sign_trade and verify_trade
src/competition/merkle_log.py          251 lines; MerkleTradeLog.append refuses
                                       a wrong competition, a wrong bot and a
                                       bad signature
src/competition/challenge_protocol.py  229 lines
```

**A correction to a figure this page and several comments carried.** The identity
module holds 252 lines, not 285. The other two counts stand.

### The halt council

**DECIDED.** The convention across comparable systems is a privileged group with
a fast path: the Arbitrum DAO's Security Council bypasses every timelock on a 9
of 12 action, and the Governor Bravo lineage lets a guardian create an emergency
proposal that skips the timelock. His principle forbids a unilateral key, so the
reconciliation keeps both.

```
an elected halt council  3 of 5, elected by the same equal-vote franchise
it can do one thing      halt the affected mechanism
it can never             change a rule, move Quintessence, mint, or alter art
the halt expires         automatically after 7 days
renewal                  needs an L2 vote, never the same council again
the repair               runs at L2 or L4 by CVSS severity, on the normal clock
```

A halt moves nothing and changes nothing, so it reverses nothing — the property
he objected to losing. It buys the time the normal route needs. An L4 repair
still takes thirty days, and a live exploit stops on day one rather than day
thirty. The expiry stops a halt becoming a permanent freeze: if the council
vanishes, the system self-heals.

The alternative is accepting that a live exploit runs for the full delay. That
is the cost of having no fast path, and it belongs in the open.

### Migration, never a proxy

**DECIDED.** Every deployed contract stays immutable. A change that no parameter
can make is made by deploying a new contract and migrating holders to it, on an
L4 vote.

```
a proxy            one address for ever, the logic replaceable. A passed L4
                   vote could replace every rule including the cap, which is
                   the reversibility he objected to. The EEA specification
                   states that a set of contracts following a proxy pattern
                   "cannot be considered immutable"
migration by vote  each deployment immutable and verifiable for ever. The cost
                   is that holders must act; anyone who does not migrate is
                   left on the old contract
```

A migration is a supply event for a capped asset, so three carry-across rules
hold the cap.

```
the new contract mints only against units locked in the old contract's
  migration address, one for one
the new contract's cap is the old contract's total ever distilled at the
  migration block, never 33,000,000 afresh
the old migration address is a held address, and the units in it are retired
```

The live total therefore never rises, and the law keeps three buckets. A
governance contract holds no Quintessence, so it adds no fourth bucket.

The vote source is the supported path rather than bespoke code. None of the names in
the next block belongs to this tree; they are OpenZeppelin's, and the library is an
unresolved import here.

```
OpenZeppelin version 5 governance documentation
  "GovernorVotes: Extracts voting weight from an IVotes contract"
  the Governor is therefore token-agnostic, so an equal-vote source with a
  tiered franchise and a dormancy clock can implement it
```

### The two defaults that can deadlock the system

**DECIDED**, and worth stating because no owner can intervene under the rules
above.

```
L4 threshold of 150   set too high, the core franchise is too small, and only
                      an L4 vote can lower it. The people it excludes are the
                      ones who would vote to. It locks. Err low, not high.
quorum of 40% at L4   if turnout never reaches it, no core change ever passes
                      and the contracts freeze as deployed. An L3 vote cannot
                      fix an L4 quorum. The most dangerous default on the list.
```

Everything else on the list is survivable. A 67% approval can deadlock on a
persistent sixty-forty split, and the system keeps running on the rules it has.
A thirty-day delay costs a month, and the halt council covers the emergency. A
narrow event-anchored definition would disenfranchise ordinary players, which is
why acting-inside is the widest of the three candidates.

**The dormancy rate is no longer on that list.** An earlier reading had a fast
decay disenfranchising ordinary players who could then never vote to widen it.
His floor ruling removes it: nobody lands below their real holdings, so a wrong
rate costs patience rather than franchise.

### The standard to classify a finding against

**DECIDED: the EEA EthTrust Security Levels, with the SWC Registry as a
cross-reference only.** The registry states its own position — its content "has
not been thoroughly updated since 2020", it is "known to be incomplete", new
entries no longer arrive, and it points readers to EthTrust. EthTrust also
addresses admin powers and upgradeability directly, grades at three levels, and
treats a proxy set as not immutable.

---

## 15. The Exchange Participation Layer — in full

**HIS RULE.**

> "The layer does not allow for direct rotation control. It only allows market
> exclusion from the volume-based rotation list."

An exchange may remove its own markets from the volume-based rotation list. It
cannot add a market, cannot choose which market rotates, and cannot time a
rotation. The power subtracts and does nothing else.

### Subtraction becomes selection, and the size of it is arithmetic

**PROPOSED**, from his own numbers. The rotation draws a fixed five markets from
the top twenty eligible. With a fixed draw and a finite pool, removing markets
raises the odds on every market left. An exchange wanting rewards on one book
does not add it. It removes the others.

Each row gives the chance that any one surviving market is drawn in a window.

```
excluded   pool   drawn   chance per surviving market
   0        20      5                25.0%
   5        15      5                33.3%
   8        12      5                41.7%
  10        10      5                50.0%
  13         7      5                71.4%
  15         5      5               100.0%
  19         1      1               100.0%
```

Excluding fifteen of twenty makes the draw certain. Excluding nineteen makes one
named market certain.

Two properties break at once. His rotation conceals which markets pay, and that
concealment is what defeats targeted farming. At a pool of five every participant
knows the answer, so the exclusion power destroys the concentration bound and the
concealment in one act.

### Three closures, and all three are needed

**DECIDED.**

**Scale the draw with the pool.** The draw becomes one quarter of the eligible
pool, rounded up, never fewer than one. That holds the four-to-one ratio at every
pool size rather than only at twenty.

```
pool  20   drawn 5   chance 25.0%
pool  16   drawn 4   chance 25.0%
pool  13   drawn 4   chance 30.8%
pool  12   drawn 3   chance 25.0%
pool  10   drawn 3   chance 30.0%
pool   5   drawn 2   chance 40.0%
pool   1   drawn 1   chance 100.0%
```

Scaling alone does not close the hole, because at a pool of one the draw is still
certain.

**A minimum eligible pool of twelve.** Below twelve eligible markets the exchange
draws nothing that window. With scaling and a floor at twelve, the worst chance
any market can reach is 30.8%, at a pool of thirteen. Against 100% with no
closure, that is the measured size of the repair. A floor of twelve lets an
exchange exclude at most eight of its twenty — enough room to remove a market it
has a real reason to remove, and not enough to choose the winner.

The floor alone is also insufficient. With the draw fixed at five, a pool held at
exactly twelve gives 41.7% per market, a 1.67 times concentration gain. Scaling
removes that.

**An exclusion takes effect at a season boundary only.** Delay closes nothing
about concentration, because a permanent exclusion set concentrates as well as a
timed one. It closes a different attack: an exclusion filed against a live
window, once the exchange can see how trading is going.

### The season boundary is an event, not a date

**MEASURED.** A season is an integer counter advanced by a call. No date,
duration, start, end or calendar field exists anywhere in the schedule module.

`src/competition/season_schedule.py` and `contracts/CompetitionRegistry.sol` —
the counter and the call that advances it

```python
GENESIS_SEASON = 1
```

```solidity
    uint256 public currentSeason = 1;
    function advanceSeason() external onlyOwner { currentSeason++; }
```

The boundary is an event rather than a date, and the call that fires it is
privileged. Under governance that privilege becomes a vote, so an exchange cannot
predict when its own exclusion takes effect. That is stronger than any fixed
calendar.

### The natural brake is not enough

**PROPOSED.** A market excluded from the rotation earns its traders no
Quintessence, so an exchange that excludes heavily makes itself less attractive
to trade on. That cost is real, and it does not suffice.

The exchange keeps its fee income either way, because Quintessence is distilled
from fees the venue has already collected. Exclusion removes a participant's
reward, never the exchange's revenue.

And the brake can invert. An exchange that concentrates the rotation on one book
funnels every PoA trader into that book and deepens it. The self-harm argument
assumes the exchange loses volume; concentration is how it would gain volume. A
brake the actor can turn into an incentive is not a brake, so the three closures
above are structural and do not depend on the exchange's preferences.

---

## 16. The persistent world — in full

**HIS.**

> "There will be persistent events or game-world based activities such as
> building Guild towns and cities or other such life-skilling that fleshes out
> MMORPGs and pushing PoA towards hosting an entire generative blockchain based
> world."

```
persistent activity   building, and other life-skilling, that continues
                      between events
guild holdings        towns and cities, built and held by a guild
the direction         PoA hosts a generative blockchain world, not only a
                      tournament surface
```

His 2026-09-07 brainstorm already set the destination — a deep, perpetual,
blockchain-based game and world. This names what fills it.

### Two clocks now exist, and the design keeps them apart

**PROPOSED.** A turn is one candle, and a missed window is a lost turn. Persistent
activity cannot run on that clock. A town is built over days, and a participant
offline for a week has not forfeited a building.

```
event time    candle-locked, synchronous, take it or lose it
world time    continuous, asynchronous, survives absence
```

Both are real and neither replaces the other. A design that folds building into
the turn structure loses the persistence. One that folds turns into world time
loses the market anchor that turns exist to provide.

### Three rules of his already cover it

**PROPOSED.** Skills already cover progression, because every skill carries
levels that grow through use. Life skills need no separate rule.

The guild treasury already exists, filled only through the bleeding transfer and
never paid out to a personal wallet. A town is a larger guild holding and the
same principle applies.

Generation is now a subsystem rather than a detail. Dungeons are generative,
market loot drops are generative, and the world is generative. Three features
name one capability, so it is one thing to build rather than three.

### The scope boundary, stated plainly

**PROPOSED.** This issue is the PoA tab's initial implementation. A persistent
generative world is not an initial implementation, and the unit list must not
quietly grow to contain one.

The direction belongs in this document so no unit builds something that
forecloses it. **The unit list stays scoped to the tab and the economy.** Where
a unit's choice would make a persistent world harder later, that is worth a line
in the unit; where it would not, the world stays a later arc.

---

## The choices, with every option and its cost

The body carries the answer to each choice in one line, and its table says which four are now closed. The text below is the original, unchanged from the body it left, so the options and their costs survive for anyone overruling a closed one.

## The nine choices

Nine questions are his. Each carries one recommendation and the cost of the
alternative. Choice 9 is closed; his own directive answered it.

### Choice 1 — how many classes

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **Seven**, the planetary set | A closed array that never needs an eighth name; roles split two, two and three | Uneven roles, with one more Healer than Tank or Damage |
| Nine, three per role | Symmetry, and a third option inside every role | Two names from outside the planetary set, so the array is no longer closed |

**Recommended: seven.** The tradition closed the set at seven. Nine opens a set,
and then someone has to defend it against a tenth.

### Choice 2 — who is a participant

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **One bot, one participant** | Matches the code: one key per identity, one registration per bot, capital committed per bot | An operator with many bots fields many participants at once |
| One instance, one participant | One person, one character, which reads more naturally | Something has to sum the engine's per-bot registrations, and the health field has no single source |

**Recommended: one bot, one participant.** The engine already does this.

`src/competition/competition_engine.py` — `BotRegistration`

```python
    bot_id: str
    config_hash: str  # SHA-256 of strategy config — proves consistency
    capital_usd: float
```

### Choice 3 — where health comes from

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **The dollar target** | Health rises through play and has a per-cycle cap already; below the line is a wound, never a loss | Two players on different targets have different pools |
| Cost basis at the venue | One exchange-truth number per player | It moves with every fill, so the pool would never hold still |

**Recommended: the dollar target.** It satisfies his never-lose-money rule with
no further work.

### Choice 4 — the dungeon's shape

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **A linear room graph** | One zone carries the action at full size and the map as a small rail | Dungeons are chains of rooms, not mazes |
| A free-form grid | Richer exploration and real navigation | The map needs the whole Player window, and the action shrinks to a banner while the map is up |

**Recommended: the linear room graph.** Only this shape lets the Player window
do both jobs at once.

### Choice 5 — the currency of each fee

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **External for the charter, tokens for every stake** | The charter injects new value; the stakes lock existing value, which is what staking means | Two currencies in one fee table |
| Tokens for all four | Every fee locks, and the supply tightens fastest | A new guild pays tokens twice, because forming one already requires holding them |
| External for all four | Every fee injects, and no token leaves circulation | Nothing locks, and locking is half of what he asked the fees to do |

**Recommended: external for the charter, tokens for every stake.** This split is
the only one that does both jobs he named, and it does not charge a new guild
twice for one act.

### Choice 6 — what a fee may never take

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **No in-network exchange into tokens** | The earned path to a raid stays earned | No token market inside the platform |
| An in-network token market | Liquidity, and a price | Tokens turn purchasable, so every earned gate turns into a paid one |

**Recommended: no in-network exchange into tokens.** This constraint alone keeps
his no-pay-wall rule true.

### Choice 7 — can Quintessence move between participants

This one carries the whole Certified Transaction Socket. His loot is explicitly
tradable and his PoA tokens are explicitly stakeable. He has said neither about
Quintessence.

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **Bound to the participant who distilled it** | The anti-whale rule holds. A whale who will not trade on Acervator cannot enter at any price | No gifting, no guild treasury of Quintessence, and a dormant participant's balance helps nobody |
| Transferable between participants | A guild can carry a new member, and a quiet season still fills an event | A whale buys entry from anyone willing to sell, and the directive fails on the day the first trade clears |
| Transferable only inside one guild | A guild can carry its own members | A whale forms a guild, buys its members' balances, and the leak reopens one step further out |

**Recommended: bound to the participant who distilled it, and not transferable
at all.** His own sentence sets the bar — participation must benefit many and
not just themselves — and a quantity that can change hands is a quantity a whale
can buy. The third option only moves the leak; it does not close it.

This is the highest-value open question in the PoA economics, because every
other part of the socket works the same way whichever answer he gives, and this
answer alone decides whether the mechanism does its job.

### Choice 8 — how many markets reward in one window

The rotation's defence against blanket farming is the ratio of live markets to
rewarding markets. Everything else in section 9 holds whichever number he picks.
That one number decides how strong the defence gets.

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| **A small fixed count, one to three** | Covering costs a multiple in the hundreds, so blanket farming stops being worth doing | A participant trading a handful of markets may distil nothing for several windows, which reads as bad luck rather than as design |
| A fraction of the universe, say one market in ten | Steadier distilling, and a participant rarely goes a window empty | Covering costs only ten times as much, so a funded participant can absorb it |
| Half the universe | Almost nobody goes empty | Covering costs twice as much, and the defence is gone |

**Recommended: a small fixed count, with the window short enough that an empty
window costs little.** A short window turns the small count from a drought into
a shuffle, and the two settings work together: the count sets the defence, and
the window length sets how much an unlucky draw hurts.

Both numbers are his, because they decide what an event costs in hours of
trading. Nothing in the design changes if he moves them.

**Read that table against the eligible set, not the whole venue.** His
eligibility rules cap the drawable set at twenty markets per exchange, so a
fraction of the universe means a fraction of twenty, and the multiples in the
table shrink with it. A small fixed count is still the strong setting; the weak
settings are weaker than that table suggests.

### Choice 9 — how a market's allotment divides among its certifiers — CLOSED

**HIS, and it closes this choice.** The question asked how a market's allotment
divides among the participants who certified in it, and the recommendation was
an equal share above a minimum qualifying volume. His capture-bounds directive
answers it and supersedes that recommendation.

| Option | What it gives | What it costs |
| ------ | ------------- | ------------- |
| An equal share per certifying participant | Volume buys no advantage at all | A participant who traded one fill takes the same share as one who traded all day |
| Proportionate to each participant's fees in that market | Effort is rewarded in the way the socket already measures it | The participant with the most volume takes the largest share of every pool, which rebuilds the whale advantage inside the split |
| An equal share, capped by a minimum qualifying volume | Volume buys no advantage above the floor, and a token fill does not qualify | One more threshold for him to set, and a participant just under the floor gets nothing |
| **HIS answer — one allotment per participant, a share ceiling, a cooldown, a graded curve** | Bounds what one participant takes, stops them returning to the same pool, and makes a low-quality trade pay less whoever submits it | Three thresholds instead of one |

His answer is stronger than the recommendation it replaces. An equal share
bounds what one participant takes from one pool. His bounds also stop the same
participant returning to that pool, and they make a low-quality trade pay less
whoever submits it. **Nothing about the pool split remains open.**
