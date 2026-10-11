# OKX Wired Across The Sectors It Serves

**Mode: Reference, with three product files changed.**

This page covers issue #1192. It answers the eight connections of that issue's
wired-venue section for OKX, establishes how OKX requires an order to be
formatted in each sector it serves, names the bot variant each format demands,
and records what changed so each sector reaches an order.

**FALSIFICATION.** This page is wrong if a field named here is absent from
OKX's own published specification, if a sector's order body accepts a field this
page calls refused, if the program's order call passes a field this page says it
omits, if an OKX order the program now refuses turns out to be one the venue
would have accepted, or if the asset category this page reads off the venue's
own `instCategory` field turns out to name something other than the sector.

---

## The verdict, one row per sector

| Sector | Verdict | The cost, where there is one |
| --- | --- | --- |
| crypto | **yes** | nothing |
| stocks | yes-if | the venue's own category must reach the recording, or all 400 markets record under the wrong sector |
| commodities | yes-if | the same record; 7 of the 21 are energy, copper or dated gold |
| futures and perpetuals | **yes** | 269 of the 751 belong elsewhere until the record lands |
| indices | **no** | the venue's own category vocabulary holds no index number |
| forex | **no** | the venue names a Forex number and publishes it on no product of its own |

**No row carries an account refusal, and OKX is the first venue in this run of
which that is true.** Gate.io's user agreement refuses "U.S. persons" as a class
and Bitget's Terms of Use name "the United States" in its Prohibited Countries.
OKX names neither. One account fact does sit on every row and it is a venue id
and not a refusal: a United States customer trades a different company, on a
host no venue id in this tree reaches.

---

## The eight connections

| # | The connection | OKX | The symbol that answers it |
| --- | --- | --- | --- |
| 1 | a connector exists and is registered | answered | `src/exchange/ccxt_connector.py, at SUPPORTED_EXCHANGES` |
| 2 | offered under every sector it serves | answered, three served and five offered | `src/gui/main_tabs/asset_class_surface.py, at EXTRA_VENUE_CLASSES` |
| 3 | the operator can enter its credentials | answered on both screens | `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` |
| 4 | a Start press reaches its connector | answered, the crypto path | `src/gui/main_window.py, in _connect_exchange_for_bot` |
| 5 | its market rules record on connect | answered, and 431 markets recorded the wrong sector before this unit | `src/exchange/ccxt_connector.py, in market_asset_class` |
| 6 | its orders carry the shape the venue publishes | answered, a unit count on both sides | `src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` |
| 7 | a built variant selects for it | answered, all six sector variants built | `src/trading/scrumming/sizing.py, at VARIANTS_BUILT` |
| 8 | its gate decisions log under it | answered, six distinct paths | `src/core/log_paths.py, in gate_log_path` |

---

## Row one, the connector

`'okx' in ccxt.exchanges` reads True on ccxt 4.5.85.
`src/exchange/ccxt_connector.py, at CCXT_CLASS_ALIASES` holds no entry for it,
`src/exchange/ccxt_connector.py, in resolve_ccxt_class` answers `ccxt.okx.okx`,
and no connector is hand-written: `'okx' in CRYPTO_CONNECTORS` is False.
`src/exchange/ccxt_connector.py, at PASSPHRASE_EXCHANGES` holds it, so the Add
form asks for a key, a secret and a passphrase.
`src/exchange/timeframes.py` declares eleven granularities for it.

## Row one, continued: the account a United States customer holds

**The answer is that the account exists, and it is with another company.**

OKX's own Terms of Service clause 3.1, read 2026-10-10 at
`https://www.okx.com/help/360021813691`:

> OKX INC., a Delaware corporation ("OKX US"), which operates under the OKX
> brand, for Users who are residents of one of OKX US's approved operating
> locations within the United States and its territories.

Clause 2.2 of the same page sends the jurisdiction question to one place:

> We may not make all of the Services available in all markets and
> jurisdictions

That place is the Risk & Compliance Disclosure, read 2026-10-10 at
`https://www.okx.com/en-us/help/risk-compliance-disclosure`. Its Section 3,
Regulatory Landscape, names the United States **in part and not whole**:

> certain jurisdictions within the United States of America including all U.S.
> territories such as Puerto Rico, American Samoa, Guam, Northern Mariana
> Island, and the U.S. Virgin Islands (St. Croix, St. John and St. Thomas)

The venue's own US Licenses page, read 2026-10-10 at
`https://www.okx.com/en-us/help/us-licenses`, names the company and the five
places it will not serve:

> The OKX digital asset trading platform for United States customers is
> provided by OKX INC.

> OKX INC. does not provide services to residents of the following states and
> territories at this time: New York, American Samoa, Guam, Northern Mariana
> Islands, and the U.S. Virgin Islands.

**It is neither an account refusal nor an address refusal.** The venue's public
endpoints answer this address.

```
GET https://www.okx.com/api/v5/public/instruments?instType=SPOT      200, 1160 rows
GET https://www.okx.com/api/v5/public/instruments?instType=MARGIN    200,  266 rows
GET https://www.okx.com/api/v5/public/instruments?instType=SWAP      200,  500 rows
GET https://www.okx.com/api/v5/public/instruments?instType=FUTURES   200,  265 rows
control  GET /api/v5/public/not-a-real-route                         404
control  GET /api/v5/public/instruments?instType=NOTATYPE            400
```

So neither set gains the venue, and both already read that way.

```
'okx' in US_IP_BLOCKED_EXCHANGES          False, before and after
'okx' in US_ACCOUNT_RESTRICTED_EXCHANGES  False, before and after
'okx' in US_RESTRICTED_EXCHANGES          False, before and after
control  'gateio'  in US_RESTRICTED_EXCHANGES     True
control  'binance' in US_IP_BLOCKED_EXCHANGES     True
```

**One finding falls out of clause 3.1 and it is not this unit's work.** The
venue id this platform registers is the global company. The library carries
three OKX ids and this tree registers one.

```
'okx'   in ccxt.exchanges True   host www.okx.com   in SUPPORTED_EXCHANGES True
'okxus' in ccxt.exchanges True   host us.okx.com    in SUPPORTED_EXCHANGES False
'myokx' in ccxt.exchanges True   host eea.okx.com   in SUPPORTED_EXCHANGES False
```

A resident of an approved United States location trades on `us.okx.com`, and no
venue id in this tree reaches that host. That is a venue id of its own, with its
own credential form and its own gate log, so it is the next venue row and not a
line inside this one.

## Row two, the sectors

`src/gui/main_tabs/asset_class_surface.py, at EXTRA_VENUE_CLASSES` lists the
venue under stocks, commodities, indices and futures and perpetuals, and
`src/gui/main_tabs/asset_class_surface.py, in crypto_venues` adds crypto, so
`venue_classes('okx')` answers five.

```
venue_classes('okx')            commodities, crypto, futures_perps, indices, stocks
control  venue_classes('notavenue')   empty
```

Forex is the sixth sector and the row does not name it. The venue names a Forex
number in its own vocabulary and publishes that number on nothing, so the row is
correct.

## Row three, the credential form

The set the screen offers and the set the Add form accepts are one list.
`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` narrows
`src/gui/main_tabs/asset_class_surface.py, in venues_for_class`, so the two
cannot differ.

```
crypto         21 venues | okx offered yes | Add form 21 rows, okx yes
stocks         20 venues | okx offered yes | Add form 20 rows, okx yes
commodities    17 venues | okx offered yes | Add form 17 rows, okx yes
indices        14 venues | okx offered yes | Add form 14 rows, okx yes
futures_perps  16 venues | okx offered yes | Add form 16 rows, okx yes
forex           8 venues | okx offered no  | Add form  8 rows, okx no
wizard         25 venues | okx offered yes
control  an invented venue id in any of them   no
```

`src/gui/main_tabs/init_wizard_surface.py, in exchange_ids` and the Settings tab
both narrow one superset,
`src/gui/main_tabs/asset_class_surface.py, in known_venues`, which answers 25
ids and holds this one.

## Row four, the Start press

`src/stocks/alpaca_connector.py, in broker_connector_class` answers None for
this venue, so `src/gui/main_window.py, in _connect_exchange_for_bot` takes the
crypto path and reaches `CCXTConnector`.

## Row five, the recording, and the three sectors it got wrong

### The venue publishes the category itself, on a public credential-free record

`GET /api/v5/public/instruments` carries an `instCategory` per market and needs
no key. The venue's own API documentation, read 2026-10-10 at
`https://www.okx.com/docs-v5/en/`, states the field and its whole vocabulary:

> The asset category of the instrument's base asset (the first segment of the
> instrument ID). For example, for BTC-USDT-SWAP, the instCategory represents
> the asset category of BTC. 1: Crypto 3: Stocks 4: Commodities 5: Forex
> 6: Bonds "": Not available

The library already exposes the route as `publicGetPublicInstruments`. It
refuses a call that names no product type, so the record is read four times.

```
with no instType parameter   50014 "Parameter instType can not be empty."
instType=SPOT                1160 rows   1: 1013, 3: 135, 4: 4, "": 8
instType=MARGIN               266 rows   1:  172, 3:  92, 4: 2
instType=SWAP                 500 rows   1:  301, 3: 190, 4: 9
instType=FUTURES              265 rows   1:  182, 3:  75, 4: 8
                             ----
                             2191 rows
```

**The venue uses three of its own five numbers.**

```
instCategory 1   1668 rows   Crypto
instCategory 3    492 rows   Stocks
instCategory 4     23 rows   Commodities
instCategory ""     8 rows   Not available
control  instCategory 5   0 rows   Forex
control  instCategory 6   0 rows   Bonds
control  instCategory 2   0 rows   no such value is published
```

### Why the venue's own `1` and `6` map onto nothing

`src/exchange/ccxt_connector.py, at NO_PUBLISHED_FAMILY` holds the empty string,
and both numbers map onto it.

`1` is Crypto, which is what Gate.io says by leaving an asset's category list
empty and what Bitget says with the word `crypto`. The venue is stating the
asset belongs to no family outside crypto, and
`src/exchange/ccxt_connector.py, in is_contract_market` still decides whether
the market is a spot pair or a perpetual. Mapping the number onto the crypto
class instead would move every crypto perpetual out of the futures sector, which
is the defect the Bitget unit caught on its first drive.

`6` is Bonds, which `src/trading/ata_spm.py, at ASSET_CLASSES` does not draw.
The venue publishes that number on nothing either way, so the entry records the
vocabulary and changes no reading.

### The base code is named only inside a composite id

OKX is the first venue to publish no base-code field on every product type.
`baseCcy` carries the code on SPOT and MARGIN and is empty on SWAP and FUTURES.
The venue's own documentation calls the code "the first segment of the
instrument ID", so
`src/exchange/ccxt_connector.py, at ASSET_CODE_LEG` names the separator and
`src/exchange/ccxt_connector.py, in _read_asset_sector_rows` reads the code off
the text before the first one.

```
instId XAAPL-USDT                  -> XAAPL
instId AAPL-USDT-SWAP              -> AAPL
instId AAPL-USD_UM_XPERP-310613    -> AAPL
instId BTC-USDT                    -> BTC
```

`src/exchange/ccxt_connector.py, at AssetSectorRecord` defaults `code_leg` to
the empty string, so Gate.io's and Bitget's rows read the field whole as
before. Both were driven again after the change.

```
gateio   5640 codes, 607 naming a family   identical to its own page
bitget   3789 codes, 3151 naming a family  identical to its own page
okx       687 codes, 311 naming a family   new
control  kraken   _published_asset_sectors answers None
control  coinbase _published_asset_sectors answers None
```

### Why the tickers had to stop being read

Twenty-seven markets read as forex and every one was a ticker collision. The
venue's own record names each one.

```
RON/EUR RON/USDC RON/USDT      Ronin, published Crypto, read as the Romanian leu
SCR/EUR SCR/USDC SCR/USDT      Scroll, published Crypto, read as the Seychellois rupee
AMD/USDT:USDT                  published Stocks, read as the Armenian dram
AMD/USD:USD-310711             the same company, dated
NOK/USDT:USDT                  Nokia, published Stocks, read as the Norwegian krone
USDT/EUR USDT/USD USDT/AED USDT/AUD USDT/BRL USDT/SGD USDT/TRY
USDC/EUR USDC/AUD USDC/BRL USDC/PLN USDC/SGD USDC/TRY USDC/USDT
USDC/USDT:USDT USD1/USDT USDS/USDT EURC/USDC
                               a dollar or euro stablecoin, published Crypto
```

### One code at a time, off the driven record

```
XAAPL -> stocks       AAPL -> stocks       NOK -> stocks       SPY -> stocks
PAXG  -> commodities  XAU  -> commodities  CL  -> commodities  H100 -> commodities
RON   -> ''           SCR  -> ''           BTC -> ''           USDT -> ''
control  NOTACODE -> absent from the record
```

### The recording after the change

Measured over all 4559 active markets the library loads, with the home
redirected and no order placed.

| Sector | Markets before | Markets after |
| --- | --- | --- |
| crypto | 1125 | 1013 |
| stocks | 0 | 400 |
| commodities | 14 | 21 |
| futures and perpetuals | 751 | 483 |
| indices | 0 | 0 |
| forex | 27 | 0 |
| options | 2642 | 2642 |

431 markets moved, and every move is named by where it came from.

| From | To | Markets |
| --- | --- | --- |
| futures_perps | stocks | 262 |
| crypto | stocks | 135 |
| forex | crypto | 23 |
| futures_perps | commodities | 7 |
| forex | stocks | 3 |
| forex | futures_perps | 1 |

The 135 are tokenised equity spot pairs and the 262 are equity contracts, so the
stocks sector gains its markets from two product lines at once. The seven that
reach commodities are the energy contracts, copper and the dated gold contracts,
which no list of precious metals can carry.

**The control, with the record blinded.** With every published `instCategory`
replaced by an empty string, 41 markets move and not 431. Those 41 are exactly
the 27 forex and 14 commodities rows the ticker heuristic had guessed, which
stop being guessed once the venue answers. So the 431 is a reading of OKX's
record and not of the reader.

```
record read      431 markets move
record blinded    41 markets move   crypto 1152, futures_perps 765, options 2642
```

### The eight rows the venue itself has not categorised

All eight are spot, all eight publish `instCategory ""`, and all eight carry the
venue's own `state: preopen`.

```
XFLY-USDT XAMC-USDT XBB-USDT XQNT-USDT XCGNX-USDT XFWDI-USDT XIONQ-USDT XINFQ-USDT
```

They record as crypto, which is what the venue answers for them today. No code
among the 4559 loaded markets is missing from the record: unmapped codes, 0.

### The record driven through the real connector method

`src/exchange/ccxt_connector.py, in _published_asset_sectors` was called on a
connector whose exchange handle is a public library instance, with no credential
and the home redirected.

```
_published_asset_sectors()   687 codes, 311 naming a family
_published_sector(published, {'base': 'NOTACODE'})  ''
_published_sector(None, {'base': 'XAAPL'})          None
```

One market at a time, through the same path.

```
XAAPL/USDT       before crypto         after stocks
AAPL/USDT:USDT   before futures_perps  after stocks
SPY/USDT:USDT    before futures_perps  after stocks
AMD/USDT:USDT    before forex          after stocks
CL/USDT:USDT     before futures_perps  after commodities
XAU/USDT:USDT    before commodities    after commodities
PAXG/USDT        before commodities    after commodities
RON/USDT         before forex          after crypto
USDT/EUR         before forex          after crypto
BTC/USDT         before crypto         after crypto
```

### The venue's own reclassification sits on its own change log

The 2026-04-22 entry, headed "Reclassification of instCategory for commodity
instruments" and marked a breaking change:

> The following instruments now return instCategory = 4 (Commodities) instead
> of 1 (Crypto): XAU-USDT-SWAP XAG-USDT-SWAP XPD-USDT-SWAP XPT-USDT-SWAP
> XCU-USDT-SWAP NG-USDT-SWAP CL-USDT-SWAP BZ-USDT-SWAP

`H100-USDT-SWAP` is the ninth swap publishing Commodities and is not on that
list, so it carried the number at listing.

## Row six, the order shape

`src/exchange/ccxt_connector.py, in declared_order_types` answers
`market and limit` for this venue, read off the library's own capability map.

### The cash market buy, which OKX answers no to

OKX's own order page makes the size unit a setting rather than a fixed rule.

> Order quantity unit setting for sz. base_ccy: Base currency, quote_ccy: Quote
> currency. Only applicable to SPOT Market Orders. Default is quote_ccy for buy,
> base_ccy for sell

**The venue's own default is a cash amount and that default never reaches an
order this program places.** `ccxt/okx.py, in create_order_request` reads
`defaultTgtCcy = self.safe_string(self.options, 'tgtCcy', 'base_ccy')` and then
sets `request['tgtCcy'] = tgtCcy` for every market that is neither a contract
nor margin, so the field always goes out explicitly. `options['tgtCcy']` reads
None on a fresh instance and
`src/exchange/ccxt_connector.py, at EXCHANGE_OPTIONS` sets nothing for this
venue, so the value is `base_ccy` and `sz` is
`self.amount_to_precision(symbol, amount)`, a unit count.

The request the library composes, read without credentials, for a market buy of
0.001 units at a price of 50000:

```
okx      {'instId': 'BTC-USDT', 'ordType': 'market', 'side': 'buy',
          'sz': '0.001', 'tdMode': 'cash', 'tgtCcy': 'base_ccy'}
control
bitget   {'symbol': 'BTCUSDT', 'orderType': 'market', 'side': 'buy',
          'size': '50', 'force': 'GTC'}
```

OKX's `sz` is the unit count. Bitget's `size` is the cash. The two separate on
the same call.

```
'okx' in CITED_CASH_MARKET_BUY   False   members binance, bitget, coinbase, gateio
market_buy_names_cash('XAAPL/USDT', 'okx')            False
whole_unit_buy_needs_limit('XAAPL/USDT', 'okx', WHOLE_UNITS)   False
control  the same two calls on bitget     True, True
control  the same two calls on coinbase   True, True
control  the same two calls on gateio     True, True
control  the same two calls on binance    True, True
control  the same two calls on kraken     False, False
control  a contract symbol on bitget      False
control  a fractional rule on bitget      False
```

So `src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` keeps its four
venues and gains none. The reading sits in the comment beside the set so the
next venue unit does not derive it again.

## Row seven, the variant

`src/trading/scrumming/sizing.py, in sector_variant` names a built variant for
every one of the six sectors.

```
crypto         Crypto Scrumming       built
stocks         Stock Scrumming        built
commodities    Commodity Scrumming    built
forex          Forex Scrumming        built
indices        Index Scrumming        built
futures_perps  Futures Scrumming      built
control  options   options Scrumming  NOT built
```

The options row is the control and it is also the behaviour: 2642 of the
venue's markets are options, `src/trading/ata_spm.py, at ASSET_CLASSES` omits
that class, and each market refuses before the connector.

## Row eight, the gate log

`src/core/log_paths.py, in gate_log_path` composes a distinct path per sector.

```
trade/gate/okx/crypto/gate.log          trade/gate/okx/indices/gate.log
trade/gate/okx/stocks/gate.log          trade/gate/okx/futures_perps/gate.log
trade/gate/okx/commodities/gate.log     trade/gate/okx/forex/gate.log
control  distinct paths   6
```

---

## The six points, per sector

| Sector | market list | order route | order shape | position and fill read | candles | bot variant |
| --- | --- | --- | --- | --- | --- | --- |
| crypto | 1013 spot markets | `POST /api/v5/trade/order` | `sz` in base units, `tgtCcy base_ccy` | `fetch_balance`, `fetch_order` | eleven granularities | Crypto Scrumming, built |
| stocks | 135 spot, 265 contract | the same route | the same, and 16 of 400 step in whole units | the same | the same | Stock Scrumming, built |
| commodities | 4 spot, 17 contract | the same route | the same, and 17 of 21 step in whole contracts | the same | the same | Commodity Scrumming, built |
| futures and perpetuals | 483 contracts, 182 dated | the same route | a contract count | the same | the same | Futures Scrumming, built |
| indices | **nothing** | not applicable | not applicable | not applicable | not applicable | Index Scrumming, built and unreached |
| forex | **nothing** | not applicable | not applicable | not applicable | not applicable | Forex Scrumming, built and unreached |

---

## The indices sector lists no OKX market, and the exposure is still reachable

No index number exists in the venue's own vocabulary at all, against a control
of 492 rows publishing Stocks. Nine index-fund tickers are listed and the venue
publishes each one as a stock.

```
SPY  QQQ  IWM  EWY  EWZ  SMH  SOXL  TQQQ  XLE
all nine, published instCategory   3
control  rows publishing Stocks   492
```

So the operator reaches the identical product under stocks. The indices row
stays on the screen and its empty market list is recorded here, because removing
a sector from a venue is the operator's decision.

---

## Forex — the absence, proven three ways

### The venue's own published refusal

OKX's own documentation names a Forex category and the venue publishes it on
nothing.

> 1: Crypto 3: Stocks 4: Commodities 5: Forex 6: Bonds "": Not available

```
instCategory == 5   0 of 2191 rows
control  instCategory == 3   492 of 2191 rows
```

This is a stronger refusal than a missing word. The door exists in the venue's
own list and the venue puts nothing behind it.

### The detours searched, and the reading that shut each one

```
another product type          all four the record carries were read; OPTION
                              adds no base code the four lack, because an
                              option's base is its underlying's code
the base and quote codes      27 markets read as forex and all 27 are
                              collisions; 2 have two national-currency legs and
                              the venue publishes both bases as Crypto
another product reaching the  the stablecoin pairs are the only currency-facing
same underlying               markets, and both legs are Crypto by the venue's
                              own record
a capability already in this  Kraken's twelve pairs with two national-currency
tree                          legs size through recorded_unit_rule today, so
                              the sizing path is not the obstacle
```

### A control proving the search could have found a route that does exist

```
spot pairs whose quote alone is a national currency      437
spot pairs whose two legs are both a national currency     2, and neither base
                                                           is a currency
rows publishing Stocks                                   492
rows publishing Commodities                               23
```

The same reader that answered 0 for Forex answered 437, 492 and 23 on the same
run. It could have found a currency pair if one existed.

---

## Step five, the arithmetic

The set the screen offers, against the set it can act on.

| Sector | Offered | Before | After | The difference the unit closed |
| --- | --- | --- | --- | --- |
| crypto | 1 | 1125 | 1013 | 112 markets left for the sector that owns them |
| stocks | 1 | 0 | 400 | the venue was offered and no market reached the sector |
| commodities | 1 | 14 | 21 | 7 markets, all energy, copper or dated gold |
| futures and perpetuals | 1 | 751 | 483 | 269 markets in the wrong sector |
| indices | 1 | 0 | 0 | nothing; the venue publishes no index product |
| forex | 0 | 27 | 0 | 27 collisions left a sector the venue does not serve |

---

## What was read

```
reading                               what it reported
4559 active markets, classified       431 moved sector
the same, with the record blinded      41 moved, the 41 the ticker had guessed
_published_asset_sectors, real path   687 base codes, 311 naming a family
gateio and bitget, driven again       5640/607 and 3789/3151, both identical
the order request the library made    sz a unit count, tgtCcy base_ccy
the venue's own host                  four real routes 200, an invented one 404
the venue's own refusal sets          neither gains the venue; two controls read
                                      as before
the surface, per sector               five sectors offer the venue, forex does
                                      not, and an invented id reaches none
the gate log                          six distinct paths
the sentence census on the manual     4391 sentences before, 4646 after, 0
                                      originals absent
```

### Controls on what the host answers

```
GET /api/v5/public/instruments?instType=SPOT       200, code "0", 1160 rows
GET /api/v5/public/not-a-real-route                404
GET /api/v5/public/instruments?instType=NOTATYPE   400
publicGetPublicInstruments() with no request       BadRequest 50014
```

### The archetypes the readings were taken with

Calibrated first, exit codes read directly.

```
coding_archetype  known_good.py 0          known_bad.py 1
coding_archetype  known_good.js 0          known_bad.js 1
gui_archetype     known_good_widget.py 0   known_bad_widget.py 1
gui_archetype     known_good_page.html 0   known_bad_page.html 1
docs_archetype    known_good.md 0          known_bad.md 1
docs_archetype    citation_good.md 0       citation_bad.md 0
```

The citation pair does not separate on the verdict. `citation_bad.md` reports
four H006 findings at MEDIUM and still exits 0, because the verdict trips on
HIGH. A green docs verdict is therefore not proof that a citation is sound, and
every citation on this page names a symbol rather than a line.

### No test covers this

`tests/` holds `conftest.py` and six Solidity files. The operator's 2026-09-06
directive removed 574 non-canon tests, so the archetypes are the verification
and no test belongs to this unit.

---

## What changed

```
src/exchange/ccxt_connector.py            AssetSectorRecord gains code_leg,
                                          ASSET_CODE_LEG names the separator,
                                          VENUE_ASSET_SECTOR_RECORDS gains the
                                          okx record, and
                                          _read_asset_sector_rows narrows the
                                          code by the separator
src/trading/scrumming/sizing.py           the comment beside
                                          CITED_CASH_MARKET_BUY records why
                                          this venue is not a member
src/gui/main_tabs/asset_class_surface.py  the okx row carries the venue's own
                                          category vocabulary and why indices
                                          lists no market
docs/manual/15-venue-compatibility.md     one add-only section, with the
                                          overtaken row quoted whole
docs/audits/                              this page
```

Nothing was deleted. The indices row stays on the surface and its empty market
list is recorded as the arithmetic above.

---

## What this page could not establish

No reading used a credential, so nothing here proves the venue accepts a live
order from this program. The 400 stocks markets and the 21 commodity markets
have never been recorded by a running build, because the recording is written on
connect and no OKX credential exists in this tree. And a resident of an approved
United States location holds an account with OKX INC. on `us.okx.com`, which no
venue id in this tree reaches, so every yes above is an order path on the global
company.

---

## Related pages

- [../../manual/15-venue-compatibility.md](../../manual/15-venue-compatibility.md)
- [../2026-10-10_bitget_wired_sectors/REPORT.md](../2026-10-10_bitget_wired_sectors/REPORT.md)
- [../2026-10-10_gateio_wired_six_sectors/REPORT.md](../2026-10-10_gateio_wired_six_sectors/REPORT.md)
- [../2026-10-07_venue_sector_readiness_matrix/REPORT.md](../2026-10-07_venue_sector_readiness_matrix/REPORT.md)
