# PoA — what he owes, closed

Reference. The issue body carries a table headed *What he owes*, with fifteen
rows. This page resolves every row, then closes the owed items his later
directives raised.

Part A reports the fifteen. Part B decides what is left, numbered 17 onward, so
the numbering continues the record in
[`2026-09-09_poa_open_decisions.md`](2026-09-09_poa_open_decisions.md), which
ended at 16. Part C is the one item returned to him.

Every decision names the precedent level it came from.

```
1  his own explicit ruling            later beats earlier
2  what follows necessarily from it   a consequence of his rules
3  researched convention              a pattern across several systems
4  a chosen number                    states the property it produces
```

Every decision carries three checks. His rules: no gate behind a pay wall;
Quintessence only from PoA activity, never destroyed, 33,000,000 total;
organically competitive at every level; performance decides redistribution; only
event-anchored activity prevents dormancy. And the whale test, one line: what a
participant with a hundred times another's Quintessence gains.

---

## Part A — the fifteen rows, resolved

**MEASURED.** No row is still open. Fourteen were closed by the posted decision
record of 2026-09-09. One he answered himself.

| # | The row | Resolved by | Where |
| - | ------- | ----------- | ----- |
| 1 | The eligibility reading: both required, or either sufficient | decision 1 — both required | open decisions, part 1 |
| 2 | How much Quintessence one dollar of exchange fee distils | decision 2 — one for one | open decisions, part 1 |
| 3 | The per-market share ceiling | decision 3 — 5% | open decisions, part 1 |
| 4 | How many markets reward in one rotation window | decision 4 — five of twenty | open decisions, part 1 |
| 5 | The manipulation protection on the Exchange Participation Layer | decision 16, on HIS RULE | open decisions, part 3 |
| 6 | Can Quintessence move between participants | **HIS ruling, 2026-09-09** | the transfer directive |
| 7 | Lifetime caps for Gold Fold and Bear Slayer | decision 5 — 100,000 and 10,000 | open decisions, part 1 |
| 8 | Where the Quint Wallet sits | decision 6 — a panel over the party window | open decisions, part 1 |
| 9 | Can a guild hold Quintessence | decision 7 — yes, spending treasury only | open decisions, part 1 |
| 10 | Who pays for a persuaded cast | decision 8 — the actor | open decisions, part 1 |
| 11 | The Action Budget Curve bands and ratio | decision 9 — five bands, 100:1 | open decisions, part 1 |
| 12 | What makes a holding significant | decision 10 — top 20% by lifetime distilled | open decisions, part 1 |
| 13 | The loot rarity scale | decision 11 — five of Ripley's gates | open decisions, part 1 |
| 14 | Whether loot shares the trophy contract | decision 12 — its own contract | open decisions, part 1 |
| 15 | The pause key, and an external review before mainnet | pause key: decision 15, a halt council. Review: **returned, Part C** | open decisions, part 2 |

### Row 6 is his, and it is the one he answered

HIS, 2026-09-09. Row 6 was named in the body as the highest-value open question.
He closed it.

> "Quint is transferable between players via a specific skill isolated to common
> Guild members, takes significant time to complete based on amount and skill
> level, and has a negative effect of 'bleeding' quint back into the 'platonic'
> where it can be respawned and redistributed to other PoA participants."

The answer is transferable, and every term on the transfer costs the sender. A
skill gate, guild membership, a duration that scales with the amount, and a
bleed to the pleroma. The anti-whale property survives because concentration is
taxed at the moment it is attempted.

### Four more rulings of his that landed after the body's table was written

**HIS.** Each closes something the body or the decision record had left open.

```
exclusion only       the Exchange Participation Layer may remove a market
                     from the rotation list and nothing else
the decay floor      the franchise decays to the address's real balance,
                     and no Quintessence moves
event anchored       "Only PoA event anchored transactions prevent dormancy"
the fixed clock      level raises the pool, the candle does not, and that is
                     the power fantasy rather than a defect
```

### His four later directives raised a new owed set

**MEASURED.** Eight directives landed on 2026-09-09 after the decision record
was posted. Each named what it left for him. Those items are the subject of Part
B.

```
turns are candles      2 items
the persistent world   5 items
the per-round pool     5 items
the clock stays fixed  4 items, taken as one decision
abilities grow dearer  5 items, taken as one decision
the level arc          5 items
items and crafting     6 items
the naming standard    3 items
```

Three thresholds from the body's own table, and two gaps recorded under the
capture bounds, were never inside the fourteen either. They open Part B.

---

## Part B — the decisions

### 17. The grade curve — linear in the grade, no exponent

**Decided: the award is the fee in USD times the trade grade, with no exponent.
The curve stays linear.**

The shipped ledger already does this, and the supply arithmetic already posted
was computed on it. An exponent of two would halve the effective mint rate and
change a figure this issue has published.

```
src/competition/quintessence_ledger.py:164  QuintessenceLedger.distil
    amount = fee * QUINTESSENCE_PER_FEE_USD * grade
src/competition/quintessence_ledger.py:14   QUINTESSENCE_PER_FEE_USD = Decimal(1)
src/trading/trade_grader.py:175             _letter_from_numeric
    A+ >= 0.93   A >= 0.85   B >= 0.70   C >= 0.55   D >= 0.40   F below
```

The anti-farming work is already done by the grader's own bands. A wash trade
carries no execution against a reference price, no timing and no outcome, so it
lands under 0.40 and pays under forty cents on the dollar before the share
ceiling and the cooldown touch it.

**Precedent: level 1.** The tree ships it, and a precedent in his own tree is the
ruling.
**Source:** TAKEN FROM the shipped ledger. The figure that would revise it is the
measured spread of the grade field at `src/trading/trade_grader.py:74` across
live certified trades.
**Checked against:** Quintessence only from PoA activity; reward play not
position. The multiplier is a measure of how well the trade was done.
**Whale test:** a participant with a hundred times the Quintessence gets the same
multiplier. The grade reads the trade, never the balance.

---

### 18. The cooldown — a hard gate, in the bot's own candles, with a floor of fifteen minutes

**Decided: the gate is hard. It pays nothing until it clears. It counts candles
of the awarding bot's configured timeframe, never fewer than three, and never
less than fifteen minutes of wall clock.**

He named a soft or a hard gate and left the choice. A soft gate that reduces a
later award is the same thing as a steeper grade curve, and decision 17 has
already settled the curve. Two mechanisms doing one job is how a design drifts,
so the gate does the job the curve does not: it bounds the rate, not the size.

The wall-clock floor exists because three candles is not always a length of time.

```
src/exchange/timeframes.py:31   ALL_TIMEFRAMES
    1m  5m  15m  30m  1h  2h  4h  6h  12h  1d  1w
src/trading/container/config.py:89   ta_timeframe: str = "1h"

a 1m bot    3 candles = 3 minutes   -> the floor extends it to 15 minutes
a 5m bot    3 candles = 15 minutes  -> exactly the floor
a 1h bot    3 candles = 3 hours     -> the floor never binds
```

Fifteen minutes is three candles at the second-fastest granularity every venue in
the map publishes. It is read off the platform's own timeframe list rather than
chosen for its sound.

**Precedent: level 2 for the hard gate and the timeframe, level 2 for the floor.**
His rule sets three candles as a minimum; the floor is the same rule applied to
the fastest timeframe the platform allows.
**Source:** TAKEN FROM `ALL_TIMEFRAMES`. The three-candle minimum and the
proportionality to the award are HIS.
**Checked against:** organically competitive at every level. A fast bot and a slow
bot wait the same real time for the same award.
**Whale test:** a participant with a hundred times the Quintessence waits longer,
not shorter. The gate's length rises with the award.

---

### 19. The rotation window — twenty-four hours, aligned to UTC midnight

**Decided: one rotation window is twenty-four hours, opening at 00:00 UTC.**

The eligibility input is already a twenty-four-hour figure, so the window and the
ranking it draws from share one period. Nothing has to be re-derived at a second
cadence.

```
src/exchange/market_data.py:122  /api/v3/coins/markets
src/exchange/market_data.py:141  vol = float(coin.get("total_volume", 0) or 0)
src/exchange/market_data.py:153  "volume_24h": vol
```

A day is also the right size for an empty draw. A participant who covers none of
the five activated markets loses one day, which is a cost worth noticing and not
a cost worth leaving the platform over. A week would make one bad guess expensive
enough to discourage trading, and an hour would make the concealment useless
because the set would turn over faster than a position.

**Precedent: level 2.** The period follows from the volume figure the platform
already fetches.
**Source:** TAKEN FROM the CoinGecko markets call the tree already makes. The
alignment to UTC midnight is CHOSEN, to produce one boundary every participant
shares regardless of venue or timezone.
**Checked against:** no gate behind a pay wall; reward play not position. A window
is a clock, and a clock charges nobody.
**Whale test:** a participant with a hundred times the Quintessence gets the same
twenty-four hours. A window cannot be bought shorter or longer.

---

### 20. A market with no published project age — refused

**Decided: a market whose project age cannot be read does not reward
Quintessence. Nothing stands in for the missing figure.**

His rule requires six months of age, and his reason is that obscure pumps must
not award Quintessence. A missing age is exactly the case a pump can manufacture,
because the data that is absent is the data that would refuse it.

The alternative was recorded and it loses on one property.

```
refuse      an asset with no known age rewards nothing
fall back   StoneTablet.listed_at_ms stands in
            src/trading/stone_tablets/registry.py:96
```

The fallback is safe in the same direction and it is gameable in one. An age
derived from the first candle the platform happens to hold is a fact about this
installation, not about the project, so two installations would disagree about
the same market. Refusing cannot be gamed by withholding data.

**Precedent: level 2.** His stated purpose decides it.
**Source:** HIS RULE on age, applied to the missing-input case.
**Checked against:** Quintessence only from PoA activity; organically competitive
at every level. A market that cannot prove its age is not a contest.
**Whale test:** a participant with a hundred times the Quintessence gains nothing.
Age belongs to the market, not to the holder.

---

### 21. Performance for the redistribution — a normalised rank, not a share of the total

**Decided: the 75% returning at the end of an Elite Event divides by each
participant's rank position in that event, normalised across the field. Never by
a share of the field's total output.**

He ruled the basis is performance. The open question was how performance is
expressed, and a share of the total re-admits scale through the back door. The
largest output becomes the denominator, so a participant who produces twice as
much takes twice as much, which is the proportional outcome his own rule forbids.

```
share of total   output / field total        scale survives
normalised rank  (n - position + 1) / sum    scale is removed
```

A field of sixty pays the first place sixty units of weight and the last place
one. A participant who doubles their damage moves up the order; it does not
double their share unless the order moves with it.

**Precedent: level 2.** It follows from his own ruling that PoA is organically
competitive at every level, and from his answer that redistribution is by
performance.
**Source:** HIS RULE for performance. The rank normalisation is CHOSEN, to produce
a payout that changes only when the order changes.
**Checked against:** performance decides redistribution; reward play not position.
**Whale test:** a participant with a hundred times the Quintessence can spend
more, and takes a share set only by where they finished. Spending more funds the
better players.

---

### 22. Which market's candles — the clock is shared, the anchor market supplies price

**Decided: the turn boundary comes from the candle clock itself, which is the same
instant on every market. Where a mechanic needs price movement, it reads the
event's anchor market, declared when the event opens and drawn from that window's
activated set.**

One-minute and five-minute candles close on the same wall-clock boundary
everywhere, so no choice of market is needed to synchronise turns. The question
only bites where a mechanic reads what the candle did, and there the event needs
one named market.

```
the boundary     the minute, shared by every market and every participant
the content      the event's anchor market, one of the window's five
```

Drawing the anchor from the activated set keeps one eligible market list behind
both halves of the design. Quintessence and the event clock then read the same
rotation rather than two.

**Precedent: level 2.** His directive aligns turns to candles, and candle
boundaries are a property of the clock.
**Source:** HIS RULE for the alignment. The anchor from the activated set is
CHOSEN, to produce one eligible market list serving both the award and the event.
**Checked against:** organically competitive at every level. Every participant in
an event shares one boundary, so no per-player timer exists to game.
**Whale test:** a participant with a hundred times the Quintessence gets the same
sixty seconds.

---

### 23. What a participant sees while a block fills — their own committed orders, then the playback

**Decided: the player window shows the previous block's playback, with the
participant's own committed actions for the live candle drawn over it as intent.
Other participants' pending actions are never shown.**

The shape is the convention in games that resolve a turn simultaneously, and
three published systems share it.

```
Frozen Synapse        unlimited planning time, a simulation of the projected
                      result against current enemy behaviour, then a resolution
                      of about five seconds once both sides commit
Laser Squad Nemesis    orders issued, probable effects previewed, submitted, and
                      a ten-second simultaneous playback when both sides finalise
the general pattern    a resolution phase computes the next state after every
                      player has submitted
```

Showing your own intent is what makes the window usable. Showing anyone else's
would destroy the simultaneity, which is the property that makes a candle a fair
boundary.

**Precedent: level 3.** The plan-preview-playback shape is a pattern across
simultaneous-turn systems rather than one product's feature.
**Source:** TAKEN FROM the three systems above.
**Checked against:** organically competitive at every level. Nobody sees another
participant's decision before committing their own.
**Whale test:** a participant with a hundred times the Quintessence sees exactly
what everyone else sees.

---

### 24. The pool's name — Impetus

**Decided: the per-round resource pool is called Impetus. The name *action
budget* stays with the Quintessence curve and never names the pool.**

Two mechanisms were heading for one natural name. His Quintessence mechanism is
the Action Budget Curve, and a per-turn allowance is what most designers would
also call an action budget.

Impetus is the impressed force that keeps a body moving and fades rather than
accumulating. It carries the speed he named, it expires by its own nature, and
it collides with nothing the platform already uses.

```
method    a count of files whose text holds each word, case-insensitive,
          across three trees: src/, contracts/ and docs/
result    no file under any of the three holds impetus, and none holds any of
          the five station words in decision 41
```

It also satisfies his own third naming rule: where an exact English word exists,
use it rather than a Latin near-miss.

**Precedent: level 1 for the latitude, level 4 for the word.** He granted Latin
and exotic names where an ancient idea has no modern term, and ruled that a plain
word wins where one exists.
**Source:** CHOSEN, to produce a name that cannot be confused with the Action
Budget Curve and that reads plainly in a row.
**Checked against:** no gate behind a pay wall. A name charges nobody.
**Whale test:** a participant with a hundred times the Quintessence gains nothing
from a word.

---

### 25. The grant — four Impetus at level one, one more every twenty levels

**Decided: a participant receives four Impetus per turn at level one, rising by
one every twenty levels, to nine at level one hundred.**

Four is the smallest grant that makes a turn a decision rather than a reflex. At
two, the turn is a move and an attack with nothing to weigh. At eight, a
participant holds more choices than a sixty-second candle allows.

```
level    1   4 Impetus
level   20   5
level   40   6
level   60   7
level   80   8
level  100   9
```

The grant more than doubles across the arc while the candle does not move, which
is the fantasy he confirmed. It stays humane because his own later refinement
raises the cost of high-level abilities with it, so the count of decisions per
turn does not climb with the grant.

**Precedent: level 4, inside a level 1 frame.** His directive set the pool's
shape — same amount each turn, sized by level, no stacking, use it or lose it.
**Source:** CHOSEN, to produce a level-one turn holding four choices and a
level-one-hundred turn holding nine, against a clock that never moves.
**Checked against:** no gate behind a pay wall; reward play not position. Levels
come from play.
**Whale test:** a participant with a hundred times the Quintessence has the same
grant at the same level. Impetus is granted, never bought.

---

### 26. The speed modifiers — one multiplier on the grant, capped at twice the level value

**Decided: every haste, slow, initiative and gear effect multiplies the grant.
The product is capped at two times the level's value and floored at one Impetus.
Fractions round down.**

He said level *or other speed effecting metrics* sizes the pool, which makes the
pool the one home for every speed effect. A single multiplier is what keeps it
one home instead of a stack of additive bonuses nobody can balance.

```
level 40 grant          6 Impetus
a 1.5x haste            9
the cap at 2x          12, and no combination exceeds it
a 0.5x slow             3
the floor               1, so a participant is never frozen out of a turn
```

The cap is what stops speed becoming the only statistic worth raising. The floor
is what stops a slow effect deleting a turn, which would hand a participant a
lost candle they could not act in.

**Precedent: level 2 for the single multiplier, level 4 for the bounds.**
**Source:** HIS RULE that speed metrics size the pool. The 2x cap and the
one-Impetus floor are CHOSEN, to produce a bounded speed race and a turn that
always holds at least one action.
**Checked against:** organically competitive at every level. A bounded modifier
keeps a lower-level participant in the fight.
**Whale test:** a participant with a hundred times the Quintessence gains nothing
directly. Gear that raises speed is loot, and loot comes from dice rolls.

---

### 27. The pool cost per action — the same five bands, one to four Impetus

**Decided: an action costs both. Its Quintessence band is unchanged, and its
Impetus cost runs one, one, two, three, four across the same five bands.**

Pegging the two scales to one band list keeps them from drifting apart. The
dearest action costs the whole level-one grant, so at level one a decisive cast
is the turn, and what levelling buys is the room to do something else beside it.

```
band    Quintessence   Impetus   at level 1, four Impetus
x1          0.001         1      a move leaves three
x3          0.003         1      a basic attack leaves three
x10         0.010         2      a class ability leaves two
x30         0.030         3      a group ability leaves one
x100        0.100         4      the decisive cast is the whole turn
```

Impetus is tempo and Quintessence is economy, and the two answer different
questions. The pool asks how much a participant can do this turn. The curve asks
what they are willing to pay for.

**Precedent: level 2.** His two directives set both scales; pegging them to one
band list follows from their having the same five action kinds.
**Source:** TAKEN FROM decision 9's five bands. The Impetus numbers are CHOSEN, to
produce a dearest action that consumes a whole level-one turn.
**Checked against:** no gate behind a pay wall; affordable. A participant who has
spent their Impetus has lost a turn, never money.
**Whale test:** a participant with a hundred times the Quintessence still cannot
exceed their Impetus. The pool is the brake that money does not reach.

---

### 28. Partial actions — refused

**Decided: an action runs only when the full Impetus cost is available. No
partial action exists, and nobody borrows against the next turn.**

His rule is that the pool does not stack and is lost unspent. A partial action
is a stack in the other direction: it spends a turn's remainder on a fraction of
something that completes later, which is carrying the pool forward by another
name.

The contrast is published. A carry-over pool changes the whole shape of a turn.

```
XCOM              his named reference. A fixed allowance per turn, lost unspent
Divinity: Original Sin   unspent action points carry into the character's next
                         turn, so skipping builds a larger turn later
```

Refusing partial actions also keeps the leftover Impetus meaningful. A
participant ending a turn with one point has a real choice between a cheap action
now and nothing, which is the decision the pool exists to create.

**Precedent: level 2.** It follows from his no-stacking, use-it-or-lose-it rule.
**Source:** HIS RULE. The Divinity contrast is TAKEN FROM the published carry-over
behaviour.
**Checked against:** organically competitive at every level. Nobody banks a turn.
**Whale test:** a participant with a hundred times the Quintessence cannot buy a
fraction of an action either.

---

### 29. Issuing actions inside one candle — four rules

**Decided: four rules, so the fantasy he confirmed survives contact with the
interface.**

He ruled the clock stays fixed and the pool grows, which puts the burden on the
surface. A participant holding nine Impetus and sixty seconds has to be able to
express them.

```
prepared actions   a participant may queue actions before the candle opens;
                   the queue commits at the boundary
repetition         repeating the last action takes one input, never a full
                   re-selection
commit             implicit at the candle's close. No confirm step exists,
                   because a confirm step can miss the boundary
readability        the Impetus remaining sits in the party window header
                   beside the Quintessence balance, always on screen
```

Prepared actions are the one that matters most. Without them the fastest events
reward reaction speed, and a participant's standing would measure their hands
rather than their trading.

**Precedent: level 2.** Each rule follows from his fixed-clock ruling and from
decision 6, which already put a persistent readout in the party window header.
**Source:** HIS RULE for the fixed clock. The four rules are CHOSEN, to produce a
turn whose limit is the decision rather than the input.
**Checked against:** organically competitive at every level. A slow surface would
make the contest a test of dexterity.
**Whale test:** a participant with a hundred times the Quintessence gets the same
interface and the same sixty seconds.

---

### 30. Charges that cross a turn boundary — five rules

**Decided: five rules. A charge is the first thing in the design that survives a
turn, so each one is stated rather than inferred.**

```
Impetus         paid per turn, as the charge occupies each turn it spans
Quintessence    committed at the start, at the band's full cost
interruption    a hit does not break a charge. A stun or a death cancels it
a missed turn   does not cancel a charge. The charge is the turn's action,
                and it was already issued
event end       an unfinished charge does nothing and refunds nothing
cancellation    by the participant, at any point, refunding nothing
```

Paying Impetus per turn is what stops a charge being free tempo. Committing
Quintessence at the start is what makes the decision a real one: a cancelled
charge is a loss, so an expensive cast is argued about before it begins rather
than abandoned halfway.

The interruption rule is the one that protects the guild negotiation. If any hit
broke a charge, the decisive cast his Action Budget Curve exists to make
arguable would never land in a sixty-player event.

**Precedent: level 2 for the shape, level 4 for the interruption line.** His
refinement states that high-level abilities take more points or more than one
turn, and that a charge trades time for power.
**Source:** HIS RULE for the charge itself. The five rules are CHOSEN, to produce a
commitment a participant cannot walk back and an enemy cannot trivially deny.
**Checked against:** Quintessence never destroyed. A committed charge's spend goes
to a held address like every other spend, and a cancellation leaves it there.
**Whale test:** a participant with a hundred times the Quintessence can afford
more cancelled charges. Each one still costs them a turn and pays the rest of the
field through the redistribution.

---

### 31. The chain's phases — the five colour stages already in the tree

**Decided: the chain has five alchemical phases, and they are the five colour
stages the trophy generator already letters.**

He asked for another hundred levels per alchemical phase and left the phases
unnamed. The tree named them before the directive existed.

```
src/competition/trophy_generator.py:243   Harvest            NIGREDO
src/competition/trophy_generator.py:244   Gold Fold          ALBEDO
src/competition/trophy_generator.py:245   Bear Slayer        CITRINITAS
src/competition/trophy_generator.py:246   Grand Accumulator  RUBEDO
src/competition/trophy_generator.py:247   Ekthelius          UNIO MYSTICA
```

Five phases at a hundred levels each is a five-hundred-level arc. Adopting the
existing names costs nothing and stops a second phase vocabulary appearing beside
the first.

**Precedent: level 2.** His directive names alchemical phases; the tree already
letters exactly five.
**Source:** TAKEN FROM `trophy_generator.py`.
**Checked against:** reward play not position. A phase is a property of the chain,
not of a holder.
**Whale test:** a participant with a hundred times the Quintessence cannot advance
a phase. Nobody can outrun the world, because the ceiling moves with the chain
everyone shares.

---

### 32. What advances a phase — a fifth of the cap minted

**Decided: a phase advances when total Quintessence ever distilled crosses the
next fifth of the cap. Five phases, 6,600,000 Quintessence each.**

He tied the arc to the chain's own ageing rather than to a calendar. The only
figure that measures this chain's age from the inside is how much of its capped
supply has ever been distilled, and the ledger already tracks it.

```
NIGREDO         0           to   6,600,000
ALBEDO          6,600,000   to  13,200,000
CITRINITAS     13,200,000   to  19,800,000
RUBEDO         19,800,000   to  26,400,000
UNIO MYSTICA   26,400,000   to  33,000,000

src/competition/quintessence_ledger.py:245  total_ever_minted
src/competition/quintessence_ledger.py:13   QUINTESSENCE_SUPPLY_CAP
```

The figure only rises, never falls, so a phase can never reverse. A calendar
would have advanced the world while nobody played, which would break the link
between the world's age and the trading that funds it.

**Precedent: level 2 for the measure, level 4 for the fifths.**
**Source:** HIS RULE that phases follow the chain's ageing. Equal fifths are
CHOSEN, to produce a monotonic phase clock read off a field the ledger already
holds.
**Checked against:** Quintessence only from PoA activity; never destroyed. The
phase clock reads distilling, which is trading done.
**Whale test:** a participant with a hundred times the Quintessence moves the
phase clock by the fees they actually paid, like everyone else, and gains no
advantage from a phase that advances for the whole world at once.

---

### 33. What the world level changes — enemies and the loot floor, never a rule

**Decided: the world level raises enemy strength and raises the floor of the loot
table. It changes no rule a participant relies on.**

He said each arc naturally increases the world level and left its effect open. The
bound matters more than the numbers, because the governance ladder already
classifies a change to a rule a holder relies on as the heaviest kind of change.

```
the world level may change   enemy health, enemy damage, the lowest loot tier
                             that can drop
it may never change          the supply cap, the distil rate, the bleed, the
                             share ceiling, the redistribution basis, the bands
```

Letting the world level touch an economic rule would give the chain's own ageing
the power the L4 vote was designed to hold. One mechanism would then be able to
change the cap without anybody voting.

**Precedent: level 2.** It follows from decision 15, where any change to a rule a
holder relies on is an L4 matter.
**Source:** HIS RULE that the world level rises. The boundary is CHOSEN, to
produce a difficulty curve that cannot reach the economy.
**Checked against:** organically competitive at every level; performance decides
redistribution. Difficulty rises for everyone at once.
**Whale test:** a participant with a hundred times the Quintessence faces the same
enemies.

---

### 34. Ability cadence — ten new abilities per hundred levels, something at every level

**Decided: one new ability every ten levels, one upgrade to an existing ability at
each half-decade, and a numeric improvement at every other level.**

Two published progressions bracket the cadence, and they agree on the shape: a
genuinely new ability is rare, and something lands often.

```
Dungeons and Dragons 5th edition   two or three class features at low levels,
                                   existing features improving as levels rise,
                                   and a choice every four levels
World of Warcraft, the 1-60 arc    every level unlocks an ability, a talent or
                                   an upgrade, with new abilities per
                                   specialization about every two levels
```

Ten new abilities per hundred levels is the design load this sets, and it is
worth stating plainly: seven classes across five phases is three hundred and
fifty abilities for the full arc, with seventy for the first.

```
every level ending in 0    a new ability
every level ending in 5    an upgrade to an existing one
every even level           a numeric step
```

**Precedent: level 3 for the cadence, level 4 for the interval.**
**Source:** TAKEN FROM the two published progressions above. The ten-level interval
is CHOSEN, to produce ten abilities per arc and a measurable design load of
seventy for the first phase.
**Checked against:** no gate behind a pay wall; reward play not position. Levels
come from experience per action, which is his own rule.
**Whale test:** a participant with a hundred times the Quintessence gains nothing.
A level costs experience and Quintessence cannot buy experience.

---

### 35. The fourth role — the mapping stands as proposed

**Decided: Quicksilver Draught is the pure healer. Copper Conduit is the support
healer. Silver Mirror is the pure support. The three principles are unchanged.**

He corrected the array to need a pure healer, a support healer and a pure
support. The imagery in the existing three names already carried the distinction.

```
Quicksilver Draught   a draught is a medicine, taken, working directly
Copper Conduit        copper conducts, carrying healing and enhancement onward
Silver Mirror         a mirror reflects rather than mends — warding,
                      redirection, no direct healing
```

Splitting the three inside Mercury keeps the tria prima intact. Salt endures, so
Tank. Sulphur burns, so Damage. Mercury is the fluid and changeable principle,
which covers sustaining and altering both, so no fourth principle is needed.

**Precedent: level 1 for the three roles, level 2 for the assignment.** He named
the three roles he wants; the assignment follows from names already in the design.
**Source:** HIS RULE for the fourth role. The mapping is TAKEN FROM the existing
class names.
**Checked against:** organically competitive at every level. Three distinct jobs
rather than three spellings of one.
**Whale test:** a participant with a hundred times the Quintessence picks from the
same seven classes.

---

### 36. Where the persistent world is seen — the player window gains a world mode

**Decided: the player window switches between event mode and world mode. No fourth
zone is added, and no second tab.**

His constraint is one PoA tab and only one. His layout has three zones, and all
three are event-shaped. The player window is the one that already carries two
jobs, the action view and the dungeon map rail, so it is the zone that already
switches what it draws.

```
event mode   players acting, the map rail for crawl and raid
world mode   guild towns and cities, life-skilling, building in progress
the others   the enemy screen and the party window stay as they are
```

A persistent world is much larger than a panel, which is why it takes a mode
rather than an overlay. Mode switching also keeps the party window intact, and
the party window is where his wallet readout and the Impetus readout live.

**Precedent: level 2.** It follows from his one-tab rule and from his own layout,
where the player window is the zone that already changes what it shows.
**Source:** HIS RULE for one tab and for the three zones. The mode is CHOSEN, to
produce a world view without a fourth zone or a second surface.
**Checked against:** no gate behind a pay wall. A view charges nobody.
**Whale test:** a participant with a hundred times the Quintessence sees the same
two modes.

---

### 37. What a town is on-chain — registry state, not an NFT

**Decided: a town is chain state keyed to a guild. It is not a token, and it
cannot be transferred or sold.**

A town is a place the guild's members act in, not an object anyone holds. Minting
it as a token would make it sellable, and a sellable town is a position a
participant can buy into rather than a thing a guild built.

```
a town        state: owner guild, level, buildings, progress timers
not a token   no id, no balance, no transfer
the contract  the registry that already holds seasons and competitions
```

This also keeps the conservation law at three buckets. A new token class holding
value would add a fourth place for value to be, and the invariant a security
audit can check at every block would stop being exact.

**Precedent: level 2.** It follows from his anti-whale rule and from the
conservation law the design already carries.
**Source:** CHOSEN, to produce a holding that cannot be bought and does not add a
bucket.
**Checked against:** organically competitive at every level; reward play not
position. A town is built, never acquired.
**Whale test:** a participant with a hundred times the Quintessence cannot buy a
town, because no town is for sale.

---

### 38. Who may build — a guild builds the town, a participant builds inside it

**Decided: a town belongs to a guild and only a guild may raise it. A participant
builds and runs their own holdings inside a town, and needs no guild for those.**

His directive names guild towns and cities, and also other life-skilling, which is
not a guild activity. Two scopes therefore exist and they do not compete.

```
guild      the town itself, its buildings, its stations
a member   a personal workshop, a plot, a craft station inside the town
anyone     life-skilling, with or without a guild
```

Requiring a guild for all of it would make the persistent world unreachable for a
participant with no guild, which is a gate in everything but name.

**Precedent: level 2.** His directive names both a guild activity and an
individual one.
**Source:** HIS RULE names guild towns and life-skilling together. The split is
CHOSEN, to produce a world reachable without a guild.
**Checked against:** no gate behind a pay wall; organically competitive at every
level. Nothing in the world needs a guild to reach.
**Whale test:** a participant with a hundred times the Quintessence may fund a
guild's town and cannot own it. A guild holding is not a personal one.

---

### 39. The world clock — jobs on real elapsed time, continuing while absent

**Decided: persistent progress runs on queued jobs measured in real elapsed
hours. A job advances while the participant is away, and a completed job waits to
be collected.**

Event time is candle-locked and take it or lose it, which is his rule. World time
cannot work that way, because a town is built over days and an absent participant
has not forfeited a building. The pattern is the convention in systems with
persistent holdings.

```
EVE Online      manufacturing jobs run for days, continue while the character
                is offline, and pause only if the facility's service module
                goes offline
OGame           a construction queue holding several buildings, each checked
                for resources when it reaches the top
Fallen Earth    crafting completed in real time whether the player was online
                or not
```

The shared property is a timer on the wall clock, a queue, and a result that
survives absence. A completed job waiting to be collected is what makes the
progress safe: nothing expires, so no participant loses a town to a night's
sleep.

**Precedent: level 3 for the shape, level 2 for keeping the clocks apart.**
**Source:** TAKEN FROM the three systems above. His directive requires persistence,
and his candle rule governs events only.
**Checked against:** only event-anchored activity prevents dormancy. A world job
is not event anchored, so it builds a town and does not preserve a vote.
**Whale test:** a participant with a hundred times the Quintessence waits the same
hours. A job cannot be paid shorter.

---

### 40. Generation — one generator, three callers

**Decided: one generator serves dungeons, market loot drops and the world. Each
caller passes its own seed and its own table.**

Three features name the same capability, and his directive calls the world
generative in the same breath as the dungeons. One generator is one thing to
audit for fairness, which matters because every one of the three pays out value.

```
the generator   deterministic from a seed, verifiable after the fact
dungeons        a seed per event
loot            a seed per drop, against the rarity weights
the world       a seed per region
```

Three separate generators would mean three fairness arguments and three places a
weight could be wrong. One generator with a published seed is checkable by
anybody, which is the property a chain-based game needs.

**Precedent: level 2.** His directive names all three as generative.
**Source:** HIS RULE for generation. The single generator is CHOSEN, to produce one
fairness surface instead of three.
**Checked against:** reward play not position. A seeded roll reads no balance.
**Whale test:** a participant with a hundred times the Quintessence rolls on the
same tables with the same seeds.

---

### 41. The naming collision — crafting takes apparatus names, the loot tiers keep the gates

**Decided: the loot rarity tiers keep Ripley's gates. Crafting stations are named
for the apparatus. No alchemical operation is a proper noun anywhere in the
design.**

The tiers are decided and posted. The operations would have to be the crafting
verbs, and a Calcination-tier item produced by a calcination step is two meanings
sharing one word.

```
the tiers stay    CALCINATION PUTREFACTION SUBLIMATION FERMENTATION EXALTATION
stations become   athanor, alembic, crucible, retort, pelican, the water bath
                  named for Maria the Jewess
measured free     no file under src/, contracts/ or docs/ holds any of the
                  five station words, by the count in decision 24
```

The apparatus vocabulary describes what each station does, which a rarity label
does not. An alembic distils and a crucible takes heat, so a recipe reads as an
instruction rather than as decoration.

**Precedent: level 2.** The tiers are already decided, so the later system is the
one that moves.
**Source:** TAKEN FROM the apparatus of the tradition. The direction of the move is
CHOSEN, to avoid rewriting a decision already posted.
**Checked against:** no gate behind a pay wall. A station name charges nobody.
**Whale test:** a participant with a hundred times the Quintessence uses the same
stations.

---

### 42. Item state — unique ids at supply one carry on-chain state, stackables do not

**Decided: gear with per-item state is minted as a unique id with a supply of one,
and its mutable properties live on-chain keyed by that id. Materials and
consumables stay fungible ids with no per-item state.**

A multi-token contract makes a token id a class and a balance a count. Per-item
state cannot live on a class, so a sword with its own wear and its own upgrades
needs an id of its own.

```
immutable, at mint   the tier, the base kind, the recipe, the crafter
mutable, on-chain    durability, upgrade level, socketed additions
off-chain            artwork and description, behind the metadata address
the refresh signal   the contract's own URI event, which the standard defines
                     for exactly this purpose
```

The published pattern is to split attributes into mutable and immutable rather
than to put everything behind a fixed metadata address. A related standard adds a
metadata-update event to the single-token standard for the same reason, so
marketplaces know to re-read. Storing the mutable half on-chain also means the
game can read it, which a metadata address cannot supply to a contract.

**Precedent: level 3.** The mutable-immutable split and the update signal are the
convention across the token standards rather than one project's scheme.
**Source:** TAKEN FROM the multi-token standard's URI event and the published
mutable-immutable split. Minting gear as one id of one unit is CHOSEN, to produce
per-item state on a contract whose ids are otherwise classes.
**Checked against:** Quintessence never destroyed. No item mechanism touches the
Quintessence buckets.
**Whale test:** a participant with a hundred times the Quintessence can buy gear,
because loot is tradable by his own rule. Gear raises speed through the capped
modifier in decision 26, and the cap is what stops purchase becoming dominance.

---

### 43. Consumables are destroyed

**Decided: a consumed item is destroyed. The indestructibility rule belongs to
Quintessence and does not extend to items.**

His reason for Quintessence was doctrinal rather than economic.

> "Quint is the essence...should not be able to be destroyed from a philosophical
> standpoint..."

The fifth essence is the incorruptible one. Matter is the thing the tradition
transmutes and consumes, so a potion that survives its own drinking would
contradict the same doctrine that protects Quintessence. Burning a consumed item
also keeps crafting meaningful: a recipe that destroys nothing produces a supply
that only grows.

**Precedent: level 2.** It follows from his own stated reason for Quintessence's
indestructibility.
**Source:** HIS RULE, read for what it actually covers.
**Checked against:** Quintessence never destroyed, 33,000,000 total. The item rule
leaves all three buckets untouched.
**Whale test:** a participant with a hundred times the Quintessence consumes items
at the same rate everyone else does.

---

### 44. Craft inputs — materials and real time, never Quintessence

**Decided: a recipe consumes materials and elapsed time. It never consumes
Quintessence or Impetus.**

Quintessence is the entry and action currency, and spending it on crafting would
put a gear ladder behind the same currency that buys entry. That is the pay wall
his first economic rule forbids, arriving by a different door.

```
consumed   materials, gathered or dropped
occupied   a station, for a real-elapsed-time job
never      Quintessence, Impetus
```

Impetus is excluded for a different reason. It exists only inside a turn, and
crafting happens in world time, where there are no turns.

**Precedent: level 2.** It follows from his no-pay-wall rule and from the two
clocks being separate.
**Source:** HIS RULE on pay walls. The material-and-time input is CHOSEN, to
produce a gear ladder reachable by playing rather than by spending.
**Checked against:** no gate behind a pay wall; Quintessence only from PoA
activity.
**Whale test:** a participant with a hundred times the Quintessence cannot
shortcut a recipe. Quintessence buys no materials and no hours.

---

### 45. Who crafts — any participant, at a station, gated by a life-skill level

**Decided: any participant may craft. A recipe requires a station and a life-skill
level. Guild stations reach the higher levels; a personal station covers the
lower ones.**

His rule is that all skills carry levels which grow through use, so crafting needs
no new progression. Restricting crafting to a class would make gear a class
privilege, and he named life-skilling as something that fleshes out the world
rather than something a class owns.

```
anyone            may craft
the recipe needs  a station of the right kind, and a skill level
personal station  the lower levels
guild station     the higher ones, which is a reason to join a guild rather
                  than a condition of playing
```

**Precedent: level 2.** It follows from his skills rule and his life-skilling
directive.
**Source:** HIS RULE for skills growing through use. The station split is CHOSEN, to
produce a reason to join a guild that is not a gate.
**Checked against:** no gate behind a pay wall; reward play not position. A skill
level comes from uses, and decision 13 already weights a use by its quality.
**Whale test:** a participant with a hundred times the Quintessence has no skill
level they did not earn.

---

### 46. The summit — five items, one per phase, named for figures not already spoken for

**Decided: five summit items, one per alchemical phase, each named for a hermetic
figure. The ideals already used by the platform are not available.**

He wants the highest items tied to hermetic figures and ideals. A count across
the tree covered four figures and six ideals, and most of the obvious ideals are
taken.

```
free, measured     no file under src/, contracts/ or docs/ holds Hermes
                   Trismegistus, Zosimos, Jabir, Maria the Jewess or
                   Philosopher's Stone
taken, measured    Ouroboros   src/exchange/crypto_assets.py:168, Cardano's
                               consensus name
                   Prima Materia  src/competition/trophy_generator.py:250,
                               the Harvest tier's own subtitle
                   rebis       trophy_generator.py:170, drawn on a trophy
                   SOLVE ET COAGULA  lettered on every trophy ring
                   Emerald Tablet    the platform's price record is the
                               Stone Tablets
```

Paracelsus and Ripley are already spoken for inside the design itself, by the
three roles and the loot tiers. Five items is one per phase, which ties the summit
to the chain's age rather than to a release.

**Precedent: level 1 for the intent, level 4 for the count.**
**Source:** HIS RULE that the summit items are tied to hermetic figures. The
five-item count is CHOSEN, to produce one summit item per phase. The collisions
are MEASURED.
**Checked against:** reward play not position; no gate behind a pay wall. A summit
item is the thinnest tail of the loot table, reached by dice rolls.
**Whale test:** a participant with a hundred times the Quintessence rolls the same
one-in-two-hundred top tier.

---

### 47. The short form — twelve characters

**Decided: every named thing carries a full name and a short form of at most
twelve characters. The short form is authored, never truncated by the surface.**

His layout puts a hundred and twenty participants on screen at forty to a page,
and the row carries a health bar, a role colour, a name and one mark slot. A long
name does not survive that row.

```
Quicksilver Draught   ->   Quicksilver
Copper Conduit        ->   Copper
Silver Mirror         ->   Silver
CALCINATION           ->   Calcination
```

Twelve characters holds the longest single word in the vocabulary already chosen,
and it is short enough that forty rows fit a page without the name crowding the
health bar. An authored short form beats a truncation because a truncation can
produce two identical labels from two different names.

**Precedent: level 2 for the requirement, level 4 for the number.** His layout
imposes the row; his naming directive grants the exotic names that need a short
form.
**Source:** CHOSEN, to produce a label that fits forty rows and never collides
after shortening.
**Checked against:** no gate behind a pay wall. A label charges nobody.
**Whale test:** a participant with a hundred times the Quintessence reads the same
rows.

---

### 48. The glossary — the manual page that already holds one

**Decided: every PoA term a participant will not know is defined in the manual's
glossary, and the tab links to it.**

The platform already has the page, and it already defines hermetic terms for the
same reason.

```
docs/manual/12-adr-index-and-glossary.md:41    Glossary
docs/manual/12-adr-index-and-glossary.md:176   Solve et coagula — dissolve and
                                               reform
docs/manual/08-tabs/proof-of-accumulation.md:224   Quintessence
```

A second glossary inside the tab would be a second authority, and the two would
disagree the first time a term changed. One page, linked from the surface.

**Precedent: level 2.** The manual is the platform's reference, and the glossary
page exists.
**Source:** TAKEN FROM the existing manual pages.
**Checked against:** no gate behind a pay wall. A definition charges nobody.
**Whale test:** a participant with a hundred times the Quintessence reads the same
glossary.

---

### 49. One vocabulary authority

**Decided: the PoA manual page is the only authority for PoA vocabulary. A name
enters the design by landing on that page, and a unit that needs a new name adds
it there in the same change.**

Two units naming one idea differently is the failure he named. The fix is a single
page that every unit reads, rather than a convention every unit remembers.

```
docs/manual/08-tabs/proof-of-accumulation.md    the PoA page
docs/manual/12-adr-index-and-glossary.md        the glossary
```

The rule has a second half that matters as much. A name already on the page is
the name, even when a better one occurs to somebody later, because two spellings
of one thing is the defect the authority exists to stop.

**Precedent: level 2.** The repository already treats the manual as the reference
for what the product is.
**Source:** HIS RULE that one authority must hold the vocabulary. The page is
TAKEN FROM the existing manual.
**Checked against:** no gate behind a pay wall.
**Whale test:** a participant with a hundred times the Quintessence names nothing.

---

## Part C — returned to him

**One item.** Everything else on the owed list is decided above or was decided on
2026-09-09.

### The external security review before the genesis deployment

**Returned.** Whether an outside firm reviews the three contracts before the
first mainnet deployment, and when.

The test it fails is the second one: it is a spend, and a spend is his. It does
not fail the first test — his own words guide it, and the recommendation is
already on the record. A review before the genesis deployment is the only
opportunity to find a flaw while fixing one is cheap, because under decision 15
every deployed contract is immutable and the first one exists before any holder
can vote.

```
his words      "Cannot have any gaps. Need modern standards and technology
               deployed for this. No one needs another baddy blockchain."
the blocker    no toolchain resolves the OpenZeppelin imports, so the three
               contracts have never been compiled
what is ready  the tooling pass is unit 5 and the contracts build first
```

The decision he makes is the money and the timing. Nothing else on this page waits
on it.
