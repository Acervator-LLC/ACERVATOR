"""Whether ``SettingsManager`` stores the keys a bot's Start reads, and which bots wait for them."""

from __future__ import annotations

from typing import Any, Iterable

API_ACCESS_REQUIRED = "API Access Required"

#: The status key ``mark_api_access`` writes on a bot that waits for its keys.
API_ACCESS_KEY = "api_access"

BROKER_TRANSPORT = "broker"
WRITTEN_TRANSPORT = "written"
CCXT_TRANSPORT = "ccxt"

#: The ``ExchangeConfig`` fields each non-broker transport's Start reads.
TRANSPORT_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    WRITTEN_TRANSPORT: ("api_key_enc", "api_secret_enc"),
    CCXT_TRANSPORT: ("api_key_enc",),
}


def start_transport(exchange_id: Any, sector: Any = "") -> str:
    """The transport ``MainWindow._connect_exchange_for_bot`` takes for ``exchange_id`` on ``sector``."""
    from ..stocks.alpaca_connector import broker_serves_sector
    from .robinhood_connector import crypto_connector_class

    if broker_serves_sector(exchange_id, sector):
        return BROKER_TRANSPORT
    if crypto_connector_class(exchange_id) is not None:
        return WRITTEN_TRANSPORT
    return CCXT_TRANSPORT


def start_key_fields(exchange_id: Any, sector: Any = "") -> tuple[str, ...]:
    """The stored fields the ``start_transport`` of ``exchange_id`` on ``sector`` reads."""
    transport = start_transport(exchange_id, sector)
    if transport == BROKER_TRANSPORT:
        from ..trading.ata_spm_signin import credential_store_fields

        return tuple(credential_store_fields(exchange_id, sector))
    return TRANSPORT_KEY_FIELDS[transport]


def api_access_required(settings: Any, exchange_id: Any, sector: Any = "") -> bool:
    """True where ``settings`` holds no ``exchange_id`` entry or leaves a ``start_key_fields`` field empty."""
    entry = settings.get_exchange(exchange_id) if settings is not None else None
    if not entry:
        return True
    return not all(entry.get(name) for name in start_key_fields(exchange_id, sector))


def active_states() -> tuple[str, str]:
    """The RUNNING and PAUSED ``BotState`` values, the two states in which a bot never waits for keys."""
    from ..trading.container.config import BotState

    return (BotState.RUNNING.value, BotState.PAUSED.value)


def mark_api_access(statuses: Iterable[dict], settings: Any) -> list[dict]:
    """Copies of ``statuses``, each bot outside ``active_states`` that ``api_access_required`` names carrying ``API_ACCESS_KEY``."""
    active = active_states()
    marked = []
    for status in statuses:
        one = dict(status)
        venue = one.get("exchange", "")
        if one.get("state") not in active and api_access_required(
            settings, venue, one.get("asset_class", "")
        ):
            one[API_ACCESS_KEY] = API_ACCESS_REQUIRED
        marked.append(one)
    return marked


def waiting_bots(statuses: Iterable[dict], settings: Any) -> dict[str, list[str]]:
    """Each exchange id to the sorted ids of its bots that ``mark_api_access`` marks."""
    waiting: dict[str, list[str]] = {}
    for one in mark_api_access(statuses, settings):
        if one.get(API_ACCESS_KEY):
            venue = str(one.get("exchange") or "")
            waiting.setdefault(venue, []).append(str(one.get("bot_id") or ""))
    return {venue: sorted(ids) for venue, ids in waiting.items()}


def released_bots(
    waited: dict[str, list[str]], statuses: Iterable[dict], settings: Any
) -> dict[str, list[str]]:
    """Each exchange in ``waited`` to its bots that ``statuses`` still holds outside ``active_states`` and ``waiting_bots`` no longer names."""
    held = list(statuses)
    active = active_states()
    idle = {
        str(one.get("bot_id") or "") for one in held if one.get("state") not in active
    }
    still = waiting_bots(held, settings)
    released: dict[str, list[str]] = {}
    for venue, ids in waited.items():
        ready = [bid for bid in ids if bid in idle and bid not in still.get(venue, ())]
        if ready:
            released[venue] = ready
    return released


def unstored_venues(entries: Iterable[dict], exchange_ids: Iterable[Any]) -> list[str]:
    """Each id in ``exchange_ids`` that no ``list_exchanges`` entry in ``entries`` names, sorted."""
    listed = {str(one.get("exchange_id") or "") for one in entries}
    return sorted({str(eid or "") for eid in exchange_ids} - listed - {""})
