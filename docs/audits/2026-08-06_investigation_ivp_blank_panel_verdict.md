# INVESTIGATION — why the Indicator Voting Panel renders no TA

**Produced** 2026-08-06 · 9 agents · 58 findings across 4 traced lanes,
each adversarially verified.
**Question** put by the operator: *"Why and how did you break the Indicator
Voting Panel between versions 3.24.35 and 3.24.50?"*

**Method** four independent traces — C51's blast radius, the real feed, writer
ordering, and the v3.24.35..HEAD diff — each attacked by a separate verifier
instructed to default to REFUTED. No project code was executed; state and logs
were read read-only.

**Companion** `2026-08-06_docket_ivp_regression_3_24_35_to_50.md`

---

## What actually happened

The chain, in order, on 2026-08-06. All times local from `~/.acervator_logs/console/system.log`; the build is the v3.24.50 PyInstaller bundle named outright in `~/.acervator_logs/console_20260806_211603.log:1`, and the repo in the working directory is byte-identical to it for both files in the blast radius (`src/__init__.py:15` reads `__version__ = "3.24.50"` in both).

**1. The bot was restored, not started.** `21:16:06,591 Restored bot 7c39c7a2 (BTC/USD on coinbase) in IDLE state (was RUNNING at save)`. `_last_summary` is initialised to `None` at `src/trading/scrumming_bot.py:402` and is never persisted, so every launch starts it empty.

**2. The panel was asked to render that bot.** `21:16:41,748 INDICATOR PANEL: bot selected = '7c39c7a2', has data = False`. Entry is `src/gui/indicator_panel.py:794 _on_bot_selected`, reachable from the combo-box signal at `src/gui/indicator_panel.py:403` and from `update_bot_list`'s tail call at `src/gui/indicator_panel.py:1018`. Which one fired is not determinable from the logs and does not matter — both land in the same place.

**3. `_data` was empty, so the generator ran.** `src/gui/indicator_panel.py:802-803` — `if self._selected_bot_id and not self._data:` / `self._generate_demo_ta()`.

**4. C51's gate refused.** `src/gui/indicator_panel.py:837-839` returns `False, f"bot {self._selected_bot_id[:8]} is real"` for any non-`demo`/`default` id. `src/gui/indicator_panel.py:880-881` logs the WARNING and calls `_render_no_data("waiting for the TA engine")`. The log confirms it at `21:16:41,749`.

**5. The refusal cleared the panel.** `src/gui/indicator_panel.py:853-854` — `self.update_data({}, getattr(self, "_symbol_label_raw", ""))` then `self._summary_label.setText(f"No TA data — {reason}")`. Inside `update_data`: `src/gui/indicator_panel.py:1033` `self._data = multi_tf_summary`, then `:1047-1048` `setRowCount(0)` on both tables. The header string on screen has exactly one producer, `:854`.

**6. The bars were never fed at all.** `src/gui/indicator_panel.py:1116` `if timeframes:` gates the only two `set_bars` calls (`:1132-1133`), so an empty dict skips them. The "Awaiting TA signals..." text is the `_ConfidenceBars` placeholder at `src/gui/indicator_panel.py:245-250`, painted only when the widget has never been fed. That corrects the operator report on one detail: the string is in the bar strips beneath the tables, not in the tables — the tables are bare zero-row grids. It also proves something stronger than any log line could: **no non-empty `update_data` ever ran on that panel instance, real or fabricated.**

**7. The real feed ran every 2 seconds and had nothing to give.** `src/gui/main_window.py:4471-4473` starts `_refresh_dashboard` on a 2000 ms timer. `src/gui/main_window.py:4977-4984` reaches `if bot and getattr(bot, '_last_summary', None):`, and `src/gui/main_window.py:5055` `self._indicator_panel.update_data(merged, symbol)` is inside that guard. The guard never opened, for a chain of reasons that are individually sufficient:

- At `21:16:41` the bot was still IDLE. It started at `21:16:44,259 Bot 7c39c7a2 starting on BTC/USD` — **2.5 seconds after the render**. A bot that is not ticking cannot assign `_last_summary`.
- Its first tick is the init tick, which emits the handshake at `04:16:48.938Z` (`~/.acervator_logs/trade/diagnostics.log.1`: `INIT HANDSHAKE OK: position=$253.41` / `Scrumming init: BTC/USD position=$253.41 vs target=$250.09 (above target by $+3.32)`) and then **returns at `src/trading/scrumming_bot.py:5101`**, inside `if not self._initialised:` (`:4904`). That return is above the candle fetch at `:6018` and far above the only live writer at `:6076`. The init tick never computes TA.
- Every tick after that is discarded by the read-rate gate. `src/trading/scrumming_bot.py:4877` `_base_skip = max(1, int((self.config.scrum_read_rate_min * 60) / _tick_sec))` with `tick_interval` = 5.0 (`:2410`) and `scrum_read_rate_min` = 1 gives 12; SEARCH mode keeps all 12 (`:4880-4881`) while TRACK/FIRE get `12 // 10 = 1` (`:4878-4879`). `:4883-4884` `if self._tick_counter < self._tick_skip and self._initialised: return`. First TA-capable tick: ~55–60 s after init.
- **The bot was stopped at `21:17:01,721`** — 12.8 seconds after its init tick, ~45 seconds short of its first action tick. `_last_summary` was `None` for the entire life of that process.

**8. Nothing rewrote the panel, in either direction.** The three `update_data` call sites in `src/` are `indicator_panel.py:853`, `indicator_panel.py:939` and `main_window.py:5055`. The first fired once and produced the blank; the second is unreachable for a real bot; the third was fenced out. The blank persisted because after `21:16:41,749` **there was no writer at all**.

The operator's XRP observation is correct and fully consistent. `TA Vote:` is emitted at `src/trading/scrumming_bot.py:6335-6336`, downstream of `:6074-6076`. Bot `a873b457` was in TRACK mode, where `_tick_skip` is 1 — it votes every ~5 s. `7c39c7a2` was in SEARCH and got 17.5 seconds of life. Both facts are true of the same process at the same instant.

## Did C51 cause it or reveal it

**For the screenshot: revealed.** For two other places in the product: caused. These must not be collapsed.

The screenshot is case (b). C51 authored the string, the destructive clear, and the wrong (empty) symbol on the header — the operator is right that `_render_no_data` clears rather than merely declines. But the clear cannot hold a panel blank against a working feed. `main_window.py:5055` is not gated on `self._data`; it is gated on `bot._last_summary`, and it re-runs every 2000 ms regardless of what cleared the panel. Whatever writes `{}`, the next dashboard tick overwrites it the moment the bot has anything. The emptiness behind C51's string was upstream of C51 and is untouched by it: `main_window.py:4977-5056` is byte-identical from the repo's first commit through HEAD, and `ScrummingBot.tick()` through line 6535 is byte-identical to v3.24.35. Pre-C51, the same dead feed was masked by fabricated numbers rendered under the real symbol — the v3.24.35 A/B run at `21:18:46,507-510` shows exactly that (`demo TA computed — BEARISH 14% (12 signals) TF=5m` / `update_data called, table rows = 1`, for real bot `c8e5c5db`). The panel was lying before and is blank now. Both states have the same root cause.

One correction to the operator's framing, in C51's favour. The destructive clear is only destructive on one of the four entry paths. `_on_bot_selected` (`indicator_panel.py:802`) and `_auto_init_demo` (`:956`) both call the generator **only when `_data` is already empty**, so the clear is a no-op there. It destroys something visible only via `force_refresh` (`:971-972`), where `self._data = {}` was already unguarded pre-C51.

Now the part that is case (a), and that no previous pass caught:

**C51 permanently blanked the stocks window's panel.** `src/gui/stock_main_window.py:255` constructs a *second* `IndicatorVotingPanel()` with `sim_mode` defaulting to False (`indicator_panel.py:372`). Its only feed is `src/gui/stock_main_window.py:517 self._indicator_panel.update_bot_list(panel_statuses)`. There is no `update_data` call anywhere in that file — the repo-wide grep returns exactly three call sites and none is in it. For that panel, fabrication was the *only* populator. Post-C51 every entry terminates in `_render_no_data`, unconditionally and forever. That is C51 causing a blank panel outright, in a window the screenshot doesn't show.

**C51 turned bot creation into a blank.** `indicator_panel.py:971-972` zeroes `_data` then calls the generator; the sole caller is `main_window.py:7228`, immediately after `register(bot)` inside `_create_bot`. Pre-C51 that was clear-then-refill within a millisecond. Post-C51 it is clear-then-refuse, and the new bot has `_last_summary = None`, so the panel is genuinely blank until its first action tick. Related: the `setCurrentIndex` at `:970` is not inside a `blockSignals` window (unlike `update_bot_list`, which brackets its rebuild at `:993`/`:1010`), so a single `force_refresh` fires the refusal twice.

**C51's clear is incomplete.** `update_data({})` zeroes the tables but skips the bar feed at `:1116`, so a wipe of a *previously populated* panel leaves the previous bot's confidence bars painted above two empty tables. That did not manifest in the screenshot (the bars were never fed), but it is a worse lie than the one C51 removed.

The repair follows the split: fix the feed for the screenshot, fix C51 for the other two.

## What I got wrong

I shipped a gate whose entire test suite has `panel._data == {}` as its success condition.

`tests/test_c51_indicator_panel_no_fabrication.py` asserts two things. First, that the demo generator still works in a demo context — `test_the_generator_still_produces_data_in_demo_context` (`:77`, `assert panel._data`) and `test_sim_mode_may_fabricate` (`:173`). Second, that a real bot receives no fabricated data — five tests at `:110`, `:119`, `:128`, `:136`, `:143`, every one of which asserts `panel._data == {}`. Plus `:154` `assert "No TA data" in panel._summary_label.text()` and `:161` `assert panel._table_a.rowCount() == 0`.

What they did **not** assert:

1. **That the panel ever shows real TA.** No test constructs a bot with a `_last_summary` and drives `main_window.py:4977-5056`. `grep -rn "_last_summary" tests/` returns only `test_sim_visual_decoupling.py`, an unrelated subject. The real feed has zero test coverage of any kind.
2. **That the empty state is reachable only when real TA is absent.** The suite proves the refusal fires. Nothing proves it stops firing when data exists.
3. **That the clear is complete.** No assertion touches `_conf_bars_a` / `_conf_bars_b` after `update_data({})`, so the stale-bars defect shipped untested.
4. **That the widget has one instance.** I never checked for a second construction site. `stock_main_window.py:255` was three greps away.

The consequence is exact: a panel that can *never* populate — which is precisely the panel the operator photographed — passes all seven refusal tests, cleanly. Seven green assertions of absence cannot distinguish "correctly refusing to lie" from "structurally incapable of telling the truth."

The positive control that would have caught it is one test: build a fake bot carrying a real `VotingSummary`, run it through `_refresh_dashboard`, and assert `panel._table_a.rowCount() > 0` and `"No TA data" not in panel._summary_label.text()`. Its falsifier is the same test with `_last_summary = None`, required to fail. I never wrote an assertion whose failure mode was "the panel stayed empty when it should have filled." I have a standing rule that a measurement isn't a finding until its instrument has a positive control. I applied it to my audits and not to my own gate.

Two more, smaller:

I removed the fabrication without establishing what it was masking. `_generate_demo_ta` was load-bearing UI. It was the sole populator of one of the two panels, and it was the reason nobody had noticed that a SEARCH bot displays nothing for the first minute of its life. Removing a lie is right. Removing it without first checking what the truth path actually does is what converted a correct change into a regression report.

The commit message overclaims. It says the fix means a refusal "cannot leave the previous bot's rows on screen under a new bot's symbol." True of the refusal path only. Because `:802` guards on `not self._data`, switching to a TA-less bot while `_data` holds a *previous* bot's real data never calls the generator, so no refusal happens, and the panel keeps showing the old numbers under the old symbol (`_symbol_label_raw`, last written at `:1035`). C51 did not fix that; it is still there.

## The repair

Ordered. R1 through R4 are display-only and carry no trading exposure. R5 does and is deliberately last.

### R1 — Give the real feed an else-branch and a heartbeat (primary)

**Change.** `src/gui/main_window.py:4982-4984`. Neither `if` has an `else`. Add them. When `sel_bid` resolves to a bot with no `_last_summary`, call a new `indicator_panel.show_no_data(bot_id, symbol, reason)` that renders the empty state under the **correct** symbol with a **specific** reason derived from bot state: `"bot idle — not started"`, `"waiting for first read (SEARCH, ~60s)"`, `"parked at target — no TA evaluated"`, `"circuit breaker tripped — showing last known"`. When `sel_bid` is falsy, say so. Also add one `logger.debug` on the success path at `:5055` — right now there is no log statement anywhere on the real feed's success path, nor inside `update_data` (`:1020-1138`), which is the only reason every lane of this investigation had to argue from absence.

This also fixes the stale-numbers-under-a-wrong-symbol defect, because the else-branch fires whether or not `_data` is currently populated.

**Blast radius.** Zero on trading. `main_window.py:4977-5056` runs inside `_refresh_dashboard`, a Qt slot. It reads `bot._last_summary` and `bot.config.symbol` and writes only to widgets. It cannot place, cancel, size, or gate an order. The only hazard is a new exception here being swallowed by `:5057` and skipping the panel for that tick.

**Test.** `test_real_feed_populates_panel`: fake bot with a real `VotingSummary` in a fake manager, call `_refresh_dashboard`, assert `rowCount() == 1`, `"No TA data" not in` the header, and `panel._symbol_label_raw == "BTC/USD"`.

**Positive control proving the test can fail.** Parametrize the identical test with `_last_summary = None` and require every assertion to invert: `rowCount() == 0`, `"No TA data"` present, and the header naming the *selected* bot's symbol rather than the previous one. If both parametrizations pass against the same code, the test measures nothing. Add a mutation check: delete the `update_data(merged, symbol)` call at `:5055` and confirm the populated case fails. If it still passes, the test isn't reaching the feed.

### R2 — Give the stocks panel a populator, or stop constructing it

**Change.** `src/gui/stock_main_window.py:255` builds a panel nothing ever feeds. Either wire a feed beside `:517` mirroring R1 (confirm the stock bot exposes a summary first — `stock_accumulation_bot.py:254` has a `_last_summary` field, but I did not verify it is written on a live path), or remove the widget. Do not restore fabrication.

**Blast radius.** Zero. Separate window, display only, no crypto path touched.

**Test.** End-to-end: fake stock bot with a summary, drive the stocks refresh, assert the panel populates.

**Positive control.** Run that exact test against the file *as it stands today* and record the failure before shipping the fix. A test that has never failed against the broken code is not evidence.

### R3 — Make `force_refresh` honest instead of destructive

**Change.** `src/gui/indicator_panel.py:971-972`. Replace `self._data = {}` / `self._generate_demo_ta()` with `show_no_data(bot_id, symbol, "new bot — waiting for first TA read")`, so a freshly created bot gets a correctly-labelled empty state rather than a clear-then-refuse. Wrap the `setCurrentIndex` at `:970` in `blockSignals(True)/(False)` as `update_bot_list` already does at `:993`/`:1010`.

**Blast radius.** Zero. One caller, `main_window.py:7228`, inside `_create_bot` behind the wizard modal, after `register(bot)`. Display only.

**Test.** Assert the header names the *new* bot's symbol and the reason, and that `_on_bot_selected` is invoked once.

**Positive control.** Assert the invocation count is 2 against the current unblocked code, then 1 after the fix. If it reads 1 both times, the counter isn't wired.

### R4 — Complete the clear

**Change.** `src/gui/indicator_panel.py:1116`. On an empty dict, still reset both bar widgets, so an empty render can never leave the previous bot's bars painted above zero-row tables.

**Blast radius.** Zero, display only.

**Test.** Populate, then `update_data({})`, assert both widgets are empty and paint their placeholder.

**Positive control.** The identical assertion must fail on current code. Verify that failure before shipping.

### R5 — Only then, decide whether the TA latency is a bug at all

**Facts, so the decision is made on source and not on the panel.** The init tick returns at `scrumming_bot.py:5101`, above the TA block. A SEARCH bot at `scrum_read_rate_min=1` waits ~12 ticks × 5 s ≈ 60 s for its first `_last_summary` (`:4877`, `:4880-4881`, `:4883-4884`, `:2410`); TRACK/FIRE bots get skip 1 and vote every tick (`:4878-4879`). Separately and independently, the MEM-258 dust-band exit at `scrumming_bot.py:5220-5234` returns before the TA block **by design** — the block's own comment at `:5206-5207` states the rule as "the bot EXITS THE TICK IMMEDIATELY. No TA evaluated." A bot parked inside its dust band computes no TA at all, permanently, not transiently. That is a distinct permanent-blank path that a latency-only fix would leave standing.

**Recommended change: none, for now.** Do not lower the SEARCH read rate. Do not move the TA computation above the dust-band return. R1's else-branch makes both states legible — "waiting for first read" and "parked at target — no TA evaluated" are honest and actionable, which is what the panel owes the operator. If you later want TA populated while parked, that is a TA-only read hoisted above the return with no access to the buy/sell path, and it gets its own cascade and its own gate.

**Blast radius if you get this wrong: high.** Lowering the SEARCH read rate multiplies exchange API calls across 35 live bots. Moving TA above the dust-band return reintroduces exactly the behaviour the operator's verbatim directive at `scrumming_bot.py:5200-5207` forbids. This is why it is last and why it is not bundled with a panel fix.

**Test, if you do proceed.** Assert that with `abs(current_value - target) <= dust_band` the tick returns without calling `_voting_engine.compute_all`. **Positive control:** the same test with the position $3.32 off target must show `compute_all` *was* called. If both branches report the same call count, the harness isn't observing the engine and the test is worthless.

## What this does NOT establish

**That the crypto real feed has ever populated the panel, in any build.** There is no log statement at `main_window.py:5055` and none anywhere in `update_data` (`indicator_panel.py:1020-1138`). The only `update_data called, table rows = N` line is at `:940`, *inside* `_generate_demo_ta`. Every historical `has data = True` in the logs is equally consistent with a surviving fabrication or a silent real update. "The feed has never worked" and "the feed works and nobody noticed" are both still live. R1's debug line is what closes this, and nothing else will.

**That the panel would have populated had the fleet kept running.** `7c39c7a2`'s first TA-capable tick was ~45 s past the moment all bots stopped. The code says the next 2 s dashboard tick would have filled it. No observation confirms that; the process ended first.

**Why 35 bots stopped at `21:17:01.707-.721`, or why only 6 of 35 were ever started.** Six staggered starts between `21:16:21` and `21:16:44`; the other 29 sat in the IDLE state they were restored into. A bot that never ticks never sets `_last_summary`, so selecting any of those 29 yields a permanently blank panel with no C51 involvement whatsoever. Neither the stop burst nor the 29 unstarted bots is a panel defect, and neither was explained.

**The screenshot's capture time.** The panel state is uniquely consistent with the `21:16:41,748` render, and the never-fed confidence bars prove no non-empty `update_data` ran on that instance — but no capture timestamp was in evidence. Activity Log lines persist in the widget after emission, so the XRP line cannot narrow the window past the process bounds `21:16:41.748` – `21:18:43.353`.

**The XRP vote line, against disk.** `TA Vote:` is a bus emission (`scrumming_bot.py:6335-6336`) rendered only in the GUI Activity Log; it is not persisted to the console logger. The operator's strongest exculpatory observation cannot be cross-checked against any file. It is corroborated structurally instead — `a873b457` was in TRACK mode, where every tick is an action tick — not by log matching.

**The bot mode distribution at the time of the incident.** `scrum_target_mode` is volatile live state written on save (`scrumming_bot.py:3533`), and the `~/.acervator/bot_state.json` snapshot available to me is stamped `21:57:44`, 41 minutes after the incident. The `scrum_read_rate_min` figures are config and stable; the mode counts are not citable for `21:16`.

**The capital-reservation fault on `7c39c7a2`.** It logged `reserve: over-commit on BTC … existing reservations 0 + requested 0.004281 > total holdings 0.003900` every ~5 s throughout `21:10`–`21:12` in the prior process. The emitter at `scrumming_bot.py:1152` says "continuing tick; will retry next call," and the tick-top call is wrapped at `scrumming_bot.py:4841-4847` with a debug-only handler, so it does not by itself abort the tick — but I did not trace whether it blocks anything downstream, and it is a live fault on a bot holding real BTC. It is out of scope for the panel and should not stay out of scope for long.
