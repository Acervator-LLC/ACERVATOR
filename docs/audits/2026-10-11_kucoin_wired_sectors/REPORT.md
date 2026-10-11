# KuCoin — the eight connections and the six sectors

Read on 2026-10-11 from kucoin's own credential-free public endpoints and its
own published pages, with the home directory redirected. No credential was used.
No order was placed and none was previewed; `ex.fetch` was replaced before every
order body was composed. The synchronous path the product itself uses,
`src/exchange/ccxt_connector.py, in sync_connect`, answered on the first call,
so nothing here went through `ccxt.async_support`.

## What this venue is

One ccxt id loads two hosts. `load_markets` returns 1659 markets: 968 spot, 690
perpetual and 1 dated. All 1659 publish `active` True, so
`src/exchange/ccxt_connector.py, in is_listed_market` skips none, and all 1659
carry `info` as a mapping, so none of the list-shaped readers the bitfinex unit
guarded is exercised.

KuCoin is the fifth venue to publish its own asset categories, and the first to
publish them on two hosts under two field names.

## The eight connections

| # | The connection | Before | After |
|---|---|---|---|
| 1 | a connector exists and is registered | answered, `SUPPORTED_EXCHANGES` | unchanged |
| 2 | offered under every sector it serves | four sectors | six |
| 3 | the operator can enter its credentials | answered, key, secret and passphrase | unchanged |
| 4 | a Start press builds its connector | answered, the ccxt path | unchanged |
| 5 | its market rules record on connect | answered, 1659 rows | unchanged |
| 6 | its orders carry the shape the venue publishes | unread | `size`, a count, on both sides |
| 7 | a built variant selects for it | unread | six variants, all built |
| 8 | its gate decisions log under it | unread | six distinct paths |

KuCoin is the first venue in this run whose row 5 was already sound. The gap was
never the recording — it was the **sector** written on the recording.

### Row 3, measured

`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` draws
`src/gui/main_tabs/asset_class_surface.py, in venues_for_class` itself, so the
Add form's set is the screen's set by construction. Measured over all six
sectors, before and after: the two sets differ by nothing in either direction.
KuCoin sits in `src/exchange/ccxt_connector.py, at PASSPHRASE_EXCHANGES`, so the
form asks for a third field. `in known_venues` holds 26 ids and an invented id is
in none of them, which is the control.

### Row 8, measured

Six real decisions written through `LogManager.log_gate_decision` with the home
redirected.

```
trade/gate/kucoin/crypto/gate.log          1 line   BTC/USDT
trade/gate/kucoin/stocks/gate.log          1 line   AAPL/USDT:USDT
trade/gate/kucoin/commodities/gate.log     1 line   XAUT/USDT
trade/gate/kucoin/forex/gate.log           1 line   USDC/EUR
trade/gate/kucoin/futures_perps/gate.log   1 line   ETH/USDT:USDT
trade/gate/kucoin/indices/gate.log         1 line   SPY/USDT:USDT
```

Six distinct writer pairs opened, every row names its own sector in its own
`data.asset_class` field, and `src/core/log_paths.py, in gate_log_files` lists
all six, so a reader follows the writer. A sector nothing was written for has no
file, which is the control.

## Reading 1 — US-person eligibility, settled

**The Gate.io, Bitget and Bitfinex shape.**
`src/exchange/ccxt_connector.py, at US_ACCOUNT_RESTRICTED_EXCHANGES` gains the
id, which makes it six venues. `at US_IP_BLOCKED_EXCHANGES` does not, because
all eight kucoin public endpoints answered HTTP 200 from this address.

KuCoin's own Terms of Use at `www.kucoin.com/legal/terms-of-use` served 428,225
bytes and 338,575 characters of text once the tags came off, so the clause is in
the served markup and not rendered in the client. Article 17(5):

> "the User (whether as an individual or legal entity) is not a resident of or
> registered in, any of the Restricted Locations. For the purpose of this
> Agreement, 'Restricted Locations' shall include the United States (including
> its territories such as Puerto Rico, Guam, the Northern Mariana Islands,
> American Samoa, etc), Singapore, the mainland of China and Hong Kong,
> Malaysia, Kazakhstan, Uzbekistan, Ontario, and British Columbia of Canada,
> France, Netherlands, the Crimea, Donetsk, Luhansk, Zaporizhzhia and Kherson
> regions of Ukraine"

Article 102: "The Platform does not offer its services outside the Turks and
Caicos Islands."

**The agreement was read whole and the search is two-sided.**

| page | characters | "Restricted Locations" | "United States" | "not a resident of" | invented phrase |
|---|---|---|---|---|---|
| kucoin Terms of Use | 338,575 | 8 | 2 | 2 | 0 |
| kucoin Privacy Policy | 352,277 | 0 | 0 | 0 | 0 |
| gemini User Agreement | 324,517 | 0 | 9 | 0 | 0 |

Gemini is the negative control the gemini unit established: nine mentions of the
United States and no refusal clause. KuCoin's own privacy policy is a second
negative control. The invented phrase answered 0 on every page. The search finds
a refusal where one exists and reports nothing where none does.

## Reading 2 — sector truth comes from the venue, settled

**KuCoin publishes a category, so
`src/exchange/ccxt_connector.py, at VENUE_ASSET_SECTOR_RECORDS` goes from four
venues to five.** Both endpoints are public, credential-free, and already
reachable as ccxt implicit methods.

| host | path | rows | code field | sector field | the words it publishes |
|---|---|---|---|---|---|
| `api.kucoin.com` | `/api/v2/symbols` | 968 | `baseCurrency` | `market` | USDS 867, BTC 50, ALTS 20, DeFi 16, Stocks 5, KCS 4, FIAT 4, Meme 2 |
| `api-futures.kucoin.com` | `/api/v1/contracts/active` | 691 | `baseCurrency` | `assetClass` | CRYPTO 527, STOCK 155, METAL 6, COMMODITY 3 |

The futures host also names the exchange behind each equity contract:
`marketType` reads NASDAQ on all 155, and `subMarketType` reads US.STOCK on 134,
HK.STOCK on 15, KR.STOCK on 5 and JP.STOCK on 1.

**Control for the search.** Seven invented paths on the same host answered 404 —
`/api/v1/market/categories`, `/api/v1/market/sectors`, `/api/v1/instruments`,
`/api/v1/assets`, `/api/v1/categories`, `/api/v3/instruments` and
`/api/v1/products` — while `/api/v3/currencies` answered 200 with 2261 rows,
`/api/v2/symbols` 200 with 968, and `/api/v1/contracts/active` 200 with 691. The
instrument could find a page that exists.

### One record cannot read both, so the container holds a tuple

`AssetSectorRecord` carries one `sector_key` and the venue uses two field names,
so `VENUE_ASSET_SECTOR_RECORDS` now maps each venue id onto a tuple of records
and `in _published_asset_sectors` loops them. The four venues that held one
record each hold a one-tuple, and their readings are unchanged.

Measured, per option:

| record | crypto | stocks | commodities | forex | futures_perps |
|---|---|---|---|---|---|
| none, before | 956 | 0 | 8 | 14 | 681 |
| futures host alone | 964 | 156 | 12 | 0 | 527 |
| both hosts | 959 | 161 | 12 | 0 | 527 |
| both hosts, with the market citations | 958 | 160 | 12 | 2 | 527 |

Both hosts is the widest true reading. It gains the five spot xStock pairs the
venue's own `market: "Stocks"` group names, which the futures host never sees.

**The cost, stated plainly.** `in market_asset_class` reads
`PRECIOUS_METAL_CODES` and `FIAT_CURRENCY_CODES` only while `published` is None,
so any record switches the code-set reading off for the whole venue. That is the
arithmetic the bitfinex and gemini units measured and the reason both declined a
record. Here the record wins 164 markets and would lose 2, and the 2 are
recovered by a citation at the grain of the market.

### Two words must be named or they resolve by accident

`src/trading/ata_spm.py, in asset_class_named` resolves `CRYPTO` onto crypto and
`Stocks` onto stocks on their own. An unnamed `CRYPTO` would therefore return
crypto as the published sector for all 527 crypto perpetuals, overriding
`in is_contract_market` and emptying the futures sector. `FIAT` resolves to
nothing on its own, and it must still be named, because it groups the pairs
**quoted** in a fiat currency — BTC-EUR, ETH-EUR, USDC-EUR and USDT-EUR, keyed
by the bases BTC, ETH, USDC and USDT — so reading it as forex off the base code
would make every bitcoin pair a currency pair. Every word of both vocabularies
is named in the record.

### The record order matters, and the existing rule makes it safe

The spot record reads first and the futures record second.
`in _read_asset_sector_rows` skips a code only while `found.get(code)` is truthy,
so a code written as the empty string is revisited. PAXG and XAUT are written
empty by the spot grouping and then take the METAL row. The order would be wrong
the other way round only for a code whose two hosts both name a family, and
there is none.

## Reading 3 — the ticker collision, settled, and it cuts both ways

Eleven kucoin bases carry a code `FIAT_CURRENCY_CODES` holds for a national
currency. Nine are not a currency market.

| base | its only markets | kucoin's own words | read before | true |
|---|---|---|---|---|
| AMD | AMD/USDT:USDT | `assetClass` STOCK, `marketType` NASDAQ, no currency row | forex | stocks |
| NOK | NOK/USDT:USDT | `assetClass` STOCK, NASDAQ, US.STOCK | forex | stocks |
| RON | RON/USDT:USDT | `assetClass` CRYPTO, priced off okex, binance, gateio, mexc | forex | futures_perps |
| SCR | SCR/USDT, SCR/USDT:USDT | `fullName` "Scroll" | forex | crypto |
| BOB | BOB/USDT | `fullName` "bob" | forex | crypto |
| MNT | MNT/USDT | `fullName` "Mantle Network" | forex | crypto |
| USD1 | USD1/USDT | `fullName` "World Liberty Financial USD" | forex | crypto |
| USDS | USDS/USDT | `fullName` "USDS Stablecoin" | forex | crypto |
| USDC | USDC/USDT, USDC/USDT:USDT | `fullName` "USD Coin" | forex | crypto |
| USDT | USDT/USDC | `fullName` "Tether" | forex | crypto |
| USDC, USDT | USDC/EUR, USDT/EUR | "USD Coin", "Tether", "Euro" | forex | forex |

`NOK` is the sharpest. KuCoin's currency list calls NOK "Norwegian Krone",
because NOK is a deposit currency there. Its only **market** is the perpetual
NOKUSDTM, whose own record reads `assetClass` STOCK, `marketType` NASDAQ,
`subMarketType` US.STOCK, and whose index sources are `binance_index`,
`binance_futures`, `okx_index` and `finnhub`. That contract is Nokia, not the
krone. `AMD` has no currency row at all and the same contract shape.

`MNT` is the same code the bitfinex unit had to move back to crypto, and kucoin
refutes it the same way: its own `fullName` reads "Mantle Network".

### And the record would create a collision of its own

Of the 169 codes the record names, **8** are also a spot base. Seven agree:
"Apple xStock", "Circle xStock", "Robinhood xStock", "MicroStrategy xStock",
"Tesla xStock", "PAX Gold" and "Tether Gold". The eighth does not.

```
BNCUSDTM   assetClass STOCK, marketType NASDAQ, subMarketType US.STOCK
           priced off binance_index, binance_futures, finnhub
BNC-USDT   kucoin's own fullName: "Bifrost"
```

`BNC` is two assets. A base-keyed row cannot separate them, and nor can the
record.

### A base code is the wrong grain for three markets

`src/trading/scrumming/sizing.py, at CITED_VENUE_MARKET_SECTORS` is new, keyed
by venue and unified symbol, and `in venue_market_sector` answers it.
`market_asset_class` reads it ahead of `in venue_base_sector`. Three rows, all
kucoin, each the venue's own word.

| market | sector | why no base code can carry it |
|---|---|---|
| BNC/USDT | crypto | the perpetual under the same code is an equity contract |
| USDC/EUR | forex | USDC also bases USDC/USDT, a dollar token against a dollar token |
| USDT/EUR | forex | USDT also bases USDT/USDC, the same case |

`USDC/EUR` holds a dollar token against a national currency, which
`TOKEN_UNDERLYING_CODES` and `FIAT_CURRENCY_CODES` already read as forex. They
carry the legs of bitfinex's `EUR/USDT`, which the same two code sets read as
forex with no citation, swapped.
KuCoin names the three legs "USD Coin", "Tether" and "Euro" on its own
currency list and groups both euro pairs under its own spot word FIAT.

**The citation's two-sided control runs through the production function.**
`market_asset_class(record, published, "kucoin")` answers crypto for BNC/USDT
and forex for USDC/EUR; `market_asset_class(record, published, "")` answers
stocks and crypto, the un-cited reading. `venue_market_sector` answers None for
`("kucoin", "BTC/USDT")`, for `("kucoin", "BNC/USDT:USDT")`, for
`("gemini", "USDC/EUR")` and for `("", "USDC/EUR")`.

### This issue's second decision does not bite here

Of the ten codes in `at TOKEN_UNDERLYING_CODES`, only PAXG, XAUT, USD1, USDC,
USDS and USDT base a kucoin market. No euro, sterling, Australian dollar or
Singapore dollar token is listed, so kucoin raises no national-currency token
against a dollar stablecoin.

## Reading 4 — the cash market buy, settled

**KuCoin is not a member of
`src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY`, which keeps its
four.** It is the first venue to publish a cash field beside the unit field on
the same spot endpoint, and the library sends the unit.

```
spot      POST https://api.kucoin.com/api/v1/orders
          {"clientOid":"...","side":"buy","symbol":"BTC-USDT","type":"market","size":"0.001"}
          {"clientOid":"...","side":"sell","symbol":"BTC-USDT","type":"market","size":"0.001"}
          {"clientOid":"...","side":"buy","symbol":"BTC-USDT","type":"market","funds":"50"}   only with cost
contract  POST https://api-futures.kucoin.com/api/v1/orders
          {"clientOid":"...","side":"buy","symbol":"AAPLUSDTM","type":"market","leverage":1,"size":1}
unified   POST https://api.kucoin.com/api/ua/v1/unified/order/place
          {"tradeType":"SPOT",...,"orderType":"MARKET","sizeUnit":"BASECCY","size":"0.001"}
          {"tradeType":"FUTURES",...,"orderType":"MARKET","sizeUnit":"UNIT","size":"1"}
```

KuCoin's own Add Order page describes `size` as "Specify quantity for currency"
and offers both fields on a market order as "(Select one out of two: size or
funds)". Its Hold section names the funds field as cash: "For market price
buy/sell orders that require specific funds, we will hold the required funds in
from your account."

`funds` reaches the wire only when the caller passes a `cost` parameter.
`src/exchange/ccxt_connector.py, in place_order` builds its `extra_params` from
the client order id and the time-in-force alone, so no order this program places
can carry it. `createMarketBuyOrderWithCost` reads True on the capability map,
which names the separate `create_market_buy_order_with_cost` method, and no
caller in this tree reaches it. `createMarketBuyOrderRequiresPrice` is unset, so
kucoin is not one of the four venues that need a fetched price.

**The venue states the unit in a field of its own on the unified route.** Its
own page: "UTA | SPOT | `size` required. Unit controlled by `sizeUnit`. Market
Order: `BASECCY` (default) or `QUOTECCY`. Limit Order: `BASECCY` only
(`QUOTECCY` or empty not allowed)." And "UTA | FUTURES | `size` uses `UNIT`
(contracts)." The composed bodies carry `BASECCY` and `UNIT`. ccxt asks kucoin
which account mode is in force before every order, so the route follows the
operator's own account, and both routes send a count.

`in market_buy_names_cash` answered False for all 1659 markets.

### The contract counts lots, and the contract publishes its size

KuCoin's own futures page names three size fields: `qty` is "Specified in
**base currency** and must be an integer multiple of the multiplier", `valueQty`
is "Specified in **quote currency**", and `size` is the lot. ccxt sends `size`.

All 691 contracts publish an amount step of 1 and a minimum of 1, so
`in recorded_unit_rule` reads every one as `WHOLE_UNITS`. Each publishes a
`multiplier`, which ccxt carries as `contractSize` and
`src/exchange/base.py, at MarketRules` records as `contract_size`: 0.01 on the
Apple perpetual, 0.001 on the bitcoin perpetual, 0.01 on the WTI perpetual. 686
of the 1659 recorded rules carry one, which is the first venue reading to fill
that field from a live venue — this issue's row 10 records the field as built
with nothing in it.

## Reading 5 — `CITED_VENUE_ORDER_TYPES` per sector, settled

`in declared_order_types` reads **"market and limit"** off kucoin's own
capability map, where `createMarketOrder` is True, and stamps it on all 1659
recorded markets. `at CITED_VENUE_ORDER_TYPES` gains a row for each of the five
sectors kucoin records a market in — crypto, stocks, commodities, forex and
futures_perps — as the fallback for a market whose record was never read.
Indices gains no row, because no market selects it. `in order_types_for`
answered "market and limit" for all 1659.

KuCoin is the first venue in this program whose capability map holds no False.
All seventeen read True: `createOrder`, `createMarketOrder`,
`createMarketBuyOrderWithCost`, `createMarketSellOrderWithCost`,
`createStopOrder`, `fetchBalance`, `fetchMyTrades`, `fetchOpenOrders`,
`fetchClosedOrders`, `fetchOrder`, `cancelOrder`, `fetchOHLCV`, `fetchTicker`,
`fetchTickers`, `fetchPositions`, `fetchPosition` and `setLeverage`. Every read
path each sector needs is declared.

## Reading 6 — `code_leg`, settled: not needed

OKX publishes no base code on its contract types, so its record splits `instId`
on a `-`. That reading does not carry. KuCoin publishes `baseCurrency` on **691
of 691** futures rows and on **968 of 968** spot rows. `displayBaseCurrency`
differs on 4 rows only, all CRYPTO, and carries Chinese characters on those
four, so `baseCurrency` is the field and neither record names a `code_leg`.

## Per sector, the six points

| sector | market list | order route | order shape | position / fill | candles | variant |
|---|---|---|---|---|---|---|
| crypto | 958 rows | both endpoints | `size`, a count | `fetch_balance` / `fetch_my_trades` | 11 timeframes | Crypto Scrumming, built |
| stocks | 160 rows | both endpoints | same | same | same | Stock Scrumming, built |
| commodities | 12 rows | both endpoints | same | same | same | Commodity Scrumming, built |
| futures and perpetuals | 527 rows | contract endpoint | same, lots | `fetch_positions` True | same | Futures Scrumming, built |
| forex | 2 rows | spot endpoint | same | same | same | Forex Scrumming, built |
| indices | 0 rows | — | — | — | — | Index Scrumming, built |

`src/trading/scrumming/sizing.py, in sector_variant` names a built variant for
every one of the 1659 markets, and `in variant_built` answers True for all 1659.
At a reference price of $100 and a scrum excess of $500: Futures Scrumming 527,
Stock Scrumming 160, Crypto Scrumming 513, Commodity Scrumming 12, Forex
Scrumming 2, Whole Unit Scrumming 445.

`in market_unit_rule` over all 1659: futures and perpetuals 527 whole; stocks
155 whole and 5 fractional, the 5 being the spot xStock pairs; commodities 9
whole and 3 fractional; forex 2 fractional; crypto 760 fractional and 198 whole.

`src/exchange/timeframes.py, at _AVAILABILITY` needed no change. ccxt publishes
fourteen granularities for kucoin and `ALL_TIMEFRAMES` draws eleven, which is
exactly the row, nothing either way. The three it leaves are 3m, 8h and 1M. Only
the row's comment changed, because it read "supports a similar superset to
Binance" where a measurement belongs.

`src/exchange/market_inspector_fetcher.py` needed no change.
`in trading_products` already reads kucoin: 814 bases, 814 trading, none not
trading. KuCoin's spot records carry no `status` and no `trading_disabled`
field, so `_product_trades` reads `is_listed_market` alone, which the gemini
unit made correct. Control: a connector with no market table answers 0 bases.

## Five markets refuse, and the refusal is the built one

KuCoin lists 5 coin-margined contracts: the bitcoin, ether, solana and ripple
perpetuals settled in their own base, and one dated bitcoin future expiring
2026-12-25. `in quote_contract_size_shapes` answers a cash amount on both sides
of each, so `in size_shape_refusal` names the cause on the buy and on the sell:

> "the venue permits a cash amount alone on a buy of this product, and every
> built variant sizes a unit count rather than a cash amount in the quote
> currency"

The 686 USDT-margined contracts return an empty refusal, which is the control.
KuCoin is the second venue whose own records select the cash-amount variant this
issue's row 6 leaves unbuilt, and each market is still read and still charted.

The dated contract is the other half. `MarketRules.expires` reads True for it
alone, so `in venue_variant` answers the expiry mechanic and the close path row
5 built applies to one kucoin market.

## The verdicts

| Sector | Verdict | The cost |
|---|---|---|
| crypto | **yes** | nothing. 958 markets |
| stocks | **yes** | nothing. 160 markets: 155 equity perpetuals the venue labels NASDAQ, and 5 spot xStock pairs |
| commodities | **yes** | nothing. 12 markets: gold on four pairs, and the silver, palladium, platinum, copper, Brent, WTI and natural-gas perpetuals |
| futures and perpetuals | **yes** | nothing. 527 markets, of which 5 refuse on the unbuilt cash-amount variant |
| forex | **yes** | nothing. 2 markets: USD Coin and Tether against the euro |
| indices | **no market, offered** | the venue publishes no index word, and labels its thirteen index-fund and sector-fund contracts STOCK |

Indices is not a block. The door exists and the venue walks through it as
stocks: SPY, QQQ, IWM, TQQQ, SQQQ, SOXL, SOXS, UVXY, XLE, EWJ, EWY, EWZ and
KORU each publish `assetClass` STOCK. This is the third venue to do that —
bitget publishes `symbolType` stock on RSPYUSDT and RQQQUSDT, and OKX publishes
`instCategory` 3 on SPY and QQQ — and the sector offers the venue with no
recorded market, exactly as those two read.

## Step five — the arithmetic

| Sector | Venues offered, before | After | Markets kucoin can act on, before | After |
|---|---|---|---|---|
| crypto | 22 | 22 | 956 | 958 |
| stocks | 21 | 21 | 0 | 160 |
| commodities | 18 | 18 | 8 | 12 |
| forex | 9 | 10 | 14, 12 of them wrong | 2 |
| indices | 15 | 16 | 0 | 0 |
| futures and perpetuals | 16 | 16 | 681 | 527 |

Two offered counts move, because forex and indices gained the id. The offered
set minus the Add form's set is empty in all six sectors, and so is the
subtraction the other way.

## The eight venues before this one did not move

Driven in the same run, through the same production method, home redirected, no
credential. One venue of nine moved.

| venue | ccxt markets | listed | published codes | named | sector counts |
|---|---|---|---|---|---|
| coinbase | 1156 | 1148 | none | — | identical |
| kraken | 1460 | 1365 | none | — | identical |
| gateio | 6679 | 6677 | 5640 | 607 | identical |
| bitget | 4265 | 4258 | 3789 | 3151 | identical |
| okx | 4571 | 4563 | 687 | 311 | identical |
| okxus | 1152 | 1152 | 413 | 111 | identical |
| bitfinex | 288 | 288 | none | — | identical |
| gemini | 347 | 347 | none | — | identical |
| kucoin | 1659 | 1659 | 1047 | 169 | **moved** |

Every one of the eight read the same before and after on `listed`,
`published_codes`, `published_named` and every sector count. That is the
venue-generic control for the container change in `_published_asset_sectors` and
for the new branch in `market_asset_class`. OKX served 4571 markets here against
the 4569 the gemini unit recorded, which is the venue listing two more
instruments and not a reading that moved.

## Verification

Archetype runs, serial, one file at a time, every one `passed=True`.
Calibration read directly off each exit code, with no command substitution
between the run and the read.

The manual page is add-only: **5511 sentences before against `origin/current`,
5804 after, zero originals absent**, decoded as UTF-8. The census is two-sided —
the committed page against itself reports 0, one reworded sentence reports 1,
two report 2. The control had to be repaired first: appending text after a
sentence's full stop leaves that sentence intact under the splitter, so the
reworded control read 0 and the instrument, not the page, was wrong.

## What this could not establish

Whether the venue accepts a live order. No reading used a credential, so the
order bodies are what the library composes and not what kucoin acknowledged.

Whether the operator's own account is a Unified Trading Account. ccxt asks
kucoin that on a private endpoint before every order, and a UTA account routes
to `/api/ua/v1/unified/order/place`. Both routes were read and both send a
count, so the shape holds either way.

## The one answer that is the operator's

KuCoin will not give a United States resident an account, in its own words, in
every one of its sectors. That is the fourth venue in this run to say so. The
program warns on such a venue and still lets a bot start. This unit built no
mechanism either way — a venue-level refusal is a shape the operator has not
named. Whether the id stays offered at all is his call.
