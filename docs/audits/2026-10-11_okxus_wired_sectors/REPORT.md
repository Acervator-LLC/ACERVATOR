# OKX US Wired Across The Sectors It Serves

**Mode: Reference, with seven product files changed.**

This page covers issue #1192. It answers the eight connections of that issue's
wired-venue section for `okxus`, the OKX INC. entity a United States resident
holds an account with, establishes how that company requires an order to be
formatted in each sector it serves, names the bot variant each format demands,
and records what changed so each sector reaches an order.

**FALSIFICATION.** This page is wrong if a field named here is absent from OKX
US's own published specification, if a sector's order body accepts a field this
page calls refused, if the program's order call passes a field this page says it
omits, if an OKX US order the program now refuses turns out to be one the venue
would have accepted, if the asset category this page reads off the venue's own
`instCategory` field turns out to name something other than the sector, or if
the instrument endpoint on `us.okx.com` turns out to narrow to OKX INC's own
offering after all.

---

## The verdict, one row per sector

| Sector | Verdict | The cost, where there is one |
| --- | --- | --- |
| crypto | **yes** | nothing |
| stocks | yes-if | all 135 markets are Unified Tokenized Stocks and the product's own terms refuse a United States resident |
| commodities | **yes** | nothing |
| indices | **no** | the venue's own category vocabulary holds no index number |
| futures and perpetuals | **no** | the library's `okxus` loads spot alone, and OKX INC's Terms define a spot platform |
| forex | **no** | the venue names a Forex number and publishes it on no product of its own |

**No row carries an account refusal of a United States person.** OKX INC. is the
company a United States resident holds an account with, and its own Licenses
page excludes named states and territories rather than the country. One product
on one row does refuse him, and it is the tokenised stock.

---

## The eight connections

| # | The connection | Before | After | The symbol that answers it |
| --- | --- | --- | --- | --- |
| 1 | a connector exists and is registered | absent | answered | `src/exchange/ccxt_connector.py, at SUPPORTED_EXCHANGES` |
| 2 | offered under every sector it serves | absent | answered, four offered | `src/gui/main_tabs/asset_class_surface.py, at EXTRA_VENUE_CLASSES` |
| 3 | the operator can enter its credentials | absent on both screens | answered on both | `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` |
| 4 | a Start press builds its connector | absent | answered, the crypto path | `src/gui/main_window.py, in _connect_exchange_for_bot` |
| 5 | its market rules record on connect | absent | answered, 1152 rows | `src/exchange/market_rules_store.py, in record_venue` |
| 6 | its orders carry the shape the venue publishes | unreached | answered, a unit count on both sides | `src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` |
| 7 | a built variant selects for it | unreached | answered, all four sector variants built | `src/trading/scrumming/sizing.py, at VARIANTS_BUILT` |
| 8 | its gate decisions log under it | unreached | answered, four distinct paths | `src/core/log_paths.py, in gate_log_path` |

Rows 1 to 5 all read absent before this unit for one reason: the id was in
neither registry, and `CCXTConnector("okxus")` raised `Unsupported exchange
'okxus'`.

---

## Row one, the connector

ccxt 4.5.85 carries three OKX ids, one per operating company, and this tree
registered one.

```
'okx'   in ccxt.exchanges True   hostname www.okx.com   registered before: True
'okxus' in ccxt.exchanges True   hostname us.okx.com    registered before: False
'myokx' in ccxt.exchanges True   hostname eea.okx.com   registered before: False
```

`okxus` subclasses `okx` in the library. It names its own hostname, its own
documentation host at `app.okx.com`, and three capability flags its parent sets
differently.

```
okxus  has['spot'] True   has['swap'] False  has['future'] False  has['option'] False
okxus  options['fetchMarkets']['types'] == ['spot']
CONTROL okx    has['spot'] True   has['swap'] True   has['future'] True   has['option'] True
CONTROL myokx  has['spot'] True   has['swap'] True   has['future'] False  has['option'] False
```

`src/exchange/ccxt_connector.py, at SUPPORTED_EXCHANGES` now holds `okxus`, and
`src/exchange/ccxt_connector.py, at PASSPHRASE_EXCHANGES` holds it too, because
the library requires `apiKey`, `secret` and `password` on this id as it does on
its parent.

```
CCXTConnector('okxus')  before: raised ValueError "Unsupported exchange 'okxus'"
CCXTConnector('okxus')  after:  built, exchange_id okxus, display_name Okxus
CONTROL CCXTConnector('okx')  built in both runs
```

---

## Row one, continued: which company, and which places it will not serve

OKX's own
[Terms of Service](https://www.okx.com/help/360021813691) clause 3.1 names the
company:

> OKX INC., a Delaware corporation ("OKX US"), which operates under the OKX
> brand, for Users who are residents of one of OKX US's approved operating
> locations within the United States and its territories.

OKX's own
[U.S. Licenses page](https://www.okx.com/en-us/help/us-licenses), last updated
15 September 2026:

> The OKX digital asset trading platform for United States customers is provided
> by OKX INC.

> OKX INC. does not provide services to residents of the following states and
> territories at this time: New York, American Samoa, Guam, Northern Mariana
> Islands, and the U.S. Virgin Islands.

That is five named places, and it names a state rather than the country. It is
therefore neither an account refusal nor an address refusal, and neither set
gains a row.

```
'okxus' in US_IP_BLOCKED_EXCHANGES          False
'okxus' in US_ACCOUNT_RESTRICTED_EXCHANGES  False
'okxus' in US_RESTRICTED_EXCHANGES          False
CONTROL 'gateio'  in US_ACCOUNT_RESTRICTED_EXCHANGES  True
CONTROL 'binance' in US_IP_BLOCKED_EXCHANGES          True
```

OKX INC's own
[U.S. Terms of Service](https://www.okx.com/en-us/help/terms-of-service-us),
last updated 16 September 2026, section 1.1, Trading Services, defines what the
company sells:

> we provide online digital asset trading account services and a platform for
> spot trading digital assets ... may facilitate margin lending

The document names no future, no perpetual and no option anywhere.

---

## The reading every count on this page depends on

**The instrument endpoint does not narrow to the company.** It answers the
exchange's catalogue on every host the company owns.

```
GET /api/v5/public/instruments   us.okx.com   eea.okx.com   www.okx.com
                      SPOT            1152          1152          1160
                      MARGIN           266           266           266
                      SWAP             500           500           500
                      FUTURES          265           265           265

us.okx.com id set == eea.okx.com id set   SPOT True  MARGIN True  SWAP True  FUTURES True
us.okx.com id set == www.okx.com id set   SPOT False MARGIN True  SWAP True  FUTURES True
```

Two separate operating companies, two separate hostnames, one identical
instrument id set on all four product types. The eight ids the global host holds
beyond the other two are the eight the OKX unit recorded as uncategorised and
pre-open: `XAMC-USDT`, `XBB-USDT`, `XCGNX-USDT`, `XFLY-USDT`, `XFWDI-USDT`,
`XINFQ-USDT`, `XIONQ-USDT` and `XQNT-USDT`.

**That eight-row difference is the control on the comparison.** It can see a
difference when one exists, so the identical United States and European lists
are a reading and not a failed fetch.

So every market count below is the exchange's catalogue read on OKX INC's host.
What the account may trade is read from OKX INC's own pages, and never from the
count. The pages are quoted above and in the tokenised stock section below.

```
GET https://us.okx.com/api/v5/public/time                      200
GET /api/v5/public/instruments with no instType     code 50014 "Parameter instType can not be empty."
GET /api/v5/public/instruments?instType=NOTATYPE    code 51000 "Parameter instType error"
GET /api/v5/public/instruments?instType=OPTION      code 50015 "Either parameter uly or instFamily is required"
```

---

## Row two, the sectors

`src/gui/main_tabs/asset_class_surface.py, at EXTRA_VENUE_CLASSES` gains the row
naming stocks, commodities and indices. Crypto arrives from the registry, so the
venue reads under four sectors.

```
venue_classes('okxus')  before: empty       after: commodities, crypto, indices, stocks
CONTROL venue_classes('okx')       commodities, crypto, futures_perps, indices, stocks
CONTROL venue_classes('notavenue') empty
```

Futures and perpetuals is absent because the connector loads no contract, and
forex is absent because the venue publishes no currency. Both are proven below.

---

## Row three, the credential form

No separate repair. `src/gui/main_tabs/settings_dialog_surface.py, in
exchange_status_rows` reads `venues_for_class`, and
`src/gui/main_tabs/init_wizard_surface.py, in exchange_ids` reads
`known_venues`, which `venues_for_class` narrows. One superset serves both
screens, so neither can hold a venue the other does not.

| Sector | Venues offered, before | After | `okxus` offered | Add form rows | `okxus` in the form |
| --- | --- | --- | --- | --- | --- |
| crypto | 21 | 22 | yes | 22 | yes |
| stocks | 20 | 21 | yes | 21 | yes |
| commodities | 17 | 18 | yes | 18 | yes |
| indices | 14 | 15 | yes | 15 | yes |
| futures and perpetuals | 16 | 16 | no | 16 | no |
| forex | 8 | 8 | no | 8 | no |

```
known_venues()            before 25   after 26
wizard exchange_ids()     after 26, okxus present
CONTROL an invented venue id in any of them   absent
```

The venue asks for a passphrase, which both screens read off
`src/exchange/ccxt_connector.py, at PASSPHRASE_EXCHANGES`.

---

## Row four, the Start press

`src/gui/main_window.py, in _connect_exchange_for_bot` reads
`broker_connector_class` first and takes the crypto path for every venue it
answers nothing for. `okxus` holds no `BrokerBase` subclass, so the press builds
a `CCXTConnector`, which it now can. `src/exchange/ccxt_connector.py, at
PREFLIGHT_URLS` gains the company's own time route, read as 200 above, so the
pre-flight tests the company's own host and not the global one.

---

## Row five, the recording

`src/exchange/ccxt_connector.py, at VENUE_ASSET_SECTOR_RECORDS` gains this
venue's own record. OKX US publishes the same field with the same vocabulary,
and the requests differ.

The company's own
[API reference](https://app.okx.com/docs-v5/en/), which states
`REST: https://us.okx.com` for production trading, carries the vocabulary:

> `1`: Crypto `3`: Stocks `4`: Commodities `5`: Forex `6`: Bonds `""`: Not
> available

The record asks for `SPOT` alone, because the library's `okxus` loads spot
alone. Asking for a product type the connector never loads would add asset codes
no market reads.

```
markets ccxt's okxus loads      1152, active 1152, every one type 'spot'
contract rows among them           0
distinct base codes among them   413
MARGIN first-leg codes outside that set   0
CONTROL SWAP codes outside it    265   AAPL, ADBE, AMD, AMZN, ANTHROPIC ...
CONTROL FUTURES codes outside it 109
```

What the venue publishes, per product type:

| `instCategory` | SPOT | MARGIN | SWAP | FUTURES |
| --- | --- | --- | --- | --- |
| 1, Crypto | 1013 | 172 | 301 | 182 |
| 3, Stocks | 135 | 92 | 190 | 75 |
| 4, Commodities | 4 | 2 | 9 | 8 |
| 5, Forex | 0 | 0 | 0 | 0 |
| 6, Bonds | 0 | 0 | 0 | 0 |
| no category at all | 0 | 0 | 0 | 0 |

Every row on all four types carries `state: live`.

### The base code, and why this record needs no separator

OKX US publishes a base code field on spot and publishes none on a contract.

```
baseCcy non-empty   SPOT 1152 of 1152   MARGIN 266 of 266   SWAP 0 of 500   FUTURES 0 of 265
```

So `src/exchange/ccxt_connector.py, at ASSET_CODE_LEG` exists for exactly the
product types this record does not ask for. The record reads `baseCcy` and names
no `code_leg`.

**Control, the two readings against each other.**
`src/exchange/ccxt_connector.py, in CCXTConnector._read_asset_sector_rows`, the
production reader, was driven twice over the same 1152 rows.

```
code_key='baseCcy',  no code_leg          413 codes mapped
code_key='instId',   code_leg='-'         413 codes mapped, map identical: True
spot rows where the two disagree          0 of 1152
```

Both readings are true here, and `baseCcy` is the field the venue publishes for
the purpose.

### What the record answers, driven end to end

Read through the real connector method with no credential and the home
redirected to a scratch tree:

```
_published_asset_sectors()   413 base codes, 111 naming a family
  stocks       109 codes
  commodities    2 codes
  published and empty  302 codes
```

### What the recording holds

`record_venue` was driven over all 1152 markets into a scratch store, and
`recorded_classes` read back:

```
rows written   1152
crypto         1013   946 stepping in fractions, 67 in whole units
stocks          135   all stepping in fractions
commodities       4   all stepping in fractions
CONTROL a symbol the venue does not list   read False
CONTROL okx rows in the same store            0
```

`market_unit_rule` and `recorded_unit_rule` agreed on every one of the 1152
rows, so no sector row fires behind the venue's own step.

### What the venue's own record moves

Measured over the 1152 markets the connector loads, against what the tickers
alone answer:

| Sector | The tickers alone | The venue's own record |
| --- | --- | --- |
| crypto | 1125 | 1013 |
| stocks | **0** | **135** |
| commodities | 4 | 4 |
| forex | **23** | **0** |

158 markets move, and the venue's own record names every one.

```
crypto -> stocks   135
forex  -> crypto    23
```

**Control, the record blinded.** With every published category replaced by an
empty string, 27 markets move and not 158. Those 27 are the 23 forex and 4
commodities rows the ticker heuristic had guessed, which stop being guessed once
the venue answers. So the 158 is a reading of OKX US's record and not of the
instrument.

**Control, the map's coverage.** Every one of the 413 base codes among the 1152
loaded markets has a row in the record. Unmapped codes: 0.

**Control, one code at a time.**

```
XAAPL -> stocks       XAMZN -> stocks
PAXG  -> commodities  XAUT  -> commodities
BTC   -> ''           USDT  -> ''           NOTACODE -> absent
```

---

## The tokenised stock refuses the account that holds the venue

All 109 stock base codes carry an `X` prefix, which is the venue's own naming
for its Unified Tokenized Stock product. OKX's own
[listing page](https://www.okx.com/en-us/help/okx-to-list-unified-tokenized-stocks-for-spot-trading)
states each asset is "named by an uppercase 'X' prefixed to the stock ticker
(e.g., XAAPL, XTSLA)".

```
category 3 markets 135, distinct codes 109, codes beginning with X  109 of 109
CONTROL category 1 codes beginning with X   XCH XDP XLM XPL XRP XTZ
category 3 quote currencies   USDC, USDT
```

The prefix alone is not the discriminator — six crypto codes carry it — and the
venue's own category number is.

OKX's
[Unified Tokenized Stock Trading Terms and Conditions](https://www.okx.com/en-us/help/unified-tokenized-stock-trading-terms-and-conditions),
effective 15 July 2026:

> you are not a U.S. Person as defined under Reg S

> you are not located in, incorporated in, or current resident of the United
> States

> Resale or transfer of UTS to U.S. Persons or within the United States is
> prohibited.

An OKX INC. account holder is a United States resident by the Licenses page's
own definition of the company. So the 135 markets the stocks sector holds on
this venue are products the venue's own terms forbid that account to hold.

**The recording still names them stocks, because that is the sector they are
in.** Nothing in this program refuses a sector, and this unit builds no
mechanism for it. Whether a bot opens in that sector is the operator's call, and
it is the one open answer this venue leaves.

OKX also publishes a jurisdiction note on the perpetual form of the same
exposure, on its own page titled "Stock perpetuals":

> Access to stock perpetuals may be restricted or prohibited in certain
> jurisdictions, including (but not limited to) the United States.

---

## Row six, the order shape

A spot market buy on this venue carries a unit count, not a cash amount. The
library writes the venue's own size-unit field on every spot order with its own
default of the base currency, and
`src/exchange/ccxt_connector.py, at EXCHANGE_OPTIONS` sets nothing against it for
this venue.

Read through the library's own request builder, with a placeholder credential
assigned after the markets loaded, and never sent:

```
okxus  market buy   {'instId': 'BTC-USDT', 'side': 'buy', 'ordType': 'market',
                     'sz': '0.001', 'tdMode': 'cash', 'tgtCcy': 'base_ccy'}
okxus  market sell  {'instId': 'BTC-USDT', 'side': 'sell', 'ordType': 'market',
                     'sz': '0.001', 'tdMode': 'cash', 'tgtCcy': 'base_ccy'}
okxus  one share    {'instId': 'XAAPL-USDT', 'side': 'buy', 'ordType': 'market',
                     'sz': '1', 'tdMode': 'cash', 'tgtCcy': 'base_ccy'}
CONTROL okx         'sz': '0.001', 'tgtCcy': 'base_ccy'
CONTROL bitget      {'symbol': 'BTCUSDT', 'orderType': 'market', 'side': 'buy',
                     'size': '50'}
```

All three calls asked for 0.001 units at a price of 50000. OKX US's `sz` is the
unit count. Bitget's `size` is the cash. The readings separate on the same call.

```
'okxus' in CITED_CASH_MARKET_BUY                           False
market_buy_names_cash('BTC/USDT', 'okxus')                 False
market_buy_names_cash('XAAPL/USDT', 'okxus')               False
whole_unit_buy_needs_limit('XAAPL/USDT','okxus','whole')   False
CONTROL the same two calls on bitget, coinbase, gateio, binance   True, True
CONTROL the same two calls on okx and kraken                      False, False
```

`src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` keeps its four
venues and the reading sits in the comment beside the set, so the next venue
unit does not derive it again.

`src/exchange/ccxt_connector.py, in declared_order_types` answers market and
limit for this venue, off its own capability map.

---

## Row seven, the variant

Every sector this venue serves selects a variant
`src/trading/scrumming/sizing.py, at VARIANTS_BUILT` holds.

```
crypto       -> Crypto Scrumming      built
stocks       -> Stock Scrumming       built
commodities  -> Commodity Scrumming   built
indices      -> Index Scrumming       built
CONTROL options -> options Scrumming  not built
```

---

## Row eight, the gate log

`src/core/log_paths.py, in gate_log_path` composes one path per sector, and the
four served sectors answer four distinct paths.

```
trade/gate/okxus/crypto/gate.log
trade/gate/okxus/stocks/gate.log
trade/gate/okxus/commodities/gate.log
trade/gate/okxus/indices/gate.log
CONTROL trade/gate/okx/crypto/gate.log
```

---

## The six points, per sector

| Point | crypto | stocks | commodities | indices |
| --- | --- | --- | --- | --- |
| market list | `load_markets`, 1013 rows | the same load, 135 rows | the same load, 4 rows | nothing |
| order route | `CCXTConnector.place_order` on the company's own host | the same | the same | nothing |
| order shape | `sz` a unit count, `tgtCcy` base | the same | the same | nothing |
| position and fill read | `fetch_balance` and `fetch_my_trades` | the same | the same | nothing |
| candles | `fetch_ohlcv`, eleven granularities | the same | the same | nothing |
| bot variant | Crypto Scrumming, built | Stock Scrumming, built | Commodity Scrumming, built | Index Scrumming, built and unreached |

One order path serves all four, because OKX US publishes one order endpoint and
one product type.

---

## The indices sector lists no OKX US market, and the exposure is still reachable

`EXTRA_VENUE_CLASSES` offers this venue under indices and its recording answers
no market there, the same shape Bitget and OKX carry. Eight index-fund tickers
are listed and every one publishes Stocks.

```
XSPY 3   XQQQ 3   XIWM 3   XEWY 3   XSMH 3   XSOXL 3   XTQQQ 3   XXLE 3
CONTROL XEWZ        absent from this host
CONTROL rows naming Stocks   135
```

No index value exists in OKX US's own vocabulary at all, so the sector is a
proven absence and not an unread one.

---

## Futures and perpetuals, the absence, proven

The library's own `okxus` loads spot alone, so 0 of the 1152 markets it answers
is a contract. The detours searched, and the reading that shut each one:

```
another endpoint      us.okx.com answers SWAP 500 and FUTURES 265 — shut by the
                      control showing eea.okx.com answers an identical set, so
                      the endpoint names the catalogue and not the company
another API version   us.okx.com serves v5 alone; no other version is published
another doc host      app.okx.com/docs-v5 names all five instTypes and EVENTS,
                      a verbatim copy of the global reference
the page's script     us.okx.com/markets/prices and app.okx.com/fees both answer
                      302 to www.okx.com, so the United States hosts serve no
                      separate catalogue page to read
another product       no other OKX INC. product reaches a contract
a capability in-tree  all six sector variants are built, so no sector is shut by
                      this platform
a different account   OKX INC's own Terms 1.1 name one platform and one set of
                      services, spot trading and margin lending
```

The venue's own published statement is the scope clause quoted above, which
names no derivative anywhere in the document. The control proving the search
could have found a route that exists: the same sweep found 1152 spot and 266
margin rows on the same host, in the same run.

**What this does not establish:** whether OKX INC. would open a derivative
product to a United States account in future. No OKX INC. page publishes one
today.

---

## Forex, the absence, proven

```
rows carrying instCategory 5, across all four product types   0 of 2183
CONTROL rows carrying instCategory 3                        492 across the four
spot pairs whose two ticker legs are both a national currency  27
  of those, pairs whose base OKX US publishes as a currency     0
CONTROL spot pairs whose quote alone is a national currency   1119
```

`RON/EUR` is Ronin and `SCR/EUR` is Scroll; the other 25 are dollar or euro
stablecoins. OKX US publishes `instCategory 1`, Crypto, for every one. The
venue's own vocabulary names a Forex number and the venue publishes it on
nothing.

---

## Step five, the arithmetic

| Sector | Offered before | Offered after | Markets it can act on | The difference |
| --- | --- | --- | --- | --- |
| crypto | 21 | 22 | 1013 | one venue the operator could not reach before |
| stocks | 20 | 21 | 135, every one refused to a United States resident by the product's own terms | 135 markets the operator should not open |
| commodities | 17 | 18 | 4 | one venue the operator could not reach before |
| indices | 14 | 15 | 0, and the venue publishes none | one venue offered with no product of its own |
| futures and perpetuals | 16 | 16 | 0 | 0 |
| forex | 8 | 8 | 0 | 0 |

`known_venues` moves from 25 to 26.

---

## The three venues before this one did not move

Driven in both trees, the base tree and this unit's worktree, in the same run:

| Venue | Codes mapped | Naming a family | Markets by sector | `venue_classes` | Cash buy | Timeframes |
| --- | --- | --- | --- | --- | --- | --- |
| okx | 687 | 311 | commodities 21, crypto 1013, futures_perps 483, options 2644, stocks 400 | five | no | 11 |
| gateio | 5640 | 607 | commodities 20, crypto 2031, forex 6, futures_perps 619, indices 18, options 3418, stocks 565 | six | yes | 9 |
| bitget | 3789 | 3151 | commodities 12, crypto 571, futures_perps 534, stocks 3141 | five | yes | 11 |

Every figure is identical in the two trees. The only readings that moved are the
four offered counts and `known_venues`, which are this unit's own arithmetic.
`CITED_CASH_MARKET_BUY` reads `binance, bitget, coinbase, gateio` in both.

---

## What was read

Every reading was taken in a process whose home directory was redirected to a
scratch tree before any module under `src/` was imported. No credential was
sent, no account was opened, and no order was placed, priced or previewed. Only
OKX US's own public, credential-free endpoints and its own published pages were
read.

The archetypes were calibrated first, and the first calibration was wrong. A
shell helper printed `exit 0` for all twelve fixtures, because it expanded a
command substitution inside the same `echo` that read the exit code. Read one
file at a time:

```
coding_archetype  known_good.py          0   known_bad.py           1
coding_archetype  known_good.js          0   known_bad.js           1
gui_archetype     known_good_widget.py   0   known_bad_widget.py    1
gui_archetype     known_good_page.html   0   known_bad_page.html    1
docs_archetype    known_good.md          0   known_bad.md           1
docs_archetype    citation_good.md       0   citation_bad.md        0
```

Eleven of twelve separate. The citation pair does not separate on the verdict:
H006 fires at MEDIUM and the verdict trips on HIGH, so every citation on this
unit's pages is checked by symbol instead.

The sentence census on the manual page carries its own two-sided control. The
first run of it reported 21 originals absent on an append-only change, because
the committed page was decoded in the machine's locale encoding and every
em-dash and curly quote was mangled. Decoded as UTF-8:

```
CENSUS                                        before 4646  after 4871  originals absent 0
CONTROL the committed page against itself     before 4646  after 4646  originals absent 0
CONTROL one committed sentence reworded       before 4646  after 4871  originals absent 1
CONTROL two new sentences reworded            before 4871  after 4871  originals absent 2
```

---

## What changed

| File | The change |
| --- | --- |
| `src/exchange/ccxt_connector.py` | `okxus` registered, its passphrase, its pre-flight URL, and its own `instCategory` record |
| `src/gui/main_tabs/asset_class_surface.py` | the three extra sectors, with the comment naming what the venue publishes and what its product terms refuse |
| `src/trading/scrumming/sizing.py` | the comment beside `CITED_CASH_MARKET_BUY` records why this venue is not a member |
| `src/exchange/timeframes.py` | the row the module's own invariant requires of every registered id |
| `src/gui/main_tabs/api_tester_tab_surface.py` | the probe host |
| `src/gui/widgets/api_tester_tab.py` | the same probe host, on the widget's own map |
| `src/exchange/exchange_chart_urls.py` | the chart row |
| `docs/manual/15-venue-compatibility.md` | add-only, with the sentence census above |

The last four are connections the registration itself would otherwise break. A
registered id with no timeframe row falls to a permissive fallback the module's
own docstring says no registered id reaches. A registered id with no probe host
composes a hostname that resolves in DNS and answers nothing on port 443, so the
API Tester would report OKX US unreachable while the company's own host answers
200. A registered id with no chart row draws a cell that opens nothing; the
company's own trade path answers 302 to the same path on the global host, so the
row lands on the chart of the same market.

Nothing was deleted.

---

## What this page could not establish

Three things, named.

**Whether the account accepts a live order.** No reading used a credential.

**Which of the 1152 markets a United States account may trade.** The instrument
endpoint does not narrow to the company, and OKX INC. publishes no narrower
market list on a credential-free endpoint. Every market count here is the
exchange's catalogue read on the company's host.

**Whether a bot should open in the stocks sector.** The product's own terms
refuse a United States resident. The program has no sector-level refusal, this
unit built none, and the answer is the operator's.

---

## Related pages

- [The venue-and-sector page](../../manual/15-venue-compatibility.md)
- [The global company's report](../2026-10-10_okx_wired_sectors/REPORT.md)
- [Bitget](../2026-10-10_bitget_wired_sectors/REPORT.md)
- [Gate.io](../2026-10-10_gateio_wired_six_sectors/REPORT.md)
