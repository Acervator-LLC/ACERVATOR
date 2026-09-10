"""Project age against the six-month Quintessence rule.

``ProjectAgeLookup.verdict_for`` answers one market with a ``ProjectAgeVerdict``.
The date comes from CoinGecko's coin detail endpoint and is kept at
``DEFAULT_GENESIS_CACHE_PATH`` with no expiry. A market whose age is unknown is
refused, and ``REFUSAL_REASONS`` names every refusal.
"""

from __future__ import annotations

import calendar
import json
import logging
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..core.io_utils import atomic_write_json
from ..core.safe_url import SafeRequest, safe_urlopen
from ..exchange.crypto_assets import ASSETS

logger = logging.getLogger("acervator.project_age")

MIN_PROJECT_AGE_MONTHS = 6

COIN_DETAIL_URL = (
    "https://api.coingecko.com/api/v3/coins/{cg_id}"
    "?localization=false&tickers=false&market_data=false"
    "&community_data=false&developer_data=false&sparkline=false"
)
HTTP_TIMEOUT_S = 15.0
USER_AGENT = "Acervator"

DEFAULT_GENESIS_CACHE_PATH = Path.home() / ".acervator" / "project_genesis_dates.json"
GENESIS_CACHE_FILE_VERSION = 1

OLD_ENOUGH = "old_enough"
TOO_YOUNG = "too_young"
NO_COINGECKO_ID = "no_coingecko_id"
NO_GENESIS_DATE = "no_genesis_date"
LOOKUP_FAILED = "lookup_failed"

REFUSAL_REASONS = (TOO_YOUNG, NO_COINGECKO_ID, NO_GENESIS_DATE, LOOKUP_FAILED)


class ProjectAgeError(RuntimeError):
    """Raised for a market ``verdict_for`` cannot read, and for a failed detail call."""


def _utc_today() -> date:
    """Return today's date in UTC."""
    return datetime.now(timezone.utc).date()


def _base_of(market: str) -> str:
    """Return the upper-case base symbol of ``market``, dropping any quote part."""
    return market.split("/")[0].upper() if "/" in market else market.upper()


def months_after(start: date, months: int) -> date:
    """Return ``start`` advanced by ``months`` calendar months, clamping the day."""
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _parse_genesis_date(served: object) -> Optional[date]:
    """Return ``served`` as a ``date``, or None for a null or malformed value."""
    if not isinstance(served, str) or not served.strip():
        return None
    try:
        return date.fromisoformat(served.strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class ProjectAgeVerdict:
    """One market's answer to the six-month rule and the ``reason`` that decided it.

    ``meets_age_rule_on`` is the date the project reaches ``MIN_PROJECT_AGE_MONTHS``.
    """

    market: str
    base: str
    coingecko_id: str
    genesis_date: str
    meets_age_rule_on: str
    meets_age_rule: bool
    reason: str

    @property
    def is_refused(self) -> bool:
        """True when ``reason`` is one of ``REFUSAL_REASONS``."""
        return self.reason in REFUSAL_REASONS

    def to_dict(self) -> dict:
        """Return this verdict as a JSON-safe dict."""
        return {
            "market": self.market,
            "base": self.base,
            "coingecko_id": self.coingecko_id,
            "genesis_date": self.genesis_date,
            "meets_age_rule_on": self.meets_age_rule_on,
            "meets_age_rule": self.meets_age_rule,
            "reason": self.reason,
        }


class ProjectAgeLookup:
    """Answers the six-month rule one market at a time, keeping each genesis date.

    ``cache_path`` and ``today`` arrive at construction; a demo run reads the same
    dates through the same ``verdict_for`` path.
    """

    def __init__(
        self,
        cache_path: str | Path | None = None,
        today: Callable[[], date] | None = None,
        http_timeout_s: float = HTTP_TIMEOUT_S,
    ) -> None:
        """Hold the cache path, the clock and the timeout; no file is read here."""
        self._path: Path = (
            Path(cache_path) if cache_path else DEFAULT_GENESIS_CACHE_PATH
        )
        self._today: Callable[[], date] = today if today is not None else _utc_today
        self._http_timeout_s = float(http_timeout_s)
        self._genesis_dates: Optional[dict[str, str]] = None
        self._ids_without_a_date: set[str] = set()

    @property
    def cache_path(self) -> Path:
        """The file ``_store`` writes and ``_load`` reads."""
        return self._path

    # -- The genesis date ----------------------------------------------------

    def _load(self) -> dict[str, str]:
        """Return the kept dates, reading ``cache_path`` once per instance."""
        if self._genesis_dates is not None:
            return self._genesis_dates
        dates: dict[str, str] = {}
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
            stored = payload.get("genesis_dates", {})
            for cg_id, served in stored.items():
                if isinstance(cg_id, str) and isinstance(served, str) and served:
                    dates[cg_id] = served
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError) as exc:
            logger.warning("genesis cache %s unreadable: %s", self._path, exc)
        self._genesis_dates = dates
        return dates

    def _store(self, coingecko_id: str, genesis_date: str) -> None:
        """Write ``genesis_date`` for ``coingecko_id`` into ``cache_path``."""
        dates = self._load()
        dates[coingecko_id] = genesis_date
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self._path,
            {
                "version": GENESIS_CACHE_FILE_VERSION,
                "genesis_dates": dates,
            },
            sort_keys=True,
        )

    def _fetch_genesis_date(self, coingecko_id: str) -> str:
        """Return CoinGecko's genesis date for ``coingecko_id``, or an empty string."""
        url = COIN_DETAIL_URL.format(cg_id=urllib.parse.quote(coingecko_id, safe=""))
        request = SafeRequest(url)
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", USER_AGENT)
        with safe_urlopen(request, timeout=self._http_timeout_s) as response:
            payload = json.loads(response.read().decode())
        served = payload.get("genesis_date")
        logger.info("CoinGecko genesis_date for %s: %r", coingecko_id, served)
        return served.strip() if isinstance(served, str) else ""

    def genesis_date_for(self, coingecko_id: str) -> str:
        """Return the kept or fetched genesis date, or an empty string for a null.

        Raises ``ProjectAgeError`` when the coin detail call does not answer.
        """
        dates = self._load()
        if coingecko_id in dates:
            return dates[coingecko_id]
        if coingecko_id in self._ids_without_a_date:
            return ""
        try:
            served = self._fetch_genesis_date(coingecko_id)
        except (OSError, ValueError, TypeError) as exc:
            # An HTTPError carries an open response body; close releases it.
            closer = getattr(exc, "close", None)
            if callable(closer):
                closer()
            raise ProjectAgeError(
                f"the coin detail call for {coingecko_id} did not answer: {exc}"
            ) from exc
        if not served:
            self._ids_without_a_date.add(coingecko_id)
            return ""
        self._store(coingecko_id, served)
        return served

    # -- The rule -----------------------------------------------------------

    def verdict_for(self, market: str) -> ProjectAgeVerdict:
        """Return the ``ProjectAgeVerdict`` for ``market``, refusing an unknown age."""
        if not isinstance(market, str) or not market.strip():
            raise ProjectAgeError(f"market must be a non-empty symbol, got {market!r}")
        symbol = market.strip()
        base = _base_of(symbol)
        asset = ASSETS.get(base)
        coingecko_id = asset.coingecko_id if asset is not None else ""

        served = ""
        genesis: Optional[date] = None
        reason = OLD_ENOUGH

        if not coingecko_id:
            reason = NO_COINGECKO_ID
        else:
            try:
                served = self.genesis_date_for(coingecko_id)
            except ProjectAgeError as exc:
                logger.warning("the detail call for %s did not answer: %s", symbol, exc)
                reason = LOOKUP_FAILED
            else:
                genesis = _parse_genesis_date(served)
                if genesis is None:
                    reason = NO_GENESIS_DATE
                    if served:
                        logger.warning(
                            "genesis_date %r for %s is not a date", served, coingecko_id
                        )

        meets_age_rule_on = ""
        if genesis is not None:
            admits_on = months_after(genesis, MIN_PROJECT_AGE_MONTHS)
            meets_age_rule_on = admits_on.isoformat()
            if self._today() < admits_on:
                reason = TOO_YOUNG

        return ProjectAgeVerdict(
            market=symbol,
            base=base,
            coingecko_id=coingecko_id,
            genesis_date=served,
            meets_age_rule_on=meets_age_rule_on,
            meets_age_rule=reason == OLD_ENOUGH,
            reason=reason,
        )
