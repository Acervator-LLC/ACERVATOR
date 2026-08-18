# Fold Tranches Tab Audit

Date: 2026-07-26. Version at audit: v3.23.34. Widget entry point:
`src/gui/bot_live_settings.py:886` `_create_fold_tranches_tab`.

Scrumming-mode-only tab (per v3.16.39 P2-VIS). Surfaces the fold-queue
state and lifetime cycle metrics, plus a per-tranche operator fire
button.

## Widget inventory

Two `QGroupBox` sections plus a conditional empty-state label.

### Section 1: `Fold-Tranche Cycle Health` summary group

| Row | Label | Value source | Type |
|-----|-------|--------------|------|
| 1 | Open tranches | `len(self._bot._fold_tranches)` | count |
| 2 | Parked USD (in fold queue) | `sum(t['usd'] for t in _fold_tranches)` | float, styled orange bold |
| 3 | Oldest tranche age | `max(now - t['created_ts'])` via `_format_age` helper | duration string |
| 4 | Lifetime tranches opened | `self._bot._tranches_created_lifetime` | int |
| 5 | Lifetime tranches closed (fold-back fired) | `self._bot._tranches_closed_lifetime` | int |
| 6 | Cycle close ratio (closed/opened) | `closed / created`, coloured by band | ratio + colour cue |

Colour rules on row 6 fire only when `created_lifetime >= 5 and open_count > 0`:
red under 0.5, orange 0.5–0.8, green ≥ 0.8. Below the 5-scrum threshold the label is
uncoloured and reads `—  (no scrums yet)` — sensible: three scrums is not enough
sample to call the cycle healthy or degraded.

### Section 2: `Open Tranches (N)` detail group (conditional on `len > 0`)

`QTableWidget`, 10 columns, `maxHeight=280`, alternating row colours, non-editable.

| Col | Header | Value source |
|-----|--------|--------------|
| 0 | # | `row + 1` |
| 1 | Age | `_format_age(now - t['created_ts'])` or `—` when missing |
| 2 | Units | `t['units']` (6-decimal) |
| 3 | USD parked | `t['usd']` |
| 4 | Sell ref $ | `t['ref']` (8-decimal) |
| 5 | Original cost $ | `t['initial_buy_price']` |
| 6 | Min rebuy $ | `ref × (1 − OTD%)` when OTD > 0, else `<ref` or `—` |
| 7 | Status | Price-only gate against Min rebuy (see below) |
| 8 | Source | `manual fire` (cyan) vs `auto scrum` |
| 9 | Fire | Per-tranche `QPushButton` wired to `_on_fire_tranche_clicked` |

### Section 3 (else): empty-state label

Short informative sentence when no tranches are open. Two-line factual message,
not prose. Left in place.

## Removed content (operator directive 2026-07-26)

Deleted the 400-word HTML QLabel that lived between the Summary and Detail groups
at old lines 958-983 (“How this works (v3.16.43 redesign)”). It made ~8 specific
claims about internal mechanics (MEM-171 highest-cost-first, MEM-244 50 %
taper threshold, MEM-253 hard stop, GEP composition, position-level smart
ceiling replacing per-tranche patent ceiling, compound continuing through
breakouts) that are prone to drift as the runtime evolves. Column headers plus
the per-column tooltips remain and are the authoritative documentation for what
each cell means.

## Runtime source verification

All attributes/methods the tab reads exist on `ScrummingBot`:

| Reference | Location |
|-----------|----------|
| `_fold_tranches` | `scrumming_bot.py:2273, 2380, 3178, 7225, 7538` |
| `_tranches_created_lifetime` | `scrumming_bot.py:3210` |
| `_tranches_closed_lifetime` | `scrumming_bot.py:1738, 2268, 2375, 3211, 8689` |
| `config.scrumming_interval_pct` | BotConfig field (checked in prior § 2 audit) |
| `get_status()` (for current_price) | ScrummingBot standard status contract |
| `manual_fire_tranche(idx)` | `scrumming_bot.py:1639` (async) |

Tranche dict fields used: `usd`, `created_ts`, `units`, `ref`, `initial_buy_price`,
`operator_initiated`. All are produced by the scrum-parking path (verified via
prior traces in the Option-B compounding investigation).

## Findings

### F22 — Explainer prose retired (operator directive; verified applied)

Deleted per 2026-07-26. Replacement comment placed at the old insertion point
citing the reason so future readers understand the deliberate omission.

### F23 — Fire button confirmation dialog uses the retired header

`_on_fire_tranche_clicked` (`bot_live_settings.py:1195`) shows the tranche's
`initial_buy_price` labelled `Original cost` — matches the current column header
(`Original cost $`, col 5). Consistent with the post-explainer state. No action.

### F24 — `_format_age` returns `1.5h` for 90 minutes

Trivial (formatting nit). The staticmethod at line 1322 uses `f"{hrs:.1f}h"` for
1 hour ≤ age < 24 hours. That's fine, but `1.5h` reads slightly awkward next to
the sub-hour formatter which returns `90m` for the same duration. Consistent
enough. No fix.

### F25 — Fire button tooltip is accurate

Text: "Operator-initiated fold-back of THIS tranche. Bypasses TA / OTD /
Target-Delta gates. Smart Ceiling + MEM-257 fail-closed still apply. Bot must
be RUNNING." Cross-checked against `manual_fire_tranche` at
`scrumming_bot.py:1639` — the method bypasses the three named gates and
enforces the two named guards. Accurate.

### F26 — Status column semantic is honest

Column 7's tooltip explicitly warns it is “Price-gate status only” and that
actual fold-back still requires TA validation and smart-ceiling headroom.
That's the right stance — the status column doesn't over-promise. Kept.

### F27 — MEM-257 reference in Fire tooltip is unqualified

The tooltip mentions `MEM-257 fail-closed`. That's an internal memory ID that
means nothing to an operator reading the tooltip cold. Not a defect per se —
the concept is “if the exchange call fails, no state changes” — but future
polish could rephrase as "if the market order fails, no reserve debit, no
tranche removal". Info only. Deferred.

## Recommendation

Ship the explainer removal as v3.23.35. No other Fold-Tranches-tab code needs
to change. F27 rewording is a low-priority polish that could ride a future
tooltip-cleanup pass.
