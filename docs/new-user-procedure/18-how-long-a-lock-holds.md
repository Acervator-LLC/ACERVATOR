# Step 18 — How long a lock holds

One step of the [New User Procedure](README.md) how-to.

![Candles to lock opens at 2.](figures/step-18-how-long-a-lock-holds.png)

**Leave Candles to lock at 2.**

Higher-TF Lock Duration is the one group on this page. It sits under the
timeframe row, below the box the step before covers.

A lock is a hold placed by a slower chart. The manual says this figure sets how
many candles such a lock keeps an opposing trade back for. The box runs from 1
to 10 and opens at 2. It stays usable whether or not phantom bots are enabled,
so a newcomer reaches it on the way to Finish.

**Nothing in the program creates a lock yet.** The manual says so: nothing calls
the step that adds one, so the countdown never starts and the lock test answers
no on every pass.

The manual also records that a new bot never receives this figure. Its own
counter opens at 2 by itself, and only the Bot Settings screen writes the figure
onto a bot that is already running. Leaving the box alone changes nothing a
first bot does.
