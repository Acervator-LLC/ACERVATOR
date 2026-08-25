"""
stock_assets.py — Stock universe and sector classification.

Provides curated lists of popular stocks organized by sector,
market cap tier, and index membership for the bot wizard.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StockInfo:
    """Information about a stock."""

    symbol: str
    name: str
    sector: str
    industry: str = ""
    market_cap_tier: str = "large"  # mega, large, mid, small
    index: str = ""  # S&P500, NASDAQ100, DOW30


# Major indices
DOW_30 = [
    StockInfo("AAPL", "Apple", "Technology", "Consumer Electronics", "mega", "DOW30"),
    StockInfo("MSFT", "Microsoft", "Technology", "Software", "mega", "DOW30"),
    StockInfo("AMZN", "Amazon", "Consumer Cyclical", "E-Commerce", "mega", "DOW30"),
    StockInfo("NVDA", "NVIDIA", "Technology", "Semiconductors", "mega", "DOW30"),
    StockInfo("GOOGL", "Alphabet", "Communication", "Internet", "mega", "DOW30"),
    StockInfo("JPM", "JPMorgan Chase", "Financial", "Banking", "mega", "DOW30"),
    StockInfo("V", "Visa", "Financial", "Payments", "mega", "DOW30"),
    StockInfo("JNJ", "Johnson & Johnson", "Healthcare", "Pharma", "mega", "DOW30"),
    StockInfo("WMT", "Walmart", "Consumer Defensive", "Retail", "mega", "DOW30"),
    StockInfo("UNH", "UnitedHealth", "Healthcare", "Insurance", "mega", "DOW30"),
    StockInfo(
        "HD", "Home Depot", "Consumer Cyclical", "Home Improvement", "mega", "DOW30"
    ),
    StockInfo("DIS", "Walt Disney", "Communication", "Entertainment", "mega", "DOW30"),
    StockInfo("MCD", "McDonald's", "Consumer Cyclical", "Restaurants", "mega", "DOW30"),
    StockInfo(
        "GS", "Goldman Sachs", "Financial", "Investment Banking", "mega", "DOW30"
    ),
    StockInfo("BA", "Boeing", "Industrials", "Aerospace", "large", "DOW30"),
]

# Popular tech / growth stocks
POPULAR_TECH = [
    StockInfo("META", "Meta Platforms", "Communication", "Social Media", "mega"),
    StockInfo("TSLA", "Tesla", "Consumer Cyclical", "Auto", "mega"),
    StockInfo("AMD", "AMD", "Technology", "Semiconductors", "large"),
    StockInfo("INTC", "Intel", "Technology", "Semiconductors", "large"),
    StockInfo("CRM", "Salesforce", "Technology", "Cloud Software", "mega"),
    StockInfo("NFLX", "Netflix", "Communication", "Streaming", "mega"),
    StockInfo("ADBE", "Adobe", "Technology", "Software", "mega"),
    StockInfo("PYPL", "PayPal", "Financial", "Fintech", "large"),
    StockInfo("SQ", "Block (Square)", "Financial", "Fintech", "large"),
    StockInfo("SHOP", "Shopify", "Technology", "E-Commerce Platform", "large"),
    StockInfo("UBER", "Uber", "Technology", "Ride-Sharing", "large"),
    StockInfo("COIN", "Coinbase", "Financial", "Crypto Exchange", "large"),
    StockInfo("PLTR", "Palantir", "Technology", "Data Analytics", "large"),
    StockInfo("SNOW", "Snowflake", "Technology", "Cloud Data", "large"),
    StockInfo("ABNB", "Airbnb", "Consumer Cyclical", "Travel", "large"),
]

# ETFs
POPULAR_ETFS = [
    StockInfo("SPY", "S&P 500 ETF", "ETF", "Index", "mega"),
    StockInfo("QQQ", "Nasdaq 100 ETF", "ETF", "Index", "mega"),
    StockInfo("IWM", "Russell 2000 ETF", "ETF", "Small Cap Index", "large"),
    StockInfo("DIA", "Dow Jones ETF", "ETF", "Index", "large"),
    StockInfo("VTI", "Total Market ETF", "ETF", "Index", "mega"),
    StockInfo("ARKK", "ARK Innovation ETF", "ETF", "Growth", "mid"),
    StockInfo("XLF", "Financial Sector ETF", "ETF", "Sector", "large"),
    StockInfo("XLK", "Technology Sector ETF", "ETF", "Sector", "large"),
    StockInfo("XLE", "Energy Sector ETF", "ETF", "Sector", "large"),
    StockInfo("GLD", "Gold ETF", "ETF", "Commodity", "large"),
    StockInfo("TLT", "20+ Year Treasury ETF", "ETF", "Bond", "large"),
    StockInfo("VIX", "Volatility Index", "ETF", "Volatility", "large"),
]

# Healthcare / Biotech
HEALTHCARE = [
    StockInfo("LLY", "Eli Lilly", "Healthcare", "Pharma", "mega"),
    StockInfo("PFE", "Pfizer", "Healthcare", "Pharma", "mega"),
    StockInfo("ABBV", "AbbVie", "Healthcare", "Pharma", "mega"),
    StockInfo("MRK", "Merck", "Healthcare", "Pharma", "mega"),
    StockInfo("TMO", "Thermo Fisher", "Healthcare", "Life Sciences", "mega"),
]

# Energy
ENERGY = [
    StockInfo("XOM", "ExxonMobil", "Energy", "Oil & Gas", "mega"),
    StockInfo("CVX", "Chevron", "Energy", "Oil & Gas", "mega"),
    StockInfo("COP", "ConocoPhillips", "Energy", "Oil & Gas", "large"),
    StockInfo("SLB", "Schlumberger", "Energy", "Services", "large"),
]

# All stocks combined
ALL_STOCKS = DOW_30 + POPULAR_TECH + POPULAR_ETFS + HEALTHCARE + ENERGY

# Remove duplicates by symbol
_seen = set()
STOCK_UNIVERSE: list[StockInfo] = []
for s in ALL_STOCKS:
    if s.symbol not in _seen:
        _seen.add(s.symbol)
        STOCK_UNIVERSE.append(s)

# Lookup
STOCK_MAP: dict[str, StockInfo] = {s.symbol: s for s in STOCK_UNIVERSE}

# Sectors
SECTORS = sorted(set(s.sector for s in STOCK_UNIVERSE))


def get_stocks_by_sector(sector: str) -> list[StockInfo]:
    """Get all stocks in a sector."""
    return [s for s in STOCK_UNIVERSE if s.sector == sector]


def get_stocks_by_tier(tier: str) -> list[StockInfo]:
    """Get stocks by market cap tier."""
    return [s for s in STOCK_UNIVERSE if s.market_cap_tier == tier]


def search_stocks(query: str) -> list[StockInfo]:
    """Search stocks by symbol or name."""
    q = query.upper()
    return [s for s in STOCK_UNIVERSE if q in s.symbol or q in s.name.upper()]
