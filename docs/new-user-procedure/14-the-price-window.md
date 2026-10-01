# Step 14 — The price window

One step of the [New User Procedure](README.md) how-to.

![Max Entry Price opens at $ 0.00000000.](figures/step-14-the-price-window.png)

**Leave Max Entry Price and Min Entry Price at zero.**

These two rows put a ceiling and a floor on the price at which the bot may open
its position. Zero means no limit, which is how a fresh install opens both.

The manual gives each one a job. Max Entry Price is the price at which the bot
will attempt its opening buy when it does not already hold enough of the asset.
Min Entry Price is the price at which it will attempt its opening sale when it
does. Only the buy side reads either number, so neither one can stop a sale.
