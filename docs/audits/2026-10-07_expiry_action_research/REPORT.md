# Expiry Action Research

**Mode: Reference.**

This report covers issue #881 row 10, a position in an expiring market. It
establishes what the venue publishes, which published market measures bear on
the decision, and what the operator must be able to set. It builds nothing. No
file under `src/` changed.

**FALSIFICATION.** This report is wrong if any cited path or line does not match
the tree it ships on, if a field named absent is read somewhere the search did
not cover, if a measure quoted here departs from its cited source, or if the
recorded market rules change the counts after this date.

---

## What the operator asked for

> This should be a user setting and must be per-bot.

> If we dictate how contracts roll over, people are going to get pissed.

> Can also research, intelligent market-structure and TA-based logic for
> different contract actions.

> Higher timeframe reads would be the most likely place to see a reason for a
> contract expiring or, more bluntly, the market moving against a trade being
> attempting by the platform or user.

Nothing about expiry is platform policy. Every choice belongs to the operator
and lives on the bot. The action itself may come from a reading rather than a
fixed instruction. The last sentence widens the question. An expiring contract
is one reason a position goes against its holder, and it is not the only one.
This report separates the general reading from the expiry-only one, because the
general one earns its place on every sector and the expiry-only one earns it on
dated futures alone.

---

## What the program holds today

Four readings exist and one of them has a reader.

```
src/exchange/base.py:139              expiry_ms, the epoch the venue closes on
src/exchange/base.py:144              expires, True for a finite positive epoch
src/exchange/base.py:155              days_to_expiry, days from a moment to it
src/trading/scrumming/sizing.py:453   venue_variant, which names the market
src/trading/bot_container.py:489      the one reader, and it writes a warning
```

The warning fires on a sale the operator's own chain already decided. Nothing
closes a position on the program's own initiative and nothing rolls one. The
search for either returns no line.

### The recorded rules, read through the program

The recorded market rules hold 1,142 Coinbase markets. One hundred carry a
positive expiry. Driving the real `venue_variant` over all 1,142 answers three
names, and the expiring hundred all answer the same one.

```
none                     816
whole-unit position      226
rolling position         100
```

`variant_permits_close` answers True for that third name, so a sale out of an
expiring market already passes the pre-flight and every purchase into one is
already refused. The close the operator wants is the program starting the sale.

### How far ahead the figure has to reach

Days to expiry over the hundred, read at 2026-10-07:

```
minimum                  12.77 days
median                   78.67 days
maximum              23,095.67 days
at or under   7 days       0 of 100
at or under  30 days      19 of 100
at or under 365 days      71 of 100
```

Twenty-two of the hundred carry a nominal expiry of 2089-12-30. Coinbase
publishes a five-year perpetual-style contract expiring 2030-12-20, and seven of
the hundred carry that date. The 2089 date is what the recorded rules hold and
what the venue published. Its convention is not sourced here, and that gap is
named rather than filled. The platform treats all twenty-two as expiring
markets, so it refuses every purchase into them today.

---

## The availability table

Each row names one input a proposed reading would need. A row reads either where
the program holds it, or what would have to exist.

| Input | Readable today | Where, or what is missing |
|---|---|---|
| the held contract's expiry epoch | yes | `MarketRules.expiry_ms`, `src/exchange/base.py:139` |
| whether the market expires at all | yes | `MarketRules.expires`, `src/exchange/base.py:144` |
| days from now to expiry | yes | `days_to_expiry`, `src/exchange/base.py:155` |
| the held contract's last price | yes | `get_ticker`, `src/exchange/base.py:295` |
| the held contract's candle series | yes | `get_ohlcv`, `src/exchange/base.py:307` |
| a second contract's price or candles | yes, by symbol | both calls take any symbol, and no caller passes a second contract |
| a higher-timeframe direction reading | yes | `weigh_higher_tf_bias`, `src/trading/phantom_balance.py:94` |
| that reading on the order path | yes | `src/trading/scrumming_bot.py:3967`, `src/simulator/back_test.py:1076`, `src/paper/paper_run.py:317` |
| EXPIRING against PERPETUAL | scan only | `src/trading/ata_asset_maps.py:108`, and `MarketRules` carries no such field |
| a contract's 24-hour volume | scan only | `src/trading/ata_asset_maps.py:114`, and `MarketRules` carries none |
| the successor contract's identity | no | the venue publishes no successor field, so a field on `MarketRules` would have to exist |
| open interest | no | no line in `src/`, and the venue does publish it |
| the next contract's open interest | no | the same field, read for a second symbol |
| settlement price | no | no line in `src/`, and the venue does publish it |
| the spot or index reference price | no | no line in `src/`, and the venue publishes `index_price` |
| contract size | no | no line in `src/`, and the trading library carries it unread |
| a weekly higher-timeframe reading on Coinbase | no | `available_timeframes` answers eight names for Coinbase and `1w` is not one |
| a per-bot expiry action, lead time or roll target | no | no line in `src/` for any of the three |

### The control on that table

The same command measured twenty-five names over `src/` and `main.py`. Nine were
expected present and sixteen absent. Every one landed where it was expected, so
the method tells a real field from an invented one.

```
expiry_ms                 14 lines   present
days_to_expiry             3 lines   present
VARIANT_ROLLING_POSITION  10 lines   present
scrum_defer_to_htf        24 lines   present
open_interest              0 lines   absent
successor_symbol           0 lines   absent
expiry_lead_days           0 lines   absent
ZZQQNOTAREALNAME           0 lines   absent
mismatches                 0 of 25
```

A symbol the recording never held reads back unknown rather than empty, which is
the second half of the same control.

### What the venue publishes and the program does not read

Coinbase names seven market readings on a futures product record, and no field
on the order path carries any of them. The record itself reaches the connector,
so the gap is a field and a reader, not a venue call. No successor field appears
in that schema at all.

```
open_interest          contracts still open on this one
settlement_price       the price the venue settled it at
index_price            the spot reference the contract tracks
contract_size          units of the underlying per contract
funding_rate           the rate a perpetual charges
time_to_expiry_ms      the venue's own countdown
contract_expiry_type   EXPIRING or PERPETUAL
```

---

## The established measures

Each measure below carries its published definition and what a reading argues
for. The timeframe named is the one the measure is published on.

### Basis

The regulator defines the basis as the difference between the spot price of a
commodity and the price of the nearest futures contract for the same commodity.
The cost-of-carry relation states it as a formula.

```
F(t,T) - S(t) = Int(t) + w(t) - c(t)

F    the futures price at t for delivery at T
S    the spot price at t
Int  financing or interest cost
w    storage cost
c    convenience yield
```

A positive basis means the contract trades above spot. A negative one means it
trades below. Read on a daily bar, because the basis is a level that moves over
weeks and the shortest window in the recorded hundred is thirteen days.

What it argues for: a wide positive basis close to expiry means the held
contract must fall toward spot. That argues for closing before the fall rather
than holding through it. **Not readable today.** It needs the spot or index
price, which no line in `src/` reads.

### Convergence

The regulator defines convergence as the tendency for the prices of physicals
and futures to approach one another, usually during the delivery month. The
basis therefore shrinks toward zero as expiry arrives.

```
|F(t,T) - S(t)|  ->  0   as t -> T
```

What it argues for: the lead time should place the action before the convergence
window rather than inside it. **Not readable today**, for the same missing input
as the basis.

### Contango and backwardation

The regulator defines contango as a market in which prices in succeeding
delivery months are progressively higher than in the nearest month, and
backwardation as one in which futures prices are progressively lower in the
distant months. Both are readings of the curve across two or more contracts of
one family, priced at the same moment.

```
contango        P(near) < P(far)
backwardation   P(near) > P(far)
```

What it argues for: in contango, rolling forward buys a dearer contract, which
is a cost. In backwardation, rolling forward buys a cheaper one, which is a
credit. This is the measure that argues close against roll. Read on a daily bar,
because the curve is one moment's cross-section and a daily reading removes the
intraday noise from each leg.

**Partly readable.** Both prices are fetchable by symbol today. The successor's
identity is not, so the second leg has no address.

### Roll yield

The measure is the difference between the profit or loss of a futures contract
and the change in the spot price of the underlying.

```
roll yield = futures return - spot return
```

What it argues for: whether a roll is worth making at all.

**The sign rule is disputed and this report does not state one.** The cited
source says the relation between curve shape and the sign of roll yield depends
on the cost-of-carry components rather than following a simple rule. A gate built
on a sign rule would rest on a judgement, not a formula. **Not readable today**
either way, for the same missing spot price.

### Open interest and its migration

Open interest is the total number of contracts still open and not offset by a
closing trade, delivery or exercise. Volume is a flow over a period, and open
interest is a stock at one moment. When open interest falls in an
expiring contract while it rises in a later-dated one, traders are moving
positions forward rather than closing them.

```
front contract    open interest falling
next contract     open interest rising
reading           the roll is under way, liquidity is leaving the front
```

What it argues for: acting before the liquidity leaves. This is the strongest
expiry-only measure, because it says when the exit becomes expensive rather than
only when the contract ends. Read on a daily bar, because end-of-day open
interest is the published series and no intraday one exists.

**Not readable today.** No line in `src/` reads open interest, although the
venue publishes it per contract.

### A higher-timeframe direction reading

The operator's sentence opens this section.

> Higher timeframe reads would be the most likely place to see a reason for a
> contract expiring or, more bluntly, the market moving against a trade being
> attempting by the platform or user.

Multiple-timeframe analysis reads the higher timeframe for the trend and the
lower one for the entry. **There is no single published formula.** The technique
is documented widely and the weighting is each author's own. The platform's own
rank weighting is therefore a house convention and not canon, and this report
does not present it as a formula.

```
the technique     read the higher timeframe for direction
the platform      weigh_higher_tf_bias, src/trading/phantom_balance.py:94
the gate today    htf_blocks_scrum and htf_blocks_fold, all three order paths
```

What it argues for: the general reading the operator describes. A higher
timeframe turning against the held position is a reason to act whatever the
market is, and an expiring contract is one case of it.

**Readable today**, with one bound. Coinbase serves eight granularities and `1w`
is not among them, so the highest reading available on the venue that holds all
one hundred expiring contracts is the daily one.

### Which measures answer which question

| Measure | The general reading | Dated contracts only | Readable today |
|---|---|---|---|
| higher-timeframe direction | yes | no | yes, to `1d` on Coinbase |
| basis | no | yes | no |
| convergence | no | yes | no |
| contango and backwardation | no | yes | partly |
| roll yield | no | yes | no |
| open-interest migration | no | yes | no |

The general reading is the one the platform can already take. Every expiry-only
measure needs a field the order path does not carry.

---

## The project's own indicators

Twenty-four modules sit under `src/trading/indicators`, and the package exports
forty-four names. Each indicator takes one candle series and a timeframe. The
candle carries a timestamp, four prices and a volume, and nothing else.

```
src/trading/indicators/types.py:83
    Candle: timestamp, open, high, low, close, volume
```

Every one of the forty-four signatures was read. None takes a second market's
series, and none takes open interest. The indicators that bear on a direction
reading, and that carry a published author, are these.

```
adx.py          Wilder's ADX and DMI
supertrend.py   an ATR trailing stop
ichimoku.py     Hosoda's Ichimoku Kinko Hyo
macd.py         Appel's moving-average convergence and divergence
bollinger.py    Bollinger's bands
vortex.py       Botes and Siepman's VI+ and VI-
kaufman_er.py   Kaufman's efficiency ratio
```

Those seven serve the general reading on any timeframe the venue offers. **No
indicator in the tree can serve a term-structure reading**, because no indicator
accepts a second contract's series. A basis, a curve or an open-interest
migration reading is a new input shape, not a new indicator over the old one.

### Where the timeframe wiring stops short

A bot carries its own timeframe and two higher-timeframe switches. A third
setting names a timeframe the venue does not serve.

```
ta_timeframe              "1h" by default, per bot
scrum_defer_to_htf        True by default, read on all three order paths
fold_defer_to_htf         True by default, read on all three order paths
detonation_timeframe      "1d" by default, offering "1w"
```

Coinbase serves no weekly candle, so that last setting's `1w` value has nothing
behind it on the venue holding every expiring contract. A bot already set to the
daily timeframe gets no higher-timeframe observer at all there, because nothing
above `1d` is offered.

---

## The three actions

Each action below is **proposed**. Nothing here is built. For each one the table
names what the operator must be able to set.

### Close before expiry

The operator has already chosen this as the default.

| What he sets | Values | Note |
|---|---|---|
| the action | close | the recorded default |
| how far ahead | a figure in days, per bot | the hundred span 12.77 to 23,095 days |
| what close means | the whole position, or stop buying and let the ladder finish | refusing purchases is already the standing behaviour |

The per-bot fields, **proposed, not present**:

```python
expiry_action: str = "close"       # "close", "roll" or "gate"
expiry_lead_days: float = 7.0      # 0 is off
expiry_close_whole: bool = True    # False lets the sell ladder finish
```

### Roll into the next contract

The operator's second sentence governs this one. The platform offers the choice
and does not impose it.

| What he sets | Values | Note |
|---|---|---|
| the action | roll | never imposed |
| how far ahead | the same figure in days | shared with the close action |
| which contract | a target | four candidates, below |

Four targets are possible and each costs something different.

```
the next by expiry in the same family     64 of 100 have a later sibling
a contract the operator names             always available, needs a control
the one with the most open interest       needs a field no line reads
the nearest contract at least N days out  needs the same family grouping
```

**The measured hazard.** Thirty-six of the hundred have no later sibling at all,
so a mechanical roll has nowhere to go for those. For the sixty-four that do,
grouping by symbol root puts the 2089 contract in the same family as the dated
ones, so the next contract after the last dated month is the 2089 one. A target
chosen by date alone lands there.

The roll fields, **proposed, not present**:

```python
expiry_roll_target: str = "next_by_date"   # or "named", or "min_days_out"
expiry_roll_symbol: str = ""               # set when the target is "named"
expiry_roll_min_days: float = 0.0          # set when the target is "min_days_out"
```

### A reading picks between them

The third action lets a gate choose close or roll rather than fixing one.

| What he sets | Values | Note |
|---|---|---|
| the action | gate | |
| how far ahead | a figure in days | when the gate starts being consulted |
| which reading drives it | the direction reading | the only one available today |
| the floor it must clear | a confidence figure | the platform already uses such floors |
| what an abstention means | close, or roll, or hold | an abstention needs a stated answer |

The gate fields, **proposed, not present**:

```python
expiry_gate_confidence_min: float = 0.75   # the floor the reading must clear
expiry_gate_fallback: str = "close"        # when the reading abstains
```

The gate can be built on the direction reading today. It cannot be built on the
basis, the curve, the roll yield or the open-interest migration until the fields
those need exist and have a reader.

---

## The decisions that are his

Four questions remain and each one is a product choice.

| # | The decision |
|---|---|
| 1 | Does close mean selling the whole position in one order, or stopping purchases and letting the existing sell ladder finish? |
| 2 | How many days ahead should the action fire? Among the hundred contracts the nearest is thirteen days out and the farthest is sixty-three years. |
| 3 | Twenty-two of the hundred carry a nominal expiry in 2089, and the platform already refuses every purchase into them. Should a contract that far out count as expiring? |
| 4 | When a bot rolls, which contract is the default target: the next one by date, one he names each time, or the nearest contract at least a set number of days out? |

---

## Recommendations

These are the author's own and are not measured.

The general reading the operator describes is the one worth building first. It
runs on every sector he trades, it already reaches all three order paths, and it
needs no new field. The expiry-only measures are sound and none can be read
today.

Among those, open-interest migration is the one to carry first if any are
carried, because it names the moment the exit becomes expensive rather than the
moment the contract ends, and the venue already publishes it per contract.

The roll target wants a control the operator reaches, not a rule. A target
chosen by date alone lands on the 2089 contract, and that alone is reason to
make the choice his.

---

## Raw evidence

Five readings sit under `raw/` in this directory. Every one was taken with the
home directory redirected before any import, and the recorded market rules were
opened read-only. Absolute paths in the captures are replaced by a placeholder.

```
raw/recorded_rules.txt   the recorded store, its keys and its expiring rows
raw/successor.txt        the family derivation and its control
raw/variant.txt          venue_variant driven over all 1,142 recorded markets
raw/availability.txt     the twenty-five-name search and its control
raw/timeframes.txt       the venue's granularities and the indicator signatures
```

---

## Sources

- [CFTC glossary](https://www.cftc.gov/LearnAndProtect/EducationCenter/CFTCGlossary/index.htm)
  for contango, backwardation, basis, convergence and cost of carry.
- [Contango](https://en.wikipedia.org/wiki/Contango) for the cost-of-carry
  formula and the convergence statement.
- [Roll yield](https://en.wikipedia.org/wiki/Roll_yield) for the definition, and
  for the statement that the sign relation is not a simple rule.
- [Open interest](https://en.wikipedia.org/wiki/Open_interest) for the
  definition and the migration reading.
- [Coinbase list products](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/list-products)
  for the futures product fields, and for the absence of a successor field.
- [Coinbase perpetual futures](https://docs.cdp.coinbase.com/coinbase-business/advanced-trade-apis/guides/perpetual)
  for the two contract expiry types.

CME Group publishes its own pages on contango, open interest and roll yield.
Every request to that host from this machine answered HTTP 403, so none is cited
here.
