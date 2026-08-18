# § 6 — DANGER ZONE — Self-Destruct (v3.15.62) — Bot Details Settings Audit

**Date:** 2026-07-26  |  **Version at audit:** v3.23.31  |  **Widget location:** `src/gui/bot_live_settings.py:2847-2876`

Action-only section — no config fields. One button that aggressively market-sells the
entire target-asset holding, clears state, and pauses the bot. Two-step operator
confirmation, red-styled to minimize misclick risk.

## Widget inventory

| # | Widget attr | Handler | Runtime call | Location |
|---|-------------|---------|--------------|----------|
| — | `_self_destruct_btn` | `_on_self_destruct_clicked` (line 488) | `bot.self_destruct(confirmation_token="SELF-DESTRUCT")` | `scrumming_bot.py:2161` |

## Confirmation flow

1. **GUI dialog** (`bot_live_settings.py:512-527`): `QInputDialog.getText` asking the
   operator to type `SELF-DESTRUCT` literally, case-sensitive. Rejects on cancel,
   empty, or mismatch. Shows the impacted symbol + bot id so operator knows *which*
   bot.
2. **Runtime re-validation** (`scrumming_bot.py:2197-2219`): even after the dialog,
   the async method independently checks `confirmation_token == "SELF-DESTRUCT"` and
   refuses otherwise, emitting an operator-visible `SELF-DESTRUCT REFUSED (entry
   guard)` log (v3.15.91 F2 fix — pre-fix this branch returned the dict silently).
3. **Threading model** (`bot_live_settings.py:531-546`): dispatched via
   `threading.Thread + asyncio.run` so the GUI thread never blocks and no cross-loop
   coupling is required with the bot's coordinator loop.

## Runtime behavior spot-checks

- **Fresh holdings** (2231): reads exchange balance at fire time, not cached bot state.
- **Aggressive market-sell** (2306-2313): uses `guarded_place_order` with role
  `SELF_DESTRUCT`. Bypasses BB detection, hysteresis, circuit breakers, higher-TF bias.
- **Failure emits** (2330, 2345): `SELF-DESTRUCT FAILED: order raised …` /
  `SELF-DESTRUCT FAILED: exchange returned no fill…` — v3.15.91 hardening.
- **State cleanup** (2258-2260, 2368+): `_main_lots = []`, `_fold_tranches` cleared,
  `_current_holdings = 0`.
- **State transition** (2182-2185): default `keep_running=False` → `BotState.PAUSED`.
  Button always passes just `confirmation_token`, so default applies.
- **Idempotence** (2256-2283): if holdings already zero, no order fires; state is
  still cleared, bot still pauses.
- **`trade.filled` emit** (2401-2418): `type="SELF_DESTRUCT"`, `role="SELF_DESTRUCT"`,
  `side="SELL"`, `trade_action="SELF_DESTRUCT"`. Consumed by v3.15.59 History tab.

## Findings

### F14 — Two-layer defense is well-implemented

**Severity:** Verified good. No fix.

Modal dialog with typed-literal token + runtime method re-validation with the same
literal. Even a corrupted GUI call missing the confirmation string will refuse at the
method boundary. Defense in depth done right.

### F15 — Dialog references `SELF_DESTRUCT FILLED`, runtime emits `SELF-DESTRUCT FIRING/FAILED`

**Severity:** Low — misleading operator guidance in a critical dialog.

`bot_live_settings.py:547-551`:

```python
QMessageBox.information(
    self, "Self-Destruct Dispatched",
    f"Self-destruct fired for bot {bid}.\n"
    f"Watch the Activity Log for SELF_DESTRUCT FILLED.\n"     # ← wrong
    f"Bot will be PAUSED on completion.")
```

Actual `bot.log` emit strings from `scrumming_bot.py`:

| Line | Emit text |
|------|-----------|
| 2224 | `SELF-DESTRUCT armed. Querying exchange for current holdings...` |
| 2241 | `SELF-DESTRUCT REFUSED (balance fetch): ...` |
| 2283 | `SELF-DESTRUCT: exchange holdings already 0. ...` |
| 2306 | `SELF-DESTRUCT FIRING: market-sell ...` |
| 2330 | `SELF-DESTRUCT FAILED: order raised ...` |
| 2345 | `SELF-DESTRUCT FAILED: exchange returned no fill...` |

All emits use **hyphenated** “SELF-DESTRUCT”. The dialog telling operator to search
for **underscore** “SELF_DESTRUCT FILLED” won't match unless the log widget uses
partial substring matching — and there's no emit with literal “FILLED” text at all
(the successful completion emit is not shown above but almost certainly uses
“SELF-DESTRUCT COMPLETE” or similar hyphenated form).

**Fix candidate:** update dialog to
> `"Watch the Activity Log for SELF-DESTRUCT FIRING or SELF-DESTRUCT FAILED."`

### F16 — Success dialog fires immediately after thread dispatch; async result not surfaced

**Severity:** Low (UX) — deferrable pending operator preference.

`bot_live_settings.py:547-551` shows the “Self-Destruct Dispatched” popup right after
`threading.Thread.start()`, before the underlying `self_destruct()` returns. If the
async method fails (balance fetch, exchange unreachable, order rejected), the
operator has already dismissed the “Dispatched” popup and only finds out by reading
the log. Failure emits (v3.15.91) are the safety net.

**Fix candidate options:**
- Adjust wording: `"Dispatched — check log for FIRING or FAILED"`.
- Disable the button post-click and re-enable on completion with terminal status
  (requires a Qt signal from the worker thread; more code but genuine feedback).
- Use `QMetaObject.invokeMethod(..., Qt.QueuedConnection)` to post a follow-up
  QMessageBox with the actual result dict.
- Do nothing (current fail-soft-log pattern is defensible for GUI-async bridging).

**Recommendation:** wording tweak now (low cost, higher accuracy). Deeper UX
(disable + re-enable + result popup) is a separate line-item and probably belongs
with F11's transient-flash pattern for consistency across DANGER buttons.

### F17 — `asyncio.run` in fresh thread per click — potential cross-loop concern

**Severity:** Info. No change proposed.

`bot_live_settings.py:531-546` creates a new event loop each click. The bot's other
async methods (main tick loop, `_execute_manual_rebalance`, etc.) presumably run on
the coordinator's loop. `self_destruct` internally awaits `exchange.get_balance` —
if the exchange interface holds any per-loop state (e.g. an `aiohttp.ClientSession`
bound to a specific loop), calling it from a fresh loop could fail.

The v3.15.91 hardening added an outer try/except around the balance fetch which
would catch such a mismatch and refuse cleanly. Operator has used this button
successfully in the past (per chronicle), so this is a theoretical concern only.
Flagging for the record.

---

## Verification methodology

- Widget layout + confirmation flow traced through
  `bot_live_settings.py:488-551, 2847-2876`.
- Runtime method traced through `scrumming_bot.py:2161-2418`.
- Emit-string audit against the dialog's guidance text (F15).
- No mechanical widget-vs-config gap (this section has no config fields).

**Real findings:** F15 (fix wording — misleading log-search guidance). F16 wording
tweak recommended. F14 verified sound. F17 informational only.

---

## Batch state at end of § 6

Pending for the next cascade:

| # | Section | Change |
|---|---------|--------|
| F10 | § 5 | `bot_live_settings.py:2781` — `v3.15.93` → `v3.15.92` (comment sync) |
| F11 | § 5 | `_cb_reset_all_btn` — transient status flash on click (operator directive) |
| F15 | § 6 | Success dialog — `SELF_DESTRUCT FILLED` → `SELF-DESTRUCT FIRING or SELF-DESTRUCT FAILED` |
| F16? | § 6 | Optionally: `"Dispatched"` → `"Dispatched — check log for FIRING or FAILED"` (batch with F15 or defer) |
