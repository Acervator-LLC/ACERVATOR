# Bot Swarm Tab Audit

Date: 2026-07-26. Version at audit: v3.23.35 (will cascade to v3.23.36).
Widget entry point: `src/gui/bot_live_settings.py:1460`
`_create_bot_swarm_tab`.

Scrumming-mode-only tab, added v3.16.44 P2-VIS. Surfaces Smart Wire
manager state so the operator can inspect the cross-compounding network
(operator’s patent-flagged Invention #6). Mirrors
`smart_wire.py:SmartWireManager` internal data — `_wires` (topology),
`_ledgers` (per-bot profit provenance), `_transactions` (chronological
feed) — plus the bot’s own `_pending_wire_credits` and
`_pending_wire_ledger`.

## Widget inventory

Five conditional `QGroupBox` sections plus two empty-state fallbacks:

### Empty state A — manager not attached (line 1476-1487)

Fires when `getattr(self._bot, "_smart_wire_mgr", None) is None`. Shows
an HTML `QLabel` explaining that Bot Swarm isn’t active for this bot and
how to enable it (register with the Smart Wire manager via the wizard).
Long but navigational — operator needs the “how to enable” pointer when
nothing else is on the tab. Kept.

### Section 1 — `Swarm Connections & Capital Flow` summary

| Row | Value source | Type |
|-----|--------------|------|
| Outbound wires | `len(wires_dict[bot_id])` | count |
| Inbound wires | count of `wires_dict[src].get(bot_id)` across sources | count |
| Lifetime wired-in | `ledger.wired_in`, coloured green if > 0 | USD |
| Lifetime wired-out | `ledger.wired_out`, coloured orange if > 0 | USD |
| Net flow | `wired_in − wired_out`, coloured by sign | signed USD |
| Pending wire credits | `_bot._pending_wire_credits`, coloured cyan if > 0 | USD |

### Section 2 — `Provenance & Mature-Profit Spawn State` (conditional on `ledger`)

| Row | Value source |
|-----|--------------|
| Starting balance (seed) | `ledger.starting_balance` |
| Predominant funder (PPS) | `ledger.predominant_source` property (non-SEED max) |
| Mature profit total (*N*% of P&L) | `ledger.mature_profit_total` property (haircut applied) |
| Mature profit allocated to spawns | `ledger.mature_profit_allocated` |
| Mature profit available | `ledger.mature_profit_available` property |
| Provenance breakdown | `ledger.provenance` dict, formatted |

### Section 3 — `Outbound Wires (N)` table (conditional on `outbound`)

`QTableWidget`, 3 columns: Target Bot (`{id} ({asset})`), Wire %,
Lifetime $ to target (aggregated from transactions feed). Max height
180 px, non-editable, alternating row colours.

### Section 4 — `Inbound Wires (N)` table (conditional on `inbound`)

Same shape as outbound, columns: Source Bot, Wire %, Lifetime $ from
source.

### Section 5 — `Pending Wire Credits (N)` table (conditional on ledger)

`QTableWidget`, 4 columns: Age, Source, USD, Ref.

### Section 6 — `Recent Wire Transactions` table (conditional)

`QTableWidget`, last 20 transactions involving this bot. 5 columns: Age,
Direction (`OUT →` orange / `← IN` green), Other Bot, USD, Type.

### Empty state B — attached but no activity (line 1795-1806)

Fires when manager is attached but every conditional section produced
nothing. Short paragraph explaining how outbound wires are configured
and when inbound wires fire. Kept — same rationale as empty state A.

## Runtime source verification

All attributes / properties the tab reads exist on the appropriate
runtime object:

| Reference | Location |
|-----------|----------|
| `_smart_wire_mgr` | `scrumming_bot.py:606` (init None), `707` (setter) |
| `_pending_wire_credits` (float) | `scrumming_bot.py:628, 1558` (increment) |
| `_pending_wire_ledger` (list) | `scrumming_bot.py:629, 1559` (append) |
| `SmartWireManager._wires` | `smart_wire.py` (topology dict) |
| `SmartWireManager._ledgers` | `smart_wire.py` |
| `SmartWireManager._transactions` | `smart_wire.py` |
| `SmartWireLedger.starting_balance` | `smart_wire.py:82` |
| `SmartWireLedger.wired_in` / `wired_out` | `smart_wire.py:79-80` |
| `SmartWireLedger.mature_profit_allocated` | `smart_wire.py:83` |
| `SmartWireLedger.mature_profit_total` (property) | `smart_wire.py:99` |
| `SmartWireLedger.mature_profit_available` (property) | `smart_wire.py:112` |
| `SmartWireLedger.predominant_source` (property) | `smart_wire.py:90` |
| `SmartWireLedger.provenance` (dict) | `smart_wire.py:81` |
| `SmartWireLedger.MATURE_RATIO` (class attr) | `smart_wire.py:87` = **0.7** |

All pending-credit dict fields (`ts`, `source`, `usd`, `ref`) and
transaction attributes (`source_bot`, `target_bot`, `amount`, `timestamp`,
`wire_type`) are produced by the smart-wire runtime and consumed
correctly by the tab.

## Changes shipped this pass

### Change 1 — removed pending-credits prose explainer (F34)

`bot_live_settings.py:1725-1734` (pre-edit) — an 80-word `QLabel`
appended below the pending-credits table describing v3.15.69 stacking
mechanics. Same “hallucinatory descriptive text” pattern operator asked
us to retire from the Fold Tranches tab this session. Column headers
(Age / Source / USD / Ref) plus per-row values are the authoritative
representation of pending-credit state; the meta-prose repeated
mechanical claims (v3.15.69 stacking, tranche-absorption) that would
drift as the runtime evolves.

Replaced with a placement comment citing the reason so future readers
understand the deliberate omission.

### Change 2 — dynamic-source `70% of P&L` label (F35)

`bot_live_settings.py:1581` (pre-edit) — the mature-profit row label
hardcoded `(70% of P&L)`. Currently accurate (`MATURE_RATIO = 0.7` at
`smart_wire.py:87`) but drift-prone if the constant ever changes. Now
computed from `SmartWireLedger.MATURE_RATIO` at render time, falling
back to `70` with a debug log if the import fails.

## Findings

### F34 — Prose explainer retired (shipped this pass)

See Change 1.

### F35 — Hardcoded 70% qualifier dynamic-sourced (shipped this pass)

See Change 2.

### F36 — Empty-state labels kept

Both empty-state labels (manager-not-attached and manager-attached-but-idle)
are longer than the Fold Tranches empty state, but they serve a
navigational purpose when nothing else is on the tab. Retained.

### F37 — Defensive property probes silently degrade

Lines around 1562 / 1573 / 1578 wrap ledger property accesses in
`try / except: pass`-with-comment. Consistent with the existing R28-OK
convention across the file; not new. GUI archetype was clearing these
in a prior pass — no HIGH findings here now. Info only.

### F38 — Transaction feed scan is O(N) per section

Sections 3 and 4 iterate the full transactions list to sum per-target /
per-source lifetime. For a bot with many transactions this could be
slow on the render path. Not measurable at current transaction volumes.
Deferred.

### F39 — Header text uses non-ASCII arrow `←` / `→`

Direction column and label text use Unicode arrows. Renders correctly
in PySide6 on Windows. Consistent with existing conventions across the
file. No fix.

## Recommendation

Ship the two changes as v3.23.36. Empty-state labels and other minor
observations require no action.
