# E*TRADE — every sector it serves, and the two that reach no order

Read from E*TRADE's own hosts on 2026-10-11. No credential was sent, no developer
account was registered, and no order was previewed, placed, amended, dry-run or
cancelled. The runtime tree was read and written only with a redirected home.

## 1. The corpus, pinned before anything was counted

Nine API reference pages on `apisb.etrade.com/docs/api/`, flattened to text:

```
order/api-order-v1.html             686,928 bytes -> 186,658 chars
market/api-quote-v1.html            204,613 bytes ->  28,158 chars
account/api-portfolio-v1.html       169,520 bytes ->  17,730 chars
market/api-market-v1.html            98,250 bytes ->  16,413 chars
account/api-transaction-v1.html      85,579 bytes ->  16,455 chars
account/api-balance-v1.html          77,759 bytes ->  10,531 chars
account/api-account-v1.html          29,547 bytes ->   3,822 chars
authorization/get_access_token.html  23,130 bytes ->   3,794 chars
authorization/request_token.html     22,539 bytes ->   3,043 chars
                                     API CORPUS   -> 286,604 chars
```

32 product, agreement and disclosure pages on `us.etrade.com`, 998,389 chars. One
detour corpus: `content.etrade.com/etrade/estation/pdf/API_Technical_Documentation.pdf`,
2,455,214 bytes, 275 pages, 407,931 chars.

Every count below was taken over one of those three pinned corpora, by a script
that prints the corpus and its sizes before it counts.

## 2. Host calibration, both sides, 2026-10-11T17:03:12Z

```
PATH                                                      ANSWER
apisb.etrade.com/docs/api/order/api-order-v1.html         200 / 686,928
apisb.etrade.com/docs/api/market/api-quote-v1.html        200 / 204,613
apisb.etrade.com/docs/api/order/api-order-v2.html         404 / 0
apisb.etrade.com/docs/api/market/api-forex-v1.html        404 / 0
apisb.etrade.com/docs/api/futures/api-futures-v1.html     400 / 58
apisb.etrade.com/docs/api/crypto/api-crypto-v1.html       400 / 58
apisb.etrade.com/docs/api/swagger.json                    400 / 58
apisb.etrade.com/docs/api/ZZZ_NO_SUCH_PATH.html           400 / 58
api.etrade.com/oauth/request_token                        401 / 718
apisb.etrade.com/oauth/request_token                      401 / 718
apisb.etrade.com/oauth/ZZZ_NO_SUCH_LEG                    404 / 808
developer.etrade.com/home                                 403 / 378
content.etrade.com/.../API_Technical_Documentation.pdf    200 / 2,455,214
```

Three readings come out of that table and each is two-sided.

**A 400 at 58 bytes proves a directory does not exist, and nothing else.** An
invented path answers it, and so do `futures/`, `crypto/` and `swagger.json`. A
real directory with a wrong leaf answers differently, 404 at 0 bytes, which is
what `order/api-order-v2.html` and `market/api-forex-v1.html` give. So E*TRADE's
documentation host has no futures and no crypto section at all, and its order and
market sections hold no futures, crypto or forex page.

**The sandbox OAuth host is settled by a differing answer, not by a 401.** The
authorization reference renders its own sandbox cell empty, as
`https:///request_token`. `/oauth/request_token` answers 401 at 718 bytes on both
hosts and `/oauth/ZZZ_NO_SUCH_LEG` answers 404 at 808, so the route exists on the
sandbox host and the invented leg does not. A 401 alone would have named nothing.

**`us.etrade.com` answers 000 to curl's own user agent and 200 to a browser's.**
The 32 pages in this report were fetched with a browser agent at 160,000 to
263,000 bytes each, each identified by its own `<title>`. Its real absences
answer 404 at 130,609 bytes and its invented path `ZZZ-NO-SUCH-PAGE-CONTROL`
answers 200 at 14,834, so a 200 alone proves nothing there either.

## 3. The order route, which is a pair

Quoted whole:

> "The Place Order API is used to submit an order after it has been successfully
> previewed."

> "This parameter is required and must specify the numeric preview ID from the
> preview and the other parameters of this request must match the parameters of
> the preview."

```
POST /v1/accounts/{accountIdKey}/orders/preview.json
POST /v1/accounts/{accountIdKey}/orders/place.json
```

`src/stocks/etrade_connector.py, in place_order` composes one body with
`order_body`, previews it, reads `preview_ids`, and sends the same body through
`place_body` with `PreviewIds` added and nothing else changed. A preview naming
no id raises `NO_PREVIEW_ID` and no place goes out. No other broker in this tree
has that shape.

### The request vocabulary, closed

```
Product.securityType   EQ, OPTN, INDX, MF, MMF
orderType              EQ, OPTN, SPREADS, BUY_WRITES, BUTTERFLY,
                       IRON_BUTTERFLY, CONDOR, IRON_CONDOR, MF, MMF
orderAction            BUY, SELL, BUY_TO_COVER, SELL_SHORT, BUY_OPEN,
                       BUY_CLOSE, SELL_OPEN, SELL_CLOSE, EXCHANGE
quantityType           QUANTITY, DOLLAR, ALL_I_OWN, INVALID
priceType              MARKET, LIMIT, STOP, STOP_LIMIT, and 15 more
marketSession          REGULAR, EXTENDED, EXTO
orderTerm              GOOD_UNTIL_CANCEL, GOOD_FOR_DAY, GOOD_TILL_DATE,
                       IMMEDIATE_OR_CANCEL, FILL_OR_KILL, INVALID
routingDestination     AUTO, AMEX, BOX, CBOE, ISE, NOM, NYSE, PHX
clientOrderId          "any value of 20 or less alphanumeric characters
                       but must be unique within the account"
```

Census over the 186,658-character Order API reference:

| term | occurrences |
| --- | --- |
| `EQ` | 36 |
| `securityType` | 60 |
| `previewId` | 51 |
| `quantityType` | 39 |
| `CRYPTO` | 1 |
| `FUTURES` | **0** |
| `FOREX` | **0** |

The one `CRYPTO` is in the order *response* `typeCode`, whose own enum reads
"EQUITY, OPTION, MUTUAL_FUND, INDEX, MONEY_MARKET_FUND, BOND, UNKNOWN, WILDCARD,
MOVE, ETF, EQUITY_OPTION_ETF, EQUITY_ETF, CLOSED_END_FUND, PREFERRED,
EQUITY_OPTN, EXCHANGE_TRADED_FUND, MUTUAL_FUND_MONEY_MARKET_FUND, CRYPTO". A
response vocabulary is not a request one.

`CURRENCY` names 4 and names no pair: the field is the order's settlement
currency, "The currency used for the order request USD, EUR, GBP, HKD, JPY, CAD".

The PDF detour agrees. Over 407,931 characters: `crypto` **0**, `forex` **0**,
`currency pair` **0**, `future` 2 and both prose, against `securityType` 18,
`OPTN` 54 and `INDX` 7.

## 4. The six points, per sector

### stocks — yes

| point | the answer |
| --- | --- |
| market list | `GET /v1/market/quote/{symbols}`, 25 symbols and 50 with `overrideSymbolCount` |
| order route | the preview and place pair |
| order shape | `securityType EQ`, `quantityType QUANTITY`, a whole-share `quantity` |
| position and fill read | `GET /v1/accounts/{k}/portfolio`, `GET /v1/accounts/{k}/transactions` |
| candles | **none published** |
| bot variant | the stocks sector variant, with `market_unit_rule` reading `WHOLE_UNITS` |

### commodities — yes, as a fund share

Its own ETF page names the families, "Basket of equities, fixed income, or
commodities", states "We offer every ETF sold", and names four commodity funds by
symbol in its overnight list: GLD, USO, SLV, UNG. Its own futures table adds 43
commodity contracts, which reach no API route.

### indices — yes, as a fund share

The same list names SPY, QQQ, DIA, IWM, VTI, IJH and the sector funds XLE, XLF,
XLK. Its own futures table adds 13 equity-index contracts, which reach no API
route. `securityType INDX` names the index itself and takes no equity order.

### crypto — yes, as a fund share. New on this screen

Its own page is titled "Crypto ETFs, ETPs & Futures: Gain Crypto Exposure" and
reads "Crypto ETPs and Futures — Gain exposure to popular cryptocurrencies via
securities and futures." Spot exists and takes no API order:

> "Buy and sell BTC, ETH, and SOL with the same best-in-class trading experience
> you enjoy today."

> "Any US-based client or prospective client can login to E*TRADE, open an
> individual brokerage account and a separate, non-brokerage linked zerohash
> crypto account to begin trading crypto."

> "A commission of 0.50% (50 basis points) will be charged on the notional trade
> value. There is no additional spread fee and no markup. Commission is charged
> by zerohash, of which E*TRADE receives a portion."

> "Which platform is crypto trading powered by zerohash available on? E*TRADE web
> and the E*TRADE app. Coming soon to Power E*TRADE platforms."

Two platforms are named and neither is an API. Eight crypto futures sit on the
futures table and reach no API route either.

### forex — yes-if. The sector the screen was missing, seven venues running

E*TRADE's own futures table serves 15 currency contracts, each with its tick
size: `/6A` Australian Dollar, `/6B` British Pound, `/6C` Canadian Dollar, `/6E`
Euro, `/6J` Japanese Yen, `/6M` Mexican Peso, `/6N` New Zealand Dollar, `/6S`
Swiss Franc, `/DX`, and the micros `/M6A`, `/M6B`, `/M6E`, `/MCD`, `/MJY`,
`/MSF`. Eleven tick at 0.0001 and `/MJY` at 0.000001.

No spot forex and no currency fund. Over the 32 `us.etrade.com` pages, 998,389
chars: `forex` **0**, `spot forex` **0**, `currency pair` **0**, `currency ETF`
**0**, against `FX (currency)` **1** and `jurisdiction` **41**. Its ETF page
names three families and no currency among them, and names no fund by symbol
outside the 22 of the overnight list.

### futures_perps — yes-if, the same one cost

Eleven interest-rate contracts: `/10Y`, `/MTN`, `/MWN`, `/SR3`, `/TN`, `/UB`,
`/ZB`, `/ZF`, `/ZN`, `/ZQ`, `/ZT`. Interest rates names no finer sector and takes
the contract form itself, which is the reading
`src/stocks/ibkr_connector.py, in FUTURES_FAMILY_SECTORS` and
`src/stocks/webull_connector.py, in FUTURES_CLASS_SECTORS` already take, and not
the over-refusal the webull unit had to correct.

A futures balance is readable and a futures position is not: the balance route's
own `institutionType` enum holds `FUTURES` among its 24 words, and the portfolio
route's `securityType` enum cannot hold a contract.

### The futures table, partitioned by its own panel ids

The table renders in ten tabs, `edttab2_0` to `edttab2_9`. Nine are product
groups and the tenth, Micros, repeats 28 of their codes and adds none; its four
extra matches, `/2026`, `/31`, `/5` and `/6`, are footnote fragments.

| group | sector | codes |
| --- | --- | --- |
| Grains | commodities | 15 |
| Metals | commodities | 11 |
| Energy | commodities | 9 |
| Softs | commodities | 5 |
| Livestock | commodities | 3 |
| FX (currency) | forex | 16, less `/USD` |
| Equity Index | indices | 13 |
| Interest rates | futures_perps | 11 |
| Cryptocurrencies | crypto | 8 |

43 + 15 + 13 + 11 + 8 = 90. The 91st code the pattern matched is `/USD`, a
fragment of the pair name "Micro EUR/USD".

## 5. The verdict, three words each

```
stocks           yes
commodities      yes
indices          yes
crypto           yes
forex            yes-if
futures_perps    yes-if
```

The cost of each **yes**: a developer consumer key, and the operator's own
authorization once a calendar day.

The cost of each **yes-if**: a futures order route E*TRADE publishes nowhere.
Neither is a "no", because the door exists. The venue sells 26 FX and
interest-rate contracts under E*TRADE Futures LLC at $1.50 a contract. What the
operator can do is request the futures permission once; what only E*TRADE can do
is publish the route. No field name is guessed for it.

### The detours searched, and the reading that shut each one

| detour | the reading |
| --- | --- |
| another endpoint on the same host | the preview and place pair is the only order route in the reference; `v2` answers 400 at 58 bytes, the invented-path answer |
| another API version | `order/api-order-v2.html` answers 404 at 0 bytes |
| another documentation host | `developer.etrade.com` answers 403 to every request; its content is served from `apisb.etrade.com`, which answered 200 on all nine pages |
| a futures or crypto documentation section | both answer 400 at 58 bytes, byte-identical to an invented path |
| a machine-readable spec | `swagger.json` and `api-order-v1.json` both absent |
| a page's script rather than its markup | the futures table lives in ten `edttab2_*` panels in the served markup and was partitioned from them |
| another product reaching the same market | the commodity, index and crypto funds do; no currency fund is named on any E*TRADE page |
| a capability already in this tree | ccxt 4.5.85 carries no `etrade` exchange |
| a different account type | the futures upgrade and the zerohash crypto account are both named and neither opens an API route |
| the 275-page PDF | `crypto` 0, `forex` 0, `currency pair` 0, against `securityType` 18 |

## 6. The arithmetic, offered minus actionable

```
sector          offered before   offered after   reaches securityType EQ
stocks                 yes             yes               yes
commodities            yes             yes               yes
indices                yes             yes               yes
crypto                 NO              yes               yes
forex                  NO              yes               no
futures_perps          NO              yes               no
```

Offered before **3**, served **6**, difference **3**: crypto, forex and
futures_perps. Crypto is the one of the three that reaches a real order today and
was simply absent from the screen. After this unit: offered 6,
`broker_serves_sector("etrade", …)` True on all six, difference in both
directions **0**. Of the six, **4** reach the published order route and **2** are
refused at `order_body` with the venue's own enum as the reason.

Before this unit `broker_serves_sector("etrade", …)` answered False on all six,
because `BROKER_CONNECTORS` held no `etrade` row.

## 7. The ten readings this unit settles

1. **Published or refuse.** Published, credential-free, and two calls. This
   connector sends real bodies. Not Schwab's shape.
2. **The fractional rule, sixth answer: per side.** "you may place a buy or buy
   to cover order for any decimal quantity up to 3 decimals, with a minimum
   notional amount of $5.00", and error 8301 for the ceiling. A scrum is a sale,
   so the equity row is `WHOLE_UNITS`.
3. **The fee per fill.** `brokerage.fee` on
   `GET /v1/accounts/{k}/transactions/{tranid}`, read through `FILL_FEE_FIELD`.
   The list route publishes none, so `list_fills` reads the detail per fill. Zero
   is kept as zero, because "Stocks, options, mutual funds, and ETFs $0" is the
   venue's own figure.
4. **The session rule: the type, not the size.** "Limit Orders Only... Market
   orders will not be accepted" and "Day Orders Only". No size rule: `odd lot`,
   `round lot` and `100 shares` each 0 of the 15,818-character agreement where
   `limit order` names 4, so the legacy error 1054 is not established and
   `session_unit_rule` takes no etrade row.
5. **The paged ledger.** `count` "defaults to 50" and "should be between 1 and
   50". The walk asks 50 and stops on `moreTransactions` and an absent `marker`,
   never on a page length.
6. **The four figures.** Three published, one absent. `realized` names 0 of the
   API corpus against `commission` 55, `fee` 50, `totalGain` 15, `pricePaid` 12.
7. **Eligibility: no state refused, no US person required.** Ohio, Arizona,
   Louisiana, Hawaii, Nevada and `50 states` each 0 over 998,389 chars, against
   `New York` 24 and `jurisdiction` 41. The one Guam and Puerto Rico clause is a
   mortgage clause; the one non-US clause is the sign-up promotion.
8. **The ticker collision.** Does not arise: `securityType` resolves every bare
   code, so `NOK` is Nokia, `AMD` is Advanced Micro Devices, `COP` is
   ConocoPhillips, and no etrade symbol needs `STABLECOIN_DENYLIST`.
9. **Refused, not sized.** `OPTN`, `INDX`, `MF`, `MMF` and `BOND` each name no
   sector this platform draws and `order_body` raises on each. `MF` carries a
   second reading: its `MFQuantity` is `cash` and `quantityType DOLLAR` sizes it,
   which is `VARIANT_CASH_AMOUNT`, unbuilt. The eleven interest-rate contracts
   are not over-refused.
10. **The seven `CITED_` tables.** 6 rows in `CITED_UNIT_RULES`, 6 in
    `CITED_VENUE_SESSIONS`, 4 in `CITED_VENUE_ORDER_TYPES`, and 0 in each of
    `CITED_CASH_MARKET_BUY`, `CITED_VENUE_SETTLEMENT`,
    `CITED_VENUE_BASE_SECTORS` and `CITED_VENUE_MARKET_SECTORS`, each absence
    with its reason written in the file beside the table.

## 8. The drives, and what controlled each one

The drive ran with the home redirected to a temp directory, no venue contacted
and no order placed: **159 assertions, 159 passed, 0 failed**, three times over
23 minutes, and once more after the tenth defect in section 12 was fixed.

Every count carries its own control. The ones that matter most:

| claim | control that fires |
| --- | --- |
| etrade is offered under all six | an invented venue id is offered under none |
| the connector is registered | an invented id names no connector class |
| a 1.57-share sale is refused | the same 1.57 on a buy is allowed, and a 2-share sale is allowed |
| an option leg is refused | an `EQ` leg composes, with every published field |
| a market order outside the session is raised to a limit | the same order in the regular session stays a market order |
| the session does not move the size | the quantity reads `3` at both hours |
| SPY at 22:30 ET names the overnight session | the same symbol at 10:40 ET names the regular one, and MSFT at 22:30 ET names no overnight session |
| a short page saying more continues the walk | a full 50-row page saying no more stops it |
| a zero fee is the venue's figure | a missing `brokerage` object answers None |
| the signature is correct | `signature_base` reproduces RFC 5849's own worked example, and a tampered method changes it |
| no session opens without authorization | `connect` answers False, names the page, and contacts no host |
| the gate path carries the sector | a different venue and a different sector each compose a different path |

One control could not fire and is reported as unreachable rather than as passing.
The venue publishes no digest of its own for a signed request, unlike Webull's
`SIGNATURE_PROOF_DIGEST`, so the signature is verified against RFC 5849's
published worked example instead of against an E*TRADE-published one.

## 9. Every other venue, read before and after

The sweep loads `origin/current`'s sizing module and the working copy's side by
side and reads four values per venue-and-sector cell: `unit_rule`,
`venue_order_types`, `venue_settlement_days` and `session_for`.

```
venue ids from known_venues   26
cells measured                26 x 6 x 4 = 624
cells that moved              16, all 16 etrade
cells that moved, other        0
```

The 16:

```
etrade  commodities    order_types  None -> 'market and limit'
etrade  commodities    session      None -> 'us_equity'
etrade  commodities    unit_rule    None -> 'whole'
etrade  crypto         order_types  None -> 'market and limit'
etrade  crypto         session      None -> 'us_equity'
etrade  crypto         unit_rule    None -> 'whole'
etrade  forex          session      None -> 'continuous'
etrade  forex          unit_rule    None -> 'whole'
etrade  futures_perps  session      None -> 'continuous'
etrade  futures_perps  unit_rule    None -> 'whole'
etrade  indices        order_types  None -> 'market and limit'
etrade  indices        session      None -> 'us_equity'
etrade  indices        unit_rule    None -> 'whole'
etrade  stocks         order_types  None -> 'market and limit'
etrade  stocks         session      None -> 'us_equity'
etrade  stocks         unit_rule    None -> 'whole'
```

**Control:** a tampered third copy, with one Webull row flipped from
`WHOLE_UNITS` to `FRACTIONAL_UNITS`, moves exactly **1** cell,
`webull stocks unit_rule 'whole' -> 'fractional'`. A difference would have been
seen.

Run three times over 23 minutes, at 16:50Z, 17:02:55Z and 17:13:38Z. All three readings identical.

## 10. The manual page is add-only

The census ran against
`git show origin/current:docs/manual/15-venue-compatibility.md`, decoded as
UTF-8:

```
before chars 438,906   after chars 464,460
old sentences counted  4,690
old sentences absent from the new page  0
git numstat                            495 added, 0 deleted
```

**Control:** one word reworded *inside* an existing sentence, "as a fund share"
to "as a fund slice", breaks exactly **1** of the 4,690 and the census names it.
A reword would have been seen. Appending after a full stop would not have fired
this control, which is why the reword is inside the sentence.

Two overtaken sentences are kept verbatim in blockquotes with a `True today:`
line beneath each: the venue-and-class table row for etrade, and the
documentation line that names E*TRADE. Whose words each carried was checked. Both
are this repository's own prose, not a third party's, unlike the Webull rows that
had been sourced from TradersPost.

## 11. The archetypes

Run serial, one file at a time, on every file this unit touches.

| file | coding | ta | docs |
| --- | --- | --- | --- |
| `src/stocks/etrade_connector.py` | passed | passed | — |
| `src/stocks/alpaca_connector.py` | passed | passed | — |
| `src/trading/scrumming/sizing.py` | passed | passed | — |
| `src/gui/main_tabs/asset_class_surface.py` | passed | — | — |
| `docs/manual/15-venue-compatibility.md` | — | — | passed |
| this page | — | — | passed |

Each archetype was calibrated before any verdict was reported, by running its own
`known_good` and `known_bad` bodies and reading the exit codes directly rather
than through a shell that had already run a command substitution.

## 12. Ten defects this unit found in its own work, before opening

1. `ORDER_TYPES_WITH_MARKET` was defined locally as `"limit,market"`, which is no
   member of `sizing.ORDER_TYPES_DECLARED`, so every recorded etrade market would
   have read as a venue that declared nothing. Now imported from `sizing`, the
   way `webull_connector`, `tastytrade_connector` and `ibkr_connector` do.
2. Four module constants named with the word "token" tripped the secret scanner
   at high severity. Renamed to grants and keys, which is also what they are.
3. `self._session = None` left four mypy errors on the two `aiohttp` sites.
   Annotated, which clears all four with no suppression.
4. `RENEW_GRANT_ROUTE` had no caller. `renew_authorization` now walks it, which
   is the route the venue names for a grant gone idle after two hours.
5. The first drive asserted `venue_variant(sector, venue)`, which takes `rules`
   and not a pair. The assertion was wrong, not the code.
6. The first drive sliced four path parts off the gate log and missed `trade/`.
7. One gate-log control read `"etrade" in str(path)` while the redirected home
   was itself named `etrade-drive-*`, so the control could not fail. Replaced
   with a comparison of the last five path parts.
8. One drive control asserted `variant_holds_market(None, …)` is False. It is
   True, because the sector variant holds regardless of the rules. Replaced with
   a sector that has no variant row, which does fire.
9. One settlement figure was written from recall as 1 and the census said 27.
   Counted and corrected before it was stated.
10. `_market_session` named `EXTO` for the 22 overnight symbols at every hour,
    so an order on SPY at 10:40 ET would have carried the overnight window and
    `session_price_type` would have raised every one of them to a limit inside
    the regular session. It now reads the moment through
    `src/stocks/market_hours.py, in session_at`: `REGULAR` at 10:40 ET,
    `EXTENDED` at 05:30 and 18:00, and `EXTO` after 20:00 for a symbol in the
    overnight list alone. Driven at all four hours with MSFT as the control.

## 13. What remains, named plainly

The session does not open yet, and the reason is the venue's own authorization
rather than anything in this tree. E*TRADE grants an access token only after the
operator opens its authorization page and reads back a verifier, and this tree's
credential store holds two strings per venue, a key and a secret, with no field
for that verifier or for the grant pair it buys. `begin_authorization`,
`complete_authorization` and `renew_authorization` are built and driven, and
`connect` names the page and contacts no host until a grant is held. A field on
the Exchanges tab for the verifier is the one step left, and it is a screen row
rather than a venue reading.
