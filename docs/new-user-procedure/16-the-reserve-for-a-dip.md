# Step 16 — The reserve for a dip

One step of the [New User Procedure](README.md) how-to.

![Hedge Rebalance Active opens ticked. Press Next.](figures/step-16-the-reserve-for-a-dip.png)

**Leave Hedge Rebalance Active ticked, then press Next.**

Hedge Rebalance is a group further down the same page, below Advanced Scrumming.
It holds money the bot keeps apart from Target Balance.

The tick decides whether the bot may use that money. The manual says it
determines whether price drifting below the first entry price can draw on a
limited amount of funds at bearish thresholds. Put plainly: when price falls, a
ticked box lets the bot buy from this reserve instead of from the balance it is
accumulating against.

Hedge Balance is the size of the reserve. A fresh install opens it at $ 200.00.
The manual calls it the limit on the extra money one bot is allowed to absorb
when price drifts below its first entry price. One such buy spends half of what
the reserve holds at that moment.

A reserve of zero is not an off switch. The manual is explicit about it: zero is
an empty reserve that never refills, and whatever the bot already holds stays
spendable until it drains. Clearing the tick is what turns the hedge off.

Next leaves Trading Parameters and opens Phantom Bots.
