# Step 12 — What it watches

One step of the [New User Procedure](README.md) how-to.

![TA Timeframe opens on 1h.](figures/step-12-what-it-watches.png)

**Leave TA Timeframe on 1h.**

TA Timeframe is the price chart the bot watches to decide a trade. The manual
calls it the timeframe at which the bot operates. The list offered here is cut
down to the granularities the venue picked on the last page supports.

The two rows above it set how that chart is read. BB Tolerance opens at 1.00 %
and sets how close to a Bollinger Band price has to come before a trade can
happen. Landing Strip Candles opens at 3 and sets how many tight candles in a
row confirm a Landing Strip. The manual states three as the minimum, and says a
longer strip has historically been the stronger signal.
