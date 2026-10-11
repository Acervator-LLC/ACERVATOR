# Bitfinex Wired Across The Sectors It Serves

**Mode: Reference, with four product files changed.**

This page covers issue #1192. It answers the eight connections of that issue's
wired-venue section for `bitfinex`, establishes how the venue requires an order
to be formatted in each sector it serves, names the bot variant each format
demands, and records what changed so each sector reaches an order.

**FALSIFICATION.** This page is wrong if a field named here is absent from
Bitfinex's own published specification, if a sector's order body accepts a field
this page calls refused, if the program's order call passes a field this page
says it omits, if a bitfinex order the program now refuses turns out to be one
the venue would have accepted, if the product name this page reads off the
venue's own announcement feed turns out to name something other than the sector,
or if a credential-free bitfinex endpoint turns out to publish an asset category
after all.

Every reading was taken on 2026-10-10 against `api-pub.bitfinex.com`,
`api.bitfinex.com`, `docs.bitfinex.com`, `support.bitfinex.com` and
`www.bitfinex.com`. No credential was used, no order was placed or previewed,
and the home directory was redirected for every drive.

---

## The verdict, one row per sector

| Sector | Verdict | The cost, where there is one |
| --- | --- | --- |
| crypto | **yes** | nothing. 189 markets |
| commodities | **yes** | nothing. 9 markets |
| forex | **yes** | nothing. 4 markets |
| indices | **yes** | nothing. 10 markets |
| futures and perpetuals | **yes** | nothing. 76 markets |
| stocks | **no** | the venue lists no company share; its 28 securities pairs trade on the Bitfinex Securities platform, by its own words "not the Bitfinex exchange" |

**Every row carries an account refusal of a United States person.** Bitfinex's
own U.S. Person FAQ states "No U.S. Person may directly or indirectly use any of
the Services or the Site." The order paths below are what the program can form;
whether this operator's account may use them is settled by the venue, not by
this page.

---

## The eight connections

| # | The connection | Before | After | The symbol that answers it |
| --- | --- | --- | --- | --- |
| 1 | a connector exists and is registered | answered | unchanged | `src/exchange/ccxt_connector.py, at SUPPORTED_EXCHANGES` |
| 2 | offered under every sector it serves | four sectors | five | `src/gui/main_tabs/asset_class_surface.py, at EXTRA_VENUE_CLASSES` |
| 3 | the operator can enter its credentials | answered, key and secret | unchanged | `src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` |
| 4 | a Start press builds its connector | answered, the ccxt path | unchanged | `src/gui/main_window.py, in _connect_exchange_for_bot` |
| 5 | its market rules record on connect | **raised**, 0 rows | 288 rows | `src/exchange/market_rules_store.py, in record_venue` |
| 6 | its orders carry the shape the venue publishes | unreached | a unit count on both sides | `src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` |
| 7 | a built variant selects for it | unreached | five sector variants, all built | `src/trading/scrumming/sizing.py, at VARIANTS_BUILT` |
| 8 | its gate decisions log under it | unreached | five distinct paths | `src/core/log_paths.py, in gate_log_path` |

Rows 5 to 8 all read absent before this unit for one reason, and it is row 5.

---

## Row five, the recording that never happened

`CCXTConnector("bitfinex").get_markets()` raised on the previous build:

```
AttributeError: 'list' object has no attribute 'get'
  src/exchange/ccxt_connector.py, in futures_asset_types
  called from src/exchange/ccxt_connector.py, in market_asset_class
  called from src/exchange/ccxt_connector.py, in get_markets
```

Bitfinex serves its market metadata as arrays. Every one of its 288 market
records carries `info` as a list, so a reader that calls `.get` on `info`
without checking its shape raises on every market of the venue.

```
market['info'] shapes, measured per venue
bitfinex   288 of 288 list
gemini     345 of 345 list
kraken    1460 of 1460 dict
```

Nine functions in that module read `info`. Six already guarded the shape and
three did not.

| Function | Guarded before | Raised on bitfinex |
| --- | --- | --- |
| `quote_step` | yes | no |
| `contract_units` | yes | no |
| `extended_session_market` | yes | no |
| `market_session` | yes | no |
| `equity_size_shapes` | yes | no |
| `tradability_size_shapes` | yes | no |
| `futures_asset_type` | **no** | 288 of 288 |
| `futures_asset_types` | **no** | 288 of 288 |
| `record_price` | **no** | 288 of 288 |

`src/exchange/market_inspector_fetcher.py, in trading_products` and
`in trading_rules` read the same field the same way, so a bitfinex connector in
the fleet also emptied the Market Inspector's product and rule tables.

### The two-sided control on the guard

Driven in one run, on the unmodified file and then on the guarded one.

| Instrument | Before the guard | After the guard |
| --- | --- | --- |
| `futures_asset_type` over 288 bitfinex markets | raised 288 | raised 0, answered 0 |
| `futures_asset_types` over 288 bitfinex markets | raised 288 | raised 0, answered 0 |
| `record_price` over 288 bitfinex markets | raised 288 | raised 0, answered 0 |
| `trading_products` with a bitfinex connector | `AttributeError` | 82 bases, 82 trading |
| `trading_rules` with a bitfinex connector | `AttributeError` | 82 bases |
| the same five over 1460 kraken markets | raised 0 | raised 0, same answers |
| `get_markets` | `AttributeError` | 288 markets, 288 rows recorded |

Kraken is the positive control: its market records are mappings, so the guard
cannot fire there, and no answer of any of the five moved. The guard returns the
same empty answer a mapping with no `future_product_details` already returned,
so no Coinbase reading changes either - all three functions answered 0 of 288
bitfinex markets and 0 of 1460 kraken markets, because neither venue publishes
Coinbase's label.

---

## Row one, the connector

`src/exchange/ccxt_connector.py, at SUPPORTED_EXCHANGES` already held
`"bitfinex": "bitfinex"`, and `src/exchange/ccxt_connector.py, at
PREFLIGHT_URLS` already held
`https://api-pub.bitfinex.com/v2/platform/status`. `CCXTConnector("bitfinex")`
builds and `sync_connect` opens a session with key and secret alone;
`src/exchange/ccxt_connector.py, at PASSPHRASE_EXCHANGES` does not hold the id
and the venue asks for no passphrase.

---

## The venue refuses a United States person

This is reading one of four the unit was sent to settle, and it is the Gate.io
and Bitget shape rather than the OKX shape.

Bitfinex's own
[U.S. Person FAQ](https://support.bitfinex.com/hc/en-us/articles/115003461254-U-S-Person-Frequently-Asked-Questions-FAQ):

> "'U.S.' refers to 'United States' and includes the several states of the
> United States and the District of Columbia. According to the Bitfinex Terms of
> Service, if you are a United States Citizen or United States Resident, you
> will not be able to use the Bitfinex platform."

> "Note: This includes if you are a U.S. permanent resident or if you are an
> individual that holds a U.S. passport."

> "No U.S. Person may directly or indirectly use any of the Services or the
> Site. If you are a U.S. Person, you are strictly prohibited from opening an
> account on Bitfinex."

Its Securities arm refuses the same person on its own terms. The
[restrictions article](https://support.bitfinex.com/hc/en-us/articles/4405999041945-Bitfinex-Securities-Restrictions-Prohibited-Persons-and-Prohibited-Jurisdictions)
opens the Prohibited Person List with "Any U.S. Person" and states such a person
"will not be able ... to trade securities at Bitfinex Securities."

**It is an account refusal and not an address block.** Every bitfinex public
endpoint used by this report answered from this machine, including the
pre-flight URL, the whole configuration set, the market load and the
announcement feed. So
`src/exchange/ccxt_connector.py, at US_ACCOUNT_RESTRICTED_EXCHANGES` gains the
id and `src/exchange/ccxt_connector.py, at US_IP_BLOCKED_EXCHANGES` does not.

The Terms of Service document itself could not be read. `www.bitfinex.com` is a
client-rendered application and the legal text is absent from the served markup:
`https://www.bitfinex.com/legal/exchange/terms/` answered 200 with 112,312 bytes
carrying 1,924 characters of text, all of it navigation, and zero occurrences of
"United States", "U.S. Person", "prohibited" or "restricted". The detours
searched were a request carrying the `RSC` header, which returned the identical
bytes; `cs.bitfinex.com`, which answered 403; and the help centre, which carries
the FAQ quoted above and cites the Terms directly. The FAQ is bitfinex's own
page and it states the refusal in the venue's own words, so the refusal is
grounded and the clause number is not.

---

## Bitfinex publishes no asset category, so no sector record is added

This is reading two, and the answer is nothing plus the count that shows it.

Bitfinex's own
[configuration reference](https://docs.bitfinex.com/reference/rest-public-conf)
documents fifteen keys. Eight are maps - `sym`, `label`, `unit`, `undl`, `pool`,
`explorer`, `tx:fee` and `tx:method` - five are lists, two are info keys. Not
one carries an asset category, an asset class, a product type or a sector.

| Key asked for | Rows served |
| --- | --- |
| `pub:list:currency` | 255 |
| `pub:list:pair:exchange` | 194 |
| `pub:list:pair:margin` | 76 |
| `pub:list:pair:futures` | 94 |
| `pub:list:pair:securities` | 28 |
| `pub:list:currency:securities` | 14 |
| `pub:list:currency:margin` | 47 |
| `pub:list:currency:paper` | 31 |
| `pub:map:currency:label` | 155 |
| `pub:map:currency:undl` | 95 |
| `pub:map:currency:pool` | 69 |
| `pub:map:currency:sym` | 83 |
| `pub:info:pair` | 194 |
| `pub:info:pair:futures` | 94 |
| `pub:map:currency:cat` | **0** |
| `pub:map:currency:type` | **0** |
| `pub:list:currency:index` | **0** |
| `pub:list:pair:index` | **0** |
| `pub:info:pair:securities` | **0** |

Fourteen documented keys answered rows and five invented keys answered nothing,
which is the control: the reader can tell a key that exists from one that does
not, so the five zeros are a reading and not a failed fetch.

### A record would cost the venue two sectors

`src/exchange/ccxt_connector.py, in market_asset_class` reads
`PRECIOUS_METAL_CODES` and `FIAT_CURRENCY_CODES` only while its `published`
argument is None. Handing it any mapping, however empty, switches that reading
off.

```
XAUT/USD    published None -> commodities      published {} -> crypto
EUR/USDT    published None -> forex            published {} -> crypto
```

Those two readings are the whole of bitfinex's commodities and forex sectors, so
an `AssetSectorRecord` for this venue would be strictly worse than none.
`src/exchange/ccxt_connector.py, at VENUE_ASSET_SECTOR_RECORDS` keeps its four
rows and records the reason beside them.

### The one product-type list the venue does publish

`pub:list:pair:securities` holds 28 pairs over the 14 asset codes
`pub:list:currency:securities` names: ALKN, ALT11M2507, ALT2612, BMN, BMN2,
CALCPB, CH100, CMSTR, CMTPL, STRCST, TITAN1, TITAN2, TITAN4 and USTBL. All 28
are also in `pub:list:pair:exchange`, and none is in `pub:list:pair:margin`.

The venue's own article for each one names what it is.

| Code | The venue's own words |
| --- | --- |
| ALKN | "tokenised limited partnership interests in Alkemya Metacore SCSp, a Luxembourg special limited partnership", whose asset is nickel wire |
| ALT2612 | "a securitization fund established in Grand Duchy of Luxembourg" |
| USTBL | "exposure to US Dollar-denominated short-term government bonds issued by the US Treasury, through the iShares $ Treasury Bond 0-1yr UCITS ETF" |
| TITAN1 | "equity in a Guernsey protected cell company ... invested into Subordinate Debt issued by a UK-based Credit Union" |
| BMN2 | "Blockstream Mining Note 2" |
| CH100, CALCPB, STRCST | "H100 NOTE", "CAPITAL B NOTE", "STRC NOTE" |

Not one is a listed company's share. Four of the articles carry one sentence
verbatim:

> "Important: This token is only available on the Bitfinex Securities platform
> and not the Bitfinex exchange."

and the venue's own
[primary-listing article](https://support.bitfinex.com/hc/en-us/articles/26351974497305-Understanding-Primary-Listing-and-Secondary-Trading-on-Bitfinex-Securities)
places secondary trading on "the Bitfinex Securities markets", requiring an
individual member to "Establish a wallet balance >= $100,000 USD in a specific
offering."

**So stocks is a proven no, on three grounds:** the venue lists no company
share, the securities it does list are not on the Bitfinex exchange by its own
words, and the platform they are on refuses any U.S. Person.

---

## The venue names its sectors in its own announcements

`https://api.bitfinex.com/v2/posts/hist` is bitfinex's own credential-free
announcement feed. 800 posts were read, paged with `end`, covering 2019-04-10 to
2026-10-09. Every non-crypto perpetual is named there by the venue itself.

| Date | The venue's own title | Codes |
| --- | --- | --- |
| 2020-09-01 | "Additional Products (euro/tether (EUR/USDt), pound/tether (GBP/USDt) and yen/tether (JPY/USDt)), Updated Product Descriptions for Derivatives Platform" | EURF0, GBPF0 |
| 2020-10-26 | "Additional Product Silver (XAGF0:USTF0), Updated Product Description for Derivatives Platform" | XAGF0 |
| 2021-04-09 | "Additional Product Tether Gold/bitcoin (XAUTF0:BTCF0) Perpetual Contract" | XAUTF0 |
| 2023-03-15 | "Additional Products, UK Oil (UKOILF0:USTF0), Palladium (XPDF0:USTF0), Platinum (XPTF0:USTF0)" | UKOILF0, XPDF0, XPTF0 |
| 2023-03-29 | "Additional Products, GERMANY 40 (GERMANY40IXF0:USTF0), SPAIN 35 (SPAIN35IXF0:USTF0), EUROPE 50 (EUROPE50IXF0:USTF0), FRANCE 40 (FRANCE40IXF0:USTF0), UK 100 (UK100IXF0:USTF0)" | five index codes |
| 2023-04-05 | "Additional Products, AUSTRALIA 200 (AUSTRALIA200IXF0:USTF0), HONG KONG 50 (HONGKONG50IXF0:USTF0), JAPAN 225 (JAPAN225IXF0:USTF0)" | three index codes |
| 2024-04-03 | "Additional Products Bitcoin Implied Volatility Index (BVIVF0:USTF0) and Ethereum Implied Volatility Index (EVIVF0:USTF0) Perpetual Futures Contracts" | BVIVF0, EVIVF0 |

The forex post carries the mechanism as well: "The pound, euro and yen products
track the respective change in price of pound, euro and yen relative to the
price of tether (USDt)."

Bitfinex's own Derivatives page carries the family list in its served markup:

> "Trade from a range of crypto, commodities, FX, equities and volatility
> perpetual swaps on Bitfinex Derivatives with up to 100x leverage and intra-day
> funding"

Two product changes the feed also records: the yen perpetual that post named is
no longer in the catalogue, and the venue's 2026-02-24 delisting notice states
"the Turkish Lira (TRY) fiat currency will be delisted" and "The TRY-PERP
(tTRYF0:USTF0) will be placed in 'reduce only' mode", which is why `TRYF0` is in
the currency list with no pair.

### The detours searched before the announcement feed

The product names were not available anywhere the sector readers already look.

| Detour | What shut it |
| --- | --- |
| `pub:map:currency:label` | 155 rows, and no label for any of the 18 non-crypto derivative codes |
| `pub:map:currency:undl` | 95 rows, and no row for the 8 index, 2 volatility, oil or three metal codes |
| `pub:map:currency:cat`, `:type`, `pub:list:currency:index`, `pub:list:pair:index` | 0 rows each |
| `conf/pub:fees` | one row, the perpetual funding clamp and slope, no product type |
| `status/deriv` with `keys=ALL` | 92 rows of price and funding state, no product type |
| `www.bitfinex.com/legal/derivative/product/` | 200 and 113,123 bytes, with zero occurrences of UKOIL, GERMANY40, XAG, Brent, FTSE, Nikkei, DAX, Index, Gold or Volatility - the page is client-rendered |
| the help centre, searched for UKOIL, Nikkei, silver, palladium and Brent crude | 0 matching articles for four of the five |

The control that the search could have found a route that exists: the same
help-centre API answered 45 articles for "United States" and a named article for
every one of the 14 securities codes, and the same conf reader answered rows for
all fourteen documented keys.

### What the citation carries, and what it does not

`src/trading/scrumming/sizing.py, at CITED_VENUE_BASE_SECTORS` holds fourteen
rows, every one keyed by `("bitfinex", base code)`.
`src/trading/scrumming/sizing.py, in venue_base_sector` answers them, and
`src/exchange/ccxt_connector.py, in market_asset_class` reads it ahead of the
recording and ahead of its own code sets.

| Rows | Why |
| --- | --- |
| `UKOIL` to commodities | the venue's own "UK Oil", and the generic reading had it under futures |
| eight index codes to indices | "GERMANY 40", "SPAIN 35", "EUROPE 50", "FRANCE 40", "UK 100", "AUSTRALIA 200", "HONG KONG 50", "JAPAN 225" |
| `BVIV` and `EVIV` to indices | "Bitcoin Implied Volatility Index", "Ethereum Implied Volatility Index" |
| `MNT`, `USDC` and `USDT` to crypto | a ticker collision the venue refutes itself, below |

An index perpetual records under its index because the sector belongs to the
underlying and the contract form rides on the listing, which is exactly the
reading `src/exchange/ccxt_connector.py, at INDEX_FUTURES_ASSET_TYPES` takes off
Coinbase's own `futures_asset_type` label.

**No row was added for a sector the generic reading already gets right.**
Silver, palladium, platinum and Tether Gold need none, because
`PRECIOUS_METAL_CODES` and `TOKEN_UNDERLYING_CODES` already answer commodities
for them. The euro and sterling markets need none, because
`FIAT_CURRENCY_CODES` already answers forex for them.

---

## The ticker collision, and the venue's own refutation

Of the nine markets the generic reading called forex, five are not currency
markets. `MNT` is the ISO 4217 code for the Mongolian tugrik and is in
`FIAT_CURRENCY_CODES` for that reason.

| Market | Base | `pub:map:currency:label` | `pub:map:currency:pool` | Margin collateral | Recorded now |
| --- | --- | --- | --- | --- | --- |
| MNT/USD, MNT/USDT | MNT | **"Mantle"** | ETH | no | crypto |
| USDC/USD, USDC/USDT | USDC | "USDc" | ETH | no | crypto |
| USDT/USD | USDT | "Tether USDt" | none | yes | crypto |
| EUR/USDT, EUR/USDT:USDT | EUR | **"Euro"** | none | yes | forex |
| GBP/USDT, GBP/USDT:USDT | GBP | **"Pound Sterling"** | none | yes | forex |

This is the AMD and NOK failure the issue records, caught before it reached the
screen: the venue publishes the label, and the label says Mantle.

Three near rows were left alone, because the decision that governs them is the
operator's and is open on issue #1192: `EURQ` ("Quantoz EURQ"), `EURR` ("StablR
Euro") and `MXNT` ("Tether MXNt") all read crypto, and whether a national
currency's token against a dollar stablecoin is a forex market is decision two
of that issue.

---

## Row six, the order shape

One path serves every sector: `POST /v2/auth/w/order/submit`. The venue's own
[Submit Order page](https://docs.bitfinex.com/reference/rest-auth-submit-order)
lists four required fields - `type`, `symbol`, `amount`, `price` - and gives
`amount` one description: "Amount of order (positive for buy, negative for
sell)."

The order bodies were read with the library's transport replaced, so nothing
left the machine, no credential was sent and no order was placed or previewed.

```
BTC/USD        buy  market   {"symbol":"tBTCUSD","amount":"0.001","type":"EXCHANGE MARKET"}
BTC/USD        sell market   {"symbol":"tBTCUSD","amount":"-0.001","type":"EXCHANGE MARKET"}
BTC/USD        buy  limit    {"symbol":"tBTCUSD","amount":"0.001","price":"50000","type":"EXCHANGE LIMIT"}
XAUT/USD       buy  market   {"symbol":"tXAUT:USD","amount":"0.01","type":"EXCHANGE MARKET"}
EUR/USDT       buy  market   {"symbol":"tEURUST","amount":"10","type":"EXCHANGE MARKET"}
BTC/USDT:USDT  buy  market   {"symbol":"tBTCF0:USTF0","amount":"1","type":"MARKET"}
```

Three facts the bodies carry. There is no `side` field: the sign of `amount`
carries the side. A spot order takes the `EXCHANGE ` prefix on its type and a
derivative order takes the bare type. And the size is a unit count in the base
currency in every sector, on both sides.

`src/exchange/ccxt_connector.py, in declared_order_types` reads "market and
limit" off the venue's own capability map, which the Submit Order page's own
type list agrees with.

### The cash market buy

This is reading three, and bitfinex is **not a member**.
`src/trading/scrumming/sizing.py, at CITED_CASH_MARKET_BUY` keeps `binance`,
`bitget`, `coinbase` and `gateio`.

```
bitfinex  market buy   amount  0.001     the base currency, sign carries the side
bitfinex  market sell  amount -0.001
bitget    market buy   size    50        the quote currency, the cash
```

The Submit Order page publishes no quote-currency size field at all, and the
venue's own capability map leaves `createMarketBuyOrderWithCost` unset while
`createMarketOrder` reads True. `market_buy_names_cash("BTC/USD", "bitfinex")`
answers False.

---

## The `code_leg` reading

This is reading four, and the separator is not needed. It exists because OKX
publishes no base code on a contract type. Bitfinex publishes the mapping
itself, under `pub:map:currency:undl`, which its own reference calls "Maps
derivatives symbols to their underlying currency".

```
pub:map:currency:undl      95 rows
EURF0  -> EUR              GBPF0 -> GBP              XAUTF0 -> XAUT
derivative bases with no row   23 of 94
```

The 23 are exactly the product types the venue names no underlying currency
for: all eight equity-index codes, both volatility-index codes, `UKOILF0`,
`XAGF0`, `XPDF0`, `XPTF0` and eleven crypto codes. The library strips the `F0`
suffix itself, so the connector reads `EUR`, `GBP`, `UKOIL` and
`AUSTRALIA200IX` directly off the parsed market and no record needs a
`code_leg`.

---

## Row seven, the variants

| Sector | Markets | Variant | Built | Holds every market |
| --- | --- | --- | --- | --- |
| crypto | 189 | Crypto Scrumming | yes | 189 of 189 |
| commodities | 9 | Commodity Scrumming | yes | 9 of 9 |
| forex | 4 | Forex Scrumming | yes | 4 of 4 |
| indices | 10 | Index Scrumming | yes | 10 of 10 |
| futures and perpetuals | 76 | Futures Scrumming | yes | 76 of 76 |
| stocks | 0 | Stock Scrumming | yes | no market to hold |

`src/trading/scrumming/sizing.py, in venue_variant` answered `MECHANIC_NONE` for
all 288 markets: none expires, none publishes a size-shape permission set, none
is untradeable at the reference excess, and none is limit only.

Bitfinex publishes no amount step. Its precision mode is significant digits, so
`src/exchange/ccxt_connector.py, in precision_to_increment` records no
`amount_increment`, `src/trading/scrumming/sizing.py, in recorded_unit_rule`
answers None on all 288 rows, and
`src/trading/scrumming/sizing.py, at CITED_UNIT_RULES` holds no bitfinex row -
so `market_unit_rule` answers None and every market sizes in fractions. The
minimum IS published and IS recorded, which is what
`src/trading/scrumming/sizing.py, in tradeable_answer` reads.

```
BTC/USD            limits.amount.min   0.00004
XAUT/USD                               0.002
EUR/USDT                               2.0
BTC/USDT:USDT                          0.00004
UK100IX/USDT:USDT                      0.0004
```

---

## Row eight, the gate log

`src/core/log_paths.py, in gate_log_path` composed one path per sector, each
distinct, with the home redirected.

```
trade/gate/bitfinex/crypto/gate.log
trade/gate/bitfinex/commodities/gate.log
trade/gate/bitfinex/forex/gate.log
trade/gate/bitfinex/indices/gate.log
trade/gate/bitfinex/futures_perps/gate.log
trade/gate/bitfinex/stocks/gate.log
```

---

## The recording, end to end

Driven through the real connector against the real public endpoints, with the
home redirected and no credential.

```
get_markets                      288 markets, every one active
record_venue                     288 rows written and read back
by sector                        crypto 189, futures_perps 76, indices 10,
                                 forex 4, commodities 9
the citation's effect            16 markets moved; blinding the venue name
                                 moves all 16 back to the answer they had
```

The sixteen, each with the sector the blinded reading gives it:

```
AUSTRALIA200IX/USDT:USDT  indices      was futures_perps
BVIV/USDT:USDT            indices      was futures_perps
EUROPE50IX/USDT:USDT      indices      was futures_perps
EVIV/USDT:USDT            indices      was futures_perps
FRANCE40IX/USDT:USDT      indices      was futures_perps
GERMANY40IX/USDT:USDT     indices      was futures_perps
HONGKONG50IX/USDT:USDT    indices      was futures_perps
JAPAN225IX/USDT:USDT      indices      was futures_perps
SPAIN35IX/USDT:USDT       indices      was futures_perps
UK100IX/USDT:USDT         indices      was futures_perps
UKOIL/USDT:USDT           commodities  was futures_perps
MNT/USD                   crypto       was forex
MNT/USDT                  crypto       was forex
USDC/USD                  crypto       was forex
USDC/USDT                 crypto       was forex
USDT/USD                  crypto       was forex
```

Blinding is the two-sided control, and it runs through the production function:
`market_asset_class(record, None, "")` answers the previous sector for all
sixteen, `market_asset_class(record, None, "bitfinex")` answers the new one, and
`venue_base_sector` answers None for `("okx", "UKOIL")`, for
`("bitfinex", "BTC")` and for `("", "UKOIL")` while answering `commodities` for
`("BITFINEX", "ukoil")`.

---

## Step five, the arithmetic

| Sector | Venues offered, before | After | Markets bitfinex can act on, before | After |
| --- | --- | --- | --- | --- |
| crypto | 22 | 22 | 0 | 189 |
| stocks | 21 | 21 | 0 | 0 |
| commodities | 18 | 18 | 0 | 9 |
| forex | 8 | 9 | 0 | 4 |
| indices | 15 | 15 | 0 | 10 |
| futures and perpetuals | 16 | 16 | 0 | 76 |

Every before-count of markets is zero for the one reason row five names.

The offered set and the set the Add form accepts are **identical in all six
sectors**, before and after, because both narrow one list:
`src/gui/main_tabs/asset_class_surface.py, in known_venues` holds 26 ids,
`src/gui/main_tabs/settings_dialog_surface.py, in exchange_status_rows` narrows
it by sector for the Exchanges tab, and
`src/gui/main_tabs/init_wizard_surface.py, in exchange_ids` offers the same 26
whole. The subtraction is zero in every cell.

---

## The four venues that did not move

Driven in the same run as the bitfinex drive, through the same production
method.

| Venue | Base codes | Naming a family | Cited rows for it | Sector counts |
| --- | --- | --- | --- | --- |
| gateio | 5640 | 607 | 0 | crypto 2031, stocks 565, commodities 20, forex 6, futures_perps 619, indices 18, options 3418 |
| bitget | 3789 | 3151 | 0 | stocks 3141, crypto 571, commodities 12, futures_perps 534 |
| okx | 687 | 311 | 0 | crypto 1013, commodities 21, stocks 400, futures_perps 483, options 2644 |
| okxus | 413 | 111 | 0 | crypto 1013, commodities 4, stocks 135 |

Every code count matches the figure the unit that wired that venue recorded.
`CITED_VENUE_BASE_SECTORS` holds 14 rows and all 14 name bitfinex, so no other
venue can read it. `CITED_CASH_MARKET_BUY` still reads `binance`, `bitget`,
`coinbase`, `gateio`.

---

## The timeframe row

`src/exchange/timeframes.py, at _AVAILABILITY` needed no change, and the row was
verified rather than assumed.

```
ccxt bitfinex publishes          12h 15m 1M 1d 1h 1m 1w 2w 30m 3h 4h 5m 6h
ALL_TIMEFRAMES draws             1m 5m 15m 30m 1h 2h 4h 6h 12h 1d 1w
published and drawn              1m 5m 15m 30m 1h 4h 6h 12h 1d 1w
the recorded row                 1m 5m 15m 30m 1h 4h 6h 12h 1d 1w
recorded but not published       none
published, drawn, not recorded   none
```

---

## What this could not establish

Three things, named plainly.

The Terms of Service text itself. `www.bitfinex.com` renders its legal pages in
the client, and the served markup carries none of the clause text. The refusal
is grounded on bitfinex's own U.S. Person FAQ, which states it in the venue's
own words and cites the Terms; the clause number is not established.

Whether the venue accepts a live order from this program. No reading used a
credential, so the order bodies above are what the library composes and not what
the venue acknowledged.

Whether a national currency's token against a dollar stablecoin is a forex
market. `EURQ`, `EURR` and `MXNT` read crypto today. That is decision two on
issue #1192 and it is the operator's.
