# Multi-sector venue models in other auto-traders

Reference. Twelve other trading projects set beside this platform on the six
questions that came out of its own venue work, and a closing list of
refinements worth considering.

## What this compares, and what it does not

Each project below was settled from its own public source and its own published
documentation. No blog post, no comparison site, and no claim off a marketing
page was used as evidence of a capability. Nothing was authenticated anywhere,
and no order was placed, priced, previewed or cancelled on any venue. Every
count says what was counted and where.

What this does **not** compare: execution speed, backtest fidelity, data
handling, strategy libraries, fees, community size, or how pleasant any of these
is to operate. It compares one thing only — how much of a venue's own rulebook
each project models, and where the asset sector comes from. A project that
scores thin here may be excellent at what it was built for. Hummingbot was built
for crypto market making; it is not trying to trade a share.

Two of the twelve could not be settled in full from public source, and both are
named in their own section. Jesse's live execution lives in a closed package,
and StockSharp's venue connectors live in a second repository that is public but
separate from the one most readers will open.

The Acervator figures below were read off this tree at commit `8acff40`. They
are counts of what is declared in source, not of what has traded.

## The six axes, side by side

Venue counts first. Each cell names the directory or list it was counted from.

| Project | Venues shipped, and what was counted |
| ------- | ------------------------------------ |
| Acervator | **26** venue ids, 24 of which name a live venue; counted from `SUPPORTED_EXCHANGES` (16), `EQUITY_VENUES` (10) and the Robinhood id |
| Hummingbot | **46** connector directories: 26 spot venues plus 20 perpetual, counted in `connector/exchange/` and `connector/derivative/` |
| NautilusTrader | **14** venue adapter crates plus 3 data-only and 1 sandbox, counted in `crates/adapters/`; `ADAPTERS.md` names 17 official and 3 community |
| QuantConnect LEAN | **37** files matching `*BrokerageModel.cs` in `Common/Brokerages/`, of which Default, Public and AlphaStreams name no venue |
| Freqtrade | **22** classes deriving from `Exchange` in `freqtrade/exchange/`; **15** names in `SUPPORTED_EXCHANGES` |
| Jesse | **38** `exchange_info` entries in `jesse/info.py`; **10** candle driver directories |
| OctoBot | **37** named venue tentacles in `Trading/Exchange/`, plus one generic ccxt fallback |
| vn.py | **18** trading gateways in its own README; **30** gateway packages found on the `vnpy` account |
| StockSharp | **383** connector directories in the separate `StockSharp/Connectors` repository; its README groups them 34 crypto, 165 stock/futures/options, 17 forex, 155 DEX |
| Backtrader | **3** live brokers in `backtrader/brokers/`, the fourth being the backtest broker |
| ccxt | **103** exchange classes, counted in the `exchanges` list and cross-checked against the TypeScript source file count, version 4.5.85 |
| Alpaca SDK | **1** venue, with **14** execution venues reported behind it in `AssetExchange` |
| IBKR SDKs | **no** static venue list; `ContractDetails.ValidExchanges` answers it per contract at runtime |

Now the six axes. **Sector** means a named asset class — crypto, stocks,
commodities, forex, indices, futures — not spot versus perpetual.

| Project | Sector concept | Where the sector comes from | Session rule | Cash-amount market buy | Equities | Per-venue specialisation |
| ------- | -------------- | --------------------------- | ------------ | ---------------------- | -------- | ------------------------ |
| Acervator | 6 sectors, every venue placed in each it offers | the venue's own published category field on 7 venues; a registry and two cited tables elsewhere | 2 named sessions, changing the unit rule and the order type | per venue, 5 venues cited | yes, 9 broker ids | 6 sector variants plus 5 order-formatting mechanics |
| Hummingbot | none; spot versus perpetual | the parent directory name | not modelled | not modelled | none | 3-level budget checker |
| NautilusTrader | 7 asset classes, 12 instrument classes | the instrument type built, with two adapters reading the venue's own field | not modelled | not modelled | yes, 1 adapter | order factory and instrument conformance |
| LEAN | 12 security types | a shipped static table of 10,824 rows | 552 market-hours entries, and one brokerage refuses a non-limit order outside hours | not modelled | yes, most of the field | 34 brokerage models with their own order-type maps |
| Freqtrade | none; spot, margin, futures | ccxt's own normalised market fields | not modelled | yes, side-aware, per venue | none | `_ft_has` capability table per venue |
| Jesse | 7 asset classes, declared | a hand-written table plus one data provider's own type codes | advisory only, not enforced | helper only | data only, never live | simulation model per asset class |
| OctoBot | none; spot, future, margin, option | the operator's configuration, checked against a per-venue allowlist | yes, per venue and per order type, on 1 venue | yes, buy side only, 9 venues | none | about 20 class flags per venue |
| vn.py | 13 products | the venue's own field through a per-gateway table | not modelled | not modelled | yes, and no crypto at all | per-venue order splitting |
| StockSharp | 26 security types | mixed; per connector, some read the venue, some do not | 227 exchange boards with working time, not wired to orders | 1 connector of 383 | yes, the largest group | 232 per-venue order conditions |
| Backtrader | none | nothing; no asset-class field on a feed | data filtering only | converted to units client-side | yes, 2 of 3 brokers | commission scheme per data feed |
| ccxt | 1 non-crypto flag: stock | each class derives it from that venue's payload; the raw row is kept | not modelled | yes, an option plus 28 declarations | tokenised only, 1 class | `has` map, 241 keys, and a `features` map on 93 classes |
| Alpaca SDK | 10 asset classes | Alpaca's own `class` field | the flag is published; the SDK does not enforce the rule | yes, in an enforced either-or with quantity | yes, equities first | runtime asset flags, hardcoded order-type matrix |
| IBKR SDKs | 12 to 15 security types, depending on the page | the operator supplies it and the venue echoes it back | `Order.outsideRth`, plus trading and liquid hours per contract | yes, mandatory on a crypto market buy | yes, the widest | `ContractDetails.OrderTypes` per contract |

Eligibility gets its own row, because the answer is almost uniform.

| Project | Does it record that a venue refuses an account from the operator's jurisdiction |
| ------- | ------------------------------------------------------------------------------- |
| Acervator | yes for crypto: 2 ids refused by address and 6 by account terms, and the refusal reaches the venue picker's own label |
| every other project in this comparison | no |

Eleven of the twelve answer this axis the same way: a separate venue object. A
US customer picks `binanceus` rather than `binance`, and must already know to.
Freqtrade states it in prose on its own exchanges page, OctoBot ships a
`binanceus` tentacle, Jesse holds a `BINANCE_US_SPOT` registry entry, and ccxt's
one geographic field names where the venue operates from rather than who it will
serve. OctoBot is the only one that learns about a refusal at all, and it learns
by being refused: it catches a permission error after the order has gone.

## Acervator, measured on this tree

Six sectors, held in one frozen set.

```
src/gui/main_tabs/asset_class_surface.py, in LAYERED_CLASSES
    crypto  stocks  commodities  forex  indices  futures_perps
```

The venue ids are three lists. Sixteen crypto venues, ten equity ids and the
Robinhood id make 26, and two of the ten name no live venue — one id was
discontinued and one duplicates the firm that `ibkr` already names. Twenty-three
of the 26 carry a row in the registry that lists the sectors beyond the one their
own list implies.

```
SUPPORTED_EXCHANGES        16 crypto venue ids
EQUITY_VENUES              10 ids, 8 firms
EXTRA_VENUE_CLASSES        23 ids carrying extra sectors
offered (venue, sector)    119 pairs
venues offering all six    12
```

Counted by sector, the offer runs crypto 23, stocks 21, commodities 21, indices
20, futures_perps 18 and forex 16. The method was to take the base sector each
list implies, add every sector the registry names, and keep only the six the
layered set holds. One older word, `derivatives`, sits in the registry and in
the display names and is not one of the six, so it was dropped from the count.

Where the sector comes from is two questions, and the manual separates them.
The registry answers what a venue could serve; a recording of real markets
answers what it does serve. Both are read.

```
src/gui/main_tabs/asset_class_surface.py, in venue_classes
src/gui/main_tabs/asset_class_surface.py, in venue_served_classes
src/gui/main_tabs/asset_class_surface.py, in venues_for_class
```

Underneath that, one market at a time, the classifier reads the venue's own
published asset-category field first and the ticker last.

```
src/exchange/ccxt_connector.py, in market_asset_class
src/exchange/ccxt_connector.py, in VENUE_ASSET_SECTOR_RECORDS
    cryptocom  gateio  mexc  kucoin  okx  okxus  bitget
```

Seven venues publish a category on a credential-free endpoint and the connector
reads it. The platform's reason for doing so is on the record, and it is a real
defect rather than a hypothetical. KuCoin's own currency list calls `NOK` the
Norwegian krone, because it is a deposit currency there, while the only market
under that code is a perpetual whose own record reads `STOCK` and `NASDAQ`. The
contract is Nokia. The manual's own table reads:

```
docs/manual/15-venue-compatibility.md, under "KuCoin, read on 2026-10-11"
    base  AMD  read before forex   true stocks
    base  NOK  read before forex   true stocks
    base  RON  read before forex   true futures_perps
```

Eleven KuCoin base codes carry a code the fiat-currency list holds, and nine of
the eleven are not a currency market. A code-derived sector got nine of eleven
wrong on one venue.

The per-market rulebook is one frozen record with twelve rules and a flag saying
whether a record was obtained at all.

```
src/exchange/base.py, in MarketRules
    min_amount        min_cost         amount_increment
    price_increment   quote_increment  contract_size
    session           buy_size_shapes  sell_size_shapes
    order_types       expiry_ms        settlement_days
    read
```

A recording persists eleven of the twelve. The settlement delay is **not**
persisted — it is absent from the store's own field lists, while the paper runner
and the back test both read it off the cited table instead.

```
src/exchange/market_rules_store.py, in RULE_FIELDS        7 numeric rules
src/exchange/market_rules_store.py, in TEXT_RULE_FIELDS   order_types, session
src/exchange/market_rules_store.py, in SHAPE_RULE_FIELDS  buy and sell shapes
src/exchange/market_rules_store.py  settlement_days  0 occurrences
src/exchange/market_rules_store.py  amount_increment 2 occurrences  (control)
```

Where a venue publishes no record, four cited tables answer, keyed by sector and
venue together.

```
src/trading/scrumming/sizing.py, in CITED_UNIT_RULES        45 rows,  9 venues
src/trading/scrumming/sizing.py, in CITED_VENUE_ORDER_TYPES 60 rows, 14 venues
src/trading/scrumming/sizing.py, in CITED_VENUE_SESSIONS    23 rows,  8 venues
src/trading/scrumming/sizing.py, in CITED_VENUE_SETTLEMENT   6 rows,  4 venues
src/trading/scrumming/sizing.py, in CITED_CASH_MARKET_BUY    5 venues
```

The session is the axis that changes an order rather than describing it. Two
sessions are named, and a session can narrow the unit rule, the order type and
the permitted size shapes at a given moment.

```
src/trading/scrumming/sizing.py, in SESSION_CONTINUOUS
src/trading/scrumming/sizing.py, in SESSION_US_EQUITY
src/trading/scrumming/sizing.py, in session_unit_rule
src/trading/scrumming/sizing.py, in session_order_types
src/trading/scrumming/sizing.py, in session_size_shapes
src/trading/scrumming/sizing.py, in permitted_order_shape
```

Size shapes are declared per side, which is the part no other project in this
comparison has. A market names which of three shapes a buy may take and which a
sell may take, and those two sets differ.

```
src/trading/scrumming/sizing.py, in SIZE_SHAPES
    whole units   fractional units   cash amount
```

Eligibility is machine-readable on the crypto side and reaches the operator's
own picker label.

```
src/exchange/ccxt_connector.py, in US_IP_BLOCKED_EXCHANGES          2 ids
src/exchange/ccxt_connector.py, in US_ACCOUNT_RESTRICTED_EXCHANGES  6 ids
src/exchange/ccxt_connector.py, in restriction_note
src/exchange/ccxt_connector.py, in exchange_label
```

On the broker side it is not machine-readable. The per-sector and per-state
refusals each broker publishes were read and written into comments beside the
registry rows, and into the per-venue audit pages, rather than into a field
anything can query.

```
src/gui/main_tabs/asset_class_surface.py, in EXTRA_VENUE_CLASSES
    comments naming eligibility rules, read 2026-10-11
docs/audits/2026-10-11_ibkr_wired_sectors/REPORT.md
    commodities refuses four named states; crypto names 103 countries
```

The variant is the sector-shaped specialisation, and it has a second axis for
the one order-formatting difference a venue's own protocol puts on a market.

```
src/trading/scrumming/sizing.py, in SECTOR_VARIANTS       6, one per sector
src/trading/scrumming/sizing.py, in VARIANT_WHOLE_UNIT
src/trading/scrumming/sizing.py, in VARIANT_SECTOR_UNNAMED
src/trading/scrumming/sizing.py, in MECHANIC_MARKETS      5 mechanics
src/trading/scrumming/sizing.py, in sector_variant
src/trading/scrumming/sizing.py, in venue_variant
```

One broker shows the per-sector mechanics in code, keyed on the venue's own
security-type word.

```
src/stocks/ibkr_connector.py, in ASSET_CLASS_SECTORS
    cash > forex   cmdty > commodities   crypto > crypto
    fund > stocks  ind > indices         stk > stocks
src/stocks/ibkr_connector.py, in FRACTIONAL_ASSET_CLASSES   cash, crypto
src/stocks/ibkr_connector.py, in LIMIT_ONLY_ASSET_CLASSES   cmdty, crypto
```

## QuantConnect LEAN

Twelve security types, in one enum, in the common assembly.

```
Common/Global.cs, in SecurityType
    Base  Equity  Option  Commodity  Forex  Future  Cfd
    Crypto  FutureOption  Index  IndexOption  CryptoFuture
```

The per-market rulebook is a comma-separated file shipped in the repository, and
it is the largest such table in this comparison. Downloaded and counted:

```
Data/symbol-properties/symbol-properties-database.csv
    rows                                10,824
    distinct market values                  27
    distinct type values                    10
    rows carrying lot_size              10,824
    rows carrying contract_multiplier   10,824
    rows carrying minimum_order_size     9,524
    columns  market, symbol, type, description, quote_currency,
             contract_multiplier, minimum_price_variation, lot_size,
             market_ticker, minimum_order_size, price_magnifier,
             strike_multiplier
```

This is a static table, not a live read of a venue. It is the opposite design
choice from reading a venue's own category field, and it buys something real:
every row has a lot size and a multiplier whether the venue publishes one today
or not. It costs something real too, because the table goes stale the moment a
venue changes a step and nothing in the running program notices.

The session model is the part no other project approaches. A second shipped file
holds the hours:

```
Data/market-hours/market-hours-database.json
    entries                                552
    entries with a premarket segment       203
    segment states  premarket  market  postmarket
    key shape       Equity-usa-[*]
```

And the session rule changes an order rather than describing it. One brokerage
model refuses an extended-hours order that is not a limit order with a
day-length time in force, before the order leaves:

```
Common/Brokerages/AlpacaBrokerageModel.cs, in CanSubmitOrder
    var supportsOutsideTradingHours =
        (order.Properties as AlpacaOrderProperties)?.OutsideRegularTradingHours ?? false;
    if (supportsOutsideTradingHours &&
        (order.Type != OrderType.Limit || order.TimeInForce is not DayTimeInForce))
```

Specialisation is the brokerage model, and it is per venue and per security type
at once. The Alpaca model holds a map from security type to the order types that
venue accepts for it.

```
Common/Brokerages/AlpacaBrokerageModel.cs, in _supportOrderTypeBySecurityType
    Equity       Market Limit StopMarket StopLimit TrailingStop
                 MarketOnOpen MarketOnClose
    Option       Market Limit ComboMarket ComboLimit
    IndexOption  Market Limit ComboMarket ComboLimit
    Crypto       Market Limit StopLimit
```

Counted in that directory: 49 files, 37 of them named `*BrokerageModel.cs`, and
three of the 37 name no venue. The Interactive Brokers model lists twelve order
types of its own and refuses market-on-close for an instrument that is not an
equity, a future or a contract for difference.

What LEAN does not model: a market buy that spends a cash amount rather than a
unit count, and whole units versus fractional stated per side. `SettlementType`
exists with two members, physical delivery and cash, and it names the kind of
settlement rather than the days a venue takes.

## NautilusTrader

The taxonomy is two enums, declared in the model crate, and it is the cleanest
separation in the field: what the thing *is*, and what *form* the contract takes.

```
crates/model/src/enums.rs, in AssetClass
    FX  Equity  Commodity  Debt  Index  Cryptocurrency  Alternative

crates/model/src/enums.rs, in InstrumentClass
    Spot  Swap  Future  FuturesSpread  Forward  Cfd  Bond
    Option  OptionSpread  Warrant  SportsBetting  BinaryOption
```

The instruments directory holds 23 files, 19 of which name an instrument type.
One of the 19 is worth naming here, because it is the shape a crypto venue's
tokenised share takes:

```
crates/model/src/instruments/tokenized_asset.rs
crates/model/src/instruments/equity.rs
crates/model/src/instruments/index_instrument.rs
crates/model/src/instruments/commodity.rs
```

The per-instrument rulebook is as complete as this platform's. Read off the
perpetual contract:

```
crates/model/src/instruments/crypto_perpetual.rs
    size_increment  size_precision  min_quantity  max_quantity
    min_notional    max_notional    multiplier    lot_size
```

Where the asset class comes from is the sharp finding, and it cuts both ways.
The OKX adapter does read that venue's own numbered category field, mapping all
five published values:

```
crates/adapters/okx/src/common/parse.rs, in okx_inst_category_to_asset_class
    Crypto    > AssetClass::Cryptocurrency
    Equity    > AssetClass::Equity
    Commodity > AssetClass::Commodity
    Fx        > AssetClass::FX
    Debt      > AssetClass::Debt
    Unknown or absent > AssetClass::Alternative
```

But that function has exactly one caller in production code, and it is the
parser for event contracts. Measured on the downloaded file: four occurrences of
the mapper's name, one being its own definition, one in
`parse_event_contract_instrument`, and two inside tests. For every OKX spot
pair, perpetual, future and option, the asset class comes from the instrument
type instead — and for two of those types it is computed from the currency codes
or fixed outright:

```
crates/model/src/instruments/currency_pair.rs, in asset_class
    either leg is a crypto currency  > AssetClass::Cryptocurrency
    otherwise                        > AssetClass::FX

crates/model/src/instruments/crypto_perpetual.rs, in asset_class
    always  AssetClass::Cryptocurrency
```

So a tokenised share listed as a spot pair answers Cryptocurrency, and an
equity-underlying perpetual answers Cryptocurrency. That is the same shape as
the `NOK` defect this platform repaired, in a project whose taxonomy is well
able to express the right answer.

The control that the search would have fired: the Interactive Brokers adapter
does read the venue's own word, through the same kind of lookup, with an escape
for a word it does not know.

```
crates/adapters/interactive_brokers/src/common/contracts.rs
    let sec_type_str = get_str("secType");
    IbSecurityType::from_str(&sec_type_str)
        .map_or_else(|_| SecurityType::Other(sec_type_str.clone()), ...)
```

## Hummingbot

Forty-six connector directories, every one crypto or crypto-shaped, and the
asset class is the parent folder's name.

```
hummingbot/client/settings.py, in AllConnectorSettings.create_connector_settings
    type=ConnectorType[type_dir.name.capitalize()]
```

The per-market rulebook is thirteen fields, and it carries two the others often
miss — a minimum notional and a separate quote-amount increment.

```
hummingbot/connector/trading_rule.pyx, in TradingRule
    trading_pair  min_order_size  max_order_size
    min_price_increment  min_base_amount_increment
    min_quote_amount_increment  min_notional_size  min_order_value
    max_price_significant_digits  supports_limit_orders
    supports_market_orders  buy_order_collateral_token
    sell_order_collateral_token
```

Sector, session and expiry are all absent, and each absence carries a control
from the same search over the same tree. Searching the package for `asset_class`,
`AssetClass` and `asset_category` returned zero files each, while the same
command returned 38 files for `min_notional_size` and 56 for
`supported_order_types`. Searching for session vocabulary returned zero files for
every term tried, while `close_time` returned 14 — so the instrument fires and
the model is genuinely not there.

Two things in that tree are worth the operator's attention, because neither is
labelled. One connector's own example pair is `EUR-USD` and its order-status map
carries `DONE_FOR_DAY` and a pending-approval state, which is traditional-market
session vocabulary; it sits under the perpetual folder with no sector marker.
Another connector reaches a regulated event-contract venue. The directory name is
the only classification, so both read as derivatives to the engine.

```
hummingbot/core/data_type/common.py, in OrderType
    MARKET  LIMIT  LIMIT_MAKER  AMM_SWAP  AMM_ADD  AMM_REMOVE
```

Forty-six connectors negotiate through that six-member vocabulary, and it holds
no stop order of any kind.

## Freqtrade

Twenty-two venue subclasses specialise a generic ccxt path, and the specialising
mechanism is a per-venue capability table that overrides the library's own
answers.

```
freqtrade/exchange/exchange_types.py, in FtHas
freqtrade/exchange/exchange.py, in Exchange._ft_has_default
freqtrade/exchange/gate.py, in Gate._ft_has and _ft_has_futures
```

Gate.io is the clearest case, because the same venue needs opposite answers for
spot and for futures. Freqtrade's own comment on the key says the library is
wrong often enough to need correcting:

```
freqtrade/exchange/exchange.py, in _ft_has_default
    marketOrderRequiresPrice
    "Override createMarketBuyOrderRequiresPrice where ccxt has it wrong"
```

This is the only project in the comparison besides Acervator that makes the
cash-amount market buy side-aware at framework level:

```
freqtrade/exchange/exchange.py, in _order_needs_price
    ordertype != "market"
    or (side == "buy" and createMarketBuyOrderRequiresPrice)
    or self._ft_has.get("marketOrderRequiresPrice", False)
```

Its minimum-order logic is the most careful of the field. It reconciles both
limit families rather than checking one, and its own docstring states the
contract — the value returned must satisfy the amount limit and the cost limit
at once.

```
freqtrade/exchange/exchange.py, in get_min_pair_stake_amount
freqtrade/exchange/exchange.py, in _get_stake_amount_limit
```

Sector does not exist. The whole taxonomy is three words, and the enum's own
docstring says so.

```
freqtrade/enums/tradingmode.py, in TradingMode
    SPOT  MARGIN  FUTURES
```

Searching the package for `expiry` returned zero files, with `contractSize`
returning two and `settle` six on the same command — so the perpetual-only
restriction is total rather than partial.

## Jesse

Jesse is the one project that declares an asset-class vocabulary and then does
not trade on it.

```
jesse/services/historical_data/contracts.py, in AssetClass
    CRYPTO  CURRENCY  EQUITY  FX  COMMODITY  INDEX  FUTURES

jesse/services/historical_data/contracts.py, in InstrumentType
    SPOT  STOCK  ETF  PERPETUAL  FUTURES_CONTRACT  INDEX
```

Four registry entries carry a non-crypto asset class, and every one of them is
marked as unavailable for live trading. Its own documentation states the reason
plainly: the traditional-market entries are a historical data source, and the
simulation model and leverage stay backtest settings. The default loop at the end
of the registry fills `crypto` for everything else.

The vocabulary reaches one decision in the whole tree. Searching the package for
`asset_class` returned nine occurrences: five registry literals, the default
loop, a dataclass field with its coercion, and one consumer choosing between a
365-day and a 252-day annualisation.

A real read of a provider's own category codes does exist, on the data side, and
it is finer-grained than anything else in this comparison — fourteen or more
security-type codes down to depositary receipts and structured products.

```
jesse/services/historical_data/massive_stocks.py, in MASSIVE_STOCK_TYPE_LABELS
```

Jesse also ships a split-adjusted data mode and a 252-day trading-year
annualisation, which are corporate-action and trading-calendar concepts that
appear in none of the other crypto-first projects.

The limit on any claim about Jesse's live venue mechanics: the execution layer is
a closed package imported by name, and the dictionary holding each venue's
minimum notional, minimum quantity and precisions has **no writer** in the open
repository. Its live rules cannot be settled from public source.

## OctoBot

Thirty-seven venue tentacles, no sector concept, and the richest per-venue flag
surface in the comparison. The asset class is chosen by the operator's
configuration and checked against a per-venue allowlist, rather than read from a
venue.

```
octobot_trading/exchanges/util/exchange_util.py, in get_exchange_type
octobot_trading/exchanges/types/rest_exchange.py, in RestExchange.get_supported_exchange_types
octobot_trading/enums.py, in ExchangeTypes
    SPOT  FUTURE  MARGIN  OPTION  UNKNOWN
```

OctoBot holds the one session rule in the four crypto-first projects, and it is
worth reading closely because it is shaped exactly like the rule this platform
needs. It is per venue, per order type, and it reads the venue's own published
session flags out of the raw market payload:

```
octobot_trading/exchanges/abstract_exchange.py, in AbstractExchange.is_market_open_for_order_type
Trading/Exchange/coinbase/coinbase_exchange.py, in Coinbase.is_market_open_for_order_type
    market order  > not market_status_info["limit_only"]
    limit order   > not market_status_info["cancel_only"]
```

Exactly one of 37 tentacles implements it; the base returns true for everything.
It gates the order type and never the size.

Its cash-amount market buy is buy-side-only by construction, and nine tentacles
opt in. There is no sell-side counterpart function at all, and the comment gives
the reason — predicting the exact amount spent.

```
octobot_trading/exchanges/types/rest_exchange.py
    RestExchange.ENABLE_SPOT_BUY_MARKET_WITH_COST
    RestExchange._create_market_buy_order
```

Contract size changes the order rather than describing it, which matters for any
venue that counts contracts rather than units:

```
octobot_trading/exchanges/types/rest_exchange.py, in RestExchange.create_order
    quantity = quantity / self.get_contract_size(symbol)
```

And one measured figure in that tree is the loudest empirical argument in this
whole comparison for not trusting a venue's published metadata. A per-venue
repair flag appears 28 times across the 37 tentacles, backed by a module that
reconstructs a missing amount minimum from a cost minimum and vice versa.

```
octobot_trading/exchanges/util/exchange_market_status_fixer.py
Trading/Exchange/*  FIX_MARKET_STATUS  28 occurrences
```

## vn.py

Thirteen products and forty-nine exchange members, with no crypto venue at all.
Searching the core package and both READMEs for three major crypto venue names
returned zero files each, against a control of four files for the domestic
futures protocol and four for Interactive Brokers.

```
vnpy/trader/constant.py, in Product
    EQUITY  FUTURES  OPTION  INDEX  FOREX  SPOT  ETF
    BOND  WARRANT  SPREAD  FUND  CFD  SWAP
```

The sector comes from the venue's own field through a per-gateway translation
table, and the table is the authority on what is tradable. Two gateways show two
incompatible failure modes for a word the table does not hold. One discards the
instrument before the platform sees it, under a comment meaning "filter
unsupported types"; the other indexes the table without a guard, so a new venue
category raises.

```
vnpy_ib/vnpy_ib/ib_gateway.py, in IbApi.contractDetails
    product = PRODUCT_IB2VT.get(ib_contract.secType, None)
    if not product: return

vnpy_xtp/vnpy_xtp/gateway/xtp_gateway.py
    product = PRODUCT_XTP2VT[data["ticker_type"]]
```

The per-contract record carries a contract multiplier, a price tick and a
minimum volume, and no size step — so the minimum does double duty as the step
when an order is rounded.

```
vnpy/trader/object.py, in ContractData
    symbol  exchange  name  product  size  pricetick
    min_volume  max_volume  stop_supported  net_position
    history_data  option_strike  option_underlying  option_type
    option_listed  option_expiry  option_portfolio  option_index
```

Its per-venue specialisation is the one genuinely novel mechanism in this
comparison, and it is not a capability flag. One strategy intent becomes several
venue-shaped orders, because two Chinese futures venues price a close of today's
position differently from a close of yesterday's.

```
vnpy/trader/converter.py, in PositionHolding.convert_order_request_shfe
vnpy/trader/converter.py, in PositionHolding.convert_order_request_lock
vnpy/trader/converter.py, in OffsetConverter.convert_order_request
vnpy/trader/constant.py, in Offset
    NONE  OPEN  CLOSE  CLOSETODAY  CLOSEYESTERDAY
```

A caution on where quantisation happens: the core engine's send path performs no
validation and forwards to the gateway. Rounding onto the price tick and the
volume step lives one layer up, in the strategy application, so a path that does
not go through that application gets no quantisation.

```
vnpy/trader/engine.py, in MainEngine.send_order
vnpy_ctastrategy/engine.py, in CtaEngine.send_order
```

## StockSharp

The widest security-type vocabulary of any project read here, and 383 shipped
connectors — in a second repository, which its own README points to.

```
Messages/SecurityTypes.cs, in SecurityTypes
    Stock  Future  Option  Index  Currency  Bond  Warrant
    Forward  Swap  Commodity  Cfd  News  Weather  Fund
    Adr  CryptoCurrency  Etf  MultiLeg  Loan  Spread
    Gdr  Receipt  Indicator  Strategy  Volatility  Repo
```

Twenty-six members. Its README groups the connectors by sector: 34 crypto, 165
stock, futures and options, 17 forex and 155 decentralised. The equities side is
the largest group rather than an afterthought.

Where the sector comes from is decided per connector, and both behaviours ship.
Some adapters read the venue's own category string; others set the type from
which endpoint was called, with no venue field consulted at all.

```
Connectors/InteractiveBrokers/Native/IBSocketHelper.cs   case "STK":
Connectors/OpenMarkets/OpenMarketsExtensions.cs          "equities" "equity" "stock"
Connectors/Binance/Native/Extensions.cs
    a switch on the adapter's configured section, not on a venue field
```

Session hours per venue are modelled thoroughly and are not wired to an order.
Two hundred and twenty-seven exchange boards are declared, many with their own
working time, and a helper answers whether a moment is trading time — but nothing
in the core makes an order's type or size depend on the answer.

```
BusinessEntities/ExchangeBoard.cs       WorkingTime  TimeZone  ExpiryTime
BusinessEntities/ExchangeBoard_Instances.cs   227 static boards
Algo/TraderHelper.cs, in IsTradeTime
```

The per-venue order model is an abstract condition object with 232 subclasses,
one per connector that needs one. Five of them carry an extended-hours flag, and
one of 383 models a cash amount for a fractional market order.

```
Messages/OrderCondition.cs                        abstract base
232 subclasses, one per connector that needs one
Connectors/SnapTrade/SnapTradeOrderCondition.cs   NotionalValue
Connectors/SnapTrade/SnapTradeOrderCondition.cs   IsExtendedHours
```

One finding there is a caution rather than a credit, and it is the same class of
defect as putting a sector in the wrong field. There is no minimum-notional
property in the platform, so the one connector that reads a venue's minimum
notional writes it into a property its own documentation calls the minimum volume
for an underlying security, grouped under derivatives.

```
Connectors/Binance/BinanceMessageAdapter_MarketData.cs
    UnderlyingSecurityMinVolume = notionalFilter?.MinNotional
```

And its strategy helper does not consult the contract it knows about. The order
builder sets a price and a volume and returns, without touching the volume step,
the minimum volume, the multiplier or the price-shrinking helper that all exist
in the same assembly.

```
Algo.Strategies/Strategy.cs, in CreateOrder
```

## Backtrader and its live forks

Three live brokers, and no asset-class field on a data feed anywhere. The feed's
own parameter list holds a session start and end and a calendar, and nothing
naming a product.

```
backtrader/feed.py, in AbstractDataBase.params
    dataname  name  compression  timeframe  fromdate  todate
    sessionstart  sessionend  filters  tz  tzinput  qcheck  calendar
```

The only notion of an asset class is a broker-side commission scheme the operator
sets. It decides whether profit and loss is computed stock-style or
futures-style, and nothing reads it from a venue.

```
backtrader/comminfo.py, in CommInfoBase.params
    commission  mult  margin  commtype  stocklike  percabs
    interest  interest_long  leverage  automargin
```

One place a venue category appears, and it is guessed from how the operator spelt
the symbol rather than read back from the venue:

```
backtrader/feeds/ibdata.py, in IBData.parsecontract
    six-digit token          > sectype FUT
    a digit token otherwise  > sectype OPT
    FUT with a strike        > sectype FOP
```

Two measured facts matter for a reader considering it. Cash-derived sizing floors
to a whole unit in both branches, so a cash target cannot express a fractional
unit even though a direct order accepts a float:

```
backtrader/comminfo.py, in CommInfoBase.getsize
    int(self.p.leverage * (cash // self.get_margin(price)))
    int(self.p.leverage * (cash // price))
```

And no maintained fork has added a live venue. Four forks were listed, including
the only one still being pushed, and all four carry the same four stores and four
brokers as the original. Third-party crypto stores exist as separate packages and
were not read, so no claim is made about them.

## ccxt as a library

One hundred and three exchange classes, counted twice and diffed, in version
4.5.85. The unified market record is the field that matters here, because it is
what every ccxt-based project in this comparison inherits.

```
ts/src/base/types.ts, in MarketInterface
    type  spot  margin  swap  future  option
    index?  stock?  prediction?  contract  linear  inverse  quanto?
    settle  settleId  contractSize  expiry  expiryDatetime
    strike  optionType  precision  limits  info
```

ccxt has grown exactly one non-crypto asset-class flag, and its manual documents
it under the market-structure heading as a boolean saying whether the market
represents a stock instrument. Counted across the TypeScript sources, one class
sets that market flag, reading it off a dedicated equity-market endpoint. Three
other files matching the same search are name collisions — two venues call the
base currency "stock", and one uses the word for a transfer account. A count that
did not read every hit would have been wrong by a factor of four.

The raw venue row survives, which is what makes a category read possible at all.
The manual's own words for the `info` field are that it holds the original
unparsed market info from the exchange, and that its contents depend on the
exchange. So OKX's numbered category is reachable through ccxt, untyped.

The capability model is two maps. The older one is a method-availability map with
241 keys declared on the base class. The newer one is keyed by market type and
is the one that carries order semantics — and ccxt's own manual labels it a work
in progress that might be incomplete. Ninety-three of the 103 classes declare it.

```
ts/src/base/Exchange.ts   the has map, 241 keys
                          featuresGenerator, featuresMapper
features[type].createOrder
    triggerPrice  stopLossPrice  takeProfitPrice  timeInForce
    trailing  iceberg  marketBuyByCost  marketBuyRequiresPrice
```

Two details that bear directly on this platform's own venue work. First, the
option that decides whether a market buy names a cash amount is **not** in the
capability map at all — it is an option on the exchange instance, with a
differently named twin inside the newer map. A product grepping the capability
map for it finds nothing. Second, 28 of 103 classes declare that a market buy
with a cost is supported, and 10 declare the general cost-order method, so the
library's answer is available for roughly a quarter of its venues.

Session rules are absent. Searching the exchange sources for extended-hours and
outside-regular-hours terms returned one file, and all three hits in it sit inside
commented-out sample responses; the same search returned time-in-force in 92 of
103 files. ccxt carries no market calendar and no session window.

Eligibility is absent in the sense that matters. The one geographic field names
where the venue operates from, in the manual's own words, rather than who it will
serve — and one major class sets it to an empty list with a country named in a
comment beside it.

## Alpaca and IBKR as official SDKs

These two shape a product more than they are usually credited with, because what
they hand over decides what a product must build.

Alpaca publishes its own asset-class field, and the SDK names it with an alias
because the wire name is a reserved word in Python. Ten asset classes ship, and
the enum's own docstring names three of them.

```
alpaca/trading/enums.py, in AssetClass
    US_EQUITY  US_OPTION  CRYPTO  CRYPTO_PERP  TREASURY
    CORPORATE  GLOBAL_EQUITY  US_INDEX  US_EQUITY_CHAIN  IPO

alpaca/trading/models.py, in Asset
    asset_class: AssetClass = Field(alias="class")
```

Two things about that SDK are worth a product's attention. It drops any field it
does not declare — there is no raw-payload escape hatch, which is the sharp
contrast with ccxt's `info` field and decides the design for anything that needs
a venue's own category value. And it publishes the extended-hours rule in
documentation while enforcing nothing locally: the same file carries more than
twenty cross-field validators, including one refusing a limit price on a market
order, and none checks the extended-hours flag against the order type or the
time in force. The rejection is a round trip away.

```
alpaca/trading/requests.py, in OrderRequest   notional and qty, enforced either-or
alpaca/trading/models.py, in Asset            fractionable  min_order_size
                                              min_trade_increment  price_increment
alpaca/trading/models.py, in Calendar         session_open  session_close  settlement_date
```

IBKR is the opposite shape: one flat contract object where a security-type string
selects the sector, and the venue list answered per contract at runtime. It is
also the only library in this comparison that publishes the per-instrument
order-type list a product actually wants.

```
ContractDetails Class Reference, interactivebrokers.github.io/tws-api
    OrderTypes      "Supported order types for this product."
    ValidExchanges  MarketRuleIds  MinTick  PriceMagnifier
    MinSize  SizeIncrement  SuggestedSizeIncrement
    TradingHours  LiquidHours  TimeZoneId  StockType
```

It arrives as comma-separated text rather than structure, so a product splits and
interprets it. And the rules that list does not carry sit in prose on the
venue's own pages — its cryptocurrency page states that only market and limit
orders are supported, and that a market buy **must** carry a cash quantity. That
is the opposite polarity from ccxt, where the same thing is an option.

Three cautions a product should know. IBKR's own two pages disagree on the
security-type list, one enumerating twelve values and another documenting
fourteen instrument types with examples, so no single page is the complete list.
The package IBKR publishes to the Python index is missing the three fractional
size fields that are on its current documentation page, and carries no mention of
a crypto contract at all. And the wrapper most products are written against is
archived, with an actively maintained successor where those fields live.

## Refinements worth considering

Each entry is a proposal, ranked by what it is worth to a live operator. None of
them was built. Two constraints were held throughout: nothing here proposes a new
technology, language or runtime, and nothing here depends on an undocumented or
scraped venue endpoint.

### Refine one — persist the settlement delay with the rest of the record

| | |
| --- | --- |
| what another project does | LEAN ships a settlement model per security and keeps it beside the other security properties, in `Common/Securities/` |
| what Acervator does today | `MarketRules.settlement_days` is declared and is absent from the store's own field lists; the paper runner and the back test read it from the 6-row cited table instead |
| what the refinement would be | add the settlement field to the store's rule lists so a recorded market carries its own settlement delay, and keep the cited table as the fallback it already is for every other rule |
| what it would cost | `src/exchange/market_rules_store.py` gains one field name in one list and the reader gains one line; nothing else reshapes, because the record already declares the field and two consumers already read it |

This is first because it is the only entry that closes a gap inside a mechanism
that already works. Every other rule a venue publishes survives a recording. This
one does not, and a sale that spends cash the venue has not settled is a real
loss rather than a modelling nicety.

### Refine two — make the broker eligibility rules queryable, not only readable

| | |
| --- | --- |
| what another project does | nothing in this field does it; the closest is OctoBot, which learns a refusal by catching a permission error after the order has gone, in `octobot_trading/exchanges/types/rest_exchange.py` |
| what Acervator does today | the crypto side holds two machine-readable sets and surfaces the refusal in the picker label, through `restriction_note` and `exchange_label`; the broker side holds per-sector and per-state refusals as comments beside `EXTRA_VENUE_CLASSES` and in the per-venue audit pages |
| what the refinement would be | give each (venue, sector) pair an eligibility value in the same shape as the crypto sets, read off the readings already taken, so the Add Exchange form can say which sector a venue will not serve this operator before a credential is entered |
| what it would cost | one new table keyed the way the cited tables are keyed, a reader beside `restriction_note`, and the Add Exchange form's own row builder; the readings exist already, so this is a transcription from comments into a field rather than new research |

Second because the work is already done and sitting in the wrong place. One
broker refuses four named states for one sector, and today nothing the operator
can click tells him so.

### Refine three — widen the order-type vocabulary from two words to the venue's own list

| | |
| --- | --- |
| what another project does | IBKR publishes `ContractDetails.OrderTypes`, "Supported order types for this product", per contract; LEAN's Alpaca brokerage model holds a map from security type to the order types that venue accepts for it |
| what Acervator does today | two declared values, `ORDER_TYPES_WITH_MARKET` and `ORDER_TYPES_LIMIT_ONLY`, carried on 60 cited rows across 14 venues and on the recorded order-types field |
| what the refinement would be | hold the venue's own order-type list rather than a two-way verdict, so a market that takes a limit and a stop but not a market order is described rather than collapsed |
| what it would cost | the record's text field becomes a set, `order_types_for` and `market_replaces_market_order` change shape, the 60 cited rows are rewritten, and the store's text field list becomes a shape field list |

Third because the two-way verdict is right for the scrum today — a scrum needs a
market order or a limit priced to cross, and nothing else. The cost is real and
the benefit is latent. It becomes worth doing the first time a variant needs a
stop.

### Refine four — read the venue's own category on the venues that publish one and are not yet read

| | |
| --- | --- |
| what another project does | NautilusTrader's OKX adapter maps all five of that venue's published category numbers, in `crates/adapters/okx/src/common/parse.rs`; StockSharp's Interactive Brokers connector switches on the venue's own security-type word, in `Connectors/InteractiveBrokers/Native/IBSocketHelper.cs` |
| what Acervator does today | seven venues are read, in `VENUE_ASSET_SECTOR_RECORDS`; the rest fall to the registry, the two cited tables, and the base and quote codes |
| what the refinement would be | add a record for any remaining venue that publishes a category on a credential-free endpoint, which is a per-venue reading unit of the kind this tree has already run nineteen times |
| what it would cost | one entry in the records table per venue, plus the reading that justifies it; the connector's own notes already record that two venues were examined and correctly declined, so the pattern for a refusal is established |

Fourth because the method is proved and the remaining ground is narrow. The
connector's own comments show the work is not uniformly worth it: one venue
publishes a category that would cost two correct sectors to gain seven, and was
declined for that reason.

### Refine five — state the session rule as a refusal the gate can report

| | |
| --- | --- |
| what another project does | LEAN's Alpaca brokerage model refuses an extended-hours order that is not a limit order with a day-length time in force, and returns a message naming why; OctoBot's `is_market_open_for_order_type` asks per venue and per order type |
| what Acervator does today | `session_unit_rule`, `session_order_types` and `session_size_shapes` each narrow the order at a moment, and `size_shape_refusal` names why a shape is refused |
| what the refinement would be | nothing structural; the mechanism is present and arguably ahead of both. The refinement is the reporting shape — one refusal sentence per session rule, in the same form the shape refusal already takes, so a held tick says which session rule held it |
| what it would cost | one format string per session rule and one call site in the order gate; no record and no table changes |

Fifth because it is a legibility change rather than a capability one. It is
cheap, and a held tick that cannot say why is the shape of defect this tree keeps
finding.

### Refinements examined and not worth doing

**A shipped static rule table, the way LEAN ships 10,824 rows.** Rejected. It
answers a different question from the one this platform asks. LEAN's table
guarantees that every row has a lot size and a multiplier whether the venue
publishes one today or not, which serves a back test over a decade of history.
This platform's recording is taken from the venue and refuses rather than
guessing when a rule is absent, and the manual's own rule is that a missing value
is a rule the venue did not publish and never a rule of zero. A shipped table
would put a second answer beside the venue's, and one of the two would be
silently wrong.

**A per-venue capability map in the shape of ccxt's.** Rejected on the evidence
of the projects that use one. ccxt's own manual calls the map that carries order
semantics a work in progress that might be incomplete, 10 of 103 classes do not
declare it at all, and Freqtrade ships a key whose comment exists to correct the
library where it has it wrong. This platform already holds the per-venue answers
it needs in four cited tables keyed by sector and venue, which is the same
information with the venue's own reading behind each row.

**A fourth size shape, or a second contract-size path.** Rejected. Three shapes
cover every venue read so far, and the contract path already converts units to a
contract count where a venue counts contracts. No reading in nineteen venue units
produced a market needing a fourth shape.

**StockSharp's order-condition object, one subclass per venue.** Rejected. It
reaches 232 subclasses to express what the sector variant plus five
order-formatting mechanics express in this tree, and its own strategy builder
then ignores the contract's steps. The mechanism scales in connector count and
not in correctness.

**vn.py's order splitting, where one intent becomes several venue-shaped
orders.** Rejected for now, and worth remembering. It exists because two Chinese
futures venues price a close of today's position differently from a close of
yesterday's. No venue in this tree's nineteen readings has that rule. If one ever
does, this is the shape the answer takes, and `vnpy/trader/converter.py` is where
to read it.

**Hummingbot's budget checker, as a model for the variant.** Rejected. Its three
levels are base, asset class and venue, and exactly one venue has the third
level. The sector variant plus the order-formatting mechanic already covers the
same two axes, with every sector populated rather than one.

## One sentence this page does not have evidence to write

No count here says whether this platform is ahead or behind. The figures sit side
by side and they point both ways. This tree models a session rule, a per-side
size shape and a per-venue cash-amount buy that most of the field does not, and
it reads seven venues' own category fields where most of the field reads a
directory name. It also holds 2 session names against LEAN's 552 market-hours
entries, 2 order-type words against IBKR's per-contract list, and 26 venue ids
against ccxt's 103 classes and StockSharp's 383 connectors. Those are different
projects answering different questions, and the comparison is useful only one row
at a time.

