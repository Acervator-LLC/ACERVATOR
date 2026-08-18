# Bot Details — Status tab verification (v3.23.23)

**Bot audited**: `c8e5c5db` (CHIP/USD, SCRUMMING mode).
**Display surface**: `src/gui/bot_live_settings.py` lines 550–632.
**Backing dataclass**: `src/trading/bot_container.py` `BotStats` (lines 620–690).
**Directive** (operator, 2026-05-10): "Everything that is available on the
exchange and is related to position health should not be getting calculated
locally in some strange manner."

**FALSIFICATION**: this report is wrong if (a) any listed source line does
not match the running code after this session, (b) a field marked
“exchange-sourced” is actually derived locally in a code path I missed,
or © a field marked “local (justified)” has an exchange API that could
supply it.

---

## Per-field verdict

| # | Field | Source | Verdict |
|---|---|---|---|
| 1 | Realised P/L | Exchange (`get_my_trades` → FIFO in `compute_position_health`) | ✓ correct |
| 2 | Unrealised P/L | **Mixed**: ticker.last (exchange) × internal `_main_lots` cost basis (local) | ✗ partial — should use exchange cost basis |
| 3 | Avg Entry (exchange) | Exchange (`get_my_trades` → weighted-avg buy in `compute_position_health`) | ✓ correct |
| 4 | Cost Basis Total | Exchange (qty × avg_entry, both from `get_my_trades`) | ✓ correct |
| 5 | Fees Paid | Exchange (sum of `Trade.fee` from `get_my_trades`) | ✓ correct |
| 6 | Total Trades | **Local** counter incremented on every executed order | ⚠ exchange has `exchange_trade_count` but this display uses the local counter |
| 7 | Active Buys | **DEAD FIELD** — always 0, never assigned anywhere in `src/` | ✗ real bug |
| 8 | Active Sells | **DEAD FIELD** — always 0, never assigned anywhere in `src/` | ✗ real bug |
| 9 | Current Price | Exchange (`ticker.last` from `fetch_ticker`) | ✓ correct |
| 10 | Uptime | **Local** (`time.monotonic() - self._start_time`) | ✓ correct — see justification |

---

## Detailed verification per field

### 1. Realised P/L — ✓ exchange-sourced (correct)

- **Rendered at**: [bot_live_settings.py:583-593](src/gui/bot_live_settings.py:583)
  ```python
  _re = float(getattr(_bot_stats, "realized_pnl_exchange", 0.0) or 0.0)
  ...
  sf.addRow("Realised P/L:", rep_lbl)
  ```
- **Populated at**: [scrumming_bot.py:3196](src/trading/scrumming_bot.py:3196)
  ```python
  self.stats.realized_pnl_exchange = float(_ph.realized_pnl_usd)
  ```
- **Source**: `compute_position_health()` at [exchange/position_health.py:18-21](src/exchange/position_health.py:18) — FIFO-matched buy/sell pairs derived from `get_my_trades()` API call. Refreshed every 5 min via `refresh_exchange_position_health()`.
- **Freshness gate**: displays “— (refresh pending)” if `exchange_data_fresh_ts == 0` (pre-first-refresh).
- **Verdict**: correctly exchange-sourced. Matches Coinbase's Returns semantic for closed cycles.

### 2. Unrealised P/L — ✗ partially local (drift from directive)

- **Rendered at**: [bot_live_settings.py:595-599](src/gui/bot_live_settings.py:595)
  ```python
  _ue = float(getattr(_bot_stats, "unrealised_pnl", 0.0) or 0.0)
  ```
- **Populated at**: [scrumming_bot.py:5100-5112](src/trading/scrumming_bot.py:5100)
  ```python
  _live_px = float(getattr(ticker, "last", 0.0) or 0.0)
  _cost_basis = sum(l["units"] × l["initial_buy_price"] for l in self._main_lots)
  _market_value = self._current_holdings * _live_px
  self.stats.unrealised_pnl = _market_value - _cost_basis
  ```
- **Split**: `_live_px` and `_current_holdings` (from `fetch_balance`) are exchange-derived; `_main_lots × initial_buy_price` is the bot's INTERNAL lot ledger, not the exchange's cost basis.
- **Problem**: The exchange already knows the true cost basis — we compute it and store it at `stats.cost_basis_total_exchange` (verified working, field 4). But `unrealised_pnl` still uses the internal `_main_lots` sum. Result: internal-vs-exchange cost-basis divergence flows into Unrealised P/L, silently.
- **Fix**: change line 5103-5107 to `_cost_basis = float(self.stats.cost_basis_total_exchange or 0.0)`. Then Unrealised = (exchange price × exchange holdings) − exchange cost basis. Fully exchange-derived, matches the Coinbase Unrealized display semantic.
- **Verdict**: needs correction. Deferred to your call — separate ticket or bundle with this Status audit's fix pass?

### 3. Avg Entry (exchange) — ✓ exchange-sourced (correct)

- **Rendered at**: [bot_live_settings.py:601-603](src/gui/bot_live_settings.py:601)
- **Populated at**: [scrumming_bot.py:3197](src/trading/scrumming_bot.py:3197)
  ```python
  self.stats.avg_entry_exchange = float(_ph.avg_entry)
  ```
- **Formula** (from position_health.py docstring): weighted running average of BUY prices for open position. `new_avg = (old_qty × old_avg + buy_qty × buy_price) / new_qty` on BUY; qty reduces but avg stays on SELL. Matches Coinbase “Avg Entry” display.
- **Verdict**: correctly exchange-sourced.

### 4. Cost Basis Total — ✓ exchange-sourced (correct)

- **Rendered at**: [bot_live_settings.py:604-605](src/gui/bot_live_settings.py:604)
- **Populated at**: [scrumming_bot.py:3198](src/trading/scrumming_bot.py:3198)
  ```python
  self.stats.cost_basis_total_exchange = float(_ph.cost_basis_total_usd)
  ```
- **Formula**: `qty × avg_entry` — both from exchange trade history. Pure derivation, no I/O.
- **Verdict**: correctly exchange-sourced.

### 5. Fees Paid — ✓ exchange-sourced (correct)

- **Rendered at**: [bot_live_settings.py:606-608](src/gui/bot_live_settings.py:606)
- **Populated at**: [scrumming_bot.py:3199](src/trading/scrumming_bot.py:3199)
  ```python
  self.stats.fees_paid_exchange = float(_ph.fees_paid_total)
  ```
- **Formula** ([position_health.py:88](src/exchange/position_health.py:88)): `sum(t.fee for t in trades)` — direct sum of exchange-reported per-trade fees. In USD/quote currency.
- **Verdict**: correctly exchange-sourced.

### 6. Total Trades — ⚠ local counter (available on exchange, not used here)

- **Rendered at**: [bot_live_settings.py:619](src/gui/bot_live_settings.py:619)
  ```python
  sf.addRow("Total Trades:", QLabel(str(stats.get("total_trades", 0))))
  ```
- **Populated by**: internal counter incremented at 6 sites in `scrumming_bot.py` (lines 2243, 8333, 8571, 8870, 9149, 9743) — every time this bot executes a trade at the exchange.
- **Exchange alternative**: `stats.exchange_trade_count` IS populated from `get_my_trades()` at [scrumming_bot.py:3200](src/trading/scrumming_bot.py:3200) but this display reads the local counter. The tooltip on Realised P/L (line 589) already cites `exchange_trade_count`, so the exchange value is available.
- **Semantic difference**: local counter = trades this process has executed (resets to 0 on restart, unless persisted). exchange_trade_count = all trades in the fill window queried from the exchange for this symbol. Not necessarily equal.
- **Verdict**: consistent with the operator directive would use `exchange_trade_count`. Current display is not strictly “wrong” but drifts from the directive.

### 7. Active Buys — ✗ dead field (real bug)

- **Rendered at**: [bot_live_settings.py:620](src/gui/bot_live_settings.py:620)
  ```python
  sf.addRow("Active Buys:", QLabel(str(stats.get("active_buys", 0))))
  ```
- **Populated by**: **nothing**. Grep for `active_buy_orders` across all of `src/` returns exactly 3 hits:
  - Definition at `bot_container.py:644`: `active_buy_orders: int = 0`
  - Read at `bot_container.py:1175`: `"active_buys": self.stats.active_buy_orders`
  - No assignment anywhere. Field stays at dataclass default `0` for the bot's entire lifetime.
- **Why the operator sees `0`**: exactly what the dead field returns.
- **What it should be**: count of unfilled BUY orders open on the exchange right now. Available via `exchange.fetch_open_orders(symbol)` (ccxt standard) filtered by `side == "buy"`.
- **Verdict**: dead field. Fix requires (a) a new coroutine that polls `fetch_open_orders` and updates `stats.active_buy_orders` + `active_sell_orders`, wired into the same 5-min refresh cycle as `refresh_exchange_position_health`, OR (b) if these values are stale by design, remove the field + the GUI row entirely (R-CLN).

### 8. Active Sells — ✗ dead field (real bug, same as #7)

- **Rendered at**: [bot_live_settings.py:621](src/gui/bot_live_settings.py:621)
- **Populated by**: **nothing**. Same story as `active_buy_orders`.
- **Verdict**: dead field. Same fix path.

### 9. Current Price — ✓ exchange-sourced (correct)

- **Rendered at**: [bot_live_settings.py:623-625](src/gui/bot_live_settings.py:623)
  ```python
  price = stats.get("current_price", 0)
  sf.addRow("Current Price:", QLabel(_fp(price) if price > 0 else "—"))
  ```
- **Populated at**: 3 sites in `scrumming_bot.py` (lines 3298, 3754, 4210) — all `self.stats.current_price = ticker.last` where `ticker` comes from `exchange.fetch_ticker(symbol)`.
- **Freshness**: refreshed on every bot tick (fastest cadence in the code — sub-minute typically).
- **Verdict**: correctly exchange-sourced.

### 10. Uptime — ✓ local (justified — cannot come from exchange)

- **Rendered at**: [bot_live_settings.py:626](src/gui/bot_live_settings.py:626)
  ```python
  sf.addRow("Uptime:", QLabel(f"{stats.get('uptime', 0):.0f}s"))
  ```
- **Populated at**: [bot_container.py:1188-1193](src/trading/bot_container.py:1188)
  ```python
  "uptime": round(
      (time.monotonic() - self._start_time)
      if (self._start_time and self.state in (RUNNING, STARTING))
      else self.stats.uptime_seconds, 1),
  ```
- **Why local and not exchange**: uptime is a **client-side** concept. It measures how long this bot process has been running on this machine since it last entered RUNNING/STARTING state. The exchange has no notion of “the operator's bot process” — from the exchange's point of view, every API call is a stateless authenticated request, not a session. There is no exchange endpoint that returns “how long has bot X been running.” This value must be local.
- **Verdict**: correctly local. Justified by the shape of the concept.

---

## Summary — action items ranked

| Priority | Item | Effort | Nature |
|---|---|---|---|
| P1 | **Active Buys / Active Sells (fields 7 + 8)** — dead fields silently showing `0` forever | ~1 hr | Real bug. Either wire to `fetch_open_orders` on the 5-min refresh, or remove the fields + rows entirely (R-CLN) |
| P2 | **Unrealised P/L (field 2)** — cost basis uses internal `_main_lots` instead of `stats.cost_basis_total_exchange` | ~10 min | Directive drift. One-line change in scrumming_bot.py:5103-5107 to use the exchange value |
| P3 | **Total Trades (field 6)** — display uses local counter, `exchange_trade_count` is available | ~5 min | Directive drift. One-line change in bot_container.py:1171 to prefer `exchange_trade_count` when fresh, fallback to local |

Values 1, 3, 4, 5, 9, 10 are correctly sourced and require no change.

Ready to proceed with any of P1/P2/P3 on your call. All findings are pinnable via new test assertions on the Status tab data flow.
