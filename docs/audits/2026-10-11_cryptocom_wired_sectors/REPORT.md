# Crypto.com — the six sectors it serves, and the three a United States account trades

Read 2026-10-11 from crypto.com's own credential-free endpoints, its own
documented API host and its own help pages. No credential was used, no order was
placed, and no order was previewed. `ccxt` 4.5.85, synchronous path, which is the
path the product uses.

## The instrument, before any reading

Five hosts answer. Each one carries its own control, a path that cannot exist.

```
api.crypto.com/exchange/v1/public/get-instruments      200   550 KB   988 rows
exchange-developer.crypto.com/exchange/v1/docs/api/... 200   21-124 KB
  .../rest/this-page-cannot-exist-9f3a                 403   111 B    the control
static2.crypto.com/exchange/assets/documents/*.pdf     200   0.9-1.7 MB
  .../this-cannot-exist-9f3a.pdf                       403   111 B    the control
help.crypto.com/en/articles/<id>-<slug>                200   130-200 KB
  .../9999999-this-cannot-exist-9f3a                   404   1.3 KB   the control
crypto.com/en/product-news/<slug>                      200   142 KB
  .../this-cannot-exist-9f3a                           404   25 B     the control
```

`crypto.com/exchange/terms` answers 200 with a 5,373-byte application shell, and
a path invented under the same prefix answers the same shell. **No reading in
this document comes from that host.** The documented API host set is production
`https://api.crypto.com/exchange/v1/{method}` and sandbox
`https://uat-api.3ona.co/exchange/v1/{method}`. There is no second production
host and no United States host, so one market list serves every account.

### The United States refusal needed a second instrument

The 420-character prose window the previous venue units used reported **zero on
all three cryptocom geo-restriction pages, and that zero was the instrument.**
Crypto.com writes its refusal as a table: the header sits about 240 country rows
away from the row naming the United States, which is far outside any prose
window. A window instrument cannot read a table.

| instrument | page | text | reading |
| ---------- | ---- | ---- | ------- |
| prose, 420-char window | kucoin terms-of-use | 84,752 | **1 passage**, quoted below |
| prose, 420-char window | coinbase US user agreement | 363,729 | 4 passages, none an account refusal |
| prose, 420-char window | cryptocom spot / margin / derivatives | 2,736 / 3,037 / 3,687 | 0 each — the instrument, not the venue |
| list header plus row | cryptocom derivatives | 3,687 | header found; **names United States, US / USA**, Canada, Japan, Singapore, Switzerland, United Kingdom |
| list header plus row | cryptocom margin | 3,037 | header found; **names United States** |
| list header plus row | cryptocom spot | 2,736 | header found; names Venezuela and Zimbabwe, **and not the United States** |
| list header plus row | kucoin terms-of-use | 84,752 | 0 headers — prose, so the other instrument is the right one |

The spot page is the negative reading **and** carries its own positive control:
the same row reader finds two of its rows, so it would have found "United
States" had the venue listed it.

kucoin's clause, the positive side, quoted whole:

> "(5) the User (whether as an individual or legal entity) is not a resident of
> or registered in, any of the Restricted Locations. For the purpose of this
> Agreement, "Restricted Locations" shall include the United States (including
> its territories such as Puerto Rico, Guam, the Northern Mariana Islands,
> American Samoa, etc), Singapore, the mainland of China and Hong Kong,
> Malaysia, Kazakhstan, Uzbekistan, Ontario, and British Columbia of Canada,
> France, Netherlands, the Crimea, Donetsk, Luhansk, Zaporizhzhia and Kherson
> regions of Ukraine"

Gemini's user agreement could not serve as the negative control. Its page is a
JavaScript shell — 388 KB of markup yielding 2,263 characters of text — and its
United States path answers 404. A zero on a shell is no reading, so coinbase's
own United States user agreement, which serves 363,729 characters, is the
negative control instead.

## Sector truth comes from the venue, and here it costs nothing

### `/public/get-instruments` — 988 rows, 18 fields

```
inst_type      CCY_PAIR 569   PERPETUAL_SWAP 409   FUTURE 10
tradable       true 988
product_type   DIGITAL_CURRENCIES 812   EQUITY 131   EQUITY_IND 28
               COMMODITIES 8   PRE_IPO 3   CURRENCIES 1   no field 5
base_ccy       988 rows, 587 distinct codes
contract_size  419 rows, all "1"
expiry_timestamp_ms  10 rows non-zero, 978 rows zero
```

The venue's own reference page publishes the whole vocabulary:

> "product_type — Product type of the instrument. Possible values: COMMODITIES,
> EQUITY_IND, CURRENCIES, DIGITAL_CURRENCIES, EVENTS, EQUITY, PRE_IPO. Only
> returned if applicable."

Seven declared words, six on a live row. `EVENTS` names the venue's prediction
markets, which `ASSET_CLASSES` does not draw, so it maps onto
`NO_PUBLISHED_FAMILY`, exactly as OKX's "6: Bonds" does. The five rows with no
field are the "only if applicable" clause: four dated futures and `SHIB/BTC`.

### The venue's own words name the same families

> "New market tags, Stocks, Commodities, Equity Index ETFs and Pre-IPO are added
> under the perpetual market"

> "Pre-IPO Perpetuals on Crypto.com Exchange let you take a position on a private
> company's value before it goes public."

So `EQUITY_IND` records under indices, which is the reading bitstamp's `ETF`
took, and `PRE_IPO` records under stocks, because the underlying is a company.
Its own blog names the commodity and index suite:

> "Macro Metals: Trade Gold (XAU), Silver (XAG), Platinum (XPT), Palladium (XPD),
> and Copper (XCU)"

> "Energy Markets: Access Crude Oil (WTI) and Natural Gas"

> "U.S. Indices: Position on the Nasdaq-100 (QQQ) and S&P 500 (SPY) benchmarks"

### What a record gains, and what it costs

`VENUE_ASSET_SECTOR_RECORDS` gains a cryptocom row on
`v1PublicGetPublicGetInstruments`, keyed `base_ccy`, sector `product_type`, no
`code_leg`. It names a sector for **171 of the venue's 587 base codes**. Driven
over all 988 markets through
`src/exchange/ccxt_connector.py, in market_asset_class`, 178 move.

| gained — 164 markets | corrected — 5 markets |
| -------------------- | --------------------- |
| 129 `EQUITY` perpetuals to stocks | `AMD/USD:USD` forex to stocks — Advanced Micro Devices |
| 3 `PRE_IPO` perpetuals to stocks | `NOK/USD:USD` forex to stocks — Nokia |
| 28 `EQUITY_IND` perpetuals to indices | `USD1/USD`, `USDS/USD`, `USDT/USD` forex to crypto |
| 4 `COMMODITIES` perpetuals to commodities | |

| lost — 9 real markets | why |
| --------------------- | --- |
| `PAXG/USD`, `PAXG/EUR`, `PAXG/USDT`, `PAXG/USD:USD` | a record makes `published` non-None, which switches off `TOKEN_UNDERLYING_CODES` and `PRECIOUS_METAL_CODES`; PAXG redeems for gold |
| `XAUT/USD`, `XAUT/BTC`, `XAUT/USDT`, `XAUT/USD:USD` | the same, XAUT redeems for gold |
| `EURC/USD` | a euro token against the dollar, two currencies |

Three `CITED_VENUE_BASE_SECTORS` rows take all nine back:
`("cryptocom","PAXG")` and `("cryptocom","XAUT")` to commodities,
`("cryptocom","EURC")` to forex.

**Verdict: the record lands.** It gains 169 true answers and costs nothing. That
is the opposite of bitstamp, where a record named 7 of 123 base codes and cost
four real markets, and it is the first venue in this issue where the record is
free.

### The envelope the record had to reach through

`_asset_sector_rows` read `ASSET_SECTOR_ROWS_KEY` off a mapping and nothing
deeper, so a response wrapping its payload read as a venue publishing no record.
Crypto.com answers `{"id", "method", "code", "result"}` and puts the rows under
`result.data`, so the first drive answered None. `ASSET_SECTOR_PAYLOAD_KEY`
names the wrapper and the reader descends through it once.

```
before the key   _published_asset_sectors answered None
after the key    a sector for 171 of 587 base codes
control          gateio, bitget, okx, okxus and kucoin unchanged, each still
                 answering its own count
```

### The market grain — nothing, and the count that shows it

`CITED_VENUE_MARKET_SECTORS` gains **no cryptocom row**. Of 587 base codes,
**three** carry more than one `product_type`:

```
BTC    DIGITAL_CURRENCIES 8   no field 2
ETH    DIGITAL_CURRENCIES 10  no field 2
SHIB   DIGITAL_CURRENCIES 3   no field 1
```

Both words resolve to the same empty family, so no base code on this venue names
two sectors. PAXG, XAUT and EURC base 4, 4 and 1 markets, each of one
`product_type`, so each takes a base row and not a market row.

## The ticker collision, settled off `product_type`

cryptocom publishes **no** public currency list with a name or a type field. Its
eleven public endpoints are get-book, get-candlestick,
get-expired-settlement-price, get-instruments, get-insurance,
get-risk-parameters, get-tickers, get-trades, get-valuations,
staking-get-conversion-rate and a deposit list `ccxt` does not declare.
`get-risk-parameters` serves 638 base-currency rows carrying haircuts, order
limits and notional caps, and no name.
`v2/public/margin/get-transfer-currencies` answers
`{"code":"100001","msg":"SYS_ERROR"}`.

What the venue publishes instead is stronger than a leg label: a family per
market.

```
NOK    EQUITY       Nokia, not the Norwegian krone         1 market
AMD    EQUITY       Advanced Micro Devices, not the dram   1 market
MNT    absent from all 587 base codes                      0 markets
SGD    absent from all 587 base codes                      0 markets
```

`NOK` and `AMD` are both in `FIAT_CURRENCY_CODES`, so both read forex before
this unit. The venue's own word is what undoes each.

### `STABLECOIN_DENYLIST` gains nothing, and here is the count

```
cryptocom dollar-quoted spot markets              537
removed by STABLECOIN_DENYLIST already              7
  EUR/USDT, EURC/USD, FRAX/USD, PYUSD/USD, PYUSD/USDT, USDS/USD, USDT/USD
universe after                                    530
bases left that name a dollar: USD1, USDU           2
```

The removal of 7 is the positive control: the list fires on this venue. Neither
`USD1` nor `USDU` carries a cryptocom word that names it a currency, and
`product_type` files both under `DIGITAL_CURRENCIES`, so adding either would be a
belief and not a reading. `src/exchange/market_inspector_fetcher.py` is
unchanged.

## The cash market buy — not a member

Crypto.com publishes both units on one endpoint, like kucoin:

| field | the venue's own words |
| ----- | --------------------- |
| `quantity` | "Order quantity. For MARKET BUY can use notional instead." |
| `notional` | "Amount to spend; for MARKET BUY only (alternative to quantity)" |

`ccxt.cryptocom.create_order_request` writes
`'quantity': self.amount_to_precision(symbol, amount)` on every order and holds
no branch that sets `notional`. Its capability map leaves
`createMarketBuyOrderWithCost` False and `createMarketOrderWithCost` False.

Composed with no credential and nothing sent:

```
BTC/USD      market buy   {'instrument_name': 'BTC_USD', 'side': 'BUY',
                           'quantity': '0.001', 'broker_id': 'CCXT',
                           'spot_margin': 'SPOT', 'type': 'MARKET'}
BTC/USD      market sell  {... 'side': 'SELL', 'quantity': '0.001' ...}
BTC/USD      limit buy    {... 'quantity': '0.001', 'price': '50000',
                           'type': 'LIMIT'}
AAPL/USD:USD market buy   {'instrument_name': 'AAPLUSD-PERP', 'side': 'BUY',
                           'quantity': '1', 'broker_id': 'CCXT',
                           'type': 'MARKET'}
XAU/USD:USD  market buy   {'instrument_name': 'XAUUSD-PERP', ... 'quantity': '1'}
EUR/USDT     market buy   {'instrument_name': 'EUR_USDT', ... 'quantity': '10',
                           'spot_margin': 'SPOT'}
```

**cryptocom is not a member of `CITED_CASH_MARKET_BUY`.** A contract carries no
`spot_margin` field, and that is the whole difference between the two shapes.

### `code_leg`

cryptocom publishes `base_ccy` on all 988 rows, a bare code. Its `symbol`
concatenates the legs — `1INCH_USD`, `1INCHUSD-PERP`, `BTCUSD-261127` — so a
split on `-` reads `1INCHUSD` and a split on `_` reads nothing on a perpetual.
**No `code_leg` is named.**

## The eight connections

| # | connection | reading | control |
| - | ---------- | ------- | ------- |
| 1 | registered | `cryptocom` in `SUPPORTED_EXCHANGES`: True | an invented id: False |
| 2 | offered under every sector it serves | all six: crypto, stocks, commodities, forex, indices, futures_perps | an invented id is offered under none |
| 3 | credential form | `exchange_status_rows` draws its venues from `venues_for_class`, and holds cryptocom in all six wings — of 22, 21, 19, 11, 18 and 17 rows | a sector with no venue draws `class_state`'s note |
| 4 | a Start press builds its connector | `MainWindow._connect_exchange_for_bot` reads `broker_serves_sector` first and `crypto_connector_class` second; both answer nothing for cryptocom in all six sectors, so it takes the ccxt path and reads the stored credential. `cryptocom` is outside `PASSPHRASE_EXCHANGES`, so a key and a secret are the whole form | `alpaca` answers broker in all six sectors and `robinhood` answers a written crypto class on crypto and broker on four others, so the picker discriminates |
| 5 | market rules record on connect | `record_venue` wrote 988 rows and `recorded_classes` read back crypto 561, futures_perps 247, stocks 134, indices 28, commodities 16, forex 2 | an empty market list writes nothing |
| 6 | the order shape | `declared_order_types` reads "market and limit" off the venue's own capability map, where `createMarketOrder` is True | gemini reads "limit only" off the same reader |
| 7 | a built variant selects | `variant_holds_market` True for 988 of 988; `venue_variant` "no order-formatting difference" for 978 and "the venue expires this market on a date" for 10 | — |
| 8 | gate decisions log under it | `gate_log_path` composes `trade/gate/cryptocom/<sector>/gate.log` for each of the six | an unoffered sector composes a path as well, so the path is not the gate |

`order_types_for(None, sector, "cryptocom")` answered **None for all six
sectors** before this unit — the same gap gemini, kucoin and bitstamp each found.
It now answers "market and limit" in all six.

## Verdicts

| sector | verdict | cost or ground |
| ------ | ------- | -------------- |
| crypto | **yes** | 561 markets, every one spot. 250 fractional steps and 311 whole |
| forex | **yes** | 2 markets, both spot: `EUR/USDT`, the venue's own `CURRENCIES` row, and `EURC/USD` |
| commodities | **yes** | 16 markets. The 6 gold-token spot pairs are what a United States account reaches; the 8 `COMMODITIES` perpetuals and the 2 gold-token perpetuals are not |
| stocks | **yes, and not for a US account** | 134 perpetual contracts, 131 `EQUITY` and 3 `PRE_IPO`. Offered, read, charted and sized. "The following locations are restricted from trading derivatives: ... United States US / USA" |
| indices | **yes, and not for a US account** | 28 perpetual contracts, the venue's own `EQUITY_IND`. Same refusal |
| futures_perps | **yes, and not for a US account** | 247 contracts, 237 perpetuals and 10 dated futures. Same refusal |

**No sector is a no.** cryptocom is the first venue in this issue to serve all
six, and the second after coinbase to be offered under all six.

### United States eligibility — neither set

Spot, in the venue's own words:

> "Please note that users from the following regions are restricted from
> participating in Spot Trading: Afghanistan ... Venezuela, Yemen, Zimbabwe"

The United States is not a row on that list, and 38 other locations are. Its own
U.S. Exchange terms name the entity and the one state they leave out:

> "The Crypto.com Exchange Services (described below) are provided to you by
> Foris DAX, Inc., a Delaware corporation and registered money services
> business"

> "'Available Jurisdiction' means all eligible U.S. jurisdictions where the
> Exchange is available for your use, except New York."

Derivatives and margin, in the venue's own words:

> "The following locations are restricted from trading derivatives: ... United
> Kingdom GB / GBR, United States US / USA, US Virgin Islands VI / VIR ..."

> "The following locations are restricted from participating in Margin Trading:
> ... United States US / USA ..."

The derivatives list also names Guam, Puerto Rico, American Samoa and the
Northern Mariana Islands, so the refusal reaches the territories.

**cryptocom sits in neither `US_IP_BLOCKED_EXCHANGES` nor
`US_ACCOUNT_RESTRICTED_EXCHANGES`,** the shape bitstamp and gemini hold, because
the refusal falls on a product and not on the account. Every public cryptocom
endpoint answered 200 from a United States address. Unlike bitstamp, a state is
established rather than unestablished: the venue's own terms exclude New York.

Detours searched before that reading, and what shut each: the global Exchange
terms, published by Foris DAX Limited, which name the United States only as a
sanctions authority and refuse no United States person; `crypto.com/exchange/...`
and `crypto.com/document/exchange-terms`, an application shell and a 403; a
derivatives host, no DNS record; the API documentation, which names no geography
and no United States host; `get-instruments`, which takes no entity parameter and
serves one list.

## The arithmetic, per sector

```
sector          offered before  venue lists  actionable before  gained
crypto                     yes          561                561       0
stocks                     yes          134                  0    +134
indices                     no           28                  0     +28
commodities                 no           16                  0     +16
forex                       no            2                  0      +2
futures_perps              yes          247                247       0
```

Three sectors were offered under nothing while the venue listed 46 markets
between them. stocks was offered and recorded nothing, because no reader of
`product_type` existed, so its 134 markets read futures_perps and a stocks bot
found an empty list. The offered set now equals the actionable set in all six.

For a United States account the actionable set is the spot column:

```
crypto 561   commodities 6   forex 2   stocks 0   indices 0   futures_perps 0
```

## The recording, before and after

```
                 before   after
crypto              558     561
stocks                0     134
futures_perps       411     247
indices               0      28
commodities          12      16
forex                 7       2
                    ---     ---
                    988     988
```

futures_perps gives up 131 equity perpetuals, 28 index perpetuals, 3 pre-IPO
perpetuals and 4 commodity perpetuals, and takes back the two gold-token
perpetuals the base rows no longer send to commodities' spot reading. forex gives
up the two equity perpetuals the fiat code set mislabelled and the three dollar
tokens quoted against the dollar.

## The regression drive

The sector and market-filter paths are shared, and the envelope key is read by
every venue holding a record, so ten venues were driven before and after:
coinbase, kraken, gateio, bitget, okx, okxus, bitfinex, gemini, kucoin and
bitstamp.

```
coinbase 1156 {crypto 904, forex 20, commodities 25, futures_perps 168, stocks 33, indices 6}
kraken   1460 {crypto 1416, forex 38, commodities 6}
gateio   6679 {crypto 2033, stocks 565, commodities 20, forex 6, futures_perps 619, indices 18, options 3418}
bitget   4265 {stocks 3141, crypto 578, commodities 12, futures_perps 534}
okx      4571 {crypto 1021, commodities 21, stocks 400, futures_perps 483, options 2646}
okxus    1152 {crypto 1013, commodities 4, stocks 135}
bitfinex  288 {crypto 189, forex 4, commodities 9, futures_perps 76, indices 10}
gemini    345 {crypto 324, forex 2, commodities 6, futures_perps 13}
kucoin   1659 {crypto 958, commodities 12, forex 2, stocks 160, futures_perps 527}
bitstamp  271 {forex 11, crypto 240, commodities 6, futures_perps 12, indices 2}
```

**Not one count moved.** The comparison is structural, over the parsed census and
not over the file bytes, and a tampered copy is the control: one market removed
from gemini's crypto count is reported as a difference on gemini and nowhere
else.

```
before vs after moved:      nothing
before vs tampered moved:   ['gemini']   gemini crypto 324 -> 323
```

### Four of those ten counts no longer match the bitstamp report, and the venues are why

The bitstamp report published `bitget {crypto 3375, forex 16, commodities 8,
futures_perps 866}` and `okxus {crypto 1125, forex 23, commodities 4}`. Today the
same instrument reads bitget with 3,141 stocks and okxus with 135. The venues'
own fields are what changed, read raw:

```
bitget publicUtaGetV3MarketInstruments category=SPOT
  3389 rows   symbolType {stock 2809, crypto 578, metal 2}
  the 2809 stock rows carry 2809 distinct baseCoin values
bitget category=USDT-FUTURES
  820 rows    symbolType {crypto 478, stock 332, metal 7, commodity 3}
  TSLAUSDT, NVDAUSDT and AAPLUSDT among the stock rows
okx publicGetPublicInstruments instType=SPOT
  1160 rows   instCategory {1: 1013, 3: 135, 4: 4, "": 8}
  the 135 are XAAPL-USDT, XAMD-USDT, XAMZN-USDT and the rest of that prefix
```

Both venues listed tokenised equities after the bitstamp reading was taken. The
pattern in the four moved counts — forex falling to zero while stocks appears —
is what a venue publishing a category for the first time looks like, because
`market_asset_class` reads `PRECIOUS_METAL_CODES` and `FIAT_CURRENCY_CODES` only
while `published` is None. Nothing in this unit touched any of those four
readings, and the before and after drives taken minutes apart agree exactly.

## The manual edit is add-only

Measured by sentence census against `git show origin/current:` the same path,
decoded as UTF-8:

```
ADD-ONLY CHECK     base 2362 sentences, new 2441, missing 0
TAMPER CONTROL     base 2362 sentences, new 2441, missing 1   <- fires
APPEND CONTROL     base 2362 sentences, new 2442, missing 0
```

The tamper control rewords one word **inside** an existing sentence, so it can
fail. The append control shows that adding text after a full stop alone would not
have exercised the check, which is why it is not the control.

Two rows the page carried are quoted whole under `OVERTAKEN` with a `True today`
line beneath each: the venue-classes row reading "crypto, stocks,
futures_perps", and the credential row reading "crypto spot" and "no refusal
recorded".

## Timeframes

`src/exchange/timeframes.py` needed no change to its row. Read from `ccxt` 4.5.85
`exchange.timeframes` after a public `load_markets()`, cryptocom publishes twelve
granularities and `ALL_TIMEFRAMES` draws ten of them, which is exactly the row.
The two it leaves are `2w` and `1M`, and `2h` is the one `ALL_TIMEFRAMES` holds
that cryptocom does not publish, so `_AVAILABILITY["cryptocom"]` equals the
intersection exactly. Only the row's comment changed, because the row carried no
reading at all.

## What the reading cannot show

No reading used a credential, so nothing here proves cryptocom accepts a live
order from this program. The order bodies are what the library composes, not what
the venue acknowledged. The United States refusal on every derivative was read
from cryptocom's own help pages and not tested, which would require an account
the operator does not hold. The five rows carrying no `product_type` are read as
the venue publishing no family for them, which is what its own "Only returned if
applicable" clause states, and not as the venue naming crypto.
