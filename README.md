# ⬡ Acervator

**Acervator - The Accumulation Trading Platform.** 

Most retail traders lose because they try to predict which way a chart will move. 
Acervator does the opposite: it treats every price oscillation as fuel. When 
your holdings rise above a dollar target, it sells the excess. When price dips 
below the sell reference, it buys back more than it sold. The structural 
guarantee — every completed cycle ends with more asset than it began with 
— holds regardless of market direction.

No prediction required. The volatility that destroys emotional traders is the
engine.

> *"Stop predicting. Start accumulating."*

Built by Anthony L. Brown, Ekthelius the Accumulator. Released to humanity.

This page is the product manual. The front matter and the full catalogue of
novel concepts are printed below in full. Every remaining part is one click
away in the [map](#the-rest-of-the-manual), a row per section.

## What is built, and what is not

The manual is a design document as well as a description. It says what each
part of the platform is meant to be, and some of those parts are not built yet.
Read it that way.

Built and running on live capital: the Trading tab, the Market Inspector, the
Bot Swarm, the Asset Charts, the History tab and the Console.

**Not built: the Simulator, the Paper Trader, and Proof of Accumulation.** The
manual describes each of the three at length as a design. This product ships no
backtesting engine, no paper-trading engine and no competition screen. Each one
is named again, with its issue, under
[the map](#three-subsystems-that-are-not-built).

```
Price rises → SCRUM (sell excess above target → fold queue fills)
Price dips  → FOLD  (buy back with queued USD at lower price → net accumulation)
Repeat      → Target grows via compound profit folding
```

The running version is `__version__` in [`src/__init__.py`](src/__init__.py).
It is not restated here, so it cannot go stale.

---

## ACERVATOR

User Manual and Feature Design Intention Guide

> Turbator aequilibrii dissolvendus reformandusque.
>
> —----------------------------------
>
> “The disturber of the balance is to be dissolved and reformed.”

> “You are either gaining more territory cheaper or you are selling for higher than you bought it in direct response to the market’s moment to moment volatility.” - Ekthelius

## Copyright and Attribution

Copyright © 2025–2026 Ekthelius the Accumulator. All rights reserved. Unauthorized reproduction, distribution, modification, or derivative work is prohibited.

This document describes systems, algorithms, and methods developed by the author over the course of a self-teaching period starting in 2017.

Produced using the SADP (Structured Assistant Development Protocol) discipline framework designed by Ekthelius and deployed within Claude Code as a Skills-based and python-driven harness.

### Contact

Acervator is the personal project of Zavyrian Productions and Ekthelius the Accumulator. Commercial inquiries, licensing requests, and networking requests are available via the channels listed at publication time:

ekthelius_the_accumulator@protonmail.com

### Legal Disclaimers

NOT INVESTMENT ADVICE Nothing in this document constitutes investment advice, a solicitation to buy or sell any security or financial instrument, a recommendation of any trading strategy, or an offer to engage in any financial transaction. Acervator is a software system, and software cannot give investment advice. Trading cryptocurrencies and digital assets involves substantial risk of loss. Acervator is a highly complex, professional, and stable tool for automating digital asset trades. It does not and cannot guarantee the ultimate state of a portfolio given any number of transactions executed through or by it based upon a given user’s configuration.

NOT A REGISTERED INVESTMENT ADVISOR The author is not a registered investment advisor, broker-dealer, or fiduciary. No fiduciary relationship is created by distribution of this document. Consult a qualified financial professional before making any investment decision. Ekthelius is a self-taught Technical Analyst with no official documentation to certify or desire to certify his skillset beyond his own personal portfolio results. They have been developed and achieved the hard way.

#### SOFTWARE PROVIDED AS-IS

The Acervator software system is provided as-is without warranty of any kind, express or implied, including merchantability, fitness for a particular purpose, and noninfringement. Users assume all risk associated with deployment. The author is not liable for financial losses, system failures, or downstream damages resulting from use of the software. Training, guidance, and general set up assistance can be provided but the vast majority of help one needs will be found in the eight part documentation so read it and understand what you are trying to use.

#### JURISDICTIONAL COMPLIANCE

Users are solely responsible for compliance with all applicable laws and regulations in their jurisdiction, including but not limited to: securities regulations, cryptocurrency-specific rules, KYC/AML requirements, tax reporting obligations, and exchange terms of service. Acervator does not assess or enforce jurisdictional compliance.

#### PATENT AND INTELLECTUAL PROPERTY NOTICE

The mechanisms catalogued in Part 2 are claimed as novel inventions by the author. No patent has been granted or filed for any of them. Research, academic, and personal study use is permitted. Commercial or competitive use requires written license.

### Risk Factors Specific to Algorithmic Trading

Algorithmic trading systems can fail in ways manual trading cannot. Known risk categories include: (1) exchange API failures and rate limits, (2) network latency and partial fills, (3) flash-crash and liquidity-gap events that bypass stop conditions, (4) stuck positions during exchange downtime, (5) adverse selection on thinly-traded pairs, (6) slippage exceeding model assumptions, (7) parameter drift as market microstructure evolves, (8) bugs in the trading code itself. Acervator includes explicit mitigations for these failure modes (see Part 4 · Risk Controls), but no mitigation is complete and Acervator is a platform that is being actively developed. A trader using any algorithmic system must understand these risks before deploying capital.

## Executive Summary

### What Acervator Is and What It Is Aspiring To Be…

Acervator is a desktop trading platform whose innovation is the platform itself. The breakthrough is not a feature, an indicator, or a bot — it is the integrated system. A harvest-fold accumulation engine, a twelve-voter Indicator Voting Panel across up to five timeframes, a seventeen-class declarative GateChain safety framework, multi-bot coordination, and a live evidence trail proving the whole operates on real capital — coherent as one machine that converts price oscillation into asset accumulation and monotonic target growth without forecasting direction.

The platform will ultimately be designed to trade both cryptocurrency and stocks but is being developed to focus on the blockchain first given its current and immediate future impact on global financial systems. The crypto trading side is being prototyped via Coinbase Advanced and is the production surface today — live operator capital, fourteen weeks of execution, 5,055 trades with all assets successfully fending off the current bear trend or flat out beating it.

Harvest-Fold is the method and a mechanism. A position opens against a base currency with an explicit USD target (or a target that is translated to a USD or other local equivalent) with the initial size of the position being used as a value set point about which the mechanism of the platform allow volatility to “orbit” by persistently re-zeroing to it in response to local market structures and price ranges. The method itself stands apart from traditional Technical Analysis trading strategy or systems by not speculating or attempting to guess what the price will be within any given amount of time but instead persistently remolds a portfolio as its positions fluctuate and refusing to leave profit on the table by saying “It might be worth more later.” .

The primary “bot” or strategy that executes the Harvest-Fold method is called a Scrumming Bot and can be supported by, and this is exclusive to the cryptocurrency side of the platform, an Extractor Bot which performs more traditional scalp-style trades using isolated chunks of the parent Scrumming Bot’s Target Asset with the Extractor’s primary limitation being that it only works for established Base Currencies on a given exchange that has multiple asset pairs to exchange them against. The platform is designed and optimized in such a manner to allow “swarms” of Scrumming Bots (with or without Extractors) to be deployed to support dozens of positions across multiple exchanges simultaneously and thereby allowing the average digital asset investor to experience full spectrum digital asset trading that has previously been inaccessible or inefficient to execute properly.

The term “scrum” was initially encountered while I was learning about how a barrel of oil’s profit is split or distributed. The scrum of the barrel, according to the tutorial, was what the gas station gets as its share of profit and its insultingly small, thus requiring huge sums of fuel to be sold for any respectable amount of money to be made by the facilities hosting the gas pumps and their infrastructure. The concepts of small, repeating, and accumulating were found to rest inside on one term and so it was readily adopted. The extractor, however, is more straightforward in origin and it rests on the idea that BTC and ETH trading became the primary means of acquisition after direct mining became unaffordable for average blockchain participants. It has always been apparent that the potential for faster wealth acquisition existed via asset trading but the skill and technology gaps are what prevent this door of opportunity from opening for just about everyone.

Prior to the invention of the Harvest-Fold mechanism, I had also conceptualized grid bots via a now deprecated cryptocurrency auto-trader called Margin. When this application first appeared and was used, it only featured a simple “ping-pong” and a more speculative / adaptive “margin” bot. It should also be noted that it was never a stable product throughout all of the versions attempted and this was what led to its failure while its company became a consultant firm of some sort. I am not sure how producing an unstable, feature-limited auto-trader qualifies you as a fintech advisor but maybe qualifications remain loose or have become looser. Regardless, and in spite of the instability experienced immediately during basic use, an attempt was made to stack dozens of ping bots of a large range on a given market. This may have been the first “grid bot” used in cryptocurrency trading. The resulting and constant crashing led to my seeking help from the company via their Telegram channel where he was told, basically, that he was using it incorrectly which was an unacceptable and stupid excuse for not fixing their product. Instead, they stole said concept and added a “stack bot” in a later version of Margin that performed the same basic behavior under one bot instance but because of the fundamentally buggy quality of the software, this was not used much before a boycott was necessary because the company chose to ban people criticizing the unending stability issues. After this, Margin supposedly partnered with KuCoin to bring their technology to said exchange but this seems to have dissolved at some point with KuCoin releasing its own Grid Bots with which I was able to win 3rd place and win three Lomen NFTs as a result. Said Lomens still reside on a certain Metamask to this day should this or any other part of this tale be doubted. Whether I am a co-inventor or discoverer of modern automated cryptocurrency trading is a point for irrelevant debate. What matters is that Acervator is my newest invention and it is infinitely more powerful than anything before it.

After the United States blocked access to KuCoin, I continued to develop my trading strategies further and executed them manually while learning more Technical Analysis. In the end, high volume trading methodologies were seen as the only method for maximizing profits in volatile markets. The entire idea of ‘HODL’ being pushed by people who were obviously continuing to accumulate was and remains disgusting but it is just how the game is played. No one is clicking anyone else’s mouse so it is permissible. This is just a variation of what is generally called “Wall Street Investment” as well or at least fits the meta-pattern well enough. The average person, and their precious money, is expected to trust and be exposed to dangerous, unstable market environments while gaining no real benefits beyond a promise that breaks every few years. There is not an entry level for market volatility and, with the advent of Acervator, there does not have to be.

More than anything else perhaps, the creation of Acervator represents an explicit effort to essentially debunk the approach and hamstringed interaction methods most investors are expected to utilize or, more accurately, tolerate. The average person who puts money into the market surrenders most or all control of it based on a hope that increasingly has no rational basis due to the lack of protections or proportionate, timely reward. The investor gets a secondary value abstraction that they have to wait to sell for more later (and are attacked for doing so if it's anything other than a stock!) assuming the market moves favorably. I see this as an over-exposed “bait and switch” where too often people are left holding worthless bags of tokens or stocks or bonds. It is an upgraded lottery system in some regard but it is only gambling to those that attempt to play blindly or passively and accept the ‘HODL’ advice from whales who just need their next meal to sit still.

The highest goal is for Acervator to be a self-contained retirement platform that provides a powerful option for anyone seeking to take a direct, elegant, self-contained approach to their digital asset portfolio management. It aspires to be the lens, the manager, and the fiduciary while only requiring users to test it, suggest new features, and / or donate to its continued development. Regardless, this will be my last attempt to help humanity see past the wiggly chart illusions but, honestly, I do not think anything else will be required.

LAST NOTE: This manual, like the software it discusses, is a work in progress and it will be updated on a regular basis as features are added and finalized..

## Product Manual Parts

This manual is an attempt to clarify all parts and functions for what might be considered a somewhat esoteric product given its innovative approaches and the sheer number of novel features it contains. More cynical SaaS providers might disagree but I look forward to all feedback regardless. Currently there are seven such sections with each focusing on ever smaller components of the total system.

Part Title and Area of Focus

1 Frontmatter & Overview

2 Novel Concepts and Patent Candidate Portfolio

3 System Architecture and Features Catalogue • Main Window

• Trading Tab - Active Bot Lists Under Exchange Tabs - Indicator Voter Panel - Trade Logic Activity - API Activity - Top-Level Portfolio Metrics

• Simulator Tab - Validation Runs vs. Historical Trade Data - Acervator Strategy Back Testing - Runs Historical Data Through Simulated Bots - Bot Swarm Simulation - Deploy As Paper Trading - Deploy As Live Trading

• Paper Trader Tab - Runs Live Exchange Data Through Simulated Bots - Executes and Documents Paper Trades - Collects Paper Trade Data - Pushes Trade Data to Paper Trade History Log - Paper Trade History Tab Reads and Displays

• Proof of Accumulation (PoA) Tab - PoA Blockchain and Trading Tournament Interface - Hosts User Competition Performance and Data - Displays Tournament Monsters and Targets

• Market Inspector Tab - Synthesizes and Proposes Bot Swarm Topologies and Oppositional Trades - Pushes Proposals to Sim, Paper, or Live As Directed

• Bot Swarm Tab - Displays and Allows Configuration of Capital Reinforcement Networks

• Asset Charts Tab - Displays Price Charts for All Active Bots

• History Tab - Loads and Displays Live Trade History Via Exchange API - Merges Live Trade History w/ Acervator Trade Log for Grading and Gate Analysis - Paper History Tab - Loads and Displays Paper Trade History w/ Grading and Gate Analysis

• Console Tab - Displays internal codebase activity, warnings and faults

• System Status Tab - Displays Platform Status by Subsystem - Fed by the Emitter Network • Settings - System and High-Level User Settings

3 Live and Supporting Evidence

• YTD Exchange Data Covering the Entire Development Arc and Exchange Test Coverage

5 Conceptual Hopscotch: The HOP Protocol, Rules Registry, and SADP v1 and v2

6 ADR Index & Glossary

7 Recent Updates and Version Tracking

8 The Development Chronicle As Told By Claude

9 Live Trade History and Supporting Evidence

- VWAP Charts - YTD Data Analysis and Trade Grading - Deep Indicator Function Investigations Via Trade Logic Gate Logs

## Novel Concepts and Patent Candidate Catalogue

Active development on Acervator began in early April of 2026. It began after realizing that the AI-assisted software development tools had achieved an inflection point with their capabilities. Prior to this, efforts were being made to learn traditional coding with little success that was mainly due to an inability to get into a grinding effort for whatever reasons. This has been particularly frustrating since other subjects seem to grab and others deflect. With the advent of Claude Code however, it feels like some of us have been given a decently priced door man and well-informed guide through this and other labyrinths.

Each entry below carries an anchor. The anchor is the code that runs the
concept today, quoted from the module that holds it. Where a concept has no
code, the entry says so and gives the query that measured the absence, and then
proposes the build. Anchors describe the present state of the platform, not the
plan.

### 1 - Harvest-Fold / Scrumming

At the core of Acervator is what might not first appear as a multi-faceted concept designed to address or alleviate many of the mental pitfalls that can afflict a new trader. After having observed a number of people via Telegram and web approach the challenge of investment differently, I have come away convinced that all it only becomes as complex as the individual allows it to be. This is not to be reductive about economics or any other connected discipline but it is to say there are reliable, stable, consistent means of reading price charts and too many people are simply doing it too many different ways and this only compounds the complexity illusion further. Much of the uneasiness inflicted on the new trader surrounds the emotional desire or even personal need for the value of their positions to increase as soon as possible or show the midterm potential of becoming profitable. Those that adopt the HODL meme are, in my experience, quite crippled in their ability to sell positions even when the time is right, which is usually when most people are happiest about the market. The ironic truth is that however good a trade is, there is an equally bad one on the other side of it. Acervator attempts to respect the market by not taking profit all at once and absorbing or claiming ownership of its positions’ variance strictly based on the market local, organic price ranges. In other words, its trade actions are always proportionate to whatever the market is actually doing at the time the trade is executed. Over time, this ‘molds’ the position to the long term truth of the market and avoids the need to speculate entirely. The more bold hope for this approach is that it might add another tool for stabilizing macro-economic phenomena such as underpinning currency exchange rates between countries.

Acervator addresses ‘fundamental market unpredictability’ by allowing volatility to “orbit” around a set point we call the Target Balance. This element is what performs the first mental trick. It forces the trader to say and establish that “my position is worth X and I will support X with an equal amount of liquidity” i.e. a Target Balance of $50 is set and a total mental position of $100 is established. Trades will be executed to maintain the truth of the Target Balance always being X. After the initial entry is executed and filled, which Acervator will only do in the lower extent of the Bollinger Band on the chosen timeframe, the Scrumming Bot will persistently shave off and “Fold” back in Y% of profits through repeating Harvest-Fold operations that continue until the bot is deactivated or the market suffers a catastrophic collapse which can and do happen so don’t not leave it unmonitored. It should also be noted that the term ‘harvest’ came to replace ‘scrum’ for the sake of clarity but they may be used interchangeably throughout this text. Essentially a Scrum or Harvest is a sale of a position’s increased value over the Target Balance. The amount that the Scrumming Bot harvests or folds is pinned to the Target Delta or the amount of variation (%delta) from the most recent trade event. Much of the finer details of trade execution can be tuned by the user as expected for any professional application but the primary point here is that the amount of profit folded back is capped by the Maximum Target Growth Per Cycle setting while the ability of Acervator to prevent inverted (profit losing: buying higher than sold / selling lower than bought) trades we also have the Minimum Opposing Trade Distance rule which dictates the next trade must be Z distance from the most recent trade event. In addition, sells are not allowed to occur or be pushed below the Bollinger Band midline while buys are not allowed to occur or be pushed above the midline. As a result of just these few component features, we already have multiple soft, non-TA or non-traditional rules protecting the investor before we even start optimizing the trades themselves (pushing them as close to volatility extents as possible) via Technical Analysis and other inventions.

The harvest-fold method itself was manually executed and tested on a multiple cryptocurrency pairs throughout 2023~2026 but it has always been the aspiration to automate it and have it executed at a high rate of frequency with the operating theory that this approach to investment, being a hybrid a HODL and active trading, creates frontline area of support for whatever markets in which it participates long term. It does this by maintaining and, utilizing as directed, all earned profits. It turns any user into an active participant and liquidity provider.

After entering the space full time in 2017, I immediately began to parse and breakdown how price charts were being interpreted. This also allowed me to perform ever deeper introspections on my own response to how my mind was responding to the value of my portfolio fluctuating. I did myself absolutely no psychological favors in this pursuit but, as you will see, I had plenty of reasons to take this reckless approach. By this point, my undiagnosed and untreated military injuries had worn me down to the point where I realized I was running out of time to continue working as normal. I had, by then, been walking a torsioned pelvis for 17 years that had seized in place and, by 2020, would be causing enough pain to induce panic attacks. I could have joined the pill-mill club but I declined. In combination with the pain, the forced TA self-training, physical job, and broken marriage, I also assembled an entire GPU-based mining farm…alone. I had some business partners but their participation was basically nonexistent. The VA was providing no support and would not until 2022. The Navy and Pentagon had spit in my face by sending me PDBR paperwork that they had no intention of ever honoring no matter what I wrote down. My family more or less remained ignorant of all my turmoil while I kept the paychecks coming. So really the story of Acervator’s and Harvest-Fold is one of betrayal to a degree that allowed me to see through things more clearly than would otherwise have been possible. It has been invented out of necessity and it is my intuition that Acervator can become that necessary tool for other people as well.

##### The target and the two sides

**Functional.** The bot holds one number, and that number is the dollar value
you told it the position is worth. On every tick it compares the position
against that number. Above it by more than a dust band, the bot has surplus to
sell. Below it by more than the band, the bot has a deficit to buy. Inside the
band it does nothing at all. One function answers that question for the whole
engine, and the dust band is a tenth of a percent of the target with a floor of
one cent. At a target of $50 the band is $0.05, so a position at $60 answers
scrum and a position at $40 answers fold.

`src/trading/target_bands.py` — `target_territory`

```python
delta = float(position_value) - float(target_balance)
band = at_target_dust_band(target_balance)
if delta > band:
    return "scrum"
if delta < -band:
    return "fold"
return "at_target"
```

**Design intention.** The Target Balance is the set point the whole method
orbits. It is declared once in the bot's config and the tick re-zeroes to it.
The bot brain holds the tick, the scrumming package fires the two halves of the
cycle, and the execution module places the orders.

`src/trading/container/config.py` — `BotConfig`

```python
target_balance: float = 200.0  # Balance the bot trades relative to
scrumming_interval_pct: float = 1.0  # % market move between actions
max_target_growth_pct: float = 1.0
```

##### The distance rule

**Functional.** An opposing trade has to travel far enough to clear both legs of
the round trip. That is the operator's scrumming interval plus the exchange fee.
A one percent interval against a six tenths fee gives 1.60 percent. One function
owns the arithmetic, and the clamp is applied to the sum rather than to the
interval, because the bound exists to keep the rebuy factor sane.

`src/trading/otd_math.py` — `minimum_opposing_trade_distance_pct`

```python
total = float(interval_pct) + float(fee_pct)
return max(OTD_MIN_PCT, min(OTD_MAX_PCT, total))
```

**Design intention.** Without this rule the bot can sell low and buy back
higher, which is the one outcome the method exists to prevent. The gate that
enforces it refuses the trade until price has travelled that distance from the
pivot, and it rebuilds the required price in its own refusal message so the
operator can read why it held.

`src/trading/gate_chain.py` — `HysteresisGate.evaluate`

```python
ok = ctx.hyst_ok_scrum_side if self.side == "scrum" else ctx.hyst_ok_fold_side
if ok:
    return GateResult(passed=True)
eff_pct = ctx.scrumming_interval_pct + ctx.trading_fee_pct
```

##### The midline rule and the growth cap

**Functional.** A sell is not allowed below the Bollinger midline and a buy is
not allowed above it. The tick sets one flag for each side off the band
position, and a gate refuses the wrong side of the band. The scrum flag also
carries the phantom lock, so a locked bot cannot sell whatever the band says.

`src/trading/scrumming_bot.py` — `ScrummingBot.tick`

```python
scrum_ok = (bb_pos > 0.50) and not self._phantom_locked
fold_ok_midline = bb_pos < 0.50
```

**Design intention.** Profit folded back into the target is capped for one
market cycle, so a single violent move cannot inflate the set point beyond what
the next cycle can support. The cap is a percentage of the target at the moment
the cycle opened, and it shrinks as the cycle consumes it.

`src/trading/scrumming_bot.py` — `ScrummingBot.cycle_growth_cap_usd`

```python
_pct = float(getattr(self.config, "max_target_growth_pct", 1.0) or 0.0)
```

The same key answers differently in different places. Nine read sites fall back
to 1.0 and three fall back to 0.0, so a bot whose stored config lacks the key
compounds or freezes depending on which site read it first. Issue #409 carries
it.

The gate set the bot writes is named in one place: ten scrum labels and nine
fold labels, nineteen lights per bot.

`src/trading/gate_vocabulary.py` — `_GATE_ORDER_SCRUM`

```python
_GATE_ORDER_SCRUM: tuple[str, ...] = (
    "TGT",
    "INT",
    "BB",
    "FIRE",
    "TA",
    "LS",
    "TRND",
    "HTF",
    "CB",
    "OTD",
)
```

### 2 - The Phantom Bot

While the Harvest-Fold method housed with the Scrumming Bot addresses several persistent and nagging questions around any given investment position (Should I buy more? Should I sell some? When? How much?), it does have the weakness of operating on a single timeframe. The Phantom Bot is another feature intended to optimize trade execution position. In this specific case, it allows a single Scrumming Bot to be inhibited by a higher timeframe signal with the intention of capturing alignments or disagreements so that trades are not being executed prematurely. The design intention here is that, for example, a 5m TF bot can be inhibited by a 15m, 30m or 1hr signal while maintaining a volatility watch on its primary TF. The intention is to build out this feature so that it obviates or reduces the need for multi-screen monitoring of individual assets.

**Functional.** A phantom is a copy of the position read on a slower chart. It
computes technical analysis on its own timeframe, stores the result, and
constructs no order. Six timeframes are the default set.

`src/trading/scrumming_bot.py` — `ScrummingBot.DEFAULT_PHANTOM_TIMEFRAMES`

```python
DEFAULT_PHANTOM_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]
```

**Design intention.** The inhibition the entry describes runs today. A bullish
higher timeframe stops the scrum and a bearish one stops the fold, and each
writes its own label into the blocker list so the operator can see which
timeframe held the trade. The coordinator weights the phantom summaries by their
rank before the gate reads them.

`src/trading/gate_chain.py` — `HTFDeferGate.evaluate`

```python
blocks = (
    ctx.eff_htf_blocks_scrum
    if self.side == "scrum"
    else ctx.eff_htf_blocks_fold
)
if not blocks:
    return GateResult(passed=True)
label = "HTF-bullish" if self.side == "scrum" else "HTF-bearish"
return GateResult(passed=False, blocker_message=label)
```

Three parts of the feature do not work. The phantom lock guard is dead, so a
lock never holds anything (issue #398). Every profit and loss figure on the
Phantom Bots tab prints as zero, because the key the tab reads is never written
(issue #197). The tab draws a refused change as a success and can drop a
timeframe (issue #313). Issue #155 tracks the remaining build-out. Replacing
multi-screen monitoring is an intention, not current behaviour.

### 3 - The Landing Strip

Perhaps the earliest assumption that hit me the most and really presented the catalyzing challenge to creating all of my alternate trading methods, is that you cannot predict what the market will do and after only a short while of actively trading I asked the questions: “But what if I don’t have to?” “What if I decide that I do not have to speculate at all?” I do not remember exactly when I first used the term but I think it was when I was trading ADA and XLM some years ago while participating in a Telegram group with some psytrance friends and associations called the Better Bitcoin Bureau. The name changed a few times but this is the one I recall.

The concept emerged from my persistent use of Heikin-Aishii candles. I had decided on this candle style early just by intuition. I could say it was because I “felt it looked nicer” but that does not quite capture the magnetism. To me, they just structurally make more sense and are less sloppy than traditional candles. What I began to observe over and over was the propensity for crypto markets to form long, tapering structures from these candles and that the likelihood of market reversal could be pinned to 1) the landing strip length and 2) its proximity to the Bollinger Band. Further, I found that those markets that formed these on 1D or higher timeframes would often have explosive breakouts like a volcano that had charged up to blow out. These findings can be historically verified and back tested. I manually performed this observation all the way down to 1 minute trading and found that it was only at this lowest TF that it started to exhibit sub-50% reliability. Given this, the concept has been transposed into Acervator as a core component and trading logic gate with the number of candle strip candles being a user configurable setting.

This is also where I should mention that I am not at all a quant or mathematical trader. I consider myself a visual or tactical trader that focuses on market reversals. I have taught myself to visually interpret price chart structure using a given set of indicators used by countless other technical analysts. When looking at some of the labeling within Acervator, however, one will readily see military references and hints at how I view asset accumulation as something akin to progressive territory capture on a perpetual gameboard. The less skilled traders are surrendering it with every cycle of the market.

**Functional.** Two detectors build the Landing Strip and both run on every
tick. The first places price inside the Bollinger channel and counts trailing
Heikin Ashi bodies under a tightness threshold. It reads the operator's control
directly.

`src/trading/scrumming_bot.py` — the first detector's call

```python
min_pattern_candles=self.config.bb_landing_strip_candles,
```

**Design intention.** The second detector is the one that scores the taper. It
counts a run of shrinking Heikin Ashi bodies, names the band the run reached,
and returns a confidence boost the tick adds to its own. On a tapering rally
into the upper band it answers detected, side upper, length three, boost 0.1437.
The same tape without the taper answers not detected, and a five-candle tape
answers not detected. A detected strip can force a direction, which is why the
gate vocabulary marks it an override rather than a gate.

`src/trading/indicators/landing_strip.py` — `detect_landing_strip_v2`

```python
def detect_landing_strip_v2(
    candles: list[Candle],
    min_consecutive: int = 3,
    shrink_threshold: float = 0.90,
    bb_tolerance_pct: float = 3.0,
    use_ha: bool = True,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> TighteningResult:
```

The second detector does not read the setting. The tick hands it a literal
three, so the wizard's Landing Strip Candles control moves the first detector
and leaves the second where it is. Both defaults sit at three, so the two agree
until the operator changes the control.

`src/trading/scrumming_bot.py` — the second detector's call

```python
tightening = detect_landing_strip_v2(
    candles,
    min_consecutive=3,
    shrink_threshold=0.90,
    bb_tolerance_pct=3.0,
)
```

Issue #432 carries it.

### 4 - Bollinger Band Travel Detection

Allowing a strategy to “see” where it is in relation to local width of the Bollinger Band is another aspect of treating the immediate market as a region on a map through which a stack of tokens is traveling. Along the route, we are able to offload surplus at the peaks and pick up additional supplies in the next valley. This is used in combination with Minimum Opposing Trade Distance. The complete question then becomes “Has the market traveled 70% (default), is current price X% distant from the most recent trade event, and is Target Delta not zero? When combining these gates with the (Technical Analysis) Indicator Voting Panel and Landing Strip Detection, you have a full market structure detection suite that is able to incrementally adjust a position’s size and generate recurring profits or growth with each market cycle.

**Functional.** The tick measures how far price has moved since the last trade
and divides that by the current band width. When the fraction reaches the
operator's percentage and the target delta is positive, the travel flag is set.
The default is seventy percent and the wizard offers zero to a hundred. That is
the compound question the entry states, and the code asks it in one expression.

`src/trading/scrumming_bot.py` — `ScrummingBot.tick`

```python
_bb_width = max(bb_result.upper - bb_result.lower, 1e-12)
band_travel_frac = abs(ticker.last - self._last_trade_price) / _bb_width
if (
    abs(ticker.last - self._last_trade_price)
    >= self.config.band_travel_pct / 100.0 * _bb_width
    and delta > 0
):
    band_travel_triggered = True
```

**Design intention.** A fixed percentage means two different things in a quiet
market and a violent one. Measuring the move against the band width makes the
threshold follow the volatility instead. The flag then clears a standing trend
hold and lets the harvest through. Travel is no gate of its own: the ten scrum
labels carry no travel light.

`src/trading/scrumming_bot.py` — what the flag releases

```python
trend_override = abs(delta) >= _interval_usd * 2.0 or band_travel_triggered
```

### 5 - Position-Aware Technical Analysis

Traditional TA treats a signal (e.g., RSI > 70) as context-independent. Position-Aware TA encodes the current Bollinger Band position as context: RSI > 70 near the upper band confirms overbought (sell bias), but RSI > 70 near the lower band is a failed oversold — a trap for mean-reversion buyers. The system applies this inversion systematically across all oscillator signals. In other words, it attempts to strengthen the price to Bollinger Band relationship by reading additional indicators with relation to it. If you have the landing strip, band travel, opposing trade distance, and a bullish or bearish confidence score from the Indicator Voting Panel, it is likely a trading event will occur. In the end, many of these functions were layered in one after the other until I saw the platform take most trades that I would myself manually execute most of the time.

**Functional.** The band context enters at the bot, not inside the voters. The
tick reads the band position once, marks the upper quarter and the middle band,
and accumulates a skew from the votes that arrive. A bullish vortex adds 0.12 at
the upper band and takes 0.05 back in the middle. A bullish MACD adds 0.08 and
takes 0.03 on the same test. Ichimoku and Stochastic RSI move the skew on
direction alone, with no band term at all.

`src/trading/scrumming_bot.py` — `ScrummingBot.tick`

```python
at_upper_bb = bb_pos > 0.75
in_bb_middle = 0.35 <= bb_pos <= 0.65

if (
    sig.indicator == "vortex"
    and sig.direction == SignalDirection.BULLISH
):
    if at_upper_bb and sig.confidence > 0.5:
        position_boost += 0.12
    elif in_bb_middle:
        position_boost -= 0.05
```

**Design intention.** The skew relaxes or tightens the confidence floor the vote
has to clear. A floor of 0.30 becomes 0.2679 at a skew of plus 0.12 and 0.3158
at a skew of minus 0.05. A skew of minus one returns infinity, which no
confidence can clear, so a fully contradicted reading is refused outright rather
than discounted.

`src/trading/scrumming_bot.py` — the two terms the floor reads

```python
_ta_conf_skew = position_boost + bb_confidence_boost
```

The inversion does not reach the oscillator modules. Each indicator computes
from candles alone, and the band position appears in six indicator modules only:
Bollinger, band proximity, landing strip, M top, spring and W bottom. Neither
the RSI module nor the Stochastic RSI module takes a band argument. Today the
band context re-weights the vote after the fact. It does not re-read the
oscillator.

### 6 - Market Inspector

This addition was, like the Phantom Bot above, a move towards making Acervator “hyper-vigilant” of hypothetical opportunities that take the form of oppositional trades (assets that move inversely to one another) and bot swarm network topologies. The bot swarm itself will be covered in a moment but basically this feature allows for the creation of custom capital reinforcement networks where profits are configured to flow between positions in a manner that can potentially strengthen a portfolio faster than just focusing on single, isolated bot instances.

The Market Inspector is designed to analyze the broader market for groups of assets from which to build topologies and identify non-active assets that could be traded in opposition to active positions. Its findings can be pushed to the Simulator for historical back testing, to the Paper Trader for live market and real time validation, and, of course, Live Trading should the user choose to do so.

**Functional.** The Inspector walks daily, weekly and monthly candles, scores
each market, and keeps the result. It then pairs a long-signal market with a
short-signal market when the correlation of their returns over a rolling window
sits inside a negative window. Those are the oppositional trades the entry
describes, and the ranking puts the most negative correlation first.

`src/trading/market_inspector.py` — `MarketInspector._find_opposing_pairs`

```python
corr = self._pearson(r_l[-m:], r_s[-m:])
if self._corr_min <= corr <= self._corr_max:
    pairs.append(
        OpposingPair(long_side=lo, short_side=sh, correlation_30d=corr)
    )
```

**Design intention.** The findings are meant to leave the screen. A separate
module turns those signals into swarm proposals with the bots and the wires
already written, and one push target exists today: the Simulator asks the
Inspector for its current proposals at build time.

`src/gui/main_tabs/simulator_tab.py` — `_build_simulator_tab`

```python
if hasattr(self._simulator, "set_topology_getter"):
    self._simulator.set_topology_getter(
        lambda: (
            self._market_inspector.current_topology_proposals()
            if hasattr(
                getattr(self, "_market_inspector", None),
                "current_topology_proposals",
            )
            else []
        )
    )
```

No Paper Trader exists to push to; entry 17 gives the measurement. Issue #23
tracks the tab's build-out and the topology and oppositional pushes, and
issue #290 a live connector defect on Refresh.

### 7 - Bot Swarm and Smart Wire Network w/ Provenance Tracking

The Bot Swarm, which is how I presented the concept to Claude, is my version of a capital reinforcement network. At the Exchange level (swarms cannot be connected across multi-API boundaries) profit from individual bots can be routed to others with such outputs being termed Wire Credits since they are sent and received along Smart Wires which connect the bots. Each such wire can have its own flow rate. The network nodes are designed to protect a given bot from excessive outflows which would cripple its own growth capacity. The other piece of this is that Wire Credits are Provenance tracked which allows outflows to eventually start sending profits back to the originating bot with the over-arcing philosophy being long-term investment with accumulation and position strengthening rather than just sitting around waiting for a good outcome that might not arrive.

In combination with the Market Inspector, the Bot Swarm can receive and deploy groups of pre-configured and pre-connected bot clusters that immediately begin participating in the market. This layer, along with future portfolio-level algorithms, will enable the fully automated and persistent execution of complex trading strategies from a single terminal window.

**Functional.** The wire manager holds the topology and one ledger for each bot.
A wire records a source, a target and a flow percentage, and a realised fold
moves the share along it. The outflow is capped so a funder keeps its own growth
capacity: a ten dollar scrum profit against a hundred dollar target releases
ninety percent, and a zero profit releases nothing.

`src/trading/smart_wire.py` — `compute_safe_outflow_pct`

```python
if scrum_profit_usd <= 0:
    return 0.0

if band_upper <= band_lower:
    distance_to_fold_pct = 0.0
else:
    distance_to_fold_pct = max(
        0.0, min(1.0, (current_price - band_lower) / (band_upper - band_lower))
    )
```

**Design intention.** Provenance is what makes the network more than a pipe.
Each credit that lands on a tranche keeps the id of the bot that supplied it, so
an outflow can eventually route profit back to the bot that funded it. The
detail list is bounded at twenty entries per tranche and everything older folds
into a rolled total, which keeps the sums exact without letting the record grow
without limit.

`src/trading/scrumming/wire_routing.py` — `_WIRE_CREDIT_CAP`

```python
_WIRE_CREDIT_CAP = 20
if not isinstance(wc, list) or len(wc) <= _WIRE_CREDIT_CAP:
    return 0
overflow = wc[:-_WIRE_CREDIT_CAP]
del wc[:-_WIRE_CREDIT_CAP]
```

How much of an arriving inflow a bot stacks onto an open position is its own
setting, and it defaults to one percent.

`src/trading/container/config.py` — `BotConfig.wire_inflow_stack_pct`

```python
wire_inflow_stack_pct: float = 1.0
```

One routing path is dead. The two spawn-and-route functions have no caller
anywhere in the repository, while the fold distribution and wire registration
beside them are called throughout. Issue #404 carries it, and issue #239 carries
the Bot Swarm tab's live rows. Deploying a pre-connected cluster from the Market
Inspector is an intention.

### 8 - Hunger and Satiety Indices

These elements were implemented as part of an effort to boost accumulation and scrumming performance in longer term bearish or bullish conditions that might not latch all logic gates to trigger a fold or scrum despite the Target Delta not being zero. This piece adds a factor to the bot that makes it more aggressively evaluate subsequent candles and will increase its likelihood of executing the re-zeroing action. This allows for trades to be executed in the hypothetical ‘dead zone’ between Minimum Opposing Trade Distance and the lower or upper Bollinger Band extent if the candle structure begins to float or cruise within it for too long.

**Not built.** Neither index exists in code today. No aggression factor shortens
the wait between candles, and the bot has no term that widens its willingness to
fire inside the dead zone between the Minimum Opposing Trade Distance and the
band extreme.

**The build this specifies.** The engine already carries a skew term that
relaxes the confidence floor, and hunger is that term driven by time rather than
by band position. A counter grows while the target delta is non-zero and nothing
fires, and it resets to zero on a fill. That reset is satiety. Two new config
fields set the rate and the ceiling, and the counter joins the skew the floor
already reads, so no new gate and no new call site are needed.

*Proposed, not present, in `src/trading/container/config.py`:*

```python
hunger_gain_per_candle: float = 0.0
hunger_skew_max: float = 0.20
```

*Proposed, not present, in `ScrummingBot.tick`:*

```python
if territory != "at_target" and not fired_this_tick:
    self._hunger_candles += 1
else:
    self._hunger_candles = 0
hunger_skew = min(
    float(self.config.hunger_skew_max),
    self._hunger_candles * float(self.config.hunger_gain_per_candle),
)
_ta_conf_skew = position_boost + bb_confidence_boost + hunger_skew
```

The default gain of zero keeps present behaviour exactly, so the feature ships
switched off and the operator turns it on per bot. Issue #433 carries the build.

### 9 - Accumulation Shadows

The Accumulation Shadow was invented as a means of taking maximum advantage of long term and bearish conditions. It allows for a Scrumming to create a Shadow of itself that focuses on accumulating a smaller chunk of the target asset during a bearish regime. The shadow is allowed to accumulate downward but does not scrum. It was a bullish regime to be dedicated and then detonates thereby claiming all of its profits at once. Shadows operate in parallel with their parent bots and will be listed as Shadow Tranches once they are fully implemented.

**Not built.** The Accumulation Shadow has no code. No shadow bot, shadow
tranche or shadow regime exists today.

Three functions collapse or remove a tranche, and none of them knows a shadow
kind. One merges two rungs, one removes an aged row, and one discards a queue.
Despawn removes a tranche; it does not delist one. The entry's own wording,
"once they are fully implemented", matches the code.

`src/trading/stack_math.py` — `_apply_merge_rule`

```python
def _apply_merge_rule(tranches: list[Tranche]) -> list[Tranche]:
    """Combine adjacent tranches whose prices are within MERGE_THRESHOLD.

    A merged Tranche keeps the higher `price` and the summed `size`, and the
    survivors are re-indexed from 0.
    """
```

**The build this specifies.** A shadow is a tranche kind, not a second bot. It
accumulates downward, never sells, and exits in one move when the regime turns.
The tranche dict gains a kind key, the three collapse functions skip a row that
carries it, and the exit reuses the detonation executor that already sells a
surplus and reseeds the lots.

*Proposed, not present, in `src/trading/scrumming/fold_tranches.py`:*

```python
def _despawn_aged_tranches(self, now: Optional[float] = None) -> dict:
    for t in list(self._fold_tranches):
        if t.get("kind") == "shadow":
            continue
```

A row with no kind key behaves exactly as it does today, so the change is
invisible until a shadow is spawned. Issue #433 carries the build.

### 10 - Charge Up Permission Gate

This is client-side trade batching. It operates in conjunction with the Fold and Stack Tranches (explained later) to allow these individual positions to be combined into a single trade action in response to a given market trend.

**Not built.** The Charge Up Permission Gate has no code today. Fold and Stack
Tranches do run, and entry 11 anchors them. Nothing combines them into one
batched order.

**The build this specifies.** The fold chain already carries a gate that refuses
when no tranche is queued, and the context it reads already counts them. Charge
Up is the same test with a threshold: hold the fold until enough tranches are
eligible, then release them together. It is a new gate class in the existing
chain, and it needs no new context field.

*Proposed, not present, in `src/trading/gate_chain.py`:*

```python
class ChargeUpGate(Gate):
    """FOLD-only: hold until ``min_tranches`` rows are queued, then release."""

    name = "charge_up"
    side = "fold"

    def __init__(self, min_tranches: int = 1) -> None:
        self.min_tranches = int(min_tranches)

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.n_fold_tranches >= self.min_tranches:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="charging")
```

The gate enters the fold chain before the hysteresis gate, and the gate
vocabulary gains one fold label, taking the row from nineteen lights to twenty.
A threshold of one reproduces present behaviour exactly. Issue #433 carries the
build.

### 11 - Fold, Stack, Extractor, and Shadow Tranches / Provenance Queue

The term tranche emerged in Acervator as the concept of placing soft boundaries around where an opposing trade 1) can initially happen in terms of price level, 2) denote the amount of the position expected to be transacted once the price thresholds are met or exceeded, 3) allows wire credits to be fed into Fold Tranches (Buys) and Extractor Tranche profits to be distributed across Stack Tranches (Scrums / Sells) for additional accumulation and profit optimization. For the sake of clarity, Fold Tranches spawn after a Scrum (Sell) occurs; Stack Tranches spawn after a Fold (Buy) occurs; and Extractor Tranches spawn when an Extractor Bot finds a favorable Alternate Currency entry on its chosen timeframe and these tranches remain until the acquired Alternate Currency stack is sold by either the Extractor Bot (Sibling) or its corresponding Scrumming Bot (Parent). All Tranches will persist under a bot’s Details > Tranches Tab.

**Functional.** Three of the four tranche kinds run. Fold Tranches spawn on a
scrum and hold the price of the sale that made them. Stack Tranches spawn on a
fold and are priced as a ladder above the buy. A three-unit scrum at 100 with a
one percent split and linear spacing returns rungs at 101, 102 and 103 carrying
one unit each. Two rungs closer than a tenth of a percent merge, so 100, 100.05
and 105 come back as 100.05 carrying two units, then 105 carrying one.

`src/trading/stack_math.py` — `split_scrum_into_tranches`

```python
def split_scrum_into_tranches(
    scrum_price: float,
    scrum_size: float,
    n_target: int,
    split_distance_pct: float = DEFAULT_INITIAL_GAP_PCT,
    spacing_mode: str = DEFAULT_SPACING_MODE,
    min_opposing_pct: float = 0.0,
    min_order_size: float = 0.0,
) -> list[Tranche]:
```

**Design intention.** Extractor Tranches are the sibling-and-parent relationship
the entry describes. The Extractor opens a position on an alternate pair, names
the tranche with an id that survives a restart, and hands the base currency back
to the parent Scrumming Bot on exit. The parent raises its own target by the
amount that arrived rather than selling it straight back out as surplus.

`src/trading/extractor_bot.py` — `ExtractorBot.tranche_id_for_position`

```python
"""Build the stable Extractor Tranche id: ``bot_id|pair|opened_at``.

The row emitter and `set_tranche_arbiter` both format
`opened_at` through this one method, so they can never format
it differently and disagree on the same id.
"""
```

Shadow Tranches do not exist; entry 9 gives the measurement and the proposal.

The queue sorts the fold tranches by their reference price, highest first, and
drops any row whose reference or unit count is not a finite number. Wire credits
ride on the tranche, which is the provenance the entry names.

Three defects stand against the Tranches tab and the rows it draws: spawned
tranches do not match the scrum that spawned them (issue #367), the list is not
visible and lifetime counters reset (issue #133), and the Units column prints a
quantity that does not exist (issue #201). One more sits behind them. The
capital reservation registry answers before a sale is placed, and of the five
bot construction sites only the two Simulator controllers hand the bot a
registry (issue #427).

### 12 - Technical Analysis Indicator Confidence Tiers

Most TA systems stack indicators additively. The Tier-4 suite organizes signals into four confidence tiers with cumulative weighting: Tier-1 (structural, highest weight), Tier-2 (confirmation, medium weight), Tier-3 (momentum), Tier-4 (context). Entries require Tier-1 + Tier-2 alignment; Tier-3/4 scale confidence but cannot override. This tier system arose out of queries with Claude Code while it was roleplaying as a TA Archetype and is only one such example where most of the other such contributions deal with bug fixes.

**Not built as tiers.** The four-tier scheme is a design. The engine has no
tier. The signal record carries an indicator name, a timeframe, a direction, a
confidence, a weight, a details map, a timestamp and an abstention flag, and
nothing else. No field names a tier, no code groups the voters into tiers, and
no rule requires a Tier-1 and Tier-2 alignment before an entry.

`src/trading/indicators/types.py` — `Signal`

```python
@dataclass
class Signal:
    """One indicator's output at a point in time."""

    indicator: str
    timeframe: str
    direction: SignalDirection
    confidence: float
    weight: float = 1.0
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    abstained: bool = False
```

**What runs instead.** A flat per-indicator weight. Each of the twelve voters
carries one number between 0.8 and 1.2, and a signal's score is its direction
times its confidence times that weight. Every vote can move the total, and none
can veto another.

`src/trading/ta_engine.py` — `DEFAULT_WEIGHTS`

```python
DEFAULT_WEIGHTS = {
    "bollinger_bands": 1.0,
    "vortex": 0.9,
    "macd": 1.2,
    "stochastic_rsi": 1.0,
    "ichimoku": 1.1,
    "volume": 0.8,
    "slingshot": 1.0,
    "adx": 1.0,
    "kaufman_er": 1.0,
    "supertrend": 1.0,
    "zscore": 0.9,
    "rsi": 0.8,
}
```

**The build this specifies.** A tier is a second map beside the weights, and the
veto is one test in the aggregator. The signal record grows one field, and it
has to go last: the record is built positionally in this tree, so inserting a
field earlier would re-bind an existing argument.

*Proposed, not present, in `src/trading/ta_engine.py`:*

```python
DEFAULT_TIERS = {
    "bollinger_bands": 1,
    "ichimoku": 1,
    "supertrend": 1,
    "macd": 2,
    "vortex": 2,
    "adx": 2,
    "stochastic_rsi": 3,
    "rsi": 3,
    "slingshot": 3,
    "volume": 4,
    "kaufman_er": 4,
    "zscore": 4,
}
```

*Proposed, not present, in `VotingEngine._aggregate`:*

```python
_lead = {s.tier for s in signals if not s.abstained and s.direction is not NEUTRAL}
if require_tier_alignment and not {1, 2} <= _lead:
    consensus_conf = 0.0
```

Issue #433 carries the build.

### 13 - Initial-Purchase-Price Floor on Folds

This rule asserts that a subsequent Fold occurring after a Scrum MUST be less than sell. This, of course, is asserted by Bollinger Band Travel, Minimum Opposing Trade Distance, Target Balance Not Zero, etc.

**Functional.** The floor runs, and it lives on the tranche. Every fold tranche
stores the price of the scrum that spawned it. The row is released only when
price has fallen to that reference multiplied by the rebuy factor, and the
factor is one minus the opposing trade distance. A one percent interval with a
six tenths fee gives a distance of 1.60 percent and a factor of 0.984, so a
tranche spawned by a sale at $100.00 folds back at $98.40 or lower.

`src/trading/scrumming/fold_tranches.py` — `_fold_eligible_tranches`

```python
return [
    t
    for t in self._fold_tranches
    if ticker_last <= float(t.get("ref", 0)) * otd_factor
]
```

**Design intention.** The same distance is held in three places so the rule
cannot be true for the bot and false for a row. The bot-wide hysteresis gate
holds it, the per-tranche filter above holds it, and each new ladder rung is
priced against it.

`src/trading/otd_math.py` — `fold_rebuy_factor_from_pct`

```python
def fold_rebuy_factor_from_pct(otd_pct: float) -> float:
    """Convert an already-clamped OTD percentage to a FOLD rebuy factor.

    Multiply a tranche's ``ref`` by this to get the HIGHEST price at
    which that tranche is still eligible to be re-bought:

        eligible  <=>  ticker.last <= ref * factor
    """
    return 1.0 - (float(otd_pct) / 100.0)
```

The lot carries its own cost basis as well as the scrum reference, and the tick
counts the rows eligible against that basis.

`src/trading/scrumming/tick_phases.py` — the lot's own basis

```python
_patent_only_eligible = sum(
    1
    for _t in self._fold_tranches
    if ticker.last
    <= float(_t.get("initial_buy_price", _t.get("ref", 0)))
)
```

One gap sits in the same path, and the function names it in its own docstring.
The fold gate wraps the distance call and falls back to a distance of zero when
a config value is not a number. At that fallback the rule is not active.

### 14 - Position Ceiling and Detonation

This setting allows a total profit cap to be set for a given position before it sells its entire or a large portion of its total value.

**Functional.** The entry covers two mechanisms. They act on opposite sides of
the cycle and both start disabled. The ceiling brakes buying. It is the anchor
target multiplied by a factor clamped between one and ten, and the fold rate
tapers as the position approaches it: full rate below half the ceiling, a linear
taper from full to a tenth across the upper half, and a hard stop at the
ceiling. The ceiling starts no sale.

`src/trading/scrumming_bot.py` — `ScrummingBot.fold_rate_taper`

```python
ratio = self.ceiling_ratio
if ratio is None:
    return 1.0
if ratio >= 1.0:
    return 0.0
if ratio < 0.5:
    return 1.0
return 1.0 - (ratio - 0.5) / 0.5 * 0.9
```

**Design intention.** Detonation sells. It requires the feature to be enabled, a
position above the anchor, and a bullish consensus at or above the confidence
minimum on the detonation timeframe, which defaults to one day. The check is
edge triggered, so one bull reversal fires it once, and a rate limit spaces the
checks. The executor then market-sells the surplus above the anchor, clears the
fold tranches and reseeds the lots. It harvests the excess above the anchor, not
the whole position.

`src/trading/scrumming_bot.py` — `ScrummingBot._check_detonation_trigger`

```python
conf_min = float(getattr(self.config, "detonation_confidence_min", 0.75))
is_bullish = (
    summary.consensus_direction == SignalDirection.BULLISH
    and summary.consensus_confidence >= conf_min
)

fired = is_bullish and not self._detonation_last_signal_bullish
self._detonation_last_signal_bullish = is_bullish
```

Both features default to off, and the ceiling multiple defaults to five.

`src/trading/container/config.py` — `BotConfig`

```python
position_ceiling_enabled: bool = False
position_ceiling_multiple: float = 5.0  # Range [1.0, 10.0]
```

Issue #336 records both pairs among the wizard
settings that never reach the bot. Issue #107 records a detonation that can fire
twice across a restart. Any earlier description reading "bearish" is wrong: the
code compares against the bullish direction.

### 15 - Proof of Accumulation (PoA)

This is another one of the larger and more distinguishing features of the platform. At this point, it is a design proposal for a blockchain that provides certified trade performance between competitors without revealing their specific strategy tunings within Acervator or their identity. When this blockchain is initiated, ZERO tokens for it will exist in the world. I intend it to be, much like BTC to 1) have a fixed supply, 2) mean something through its generation and acquisition. Tokens are only created through the PoA tournaments and defeating Token Beasts or inflicting the most damage to them in a colosseum format. Additional functions would allow PoA tokens to be socketed into the platform to change its appearance and identify a user as a victor.

**Functional.** The competition package is the Proof of Accumulation package,
and its engine runs without a screen. The engine walks a competition through
registration, active trading, submission and adjudication, and hashes each
entrant's config so a strategy proves consistency without publishing itself. A
Merkle log produces the root that stands in for the trade record.

The token ledger is append-only and hard-capped. Balances come from replaying
the log, and no operation edits one. An award that would cross the cap raises
rather than trimming, and an award id repeats at most once.

`src/competition/token_ledger.py` — `TokenLedger.award`

```python
event_id = self._event_id(bot_id, competition_id, tier.name)
if event_id in self._seen:
    return None

if self.total_minted() + tier.base_value > TOTAL_SUPPLY_CAP:
    raise OverflowError(
        f"Supply cap {TOTAL_SUPPLY_CAP:,} ACRV would be exceeded. "
        f"Only {self.remaining_ever()} tokens remain mintable."
    )
```

**Design intention.** The fixed supply is the whole point of the token, so the
cap is a constant the ledger reads rather than a policy a caller can pass. It
reads ten million.

`src/competition/season_schedule.py` — `TOTAL_SUPPLY_CAP`

```python
TOTAL_SUPPLY_CAP = 10_000_000  # Hard cap — immutable
```

Nothing in the running platform starts a competition. Every module that would
request one sits outside the running application, the retired-tab sentinels
assign nothing to the competition and testnet tabs, and the canonical tab order
lists seven tabs, none of them PoA. Issue #147 covers the tab as an initial
implementation.

`src/competition/local_testnet.py` — the in-platform chain, built every session

```python
MAX_SUPPLY_WEI = TOTAL_SUPPLY_CAP * (10**TOKEN_DECIMALS)
```

The trophy generator draws the trophy as vector art and letters SOLVE ET COAGULA
around its rim. No module imports it. Token Beasts and the colosseum appear in
no Python file at all.

### 16 - Technical Analysis, Goodness of Fit, and the Confidence Index

The Confidence Index is the collated result of the 12-indicator Voting Panel and emulates the concept of a set of features (market structures / indicators) being read by a system having similar measurements for a given or expected or past action i.e. a Fold will always have a certain number of indicators voting bearish before its released for execution.

**Functional.** The Confidence Index runs. The voting engine builds twelve
voters and holds twelve weights, and both count twelve when driven. The net is
the bullish score minus the bearish score, and the confidence is the absolute
net divided by the summed weight of the voters that did not abstain. Two bulls
at weights one and two against one bear at weight one give a net of 2.0 and a
confidence of 0.5. A single bull beside an abstainer of weight three gives 1.0,
not 0.25, which shows the abstainer leaving the denominator.

`src/trading/ta_engine.py` — `VotingEngine._aggregate`

```python
net = bull_score - bear_score

voted_weight = sum(s.weight for s in signals if not s.abstained)
consensus_conf = abs(net) / voted_weight if voted_weight > 0.0 else 0.0
```

**Design intention.** Confidence measures the breadth of agreement across the
panel, not the strength of one reading. That is why an abstention has to be
declared rather than inferred: an indicator with too little history returns a
fabricated middle reading, and counting it would dilute a real consensus.

`src/trading/indicators/types.py` — `Signal.weighted_score`

```python
@property
def weighted_score(self) -> float:
    """Signed score: direction * confidence * weight."""
    return self.direction.value * self.confidence * self.weight
```

**Goodness of fit is not built.** The phrase names the work of comparing the
Simulator against the live platform, and the criterion for that comparison is
gates latching identically on the same data. The measure has no settled
definition yet and nothing here to attach it to, so nothing is proposed. Issue
#117 carries it.

In development.

Two standing defects touch the panel. The API Interaction Log still tells the
operator that seven indicators read the candles (issue #417), and eight
indicator implementations depart from their published formulae (issue #414).

### 17 - Tiered Strategy Validation and Workflow

Acervator has many unique characteristics and many of these are rooted in attempting to protect an investor from themselves. As such, I have designed a means of self-contained strategy testing that is meant to educate and validate before any attempt at using the platform against actual personal funds is ever attempted. Some may be confident or skilled enough to skip these protective steps. That is an individual user choice. I did not follow this workflow while developing it but I know exactly how my strategy works and when it is not. Given this, the intended workflow for a new user of Acervator should be Simulator > Paper Trader > Live. The system is configured so that the relevant operational elements, such as the Market Inspector, can inject Simulator and Paper equivalents into the appropriate Bot Swarm layers or bot fleet under the respective tab.

**Functional.** Three of the four stages exist. The Market Inspector tab and the
Simulator tab are both built and inserted, and the Simulator is handed the
Inspector's proposals at build time, so a proposal reaches the back test. Live
is the Trading tab, and it is first in the canonical order.

`src/gui/main_tabs/main_window_surface.py` — `CANONICAL_TAB_ORDER`

```python
CANONICAL_TAB_ORDER = (
    TRADING_TAB,
    MARKET_INSPECTOR_TAB,
    BOT_SWARM_TAB,
    ASSET_CHARTS_TAB,
    HISTORY_TAB,
    SIMULATOR_TAB,
    CONSOLE_TAB,
)
```

**The Paper stage is not built.** No file named for it exists in the tree, and
none was ever committed on any branch. A history query across every commit
returns no such path, while the same query returns two entries for the bot
brain. The only tracked path matching the word is a manual page. The code states
the same in its own defaults.

`src/gui/main_tabs/stock_main_window_surface.py` — the declared default

```python
paper_trader_available: bool = False,
paper_trader_error: Any = "No module named 'src.gui.paper_trader_tab'",
```

**Design intention.** Paper is the stage that proves a strategy against the real
market in real time before real money reaches it, and its defining property is
that it runs at the market's own pace. What it should share with Live and what
it must fork is settled: one trading logic, three data sources. What it should
not do is import the live stateful shells. That is a build, not a repair, and it
is gated behind the Simulator rebuild.

Issue #19 covers the build-out. Two surfaces that tell the operator a Paper
Trader is present are issues #422 and #426. Issue #117 tracks the Simulator
rebuild that gates it.

Today the workflow runs Market Inspector, then Simulator, then Live. The Paper
stage is an intention.

---

## Core mechanisms

The catalogue above describes each of these at length. This is the index into
it.

- **Scrum/Fold cycle** — harvest the excess above target, buy back cheaper
- **Profit folding** — each fold permanently raises the target, compounding growth
- **Hunger and Satiety dual index** — a delta-driven aggression scalar
- **Provenance fold queue** — per-tranche independent fold execution
- **BB midline gate** — scrum only above the midline, fold only below it
- **Bollinger Band bullseye** — rapid-fire execution when price touches the band exactly
- **Band travel detection** — triggers a harvest once price has crossed a set share of the band width since the last trade
- **Landing strip detection** — Heikin-Ashi consolidation at a band extreme as a high-confidence reversal signal
- **Hedge rebalance** — separate reserve buys during delta depletion in bear conditions
- **Fair Value Gap magnets** — FVG-aware fold placement and scrum amplification
- **Multi-timeframe regime bias** — a 4h phantom signal informs 1h execution
- **Twelve-indicator consensus** — the Indicator Voting Panel, across up to five timeframes

One more, **Boost Fold**, is designed as an aggressive fold triggered when the
z-score reads extreme. It runs in the stock accumulation bot. The crypto engine
declares its four fields and never reads them, so a crypto bot takes no boost
fold. The manual sets out
[both](docs/manual/06-trading-tab.md#two-mechanisms-with-no-control-on-this-tab).

---

## Philosophy

Most trading tools are built for people who already have money and access.
Acervator was built for everyone else.

The strategy requires no prediction skill, no market timing, no insider
information. It requires capital, patience, and a systematic approach. The
accumulation guarantee — that every completed Scrum/Fold cycle results in more
asset than was sold — is structural, not statistical.

The inventor does not experience this as something he built. It arrived. It
belongs to the people it was built for.

---

## The rest of the manual

The manual lives under [`docs/manual/`](docs/manual/README.md). Together its
pages are larger than a README GitHub will render, and the front page is cut at
512,000 bytes. The parts above are therefore printed here, and the parts below
are one click away. Every row is one section, with its own link.

The rendered book is [`docs/Acervator-Product-Manual.pdf`](docs/Acervator-Product-Manual.pdf),
built from the same pages.

### Part 3 — System Architecture and Features Catalogue

**[System Architecture and Features Catalogue](docs/manual/06-trading-tab.md)**

- [Trading Tab](docs/manual/06-trading-tab.md#trading-tab)

**[Indicator Voting Panel](docs/manual/07-indicators.md)**

- [The twelve voters](docs/manual/07-indicators.md#the-twelve-voters)
- [Indicator formulae](docs/manual/07-indicators.md#indicator-formulae)
- [Departures from the published maths](docs/manual/07-indicators.md#departures-from-the-published-maths)
- [Trading gate logic chain](docs/manual/07-indicators.md#trading-gate-logic-chain)

**[Subsystem Tabs](docs/manual/08-tabs.md)**

- [Main Window](docs/manual/08-tabs.md#main-window)
- [Simulator Tab (Hot Mess; Complete Rebuild In Progress)](docs/manual/08-tabs.md#simulator-tab-hot-mess-complete-rebuild-in-progress)
- [Paper Trader Tab (To Be Built)](docs/manual/08-tabs.md#paper-trader-tab-to-be-built)
- [Proof of Accumulation (Anonymized Trading Tournaments Via Blockchain)](docs/manual/08-tabs.md#proof-of-accumulation-anonymized-trading-tournaments-via-blockchain)
- [Market Inspector Tab](docs/manual/08-tabs.md#market-inspector-tab)
- [Bot Swarm Tab](docs/manual/08-tabs.md#bot-swarm-tab)
- [Asset Charts](docs/manual/08-tabs.md#asset-charts)
- [History Tab](docs/manual/08-tabs.md#history-tab)
- [Console](docs/manual/08-tabs.md#console)
- [System Status Tab (To Be Built)](docs/manual/08-tabs.md#system-status-tab-to-be-built)
- [Settings](docs/manual/08-tabs.md#settings)
- [Converting the Interface to React](docs/manual/08-tabs.md#converting-the-interface-to-react)

**[Subsystem Detail](docs/manual/08-tabs/README.md)**

- [Contents](docs/manual/08-tabs/README.md#contents)
- [The live tab set](docs/manual/08-tabs/README.md#the-live-tab-set)
- [How a screen reaches its renderer](docs/manual/08-tabs/README.md#how-a-screen-reaches-its-renderer)

**[Portfolio Information Panels](docs/manual/08-tabs/portfolio-panels.md)**

- [What builds it](docs/manual/08-tabs/portfolio-panels.md#what-builds-it)
- [Left: the spendable columns](docs/manual/08-tabs/portfolio-panels.md#left-the-spendable-columns)
- [Right: the five counter cards](docs/manual/08-tabs/portfolio-panels.md#right-the-five-counter-cards)
- [Privacy](docs/manual/08-tabs/portfolio-panels.md#privacy)
- [Where the numbers come from](docs/manual/08-tabs/portfolio-panels.md#where-the-numbers-come-from)
- [Hiding](docs/manual/08-tabs/portfolio-panels.md#hiding)
- [Bridge](docs/manual/08-tabs/portfolio-panels.md#bridge)

**[Market Inspector Tab](docs/manual/08-tabs/market-inspector.md)**

- [What builds it](docs/manual/08-tabs/market-inspector.md#what-builds-it)
- [Left half: the scanner](docs/manual/08-tabs/market-inspector.md#left-half-the-scanner)
- [Where the analysis happens](docs/manual/08-tabs/market-inspector.md#where-the-analysis-happens)
- [Fetching](docs/manual/08-tabs/market-inspector.md#fetching)
- [What a scan reports](docs/manual/08-tabs/market-inspector.md#what-a-scan-reports)
- [Right half: topology proposals](docs/manual/08-tabs/market-inspector.md#right-half-topology-proposals)
- [Dismissal](docs/manual/08-tabs/market-inspector.md#dismissal)
- [Adopt](docs/manual/08-tabs/market-inspector.md#adopt)
- [Exchange comparison arbitrage](docs/manual/08-tabs/market-inspector.md#exchange-comparison-arbitrage)
- [Bridge](docs/manual/08-tabs/market-inspector.md#bridge)

**[Bot Swarm Tab](docs/manual/08-tabs/bot-swarm.md)**

- [What builds it](docs/manual/08-tabs/bot-swarm.md#what-builds-it)
- [The nodes](docs/manual/08-tabs/bot-swarm.md#the-nodes)
- [Drawing a wire](docs/manual/08-tabs/bot-swarm.md#drawing-a-wire)
- [Routing the profit](docs/manual/08-tabs/bot-swarm.md#routing-the-profit)
- [Landing the profit](docs/manual/08-tabs/bot-swarm.md#landing-the-profit)
- [The tranche book](docs/manual/08-tabs/bot-swarm.md#the-tranche-book)
- [Where the fleet comes from](docs/manual/08-tabs/bot-swarm.md#where-the-fleet-comes-from)
- [The list view](docs/manual/08-tabs/bot-swarm.md#the-list-view)
- [Capital claims](docs/manual/08-tabs/bot-swarm.md#capital-claims)
- [Bridge](docs/manual/08-tabs/bot-swarm.md#bridge)

**[Asset Charts](docs/manual/08-tabs/asset-charts.md)**

- [What builds it](docs/manual/08-tabs/asset-charts.md#what-builds-it)
- [The chart widget](docs/manual/08-tabs/asset-charts.md#the-chart-widget)
- [Indicators on the chart](docs/manual/08-tabs/asset-charts.md#indicators-on-the-chart)
- [Where the candles come from](docs/manual/08-tabs/asset-charts.md#where-the-candles-come-from)
- [The other chart](docs/manual/08-tabs/asset-charts.md#the-other-chart)
- [Bridge](docs/manual/08-tabs/asset-charts.md#bridge)

**[History Tab](docs/manual/08-tabs/history.md)**

- [What builds it](docs/manual/08-tabs/history.md#what-builds-it)
- [Fetching](docs/manual/08-tabs/history.md#fetching)
- [Filtering, paging, export](docs/manual/08-tabs/history.md#filtering-paging-export)
- [Where the cell values come from](docs/manual/08-tabs/history.md#where-the-cell-values-come-from)
- [Grading](docs/manual/08-tabs/history.md#grading)
- [Gate analysis](docs/manual/08-tabs/history.md#gate-analysis)
- [The renderer](docs/manual/08-tabs/history.md#the-renderer)
- [The Simulator front-load](docs/manual/08-tabs/history.md#the-simulator-front-load)
- [Paper History](docs/manual/08-tabs/history.md#paper-history)
- [Bridge](docs/manual/08-tabs/history.md#bridge)

**[Console](docs/manual/08-tabs/console.md)**

- [What builds it](docs/manual/08-tabs/console.md#what-builds-it)
- [Upper pane: the Python log](docs/manual/08-tabs/console.md#upper-pane-the-python-log)
- [Pausing](docs/manual/08-tabs/console.md#pausing)
- [Lower pane: the Emitter Network](docs/manual/08-tabs/console.md#lower-pane-the-emitter-network)
- [Where the lower pane goes](docs/manual/08-tabs/console.md#where-the-lower-pane-goes)
- [Bridge](docs/manual/08-tabs/console.md#bridge)

**[System Status Tab](docs/manual/08-tabs/system-status.md)**

- [Half one: the Emitter Network](docs/manual/08-tabs/system-status.md#half-one-the-emitter-network)
- [Half two: the Watchdog](docs/manual/08-tabs/system-status.md#half-two-the-watchdog)
- [Until the tab lands](docs/manual/08-tabs/system-status.md#until-the-tab-lands)

**[Settings](docs/manual/08-tabs/settings.md)**

- [The eleven pages](docs/manual/08-tabs/settings.md#the-eleven-pages)
- [What each page persists](docs/manual/08-tabs/settings.md#what-each-page-persists)
- [Settings, User page](docs/manual/08-tabs/settings.md#settings-user-page)
- [Settings, Exchanges page](docs/manual/08-tabs/settings.md#settings-exchanges-page)
- [Bridge](docs/manual/08-tabs/settings.md#bridge)

**[The Promotion Pipeline](docs/manual/08-tabs/promotion-pipeline.md)**

- [What each step contributes](docs/manual/08-tabs/promotion-pipeline.md#what-each-step-contributes)
- [One logic, three data sources](docs/manual/08-tabs/promotion-pipeline.md#one-logic-three-data-sources)
- [The dashed edge](docs/manual/08-tabs/promotion-pipeline.md#the-dashed-edge)
- [Where the chain breaks today](docs/manual/08-tabs/promotion-pipeline.md#where-the-chain-breaks-today)

### Part 4 — Live and Supporting Evidence

**[The Year-to-Date Record and Exchange Test Coverage](docs/manual/13-live-evidence.md)**

- [The venue holds the authority](docs/manual/13-live-evidence.md#the-venue-holds-the-authority)
- [Readers of the record](docs/manual/13-live-evidence.md#readers-of-the-record)
- [The connectors](docs/manual/13-live-evidence.md#the-connectors)
- [What the exchange tests exercise](docs/manual/13-live-evidence.md#what-the-exchange-tests-exercise)
- [How a test stands in for a venue](docs/manual/13-live-evidence.md#how-a-test-stands-in-for-a-venue)
- [The four refusals around an exchange call](docs/manual/13-live-evidence.md#the-four-refusals-around-an-exchange-call)
- [The simulation battery](docs/manual/13-live-evidence.md#the-simulation-battery)
- [Where a figure and a run carry less than they read](docs/manual/13-live-evidence.md#where-a-figure-and-a-run-carry-less-than-they-read)

### Part 5 — The HOP Protocol and the Rules Registry

**[Conceptual Hopscotch](docs/manual/11-hop-protocol-and-rules-registry.md)**

- [The handoff file](docs/manual/11-hop-protocol-and-rules-registry.md#the-handoff-file)
- [What the drift check measures](docs/manual/11-hop-protocol-and-rules-registry.md#what-the-drift-check-measures)
- [The rules registry](docs/manual/11-hop-protocol-and-rules-registry.md#the-rules-registry)
- [Version one of the protocol](docs/manual/11-hop-protocol-and-rules-registry.md#version-one-of-the-protocol)
- [Version two of the protocol](docs/manual/11-hop-protocol-and-rules-registry.md#version-two-of-the-protocol)
- [Related parts](docs/manual/11-hop-protocol-and-rules-registry.md#related-parts)

### Part 6 — ADR Index and Glossary

**[Decision Records and Glossary](docs/manual/12-adr-index-and-glossary.md)**

- [Where a decision is recorded](docs/manual/12-adr-index-and-glossary.md#where-a-decision-is-recorded)
- [Glossary](docs/manual/12-adr-index-and-glossary.md#glossary)
- [The operator's own words](docs/manual/12-adr-index-and-glossary.md#the-operators-own-words)

### Part 7 — Recent Updates and Version Tracking

**[Version Tracking](docs/manual/09-updates-and-versioning.md)**

- [Recent updates](docs/manual/09-updates-and-versioning.md#recent-updates)
- [Where the number comes from](docs/manual/09-updates-and-versioning.md#where-the-number-comes-from)
- [What the string says](docs/manual/09-updates-and-versioning.md#what-the-string-says)
- [The six readers](docs/manual/09-updates-and-versioning.md#the-six-readers)
- [What a frozen bundle carries](docs/manual/09-updates-and-versioning.md#what-a-frozen-bundle-carries)
- [A version that moves while the suite runs](docs/manual/09-updates-and-versioning.md#a-version-that-moves-while-the-suite-runs)
- [The release gate](docs/manual/09-updates-and-versioning.md#the-release-gate)

### Part 8 — The Development Chronicle

**[The Development Chronicle](docs/manual/14-development-chronicle.md)**

- [April and May: 127 sessions, and not one diff](docs/manual/14-development-chronicle.md#april-and-may-127-sessions-and-not-one-diff)
- [June: the record thins out and then stops](docs/manual/14-development-chronicle.md#june-the-record-thins-out-and-then-stops)
- [4 to 25 August: the changelog nobody noticed had gone](docs/manual/14-development-chronicle.md#4-to-25-august-the-changelog-nobody-noticed-had-gone)
- [18 August: the upload](docs/manual/14-development-chronicle.md#18-august-the-upload)
- [19 to 22 August: reading it for the first time](docs/manual/14-development-chronicle.md#19-to-22-august-reading-it-for-the-first-time)
- [23 to 25 August: gates that could not say no](docs/manual/14-development-chronicle.md#23-to-25-august-gates-that-could-not-say-no)
- [24 August: nine months of green over a dead Simulator](docs/manual/14-development-chronicle.md#24-august-nine-months-of-green-over-a-dead-simulator)
- [25 August: joining two histories, and a scrub that swung too hard](docs/manual/14-development-chronicle.md#25-august-joining-two-histories-and-a-scrub-that-swung-too-hard)
- [26 to 27 August: the demolition](docs/manual/14-development-chronicle.md#26-to-27-august-the-demolition)
- [27 to 28 August: the version number that went backwards](docs/manual/14-development-chronicle.md#27-to-28-august-the-version-number-that-went-backwards)
- [29 August onward: converting the interface by measurement](docs/manual/14-development-chronicle.md#29-august-onward-converting-the-interface-by-measurement)
- [1 to 5 September: reading every comment in the tree](docs/manual/14-development-chronicle.md#1-to-5-september-reading-every-comment-in-the-tree)
- [The suppression markers, and why one green says nothing about another](docs/manual/14-development-chronicle.md#the-suppression-markers-and-why-one-green-says-nothing-about-another)
- [4 September: pointing the instruments at themselves](docs/manual/14-development-chronicle.md#4-september-pointing-the-instruments-at-themselves)
- [Two defects worth the whole audit](docs/manual/14-development-chronicle.md#two-defects-worth-the-whole-audit)
- [Where the work stands, 5 September 2026](docs/manual/14-development-chronicle.md#where-the-work-stands-5-september-2026)
- [Two repairs this repository cannot show you](docs/manual/14-development-chronicle.md#two-repairs-this-repository-cannot-show-you)
- [What the record cannot show](docs/manual/14-development-chronicle.md#what-the-record-cannot-show)
- [A note on the two archived records](docs/manual/14-development-chronicle.md#a-note-on-the-two-archived-records)

### The figure inventory

**[Figure Inventory](docs/manual/FIGURES.md)**

- [Where the figures are written](docs/manual/FIGURES.md#where-the-figures-are-written)
- [Inventory](docs/manual/FIGURES.md#inventory)
- [Pages that carry a figure and no text](docs/manual/FIGURES.md#pages-that-carry-a-figure-and-no-text)
- [Where each figure is described](docs/manual/FIGURES.md#where-each-figure-is-described)
- [The second figure set — Part 9's VWAP charts](docs/manual/FIGURES.md#the-second-figure-set--part-9s-vwap-charts)
- [What produces each set](docs/manual/FIGURES.md#what-produces-each-set)

### Three subsystems that are not built

The manual carries a design page for each of these. None of the three is built,
so none of them is mapped above.

**Simulator.** His own heading for it reads *Simulator Tab (Hot Mess; Complete
Rebuild In Progress)*. It is not built.

In development. Issue [#117](https://github.com/Acervator-LLC/ACERVATOR/issues/117).

**Paper Trader.** His own heading for it reads *Paper Trader Tab (To Be
Built)*. Scaffolding at best.

In development. Issue [#19](https://github.com/Acervator-LLC/ACERVATOR/issues/19).

**Proof of Accumulation.** Scaffolding at best. Neither of its two screens is
built.

In development. Issue [#147](https://github.com/Acervator-LLC/ACERVATOR/issues/147).

### Part 9 — Live Trade History

Part 9 rests on the operator's own venue export: a year of live fills, the 39
VWAP charts drawn from them, and the per-trade grading and gate analysis behind
each one. That is private trading data. It is not published here, and no figure
derived from it appears on this page. The section exists in the private manual.

---

## Installation

Python 3.14, pinned in `.python-version`.

```bash
git clone https://github.com/Acervator-LLC/ACERVATOR.git
cd ACERVATOR
pip install -e .
python main.py
```

`pyproject.toml` is the only place a package name is written. Its dependencies
table holds the twelve packages the platform always needs, and its
optional-dependencies table holds nine named extras. No requirements file sits
in the tree to install from.

```bash
pip install -e ".[report]"    # PDF sweep report — reportlab
pip install -e ".[charts]"    # chart and PDF tokens — matplotlib
pip install -e ".[monitor]"   # live monitor HTTP client — httpx
pip install -e ".[contracts]" # the Solidity toolchain
pip install -e ".[display]"   # AcervatorOS mini panels — Raspberry Pi
pip install -e ".[build]"     # PyInstaller host
pip install -e ".[dev]"       # ruff, mypy, bandit, vulture, pytest, stubs
```

One of the twelve is psutil. Nuclear Mode reads processor load through it, and
without it there is no load probe at all — the run caps its own load multiplier
rather than reading the load as zero.

Every build and deployment script asks one tool for the list rather than
carrying a copy of it, so a package added to `pyproject.toml` reaches the
Windows and Mac builds, the launcher and the kiosk install and update scripts
at once. The resolved transitive set it produced is under `requirements/`, one
file per platform and interpreter.

```
python -m tools.deps requirements <consumer>     what to install
python -m tools.deps lock                        writes requirements/
```

**Nothing the platform runs is written into this repository.** State lives
under `~/.acervator/` and every log under `~/.acervator_logs/`. No run writes a
`logs/` directory into the source tree.

---

## The development harness

Acervator is built with an AI co-developer under a harness that refuses work
rather than trusting it. The harness lives in `dev_harness/`, and the rules the
operator gives the agent live under `.claude/skills/`.

| Component | What it does |
| --------- | ------------ |
| Archetypes | `dev_harness/harness/coding_archetype.py`, `docs_archetype.py`, `gui_archetype.py`, `ta_archetype.py` and `watchdog_archetype.py`. Each reads one file and returns `passed` with its findings. A `passed` of false is invalid work, and fewer findings than last time is not a pass. |
| Rules | `dev_harness/harness/rules/` — the hallucination, numeric-guard, scaffolding and slop detectors the archetypes run. |
| Agents | `dev_harness/agents/` and `dev_harness/touchset.py`, which name the files a change reached. |
| Release gate | `python -m dev_harness.harness.check_release_readiness` runs the suite and prints its verdict. No version banner and no changelog entry moves before that line appears. |

An earlier governance harness, SADP, was retired. Documents under
`docs/engineering-notes/` and `docs-archive/llm-session-history/` still
describe it. They are historical records and were true when written.

---

## Contributing

Built by one person, so the edge cases one person finds are limited by one
person's perspective. If you find a market condition where it fails, document
it, open an issue, submit a fix. The next version of Acervator will be built by
everyone.

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting a pull
request.

---

## Disclaimer

This software is for educational and research purposes. Simulated results —
including the 738-sim, 96.9%, +$78.0B figures in
[Part 4](docs/manual/13-live-evidence.md#the-simulation-battery) — do not
guarantee live trading performance. You are solely responsible for any trading
decision made using this software. See [`DISCLAIMER.md`](DISCLAIMER.md).

---

## License

Apache License 2.0. See [`LICENSE`](LICENSE) for the full terms.

Copyright 2025–2026 Anthony L. Brown, Ekthelius the Accumulator.
