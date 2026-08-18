# Stack Tranches Tab Audit

Date: 2026-07-26. Version at audit: v3.23.35. Widget entry point:
`src/gui/bot_live_settings.py:1331` `_create_stack_tranches_tab`.

Scrumming-mode-only tab, added v3.23.28 as a mirror of the Fold Tranches
tab for the Stack Mode ledger. Renders even when `stack_mode` is off
or the ledger is empty (per v3.23.29 operator directive — no sub-gate
so the operator can find the tab while investigating the feature).

## Widget inventory

### Section 1: `Stack-Tranche Cycle Health` summary group

| Row | Label | Value source | Type |
|-----|-------|--------------|------|
| 1 | Pending tranches | `len([t for t in _stack_tranches if t['status'] == 'pending'])` | count |
| 2 | Filled tranches | `len([t for t in _stack_tranches if t['status'] == 'filled'])` | count |
| 3 | Cancelled tranches | `len([t for t in _stack_tranches if t['status'] == 'cancelled'])` | count |
| 4 | Pending size (unfilled) | `sum(t['size'] for t in pending)`, styled orange bold | base-unit float |
| 5 | Oldest pending age | `_format_age(max(now - t['opened_ts']))` for pending tranches | duration string |
| 6 | Lifetime tranches opened | `self._bot._stack_created` | int |
| 7 | Fill ratio (filled/opened) | `filled_count / created_lifetime`, coloured by band | ratio + colour cue |

Colour rules on row 7 activate when `created_lifetime >= 3 and pending > 0`:
red under 0.3, orange 0.3–0.7, green ≥ 0.7. Thresholds are looser than the
Fold Tranches ratio (0.5/0.8) because Stack tranches complete faster —
Stack fills are single limit orders resolving in seconds/minutes, whereas
Fold-back closes wait for price to move through the OTD gate over
minutes/hours/days. Different behaviour → different “healthy” ratios.

### Section 2: Detail render

**Empty state** (no tranches): short factual sentence.

**Populated state**: `QGroupBox("Tranches (N)")` containing:
- Monospace header `QLabel` (functional column labels, not prose)
- One monospace `QLabel` per tranche, colour-coded by status
  (green = filled, red = cancelled, default = pending)
- Columns: #, Target Price, Size, Mode (VISIBLE/INVISIBLE), Status,
  Fill Price, Age

Notable design decision: this tab uses aligned monospace `QLabel` rows
instead of a `QTableWidget` (which Fold Tranches uses). Consequence: no
per-row interaction affordance (no per-tranche cancel/fire button). At
v3.23.35 Stack tranches self-manage via the reconciler; there is no
operator-visible action equivalent to Fold Tranches' Fire button. If a
future feature adds one, upgrading this section to `QTableWidget` will
be part of that ticket.

## Runtime source verification

All attributes/methods the tab reads exist on `ScrummingBot`:

| Reference | Location |
|-----------|----------|
| `_stack_tranches` (list) | `scrumming_bot.py:418` (init), `9182` (append) |
| `_stack_created` (int) | `scrumming_bot.py:419` (init), `9183` (increment) |
| `_format_age` (staticmethod) | `bot_live_settings.py:1322` |

**Tranche dict fields consumed by GUI** are all set by the stack lifecycle:

| Field | Set at | Consumed by GUI at |
|-------|--------|--------------------|
| `index` | `scrumming_bot.py:9144` (initial) | col 1 |
| `price` | `scrumming_bot.py:9145` (initial) | col 2 |
| `size` | `scrumming_bot.py:9146` (initial) | col 3, row-4 aggregation |
| `visible` | `scrumming_bot.py:9151` (initial) | col 4 |
| `status` | `scrumming_bot.py:9147` (initial `pending`), updated to `filled` / `cancelled` in visible + invisible reconcilers | col 5, row-1/2/3 counts, colour |
| `opened_ts` | `scrumming_bot.py:9148` (initial) | col 7 (age), row-5 (oldest pending) |
| `fill_price` | Set by reconciler on fill transition | col 6 (`—` when still pending) |

**No dead-field consumption.** Every GUI-side lookup has a runtime
producer.

## Findings

### F28 — No hallucinatory descriptive prose present

Unlike the Fold Tranches tab (from which we retired the 400-word HTML
explainer this cascade), the Stack Tranches tab renders no prose block.
The only descriptive strings are: two `QGroupBox` titles, a two-line
empty-state label, and functional column labels in a monospace header
row. All are short and factual. No action.

### F29 — Ratio-band thresholds are asymmetric with Fold Tranches (deliberate)

Fold Tranches uses 0.5 / 0.8 red/orange thresholds (bot_live_settings.py:948-953).
Stack Tranches uses 0.3 / 0.7 (line 1385-1392). The asymmetry is a
deliberate reflection of the two ledgers' different completion cadences,
not a bug. Documented above; no code change.

### F30 — `_stack_created` is monotonic, never decremented

Stack tranches can transition to `cancelled` (when exchange placement
returns None or raises), but the lifetime counter still counts them as
“opened”. The Fill Ratio row therefore double-penalises cancels: they
inflate the denominator and never appear in the numerator. That's
arguably the correct signal — cancels represent placement failures the
operator should notice — but the row’s label “Fill ratio (filled/opened)”
could be misread as “of the ones that resolved, what fraction filled”.
More precise wording would be `Fill ratio (filled / lifetime opened)`
or `Fill success rate`. Info only. Deferred.

### F31 — No manual-cancel button per tranche

Fold Tranches has a per-row Fire button; Stack Tranches has no equivalent.
An operator cannot cancel a pending stack tranche from the GUI — they
must let it self-reconcile or restart the bot. Not a defect (no reported
need), but flagged for future symmetry work. Deferred.

### F32 — Monospace column widths hardcode price precision at 8 decimals

Line 1433-1434 formats price/fill_price with 10-wide, 8-decimal fields.
Fine for most crypto pairs (BTC/USD at $65_000 fits; SHIB at 0.00001234
fits). Would misalign on a hypothetical instrument with >$99_999 price
(fits `99999.99999999`, edge case) or with a price whose precision
exceeds 8 decimals (none on Coinbase). No fix — acceptable for current
supported instruments.

### F33 — Age missing timestamp fallback shows `— (no timestamp)`

Line 1376 handles pending tranches whose `opened_ts` is missing/zero.
Since `opened_ts` is always set at tranche creation (line 9148 in
scrumming_bot.py), this branch would only trigger on state migrated
from before v3.23.28. Unlikely in practice but harmless — the fallback
is graceful. Kept.

## Recommendation

Ship no code changes for this tab. The audit surfaced no defects and
no prose to remove. F30 (label wording) and F31 (no manual-cancel) are
deferrable enhancements pending operator need.
