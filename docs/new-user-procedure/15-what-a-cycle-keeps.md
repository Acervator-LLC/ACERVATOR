# Step 15 — What a cycle keeps

One step of the [New User Procedure](README.md) how-to.

![Scrum Fold Ratio opens at 100 %.](figures/step-15-what-a-cycle-keeps.png)

**The last three rows decide what a finished cycle keeps.**

Scrum Fold Ratio opens at 100 % and sets how much of a sale's profit is queued
to buy back in. The manual calls it the share redistributed to the bot's own
organic compounding.

Max Target Growth % opens at 1.00 % and caps how far Target Balance may grow in
one market cycle. The manual names it the organic compounding mechanic.

Trading Fee % opens at 0.60 % and holds the venue's fee per side. The manual
says it is added to the minimum opposing trade distance, so a bot does not lose
its gains to fees in a tight market.

Scrum Fold Ratio accepts 1 % to 100 %. At 100 % every dollar a sale raised goes
back into the queue waiting to buy the dip, which accumulates the most and leaves
the least cash in hand. Lower it and the difference is skimmed out of the queue
and kept as cash, which is the safer choice when price keeps falling after a sale
and the queue would otherwise spend everything on the way down. The live fleet is
split here: 30 bots run 100 %, and 8 run 50 %. The field opens at 100 %.

Max Target Growth % accepts 0 % to 100 %, and it is the only thing in the program
allowed to raise Target Balance. At 1 % a cycle may lift the line by one percent
of itself and no more. At 0 % the line is frozen and the bot accumulates the asset
without ever trading against a larger figure. A large setting here lets one good
cycle commit far more money than the reader signed up for, which is why all 38
live bots run 1.00 %, the figure the field opens at.

Trading Fee % accepts 0 % to 5 %, and it is the reader's own venue fee per side,
not a charge this program makes. The program adds it to the Opposing Trade
Interval from four steps back, and the sum is the real distance between opposite
trades. Enter it below the fee actually charged and the gap stops covering the
round trip, so trades that look profitable finish behind. Rounding it up is
cheap insurance. The live fleet is split: 24 bots run 1.60 % and 14 run 0.60 %.
The field opens at 0.60 %, which is the top tier at one venue, and a reader whose
venue charges more should say so here.

Scrumming Settings ends here. One group further down the page carries the last
step on it.
