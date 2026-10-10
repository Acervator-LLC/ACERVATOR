# Gate.io Wired Across Six Sectors

**Mode: Reference, with three product files changed.**

This page covers issue #1192. It answers the eight connections of that issue's
wired-venue section for Gate.io, establishes how Gate.io requires an order to
be formatted in each of the six sectors it serves, names the bot variant each
format demands, and records what changed so each sector reaches an order.

**FALSIFICATION.** This page is wrong if a field named here is absent from
Gate.io's own published specification, if a sector's order body accepts a field
this page calls refused, if the program's order call passes a field this page
says it omits, if a Gate.io order the program now refuses turns out to be one
the venue would have accepted, or if the asset sector this page reads off the
venue's own `category` list turns out to name something other than the sector.

---

## The verdict, one row per sector

| Sector | Verdict | The cost, where there is one |
| --- | --- | --- |
| crypto | yes-if | the venue's own terms refuse a U.S. person |
| stocks | yes-if | the same account refusal, and nothing else |
| commodities | yes-if | the same account refusal, and nothing else |
| forex | yes-if | the same account refusal, and nothing else |
| indices | yes-if | the same account refusal, and nothing else |
| futures and perpetuals | yes-if | the same account refusal; one market of 619 refuses on the cash-amount shape |

**One cost sits on all six rows and it is not a sector fact.** Gate.io's own
user agreement refuses a U.S. person, so the operator cannot open the account
any of these sectors needs. The order path reaches every sector; the account
does not exist. That is the issue's own definition of a yes-if, a door that
exists and cannot be walked through.

**No sector reads no, and no sector reads not established.** Every one of the
six has a market list, an order route, a published order body, a position and
fill read, candles and a built variant, all six points answered.

---

## The eight connections

Every reading was taken in a process whose home directory was redirected to a
scratch tree before any module under the source tree was imported, with the
redirected home printed and the tree's contents listed afterwards. No
credential was sent, no account was created, and no order was placed, priced,
amended, previewed or cancelled.

| # | The connection | Gate.io | The symbol that answers it |
| --- | --- | --- | --- |
| 1 | a connector exists and is registered | answered, through the library's renamed class | `src/exchange/ccxt_connector.py, in CCXT_CLASS_ALIASES` |
| 2 | offered under every sector it serves | answered, six of six | `src/gui/main_tabs/asset_class_surface.py, in EXTRA_VENUE_CLASSES` |
| 3 | the operator can enter its credentials | answered, on the Exchanges tab and in the first-run wizard | `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` |
| 4 | a Start press builds its connector | answered | `src/gui/main_window.py, in _connect_exchange_for_bot` |
| 5 | its market rules record on connect | **four sectors recorded nothing or the wrong thing, now answered** | `src/exchange/ccxt_connector.py, in _published_asset_sectors` |
| 6 | its orders carry the shape the venue publishes | answered, two bodies across the six sectors | `src/exchange/ccxt_connector.py, in declared_order_types` |
| 7 | a built variant selects for it | answered, six sector variants and the whole-unit one | `src/trading/scrumming/sizing.py, in VARIANTS_BUILT` |
| 8 | its gate decisions log under it | answered, six distinct paths | `src/core/log_paths.py, in gate_log_path` |

---

## Row one, the connector

The membership test the issue names does not hold on the current library, and
the venue is reached anyway.

```
ccxt version                            4.5.85
'gateio' in ccxt.exchanges              False
'gate'   in ccxt.exchanges              True
'gateio' in SUPPORTED_EXCHANGES         True, of 15 ids
resolve_ccxt_class(ccxt, 'gateio')      <class 'ccxt.gate.gate'>
'gateio' in CRYPTO_CONNECTORS           False, so no connector was written
'gateio' in PASSPHRASE_EXCHANGES        False, so the form asks for a key and a
                                        secret and no passphrase
```

The library renamed the class, and `src/exchange/ccxt_connector.py, in
resolve_ccxt_class` reads `CCXT_CLASS_ALIASES` when the direct attribute is
absent. The earlier Gate.io page recorded the same three readings and they hold
today.

The library's own capability map carries every product line the six sectors
need.

```
has[spot]   True    has[margin] True   has[swap] True
has[future] True    has[option] True
api sections            private, public
endpoint entries        395
```

---

## Row one, continued: the account the venue will not open

`US_ACCOUNT_RESTRICTED_EXCHANGES` named two venues and not this one, so the
connect path warned nothing while the venue's own published words refuse the
operator. The set now holds it.

> You and any Represented Persons are not "U.S. persons" or "U.S. customers"

> we do not intend to provide Services to or solicit such "U.S. persons" or
> "U.S. customers," and expressly prohibit the same from using any of our
> Services

Both sentences are clause 2.10 of
[the user agreement](https://www.gate.com/legal/user-agreement), read
2026-10-10. The restricted-locations page names the country first in its own
list.

> Currently restricted regions include but are not limited to: the United
> States, Mainland China, Singapore, Canada, France, Germany, Hong Kong

Read at
[the restricted-locations page](https://www.gate.com/help/guide/faq/40959/restricted-locations),
2026-10-10.

```
before   'gateio' in US_ACCOUNT_RESTRICTED_EXCHANGES    False
         'gateio' in US_RESTRICTED_EXCHANGES            False
after    'gateio' in US_ACCOUNT_RESTRICTED_EXCHANGES    True
         'gateio' in US_RESTRICTED_EXCHANGES            True
         the words the connect path now records         US account restricted
         the record it writes                           US_RESTRICTION_WARNING
control  'coinbase' in US_RESTRICTED_EXCHANGES          False, before and after
```

**The warning reaches the log and not the venue picker.**
`src/exchange/ccxt_connector.py, in exchange_label` composes the note, and its
only reader is `src/exchange/ccxt_connector.py, in list_supported_exchanges`,
which no screen calls. The first-run wizard's own `exchange_label` in
`src/gui/main_tabs/init_wizard_surface.py` is a different function and notes a
passphrase alone. Putting the refusal beside the venue's own button is its own
row, and this page does not reshape a screen.

**The address is not the refusal.** The venue's public endpoints answer a US
address, so this is an account matter and not an IP block, which is why the
entry sits in the account set and not the IP one.

```
GET https://api.gateio.ws/api/v4/spot/currencies    status 200, 5640 rows
```

---

## Row two, the sectors

The surface offers the venue under all six, and the entry that puts five of
them there did not move.

```
EXTRA_VENUE_CLASSES['gateio']   stocks, commodities, forex, indices,
                                futures_perps
crypto arrives from             crypto_venues, off SUPPORTED_EXCHANGES
venue_classes('gateio')         commodities, crypto, forex, futures_perps,
                                indices, stocks
sectors offering gateio         6 of 6
```

---

## Row three, the credential form

One source answers the whole arithmetic. The Exchanges tab reads the sector's
own venue list and the Add form reads that same list, so the set the screen
offers and the set it can act on cannot differ.

```python
# src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows
    for venue in sorted(acs.venues_for_class(wing)):
```

| Sector | Venues offered | The form accepts this venue |
| --- | --- | --- |
| crypto | 21 | yes |
| stocks | 20 | yes |
| commodities | 17 | yes |
| forex | 8 | yes |
| indices | 14 | yes |
| futures_perps | 16 | yes |

The first-run wizard narrows the same superset and offers this venue too.

```
known_venues count                  25
wizard exchange_ids count           25
'gateio' offered by the wizard      True
add_exchange_enabled('crypto')      True
```

**The wizard's own screen is still not mounted**, which the issue's row three
already records as its own row. That is unchanged by this page.

---

## Row four, the Start press

The venue takes the library path, because neither the broker registry nor the
written-crypto registry names it. Nothing venue-specific stands between the
press and the connector.

```python
# src/gui/main_window.py, in _connect_exchange_for_bot
            if broker_connector_class(eid) is not None:
                return self._connect_broker_for_bot(bot)

            if crypto_connector_class(eid) is not None:
                return self._connect_written_crypto_for_bot(bot)
```

```
broker_connector_class('gateio')    None
crypto_connector_class('gateio')    None
the path taken                      CCXTConnector('gateio')
```

---

## Row five, the recording, and the four sectors it got wrong

This is the row that was broken, and it was broken four ways at once.
`get_markets` labels every market it records, and the label decides which
sector's product list that market appears in, through
`src/gui/main_tabs/asset_class_surface.py, in markets_of_class`.

Measured on the venue's own public market list, 6677 active markets, with the
classifier as it stood.

| Sector | Markets the sector's list held | What was wrong |
| --- | --- | --- |
| crypto | 2187 | held 163 tokenised equities and 3 metal tokens, and lacked 10 markets of its own that read forex |
| stocks | 0 | the operator could reach no market at all |
| commodities | 138 | 130 of the 138 were option contracts |
| forex | 20 | **every one of the twenty was not a currency** |
| indices | 0 | the operator could reach no market at all |
| futures_perps | 4332 | 3288 of the 4332 were option contracts |

### The forex rows were ticker collisions, and the venue names each one

`market_asset_class` read a market as forex when both legs resolved to a
currency code, and `FIAT_CURRENCY_CODES` holds 170 three-letter codes. Gate.io
lists crypto tokens and equity perpetuals whose tickers are those same letters.
Its own `/spot/currencies` record publishes a name for each.

| The code | What the program called it | What the venue's own record names |
| --- | --- | --- |
| AMD | forex, the Armenian dram | Advanced Micro Devices |
| COP | forex, the Colombian peso | ConocoPhillips |
| NOK | forex, the Norwegian krone | Nokia |
| CAD | forex, the Canadian dollar | Caduceus Protocol |
| BDT | forex, the Bangladeshi taka | Bandot Protocol |
| ISK | forex, the Icelandic krona | ISKRA Token |
| RON | forex, the Romanian leu | Ronin Network |
| SCR | forex, the Seychellois rupee | Scroll |
| TTD | forex, the Trinidad dollar | TradeTide |
| MNT | forex, the Mongolian tugrik | Mantle |
| BOB | forex, the Bolivian boliviano | BOB |

Three of those eleven are equity perpetuals, so the operator was offered three
share contracts inside the forex sector while the stocks sector held none.

### The venue publishes the sector itself, on a public credential-free record

Gate.io's `/spot/currencies` record carries a `category` list per asset code,
and the words in it are the platform's own vocabulary.

```
the venue's own category counts, 5640 codes
  []                                  5032
  ['stocks']                           401
  ['gstocks', 'stocks']                 78
  ['stocks', 'ondo-stocks']             47
  ['stocks', 'xstocks']                 41
  ['indices']                           17
  ['metals']                            11
  ['forex']                              4
  ['commodities']                        3
  ['metals', 'stocks', 'ondo-stocks']    3
  ['ondo-stocks']                        1
  ['metals', 'stocks']                   1
  ['indices', 'stocks', 'xstocks']       1
```

`stocks`, `indices`, `forex` and `commodities` are live class names in
`src/trading/ata_spm.py, at ASSET_CLASSES`, and `metals` already resolves onto
commodities through `RETIRED_CLASSES` in that same module. So no new vocabulary
and no new map were needed: `src/trading/ata_spm.py, in asset_class_named`
resolves each published word, and the first category of a row that resolves is
the sector that row names.

`src/exchange/ccxt_connector.py, in _published_asset_sectors` reads that record
through the library's own public method and answers one sector per asset code.

```
the method                   publicSpotGetCurrencies
codes answered               5640
codes carrying a sector        607
  stocks                       567
  commodities                   18
  indices                       18
  forex                          4
one asset at a time         AAPLX -> stocks      SPX500 -> indices
                            XAUT  -> commodities EURUSD -> forex
                            CAD   -> ''          BTC    -> ''
                            NOTACODE -> absent
```

**An empty list is the venue's own answer, not a gap.** Gate.io publishes a
category for 607 of its 5640 codes, so a code with an empty list is the venue
stating the asset is none of its labelled families.
`src/exchange/ccxt_connector.py, in market_asset_class` therefore stops reading
the base and quote codes for a venue that publishes such a record, and the
eleven collisions above close with it.

### An option contract is not a perpetual, and the program draws no options sector

3418 of the venue's 6677 active markets are option contracts. Every one carried
`contract` true, so `is_contract_market` answered true and the market recorded
under futures and perpetuals, or under commodities where its underlying is a
metal. An option's order body is a third body with its own multiplier field,
and no variant sizes one.

`src/trading/ata_spm.py, at CLASS_OPTIONS` names the sector an option records
under. `ASSET_CLASSES` omits it, so no screen offers it, and
`src/trading/scrumming/sizing.py, in sector_variant` names a variant
`VARIANTS_BUILT` lacks, which refuses the market rather than sizing it as a
perpetual.

```
rows recorded under options                 3418
of those, rows reaching any sector's list       0
symbol_class on one of them                 options
the variant it names                        options Scrumming
that variant is built                       False
```

**That exposed a second defect in the read path, in a different module.**
`src/gui/main_tabs/asset_class_surface.py, in symbol_class` answered crypto for
any recorded label its resolver did not know, which would have moved all 3418
option rows into the crypto list. Its own docstring says it answers crypto for
a symbol the recording holds none for, so the code disagreed with its stated
contract. It now answers crypto only where the recording holds no row.

```
control  symbol_class on a symbol with no recorded row    crypto
control  symbol_class on a recorded crypto market         crypto
         symbol_class on a recorded option market         options
```

### The recording after the change

```
rows written                       6677
rows carrying a sector             6677
markets whose sector moved          612
```

| Sector | Markets before | Markets after |
| --- | --- | --- |
| crypto | 2187 | 2031 |
| stocks | 0 | 565 |
| commodities | 8 | 20 |
| forex | 20 | 6 |
| indices | 0 | 18 |
| futures_perps | 1044 | 619 |
| options, which no screen offers | 3418 | 3418 |

Every one of the 612 moves, named by where it came from and where it went.

| From | To | Markets |
| --- | --- | --- |
| futures_perps | stocks | 399 |
| crypto | stocks | 163 |
| futures_perps | indices | 18 |
| forex | crypto | 10 |
| futures_perps | commodities | 9 |
| forex | futures_perps | 4 |
| crypto | commodities | 3 |
| forex | stocks | 3 |
| futures_perps | forex | 3 |

The 399 are equity perpetuals and the 163 are tokenised equity spot pairs, so
the stocks sector gains its markets from two product lines at once. The ten
that leave forex for crypto are the stablecoin and token pairs the ticker
collision caught.

The before column reads the classifier with no published sector supplied, which
is what every other venue still gets. The two columns differ by 612 markets and
by nothing else.

**Control: the same arithmetic reports no movement when the venue's record is
blinded.** With every published category replaced by an empty list, the only
markets that move are the 3418 options, and all 612 sector moves disappear. So
the 612 is a reading of the venue's record and not of the instrument.

**Control: a venue that publishes no such record is untouched.**

```
VENUE_ASSET_CATEGORY_METHOD              {'gateio': 'publicSpotGetCurrencies'}
kraken _published_asset_sectors()        None
```

---

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
option-shaped symbols               0
modification time, before == after  True
size, before == after               True
```

**Nothing in this branch can move a row of it.**
`VENUE_ASSET_CATEGORY_METHOD` names one venue and it is not the recorded one,
so `market_asset_class` reads `published` as None for every recorded row and
answers exactly what it answered before. No recorded symbol is an option, so
`CLASS_OPTIONS` reaches none of them. Every recorded row already names a
sector the resolver knows, so `symbol_class`'s narrowed fallback changes none
of them either.

---

## Row six, the order shape

Two bodies serve all six sectors. The spot body carries three of them and the
futures body carries the other three. Each was built by the library's own
request builder with the transport replaced, so nothing reached the venue.

```
fetch2          the transport is replaced; nothing reaches the venue
fetch           the transport is replaced; nothing reaches the venue
load_markets    the transport is replaced; nothing reaches the venue
```

All three were called to confirm the replacement before any body was built.

### The spot body, which crypto, stocks and commodities take

```
endpoint        POST /spot/orders
size field      amount
order types     limit, market
time in force   ioc on a market order
```

```
crypto       BTC/USDT    sell market  {"currency_pair": "BTC_USDT", "type": "market", "account": "spot", "side": "sell", "amount": "5", "time_in_force": "ioc"}
crypto       BTC/USDT    buy  market  {"currency_pair": "BTC_USDT", "type": "market", "account": "spot", "side": "buy", "amount": "500", "time_in_force": "ioc"}
stocks       AAPLX/USDT  sell limit   {"currency_pair": "AAPLX_USDT", "type": "limit", "account": "spot", "side": "sell", "amount": "5", "price": "100"}
commodities  XAUT/USDT   buy  market  {"currency_pair": "XAUT_USDT", "type": "market", "account": "spot", "side": "buy", "amount": "500", "time_in_force": "ioc"}
```

The market buy's `amount` is 500 where five units were asked at a price of one
hundred, because this venue reads that field as a cash amount on a market buy
and as a unit count on a market sell. Its own page states it in one sentence.

> `side`: `buy` refers to the quote currency, e.g. `USDT` in `BTC_USDT`

`src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` already holds this
venue, so the reading did not move and no change was needed.

```
market_buy_names_cash('BTC/USDT', 'gateio')    True
CITED_CASH_MARKET_BUY                          binance, coinbase, gateio
```


The cash rule reaches 896 of the venue's markets, every one of them a crypto
spot pair whose published step is a whole unit.
`src/trading/scrumming/sizing.py, in whole_unit_buy_needs_limit` answers True
for those, so the buy becomes a limit order priced to cross and the unit count
the size rule floored is the count the venue credits. A market buy sized in
cash cannot hold a unit count, which is why the limit order is the treatment.

| Sector | Unit rule | Cash market buy | The buy needs a limit order | Markets |
| --- | --- | --- | --- | --- |
| crypto | whole | yes | yes | 896 |
| crypto | fractional | yes | no | 1135 |
| stocks | fractional | yes | no | 163 |
| stocks | whole | no | no | 402 |
| commodities | fractional | yes | no | 5 |
| commodities | whole | no | no | 15 |
| forex | fractional | yes | no | 2 |
| forex | whole | no | no | 4 |
| indices | whole | no | no | 18 |
| futures_perps | whole | no | no | 619 |

### The futures body, which forex, indices and futures_perps take

```
endpoint        POST /futures/{settle}/orders
size field      size, signed; positive bids and negative asks
contract        the contract id
price           zero with an ioc time in force is the market order
settle          usdt on every one of these markets
```

```
forex          EURUSD/USDT:USDT  sell limit   {"contract": "EURUSD_USDT", "size": -5, "settle": "usdt", "price": "1.1235"}
forex          EURUSD/USDT:USDT  buy  market  {"contract": "EURUSD_USDT", "size": 5, "settle": "usdt", "price": "0", "tif": "ioc"}
indices        SPX500/USDT:USDT  sell limit   {"contract": "SPX500_USDT", "size": -5, "settle": "usdt", "price": "7807.18"}
futures_perps  BTC/USDT:USDT     buy  limit   {"contract": "BTC_USDT", "size": 5, "settle": "usdt", "price": "83049.4"}
```

**No cash field appears in this body on either side**, so the cash market buy
rule that governs the spot body does not reach the three sectors served here.

```
crypto        BTC/USDT          cash market buy True   unit rule fractional
stocks        AAPLX/USDT        cash market buy True   unit rule fractional
commodities   XAUT/USDT         cash market buy True   unit rule fractional
forex         EURUSD/USDT:USDT  cash market buy False  unit rule whole
indices       SPX500/USDT:USDT  cash market buy False  unit rule whole
futures_perps BTC/USDT:USDT     cash market buy False  unit rule whole
```

### The one market that refuses, and it refuses before the connector

One contract of the 619 is margined in its own base asset, so one contract is a
fixed cash amount rather than a fraction of a unit.
`src/exchange/ccxt_connector.py, in contract_units` answers nothing rather than
a figure, so no dollar amount is written into a unit-count field, and the order
refuses on the size shape.

```
BTC/USD:BTC    contract_units        None
               buy size shapes       cash amount
               sell size shapes      cash amount
               handed to place_order nothing, on either side
```

### The expiry the dated contracts carry

30 of the 619 futures rows carry an expiry, which the expiry close reads.

```
ADA/USDT:USDT-261016   expiry_ms 1792137600000   expires True   permits_close True
ADA/USDT:USDT-261023   expiry_ms 1792742400000   expires True   permits_close True
```

---

## Row seven, the variant

Every one of the six sectors selects a variant that is built, read at the
venue's own last price.

| Sector | Markets | The variants its markets select |
| --- | --- | --- |
| crypto | 2031 | Crypto Scrumming, 2031 |
| stocks | 565 | Stock Scrumming 252, Whole Unit Scrumming 313 |
| commodities | 20 | Commodity Scrumming 7, Whole Unit Scrumming 13 |
| forex | 6 | Forex Scrumming, 6 |
| indices | 18 | Index Scrumming 4, Whole Unit Scrumming 14 |
| futures_perps | 619 | Futures Scrumming 601, Whole Unit Scrumming 18 |

```
Commodity Scrumming        built True
Crypto Scrumming           built True
Forex Scrumming            built True
Futures Scrumming          built True
Index Scrumming            built True
Stock Scrumming            built True
options Scrumming          built False
```

**No sector demands a variant that is not built.** `options Scrumming` is the
one unbuilt name, it belongs to no sector the platform draws, and naming it is
what refuses those 3418 markets.

Whole Unit Scrumming answers ahead of the sector where the venue's smallest
order costs more than a reference scrum excess, which is a property of the
market's own floor and price and not a seventh variant.

---

## Row eight, the gate log

One path per sector, each naming the venue and the sector, every one created
under the redirected home during the drive.

```
trade/gate/gateio/crypto/gate.log
trade/gate/gateio/stocks/gate.log
trade/gate/gateio/commodities/gate.log
trade/gate/gateio/forex/gate.log
trade/gate/gateio/indices/gate.log
trade/gate/gateio/futures_perps/gate.log

distinct paths   6 of 6 sectors
```

---

## The six points, per sector

Coinbase is the mirror. Every row below is answered on all six points.

| Sector | Market list | Order route | Order shape | Position and fill read | Candles | Bot variant |
| --- | --- | --- | --- | --- | --- | --- |
| crypto | `load_markets`, 2031 markets | `POST /spot/orders` | `amount`, cash on a market buy | the library's own balance and trade reads | `src/exchange/timeframes.py, at gateio`, nine timeframes | Crypto Scrumming |
| stocks | `load_markets`, 163 tokenised spot pairs and 402 equity perpetuals | `POST /spot/orders` and `POST /futures/usdt/orders` | `amount`, and `size` on the perpetual | the same two reads | the same nine | Stock Scrumming, Whole Unit Scrumming |
| commodities | `load_markets`, 5 metal spot pairs and 15 metal perpetuals | the same two routes | the same two bodies | the same two reads | the same nine | Commodity Scrumming, Whole Unit Scrumming |
| forex | `load_markets`, 6 markets the venue's own record calls forex | the same two routes | the same two bodies | the same two reads | the same nine | Forex Scrumming |
| indices | `load_markets`, 18 index perpetuals | `POST /futures/usdt/orders` | `size`, signed | the same two reads | the same nine | Index Scrumming, Whole Unit Scrumming |
| futures and perpetuals | `load_markets`, 619 markets, 30 of them dated | `POST /futures/{settle}/orders` and `POST /delivery/{settle}/orders` | `size`, signed, with the expiry read | the same two reads | the same nine | Futures Scrumming, Whole Unit Scrumming |

The timeframe list is the one the program holds for this venue, nine values, so
every sector's candles come from one source with one set of granularities.

```
src/exchange/timeframes.py, at gateio
    1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w
```

---

## Step five, the arithmetic

Per sector: the venues the screen offers, whether this venue is among them, the
markets its sector list narrows to, and how many of those the engine can size.

| Sector | Venues offered | This venue offered | Markets in its list | Markets it can size | Difference |
| --- | --- | --- | --- | --- | --- |
| crypto | 21 | yes | 2031 | 2031 | none |
| stocks | 20 | yes | 565 | 565 | none |
| commodities | 17 | yes | 20 | 20 | none |
| forex | 8 | yes | 6 | 6 | none |
| indices | 14 | yes | 18 | 18 | none |
| futures_perps | 16 | yes | 619 | 618 | 1, the base-margined contract |

**The one difference is a refusal the program means.** The base-margined
contract names a cash amount on both sides, the cash-amount shape is not built,
and the order stops before the connector.

Before this unit the same subtraction read differently on four of the six rows:
stocks offered a venue with no market, indices offered a venue with no market,
forex offered twenty markets none of which was a currency, and commodities and
futures offered 3418 option contracts between them.

---

## What was read

```
https://www.gate.com/legal/user-agreement
https://www.gate.com/help/guide/faq/40959/restricted-locations
https://api.gateio.ws/api/v4/spot/currencies
https://api.gateio.ws/api/v4/stock/symbols
https://api.gateio.ws/api/v4/tradfi/symbols
    all read 2026-10-10
```

Every venue reading is of a public page or a public, credential-free endpoint.
Every behaviour reading is of the connector library's own code in this
machine's own site packages, or of this branch's own code driven in a process
with the home directory redirected. The two are reported separately throughout.

### Controls on what the host answers

The same host answers a real path and refuses an invented one, in the same run.

```
GET  spot/currencies      200, 5640 rows
GET  spot/notapath        HTTP 400 Bad Request
GET  stock/symbols        200, a page of 4715 symbols over 472 pages
GET  tradfi/symbols       200, a list of CFD symbols
GET  tradfi/contracts     HTTP 404 Not Found
GET  tradfi/instruments   HTTP 404 Not Found
```

```
publicSpotGetCurrencies         callable on the instance
publicSpotGetNotapath           not callable
'NOTACODE' in the venue record  False
'BTC' in the venue record       True
venue_classes('notavenue')      empty
resolve_ccxt_class('notavenue') None
```

---

## The detours searched, and what each shut

The earlier Gate.io page recorded the TradFi Stock line and the CFD line as
unreachable because the installed library carries no endpoint for either, and
it read three sectors as listed-and-charted-only on that ground. **That reading
is now stale for a reason that has nothing to do with those two lines.** The
sectors are reached through the spot and futures lines the library already
carries, so neither absent line decides a sector any more.

| The detour | What was read | Where it leads |
| --- | --- | --- |
| another endpoint | `/stock/orders` and `/tradfi/orders` answer `MISSING_REQUIRED_HEADER`, so both paths exist and both need a signature | the lines are real and no library endpoint builds their orders |
| the installed library's own map | 395 endpoint entries, none naming stock, tradfi or cfd | unchanged from the earlier page |
| another documentation host | `api.gateio.ws` serves `/stock/symbols` and `/tradfi/symbols` publicly | **this corrects the earlier page**, the symbol lists are readable with no credential |
| another product reaching the same market | the spot and futures lines carry 565 equity, 18 index, 20 metal and 6 forex markets | **this is what decided all four sectors** |
| a capability already in this tree | `asset_class_named` already resolves `metals`, and `markets_of_class` already narrows by the recorded sector | no new mechanism was needed, only the venue's own label |
| a page's script rather than its served markup | not reached, the public JSON endpoints answered directly | no absence was recorded from markup |
| a different account type | the venue's refusal is of the person, not of an account tier | the cost on every row above |

**The earlier page's control was the one that failed.** Its endpoint search
reported zero entries naming stock, tradfi or cfd, and the same search reported
zero entries naming `spot/orders`, a path that certainly exists. A search whose
control reads zero cannot tell an absence from a blind reading. The library's
api map nests by section rather than by path string, so the search pattern
never matched anything. The detour row above re-ran it against the section
keys, where `stock` and `tradfi` are genuinely absent and the control finds
what exists.

### Which readings would read the same whether a sector is reachable or not

Stated plainly, because three of them did exactly that before this unit.

- **`venues_for_class(sector)` and the Add form's own set.** Both read
  `EXTRA_VENUE_CLASSES`, which is a declaration. They read six of six before
  this unit, while two of the six sectors had no market at all. A venue offered
  under a sector is not a sector with a market in it.
- **`gate_log_path(venue, sector)`.** It composes a path from two strings and
  creates the directory. It answers six of six for any venue id and any sector
  name, including an invented one, so it can never report a sector unreachable.
- **`declared_order_types`.** It reads the exchange's capability map, which is
  one answer for the whole venue, so it reads the same for all six sectors
  whatever each sector lists.
- **`VARIANTS_BUILT` membership.** It is a set of eight names. It answers built
  for a sector with no market as readily as for one with 2031.
- **A market count taken off `load_markets` without the sector label.** 6677
  active markets is the same number whether the labels are right or wrong, and
  only the per-sector narrowing moves.

The readings that do discriminate are the three the step-five table uses: the
markets a sector's list narrows to, the markets the engine can size out of that
list, and the order body the library builds for one of them.

---

## What changed

Three product files.

```
src/exchange/ccxt_connector.py
    VENUE_ASSET_CATEGORY_METHOD names the public, credential-free method a
    venue publishes its own asset sectors on
    _published_asset_sectors reads that record and answers one sector per
    asset code
    _published_sector answers the sector one market's base code carries
    market_asset_class takes that sector ahead of the base and quote codes,
    answers CLASS_OPTIONS for an option record, and reads the codes only
    where the venue publishes no such record
    is_option_market names an option record
    get_markets supplies the published sector for every market it records
    US_ACCOUNT_RESTRICTED_EXCHANGES holds this venue

src/trading/ata_spm.py
    CLASS_OPTIONS names the sector an option contract records under, outside
    ASSET_CLASSES so no screen offers it

src/gui/main_tabs/asset_class_surface.py
    symbol_class answers crypto only where the recording holds no row, which
    is what its own docstring already stated
```

**No variant was added.** The six sector variants and the whole-unit variant
were already built, and `options Scrumming` is a name `sector_variant` composes
for a sector with no variant, which is the mechanism that refuses a market
rather than trading it under another sector's variant.

**Nothing on the order guard moved.** `guarded_place_order`'s refusals, the
expiry close, the approval guard, the session-route guard, every venue's
signing and credential handling, `SYNC_QUEUE_CAP` and the bulk-read constants
are untouched by this branch.

---

## What this page could not establish

```
whether the venue would accept a live order from this program
    no credential was sent and no order was placed, so nothing here proves a
    fill

the per-pair step of any single spot market
    the step, the minimum and the precision exist in the live currency-pairs
    record; the market list was read and the per-pair record was not asked
    separately

the order body of the TradFi Stock line and of the CFD line
    both paths exist and both demand a signature, and the installed library
    builds neither; the lines decide no sector now, so no sector waits on them

whether a tokenised equity's 24/7 or 24/5 window reaches the session rule
    the venue publishes two windows for that family and the program holds one
    session rule per market record
```

---

## Related pages

- [`docs/manual/15-venue-compatibility.md`](../../manual/15-venue-compatibility.md)
  the venue table and the variant definitions this page reads against
- [`docs/manual/16-sector-exchange-product-tree.md`](../../manual/16-sector-exchange-product-tree.md)
  the sector, venue and product levels
- [`docs/audits/2026-10-09_gateio_sector_order_formats/REPORT.md`](../2026-10-09_gateio_sector_order_formats/REPORT.md)
  the earlier order-format pass this page re-measures and corrects
- [`docs/audits/2026-10-09_kraken_sector_order_formats/REPORT.md`](../2026-10-09_kraken_sector_order_formats/REPORT.md)
  the shape this page follows
- [`docs/audits/2026-10-08_coinbase_sector_order_formats/REPORT.md`](../2026-10-08_coinbase_sector_order_formats/REPORT.md)
  the mirror the six points are walked against
- [`docs/audits/2026-10-07_venue_sector_readiness_matrix/REPORT.md`](../2026-10-07_venue_sector_readiness_matrix/REPORT.md)
  which venue reaches which sector
