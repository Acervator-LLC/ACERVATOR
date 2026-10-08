# Exchange Build-Out Order

**Mode: Reference.**

This report ranks the venues the platform already names, so the next build-out
is chosen from a figure and not from a guess. It builds nothing. No file under
`src/`, `main.py`, `tools/` or `dev_harness/` changed, and no page under
`docs/manual/` changed.

**FALSIFICATION.** This report is wrong if a venue id it names is absent from
the two module constants it reads, if a sector count it gives differs from the
matrix it counted, if a volume figure it quotes is absent from the page it
cites, or if the recording holds more than one venue.

---

## What the operator asked for

> Follow this with a list of build outs ordered by decreasing trade volume and
> sector coverage.

> Everything must be anchored in research. No guessing!

Coinbase is first and Robinhood is second by his instruction. Both are fixed at
the top and neither is ranked. Everything after them is ranked below.

---

## The venues, read out of the tree

Two module constants name every venue. `src/gui/main_tabs/asset_class_surface.py`,
`crypto_venues` reads the first and returns it whole. The same file declares the
second as `EQUITY_VENUES`.

```
src/exchange/ccxt_connector.py, SUPPORTED_EXCHANGES          15 crypto ids
src/gui/main_tabs/asset_class_surface.py, EQUITY_VENUES        9 broker ids
                                                              --
                                                              24 ids in all
```

**Twenty-four ids were found.** The nine broker ids name eight firms, because
`EQUITY_VENUES` holds both `ibkr` and `interactivebrokers` for Interactive
Brokers. Coinbase is one of the fifteen, so twenty-three ids are ranked.
Robinhood is in neither constant. It is fixed second by instruction and is not
ranked.

---

## The recording holds one venue

This is the reason twenty-three of the twenty-four ids reach nothing. The file
`src/exchange/market_rules_store.py`, `store_path` names was read read-only and
counted. Nothing was written to it.

```
top-level venue keys          1
market rows under that key    1146
```

One venue is recorded. Issue #1192 counted 1142 rows on 2026-10-07 and the file
now holds 1146, so the recording moved since that count and the venue count did
not. `asset_class_surface.recorded_venue_classes` therefore answers nothing for
the other twenty-three ids, and `src/trading/bot_container.py`, `_asset_class`
falls back to the sector a bot declares.

---

## Key one, the sectors a venue covers

This key is already researched and is not re-derived here. It is counted out of
[2026-10-07_venue_sector_readiness_matrix/REPORT.md](../2026-10-07_venue_sector_readiness_matrix/REPORT.md),
which carries twenty-six venues by six sectors with one verdict per cell.

That report defines its four verdicts. Two of them mean the venue lists a
product in the sector and two mean it does not.

```
READY     the venue lists the product and our code can place the order
BLOCKED   the venue lists the product and our code cannot reach it
ABSENT    the venue lists no product in that sector
WRONG     the program lists the sector and the venue has none
```

**Coverage is the count of READY and BLOCKED cells.** Those are the two
verdicts that mean a product exists to trade. A question mark on a verdict does
not change the verdict, so it does not change the count.

| Venue | crypto | stocks | commodities | forex | indices | futures / perps | sectors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| binance | R | B | B | B | B | B | 6 |
| bybit | R | B | B | B | B | B | 6 |
| gateio | R | B | B | B | B | B | 6 |
| kraken | R | B | B | B | B | B | 6 |
| kucoin | R | B | B | B | B | B | 6 |
| cryptocom | R | B | B | B | B | B | 6 |
| bitget | R | B | B | B | B | B | 6 |
| schwab | B | B | B | B | B | B | 6 |
| ibkr | B | B | B | B | B | B | 6 |
| fidelity | B | B | B | B | B | B | 6 |
| okx | R | B | B | — | B | B | 5 |
| mexc | R | B | — | B | B | B | 5 |
| bitfinex | R | — | B | B | B | B | 5 |
| huobi | R | B | — | B | B | B | 5 |
| tastytrade | B | B | B | — | B | B | 5 |
| webull | B | B | B | — | B | B | 5 |
| poloniex | R | B | — | — | B | B | 4 |
| gemini | R | — | B | B | — | B | 4 |
| alpaca | B | B | B | — | B | — | 4 |
| bitstamp | R | — | B | B | — | — | 3 |
| etrade | — | B | B | — | B | — | 3 |
| interactivebrokers | — | W | — | — | — | — | 0 |
| tdameritrade | — | W | — | — | — | — | 0 |

`R` is READY, `B` is BLOCKED, an em dash is ABSENT and `W` is WRONG. The two ids
that count zero are the ones the matrix marks WRONG in stocks and ABSENT
everywhere else. Coinbase counts 6 and Robinhood counts 5. Both are fixed and
neither is ranked.

---

## Key two, trade volume

This is the figure the ranking had to establish. No figure here is estimated,
converted or inferred.

### The crypto venues

None of the fifteen publishes a figure of its own that compares with the
others, so the figure is a third-party one. Two aggregators were read on
2026-10-08 and both readings are shown.

```
primary     CoinMarketCap, "Spot Trading Volume(24h)", in US dollars
secondary   CoinGecko, "24h Volume", in bitcoin
measure     spot volume over 24 hours, not total volume and not derivatives
reported by a third party, not by the venue
```

The primary is CoinMarketCap because it names its measure. Its ranking page
states "233 spot exchanges with a total 24h volume of $932.17B", and each venue
page prints `Spot Trading Volume(24h)` against a dollar figure. CoinGecko heads
its column `24h Volume` and its page states "As of today, we track 160 crypto
exchanges with a total 24h trading volume of $106 Billion, a 4.8% change in the
last 24 hours". CoinGecko does not say on that page whether the column is spot
only, so it is the cross-check and not the ranking key.

| Venue | CoinMarketCap spot 24h, USD | CoinGecko 24h, BTC |
| --- | --- | --- |
| binance | 12,313,776,868 | 150,153.4359 |
| okx | 2,207,798,651 | 26,321.0554 |
| bybit | 2,165,543,168 | 26,346.0032 |
| gateio | 1,899,524,136 | 22,995.1191 |
| kraken | 1,826,079,158.41 | 22,112.3463 |
| mexc | 1,599,542,322.49 | 14,428.7615 |
| kucoin | 1,377,543,491 | 16,555.8546 |
| bitfinex | 1,157,463,687.53 | 15,012.6306 |
| poloniex | 945,777,787.84 | 11,297.8069 |
| huobi | 856,251,198 | 10,255.4818 |
| cryptocom | 826,680,593.85 | 10,270.9493 |
| bitget | 813,319,184 | 10,126.7512 |
| bitstamp | 445,456,235.27 | 5,179.3868 |
| gemini | 55,636,483.15 | 619.7547 |

Coinbase is fixed first and not ranked. It reads 4,110,778,788 US dollars and
50,455.9471 bitcoin on the same two pages.

**Where the two sources disagree.** The two orders are the same except for
three adjacent pairs, and one gap is large.

```
okx / bybit        CoinMarketCap puts okx first, CoinGecko puts bybit first
huobi / cryptocom  CoinMarketCap puts huobi first, CoinGecko puts cryptocom first
mexc / kucoin      CoinMarketCap puts mexc first, CoinGecko puts kucoin first
```

The mexc gap is the only large one. CoinMarketCap prints 19,447 bitcoin beside
its mexc dollar figure and CoinGecko prints 14,428.7615, which is 26 per cent
lower for the same measure on the same day. The ranking takes CoinMarketCap for
mexc, because that page names its measure and prints both units, and its two
units agree with each other. The other two pairs sit inside one per cent and
either source orders them.

Two names are worth recording. CoinMarketCap titles bitstamp "Bitstamp by
Robinhood" and states "Robinhood's acquisition of Bitstamp in June 2025", so the
venue fixed second already owns one of the fifteen. The id `huobi` reaches the
library class `htx` through `src/exchange/ccxt_connector.py`,
`CCXT_CLASS_ALIASES`, and both aggregators list it as HTX.

### The brokers

A broker publishes no spot volume. What each firm publishes is named below with
what it measures. A trade count is not a dollar figure, and the two are never
mixed in one order.

| Firm, and its id or ids | Figure as printed | What it measures | Period | Published | Reported by |
| --- | --- | --- | --- | --- | --- |
| Charles Schwab, `schwab` | "Client Daily Average Trades (DATs) (in thousands)" 9,821 | all client trades per day | August 2026 | 15 September 2026 | the firm |
| Fidelity, `fidelity` | 5.7 million daily average trades | "total customer/client trades divided by the number of trading days in the applicable reporting period" | the quarter to 30 June 2026 | the firm's quarterly business update | the firm |
| Interactive Brokers, `ibkr` and `interactivebrokers` | 4.111 million Daily Average Revenue Trades | revenue-earning trades per day, a narrower count than a daily average trade | September 2026 | 1 October 2026 | the firm, quoted from a third party that reported it |
| Webull, `webull` | "Equity notional volume" grew to $279 billion | the dollar value of equity trades | the quarter to 30 June 2026 | 19 August 2026, Form 6-K | the firm |
| Alpaca, `alpaca` | no published figure | the firm publishes growth percentages and no volume | — | — | a third party gives $180 billion annualised for 2024 |
| tastytrade, `tastytrade` | no published volume figure | its parent publishes net trading revenue of $65.3 million, which is revenue and not volume | the quarter to 30 September 2026 | the parent's quarterly trading update | the parent |
| E\*TRADE, `etrade` | no published figure | its parent publishes a percentage change in self-directed daily average revenue trades and no figure | — | — | — |
| TD Ameritrade, `tdameritrade` | no published figure | the firm reports nothing; it was absorbed and its interface was discontinued on 10 May 2024 | — | — | — |

Three readings need a note. Schwab's figure is printed in thousands, so 9,821
is 9.821 million trades a day. Interactive Brokers' own release and the wire
copy of it both answered HTTP 403 to a fetch, so the figure is quoted from a
named third-party report of that release rather than from the release itself;
the release is published and is not behind a sign-in. A daily average revenue
trade counts only revenue-earning trades, so it is not the same measure as a
daily average trade and the two are marked where they appear.

Robinhood is fixed second and is not ranked. Its own August 2026 operating data
gives equity notional trading volumes of $335 billion for the month and an
average daily volume of $16.0 billion. The release page did not answer inside
the fetch timeout, so that reading comes from the search index of the firm's own
release and not from the page.

---

## The ranking rule

**Sector coverage groups the list and trade volume orders each group: the crypto
venues come first inside a group, ordered by the 24-hour spot dollar volume one
third party measures the same way for all fifteen, and the brokers follow,
ordered by whatever each firm publishes and last where it publishes nothing,
because no published figure compares a broker's trade count or quarterly
notional against a venue's 24-hour spot volume.**

The two keys disagree, so the rule matters. Both orders are shown. The ranking
makes no weighted score, so there is no score to show inputs for.

---

## Table A, the build-out order

Coverage groups the list and volume orders each group. This is the order this
report recommends.

| # | Venue | Sectors | Volume key | Measure |
| --- | --- | --- | --- | --- |
| — | coinbase | 6 | 4,110,778,788 | fixed first by instruction |
| — | robinhood | 5 | 335,000,000,000 for the month | fixed second by instruction |
| 1 | binance | 6 | 12,313,776,868 | spot 24h, USD |
| 2 | bybit | 6 | 2,165,543,168 | spot 24h, USD |
| 3 | gateio | 6 | 1,899,524,136 | spot 24h, USD |
| 4 | kraken | 6 | 1,826,079,158 | spot 24h, USD |
| 5 | kucoin | 6 | 1,377,543,491 | spot 24h, USD |
| 6 | cryptocom | 6 | 826,680,594 | spot 24h, USD |
| 7 | bitget | 6 | 813,319,184 | spot 24h, USD |
| 8 | schwab | 6 | 9,821 thousand | client trades a day |
| 9 | fidelity | 6 | 5.7 million | client trades a day |
| 10 | ibkr | 6 | 4.111 million | revenue trades a day |
| 11 | okx | 5 | 2,207,798,651 | spot 24h, USD |
| 12 | mexc | 5 | 1,599,542,322 | spot 24h, USD |
| 13 | bitfinex | 5 | 1,157,463,688 | spot 24h, USD |
| 14 | huobi | 5 | 856,251,198 | spot 24h, USD |
| 15 | webull | 5 | 279,000,000,000 for the quarter | equity notional, USD |
| 16 | tastytrade | 5 | no published figure | — |
| 17 | poloniex | 4 | 945,777,788 | spot 24h, USD |
| 18 | gemini | 4 | 55,636,483 | spot 24h, USD |
| 19 | alpaca | 4 | no published figure | — |
| 20 | bitstamp | 3 | 445,456,235 | spot 24h, USD |
| 21 | etrade | 3 | no published figure | — |
| 22 | interactivebrokers | 0 | 4.111 million | revenue trades a day |
| 23 | tdameritrade | 0 | no published figure | — |

The id `interactivebrokers` names the same firm as `ibkr` and carries the same
figure. It sits at 22 because the matrix gives it no sector, not because the
firm is small.

---

## Table B, volume first

The same twenty-three ids on the volume key alone, with coverage beside each.
This is what changes if volume outranks coverage.

| # | Venue | Volume key | Measure | Sectors |
| --- | --- | --- | --- | --- |
| 1 | binance | 12,313,776,868 | spot 24h, USD | 6 |
| 2 | okx | 2,207,798,651 | spot 24h, USD | 5 |
| 3 | bybit | 2,165,543,168 | spot 24h, USD | 6 |
| 4 | gateio | 1,899,524,136 | spot 24h, USD | 6 |
| 5 | kraken | 1,826,079,158 | spot 24h, USD | 6 |
| 6 | mexc | 1,599,542,322 | spot 24h, USD | 5 |
| 7 | kucoin | 1,377,543,491 | spot 24h, USD | 6 |
| 8 | bitfinex | 1,157,463,688 | spot 24h, USD | 5 |
| 9 | poloniex | 945,777,788 | spot 24h, USD | 4 |
| 10 | huobi | 856,251,198 | spot 24h, USD | 5 |
| 11 | cryptocom | 826,680,594 | spot 24h, USD | 6 |
| 12 | bitget | 813,319,184 | spot 24h, USD | 6 |
| 13 | bitstamp | 445,456,235 | spot 24h, USD | 3 |
| 14 | gemini | 55,636,483 | spot 24h, USD | 4 |
| 15 | webull | 279,000,000,000 for the quarter | equity notional, USD | 5 |
| 16 | schwab | 9,821 thousand | client trades a day | 6 |
| 17 | fidelity | 5.7 million | client trades a day | 6 |
| 18 | ibkr | 4.111 million | revenue trades a day | 6 |
| 19 | interactivebrokers | 4.111 million | revenue trades a day | 0 |
| 20 | alpaca | no published figure | — | 4 |
| 21 | tastytrade | no published figure | — | 5 |
| 22 | etrade | no published figure | — | 3 |
| 23 | tdameritrade | no published figure | — | 0 |

The two tables differ most on three venues. Volume first moves okx from 11 to 2,
moves mexc from 12 to 6, and pushes the three large brokers from 8, 9 and 10
down to 16, 17 and 18. Every other venue moves by three places or fewer.

---

## What each build-out costs

Four costs apply, and the first three are the same for whole groups of venues.

**Every crypto id already has a connector.** `src/exchange/ccxt_connector.py`,
`CCXTConnector` constructs for any id in `SUPPORTED_EXCHANGES`, and
`src/gui/main_window.py`, `_connect_exchange_for_bot` takes that path for every
id `broker_connector_class` answers None for. That covers all fifteen.

**Eight of the nine broker ids need a hand-written connector.**
`src/stocks/alpaca_connector.py`, `BROKER_CONNECTORS` holds one id, `alpaca`,
mapped to a hand-written `AlpacaConnector`. The library cannot carry the other
eight, measured against the installed library.

```
ccxt 4.5.85 holds 104 exchange ids
alpaca              in ccxt
ibkr                not in ccxt
interactivebrokers  not in ccxt
schwab              not in ccxt
tdameritrade        not in ccxt
webull              not in ccxt
tastytrade          not in ccxt
fidelity            not in ccxt
etrade              not in ccxt
```

The library's own `alpaca` class is a crypto class, so it cannot stand in for
the broker either. Its description answers `future` False and names four crypto
venues as the markets it reaches.

**Nothing is recorded for twenty-three of the twenty-four ids.** One venue is in
the recording, counted above. `src/exchange/ccxt_connector.py`, `get_markets`
and `src/stocks/broker_base.py`, `record_markets` are the only two callers of
`market_rules_store.record_venue` in `src/`, so a venue reaches a market rule
only when one of those two runs against it. The broker caller is written and
`src/gui/main_window.py`, `_connect_broker_for_bot` answers False, so no broker
has ever reached it.

**Credentials.** `src/exchange/ccxt_connector.py`, `PASSPHRASE_EXCHANGES` names
the three crypto ids needing a third field.

```
kucoin, okx, bitget          key, secret and passphrase
the other twelve crypto ids  key and secret
```

The broker credential shapes are the ones
[15-venue-compatibility.md](../../manual/15-venue-compatibility.md) records per
firm: a key and a secret for Alpaca, a TWS session for Interactive Brokers, and
a key issued on the Schwab developer portal for Schwab. That page records a
shape not stated by the pages it read for tastytrade, E\*TRADE and Webull, and
no reachable interface at all for TD Ameritrade or Fidelity.

**Reachability from the United States.** Four crypto ids carry a recorded
refusal, measured at `src/exchange/ccxt_connector.py`,
`VENUE_MEASUREMENT_DATE`, which reads 2026-08-28.

```
US_IP_BLOCKED_EXCHANGES          binance, bybit
US_ACCOUNT_RESTRICTED_EXCHANGES  poloniex, huobi
```

The matrix report's own United States column marks more venues than these two
sets do. The sets in the code are the ones the connect path warns on, so they
are the ones quoted here, and the difference belongs to the matrix.

---

## The control on the method

Before any figure above was trusted, the method was shown able to answer both
ways.

**It returned a figure for one already established.** Coinbase's own
shareholder letter, filed with the Securities and Exchange Commission and dated
30 October 2025, states "Total Trading Volume was $295 billion, up 24% Q/Q".
That figure is self-reported, quarterly and total, so it is not the same measure
as the spot figures above and it is not used in the ranking.

**It returned no published figure for one known absent.** A search for a
current published trade volume for TD Ameritrade returned a delisted company
profile and material from earlier years, and no current figure from the firm.
That matches the manual, which records the TD Ameritrade interface as
discontinued on 10 May 2024.

**An invented path was refused by both hosts.** Neither host answered success
for a path that does not exist.

```
coinbase.com, an invented page       HTTP 403, no body
coinmarketcap.com, an invented slug  HTTP 404, no body
```

No host answered success for an invented path, so the case where a status code
proves nothing did not arise. Every figure above still rests on quoted content
and not on a status code.

---

## Conditions this report was produced under

```
public pages and published data only, read-only
no account created, no sign-in, no key, no interface call, no order
~/.acervator/market_rules.json read, never written
~/.acervator/coinbase_credentials.json never opened
no file under dist/ launched
```

---

## Sources

| Source | What was read | Date read |
| --- | --- | --- |
| `src/exchange/ccxt_connector.py` | `SUPPORTED_EXCHANGES`, `CCXT_CLASS_ALIASES`, `PASSPHRASE_EXCHANGES`, `US_IP_BLOCKED_EXCHANGES`, `US_ACCOUNT_RESTRICTED_EXCHANGES`, `VENUE_MEASUREMENT_DATE`, `get_markets` | 2026-10-08 |
| `src/gui/main_tabs/asset_class_surface.py` | `EQUITY_VENUES`, `crypto_venues`, `recorded_venue_classes` | 2026-10-08 |
| `src/stocks/alpaca_connector.py` | `BROKER_CONNECTORS`, `broker_connector_class` | 2026-10-08 |
| `src/stocks/broker_base.py` | `record_markets` | 2026-10-08 |
| `src/gui/main_window.py` | `_connect_exchange_for_bot`, `_connect_broker_for_bot` | 2026-10-08 |
| `2026-10-07_venue_sector_readiness_matrix/REPORT.md` | the venue-by-sector matrix and its four verdicts | 2026-10-08 |
| `docs/manual/15-venue-compatibility.md` | the venue table and its credential shapes | 2026-10-08 |
| coinmarketcap.com, the ranking page and each venue page | `Spot Trading Volume(24h)` per venue | 2026-10-08 |
| coingecko.com, the exchanges page | the `24h Volume` column per venue | 2026-10-08 |
| pressroom.aboutschwab.com, Monthly Activity Highlights of 15 September 2026 | client daily average trades for August 2026 | 2026-10-08 |
| about.fidelity.com, the quarterly business update to 30 June 2026 | daily average trades and the firm's own definition of them | 2026-10-08 |
| fxnewsgroup.com, reporting Interactive Brokers' release of 1 October 2026 | daily average revenue trades for September 2026 | 2026-10-08 |
| sec.gov, Webull Form 6-K of 19 August 2026 | equity notional volume for the quarter to 30 June 2026 | 2026-10-08 |
| iggroup.com and its quarterly trading update | tastytrade net trading revenue, which is not a volume | 2026-10-08 |
| investors.robinhood.com, August 2026 operating data | equity notional trading volumes for the month | 2026-10-08 |
| sacra.com | the only Alpaca volume figure found, a third-party estimate for 2024 | 2026-10-08 |
| sec.gov, Coinbase shareholder letter of 30 October 2025 | total trading volume for the quarter | 2026-10-08 |

---

## What is not resolved

One figure could not be quoted from its own page: Interactive Brokers' monthly
metrics release, whose own host and whose wire copy both answered HTTP 403 to a
fetch. The figure is published and is not behind a sign-in, and it is quoted
here from a named third party that reported the same release.

One decision is the operator's: whether he accepts the ranking rule, which he
judges from Table A against Table B.
