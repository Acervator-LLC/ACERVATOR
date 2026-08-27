# ACERVATOR DEPARTMENT LEAD REVIEW
**Acervator v3.12.0 · SADP v1.14 · Session 18 · 2026-04-20**
**First pass under the new Department Leads framework.**

Context: ten Department Leads (see `sadp/DEPARTMENT_LEADS.md`) reviewed
the current trading logic, indicator set, risk model, and execution
discipline of Acervator v3.12.0. What follows is each Lead's verdict,
voiced as their archetype would frame it, grounded in what the code
actually does.

---

## Code surface audited

- **Indicators in live decision-making**: Bollinger Bands only (`bb_pos`,
  z-score). Volume is logged but not used in signals.
- **Trade triggers**: `bb_pos < 0.20 AND Δ < 0 → FOLD (buy)`,
  `bb_pos > 0.80 AND Δ > 0 → SCRUM (sell)`. Fixed ±2% delta threshold.
- **Position sizing**: Fixed USD allocation per bot (target_usd = 200),
  not volatility-adjusted.
- **Risk model**: R43 Fee Guard (won't trade if profit ≤ fee),
  R55 VH v3 (verify-hit slippage tolerance per asset class).
- **Present**: Sharpe ratio, Calmar ratio, max-drawdown reporting.
- **Absent from decision path**: RSI, ADX, ATR, Stochastic, MACD,
  volume-price analysis, trend filter, multi-timeframe, regime detector,
  Wyckoff phase ID, Elliott wave, correlation exposure, portfolio heat.

---

## Verdicts

### 1. Richard Wyckoff — "You named it, but you didn't build it"

You named the platform after my method. I opened the source expecting
to find Composite Operator analysis, phase diagrams, volume-price
footprints. Instead I found a Bollinger Band fader with my vocabulary
pasted on top.

Your "accumulation" means `bb_pos < 0.20 AND price moved down`. That
is not accumulation. That is fading volatility. True accumulation is
a structural phenomenon with specific observable events in sequence:
Preliminary Support, Selling Climax, Automatic Rally, Secondary Test,
the Spring, the Test of the Spring, Sign of Strength, Last Point of
Support. Each has a specific volume-price signature. Your bots at
`bb_pos=0.19` are just as likely to be buying into Phase D distribution
disguised as accumulation as they are to be buying a legitimate test
of support.

Volume is the footprint of the Composite Operator. I see `volume_24h`
tracked in `reconciliation.py` for display, but it drives nothing in
the decision path. This is like looking at weather radar without
watching the rain. **Volume-price discrimination is the single biggest
missing layer.**

**Verdict**: *Fails a Wyckoff review.* Rename or rebuild.

---

### 2. John Bollinger — "You're using my tool the wrong way"

You are using my bands. That I appreciate. You are using them the
way I spent three decades warning people not to.

A band-position trigger without independent confirmation is the
single most common misuse of this tool. I wrote it in the book: bands
are half a system. The other half is confirmation — from a
non-correlated indicator like RSI, volume, or order-flow imbalance.
Your `bb_pos < 0.20` → BUY fires on nothing else. A fade without
confirmation is a coin flip.

Further omissions: %b isn't tracked explicitly (your `bb_pos` is
close but not calibrated the same way). Bandwidth isn't tracked at
all. Bandwidth at multi-period lows (a BB squeeze) is the single
best pre-breakout signal bands produce — and it's exactly when your
MR engine should STAND ASIDE, because a squeeze precedes an
explosive directional move. Your bots would be fading right into it.

And the W-Bottom and M-Top patterns — which are what bands were
really designed to reveal — don't exist in your code.

**Verdict**: *Using bands correctly = bands + %b + bandwidth +
confirmation + structural patterns.* You have bands. Fix the other
four.

---

### 3. Linda Raschke — "MR in all weather is malpractice"

Mean reversion has preconditions. Low ADX. Narrow-range days.
Mean-reverting volatility. These are not nice-to-haves; they are
the difference between a strategy with edge and a strategy that
hands money to whoever's on the other side.

You are trading MR in every market regime. In a trend day, your
bot scrums at `bb_pos=0.80` on what turns into a `+15%` continuation,
then folds at `bb_pos=0.20` on what continues to `-25%`. This is
textbook MR-in-trend bleed.

R56 ABV suggests you've thought about regime sensitivity. But the
MR engine doesn't GATE on regime — regime influences reporting, not
trades. That's backwards. ADX should gate entry: below 20, MR is
active; above 25, MR stands aside.

And the Anti setup — where a counter-trend pattern signals trend
CHANGE rather than reversion — is absent. You cannot distinguish
"fade this pullback" from "this pullback is the end of the trend."
Those require opposite trades.

**Verdict**: *You have an MR engine; you don't have MR discipline.*
Add regime gating before the next capital deployment.

---

### 4. J. Welles Wilder — "Your thresholds are arithmetic; markets are geometric"

A `2%` move is not a `2%` move. In low-volatility bonds, a 2% move
is a regime shift. In high-volatility oil, 2% is a normal afternoon.
Your engine treats them identically.

ATR exists for exactly this reason. I invented it in 1978. Position
size should be `ATR-normalized`: risk a fixed dollar amount per
trade, divide by ATR-per-asset, that's your size. Stops should be
ATR-multiples, never fixed percentages. Scrum/fold thresholds should
be ATR-referenced — say, `0.5 × ATR` — not fixed at `2%`.

You cite per-asset-class tolerances in R55 VH v3 (crypto 4%, meme
4%, equity 2%, ETF 1.5%, bond 1%). That's progress — someone
recognized the problem — but it's a step function, not a smooth
volatility adjustment. ATR handles this natively without needing a
classification table.

ADX tells you whether to be trading MR or trend-following in the
first place. RSI gives you the confirmation John was asking for.
Parabolic SAR gives you trailing stops that adapt to volatility.
DMI gives you direction with strength.

**Verdict**: *You're using 1980 tools in 2026.* I gave you an
upgrade path in 1978. Take it.

---

### 5. Nassim Nicholas Taleb — "Your backtest is the map; markets are the territory"

Bollinger Bands assume normality. Markets live in Extremistan. A
"2-standard-deviation" event in Gaussian-land is a 2.3% occurrence.
In real markets, it happens 5-10% of the time — sometimes more
during regime transitions. When it happens three standard deviations
out, you are not seeing a rare event; you are seeing a regime
change.

Your engine buys the lower band. This has a very specific failure
mode: in October 1987, August 1998, September 2008, March 2020,
"price at the lower band" meant "price is going MUCH further down
in the next several hours." Your MR bots would have been obliterated.
Your fee guard won't save you — you can cross into massive negative
territory inside a single bar.

Where is the left-tail circuit breaker? Where is the vol-regime
change detector that says "stop trading, the world just changed"?
Your backtesting at 63 × 6 = 378 combinations — are those 378
independent regimes, or 378 samples of the 2017–2023 post-ZIRP era?

Anti-fragility is philosophically aligned with your R28 FL. But
R28 FL is about telemetry. It's not about exposure. You can surface
a loud failure and still have already blown up.

**Verdict**: *Your system will work until the first time it doesn't,
and then it will work never again.* Add tail exposure management
before scale.

---

### 6. Ed Seykota — "You cut winners. You ride losers. This is backwards"

The trend is your friend. Your engine is its enemy.

A bot that scrums at `+2%` exits every trend-continuation at the
first pullback. A bot that folds at `-2%` buys into every trend-
down that continues. You are systematically cutting winners short
and adding to losers — the opposite of every durable trading
discipline.

Where is the higher-timeframe trend filter? Above the 200-period
MA on the daily: only long-side MR. Below: only short-side MR, or
stand aside. This is not optional in modern systematic trading.

Auto-scaling by CPU/RSS load — interesting engineering, but has
nothing to do with market conditions. You should be scaling up
when market volatility matches your strategy's preconditions, not
when your computer has spare cycles.

**Verdict**: *You built a counter-trend bleed machine.* A trend
filter is one function call away from fixing the class of error.

---

### 7. Paul Tudor Jones — "Your risk model is 'hope'"

Fixed $200 per bot, symmetric ±2% triggers, 15 bots running — I
can't find the risk model. What's your risk per trade? What's your
risk per bot? What's your total portfolio heat at full scale?

The scrum/fold is symmetric: `+2%` exit and `-2%` re-entry. That
is 1:1 reward-to-risk. After fees, that needs a 50%+ win rate
just to break even. Do you have 50%+ win rate? Have you measured?
Bulkowski will want this question answered.

Asymmetry is non-negotiable in my book. Minimum 3:1 reward-to-risk,
preferably 5:1. Cut losers at half-R, let winners run to 3R+. You
have the opposite: symmetric thresholds with a psychological bias
toward the mean.

And I always assume my position is wrong. Your bots, by design,
have no such humility — `bb_pos < 0.20` always means BUY with full
conviction. Where's the sizing based on confidence? Where's the
correlation check — could 15 bots on different assets actually be
one macro bet in 15 costumes?

**Verdict**: *A trader without risk discipline is a donor.*
Position sizing and R:R asymmetry are the fixes.

---

### 8. Thomas Bulkowski — "Without measurement it's superstition"

What is the documented edge-per-trade of the BB MR strategy in
Acervator? Not impressions, not simulator anecdotes — measured,
out-of-sample, across regimes.

Win rate per regime? Average win? Average loss? Profit factor?
Expectancy per trade? I don't see these computed anywhere in the
analytics engine. You have Sharpe and Calmar — those are
aggregate measures after the fact. They don't tell you whether
the underlying edge is real.

Your 63 assets × 6 periods setup is a start. But periods that span
2020–2024 are mostly the same macro regime. Walk-forward with
purged cross-validation across genuinely different market regimes
(2008 crisis, 2013 bull, 2015-2016 range, 2020 covid, 2022 drawdown)
is what separates strategy discovery from curve-fitting.

**Verdict**: *Every feature lands without empirical edge proof.*
Measurement should precede deployment, not follow it.

---

### 9. Alexander Elder — "One screen is gambling"

You trade on one timeframe — the trigger timeframe. Triple Screen
demands three: higher (tide), medium (wave), lower (ripple). A
lower-TF MR trade that fights the higher-TF tide is statistically
unfavorable regardless of bb_pos.

Where is your tide? Your wave?

Force Index, Elder-Ray — bull/bear power divergences — absent.
These are the confirmation tools Bollinger was asking for, from a
different angle.

Psychologically: your auto-scaling is based on CPU load. This is
an architectural tell. The system that scales up for market
conditions is a system aligned with its purpose. The system that
scales up for compute headroom is a system that's forgotten what
it's for.

**Verdict**: *Correct the timeframe blindness before adding any
more indicators.* More indicators on one screen are still one
screen.

---

### 10. Jesse Livermore — "You're playing checkers, markets are chess"

Listen. Markets don't move because an indicator flashes. They move
because enough buyers outweighed enough sellers, or vice versa. Your
bots fire on mechanical triggers without regard to what the market
is actually trying to do.

What is the line of least resistance right now? Is the market trying
to go up, down, or sideways? Your engine doesn't ask. It just reads
an oscillator and pulls the trigger.

Pyramiding: the best idea gets more capital, the bad one gets cut.
Your 15 bots all carry the same stake regardless of performance.
The winning bot should be scaled up; the losing bot should be shut
off. You have neither feedback loop.

And speculation — which is what this is — requires conviction.
Mechanical conviction from a statistical table I can respect. Your
engine has neither real statistical table (Bulkowski covered that)
nor conviction signal.

**Verdict**: *Feel the market's intent before firing at the chart.*

---

## Synthesis — patterns across all ten verdicts

Five themes keep surfacing across Leads who never met each other:

**1. Single-indicator trigger is consensus malpractice.**
Bollinger, Wilder, Elder, Raschke, Livermore each call it out from
different angles. An independent confirmation layer is the minimum
upgrade. RSI + volume + ADX are the three most-cited.

**2. No regime awareness.**
Raschke, Seykota, Taleb, Elder all name this. The engine fires the
same trades in trend, range, volatility regime, and crisis. The
exit from this is ADX + higher-TF trend filter at a minimum.

**3. Fixed thresholds where volatility lives.**
Wilder names this explicitly. Fixed ±2% in a system that covers
crypto, meme stocks, bonds, and ETFs is arithmetic where geometry
belongs. ATR normalization is the fix.

**4. No tail discipline.**
Taleb and Tudor Jones both name this. The system optimizes the
middle. The middle is not where capital dies. Left-tail circuit
breakers are the minimum. Regime-transition detection is the next
level.

**5. No measured edge.**
Bulkowski is loudest here; Tudor Jones seconds it. No feature
should ship without a measured edge, out-of-sample, across regimes.
Sharpe-after-the-fact is not edge-before-the-bet.

---

## Candidate rules that fall out

These are not being formalized this turn. They're the rule-shaped
objects that surfaced during this review, which future SADP turns
should consider.

- **R60 candidate — "Indicator Confirmation Requirement"**: No single
  indicator triggers a trade. Every signal requires confirmation from
  a non-correlated second indicator. (Bollinger's demand, seconded by
  Elder, Wilder, Raschke.)

- **R61 candidate — "Regime Gating"**: Trading logic must consult a
  regime classifier (ADX or equivalent) and can be gated off in
  unsuitable regimes. (Raschke, Seykota, Elder.)

- **R62 candidate — "Volatility-Normalized Thresholds"**: All fixed
  percentage thresholds must be replaced with volatility-relative
  thresholds (ATR-multiples or equivalent) before v4. (Wilder.)

- **R63 candidate — "Tail Circuit Breaker"**: System must detect
  regime-transition volatility and suspend MR trading. Must have a
  kill-switch for drawdown > N%. (Taleb, Tudor Jones.)

- **R64 candidate — "Edge-Before-Deploy"**: No trading feature ships
  without measured edge in out-of-sample walk-forward testing across
  at least 3 distinct market regimes. (Bulkowski, Tudor Jones.)

- **R65 candidate — "Multi-Timeframe Confirmation"**: MR trades must
  check higher-TF trend; trades against the higher-TF tide require
  explicit override or are disallowed. (Elder, Seykota.)

- **R66 candidate — "Position-Size Risk Parity"**: Fixed-$ allocation
  per bot replaced with volatility-targeting or Kelly-fractional.
  (Tudor Jones, Wilder, Livermore.)

Six of the ten Leads would consider the current v3.12.0 a work-in-
progress toward a system they'd endorse. Four (Wyckoff, Bollinger,
Taleb, Tudor Jones) would not trust capital to it in its current
form. That four-of-ten "not yet" is not a failing — it's an honest
read of where the codebase is in its maturity curve.

---

## Recommended next actions (if appetite)

The cheapest wins, ordered by cost-benefit:

1. **Trend filter** (one function, ~30 lines). Higher-TF moving average
   gate on MR trades. Answers Seykota, Elder, partially Raschke.
2. **ADX regime gate** (one new indicator, ~40 lines). Turn MR off
   when ADX > 25. Answers Raschke, Wilder, Taleb partially.
3. **ATR-normalized thresholds** (refactor of scrum/fold trigger
   logic). Replaces fixed 2% with `ATR × multiplier`. Answers Wilder
   completely, Taleb partially.
4. **Volume confirmation** (on existing `volume_24h` data — just
   gate signals on above-average volume). Answers Bollinger partially,
   Wyckoff partially.
5. **Drawdown kill-switch** (analytics → circuit breaker). Answers
   Taleb, Tudor Jones.
6. **Walk-forward harness** (tooling, significant work). Answers
   Bulkowski.

Wyckoff-level fixes (phase identification, volume-price analysis as
decision driver, composite operator tracking) are a larger project
— reasonable to defer until the simpler layers are in place.

---

## Final note

These Leads are archetypes — voiced to carry the weight of the
standards their real counterparts established. The critiques are
meant to sharpen, not embarrass. Acervator is still early in its
development; none of these Leads expected a v3.12.0 to match the
standards of a system at trading maturity. What they expected, and
what this review documents, is that the standards exist, are
legitimate, and are worth aiming at.

That aiming is the augment.
