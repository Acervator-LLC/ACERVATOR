# Step 9 — Choose the engine

One step of the [New User Procedure](README.md) how-to.

![Press Accumulation Trading, then Next. The wizard opens Select Asset Pair.](figures/step-9-choose-the-engine.png)

**Press Accumulation Trading (Scrumming), then Next.**

The New Bot button opens this wizard on Trading Mode. Next opens Select Asset
Pair.

The page offers two engines and the bot keeps the one picked here. The wizard
asks once. A running bot's own settings screen offers no way to swap it.

Accumulation Trading is the engine this product is built around. It holds one
asset. It sells the part of the position that has risen above a dollar target,
and it buys back more of the asset when price falls. Each finished round leaves
the bot holding more of the asset than it held before. Twelve indicators vote on
when to sell and when to buy.

Base Currency Extractor is the other engine. It grows a pool of one currency by
sending small amounts into many other markets at once. It closes a position only
when the exit returns more of the pool currency than it spent. It runs no shadow
bots, and it is not what a first bot wants.

The choice changes the pages that follow. Accumulation Trading asks for one pair
next, then for the settings the next nine steps cover, then for shadow bots. The
Extractor asks for a pool instead of a pair, and the wizard finishes without ever
showing the shadow-bot page.

Every bot in the live fleet runs Accumulation Trading, all 38 of them. That is
what this how-to follows from here on.
