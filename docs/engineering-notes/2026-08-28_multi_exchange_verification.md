# Multi-exchange verification — 15 declared venues

Issue #63. Measured 2026-08-28 from the operator's workstation in Oregon,
United States. ccxt 4.5.76, Python 3.14.4.

## Method, and its hard limit

Every number below comes from a public, unauthenticated endpoint. No
credentials were used for any venue. No order was placed, modified or
cancelled anywhere.

| established | how |
|---|---|
| reachable | HTTP GET of the venue's `PREFLIGHT_URLS` entry (`src/exchange/ccxt_connector.py:213`) |
| US / Oregon accessible | the same request, from the operator's own IP |
| top ten by volume | CoinGecko public `/api/v3/exchanges`, 2026-08-28 |
| timeframes offered | `exchange.timeframes` after a public `load_markets()` |
| passphrase required | ccxt `requiredCredentials['password']` |
| precision / min-order metadata | `load_markets()` market dicts, counted over every active spot market |

**NOT established, for any venue including Coinbase:** order placement,
fill behaviour, fee tiers as charged, balance reads, order lifecycle,
rate-limit behaviour under authenticated load. Those need credentials on
the venue. A public endpoint answering is not evidence that an order
would be accepted, and no verdict below upgrades it to one.

Coinbase carries the verdict `supported` because Acervator has traded on
it with real money, not because its endpoints answered.

## Top ten by volume — source and date

CoinGecko `/api/v3/exchanges`, fetched 2026-08-28, 500 rows.

The ranking used is CoinGecko's **trust-score rank**, not raw reported
volume. Raw 24h volume ordering puts BTCC (trust rank 155), CoinUp.io
(166) and Tapbit (83) at ranks 2, 3 and 5 — self-reported figures no
ranking treats as real. CoinGecko's `trade_volume_24h_btc_normalized`,
the de-washed figure, was null on all 500 rows, so it could not be used.

| rank | venue | in `SUPPORTED_EXCHANGES` |
|---|---|---|
| 1 | Coinbase Exchange | yes |
| 2 | Binance | yes |
| 3 | Kraken | yes |
| 4 | OKX | yes |
| 5 | Gate | yes (`gateio`) |
| 6 | Bitget | yes |
| 7 | Bitstamp | yes |
| 8 | MEXC | yes |
| 9 | Bybit | yes |
| 10 | **LBank** | **NO** |

The registry covers nine of the top ten. **LBank is absent.** Measured
2026-08-28: `https://api.lbank.info/v2/timestamp.do` returns HTTP 200 in
295 ms, `ccxt.lbank().load_markets()` returns 2172 markets (1373 spot),
twelve timeframes, no passphrase, `precisionMode` TICK_SIZE. It is
reachable and would fit the registry. **Not added — the operator sets
the list.**

Four declared venues are far outside the top ten: Gemini (27), Bitfinex
(40), HTX/`huobi` (85), Poloniex (92).

## The 15 declared venues

`SUPPORTED_EXCHANGES`, `src/exchange/ccxt_connector.py:122`.

| venue | rank | reachable | US accessible | tf offered / declared | passphrase | precision / min-order metadata | verdict |
|---|---|---|---|---|---|---|---|
| coinbase | 1 | yes, HTTP 200, 176 ms | yes | 8 / 8 — exact | no | 929/929 spot carry amount-min, cost-min, both precisions | **supported** — traded with real money |
| binance | 2 | **no, HTTP 451** | **no** | 11 / 11 — ccxt static metadata, venue unreachable | no | unmeasurable, `load_markets` refused | **unsupported from here** — geo-blocked |
| kraken | 3 | yes, HTTP 200, 254 ms | yes | 8 / 8 — exact | no | 1437/1437 complete | **unverified** — no credentials, nothing traded |
| okx | 4 | yes, HTTP 200, 215 ms | yes | 11 / 11 — exact | **yes** | 1383/1383 amount-min; **0/1383 cost-min** | **unverified** |
| gateio | 5 | yes, HTTP 200, 757 ms | yes | 9 / 11 — **lacks 6h, 12h** | no | 2232/2232 complete | **unverified** |
| bitget | 6 | yes, HTTP 200, 421 ms | yes | 11 / 11 — exact | **yes** | 1294/1294 amount-min; 1224/1294 cost-min | **unverified** |
| bitstamp | 7 | yes, HTTP 200, 549 ms | yes | 11 / 11 — exact | no | **0/303 amount-min**; 303/303 cost-min | **unverified** |
| mexc | 8 | yes, HTTP 200, 258 ms | yes | 8 / 11 — **lacks 2h, 6h, 12h** | no | 2099/2099 complete | **unverified** |
| bybit | 9 | **no, HTTP 403** | **no** | 11 / 11 — ccxt static metadata, venue unreachable | no | unmeasurable, `load_markets` refused | **unsupported from here** — geo-blocked |
| kucoin | 11 | yes, HTTP 200, 325 ms | yes | 11 / 11 — exact | **yes** | 1007/1007 complete | **unverified** |
| cryptocom | 12 | yes, HTTP 200, 207 ms | yes | 10 / 11 — **lacks 2h** | no | **0/578 amount-min and 0/578 cost-min** | **unverified** |
| gemini | 27 | yes, HTTP 200, 389 ms | yes | 7 / 11 — **lacks 2h, 4h, 12h, 1w** | no | 331/331 amount-min; **0/331 cost-min** | **unverified** |
| bitfinex | 40 | yes, HTTP 200, 119 ms | yes | 10 / 11 — **lacks 2h** | no | 197/197 amount-min; **0/197 cost-min**; **SIGNIFICANT_DIGITS mode** | **unverified** |
| huobi | 85 | yes, HTTP 200, 339 ms | yes | 8 / 11 — **lacks 2h, 6h, 12h** | no | 2159/2159 complete | **unverified** — public endpoints answer, venue terms refuse US accounts |
| poloniex | 92 | yes, HTTP 200, 663 ms | yes | 11 / 11 — exact | no | 866/866 complete | **unverified** — public endpoints answer, venue terms refuse US accounts |

"tf declared" is `src/exchange/timeframes.py`, counted against
`ALL_TIMEFRAMES` (11 entries). Eight venues had no entry in that map and
were reading the permissive fallback, which declares all eleven.

Verdict counts: **1 supported, 2 unsupported from here, 12 unverified.**

## `US_RESTRICTED_EXCHANGES` — declared vs measured

Declared before this note, as one set: `poloniex`, `huobi`, `bybit`.

Measured 2026-08-28 from Oregon:

| venue | declared restricted | public endpoint from a US IP |
|---|---|---|
| bybit | yes | **HTTP 403** — CloudFront, "configured to block access from your country". Declaration confirmed. |
| poloniex | yes | **HTTP 200**, 866 spot markets load. Public API is not IP-blocked. |
| huobi | yes | **HTTP 200**, 2159 spot markets load. Public API is not IP-blocked. |
| binance | **no** | **HTTP 451** — "Service unavailable from a restricted location". **Absent from the declared set and the most-blocked venue measured.** |

The declared set conflated two different refusals. It is now split into
two sets whose membership is established by two different methods:

- `US_IP_BLOCKED_EXCHANGES` = `{binance, bybit}` — measured, public
  endpoint refuses a US IP. The venue cannot be reached at all.
- `US_ACCOUNT_RESTRICTED_EXCHANGES` = `{poloniex, huobi}` — from venue
  terms, not from a probe. Public data flows; a US account is refused.
  **Not falsifiable without opening an account there**, so neither was
  removed.

`US_RESTRICTED_EXCHANGES` is the union, so the warning at
`ccxt_connector.py:542` fires on the same three venues as before, plus
Binance.

## Timeframes — the "equal functionality" answer

Eight of the fifteen venues had no entry in `_AVAILABILITY` and read the
permissive fallback, which hands back all eleven timeframes. **Six of the
eight offer fewer.**

| venue | fallback claimed | measured | over-claimed |
|---|---|---|---|
| bitfinex | 11 | 10 | 2h |
| cryptocom | 11 | 10 | 2h |
| gateio | 11 | 9 | 6h, 12h |
| gemini | 11 | 7 | 2h, 4h, 12h, 1w |
| huobi | 11 | 8 | 2h, 6h, 12h |
| mexc | 11 | 8 | 2h, 6h, 12h |
| bitget | 11 | 11 | none |
| bitstamp | 11 | 11 | none |
| poloniex | 11 | 11 | none |

The failure mode is the one `timeframes.py` documents in its own module
docstring: the GUI offers the timeframe, ccxt returns an empty candle
array, the TA engine sees fewer than 30 candles and holds. No error is
raised anywhere.

The seven venues that already had entries — coinbase, binance, kraken,
kucoin, bybit, okx, and the `coinbasepro` / `cb` / `binanceus` aliases —
matched measurement exactly. The declared map was accurate; the fallback
was the defect.

### Timeframe-pinned call sites

| site | pin | venues that lack it |
|---|---|---|
| `src/trading/scrumming_bot.py:385` `DEFAULT_PHANTOM_TIMEFRAMES` | 5m 15m 30m 1h **4h** 1d | 4h: coinbase, gemini |
| `src/trading/scrumming_bot.py:3714` phantom lock | **4h**, 1h | 4h: coinbase, gemini |
| `src/trading/phantom_balance.py:643` documented phantom set | 5m 15m 1h **4h** 1d | 4h: coinbase, gemini |

`src/trading/ta_engine.py:484` weights timeframes through
`tf_weights.get(tf, 1.0)`, so a missing timeframe is not voted rather
than raising. The breakage is upstream of it: no candles arrive at all.

The 4h phantom lock at `scrumming_bot.py:3714` **cannot fire on
Coinbase**, the only venue in production, because Coinbase publishes no
4h candle. Half of that two-timeframe lock has never been reachable.

## Passphrase

`PASSPHRASE_EXCHANGES` = `{kucoin, okx, bitget}`,
`ccxt_connector.py:173`.

Checked against ccxt `requiredCredentials['password']` for all 15
venues. **Exact match: 3 of 3 correct, 12 of 12 correctly absent.** No
change.

## Market metadata — a defect present on the live venue

`AssetInfo.price_precision` and `AssetInfo.amount_precision`
(`src/exchange/base.py:148`) are documented "Decimal places". They are
consumed as decimal places: `BotContainer._get_market_limits`
(`src/trading/bot_container.py:192`) returns `amount_precision` and
`guarded_place_order` truncates a live order size to that many places
before its minimum-size check.

The producer did not produce decimal places.

```python
price_precision=int(precision.get("price", 8) or 8),
amount_precision=int(precision.get("amount", 8) or 8),
```

ccxt reports decimal places only under `DECIMAL_PLACES` mode.
**Fourteen of the fifteen venues report `TICK_SIZE`**, where the same
field carries a step size — `1e-06`, `0.01`, `1.0`. `int(1e-06)` is `0`,
`0` is falsy, and the `or 8` fallback then answers for a market that
published its step.

Measured 2026-08-28 over every active spot market each venue publishes:

| venue | markets with the wrong amount precision |
|---|---|
| **coinbase** | **886 / 929** |
| gateio | 2232 / 2232 |
| huobi | 2158 / 2159 |
| mexc | 2097 / 2099 |
| okx | 1370 / 1383 |
| bitget | 1293 / 1294 |
| kucoin | 1004 / 1007 |
| kraken | 968 / 1437 |
| poloniex | 866 / 866 |
| cryptocom | 578 / 578 |
| gemini | 319 / 331 |
| bitstamp | 240 / 303 |
| bitfinex | 0 / 197 (SIGNIFICANT_DIGITS, `int()` is a no-op) |

Coinbase `BTC/USD` publishes a `1e-08` step, which happens to equal the
fallback of 8, so the venue in production and the pair most watched on
it are among the 43 Coinbase markets the defect gets right. `XRP/USD`
publishes `1e-06`; the sizer was handed 8. A year of live trading did
not surface it.

Two distinct shapes:

- step **below** 1 — `int()` truncates to 0, falsy, fallback fires.
- step **at or above** 1 — Gate.io publishes `1.0` on whole-unit
  markets. `int(1.0)` is `1` and truthy, so the fallback does *not* fire
  and the sizer receives one decimal place on a market that accepts
  none.

`precision_to_decimals` in `ccxt_connector.py` converts by
`precisionMode`. Under `SIGNIFICANT_DIGITS` a decimal-place count does
not exist independently of the number being rounded, so it returns the
caller's default rather than misreading a digit count as a place count.
That moves Bitfinex `price_precision` from 5 to 8;
`AssetInfo.price_precision` has no consumer on the order path.

`getattr(self._ex, "precisionMode", CCXT_DECIMAL_PLACES)` keeps the
Simulator path unchanged: `TabletBackend._default_market`
(`src/exchange/tablet_backend.py:216`) publishes integer decimal places
and declares no `precisionMode`, so the default returns exactly what it
publishes.

### Minimum order metadata gaps

`get_markets` coerces a missing minimum to `0.0`, and
`_get_market_limits` fails open on absence, so these venues degrade
silently rather than blocking:

| venue | gap |
|---|---|
| cryptocom | **no amount-min and no cost-min on any of 578 spot markets** |
| bitstamp | no amount-min on any of 303 |
| okx | no cost-min on any of 1383 |
| gemini | no cost-min on any of 331 |
| bitfinex | no cost-min on any of 197 |

On cryptocom the pre-flight size check has nothing to check against.

## Coinbase-shaped code

| site | shape |
|---|---|
| `src/exchange/ccxt_connector.py:502` | `if self._exchange_id == "coinbase" and api_secret:` |
| `src/exchange/ccxt_connector.py:232` | `EXCHANGE_OPTIONS` holds one key, `coinbase` |
| `src/exchange/ccxt_connector.py:244` | `DISABLE_FETCH_CURRENCIES` holds one key, `coinbase` |
| `src/trading/stone_tablets/fetcher.py:653` | `if exchange_id == "coinbase":` |
| `src/trading/scrumming_bot.py:2149` | `_EXCHANGE_UNSUPPORTED_TFS` — see below |

### `_EXCHANGE_UNSUPPORTED_TFS` contradicts the measurement

`src/trading/scrumming_bot.py:2149` carries a second, hardcoded copy of
timeframe availability:

```python
_EXCHANGE_UNSUPPORTED_TFS = {
    "coinbase": {"4h", "2h", "30m", "1m"},
}
```

Measured Coinbase set, 2026-08-28: `1m 5m 15m 30m 1h 2h 6h 1d`.
**Coinbase offers 1m, 30m and 2h.** Only 4h is genuinely absent, which
is what `timeframes.py` has said all along.

When an operator applies a phantom timeframe set on Coinbase, this
filter silently strips 1m, 30m and 2h from it. That is a live-venue
behaviour change and it is **not fixed here** — it lives in the trading
engine, it alters what running bots do, and it is its own item.

## Changes made

| file | change |
|---|---|
| `src/exchange/ccxt_connector.py` | `precision_to_decimals` and the three `precisionMode` constants; `get_markets` uses it for both precisions; `US_IP_BLOCKED_EXCHANGES` / `US_ACCOUNT_RESTRICTED_EXCHANGES` with `US_RESTRICTED_EXCHANGES` as their union; `VERIFIED_EXCHANGES`; `VENUE_MEASUREMENT_DATE`; `exchange_label`; `list_supported_exchanges` carries verified, us_ip_blocked and label |
| `src/exchange/timeframes.py` | measured allow-lists for the nine venues that were reading the permissive fallback |
| `src/gui/settings_dialog.py` | the exchange picker builds its label from `exchange_label` |
| `src/gui/preflight_check.py` | the duplicate `int(precision)` arithmetic replaced with `precision_to_decimals` |
| `tests/test_exchange_registry.py` | precisionMode constants pinned against installed ccxt; the two US sets and their union; `VERIFIED_EXCHANGES`; label and listing status; no supported venue falls through the timeframe fallback |
| `tests/test_venue_precision_is_decimal_places.py` | new — the precision contract, driven through `get_markets` |
| `tests/fixtures/venue_precision_metadata.json` | new — the measured metadata behind it |
| `tests/test_unitc_ccxt_connector_behaviour_parity.py` | listing-shape test restated over the wider row |

`SUPPORTED_EXCHANGES` is **unchanged**. No venue was dropped and none was
added. Binance and Bybit stay in the registry and now say "blocked from
US" where a user picks one; LBank stays out.

The picker label follows the wording already in the operator's tree for
equity brokers (`settings_dialog.py:186`, "planned, not yet live").

## Open, not resolved here

| item | where |
|---|---|
| `_EXCHANGE_UNSUPPORTED_TFS` strips three timeframes Coinbase offers | `src/trading/scrumming_bot.py:2149` |
| the 4h phantom lock cannot fire on Coinbase | `src/trading/scrumming_bot.py:3714` |
| LBank is rank 10 and not in the registry | `src/exchange/ccxt_connector.py:122` |
| three GUI sites still build their own picker labels | `src/gui/live_bot_window.py:120`, `src/gui/init_wizard.py:112`, `src/gui/widgets/api_tester_tab.py:67` |
| every non-Coinbase venue's order placement, fills, fee tiers and balance reads | needs credentials on the venue |
