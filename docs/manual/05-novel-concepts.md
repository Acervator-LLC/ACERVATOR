# Novel Concepts and Patent Candidate Catalogue

Active development on Acervator began in early April of 2026. It began after realizing that the AI-assisted software development tools had achieved an inflection point with their capabilities. Prior to this, efforts were being made to learn traditional coding with little success that was mainly due to an inability to get into a grinding effort for whatever reasons. This has been particularly frustrating since other subjects seem to grab and others deflect. With the advent of Claude Code however, it feels like some of us have been given a decently priced door man and well-informed guide through this and other labyrinths.

Each entry below carries an anchor: the module and the symbol that run it
today. Where a concept has no code, the anchor says so and gives the query
that measured the absence. Anchors describe the present state of the
platform, not the plan.

## 1 - Harvest-Fold / Scrumming

At the core of Acervator is what might not first appear as a multi-faceted concept designed to address or alleviate many of the mental pitfalls that can afflict a new trader. After having observed a number of people via Telegram and web approach the challenge of investment differently, I have come away convinced that all it only becomes as complex as the individual allows it to be. This is not to be reductive about economics or any other connected discipline but it is to say there are reliable, stable, consistent means of reading price charts and too many people are simply doing it too many different ways and this only compounds the complexity illusion further. Much of the uneasiness inflicted on the new trader surrounds the emotional desire or even personal need for the value of their positions to increase as soon as possible or show the midterm potential of becoming profitable. Those that adopt the HODL meme are, in my experience, quite crippled in their ability to sell positions even when the time is right, which is usually when most people are happiest about the market. The ironic truth is that however good a trade is, there is an equally bad one on the other side of it. Acervator attempts to respect the market by not taking profit all at once and absorbing or claiming ownership of its positions’ variance strictly based on the market local, organic price ranges. In other words, its trade actions are always proportionate to whatever the market is actually doing at the time the trade is executed. Over time, this ‘molds’ the position to the long term truth of the market and avoids the need to speculate entirely. The more bold hope for this approach is that it might add another tool for stabilizing macro-economic phenomena such as underpinning currency exchange rates between countries.

Acervator addresses ‘fundamental market unpredictability’ by allowing volatility to “orbit” around a set point we call the Target Balance. This element is what performs the first mental trick. It forces the trader to say and establish that “my position is worth X and I will support X with an equal amount of liquidity” i.e. a Target Balance of $50 is set and a total mental position of $100 is established. Trades will be executed to maintain the truth of the Target Balance always being X. After the initial entry is executed and filled, which Acervator will only do in the lower extent of the Bollinger Band on the chosen timeframe, the Scrumming Bot will persistently shave off and “Fold” back in Y% of profits through repeating Harvest-Fold operations that continue until the bot is deactivated or the market suffers a catastrophic collapse which can and do happen so don’t not leave it unmonitored. It should also be noted that the term ‘harvest’ came to replace ‘scrum’ for the sake of clarity but they may be used interchangeably throughout this text. Essentially a Scrum or Harvest is a sale of a position’s increased value over the Target Balance. The amount that the Scrumming Bot harvests or folds is pinned to the Target Delta or the amount of variation (%delta) from the most recent trade event. Much of the finer details of trade execution can be tuned by the user as expected for any professional application but the primary point here is that the amount of profit folded back is capped by the Maximum Target Growth Per Cycle setting while the ability of Acervator to prevent inverted (profit losing: buying higher than sold / selling lower than bought) trades we also have the Minimum Opposing Trade Distance rule which dictates the next trade must be Z distance from the most recent trade event. In addition, sells are not allowed to occur or be pushed below the Bollinger Band midline while buys are not allowed to occur or be pushed above the midline. As a result of just these few component features, we already have multiple soft, non-TA or non-traditional rules protecting the investor before we even start optimizing the trades themselves (pushing them as close to volatility extents as possible) via Technical Analysis and other inventions.

The harvest-fold method itself was manually executed and tested on a multiple cryptocurrency pairs throughout 2023~2026 but it has always been the aspiration to automate it and have it executed at a high rate of frequency with the operating theory that this approach to investment, being a hybrid a HODL and active trading, creates frontline area of support for whatever markets in which it participates long term. It does this by maintaining and, utilizing as directed, all earned profits. It turns any user into an active participant and liquidity provider.

After entering the space full time in 2017, I immediately began to parse and breakdown how price charts were being interpreted. This also allowed me to perform ever deeper introspections on my own response to how my mind was responding to the value of my portfolio fluctuating. I did myself absolutely no psychological favors in this pursuit but, as you will see, I had plenty of reasons to take this reckless approach. By this point, my undiagnosed and untreated military injuries had worn me down to the point where I realized I was running out of time to continue working as normal. I had, by then, been walking a torsioned pelvis for 17 years that had seized in place and, by 2020, would be causing enough pain to induce panic attacks. I could have joined the pill-mill club but I declined. In combination with the pain, the forced TA self-training, physical job, and broken marriage, I also assembled an entire GPU-based mining farm…alone. I had some business partners but their participation was basically nonexistent. The VA was providing no support and would not until 2022. The Navy and Pentagon had spit in my face by sending me PDBR paperwork that they had no intention of ever honoring no matter what I wrote down. My family more or less remained ignorant of all my turmoil while I kept the paychecks coming. So really the story of Acervator’s and Harvest-Fold is one of betrayal to a degree that allowed me to see through things more clearly than would otherwise have been possible. It has been invented out of necessity and it is my intuition that Acervator can become that necessary tool for other people as well.

`ScrummingBot` in `src/trading/scrumming_bot.py` holds the method.
`ScrummingBot.tick` runs one cycle. `TickPhaseMixin._tick_execute_scrum` and
`_tick_execute_fold` in `src/trading/scrumming/tick_phases.py` fire the two
halves, and `ExecutionEngineMixin._execute_sell` and `_execute_buy` in
`src/trading/scrumming/execution.py` place the orders.

- **Target Balance** is `BotConfig.target_balance` in
  `src/trading/container/config.py`. **Target Delta** is the drift from it.
  `target_territory` in `src/trading/target_bands.py` names the side, and
  `at_target_dust_band` sets the no-op band. At a target of $50 the dust band
  measures $0.05; a position at $60 answers `scrum` and one at $40 answers
  `fold`.
- **Maximum Target Growth Per Cycle** is `max_target_growth_pct`, 1.0 by
  default. `ScrummingBot.cycle_growth_cap_usd` turns it into a dollar cap and
  `_apply_fold_target_growth` applies it. The same key falls back to 0.0 at
  four sites and 1.0 at five, which issue #409 records.
- **Minimum Opposing Trade Distance** is
  `minimum_opposing_trade_distance_pct` in `src/trading/otd_math.py`. It adds
  the scrumming interval to the trading fee and clamps the sum. A 1.00%
  interval with a 0.60% fee measures 1.60%. `HysteresisGate` in
  `src/trading/gate_chain.py` then refuses the trade until price travels that
  far from the pivot.
- **The midline rule** lives in `ScrummingBot.tick`, which sets `scrum_ok`
  from `bb_pos > 0.50` and `fold_ok_midline` from `bb_pos < 0.50`.
  `MidlineGate` refuses the wrong side of the band.

`gate_vocabulary.py` names the whole gate set the bot writes: ten scrum
labels and nine fold labels, nineteen lights per bot.

## 2 - The Phantom Bot

While the Harvest-Fold method housed with the Scrumming Bot addresses several persistent and nagging questions around any given investment position (Should I buy more? Should I sell some? When? How much?), it does have the weakness of operating on a single timeframe. The Phantom Bot is another feature intended to optimize trade execution position. In this specific case, it allows a single Scrumming Bot to be inhibited by a higher timeframe signal with the intention of capturing alignments or disagreements so that trades are not being executed prematurely. The design intention here is that, for example, a 5m TF bot can be inhibited by a 15m, 30m or 1hr signal while maintaining a volatility watch on its primary TF. The intention is to build out this feature so that it obviates or reduces the need for multi-screen monitoring of individual assets.

`PhantomBalanceBot` in `src/trading/phantom_balance.py` runs. Its `_tick`
computes TA on one timeframe and stores the result on `last_summary`. It
constructs no order. `TimeframeCoordinator.get_higher_tf_bias` weights those
summaries by `tf_rank`, and `HTFDeferGate` in
`src/trading/gate_chain.py` turns a higher-timeframe bias into a block: a
bullish higher timeframe stops the scrum and writes `HTF-bullish`, a bearish
one stops the fold and writes `HTF-bearish`. That is the inhibition the entry
describes, and it runs today.
`PhantomBalanceManager.create_phantom_set` builds one phantom per timeframe,
and `ScrummingBot.update_phantom_config` and `get_phantom_statuses` are the
parent bot's side of it.

Three parts of the feature do not work. `TimeframeCoordinator.create_lock`
has no caller, so `is_locked` always answers False (issue #398). Every P&L
figure on the Phantom Bots tab prints `$+0.0000`, because the key the tab
reads is never written (issue #197). The tab draws a refused change as a
success and can drop a timeframe (issue #313). Issue #155 tracks the
remaining build-out. Multi-screen replacement is an intention, not current
behaviour.

## 3 - The Landing Strip

Perhaps the earliest assumption that hit me the most and really presented the catalyzing challenge to creating all of my alternate trading methods, is that you cannot predict what the market will do and after only a short while of actively trading I asked the questions: “But what if I don’t have to?” “What if I decide that I do not have to speculate at all?” I do not remember exactly when I first used the term but I think it was when I was trading ADA and XLM some years ago while participating in a Telegram group with some psytrance friends and associations called the Better Bitcoin Bureau. The name changed a few times but this is the one I recall.

The concept emerged from my persistent use of Heikin-Aishii candles. I had decided on this candle style early just by intuition. I could say it was because I “felt it looked nicer” but that does not quite capture the magnetism. To me, they just structurally make more sense and are less sloppy than traditional candles. What I began to observe over and over was the propensity for crypto markets to form long, tapering structures from these candles and that the likelihood of market reversal could be pinned to 1) the landing strip length and 2) its proximity to the Bollinger Band. Further, I found that those markets that formed these on 1D or higher timeframes would often have explosive breakouts like a volcano that had charged up to blow out. These findings can be historically verified and back tested. I manually performed this observation all the way down to 1 minute trading and found that it was only at this lowest TF that it started to exhibit sub-50% reliability. Given this, the concept has been transposed into Acervator as a core component and trading logic gate with the number of candle strip candles being a user configurable setting.

This is also where I should mention that I am not at all a quant or mathematical trader. I consider myself a visual or tactical trader that focuses on market reversals. I have taught myself to visually interpret price chart structure using a given set of indicators used by countless other technical analysts. When looking at some of the labeling within Acervator, however, one will readily see military references and hints at how I view asset accumulation as something akin to progressive territory capture on a perpetual gameboard. The less skilled traders are surrendering it with every cycle of the market.

Two detectors build the Landing Strip, and both run on every tick.

`detect_bb_proximity` in `src/trading/indicators/bb_proximity.py` is the
first. It places price inside the Bollinger channel and counts trailing
Heikin Ashi bodies under a tightness threshold. It reads the operator's
setting: `ScrummingBot.tick` passes `config.bb_landing_strip_candles` as
`min_pattern_candles`.

`detect_landing_strip_v2` in `src/trading/indicators/landing_strip.py` is the
second. It counts a run of shrinking Heikin Ashi bodies, names the band the
run reached, and returns a `confidence_boost`. `compute_heikin_ashi` in
`src/trading/indicators/heikin_ashi.py` supplies the candle transform. On a
tapering rally into the upper band it answers `detected=True`, `side="upper"`,
`length=3`, `confidence_boost=0.1437`. The same tape without the taper answers
`detected=False`, and a five-candle tape answers `detected=False`.
`ScrummingBot.tick` adds the boost to `bb_confidence_boost` and lets the strip
force a direction, which is why `gate_vocabulary.py` marks `LS` an override
rather than a gate.

The second detector does not read the setting. `ScrummingBot.tick` passes
`min_consecutive=3` to it as a literal, so the wizard's Landing Strip Candles
control moves the first detector and leaves the second at three. Both
defaults sit at three, so the two agree until the operator changes the
control. Issue #432 carries it.

## 4 - Bollinger Band Travel Detection

Allowing a strategy to “see” where it is in relation to local width of the Bollinger Band is another aspect of treating the immediate market as a region on a map through which a stack of tokens is traveling. Along the route, we are able to offload surplus at the peaks and pick up additional supplies in the next valley. This is used in combination with Minimum Opposing Trade Distance. The complete question then becomes “Has the market traveled 70% (default), is current price X% distant from the most recent trade event, and is Target Delta not zero? When combining these gates with the (Technical Analysis) Indicator Voting Panel and Landing Strip Detection, you have a full market structure detection suite that is able to incrementally adjust a position’s size and generate recurring profits or growth with each market cycle.

`ScrummingBot.tick` measures the travel. It divides the distance from the last
trade price by the Bollinger band width, holds the result in
`band_travel_frac`, and sets `band_travel_triggered` when the distance reaches
`config.band_travel_pct / 100` of the width **and** the Target Delta is
positive. `band_travel_pct` starts at 70 in
`src/trading/container/config.py`, and the wizard offers 0 to 100. That is the
compound question the entry states, and the code asks it in one expression.

The flag then feeds `trend_override`, which clears a standing `trend_hold` and
lets the scrum through. Band travel releases a harvest that a strong-trend
hold would otherwise keep. Travel is no gate of its own: the ten scrum labels
in `gate_vocabulary.py` carry no travel light. `BollingerBands` in
`src/trading/indicators/bollinger.py` supplies the band it measures against.

## 5 - Position-Aware Technical Analysis

Traditional TA treats a signal (e.g., RSI > 70) as context-independent. Position-Aware TA encodes the current Bollinger Band position as context: RSI > 70 near the upper band confirms overbought (sell bias), but RSI > 70 near the lower band is a failed oversold — a trap for mean-reversion buyers. The system applies this inversion systematically across all oscillator signals. In other words, it attempts to strengthen the price to Bollinger Band relationship by reading additional indicators with relation to it. If you have the landing strip, band travel, opposing trade distance, and a bullish or bearish confidence score from the Indicator Voting Panel, it is likely a trading event will occur. In the end, many of these functions were layered in one after the other until I saw the platform take most trades that I would myself manually execute most of the time.

The band context enters at the bot, not inside the voters.
`ScrummingBot.tick` reads `bb_position` from the Bollinger voter, sets
`at_upper_bb` from `bb_pos > 0.75` and `in_bb_middle` from
`0.35 <= bb_pos <= 0.65`, and accumulates a `position_boost`. Two voters take
a band term: a bullish vortex adds 0.12 at the upper band and subtracts 0.05
in the middle, and a bullish MACD adds 0.08 and subtracts 0.03 on the same
test. Ichimoku and Stochastic RSI move the boost on direction alone, with no
band term. `_skewed_confidence_floor` then relaxes the TA confidence floor by
the total skew: a floor of 0.30 becomes 0.2679 at a skew of +0.12 and 0.3158
at a skew of −0.05, and a skew of −1.0 returns infinity, which no confidence
can clear.

The inversion does not reach the oscillator modules. Each indicator computes
from candles alone, and `bb_position` appears in six indicator modules only:
`bollinger.py`, `bb_proximity.py`, `landing_strip.py`, `m_top.py`,
`spring.py` and `w_bottom.py`. Neither `rsi.py` nor `stochastic_rsi.py` takes
a band argument. Today the band context re-weights the vote after the fact; it
does not re-read the oscillator.

## 6 - Market Inspector

This addition was, like the Phantom Bot above, a move towards making Acervator “hyper-vigilant” of hypothetical opportunities that take the form of oppositional trades (assets that move inversely to one another) and bot swarm network topologies. The bot swarm itself will be covered in a moment but basically this feature allows for the creation of custom capital reinforcement networks where profits are configured to flow between positions in a manner that can potentially strengthen a portfolio faster than just focusing on single, isolated bot instances.

The Market Inspector is designed to analyze the broader market for groups of assets from which to build topologies and identify non-active assets that could be traded in opposition to active positions. Its findings can be pushed to the Simulator for historical back testing, to the Paper Trader for live market and real time validation, and, of course, Live Trading should the user choose to do so.

`MarketInspector` in `src/trading/market_inspector.py` runs the scan.
`scan_universe` walks daily, weekly and monthly candles, scores each market
through `_score_market`, and keeps the result on `last_signals`.
`_find_opposing_pairs` pairs a long-signal market with a short-signal market
when `_pearson` over a rolling return window makes them negatively
correlated. `get_shared_inspector` is the one instance; `src/gui/main_window.py`
and `src/gui/main_tabs/market_inspector_surface.py` reach it.
`detect_all_topologies` in `src/trading/topology_proposals.py` turns those
signals into swarm proposals, with `_make_bot_entry` and `_make_wire` writing
the bots and the wires.

One push target exists. `_build_simulator_tab` in
`src/gui/main_tabs/simulator_tab.py` calls `set_topology_getter`, so the
Simulator reads the current proposals. No Paper Trader exists to push to; entry
17 gives the measurement. Issue #23 tracks the tab's build-out, issue #18 the
topology and oppositional pushes, and issue #290 a live connector defect on
Refresh.

## 7 - Bot Swarm and Smart Wire Network w/ Provenance Tracking

The Bot Swarm, which is how I presented the concept to Claude, is my version of a capital reinforcement network. At the Exchange level (swarms cannot be connected across multi-API boundaries) profit from individual bots can be routed to others with such outputs being termed Wire Credits since they are sent and received along Smart Wires which connect the bots. Each such wire can have its own flow rate. The network nodes are designed to protect a given bot from excessive outflows which would cripple its own growth capacity. The other piece of this is that Wire Credits are Provenance tracked which allows outflows to eventually start sending profits back to the originating bot with the over-arcing philosophy being long-term investment with accumulation and position strengthening rather than just sitting around waiting for a good outcome that might not arrive.

In combination with the Market Inspector, the Bot Swarm can receive and deploy groups of pre-configured and pre-connected bot clusters that immediately begin participating in the market. This layer, along with future portfolio-level algorithms, will enable the fully automated and persistent execution of complex trading strategies from a single terminal window.

`SmartWireManager` in `src/trading/smart_wire.py` holds the topology and one
`BotLedger` for each bot. `register_wire` records a source, a target and a
flow percentage; `bot_container.py` calls it. `distribute_fold_profit` moves
the share on a realised fold, and `tick_phases.py` calls that on the bot's
own tick. `compute_safe_outflow_pct` caps the outflow so a funder keeps its
own growth capacity: a 10 dollar scrum profit against a 100 dollar target
releases 90.0 percent, and a zero profit releases 0.0.

Provenance runs. `BotLedger.provenance` maps each funder id to the amount it
supplied, `predominant_source` returns the largest non-seed funder, and
`primary_provenance_starting_balance` reads it back. `WireRoutingMixin` in
`src/trading/scrumming/wire_routing.py` writes a `wire_credits` entry onto the
tranche a credit lands in. `_WIRE_CREDIT_CAP` holds twenty detail entries per
tranche and `_roll_wire_credit_overflow` folds the rest into
`wire_credits_rolled`, which keeps the totals exact.

One routing path is dead. `process_wires` and `execute_spawn_wire` have no
caller anywhere in the repository. An `ast.Call` sweep over every Python file
found zero for each, while the same sweep found 23 call sites for
`distribute_fold_profit` and 28 for `register_wire`. The module docstring
states the same. Issue #404 carries it. Issue #239 carries the Bot Swarm tab's
live rows. Deploying a pre-connected cluster from the Market Inspector is an
intention.

## 8 - Hunger and Satiety Indices

These elements were implemented as part of an effort to boost accumulation and scrumming performance in longer term bearish or bullish conditions that might not latch all logic gates to trigger a fold or scrum despite the Target Delta not being zero. This piece adds a factor to the bot that makes it more aggressively evaluate subsequent candles and will increase its likelihood of executing the re-zeroing action. This allows for trades to be executed in the hypothetical ‘dead zone’ between Minimum Opposing Trade Distance and the lower or upper Bollinger Band extent if the candle structure begins to float or cruise within it for too long.

Neither index exists in code. A token sweep over every Python file in the
repository returns zero occurrences of `hunger`, `satiety`, `_hunger_index`
and `_satiety_index`; the same sweep returns 22 occurrences of
`minimum_opposing_trade_distance_pct`, so the instrument does find a name that
is present. `git log --all -S"hunger" -- "*.py"` returns no commit on any
branch, against a control of three commits for `_tick_execute_scrum`. The two
words appear only in handoff notes and archived session history.

No aggression factor shortens the wait between candles today. The bot has no
term that widens its willingness to fire inside the dead zone between the
Minimum Opposing Trade Distance and the band extreme.

## 9 - Accumulation Shadows

The Accumulation Shadow was invented as a means of taking maximum advantage of long term and bearish conditions. It allows for a Scrumming to create a Shadow of itself that focuses on accumulating a smaller chunk of the target asset during a bearish regime. The shadow is allowed to accumulate downward but does not scrum. It was a bullish regime to be dedicated and then detonates thereby claiming all of its profits at once. Shadows operate in parallel with their parent bots and will be listed as Shadow Tranches once they are fully implemented.

The Accumulation Shadow has no code. No shadow bot, shadow tranche or shadow
regime exists. Every `shadow` identifier under `src/` carries one of three
other meanings: a drawing effect (`QGraphicsDropShadowEffect`,
`SHADOW_COLOUR`, `SHADOW_BLUR_RADIUS_PX`), a hardcoded version string that
shadows the real one (`ShadowLiteral` in `src/core/version_sweep.py`), or the
phrase "shadow bot" used to describe the Phantom Bot in
`src/gui/bot_wizard.py` and `src/gui/main_window.py`.

Three functions collapse or remove a tranche, and none of them knows a shadow
kind: `_apply_merge_rule` in `src/trading/stack_math.py` merges two rungs,
`_despawn_aged_tranches` in `src/trading/scrumming/fold_tranches.py` removes an
aged one, and `clear_fold_tranches` and
`ScrummingBot.clear_stack_tranches` discard a queue. Despawn removes a
tranche; it does not delist one. The entry's own wording — "once they are
fully implemented" — matches the code.

## 10 - Charge Up Permission Gate

This is client-side trade batching. It operates in conjunction with the Fold and Stack Tranches (explained later) to allow these individual positions to be combined into a single trade action in response to a given market trend.

The Charge Up Permission Gate has no code. A token sweep over every Python
file returns zero occurrences of `charge_up`, `_charge_bar` and `_charge_n`,
against 22 for `minimum_opposing_trade_distance_pct`.
`git log --all -S"_charge_bar" -- "*.py"` returns no commit on any branch,
against a control of three for `_tick_execute_scrum`. The words appear only in
handoff notes.

Fold and Stack Tranches do run (entry 11). Nothing combines them into one
batched order.

## 11 - Fold, Stack, Extractor, and Shadow Tranches / Provenance Queue

The term tranche emerged in Acervator as the concept of placing soft boundaries around where an opposing trade 1) can initially happen in terms of price level, 2) denote the amount of the position expected to be transacted once the price thresholds are met or exceeded, 3) allows wire credits to be fed into Fold Tranches (Buys) and Extractor Tranche profits to be distributed across Stack Tranches (Scrums / Sells) for additional accumulation and profit optimization. For the sake of clarity, Fold Tranches spawn after a Scrum (Sell) occurs; Stack Tranches spawn after a Fold (Buy) occurs; and Extractor Tranches spawn when an Extractor Bot finds a favorable Alternate Currency entry on its chosen timeframe and these tranches remain until the acquired Alternate Currency stack is sold by either the Extractor Bot (Sibling) or its corresponding Scrumming Bot (Parent). All Tranches will persist under a bot’s Details > Tranches Tab.

Three of the four tranche kinds run.

- **Fold Tranches** spawn on a scrum. `FoldTrancheAccountingMixin` in
  `src/trading/scrumming/fold_tranches.py` owns them:
  `_bound_new_fold_tranches` bounds the new rows, `_apply_scrum_fold_pct`
  scales what the sell just appended, and `_fold_eligible_tranches` releases a
  row when price falls to `ref * otd_factor`.
- **Stack Tranches** spawn on a fold. `ScrummingBot._spawn_stack_from_fold`
  and `_open_stack_from_scrum` create them, and
  `split_scrum_into_tranches` in `src/trading/stack_math.py` prices the
  ladder. A three-unit scrum at 100 with a 1% split and linear spacing returns
  rungs at 101, 102 and 103 carrying one unit each.
  `_apply_merge_rule` folds two rungs closer than 0.1% together: 100, 100.05
  and 105 come back as 100.05 carrying two units, then 105 carrying one.
- **Extractor Tranches** spawn when an Extractor Bot enters a pair.
  `ExtractorBot.tranche_id_for_position` and `extractor_tranche_rows` in
  `src/trading/extractor_bot.py` name and list them.
  `_hand_base_currency_to_parent` returns the base currency to the parent
  Scrumming Bot, which takes it in
  `ScrummingBot.apply_extractor_tranche_return`. That is the sibling-and-parent
  relationship the entry describes.
- **Shadow Tranches** do not exist; entry 9 gives the measurement.

The queue is `_fold_discharge_order`, which sorts the fold tranches by `ref`
descending and drops any row whose `ref` or `units` is not a finite number.
Wire credits ride on the tranche through `WireRoutingMixin._add_wire_credits`,
which is the provenance the entry names.

Three defects stand against the Tranches tab and the rows it draws: spawned
tranches do not match the scrum that spawned them (issue #367), the list is
not visible and lifetime counters reset (issue #133), and the Units column
prints a quantity that does not exist (issue #201). One more sits behind them:
`CapitalReservationRegistry` in `src/trading/capital_reservation.py` answers
`effective_available` before `_execute_sell` places a sale, and of the five
`ScrummingBot` construction sites only the two Simulator controllers hand the
bot a registry (issue #427).

## 12 - Technical Analysis Indicator Confidence Tiers

Most TA systems stack indicators additively. The Tier-4 suite organizes signals into four confidence tiers with cumulative weighting: Tier-1 (structural, highest weight), Tier-2 (confirmation, medium weight), Tier-3 (momentum), Tier-4 (context). Entries require Tier-1 + Tier-2 alignment; Tier-3/4 scale confidence but cannot override. This tier system arose out of queries with Claude Code while it was roleplaying as a TA Archetype and is only one such example where most of the other such contributions deal with bug fixes.

The four-tier scheme is a design. The engine has no tier.
`Signal` in `src/trading/indicators/types.py` carries `indicator`,
`timeframe`, `direction`, `confidence`, `weight`, `details`, `timestamp` and
`abstained`, and nothing else. No field names a tier, no code groups the
voters into tiers, and no rule requires a Tier-1 and Tier-2 alignment before
an entry.

What runs instead is a flat per-indicator weight. `DEFAULT_WEIGHTS` in
`src/trading/ta_engine.py` gives each of the twelve voters one number between
0.8 and 1.2, and `Signal.weighted_score` multiplies direction by confidence by
that weight. Every vote can move the total, and none can veto another.

Two names in the tree use the word for something else, and neither is this
feature: `classify_tier` in `src/competition/season_schedule.py` ranks a
trophy by percentile, and a comment in `src/trading/indicators/spring.py`
calls a Wyckoff Spring a Tier-1 setup.

## 13 - Initial-Purchase-Price Floor on Folds

This rule asserts that a subsequent Fold occurring after a Scrum MUST be less than sell. This, of course, is asserted by Bollinger Band Travel, Minimum Opposing Trade Distance, Target Balance Not Zero, etc.

The floor runs, and it lives on the tranche. Every fold tranche stores `ref`,
the price of the scrum that spawned it. `_fold_eligible_tranches` in
`src/trading/scrumming/fold_tranches.py` releases the row only when
`ticker_last <= ref * otd_factor`, and `ScrummingBot.tick` builds
`otd_factor` from `fold_rebuy_factor_from_pct` in `src/trading/otd_math.py`,
which returns `1 - OTD/100`. A 1.00% interval with a 0.60% fee gives an OTD of
1.60% and a factor of 0.984, so a tranche spawned by a sale at $100.00 folds
back at $98.40 or lower. The fold-side `HysteresisGate` in
`src/trading/gate_chain.py` holds the same distance for the bot as a whole,
and `placement_floor_price` in `src/trading/stack_math.py` holds it for each
new ladder rung.

One gap sits in the same path, and the function names it in its own
docstring: the fold gate wraps the OTD call and falls back to an OTD of 0.0
when a config value is not a number. At that fallback the distance rule is not
active.

## 14 - Position Ceiling and Detonation

This setting allows a total profit cap to be set for a given position before it sells its entire or a large portion of its total value.

The entry covers two mechanisms. Both start disabled, and they act on
opposite sides of the cycle.

The **ceiling** brakes buying. `ScrummingBot.position_ceiling_usd` returns the
anchor target multiplied by `position_ceiling_multiple`, clamped to the range
1 to 10. `ceiling_ratio` divides the holdings value by that ceiling.
`fold_rate_taper` returns 1.0 below a ratio of 0.5, tapers from 1.0 to 0.1
across 0.5 to 1.0, and returns 0.0 at or above 1.0. `SmartCeilingGate` in
`src/trading/gate_chain.py` then blocks the fold, and `gate_vocabulary.py`
paints that block as the `CEIL` light. The ceiling starts no sale.

**Detonation** sells. `ScrummingBot._check_detonation_trigger` requires
`detonation_enabled`, a position value above the anchor, and a **bullish**
consensus at or above `detonation_confidence_min` on `detonation_timeframe`,
which defaults to `1d`. The check is edge triggered, so one bull reversal
fires it once, and a rate limit spaces the checks.
`ExecutionEngineMixin._execute_detonation` then market-sells the surplus above
`_anchor_target_balance`, clears the fold tranches, and reseeds the lots. It
harvests the excess above the anchor, not the whole position.

`detonation_enabled` and `position_ceiling_enabled` both default to False, and
issue #336 records both pairs among the wizard settings that never reach the
bot. Issue #107 records a detonation that can fire twice across a restart. Any
earlier description reading "bearish" is wrong: the code compares against
`SignalDirection.BULLISH`.

## 15 - Proof of Accumulation (PoA)

This is another one of the larger and more distinguishing features of the platform. At this point, it is a design proposal for a blockchain that provides certified trade performance between competitors without revealing their specific strategy tunings within Acervator or their identity. When this blockchain is initiated, ZERO tokens for it will exist in the world. I intend it to be, much like BTC to 1) have a fixed supply, 2) mean something through its generation and acquisition. Tokens are only created through the PoA tournaments and defeating Token Beasts or inflicting the most damage to them in a colosseum format. Additional functions would allow PoA tokens to be socketed into the platform to change its appearance and identify a user as a victor.

`src/competition/` is the PoA package, and its engine runs without a screen.

- `CompetitionEngine` in `competition_engine.py` walks a competition through
  registration, active trading, submission and adjudication, and hashes each
  entrant's config so a strategy proves consistency without publishing itself.
- `MerkleTradeLog` in `merkle_log.py` produces the root that stands in for the
  trade record, and `BotIdentity` in `bot_identity.py` holds the entrant
  identity.
- `TokenLedger` in `token_ledger.py` is append-only and hard-capped.
  `TOTAL_SUPPLY_CAP` in `season_schedule.py` reads 10,000,000, `award` refuses
  an award that would cross it, and an award id repeats at most once. Balances
  come from replaying the log; no operation edits one.
- `LocalTestnet` in `local_testnet.py` is the in-platform chain, and
  `SharedTestnetBridge.install_on` in `src/gui/shared_testnet.py` builds it
  during `MainWindow._setup_ui`. The chain exists in every running session.

Nothing in the running platform starts a competition.
`SharedTestnetBridge.request_competition` has five callers under `src/`, and
all five sit in modules outside `main.py`'s import closure —
`src/gui/testnet_tab.py`, `src/gui/main_tabs/testnet_tab_surface.py` and
`src/gui/main_tabs/shared_testnet_surface.py`. That closure holds 211 `src`
modules and leaves 130 outside it.
`RetiredTabsMixin._install_retired_tab_sentinels` in
`src/gui/main_tabs/retired_tabs.py` assigns `None` to `_competition_tab` and
`_testnet_tab`, and `CANONICAL_TAB_ORDER` in `src/gui/main_window.py` lists
seven tabs, none of them PoA. Issue #147 covers the tab as an initial
implementation.

`trophy_generator.py` draws the trophy as SVG and letters
`SOLVE · ET · COAGULA` around its rim. No module imports it. Token Beasts and
the colosseum appear in no Python file at all.

## 16 - Technical Analysis, Goodness of Fit, and the Confidence Index

The Confidence Index is the collated result of the 12-indicator Voting Panel and emulates the concept of a set of features (market structures / indicators) being read by a system having similar measurements for a given or expected or past action i.e. a Fold will always have a certain number of indicators voting bearish before its released for execution.

The Confidence Index runs. `VotingEngine._create_indicators` in
`src/trading/ta_engine.py` builds twelve voters, and `DEFAULT_WEIGHTS` holds
twelve weights; both count twelve when driven. `VotingEngine._aggregate`
computes `net` as the bullish score minus the bearish score, then divides its
absolute value by `voted_weight`, the summed weight of the voters that did not
abstain. Two bulls at weights 1 and 2 against one bear at weight 1 give a net
of 2.0 and a confidence of 0.5. A single bull beside an abstainer of weight 3
gives 1.0, not 0.25, which shows the abstainer leaving the denominator.
Confidence measures the breadth of agreement across the panel, not the
strength of one reading. `Signal.abstained` separates an indicator that
cast no vote from one that measured and found no direction.

"Goodness of fit" has no code. A search across every Python file returns no
occurrence. The phrase names the Simulator-against-live comparison work in the
session record, which issue #117 now carries.

Two standing defects touch the panel: the API Interaction Log still tells the
operator that seven indicators read the candles (issue #417), and eight
indicator implementations depart from their published formulae (issue #414).

## 17 - Tiered Strategy Validation and Workflow

Acervator has many unique characteristics and many of these are rooted in attempting to protect an investor from themselves. As such, I have designed a means of self-contained strategy testing that is meant to educate and validate before any attempt at using the platform against actual personal funds is ever attempted. Some may be confident or skilled enough to skip these protective steps. That is an individual user choice. I did not follow this workflow while developing it but I know exactly how my strategy works and when it is not. Given this, the intended workflow for a new user of Acervator should be Simulator > Paper Trader > Live. The system is configured so that the relevant operational elements, such as the Market Inspector, can inject Simulator and Paper equivalents into the appropriate Bot Swarm layers or bot fleet under the respective tab.

Three of the four stages exist. The Paper stage does not.

- **Market Inspector** builds. `_build_market_inspector_tab` in
  `src/gui/main_tabs/market_inspector_tab.py` inserts the tab.
- **Simulator** builds. `_build_simulator_tab` in
  `src/gui/main_tabs/simulator_tab.py` inserts `SimulatorTab` and calls
  `set_topology_getter`, so a Market Inspector proposal reaches it. Issue #117
  tracks its rebuild.
- **Paper Trader** is not built. No file named `paper*.py` exists in the tree,
  and none was ever committed on any branch:
  `git log --all --diff-filter=ADR --name-only` returns no such path, while
  the same query returns two entries for `src/trading/scrumming_bot.py`. The
  only tracked path matching the word is a manual page. The code states the
  same in its own defaults —
  `src/gui/main_tabs/stock_main_window_surface.py` carries
  `paper_trader_available: bool = False` beside
  `paper_trader_error = "No module named 'src.gui.paper_trader_tab'"` — and
  `RetiredTabsMixin` assigns `None` to `_paper_trader`. Issue #19 covers the
  build-out. Two surfaces that tell the operator a Paper Trader is present are
  issues #422 and #426.
- **Live** is the Trading tab, first in `CANONICAL_TAB_ORDER`.

Today the workflow runs Market Inspector, then Simulator, then Live. The Paper
stage is an intention.
