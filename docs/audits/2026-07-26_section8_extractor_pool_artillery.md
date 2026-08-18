# § 8 — Extractor — Pool & Artillery — Bot Details Settings Audit

**Date:** 2026-07-26  |  **Version at audit:** v3.23.32  |  **Widget location:** `src/gui/bot_live_settings.py:2987-3132`  |  **Runtime:** `src/trading/extractor_bot.py`

Extractor-mode-only subsection. Eight configuration widgets governing pool sizing,
artillery rounds, watch-list scanning, exit sizing, compounding tiers, and cost-basis
cap. Plus a read-only display of manual alt-target overrides.

## Widget inventory

| # | Widget attr | Config field | Type | Range/Default | Runtime consumer(s) |
|---|-------------|--------------|------|---------------|---------------------|
| 1 | `_ext_chunk_size`      | `extractor_chunk_size_usd`         | float | 10–10M / **100.0** | `extractor_bot.py:270-278, 395-434 (set_pool_size_live)` |
| 2 | `_ext_artillery_size`  | `extractor_artillery_size_usd`     | float | 0.5–100k / **5.0**  | `extractor_bot.py` (multiple) |
| 3 | `_ext_scan_top_n`      | `extractor_scan_top_n`             | int   | 5–10 / **8**        | `extractor_bot.py` scan loop |
| 4 | `_ext_scan_refresh`    | `extractor_scan_refresh_candles`   | int   | 10–600 / **60**     | `extractor_bot.py` scan loop |
| 5 | `_ext_pool_reserve`    | `extractor_pool_reserve_pct`       | float | 0–90 % / **50.0**   | `extractor_bot.py:531-534` |
| 6 | `_ext_exit_pct`        | `extractor_exit_pct`               | float | 10–100 % / **100.0**| `extractor_bot.py:910, 916, 1210, 1248, 1306` |
| 7 | `_ext_max_tier`        | `extractor_max_compounding_tier`   | int   | 1–10 / **3**        | `extractor_bot.py:1257` |
| 8 | `_ext_max_cost_basis`  | `extractor_max_cost_basis_multiple`| float | 1.0–10.0 / **2.0**  | `extractor_bot.py:974, 1073` |
| — | (display) `_ext_alt_targets` | `extractor_alt_targets`      | list  | (empty)             | scan-loop consumer |

**All 8 fields exist in `BotConfig`** (bot_container.py:378-410).
**All 8 (+ alt_targets) live-editable** (bot_container.py:598-607).
**All in restore path** (bot_container.py:2550-2575).

## Runtime behavior spot-checks

### Pool reserve gate (F20 candidate — verified accurate)

`extractor_bot.py:531-534`:

```python
reserve = self._chunk_size_base * (self.config.extractor_pool_reserve_pct / 100.0)
return (self._chunk_free_base - artillery_base) >= reserve
```

Tooltip says: `"New artillery fires only if (chunk_free - artillery_size) >= reserve."`
**Matches exactly** (in base-currency units; USD conversion happens upstream).

### Pool size live-edit re-anchors correctly

`extractor_bot.py:395-434`: `set_pool_size_live` recomputes `_chunk_size_base` from
the operator's new USD value at the construction-time conversion rate, then scales
`_chunk_free_base` proportionally to preserve the deployed:free ratio (so the bot
doesn't claim phantom free base units it doesn't own). Also updates the capital
reservation registry so sibling ScrummingBots see the new claim.

Tooltip claim `"changing live re-anchors the pool's reference USD value (not the
held base units — those are exchange-tracked)"` is accurate — the operator adjusts
the bot's internal allocation ledger, but no exchange holdings move.

### Compounding tier logic — real finding

`extractor_bot.py:1258-1276`:

```python
if pos.compounding_tier < max_tier and gain_base > 0:
    self._chunk_free_base += base_received
    if pos.alt_units > 1e-12:
        pos.compounding_tier += 1
    log_kind = "ROLL_TO_NEXT_TIER"
else:
    self._chunk_free_base += base_received
    log_kind = "LOCK_TO_POOL"
```

The two branches deposit `base_received` into `_chunk_free_base` **identically**.
The only observable differences are the `log_kind` string and whether
`compounding_tier` gets bumped. Comment at 1264-1266 explicitly confirms:

> `For simplicity at v3.19.1, we treat the gain as locked-to-pool for now (the
> rolling mechanism with gain-as-next-artillery-size is a v3.19.1+ follow-up;
> this ship handles the lock case cleanly).`

The tooltip describes v3.19.1+ intended behavior, not current v3.23.x behavior.
See **F20**.

## Findings

### F20 — Compounding-tier tooltip describes not-yet-shipped behavior

**Severity:** Medium — operator-visible tooltip misrepresents current runtime.

Tooltip (`bot_live_settings.py:3080-3083`):

> `"Max compounding tier per position. Tier N rolls N-1 times then locks realized
> base gain to the pool. Tier 1 always locks."`

Current runtime at v3.23.32 (`extractor_bot.py:1258-1276`): the ROLL branch
increments the tier counter and logs `"ROLL_TO_NEXT_TIER"`, but the base gain goes
to `_chunk_free_base` identically to the LOCK branch. There is no “rolling”
behavior at the artillery-size level yet. The tier setting only affects a log-line
label; it does not change how the next artillery round is sized.

**Two options:**
- **(a) Update tooltip to match current behavior.** Suggested: `"Compounding tier
  counter (currently informational — logs ROLL_TO_NEXT_TIER vs LOCK_TO_POOL). Gain
  always deposits to the pool at this version; gain-as-next-artillery-size is a
  planned enhancement."`
- **(b) Ship the rolling mechanism.** Larger change; needs a design pass on how
  gain propagates to next PENDING→IN_FLIGHT for the same pair, and how it
  interacts with `extractor_max_cost_basis_multiple`.

**Recommendation:** ship (a) now so the tooltip stops lying, then queue (b) as its
own feature ticket.

### F21 — Alt Targets is read-only in the live-settings dialog

**Severity:** Info — known deferred item.

Widget code (`bot_live_settings.py:3111-3132`) shows manual alt-target list as a
read-only label. Comment at 3109-3110:

> `# v3.19.28 — surface the manual override list. Read-only display for now`
> `# (multi-select live editor is a larger follow-up); shows the operator what`
> `# the bot is using.`

Known gap. Operator must edit alt-targets via wizard rebuild or config file for now.
Not a defect.

### F22 — Everything else verified sound

- Pool reserve formula matches tooltip exactly.
- Pool size live-edit preserves deployed:free ratio and updates capital reservation
  registry (verified at 427-462).
- All ranges (5-10 top-N, 0-90% reserve, 1.0-10.0x cost basis) enforce documented
  design constraints.
- Alt-targets empty→auto-scan fallback correctly displayed to operator (3125-3131).

---

## Verification methodology

- BotConfig existence + live-editable + restore path checked for all 8 fields +
  alt-targets list.
- Runtime consumers cross-referenced in `extractor_bot.py`.
- Pool reserve formula, pool size live-edit ratio math, and compounding tier logic
  cross-checked against tooltips.

**One real finding (F20 tooltip inaccuracy).** One known deferred item (F21). No
other defects.

---

## Batch state at end of § 8

Pending for the next cascade:

| # | Section | Change |
|---|---------|--------|
| F18 | § 7 | Append “must be above anchor” gate to detonation tooltip |
| F20 | § 8 | Rewrite compounding-tier tooltip to match current v3.23.x behavior |

Proceed to § 9 (Alt Targets — manual override, at bot_live_settings.py:3111 — already
covered above as F21) or wrap the audit with cascade if § 9 is the same section.
