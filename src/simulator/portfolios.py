"""The portfolios the Portfolio Battery runs, taken from the historical archive.

``PORTFOLIOS`` maps each name to a ``Portfolio`` holding its symbols and equal
``weights``. ``PERIODS`` carries the six windows the archive addressed them
over, and ``is_crypto`` routes a symbol to the crypto or the non-crypto
historical price source. Nothing here reads or writes price data.
"""

from __future__ import annotations

from dataclasses import dataclass

ARCHIVE_SOURCE: str = "RAIntSimBat_standalone"
"""The archive every definition in this module was read out of."""

PERIODS: dict[str, tuple[str, str]] = {
    "2020": ("2020-01-01", "2020-12-31"),
    "2021": ("2021-01-01", "2021-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "Apr23-Apr24": ("2023-04-01", "2024-04-01"),
    "Apr24-Apr25": ("2024-04-01", "2025-04-01"),
    "Apr25-Apr26": ("2025-04-01", "2026-04-01"),
}
"""Each archive period label mapped to its ``(start, end)`` UTC dates."""


@dataclass(frozen=True)
class Portfolio:
    """One named basket of ``symbols`` from ``ARCHIVE_SOURCE``.

    The archive committed the same capital to every symbol it ran, so
    ``weights`` divides one share equally across ``symbols``.
    """

    name: str
    symbols: tuple[str, ...]
    description: str
    source: str = ARCHIVE_SOURCE

    @property
    def weights(self) -> dict[str, float]:
        """Return each symbol's equal share of one, or ``{}`` for no symbols."""
        if not self.symbols:
            return {}
        share = 1.0 / len(self.symbols)
        return {symbol: share for symbol in self.symbols}


def is_crypto(symbol: str) -> bool:
    """True when ``symbol`` is in ``CRYPTO_SYMBOLS``, case-insensitively."""
    return symbol.upper() in CRYPTO_SYMBOLS


def symbols_for(portfolio_name: str) -> tuple[str, ...]:
    """Return one portfolio's symbols, or an empty tuple for an unknown name."""
    entry = PORTFOLIOS.get(portfolio_name)
    return entry.symbols if entry is not None else ()


SYMBOLS: tuple[str, ...] = (
    "AAPL", "ADA", "AGG", "AMC", "AMD", "AMZN", "ARKF", "ARKG", "ARKK",
    "ARKW", "ATOM", "AVAX", "BABA", "BBBY", "BIDU", "BNB", "BND", "BTC",
    "CCIV", "COIN", "CVNA", "DKNG", "DOGE", "DOT", "ETH", "EXPR", "GLD",
    "GME", "GOOGL", "IEF", "IPOF", "IWM", "JD", "KOSS", "LINK", "MATIC",
    "MCHI", "META", "MSFT", "NIO", "NVDA", "OPEN", "PLTR", "PRNT", "PTON",
    "QQQ", "ROKU", "SLV", "SNDL", "SOFI", "SOL", "SPY", "TDOC", "TIP",
    "TLT", "TRX", "TSLA", "USO", "UWMC", "VNQ", "XLU", "XRP", "ZM"
)

CRYPTO_SYMBOLS: frozenset[str] = frozenset(
    {
        "ADA", "ATOM", "AVAX", "BNB", "BTC", "DOGE", "DOT", "ETH", "LINK",
        "MATIC", "SOL", "TRX", "XRP"
    }
)

PORTFOLIOS: dict[str, Portfolio] = {
    "CRYPTO": Portfolio(
        name="CRYPTO",
        symbols=(
            "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "TRX",
            "AVAX", "DOT"
        ),
        description="All 10 crypto assets, equal weight",
    ),
    "EQUITY": Portfolio(
        name="EQUITY",
        symbols=(
            "GLD", "SLV", "USO", "SPY", "QQQ", "IWM", "AAPL", "MSFT",
            "NVDA", "TSLA", "GME", "AMD", "SOFI", "PLTR", "SNDL"
        ),
        description="All 16 equity assets, equal weight",
    ),
    "BALANCED": Portfolio(
        name="BALANCED",
        symbols=(
            "BTC", "ETH", "SOL", "BNB", "XRP", "SPY", "QQQ", "GLD",
            "AAPL", "NVDA"
        ),
        description="5 top crypto + 5 core equity",
    ),
    "CONSERVATIVE": Portfolio(
        name="CONSERVATIVE",
        symbols=("SPY", "QQQ", "IWM", "GLD", "SLV", "AAPL", "MSFT", "BTC"),
        description="Heavy equity, minimal crypto — capital preservation",
    ),
    "AGGRESSIVE": Portfolio(
        name="AGGRESSIVE",
        symbols=(
            "BTC", "ETH", "SOL", "AVAX", "DOT", "NVDA", "TSLA", "AMD",
            "PLTR", "GME"
        ),
        description="High-volatility crypto + growth stocks",
    ),
    "DEGEN": Portfolio(
        name="DEGEN",
        symbols=("DOGE", "GME", "SNDL", "SOFI", "TRX", "ADA"),
        description="Maximum volatility — meme assets and micro-caps",
    ),
    "INCOME": Portfolio(
        name="INCOME",
        symbols=("GLD", "SLV", "USO", "SPY", "QQQ", "IWM"),
        description="Commodity ETFs + index ETFs, lower volatility",
    ),
    "FULL": Portfolio(
        name="FULL",
        symbols=(
            "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "TRX",
            "AVAX", "DOT", "GLD", "SLV", "USO", "SPY", "QQQ", "IWM",
            "AAPL", "MSFT", "NVDA", "TSLA", "GME", "AMD", "SOFI", "PLTR",
            "SNDL"
        ),
        description="All 26 supported assets simultaneously",
    ),
    "BOGLEHEAD": Portfolio(
        name="BOGLEHEAD",
        symbols=("SPY", "QQQ", "IWM"),
        description="Total market index — SPY + QQQ + IWM (Bogle philosophy)",
    ),
    "ALL_WEATHER": Portfolio(
        name="ALL_WEATHER",
        symbols=("SPY", "IWM", "GLD", "SLV", "USO"),
        description="Ray Dalio inspired — equities + gold + oil + broad index",
    ),
    "BUFFETT": Portfolio(
        name="BUFFETT",
        symbols=("AAPL", "MSFT", "SPY", "GLD"),
        description="Warren Buffett style — quality blue chip + broad index",
    ),
    "SIXTY_FORTY": Portfolio(
        name="SIXTY_FORTY",
        symbols=("SPY", "QQQ", "IWM", "GLD", "SLV", "USO"),
        description="Classic 60/40 — 3 index ETFs + 3 commodity ETFs",
    ),
    "SECTOR_TECH": Portfolio(
        name="SECTOR_TECH",
        symbols=("NVDA", "MSFT", "AAPL", "AMD", "QQQ"),
        description="Tech sector concentration — NVDA MSFT AAPL AMD QQQ",
    ),
    "GROWTH_STOCK": Portfolio(
        name="GROWTH_STOCK",
        symbols=("NVDA", "TSLA", "AMD", "PLTR", "SOFI"),
        description="High-conviction growth names — NVDA TSLA AMD PLTR SOFI",
    ),
    "DEFENSIVE": Portfolio(
        name="DEFENSIVE",
        symbols=("GLD", "SLV", "SPY", "IWM", "AAPL", "MSFT"),
        description="Capital preservation — gold + silver + blue chip + index",
    ),
    "CRYPTO_BLUE": Portfolio(
        name="CRYPTO_BLUE",
        symbols=("BTC", "ETH", "BNB"),
        description="Institutional-grade crypto only — BTC ETH BNB",
    ),
    "DIGITAL_GOLD": Portfolio(
        name="DIGITAL_GOLD",
        symbols=("BTC", "ETH", "GLD", "SLV"),
        description="Digital + physical store of value — BTC ETH GLD SLV",
    ),
    "RETIREMENT": Portfolio(
        name="RETIREMENT",
        symbols=("SPY", "QQQ", "GLD", "AAPL", "MSFT", "IWM", "SLV"),
        description="Target-date approximation — diversified moderate risk",
    ),
    "ARK_SUITE": Portfolio(
        name="ARK_SUITE",
        symbols=("ARKK", "ARKG", "ARKW", "ARKF", "PRNT"),
        description="Cathie Wood ARK suite — -75%% by 2022 [LIVE DATA]",
    ),
    "SIXTY_FORTY_FAIL": Portfolio(
        name="SIXTY_FORTY_FAIL",
        symbols=("SPY", "QQQ", "TLT", "IEF", "AGG"),
        description="60/40 Failure 2022 — both legs down simultaneously [LIVE DATA]",
    ),
    "PANDEMIC_DARLINGS": Portfolio(
        name="PANDEMIC_DARLINGS",
        symbols=("PTON", "ZM", "TDOC", "ROKU", "CVNA"),
        description="Pandemic darlings — PTON ZM TDOC ROKU CVNA [LIVE DATA]",
    ),
    "CHINA_TECH": Portfolio(
        name="CHINA_TECH",
        symbols=("BABA", "JD", "BIDU", "NIO", "MCHI"),
        description="China tech crash 2021 — BABA JD BIDU NIO [LIVE DATA]",
    ),
    "LONG_BONDS": Portfolio(
        name="LONG_BONDS",
        symbols=("TLT", "IEF", "TIP", "AGG", "BND"),
        description="Long bond annihilation 2022 — TLT IEF AGG [LIVE DATA]",
    ),
    "CRYPTO_COLLAPSE": Portfolio(
        name="CRYPTO_COLLAPSE",
        symbols=("BTC", "ETH", "SOL", "ADA", "AVAX"),
        description="Crypto collapse 2022 — full ecosystem carnage [VALIDATED+LIVE]",
    ),
    "SPAC_BUST": Portfolio(
        name="SPAC_BUST",
        symbols=("IPOF", "CCIV", "DKNG", "OPEN", "UWMC"),
        description="SPAC bubble burst 2021-2022 [LIVE DATA]",
    ),
    "MEME_HANGOVER": Portfolio(
        name="MEME_HANGOVER",
        symbols=("GME", "AMC", "BBBY", "KOSS", "EXPR"),
        description="Meme stock aftermath — GME AMC post-squeeze [LIVE DATA]",
    ),
    "RATE_SENSITIVE": Portfolio(
        name="RATE_SENSITIVE",
        symbols=("VNQ", "XLU", "TLT", "ARKK", "PTON"),
        description="Rate-sensitive destruction 2022 — REITs utilities [LIVE DATA]",
    ),
    "EQUITY_MACRO": Portfolio(
        name="EQUITY_MACRO",
        symbols=("SPY", "GLD"),
        description="",
    ),
    "EQUITY_TECH": Portfolio(
        name="EQUITY_TECH",
        symbols=("NVDA", "AMD", "MSFT", "AAPL"),
        description="",
    ),
    "EQUITY_COMMODITY": Portfolio(
        name="EQUITY_COMMODITY",
        symbols=("GLD", "SLV", "USO", "SPY"),
        description="",
    ),
    "EQUITY_CONSERVATIVE": Portfolio(
        name="EQUITY_CONSERVATIVE",
        symbols=("SPY", "QQQ", "GLD"),
        description="",
    ),
    "EQUITY_AGGRESSIVE": Portfolio(
        name="EQUITY_AGGRESSIVE",
        symbols=("NVDA", "TSLA", "AMD"),
        description="",
    ),
    "EQUITY_INDEX": Portfolio(
        name="EQUITY_INDEX",
        symbols=("SPY", "QQQ", "IWM"),
        description="",
    ),
    "EQUITY_60_40": Portfolio(
        name="EQUITY_60_40",
        symbols=("SPY", "QQQ", "GLD", "IWM"),
        description="",
    ),
    "EXTENDED": Portfolio(
        name="EXTENDED",
        symbols=(
            "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "TRX",
            "AVAX", "DOT", "GLD", "SPY", "NVDA", "AAPL", "MSFT", "TSLA",
            "AMD", "META", "GOOGL", "AMZN", "ARKK", "TLT", "COIN", "LINK",
            "MATIC", "ATOM"
        ),
        description="Extended 26-asset benchmark — validated + live data [MIXED]",
    ),
}


__all__ = [
    "ARCHIVE_SOURCE",
    "CRYPTO_SYMBOLS",
    "PERIODS",
    "PORTFOLIOS",
    "SYMBOLS",
    "Portfolio",
    "is_crypto",
    "symbols_for",
]
