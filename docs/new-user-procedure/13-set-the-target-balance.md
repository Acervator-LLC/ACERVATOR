# Step 13 — Set the Target Balance

One step of the [New User Procedure](README.md) how-to.

![Target Balance opens at $ 200.00.](figures/step-13-set-the-target-balance.png)

**Set Target Balance.**

Target Balance is the balance this bot trades against. A fresh install opens it
at $ 200.00. The manual calls it the intended starting and locked value for the
position the bot controls.

This is the one figure in the group worth setting before a first bot runs. Three
more steps stay on this page after it.

The figure is a line, not a budget. The bot compares what its position is worth
right now against this line. Above the line it sells the excess. Below the line
it buys back toward it. Every automatic buy is sized by the distance to this
line, so the figure decides how much money a single bot ever puts to work.

The box accepts $ 1.00 up to $ 1,000,000.00. Two steps on, Max Target Growth %
caps how far this figure may climb on its own, so the position can never grow
past the line plus that cap. Nothing else in the program raises it.

A figure larger than the money actually sitting at the venue is the common first
mistake. The bot tries to buy up to the line, the venue refuses, and the Console
fills with refusals. A figure too small is the quieter mistake. Each round moves
so little that the venue's fee takes most of what the round earned, and the
smallest order the venue accepts may stop the bot trading at all.

The live fleet runs ten different figures across its 38 bots, chosen per market
rather than once for the fleet. The sound way to pick the first one is to decide
what a reader is content to have working in one market, confirm that money is
settled at the venue, and name that. It can be raised later from the bot's own
settings screen without stopping the bot.
