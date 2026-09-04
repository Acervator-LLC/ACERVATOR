"""``detect_all_topologies`` builds cross-market topology proposals.

It fans out to ``detect_momentum_funnel``, ``detect_mean_reversion_pair``,
``detect_sector_cluster`` and ``detect_distance_to_band``, dedupes the
union by asset overlap and caps it at ``PROPOSAL_CAP``. Every detector is
a pure function of a caller-supplied ``context`` dict and returns plain
dicts from ``make_proposal``. ``load_sector_map`` and
``load_target_defaults`` read ``SECTOR_MAP_PATH`` and
``TARGET_DEFAULTS_PATH``.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("acervator.topology_proposals")

MOMENTUM_MIN_CORR: float = 0.75
MOMENTUM_MIN_CLUSTER_SIZE: int = 3
MOMENTUM_WIRE_PCT: float = 20.0

MEAN_REVERSION_MAX_CORR: float = -0.60
MEAN_REVERSION_MIN_VOLUME_USD: float = 1_000_000.0
MEAN_REVERSION_WIRE_PCT: float = 25.0

SECTOR_MIN_CLUSTER_SIZE: int = 4
SECTOR_MAX_CLUSTER_SIZE: int = 6
SECTOR_WIRE_PCT: float = 15.0
# SECTOR_SIZE_WEIGHT and SECTOR_LIQUIDITY_WEIGHT sum to 1.0, holding the
# sector score on 0..100.
SECTOR_SIZE_WEIGHT: float = 0.7
SECTOR_LIQUIDITY_WEIGHT: float = 0.3

DISTANCE_DEEP_PCT: float = 10.0
DISTANCE_WIRE_PCT: float = 30.0

DEFAULT_TARGET_USD_FALLBACK: float = 25.0
PROPOSAL_CAP: int = 20

REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent
SECTOR_MAP_PATH: Path = Path(__file__).resolve().parent / "sector_map.json"
TARGET_DEFAULTS_PATH: Path = (
    Path(__file__).resolve().parent / "asset_target_defaults.json"
)


def load_sector_map(path: Optional[Path] = None) -> dict[str, str]:
    """Read the ``{asset: sector_tag}`` map from ``SECTOR_MAP_PATH``.

    Returns an empty dict on any read or parse error, which leaves
    ``detect_sector_cluster`` with no proposals.
    """
    _path = path or SECTOR_MAP_PATH
    try:
        raw = json.loads(_path.read_text(encoding="utf-8"))
    except Exception as _exc:  # noqa: BLE001 - config-load best-effort
        logger.debug("topology_proposals: sector map load failed (%s)", _exc)
        return {}
    assets = raw.get("assets", {}) if isinstance(raw, dict) else {}
    return {
        str(k).upper(): str(v).lower()
        for k, v in assets.items()
        if isinstance(k, str) and isinstance(v, str)
    }


def load_target_defaults(path: Optional[Path] = None) -> tuple[dict[str, float], float]:
    """Read the per-asset target-USD map from ``TARGET_DEFAULTS_PATH``.

    Returns ``(defaults, fallback)``, where ``fallback`` is
    ``DEFAULT_TARGET_USD_FALLBACK`` on any load error.
    """
    _path = path or TARGET_DEFAULTS_PATH
    try:
        raw = json.loads(_path.read_text(encoding="utf-8"))
    except Exception as _exc:  # noqa: BLE001 - config-load best-effort
        logger.debug("topology_proposals: target defaults load failed (%s)", _exc)
        return {}, DEFAULT_TARGET_USD_FALLBACK
    if not isinstance(raw, dict):
        return {}, DEFAULT_TARGET_USD_FALLBACK
    defaults_raw = raw.get("defaults", {})
    out: dict[str, float] = {}
    if isinstance(defaults_raw, dict):
        for k, v in defaults_raw.items():
            try:
                out[str(k).upper()] = float(v)
            except (TypeError, ValueError):
                continue
    try:
        fallback = float(raw.get("fallback_usd", DEFAULT_TARGET_USD_FALLBACK))
    except (TypeError, ValueError):
        fallback = DEFAULT_TARGET_USD_FALLBACK
    return out, fallback


def suggested_target_usd(
    asset: str,
    defaults: Optional[dict[str, float]] = None,
    fallback: Optional[float] = None,
) -> float:
    """Look up ``asset`` in ``defaults``, or return ``fallback``.

    A ``None`` ``defaults`` or ``fallback`` is filled from
    ``load_target_defaults``.
    """
    if defaults is None or fallback is None:
        _defaults, _fallback = load_target_defaults()
        if defaults is None:
            defaults = _defaults
        if fallback is None:
            fallback = _fallback
    key = (asset or "").upper()
    return float(defaults.get(key, fallback))


def make_proposal(
    *,
    archetype: str,
    assets: list[str],
    bots: list[dict[str, Any]],
    wires: list[dict[str, Any]],
    title: str,
    score: float,
    adopt_notes: Optional[list[str]] = None,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Build the proposal dict every detector returns.

    ``id`` joins ``archetype`` to the sorted ``assets``, and ``score`` is
    clamped to 0..100.
    """
    _now = time.time() if now is None else now
    canonical_assets = sorted({(a or "").upper() for a in assets if a})
    _id = f"{archetype}:{'-'.join(canonical_assets)}"
    return {
        "id": _id,
        "archetype": archetype,
        "title": title,
        "created_ts": _now,
        "score": float(max(0.0, min(100.0, score))),
        "assets": canonical_assets,
        "bots": list(bots),
        "wires": list(wires),
        "adopt_notes": list(adopt_notes or []),
    }


def _make_bot_entry(
    asset: str,
    quote: str,
    symbol: str,
    role: str,
    existing_bot_id: str = "",
    target_defaults: Optional[dict[str, float]] = None,
    target_fallback: Optional[float] = None,
) -> dict[str, Any]:
    return {
        "asset": asset.upper(),
        "quote": quote.upper(),
        "symbol": symbol,
        "existing_bot_id": existing_bot_id,
        "role": role,
        "suggested_target_usd": suggested_target_usd(
            asset, target_defaults, target_fallback
        ),
    }


def _make_wire(
    source: str,
    target: str,
    pct: float,
    rationale: str,
) -> dict[str, Any]:
    return {
        "source_asset": source.upper(),
        "target_asset": target.upper(),
        "pct": float(pct),
        "rationale": rationale,
    }


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Return the sample correlation of ``xs`` and ``ys``.

    Returns 0.0 when ``n`` is under two or ``denom`` is zero.
    """
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    mean_x = sum(xs[:n]) / n
    mean_y = sum(ys[:n]) / n
    num = 0.0
    var_x = 0.0
    var_y = 0.0
    for i in range(n):
        dx = xs[i] - mean_x
        dy = ys[i] - mean_y
        num += dx * dy
        var_x += dx * dx
        var_y += dy * dy
    denom = math.sqrt(var_x * var_y)
    if denom <= 0:
        return 0.0
    return num / denom


def detect_momentum_funnel(
    tickers_by_asset: dict[str, dict[str, Any]],
    correlations: dict[tuple[str, str], float],
    min_corr: float = MOMENTUM_MIN_CORR,
    min_cluster: int = MOMENTUM_MIN_CLUSTER_SIZE,
    target_defaults: Optional[dict[str, float]] = None,
    target_fallback: Optional[float] = None,
    now: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Emit one proposal per correlated cluster of USD-quoted assets.

    ``tickers_by_asset`` carries ``quote``, ``symbol``, ``baseVolume``
    and ``existing_bot_id`` per asset; ``correlations`` is keyed by
    sorted asset pairs and a pair it omits counts as 0.0.
    """
    usd_quote_assets = [
        a.upper()
        for a, meta in tickers_by_asset.items()
        if (meta.get("quote", "") or "").upper() in ("USD", "USDC")
    ]

    if len(usd_quote_assets) < min_cluster:
        return []

    # A cluster holds peers correlated to its seed, never to each other.
    clusters: list[set[str]] = []
    seen: set[frozenset[str]] = set()
    for seed in usd_quote_assets:
        cluster = {seed}
        for peer in usd_quote_assets:
            if peer == seed:
                continue
            key = tuple(sorted((seed, peer)))
            if correlations.get(key, 0.0) >= min_corr:
                cluster.add(peer)
        if len(cluster) >= min_cluster:
            fs = frozenset(cluster)
            if fs not in seen:
                seen.add(fs)
                clusters.append(cluster)

    out: list[dict[str, Any]] = []
    for cluster in clusters:
        ranked = sorted(
            cluster,
            key=lambda a: float(tickers_by_asset.get(a, {}).get("baseVolume", 0.0)),
            reverse=True,
        )
        leader = ranked[0]
        laggers = ranked[1:]
        assets_list = ranked
        bots = [
            _make_bot_entry(
                asset=a,
                quote=tickers_by_asset[a].get("quote", "USD"),
                symbol=tickers_by_asset[a].get("symbol", f"{a}/USD"),
                role=("leader" if a == leader else "lagger"),
                existing_bot_id=str(tickers_by_asset[a].get("existing_bot_id", "")),
                target_defaults=target_defaults,
                target_fallback=target_fallback,
            )
            for a in assets_list
        ]
        wires = [
            _make_wire(
                source=leader,
                target=lag,
                pct=MOMENTUM_WIRE_PCT,
                rationale=(f"Leader {leader} feeds lagger {lag} " "(24h volume rank)"),
            )
            for lag in laggers
        ]
        avg_corr = 0.0
        pairs = 0
        for a in cluster:
            for b in cluster:
                if a >= b:
                    continue
                avg_corr += correlations.get(tuple(sorted((a, b))), 0.0)
                pairs += 1
        if pairs > 0:
            avg_corr /= pairs
        score = max(0.0, min(100.0, 100.0 * avg_corr))
        title = f"Momentum funnel: {leader} → " f"{', '.join(laggers)}"
        out.append(
            make_proposal(
                archetype="momentum_funnel",
                assets=assets_list,
                bots=bots,
                wires=wires,
                title=title,
                score=score,
                adopt_notes=[
                    f"{len(assets_list)} bots; leader {leader} wires "
                    f"{MOMENTUM_WIRE_PCT}% to each of {len(laggers)} lagger(s)."
                ],
                now=now,
            )
        )
    return out


def detect_mean_reversion_pair(
    opposing_pairs: list[dict[str, Any]],
    tickers_by_asset: dict[str, dict[str, Any]],
    max_corr: float = MEAN_REVERSION_MAX_CORR,
    min_volume_usd: float = MEAN_REVERSION_MIN_VOLUME_USD,
    target_defaults: Optional[dict[str, float]] = None,
    target_fallback: Optional[float] = None,
    now: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Emit one proposal per qualifying row of ``opposing_pairs``.

    A row carries ``long_asset``, ``short_asset`` and ``corr``, and both
    sides need ``baseVolume`` times ``last`` at or above
    ``min_volume_usd``.
    """
    out: list[dict[str, Any]] = []
    seen_pairs: set[frozenset[str]] = set()
    for row in opposing_pairs or []:
        a = (row.get("long_asset", "") or "").upper()
        b = (row.get("short_asset", "") or "").upper()
        corr = float(row.get("corr", 0.0))
        if not a or not b or a == b:
            continue
        if corr > max_corr:
            continue
        pair_key = frozenset({a, b})
        if pair_key in seen_pairs:
            continue
        meta_a = tickers_by_asset.get(a, {})
        meta_b = tickers_by_asset.get(b, {})
        if not meta_a or not meta_b:
            continue
        vol_usd_a = float(meta_a.get("baseVolume", 0.0)) * float(
            meta_a.get("last", 0.0)
        )
        vol_usd_b = float(meta_b.get("baseVolume", 0.0)) * float(
            meta_b.get("last", 0.0)
        )
        if vol_usd_a < min_volume_usd or vol_usd_b < min_volume_usd:
            continue
        seen_pairs.add(pair_key)
        bots = [
            _make_bot_entry(
                asset=a,
                quote=meta_a.get("quote", "USD"),
                symbol=meta_a.get("symbol", f"{a}/USD"),
                role="peer_a",
                existing_bot_id=str(meta_a.get("existing_bot_id", "")),
                target_defaults=target_defaults,
                target_fallback=target_fallback,
            ),
            _make_bot_entry(
                asset=b,
                quote=meta_b.get("quote", "USD"),
                symbol=meta_b.get("symbol", f"{b}/USD"),
                role="peer_b",
                existing_bot_id=str(meta_b.get("existing_bot_id", "")),
                target_defaults=target_defaults,
                target_fallback=target_fallback,
            ),
        ]
        wires = [
            _make_wire(
                a,
                b,
                MEAN_REVERSION_WIRE_PCT,
                f"{a} scrum funds {b} fold (anti-corr {corr:.2f})",
            ),
            _make_wire(
                b,
                a,
                MEAN_REVERSION_WIRE_PCT,
                f"{b} scrum funds {a} fold (anti-corr {corr:.2f})",
            ),
        ]
        score = max(0.0, min(100.0, 100.0 * abs(corr)))
        out.append(
            make_proposal(
                archetype="mean_reversion_pair",
                assets=[a, b],
                bots=bots,
                wires=wires,
                title=f"Mean-rev pair: {a} ↔ {b}",
                score=score,
                adopt_notes=[
                    f"Bidirectional {MEAN_REVERSION_WIRE_PCT}% wires; both sides "
                    f"liquid (≥ ${min_volume_usd:,.0f} 24h)."
                ],
                now=now,
            )
        )
    return out


def detect_sector_cluster(
    tickers_by_asset: dict[str, dict[str, Any]],
    sector_map: dict[str, str],
    min_cluster: int = SECTOR_MIN_CLUSTER_SIZE,
    max_cluster: int = SECTOR_MAX_CLUSTER_SIZE,
    target_defaults: Optional[dict[str, float]] = None,
    target_fallback: Optional[float] = None,
    now: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Emit one proposal per sector ``sector_map`` fills.

    A sector needs ``min_cluster`` members, keeps its ``max_cluster``
    most liquid, and an asset ``sector_map`` omits reaches no proposal
    here.
    """
    if not sector_map:
        return []
    by_sector: dict[str, list[str]] = {}
    for asset, meta in tickers_by_asset.items():
        upper = asset.upper()
        sector = sector_map.get(upper)
        if not sector:
            continue
        if (meta.get("quote", "") or "").upper() not in ("USD", "USDC"):
            continue
        by_sector.setdefault(sector, []).append(upper)

    # prepared holds every qualifying sector; _max_volume spans them all.
    prepared: list[tuple[str, list[str], float]] = []
    for sector in sorted(by_sector):
        members = by_sector[sector]
        if len(members) < min_cluster:
            continue
        ranked = sorted(
            members,
            key=lambda a: (
                -float(tickers_by_asset.get(a, {}).get("baseVolume", 0.0)),
                a,
            ),
        )[:max_cluster]
        sector_volume = sum(
            float(tickers_by_asset.get(a, {}).get("baseVolume", 0.0) or 0.0)
            for a in ranked
        )
        prepared.append((sector, ranked, sector_volume))

    _max_volume = max((v for _s, _r, v in prepared), default=0.0)

    out: list[dict[str, Any]] = []
    for sector, ranked, sector_volume in prepared:
        hub = ranked[0]
        spokes = ranked[1:]
        bots = [
            _make_bot_entry(
                asset=a,
                quote=tickers_by_asset[a].get("quote", "USD"),
                symbol=tickers_by_asset[a].get("symbol", f"{a}/USD"),
                role=("hub" if a == hub else "spoke"),
                existing_bot_id=str(tickers_by_asset[a].get("existing_bot_id", "")),
                target_defaults=target_defaults,
                target_fallback=target_fallback,
            )
            for a in ranked
        ]
        wires = [
            _make_wire(
                source=hub,
                target=sp,
                pct=SECTOR_WIRE_PCT,
                rationale=(f"Sector {sector}: hub {hub} feeds spoke {sp}"),
            )
            for sp in spokes
        ]
        _size_ratio = len(ranked) / float(max_cluster)
        _liq_ratio = (sector_volume / _max_volume) if _max_volume > 0 else 0.0
        score = max(
            0.0,
            min(
                100.0,
                100.0
                * (
                    SECTOR_SIZE_WEIGHT * _size_ratio
                    + SECTOR_LIQUIDITY_WEIGHT * _liq_ratio
                ),
            ),
        )
        out.append(
            make_proposal(
                archetype="sector_cluster",
                assets=ranked,
                bots=bots,
                wires=wires,
                title=(f"Sector cluster ({sector}): {hub} → " f"{', '.join(spokes)}"),
                score=score,
                adopt_notes=[
                    f"Sector '{sector}': hub {hub} wires "
                    f"{SECTOR_WIRE_PCT}% to each of {len(spokes)} spoke(s)."
                ],
                now=now,
            )
        )
    return out


def detect_distance_to_band(
    bots_snapshot: list[dict[str, Any]],
    deep_pct: float = DISTANCE_DEEP_PCT,
    now: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Pair each deep-scrum bot with a deep-fold bot on the same asset.

    A ``bots_snapshot`` entry needs ``target_balance`` above zero, a
    numeric ``position_val`` and an ``asset``; ``deep_pct`` sets the
    distance both sides must reach.
    """
    deep_scrum: list[dict[str, Any]] = []
    deep_fold: list[dict[str, Any]] = []
    for b in bots_snapshot or []:
        try:
            tgt = float(b.get("target_balance", 0.0))
            pos = float(b.get("position_val", 0.0))
        except (TypeError, ValueError):
            continue
        if tgt <= 0:
            continue
        dist_pct = 100.0 * (pos - tgt) / tgt
        if dist_pct >= deep_pct:
            deep_scrum.append({**b, "_dist_pct": dist_pct})
        elif dist_pct <= -deep_pct:
            deep_fold.append({**b, "_dist_pct": dist_pct})

    out: list[dict[str, Any]] = []
    for s_bot in deep_scrum:
        s_asset = (s_bot.get("asset", "") or "").upper()
        for f_bot in deep_fold:
            f_asset = (f_bot.get("asset", "") or "").upper()
            if s_asset != f_asset or not s_asset:
                continue
            s_symbol = s_bot.get("symbol", f"{s_asset}/USD")
            f_symbol = f_bot.get("symbol", f"{f_asset}/USD")
            bots = [
                {
                    "asset": s_asset,
                    "quote": (s_bot.get("quote", "USD") or "USD").upper(),
                    "symbol": s_symbol,
                    "existing_bot_id": str(s_bot.get("bot_id", "")),
                    "role": "scrum_deep",
                    "suggested_target_usd": float(s_bot.get("target_balance", 0.0)),
                },
                {
                    "asset": f_asset,
                    "quote": (f_bot.get("quote", "USD") or "USD").upper(),
                    "symbol": f_symbol,
                    "existing_bot_id": str(f_bot.get("bot_id", "")),
                    "role": "fold_deep",
                    "suggested_target_usd": float(f_bot.get("target_balance", 0.0)),
                },
            ]
            wires = [
                _make_wire(
                    source=s_asset,
                    target=f_asset,
                    pct=DISTANCE_WIRE_PCT,
                    rationale=(
                        f"{s_asset} bot {s_bot.get('bot_id','')[:6]} "
                        f"({s_bot['_dist_pct']:+.1f}%) → "
                        f"{f_bot.get('bot_id','')[:6]} "
                        f"({f_bot['_dist_pct']:+.1f}%)"
                    ),
                )
            ]
            score = max(
                0.0, min(100.0, abs(s_bot["_dist_pct"]) + abs(f_bot["_dist_pct"]))
            )
            out.append(
                make_proposal(
                    archetype="distance_to_band",
                    assets=[s_asset],
                    bots=bots,
                    wires=wires,
                    title=(f"Distance handoff: {s_asset} " f"deep-scrum → deep-fold"),
                    score=score,
                    adopt_notes=[
                        f"Intra-{s_asset} handoff: {DISTANCE_WIRE_PCT}% wire."
                    ],
                    now=now,
                )
            )
    return out


def detect_all_topologies(
    context: dict[str, Any],
    cap: int = PROPOSAL_CAP,
) -> list[dict[str, Any]]:
    """Union every detector's proposals, dedupe them and cap at ``cap``.

    Every ``context`` key is optional, and ``sector_map``,
    ``target_defaults`` and ``target_fallback`` are read from disk when
    absent.

        tickers_by_asset:   dict[str, dict]
        correlations:       dict[tuple[str, str], float]
        opposing_pairs:     list[dict]
        sector_map:         dict[str, str]
        bots_snapshot:      list[dict]
        target_defaults:    dict[str, float]
        target_fallback:    float
        now:                float
    """
    if not isinstance(context, dict):
        return []

    tickers = context.get("tickers_by_asset") or {}
    correlations = context.get("correlations") or {}
    opposing = context.get("opposing_pairs") or []
    sector_map = context.get("sector_map")
    if sector_map is None:
        sector_map = load_sector_map()
    bots_snapshot = context.get("bots_snapshot") or []
    target_defaults = context.get("target_defaults")
    target_fallback = context.get("target_fallback")
    if target_defaults is None or target_fallback is None:
        _d, _f = load_target_defaults()
        if target_defaults is None:
            target_defaults = _d
        if target_fallback is None:
            target_fallback = _f
    now = context.get("now")

    proposals: list[dict[str, Any]] = []
    proposals.extend(
        detect_momentum_funnel(
            tickers,
            correlations,
            target_defaults=target_defaults,
            target_fallback=target_fallback,
            now=now,
        )
    )
    proposals.extend(
        detect_mean_reversion_pair(
            opposing,
            tickers,
            target_defaults=target_defaults,
            target_fallback=target_fallback,
            now=now,
        )
    )
    proposals.extend(
        detect_sector_cluster(
            tickers,
            sector_map,
            target_defaults=target_defaults,
            target_fallback=target_fallback,
            now=now,
        )
    )
    proposals.extend(detect_distance_to_band(bots_snapshot, now=now))

    # _ARCHETYPE_RANK keys are the archetype values make_proposal writes.
    _ARCHETYPE_RANK = {
        "momentum_funnel": 0,
        "mean_reversion_pair": 1,
        "sector_cluster": 2,
        "distance_to_band": 3,
    }
    proposals.sort(
        key=lambda p: (
            -float(p["score"]),
            _ARCHETYPE_RANK.get(str(p.get("archetype", "")), 99),
            str(p.get("title", "")),
        )
    )

    # kept takes the first of a clashing pair; the sort above ranked it
    # higher.
    kept: list[dict[str, Any]] = []
    for p in proposals:
        p_assets = set(p["assets"])
        clash = False
        for k in kept:
            k_assets = set(k["assets"])
            overlap = p_assets & k_assets
            if not overlap:
                continue
            smaller = min(len(p_assets), len(k_assets))
            if smaller == 0:
                continue
            if len(overlap) >= 2 and (len(overlap) / smaller) >= 0.5:
                clash = True
                break
        if not clash:
            kept.append(p)
        if len(kept) >= cap:
            break
    return kept[:cap]


__all__ = [
    "MOMENTUM_MIN_CORR",
    "MOMENTUM_MIN_CLUSTER_SIZE",
    "MOMENTUM_WIRE_PCT",
    "MEAN_REVERSION_MAX_CORR",
    "MEAN_REVERSION_MIN_VOLUME_USD",
    "MEAN_REVERSION_WIRE_PCT",
    "SECTOR_MIN_CLUSTER_SIZE",
    "SECTOR_MAX_CLUSTER_SIZE",
    "SECTOR_WIRE_PCT",
    "DISTANCE_DEEP_PCT",
    "DISTANCE_WIRE_PCT",
    "DEFAULT_TARGET_USD_FALLBACK",
    "PROPOSAL_CAP",
    "load_sector_map",
    "load_target_defaults",
    "suggested_target_usd",
    "make_proposal",
    "detect_momentum_funnel",
    "detect_mean_reversion_pair",
    "detect_sector_cluster",
    "detect_distance_to_band",
    "detect_all_topologies",
]
