# Bitget Wired Across The Sectors It Serves

**Mode: Reference, with three product files changed.**

This page covers issue #1192. It answers the eight connections of that issue's
wired-venue section for Bitget, establishes how Bitget requires an order to be
formatted in each sector it serves, names the bot variant each format demands,
and records what changed so each sector reaches an order.

**FALSIFICATION.** This page is wrong if a field named here is absent from
Bitget's own published specification, if a sector's order body accepts a field
this page calls refused, if the program's order call passes a field this page
says it omits, if a Bitget order the program now refuses turns out to be one the
venue would have accepted, or if the asset sector this page reads off the venue's
own `symbolType` field turns out to name something other than the sector.

---

## The verdict, one row per sector

| Sector | Verdict | The cost, where there is one |
| --- | --- | --- |
| crypto | yes-if | the venue's own terms refuse a U.S. person |
| stocks | yes-if | the same account refusal, and nothing else |
| commodities | yes-if | the same account refusal, and nothing else |
| futures and perpetuals | yes-if | the same account refusal; two markets of 876 refuse on the cash-amount shape |
| indices | yes-if | the same account refusal; the venue files its index funds under stocks, so the sector lists no market of its own |
| forex | **no** | the venue publishes no currency family and lists no pair with two national-currency legs |

**One cost sits on five of the six rows and it is not a sector fact.** Bitget's
own Terms of Use refuse a U.S. person, so the operator cannot open the account
any of these sectors needs. The order path reaches every sector the venue
serves; the account does not exist. That is the issue's own definition of a
yes-if, a door that exists and cannot be walked through.

**The forex row is the one "no", and the door does not exist.** The section
*Forex — the absence, proven three ways* below carries the venue's own record,
the detours searched, and the control.

---

## The eight connections

Every reading was taken in a process whose home directory was redirected to a
scratch tree before any module under the source tree was imported, with the
redirected home printed and the tree's contents listed afterwards. No credential
was sent, no account was created, and no order was placed, priced, amended,
previewed or cancelled.

| # | The connection | Bitget | The symbol that answers it |
| --- | --- | --- | --- |
| 1 | a connector exists and is registered | answered, the library's own class | `src/exchange/ccxt_connector.py, in SUPPORTED_EXCHANGES` |
| 2 | offered under every sector it serves | answered, four served and five offered | `src/gui/main_tabs/asset_class_surface.py, in EXTRA_VENUE_CLASSES` |
| 3 | the operator can enter its credentials | answered, on the Exchanges tab and in the first-run wizard | `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` |
| 4 | a Start press builds its connector | answered, the crypto path | `src/stocks/alpaca_connector.py, in broker_connector_class` |
| 5 | its market rules record on connect | **3156 of 4258 markets recorded the wrong sector, now answered** | `src/exchange/ccxt_connector.py, in _published_asset_sectors` |
| 6 | its orders carry the shape the venue publishes | **the spot market buy is a cash amount and the program did not know, now answered** | `src/trading/scrumming/sizing.py, in CITED_CASH_MARKET_BUY` |
| 7 | a built variant selects for it | answered, six sector variants and the whole-unit one | `src/trading/scrumming/sizing.py, in VARIANTS_BUILT` |
| 8 | its gate decisions log under it | answered, six distinct paths | `src/core/log_paths.py, in gate_log_path` |

---

## Row one, the connector

The library carries the class under the id the platform uses, so no alias and no
hand-written connector is needed.

```
ccxt version                            4.5.85
'bitget' in ccxt.exchanges              True
'bitget' in SUPPORTED_EXCHANGES         True, of 15 ids
'bitget' in CCXT_CLASS_ALIASES          False
resolve_ccxt_class(ccxt, 'bitget')      <class 'ccxt.bitget.bitget'>
'bitget' in CRYPTO_CONNECTORS           False, so no connector was written
'bitget' in PASSPHRASE_EXCHANGES        True, so the form asks for a key, a
                                        secret and a passphrase
PREFLIGHT_URLS['bitget']                api.bitget.com/api/v2/public/time
```

The library's own capability map carries the product lines the sectors need, and
it declares no option line.

```
has[spot]   True    has[margin] True   has[swap] True
has[future] True    has[option] False
api sections            private, public
endpoint entries        791
```

The absent option line matters. Gate.io's 3418 option contracts had to be given
a sector of their own; Bitget publishes none, and `is_option_market` answers
true for 0 of its 4258 active markets.

---

## Row one, continued: the account the venue will not open

`US_ACCOUNT_RESTRICTED_EXCHANGES` named three venues and not this one, so the
connect path warned nothing while the venue's own published words refuse the
operator. The set now holds it.

> **Prohibited Countries** means the following countries and such other
> locations as designated by Bitget from time to time, including Austria,
> Canada, Crimea, Cuba, Donetsk, France, Germany, Hong Kong, Iran, Japan,
> Kazakhstan, Luhansk, Malaysia, North Korea, Singapore, Sudan, the United
> States (including the following U.S. Territories: Puerto Rico, Guam, U.S.
> Virgin Islands, American Samoa and the Northern Mariana Islands and the
> following U.S. Minor Outlying Islands Baker Island, Howland Island, Jarvis
> Island, Johnston Atoll, Kingman Reef, Midway Islands, Navassa Island, Palmyra
> Atoll and Wake Island), Iraq, Libya, Yemen, Afghanistan, the Central African
> Republic, the Democratic Republic of the Congo, Guinea-Bissau, Haiti,
> Lebanon, Somalia, South Sudan and Thailand.

That is section 1, Definition. The eligibility clauses then require the account
holder to be outside it.

> **2.6** are not accessing the Services in a jurisdiction where such Services
> are not permitted, restricted or illegal

> **2.8** are not a Restricted Person

Section 1 defines a Restricted Person as one who, among other things, "resides
or is established, or has operations in any of the Prohibited Countries", and
section 11.1(xvii) forbids the use outright.

> access, use, or attempt to access or use, Services directly or indirectly
> with (1) jurisdictions Bitget has deemed high risk, including but not limited
> to, the Prohibited Countries or (2) persons Bitget has deemed high risk,
> including but not limited to, individuals or entities named as a restricted
> person or party on any list maintained by the United States, United Kingdom,
> European Union or United Nations

All four clauses are on
[the Terms of Use](https://www.bitget.com/support/articles/360014944032-terms-of-use),
read 2026-10-10.

```
before   'bitget' in US_ACCOUNT_RESTRICTED_EXCHANGES    False
         'bitget' in US_RESTRICTED_EXCHANGES            False
after    'bitget' in US_ACCOUNT_RESTRICTED_EXCHANGES    True
         'bitget' in US_RESTRICTED_EXCHANGES            True
         the words the connect path records             US account restricted
control  'coinbase' in US_RESTRICTED_EXCHANGES          False, before and after
control  'kraken'   in US_RESTRICTED_EXCHANGES          False, before and after
control  'gateio'   in US_RESTRICTED_EXCHANGES          True, before and after
```

**The address is not the refusal.** The venue's public endpoints answer a US
address, so this is an account matter and not an IP block, which is why the
entry sits in the account set and not the IP one.

```
GET https://api.bitget.com/api/v2/public/time                 200
GET https://api.bitget.com/api/v3/market/instruments?...       200, 3389 rows
control  GET https://api.bitget.com/api/v2/public/not-a-real-route   404
```

**The warning reaches the log and not the venue picker.** That is the same
finding the Gate.io page records, and it has not changed: `exchange_label`
composes the note and `list_supported_exchanges` is its only reader, which no
screen calls. Putting the refusal beside the venue's own button is its own row,
and this page does not reshape a screen.

---

## Row two, the sectors

The surface offers the venue under five, and the venue's own record names four.

```
EXTRA_VENUE_CLASSES['bitget']   stocks, commodities, indices, futures_perps
crypto arrives from             crypto_venues, off SUPPORTED_EXCHANGES
venue_classes('bitget')         commodities, crypto, futures_perps, indices,
                                stocks
sectors offering bitget         5 of 6
venue_served_classes('bitget')  commodities, crypto, futures_perps, stocks
                                after the recording drive
control  an invented venue id   no class at all
```

Nothing was added to the surface. Four served sectors were already offered, and
the fifth, indices, is offered with no market of its own, which the section
below establishes from the venue's pages rather than removing the row.

---

## Row three, the credential form

One source answers the whole arithmetic. The Exchanges tab reads the sector's
own venue list and the Add form reads that same list, so the set the screen
offers and the set it can act on cannot differ.

```
crypto         21 venues | bitget among them  yes
stocks         20 venues | bitget among them  yes
commodities    17 venues | bitget among them  yes
indices        14 venues | bitget among them  yes
futures_perps  16 venues | bitget among them  yes
forex           8 venues | bitget among them  no, and the venue serves none
wizard         25 venues | bitget among them  yes
control  an invented venue id in any of them  no
```

The row the tab draws for it:

```
('Bitget (bitget)', 'bitget', 'unset', ...)
```

`PASSPHRASE_EXCHANGES` holds the venue, so the form asks for the third field the
venue's own key page requires.

---

## Row four, the Start press

`broker_connector_class('bitget')` answers None and `BROKER_CONNECTORS` holds
`alpaca` and `robinhood` alone, so `MainWindow._connect_exchange_for_bot` takes
the crypto path and builds a `CCXTConnector`. Nothing on this row moved.

---

## Row five, the recording, and the three sectors it got wrong

### The venue publishes the sector itself, on a public credential-free record

`GET /api/v3/market/instruments` carries a `symbolType` per market. The library
already exposes it as `publicUtaGetV3MarketInstruments`, and it refuses a call
that names no product type, so the record is read five times.

```
with no category parameter   400172 "Parameter verification failed"
category=SPOT                3389 rows   stock 2809, crypto  578, metal 2
category=USDT-FUTURES         820 rows   crypto 478, stock  332, metal 7,
                                         commodity 3
category=COIN-FUTURES          24 rows   crypto  24
category=USDC-FUTURES          49 rows   crypto  49
category=MARGIN               321 rows   crypto 321
                             ----
                             4603 rows
```

The whole published vocabulary is four words.

```
stock      3141   asset_class_named -> ''
crypto     1450   asset_class_named -> 'crypto'
metal         9   asset_class_named -> ''
commodity     3   asset_class_named -> ''
```

Gate.io published the platform's own words, so no map was needed. Bitget
publishes the singular form, so three of its four words resolve to nothing and
the fourth resolves to a class that is wrong for a contract. The record
therefore carries the venue's own vocabulary beside its method.

`src/exchange/ccxt_connector.py, at VENUE_ASSET_SECTOR_RECORDS` holds one
`AssetSectorRecord` per venue: the method, the requests it takes, the field
naming the asset code, the field naming the sector, and the venue's own words.
`src/exchange/ccxt_connector.py, in _published_asset_sectors` reads it,
`in _asset_sector_rows` takes each response's rows, and
`in _read_asset_sector_rows` writes one sector per asset code.

```
gateio   method=publicSpotGetCurrencies          requests=0 code=currency
                                                 sector=category  words={}
bitget   method=publicUtaGetV3MarketInstruments  requests=5 code=baseCoin
                                                 sector=symbolType
         words={'stock': 'stocks', 'metal': 'metals',
                'commodity': 'commodities', 'crypto': ''}
```

Gate.io's row takes every default, so its reading did not move. That is the
two-sided control on the rename and it is measured below.

### Why the venue's own `crypto` word maps onto nothing

`src/exchange/ccxt_connector.py, at NO_PUBLISHED_FAMILY` is the empty string,
and Bitget's `crypto` maps onto it. Gate.io says the same thing by leaving an
asset's category list empty; Bitget says it with a word. Either way the venue is
stating the asset belongs to no family outside crypto, and
`src/exchange/ccxt_connector.py, in is_contract_market` still decides whether
the market is a spot pair or a perpetual.

**The first drive of the change caught this.** Mapping the word onto the crypto
class instead, which is what `asset_class_named` answers for it, moved 526
perpetual contracts out of the futures sector.

```
crypto mapped onto 'crypto'   futures_perps  866 -> 7, crypto 3368 -> 1098,
                              3682 markets moved
crypto mapped onto ''         futures_perps  866 -> 534, crypto 3368 -> 571,
                              3156 markets moved
```

### Why the tickers had to stop being read

Sixteen markets read as forex and every one was a ticker collision.

```
AMD/USDT:USDT   Advanced Micro Devices, read as the Armenian dram
COP/USDT:USDT   ConocoPhillips, read as the Colombian peso
NIO/USDT:USDT   NIO Inc., read as the Nicaraguan cordoba
RON/USDT        the venue publishes stock, read as the Romanian leu
RWF/USDT        the venue publishes stock, read as the Rwandan franc
USDT/EUR USDT/BRL USDT/VND USDT/USD USDC/EUR USDC/USD USDC/USDT
USD1/USDT USD1/USDC USDS/USDT USDC/USDT:USDT
                a dollar stablecoin, published crypto on both legs
```

`src/exchange/ccxt_connector.py, in market_asset_class` reads the base and quote
codes only where the venue publishes no record, so a venue publishing one stops
all sixteen guesses at once.

### One code at a time, off the driven record

```
RCVCO -> stocks        RSPY -> stocks         RQQQ -> stocks
PAXG  -> commodities   XAUT -> commodities    XAU  -> commodities
CL    -> commodities   NATGAS -> commodities
BTC   -> ''            USDT -> ''
AMD   -> stocks        COP  -> stocks         NIO  -> stocks
RON   -> stocks        RWF  -> stocks
control  NOTACODE -> absent
control  kraken's own _published_asset_sectors() -> None
```

### Two codes are published under two sectors, and the first request wins

`PAXG` and `XAUT` are published as `metal` under SPOT and USDT-FUTURES and as
`crypto` under MARGIN. `_read_asset_sector_rows` leaves a code a previous row
already named untouched, and `record.requests` puts SPOT first, so both answer
commodities. Of 3789 distinct base codes, those two are the only pair under two
sectors.

### The recording after the change

```
rows written                       4258
rows carrying a sector             4258
markets whose sector moved         3156
```

| Sector | Markets before | Markets after |
| --- | --- | --- |
| crypto | 3368 | 571 |
| stocks | 0 | 3141 |
| commodities | 8 | 12 |
| forex | 16 | 0 |
| indices | 0 | 0 |
| futures_perps | 866 | 534 |

Every one of the 3156 moves, named by where it came from and where it went.

| From | To | Markets |
| --- | --- | --- |
| crypto | stocks | 2807 |
| futures_perps | stocks | 329 |
| forex | crypto | 10 |
| forex | stocks | 5 |
| futures_perps | commodities | 4 |
| forex | futures_perps | 1 |

The 2807 are tokenised equity spot pairs and the 329 are equity perpetuals, so
the stocks sector gains its markets from two product lines at once. The four
that reach commodities are `CL/USDT:USDT`, `BZ/USDT:USDT`,
`NATGAS/USDT:USDT` and `COPPER/USDT:USDT`, which are crude oil, Brent, natural
gas and copper, and no list of precious metals can carry them.

The before column reads the classifier with no published sector supplied, which
is what every venue outside `VENUE_ASSET_SECTOR_RECORDS` still gets.

**Control: the same arithmetic reports almost no movement when the venue's
record is blinded.** With every published sector replaced by an empty string, 24
markets move and not 3156. Those 24 are exactly the 16 forex and 8 commodities
rows the ticker heuristic had guessed, which stop being guessed as soon as the
venue answers anything. So the 3156 is a reading of Bitget's record and not of
the instrument.

**Control: Gate.io's own reading is unchanged by the rename.** Driven after the
change, with the home redirected and no credential sent.

```
gateio codes                5640
gateio codes with a sector   607
  stocks 567 | commodities 18 | indices 18 | forex 4
AAPLX -> stocks      SPX500 -> indices
XAUT  -> commodities EURUSD -> forex
CAD   -> ''          BTC    -> ''
NOTACODE -> absent
```

Every figure matches the Gate.io page's own.

### The seven markets the record does not hold

4251 of the 4258 loaded markets have a base code the record holds. The seven it
does not are the venue's own demo-trading symbols, `SBTC`, `SETH` and `SXRP`,
and `category=SUSDT-FUTURES` answers HTTP 400, so they sit in no live product
type. Each answers an empty published sector, which leaves `is_contract_market`
to give it the sector it already had.

### `get_markets` driven end to end

With the home redirected and the recording written into the scratch tree:

```
markets answered                   4258
rows the recording holds           4258
rows carrying a sector             4258
  crypto 571 | futures_perps 534 | stocks 3141 | commodities 12
the file written      .acervator/market_rules.json, 1,632,503 bytes
```

Read back through the surface the bots and the tabs use:

```
symbol_class  RCVCO/USDT      -> stocks
symbol_class  BTC/USDT        -> crypto
symbol_class  BTC/USDT:USDT   -> futures_perps
symbol_class  PAXG/USDT       -> commodities
control  symbol_class on a symbol with no recorded row -> crypto
```

### The operator's own recording cannot move

The live recording was read read-only through the `path` argument
`src/exchange/market_rules_store.py, in load_document` takes, and its
modification time and size were read before and after.

```
top-level venue keys                1, coinbase
rows under that key              2148
rows carrying a sector           2148   stocks 1033, crypto 896,
                                        futures_perps 168, commodities 25,
                                        forex 20, indices 6
'bitget' among its venue keys    False
modification time, before == after  True
size, before == after               True
```

**Nothing in this branch can move a row of it.**
`VENUE_ASSET_SECTOR_RECORDS` names Gate.io and Bitget, and the recorded venue is
neither, so `market_asset_class` reads `published` as None for every recorded
row and answers exactly what it answered before.

---

## Row six, the order shape

Bitget's own
[Place Order page](https://www.bitget.com/api-doc/uta/trade/Place-Order),
read 2026-10-10, publishes `POST /api/v3/trade/place-order` and states the size
unit per order type.

> **Spot/Margin market buy orders**: the unit is quote coin
> **Limit and market sell orders**: the unit is base coin
> **USDT/USDC-Futures**: The unit is base coin
> **COIN-Futures**: The unit is quote coin

The same page publishes `category` as "Product type `SPOT` Spot trading
`MARGIN` Margin trading `USDT-FUTURES` USDT futures", `side` as
"Order side `buy`/`sell`", `orderType` as "Order type `limit`/`market`" and
`clientOid` as "Client order ID".

The library's own request builder agrees, in `ccxt/bitget.py, in
create_order_request`. On a spot market buy it sets
`createMarketBuyOrderRequiresPrice = True` and writes
`request['size'] = cost_to_precision(amount * price)`; on every other spot order
it writes `amount_to_precision(amount)`; on a contract it writes
`amount_to_precision(amount)`. The client order id reaches the body as
`clientOid`, which is the field the venue's page names.

### The cash market buy, which three sectors take

```
before   market_buy_names_cash('BTC/USDT', 'bitget')          False
         markets whose cash buy takes a limit order              0
after    market_buy_names_cash('BTC/USDT', 'bitget')           True
         market_buy_names_cash('BTC/USDT:USDT', 'bitget')     False
         markets a market buy sizes in cash                   3382,
                                                              every one spot
         markets stepping in whole units                       407
         markets whose cash buy takes a limit order             36
           of those, crypto 29 and stocks 7
control  market_buy_names_cash('BTC/USDT', 'kraken')          False
control  the limit-order count on kraken                          0
control  a contract symbol among the 3382                         0
```

`src/trading/scrumming/sizing.py, in whole_unit_buy_needs_limit` answers True
for those 36, so each takes a limit order in place of a market buy. A market buy
sized in cash cannot name a whole unit count, which is the rule that already
covers Coinbase, Binance and Gate.io.

`src/exchange/ccxt_connector.py, in place_order` already fetches a ticker for a
market buy carrying no price, on any venue, so the price the cash amount is
computed from is already in hand.

### The two markets that refuse, and they refuse before the connector

Two of the venue's markets take the COIN-Futures shape, and both are its own
demo symbols.

```
SBTC/SUSD:SBTC   quote_contract_size_shapes  (cash amount, cash amount)
                 permits_size_shapes         True
                 permitted_order_shape buy   cash amount
                 shape_unit_rule of it       None
                 size_shape_refusal          the venue permits a cash amount
                                             alone on a buy of this product
SETH/SUSD:SETH   the same five readings
control  BTC/USDT:USDT  permits_size_shapes False, refusal ''
VARIANT_CASH_AMOUNT in VARIANTS_BUILT        False
```

That is row 6 of the issue's build order, unbuilt, and it refuses the market
rather than sizing it wrongly.

---

## Row seven, the variant

Every sector the venue serves has a built variant.

```
crypto         -> Crypto Scrumming       built=True
stocks         -> Stock Scrumming        built=True
commodities    -> Commodity Scrumming    built=True
forex          -> Forex Scrumming        built=True
indices        -> Index Scrumming        built=True
futures_perps  -> Futures Scrumming      built=True
SECTOR_VARIANTS rows   6
VARIANTS_BUILT rows    8
control  sector_variant('options') -> options Scrumming, built=False
```

No variant was added. The whole-unit variant covers the 407 markets whose
published step is a whole unit, and the cash-amount variant is the one the two
demo contracts need and the program does not hold.

---

## Row eight, the gate log

`src/core/log_paths.py, in gate_log_path` composes a distinct path per sector,
six of six.

```
trade/gate/bitget/crypto/gate.log         trade/gate/bitget/indices/gate.log
trade/gate/bitget/stocks/gate.log         trade/gate/bitget/forex/gate.log
trade/gate/bitget/commodities/gate.log    trade/gate/bitget/futures_perps/gate.log
distinct paths  6
```

---

## The six points, per sector

| Sector | market list | order route | order shape | position and fill read | candles | bot variant |
| --- | --- | --- | --- | --- | --- | --- |
| crypto | 571 recorded rows | `POST /api/v3/trade/place-order`, `category: SPOT` | `size` in quote coin on a market buy, base coin otherwise | `fetchBalance`, `fetchOrder`, `fetchMyTrades` all True | `fetchOHLCV` True, eleven granularities | Crypto Scrumming, built |
| stocks | 3141 recorded rows | the same spot route, plus the contract route for 329 | the same, and 0.0001 of a share is the published minimum | the same three reads | the same | Stock Scrumming, built |
| commodities | 12 recorded rows | the spot route for 2, the contract route for 10 | the same | the same three reads, plus `fetchPositions` True | the same | Commodity Scrumming, built |
| futures and perpetuals | 534 recorded rows | `POST /api/v3/trade/place-order` with a futures category | `size` in base coin on USDT and USDC futures | the same four reads | the same | Futures Scrumming, built |
| indices | **0 recorded rows** | the spot route, reached under stocks | the spot shape | the same three reads | the same | Index Scrumming, built |
| forex | **0 recorded rows** | **none published** | **none published** | **none published** | the same | Forex Scrumming, built |

Indices is answered on five points of six. The market list is the one point with
no equivalent, and the product itself is reachable under stocks.

Forex is answered on one point of six, and the block is at the market list.

---

## The indices sector lists no Bitget market, and the exposure is still reachable

`symbolType` reads `index` on none of the 4603 rows.

```
symbolType == index     0        symbolType == indices   0
symbolType == etf       0        symbolType == bond      0
control  symbolType == stock  3141
```

Eight index-fund tokens are listed and the venue publishes each one as a stock.

```
RSPYUSDT SPY    RQQQUSDT QQQ    RDIAUSDT DIA    RIWMUSDT IWM
RVOOUSDT VOO    RIVVUSDT IVV    RVTIUSDT VTI    REEMUSDT EEM
all eight, published symbolType   stock
```

A name search over the venue's own 2807 equity rows finds 6 names carrying
"index", 157 carrying "ETF", 53 carrying "trust", 100 carrying "shares" and 12
carrying "fund", among them `VDE` "Vanguard Energy Index Fund ETF" and `FNDX`
"Schwab Strategic Tr Fundamental U S Large Co Index Etf". Control: the same
search finds 556 names carrying "inc" and 0 carrying a word that is not there.

So the door exists and the venue files it under stocks. The indices row stays on
the screen and its empty market list is recorded here, because removing a sector
from a venue is the operator's decision and not a measurement.

---

## Forex — the absence, proven three ways

### The venue's own published refusal

The venue publishes no currency family anywhere in its instrument record.

```
rows read                4603, across all five product types
symbolType == forex         0        symbolType == currency  0
symbolType == fx            0        symbolType == fiat      0
control  symbolType == stock  3141
```

And no spot pair it lists has two national-currency legs.

```
spot pairs with two national-currency legs         0
base codes that are an ISO currency code           RON, RWF, both published
                                                   as a stock
quote codes bitget spot uses   USDT 3319, USDC 31, EUR 11, USD1 7, BRL 4,
                               BTC 3, USD 3, USDE 3, RLUSD 3, ETH 2,
                               SOL 1, U 1, VND 1
control  pairs whose quote alone is a national currency   19
```

### The detours searched, and the reading that shut each one

| The detour | What shut it |
| --- | --- |
| another endpoint | all five product types of `/api/v3/market/instruments` were read, 4603 rows, and `/api/v2/spot/public/coins` served 5483 rows whose fields are `coinId`, `coin`, `transfer`, `chains`, `areaCoin` with no sector among them |
| another API version | the v2 spot symbols endpoint served 3389 rows and carries no sector field; the v3 instruments endpoint carries `symbolType` and names no currency |
| another endpoint path naming the product | the library's 128 public endpoint paths were searched for `categor`, `sector`, `classif`, `tag`, `label`, `area`, `zone`, `forex`, `fiat` and `equity`; all ten answered 0, against a control of 2 paths naming `coins` and 1 naming `stock` |
| another product reaching the same market | the 11 pairs quoted in EUR, the 4 in BRL and the 1 in VND are a crypto asset or a dollar stablecoin against a national currency, and the venue publishes each base as crypto |
| the page the readiness matrix cited | `bitget.com/support/articles/12560603776372` is titled "Bitget Launches EUR and GBP Fiat Trading Pairs" and lists `USDT/EUR, BTC/EUR, ETH/EUR, USDT/GBP, BTC/GBP ETH/GBP`; every pair has one crypto leg |
| a capability already in this tree | `src/trading/scrumming/sizing.py, in session_unit_rule` and `in recorded_unit_rule` would size a currency pair if one existed, and Kraken's twelve such pairs prove they do |

### A control proving the search could have found a route that does exist

The same five instrument reads, in the same run, found 3141 stock rows, 9 metal
rows and 3 commodity rows, and each one became a recorded market under its own
sector. The same endpoint-path search found the `coins` and `stock-info` paths.
The same symbol search found 8 index-fund tokens. So a forex product on this
venue would have been found by the readings that report zero of it.

**This overtakes a line on an earlier page.**
`docs/audits/2026-10-07_venue_sector_readiness_matrix/REPORT.md` records
`bitget | forex | offers` and its own quoted sentence is a crypto-fiat
announcement. Under the reading Kraken settled on this issue, which is two
national-currency legs, Bitget offers none. The matrix's verdict is not reversed
by this page for any other venue.

---

## Step five, the arithmetic

The set the screen offers, against the set it can act on.

| Sector | Venues offered | Of those, bitget can act | The difference |
| --- | --- | --- | --- |
| crypto | 21 | yes, 571 markets | 0 |
| stocks | 20 | yes, 3141 markets, 0 before this unit | 0 |
| commodities | 17 | yes, 12 markets, 8 before this unit | 0 |
| indices | 14 | **no market of its own** | 1 venue offered, 0 markets |
| futures_perps | 16 | yes, 534 markets, of which 2 refuse | 2 markets |
| forex | 8 | bitget is not offered and serves none | 0 |

Offered minus actionable, per sector: crypto 0, stocks 0, commodities 0, indices
1 venue, futures and perpetuals 2 markets, forex 0.

---

## What was read

| What | Where | When |
| --- | --- | --- |
| the Prohibited Countries definition and sections 2.6, 2.8 and 11.1(xvii) | `bitget.com/support/articles/360014944032-terms-of-use` | 2026-10-10 |
| the order body, the size unit per order type, and the field names | `bitget.com/api-doc/uta/trade/Place-Order` | 2026-10-10 |
| the instrument record, five product types | `api.bitget.com/api/v3/market/instruments` | 2026-10-10 |
| the equity product list, its names and trading windows | `api.bitget.com/api/v3/reality/market/stock-info` | 2026-10-10 |
| the spot coin list | `api.bitget.com/api/v2/spot/public/coins` | 2026-10-10 |
| the spot symbol list | `api.bitget.com/api/v2/spot/public/symbols` | 2026-10-10 |
| the EUR and GBP pair announcement | `bitget.com/support/articles/12560603776372` | 2026-10-10 |
| the library's own request builder | `ccxt/bitget.py, in create_order_request`, ccxt 4.5.85 | 2026-10-10 |

### Controls on what the host answers

```
GET /api/v2/public/time                      200
GET /api/v3/market/instruments?category=SPOT 200, 3389 rows
GET /api/v3/market/instruments               400172, parameter verification
                                             failed
GET /api/v3/market/instruments?category=SUSDT-FUTURES   400
GET /api/v2/public/not-a-real-route          404
```

A real path answered 200, a real path with a missing parameter answered its own
error code, and an invented path answered 404, all in the same run. So each 200
above is a reading and not a host that agrees with every request.

### The instruments the readings were taken with

Every archetype was calibrated before its reading was trusted. Exit codes read
directly:

```
coding_archetype  known_good.py 0   known_bad.py 1
coding_archetype  known_good.js 0   known_bad.js 1
docs_archetype    known_good.md 0   known_bad.md 1
docs_archetype    citation_good.md 0   citation_bad.md 0
```

The citation pair does not separate on the verdict. `citation_bad.md` reports
four H006 findings at MEDIUM and still exits 0, because the verdict trips on
HIGH. A green docs verdict is therefore not proof that a citation is sound, and
every citation on this page was checked by symbol instead.

### No test covers this

`pytest --collect-only` collects nothing. The `tests/` tree holds a
`conftest.py` and six Solidity contract tests, and no Python test names any
symbol this unit changed. The zero is a reading of the tree and not of the
command: the directory listing shows the six Solidity files and no Python
candidate.

---

## What changed

Three product files.

```
src/exchange/ccxt_connector.py
    US_ACCOUNT_RESTRICTED_EXCHANGES holds this venue, with the clause quoted
    AssetSectorRecord carries one venue's whole asset-sector record
    VENUE_ASSET_SECTOR_RECORDS replaces VENUE_ASSET_CATEGORY_METHOD and holds
    Gate.io's row unchanged beside Bitget's
    NO_PUBLISHED_FAMILY names what a venue's own word maps onto where that
    word names no family outside crypto
    ASSET_SECTOR_ROWS_KEY names the key a mapping response carries its rows
    under
    _published_asset_sectors reads the record once per request it names
    _asset_sector_rows takes one call's rows, from the response itself or from
    its own rows key
    _read_asset_sector_rows writes one sector per asset code and leaves a code
    a previous row already named untouched

src/trading/scrumming/sizing.py
    CITED_CASH_MARKET_BUY holds this venue, so whole_unit_buy_needs_limit
    answers True for its 36 whole-stepping spot markets

src/gui/main_tabs/asset_class_surface.py
    EXTRA_VENUE_CLASSES records why the indices row holds a venue whose own
    record names no index
```

**No sector was added to the surface and none was removed.** Four of the five
offered sectors were already offered and now hold markets; the fifth holds none
and the venue's own pages say why.

---

## What this page could not establish

```
whether the venue accepts a live order from this program
    no reading used a credential, so every order shape here is read from the
    venue's own page and the library's own builder and never from a fill

whether the operator can ever hold an account
    the venue's terms refuse a U.S. person, and no software substitutes

whether the 36 limit-order markets fill as a market buy would
    no order was placed, so the substitution is proved on the size and not on
    the fill

whether the two demo contracts have a live sibling
    category=SUSDT-FUTURES answers HTTP 400, so the demo product type is not
    in the instrument record this page reads
```

---

## Related pages

- [`docs/manual/15-venue-compatibility.md`](../../manual/15-venue-compatibility.md)
  the venue table and the variant definitions this page reads against
- [`docs/manual/16-sector-exchange-product-tree.md`](../../manual/16-sector-exchange-product-tree.md)
  the sector, venue and product levels
- [`docs/audits/2026-10-10_gateio_wired_six_sectors/REPORT.md`](../2026-10-10_gateio_wired_six_sectors/REPORT.md)
  the venue whose record this one is read beside, and the shape this page follows
- [`docs/audits/2026-10-09_kraken_sector_order_formats/REPORT.md`](../2026-10-09_kraken_sector_order_formats/REPORT.md)
  the reading that settled what a forex market is
- [`docs/audits/2026-10-08_coinbase_sector_order_formats/REPORT.md`](../2026-10-08_coinbase_sector_order_formats/REPORT.md)
  the mirror the six points are walked against
- [`docs/audits/2026-10-07_venue_sector_readiness_matrix/REPORT.md`](../2026-10-07_venue_sector_readiness_matrix/REPORT.md)
  which venue reaches which sector
