# Bot Details — Settings tab § 1 Trading Parameters (v3.23.24)

**Display surface**: `src/gui/bot_live_settings.py` lines 2172–2210.
**Apply flow**: `_apply_changes()` at line 376. Routes through
`_RUNTIME_ROUTED` map (line 421) for fields with a live-update method;
others go through plain `setattr(cfg, ...)`.

**FALSIFICATION**: this report is wrong if (a) any listed source line
doesn't match after this session, (b) a field marked “dead” is
actually consumed on a code path I missed, or © `_RUNTIME_ROUTED`
gets a new entry that changes the plumbing.

---

## Per-widget verdict

| Widget | BotConfig field | Type / Default | Runtime route | Actually consumed? | Verdict |
|---|---|---|---|---|---|
| Order Visibility (QComboBox) | `visibility` | `str` / `"orderbook"` | `set_visibility_live` → `self._invisible` | ✓ yes — 4 branch sites in scrumming_bot | ✓ correct |
| Check Interval (QSpinBox 1-120 sec) | `market_check_interval` | `int` / `5` | plain setattr | ✗ **NO reader anywhere in src/** | ✗ **dead field** |
| Aggressive Trading (QCheckBox) | `aggressive_trading` | `bool` / `False` | `set_aggressive_live` → `self._aggressive` | ✓ yes — used at line 4164 | ✓ correct |
| Bulk Trading (QCheckBox) | `bulk_trading` | `bool` / `False` | plain setattr | ✗ **NO reader in src/trading/** | ✗ **dead field** |

Also noted in passing (not exposed in this subsection but present on BotConfig):

| Field | Read anywhere? |
|---|---|
| `bulk_partial_on_return` | ✗ NO reader in src/ (not surfaced in GUI either — triple-dead) |

---

## Detail per finding

### ✓ Order Visibility — correct

- **Init**: `self._vis.setCurrentIndex` at [bot_live_settings.py:2180-2182](src/gui/bot_live_settings.py:2180) from `cfg.visibility`.
- **Change signal**: `_mark_changed("visibility", self._vis.currentData())` at [line 2184](src/gui/bot_live_settings.py:2184).
- **Apply**: routed through `set_visibility_live` (in `_RUNTIME_ROUTED` map at [bot_live_settings.py:423](src/gui/bot_live_settings.py:423)).
- **Runtime state variable**: `self._invisible` at [scrumming_bot.py:270](src/trading/scrumming_bot.py:270) — set once at `__init__` from `config.visibility == "internal"`, then live-updated by `set_visibility_live` at [line 1007](src/trading/scrumming_bot.py:1007).
- **Consumers**: `self._invisible` gates the LIMIT vs MARKET order path in `_execute_buy` / `_execute_sell` / `_execute_manual_rebalance` (docstring cites lines 1118, 3556, 3567, 3906).
- **Verdict**: correctly plumbed end-to-end. Toggling this widget changes the running bot's next order type.

### ✗ Check Interval — dead field

- **Init**: `self._interval.setValue(cfg.market_check_interval)` at [line 2190](src/gui/bot_live_settings.py:2190).
- **Change signal**: `_mark_changed("market_check_interval", v)` at [line 2193](src/gui/bot_live_settings.py:2193).
- **Apply path**: NOT in `_RUNTIME_ROUTED`. Falls through to `setattr(cfg, "market_check_interval", value)` at [bot_live_settings.py:456](src/gui/bot_live_settings.py:456).
- **Runtime consumers**: grep across `src/` for `market_check_interval` returns **6 hits — 2 in the Settings widget itself, 2 in `main_window.py` restore path, 2 in `bot_container.py` (dataclass def + kwarg allowlist). Zero in `src/trading/`.**
- **Actual tick interval**: hardcoded `5.0` in `scrumming_bot.py:1741-1742` (`tick_interval` property returns literal `5.0`).
- **Operator impact**: user can set “Check Interval: 30 sec”, click Apply, see “1 change applied — active immediately”. The bot continues ticking every 5 seconds regardless. Value is persisted, saved to `bot_state.json`, restored on restart — and continues to be ignored.
- **Fix options**:
  - **(a) wire it**: change `tick_interval` property in `scrumming_bot.py` to return `float(self.config.market_check_interval)`. Two-line change plus a live-update route so the running tick loop actually adopts the new value between ticks. Real behavior change.
  - **(b) remove it**: delete the widget, delete the field, R-CLN sweep. Honest surface.
  - **© label it**: rename the widget to something like “Invisible-mode price check (unused v3.16+)” so the operator knows it's inert. Weakest option.

### ✓ Aggressive Trading — correct

- **Init**: `self._aggressive.setChecked(cfg.aggressive_trading)` at [line 2198](src/gui/bot_live_settings.py:2198).
- **Change signal**: `_mark_changed("aggressive_trading", v)` at [line 2200](src/gui/bot_live_settings.py:2200).
- **Apply**: routed through `set_aggressive_live` (in `_RUNTIME_ROUTED`).
- **Runtime state**: `self._aggressive` at [scrumming_bot.py:271](src/trading/scrumming_bot.py:271), live-updated at [line 1035](src/trading/scrumming_bot.py:1035).
- **Consumers**: `self._aggressive` read at [scrumming_bot.py:4164](src/trading/scrumming_bot.py:4164) for AGGRESSIVE log tagging. NB — cited by set_aggressive_live docstring as gating “downstream behavior” but only 1 grep hit outside the setter. Worth a deeper trace in a separate ticket to confirm what “downstream behavior keyed off self._aggressive” refers to; the wiring itself is correct.
- **Verdict**: end-to-end plumbing is correct. Behavior impact may be narrower than the docstring implies.

### ✗ Bulk Trading — dead field

- **Init**: `self._bulk.setChecked(cfg.bulk_trading)` at [line 2205](src/gui/bot_live_settings.py:2205).
- **Change signal**: `_mark_changed("bulk_trading", v)` at [line 2207](src/gui/bot_live_settings.py:2207).
- **Apply path**: NOT in `_RUNTIME_ROUTED`. Falls to plain `setattr`.
- **Runtime consumers**: grep across `src/` for `.bulk_trading` returns **1 hit — the Settings widget init at [line 2205](src/gui/bot_live_settings.py:2205). Zero in `src/trading/`.**
- **Operator impact**: same shape as Check Interval — toggle-click-Apply does nothing to bot behavior.
- **Fix options**: same three as Check Interval.

### ✗ `bulk_partial_on_return` — triple-dead field

- **Declaration**: [bot_container.py:259](src/trading/bot_container.py:259). Passed at construction ([main_window.py:5814-5815](src/gui/main_window.py:5814)), restored on save ([bot_container.py:2373-2374](src/trading/bot_container.py:2373)), listed in `_SCRUMMING_ONLY_FIELDS` allowlist.
- **Not exposed in Settings GUI** (no widget for it).
- **Not read anywhere in src/**.
- Effectively unreachable. Pure R-CLN candidate.

---

## Summary — action items for § 1

| Priority | Item | Kind |
|---|---|---|
| P1 | `market_check_interval` — pick fix (a) wire, (b) remove, or © relabel | Dead field, operator-visible |
| P1 | `bulk_trading` — pick fix (a) wire, (b) remove, or © relabel | Dead field, operator-visible |
| P3 | `bulk_partial_on_return` — R-CLN remove from BotConfig + restore path | Dead field, operator-invisible |

Correctly-plumbed widgets: 2/4 (visibility, aggressive_trading).
Dead widgets: 2/4 (market_check_interval, bulk_trading).

Bonus dead field found in passing: `bulk_partial_on_return`.

Awaiting your call on the fix option per P1 item, then I'll implement + pin. If you prefer to keep the audit rolling and defer the fixes to a batch pass after all Settings subsections are audited, say so and I'll move on to § 2 Scrumming Settings.
