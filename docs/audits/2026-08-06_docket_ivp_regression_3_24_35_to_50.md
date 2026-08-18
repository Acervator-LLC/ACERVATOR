# DOCKET — the Indicator Voting Panel renders no TA (v3.24.35 → v3.24.50)

**Filed** 2026-08-06 · **Reported by** operator, with screenshot
**Status** OPEN — investigation running, prime suspect is my own change
**Grade** `T-1c` → **P2** (false/absent information, automatic, but VISIBLE)

---

## 1. The report

> "Why and how did you break the Indicator Voting Panel between versions
> 3.24.35 and 3.24.50?"

Screenshot: the panel header reads **"No TA data — waiting for the TA
engine"**. Both tables are empty, showing "Awaiting TA signals…". A real
bot is selected (`BTC/USD [7c39c7a2]`).

The same screenshot's Activity Log shows TA **is** being computed:

```
[21:16:51] [XRP/b457] TA Vote: BEARISH (conf=0.12, B:3/N:5/S:4) | BB pos=0.58
```

So the data exists in the process and is not reaching the panel.

## 2. The prime suspect is mine

That header string is **my** text. `_render_no_data("waiting for the TA
engine")` was added by cascade C51 (`b24f350`). The panel is displaying
exactly the state I built for it.

C51 gated `_generate_demo_ta` so it refuses to fabricate TA for a real
bot. That was correct and I stand behind it: the panel had been running
the real `VotingEngine` over invented candles and rendering the result
under the real bot's symbol, deterministically per bot so it never even
flickered.

**What I did not do is verify that real TA would replace it.**

`_render_no_data` does not merely decline to fabricate. It calls
`update_data({}, ...)`, which clears `self._data` and sets both tables to
zero rows. It is an active wipe, not a passive abstention.

## 3. The two possibilities, which have different repairs

This distinction is the whole investigation and must not be collapsed:

**(a) C51 CAUSED it.** A no-data render lands *after* a good real render
and blanks it. `force_refresh` is the candidate: it sets
`self._data = {}` and then calls `_generate_demo_ta()` unconditionally,
so post-C51 it clears the panel and the gate then declines to refill.
Before C51 it refilled with fabricated data, which would have masked the
wipe completely.

**(b) C51 REVEALED a pre-existing break.** The real feed
(`main_window.py:5055`) is gated on `bot._last_summary`, which is
assigned in only two places, both inside `ScrummingBot.tick()` —
`:5841`, nested under a near-empty-position branch, and `:6076`, under
`if len(candles) >= 30`. If that chain does not complete for the selected
bot, the real feed never fires and fabricated data was the *only* thing
this panel ever displayed.

If (b) is true, then this panel has never shown real TA, and C51 did not
break it — C51 stopped it lying and exposed that it was never wired.

Both may hold simultaneously. The investigation is instructed to keep
them separate.

## 4. What I got wrong, stated plainly

C51's tests included what I called positive controls. They asserted:

- the demo generator still produces data in a demo context
- the fabricated output looks real (indicator names, confidences)
- it is deterministic per bot
- a real bot receives **no fabricated data** on all three entry paths
- sim mode still works

Every one of those passed, and every one of them was about the
**fabrication path**. Not one asserted that a real bot with real TA ends
up with a **populated** panel. I verified that I had removed the lie. I
never verified that the truth arrived.

That is precisely the discipline I had been applying elsewhere in this
same cascade — "a measurement is not a finding until its instrument has
a positive control" — and I did not apply it to the thing the panel is
actually for. The correct control was: seed a bot with real
`_last_summary` data, drive the real feed, and assert the tables are
non-empty. It did not exist, so nothing failed when the panel went dark.

## 5. Why the severity is P2 rather than P0

It is `T` (the operator is denied information they act on) and
reachability `1` (automatic). But detectability is `c` — **visible**. The
panel says, in plain language, that it has no data. It is not pretending
to have data it lacks.

That is a meaningful improvement on the pre-C51 state, which was `T-1a`:
confidently wrong, silent, and indistinguishable from a real reading.
A blank panel is a bad outcome; a fabricated one was a worse one. This
grading is not self-exoneration — the panel is still broken and still
mine to fix.

## 6. What this docket does NOT establish

- **Whether the real feed has ever worked.** Unknown at filing. It
  decides whether this is a regression or an exposure.
- **Whether C51 is the only change involved.** Everything from v3.24.35
  to v3.24.50 touching the panel, its feed, or `_last_summary` is being
  enumerated; C51 is the obvious suspect, not a proven sole cause.
- **Which build the screenshot shows.** The tranche audit established
  that the running process had been executing older code than the source
  on disk. If that still holds, the screenshot may not reflect HEAD.
- **No fix is proposed here.** Reverting C51 would restore fabricated TA
  under real symbols, which is strictly worse. The repair must make the
  real feed arrive, not restore the lie.

## 7. Reference

- `src/gui/indicator_panel.py` — `_render_no_data`, `_may_fabricate`,
  `force_refresh`, `_auto_init_demo`, `_on_bot_selected`
- `src/gui/main_window.py:5055` — the real feed, and `:7228` force_refresh
- `src/trading/scrumming_bot.py:5841`, `:6076` — the only writers of `_last_summary`
- Commit `b24f350` — C51
- `docs/audits/2026-08-06_defect_severity_triage.md` — the ADG rubric used above
