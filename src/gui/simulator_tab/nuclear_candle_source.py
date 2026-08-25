"""
src/gui/simulator_tab/nuclear_candle_source.py — Tape-based candle feed.

v3.18.8 (Phase B revision) — REWRITTEN per operator directive 2026-05-20:

    "For Nuclear Mode, we can just use the Candle Tapes from
    RAIntSimBat. They represent organic price action data in two year
    chunks. We can just play the tape forward for the full length, flip
    it, run the full length, flip it again, and so on until Nuclear
    Mode is turned off. The injected, smoothed randomized data that is
    used instead of this has always been a sticking point for me. We
    also do not have to maintain ticker associations. We just have Tape
    A, Tape B, and so on."

The v3.18.7 implementation used ``gen_from_anchors`` (smoothstep
interpolation between 3 anchor points with gaussian noise) — that is
the "injected, smoothed randomized data" the operator has flagged.
Retired entirely.

NEW MODEL:
  • Scan ``sadp/RAIntSimBat/data/cache/*.json`` at construction.
  • Each cache file = one TAPE of REAL historical OHLCV (fetched by
    RAIntSimBat from CoinGecko for crypto + Yahoo Finance for equity).
  • Cache file format (set by RAIntSimBat._save_cache):
        {"symbol": "BTC", "year": "2023", "fetched": <ts>,
         "candles": [[ts, o, h, l, c, v], ...]}
  • Tapes assigned A, B, C, ... in scan order. Operator-facing label
    includes the source: "Tape A — BTC 2023".
  • Bot doesn't care about tickers. Internally the tapes are keyed by
    letter; the NuclearSimExchange synthesizes "TAPEA/USD" style symbols
    for the bot to trade against.

PLAYBACK:
  Play forward to the end, flip, play backward to the start, flip,
  repeat indefinitely. Each direction-flip is a "wrap" event the
  controller can count (Phase D may emit it on the perf log so the
  operator sees how long the bot ran on each polarity).

EMPTY-CACHE PATH:
  If no cache files are found, NuclearCandleSource is constructable
  (no crash) but has zero tapes. ``list_tapes()`` returns []. Callers
  check this and surface an actionable message to the GUI ("Run the
  RAIntSimBat battery once to populate the cache").
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.nuclear_sim")


# Default location of RAIntSimBat's cache directory, relative to this
# file. Resolved once at construction; can be overridden via the
# constructor's ``cache_dir`` kwarg for tests.
_NOISE_MIN_PCT = 0.10
_NOISE_MAX_PCT = 0.25
"""Per-pass noise amplitude bounds, operator directive 2026-08-04:
"plays tapes forward and then backwards with a 10~25% random noise
injection to vary the market structure conditions."

The amplitude is drawn ONCE per pass (per direction flip), not per
candle, so a single playthrough has a consistent volatility character
rather than randomly alternating between calm and violent bar to bar.
"""

_MIN_PRICE = 1e-12
"""Perturbation floor. A price must stay strictly positive or downstream
division (position sizing, VWAP, percentage gates) produces inf/NaN and
the failure surfaces far from here."""

_MIN_TAPE_CANDLES = 20
"""Below this a tape cannot warm up TA, so it is not a usable tape.
Matches the threshold ``_load_tape`` has always applied to the legacy
cache; shared so both discovery paths reject the same inputs."""

_DEFAULT_MAX_TAPES: Optional[int] = None
"""How many tablets become tapes. ``None`` = all of them.

Was 12. Operator 2026-08-04: "Active Tape list appears to be
incomplete" — it was hiding 394 of 406 tablets. The cap only existed
because discovery used to load every body it offered; now that bodies
load lazily in ``wire()``, listing the whole archive is free and the
limit has no reason to exist. Kept as a parameter so tests can bound it.
"""


def _default_cache_dir() -> Path:
    here = Path(__file__).resolve()
    # src/gui/simulator_tab/ → repo root is 3 parents up
    repo_root = here.parents[3]
    return repo_root / "sadp" / "RAIntSimBat" / "data" / "cache"


@dataclass
class _Tape:
    """One playback tape. Plays forward then reverses then forwards
    indefinitely, so the candle stream is infinite from the bot's POV.
    """

    tape_id: str  # "A", "B", "C", ...
    label: str  # operator-facing: "Tape A — BTC 2023"
    source_file: str  # filename for diagnostics
    symbol_source: str  # e.g. "BTC" or "EQ_GLD"
    period_source: str  # e.g. "2023"
    candles: list = field(default_factory=list)  # [(ts, o, h, l, c, v), ...]
    cursor: int = 0
    direction: str = "forward"  # "forward" | "reverse"
    wrap_count: int = 0  # incremented each direction-flip
    # v3.24.20 — per-pass noise injection (operator directive 2026-08-04:
    # "plays tapes forward and then backwards with a 10~25% random noise
    # injection to vary the market structure conditions").
    declared_candles: int = 0
    """Candle count from MANIFEST. Known before the body is read, so the
    GUI can show tape size without paying for a load."""
    noise_enabled: bool = True
    noise_pct: float = 0.0  # re-rolled in [MIN,MAX] on each flip
    noise_seed: int = 0  # re-rolled on each flip

    def __len__(self) -> int:
        return len(self.candles)

    def reroll_noise(self, rng) -> None:
        """Draw a fresh noise amplitude + seed for the next pass.

        Called once per direction flip, NOT per candle. A pass is
        internally coherent — the same index yields the same perturbed
        candle for the whole pass — while successive passes over the same
        tape present different market structure. That is the point: the
        bot should not be able to learn one fixed tape.
        """
        self.noise_pct = rng.uniform(_NOISE_MIN_PCT, _NOISE_MAX_PCT)
        self.noise_seed = rng.getrandbits(32)

    def _perturb(self, idx: int, candle: tuple) -> tuple:
        """Return ``candle`` with deterministic per-pass noise applied.

        Deterministic in ``(noise_seed, idx)`` rather than drawn fresh on
        each call. This matters: ``history()`` re-reads the same indices
        on every tick, and if the values moved between reads the bot's TA
        would be computed over a series that never existed. Same seed and
        index always give the same candle.

        OHLC validity is enforced after perturbation — ``high`` is raised
        to bracket every other price and ``low`` lowered — so a noisy
        candle is still a well-formed candle. Timestamps are never
        touched; the master clock stays authoritative.
        """
        ts, o, h, low, c, v = candle
        amp = self.noise_pct
        if amp <= 0.0:
            return candle

        def jitter(salt: int) -> float:
            # xorshift-style mix over (seed, idx, salt) -> [-1.0, 1.0].
            x = self.noise_seed ^ (idx * 0x9E3779B1) ^ (salt * 0x85EBCA6B)
            x &= 0xFFFFFFFF
            x ^= x >> 15
            x = (x * 0x2545F491) & 0xFFFFFFFF
            x ^= x >> 13
            return ((x & 0xFFFF) / 32767.5) - 1.0

        # One shared drift moves the whole candle (preserving its shape),
        # plus small independent jitter per price so the bar's internal
        # geometry also varies.
        drift = 1.0 + amp * jitter(0)
        no = max(o * (drift + amp * 0.25 * jitter(1)), _MIN_PRICE)
        nc = max(c * (drift + amp * 0.25 * jitter(2)), _MIN_PRICE)
        nh = max(h * (drift + amp * 0.25 * jitter(3)), _MIN_PRICE)
        nl = max(low * (drift + amp * 0.25 * jitter(4)), _MIN_PRICE)
        nv = max(v * (1.0 + amp * jitter(5)), 0.0)
        # Re-establish the OHLC invariant that perturbation can break.
        hi = max(no, nc, nh, nl)
        lo = min(no, nc, nh, nl)
        return (ts, no, hi, lo, nc, nv)

    def _at(self, idx: int) -> tuple:
        """Candle at ``idx``, noise applied when enabled."""
        raw = self.candles[idx]
        if not self.noise_enabled or self.noise_pct <= 0.0:
            return raw
        return self._perturb(idx, raw)

    @property
    def current(self):
        if not self.candles:
            return None
        # Clamp defensively
        c = max(0, min(self.cursor, len(self.candles) - 1))
        return self._at(c)

    def history(self, limit: int) -> list:
        """Return up to `limit` candles ending at the cursor, in
        forward chronological order regardless of current direction.

        This is what ``get_ohlcv`` consumes — bots compute TA on a
        chronologically-ordered window. When playing in reverse, the
        underlying candle ordering is reversed relative to the source,
        which is fine: BB/Vortex/MACD all operate on price-time, not
        wall-clock-time, and a reversed real tape is still a valid
        price-time series (it just has a different organic shape).
        """
        if not self.candles:
            return []
        end = max(0, min(self.cursor + 1, len(self.candles)))
        start = max(0, end - limit)
        # v3.24.20 — read through _at so the TA window sees the same
        # perturbed series the bot is trading. Building this from the raw
        # candles instead would mean indicators computed on prices that
        # never appeared at the cursor. Slicing produces a NEW list; the
        # underlying tablet-derived candles are never modified.
        window = [self._at(i) for i in range(start, end)]
        if self.direction == "reverse":
            # When in reverse, the cursor is decreasing — the "history"
            # is the window of candles starting from cursor going
            # back toward 0 (which is now the future from the bot's
            # POV). Slice + reverse so the chronological order matches
            # what TA expects.
            window = list(reversed(window))
        return window


def noised_series(
    rows: list,
    seed: int,
) -> tuple[list, float]:
    """Return ``(noised_copy_of_rows, noise_pct)`` for one pass.

    v3.24.73 — THE canonical way to apply Nuclear-Mode market noise to a
    plain row list. Promoted here, next to `_Tape`, so exactly one
    perturbation implementation exists.

    `topology_stress._noised_rows` had this logic and stated the reason
    it must not be duplicated: a second implementation "could drift from
    it, and then a stress result would describe a market structure the
    operator never actually simulates." That argument applies with more
    force now that Nuclear v2 uses it too — three copies would let the
    stress backtester, Nuclear v1 and Nuclear v2 each simulate a
    different market while reporting the same noise percentage.

    THE STONE TABLETS ARE NEVER WRITTEN OVER. `rows` is copied, not
    mutated, and nothing here touches disk. Operator directive
    2026-08-02: "You do not modify the fucking stone tablets."

    A pass is internally COHERENT: perturbation is deterministic in
    (seed, index), so re-reading the same index during TA warm-up yields
    the same candle. Drawing fresh noise per read would compute
    indicators over a series that never existed.

    Timestamps are never perturbed — the master clock stays
    authoritative — and the OHLC invariant is re-established after
    perturbation, so a noised candle is still a well-formed candle.
    """
    tape = _Tape(
        tape_id="N",
        label="noised",
        source_file="",
        symbol_source="",
        period_source="",
        candles=[tuple(r) for r in rows],
        noise_enabled=True,
    )
    tape.reroll_noise(random.Random(seed))  # noqa: S311 - not crypto
    out = [list(tape._at(i)) for i in range(len(tape.candles))]
    return out, float(tape.noise_pct)


class NuclearCandleSource:
    """Pumps REAL historical candle data from RAIntSimBat's cache.

    Public API consumed by NuclearSimExchange + NuclearController:
        list_tapes() -> [tape_id, ...]            # alphabetic ids
        tape_label(tape_id) -> str                # human-readable label
        active_tapes() -> [tape_id, ...]          # ids that are wired up
        wire(tape_id)                              # mark a tape as in use
        advance(tape_id)                          # advance one candle
        current(tape_id) -> tuple                 # (ts, o, h, l, c, v)
        current_price(tape_id) -> float           # close of current candle
        history(tape_id, limit) -> list           # last N candles
        stats() -> dict                           # for diagnostics
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        max_tapes: Optional[int] = _DEFAULT_MAX_TAPES,
        noise_enabled: bool = True,
        noise_rng_seed: Optional[int] = None,
    ) -> None:
        self._cache_dir: Path = (
            Path(cache_dir) if cache_dir is not None else _default_cache_dir()
        )
        self._max_tapes: Optional[int] = (
            None if max_tapes is None else max(1, int(max_tapes))
        )
        self._noise_enabled: bool = bool(noise_enabled)
        # Seedable so a stress run can be replayed exactly. Left unseeded
        # in normal use, which is the point — successive Nuclear runs
        # should not present the same market structure twice.
        # noqa justification: S311 flags non-cryptographic RNG. This
        # generates market-structure noise for a backtester; it guards
        # nothing and protects nothing. A CSPRNG here would be slower and
        # unseedable, and seedability is a requirement (reproducible runs).
        self._rng = random.Random(noise_rng_seed)  # noqa: S311
        self._tapes: dict[str, _Tape] = {}
        # v3.24.28 — manifest row per tape, so a tape can be listed and
        # described without its candle body being resident.
        self._entries: dict[str, object] = {}
        self._wired: set[str] = set()
        self._discover_tapes()

    # ─── Discovery ──────────────────────────────────────────────────────

    def _discover_tapes(self) -> None:
        """Populate tapes, preferring the Stone Tablet archive.

        Idempotent — re-discovery rebuilds the dict. Tape A/B/C
        assignment is deterministic in both paths so a tape id means the
        same thing across runs.

        v3.24.20 — SOURCE CHANGED. This used to scan only
        ``sadp/RAIntSimBat/data/cache/*.json``. That directory does not
        exist in this tree: SADP was deprecated as an authority and the
        RAIntSimBat cache went with it. So ``list_tapes()`` returned []
        on every call, the panel rendered its empty state, and Nuclear
        Mode was inert — while telling the operator to "run an
        RAIntSimBat battery", an instruction that could no longer be
        followed.

        The Stone Tablet archive is the correct source now: 406 assets /
        7,230,993 real 5m candles at ``~/.acervator/stone_tablets``,
        built this session. It is real exchange OHLCV, which is exactly
        what the operator asked tapes to be:

            "They represent organic price action data ... The injected,
            smoothed randomized data that is used instead of this has
            always been a sticking point for me."

        The legacy cache is still honoured when present, so an operator
        who restores that tree keeps their existing tape ids.
        """
        self._tapes.clear()
        if self._cache_dir.is_dir():
            cache_files = sorted(self._cache_dir.glob("*.json"))
            for idx, path in enumerate(cache_files):
                tape_id = self._index_to_letter(idx)
                tape = self._load_tape(tape_id, path)
                if tape is not None:
                    self._tapes[tape_id] = tape
            if self._tapes:
                logger.info(
                    "NuclearCandleSource: %d tape(s) from legacy cache %s",
                    len(self._tapes),
                    self._cache_dir,
                )
                return
        self._discover_tapes_from_tablets()

    def _discover_tapes_from_tablets(self) -> None:
        """Build tapes from the Stone Tablet archive.

        Selection is by candle count, descending: the fullest tablets
        are the assets with the longest continuous listing history, and
        those are what a stress backtester wants. Ties break on asset
        name so ordering is stable.

        Tablets are READ ONLY here. Nothing in this path writes to the
        archive.
        """
        try:
            from src.trading.stone_tablets.storage import (
                read_manifest,
            )
        except ImportError as exc:
            logger.warning(
                "NuclearCandleSource: Stone Tablet storage unavailable "
                "(%s); no tapes.",
                exc,
            )
            return

        try:
            entries = read_manifest()
        except OSError as exc:
            logger.warning(
                "NuclearCandleSource: could not read tablet manifest: %s", exc
            )
            return
        if not entries:
            logger.info(
                "NuclearCandleSource: tablet manifest is empty; no tapes. "
                "Build the archive before using Nuclear Mode."
            )
            return

        usable = [
            e for e in entries if getattr(e, "candle_count", 0) >= _MIN_TAPE_CANDLES
        ]
        usable.sort(key=lambda e: (-int(e.candle_count), str(e.asset)))
        chosen = usable if self._max_tapes is None else usable[: self._max_tapes]
        if not chosen:
            logger.info(
                "NuclearCandleSource: %d tablet(s) present but none has "
                ">= %d candles; no tapes.",
                len(entries),
                _MIN_TAPE_CANDLES,
            )
            return

        # v3.24.28 — INDEX ONLY, no bodies. Operator 2026-08-04: "Active
        # Tape list appears to be incomplete." It was — 394 of 406
        # tablets were hidden behind a 12-tape cap.
        #
        # That cap existed because this loop used to read_tablet() every
        # tape it offered, and 406 bodies cost ~13 s and ~2.3 GB (the
        # same defect just fixed in the Stone Tablets registry). Simply
        # raising the cap would have reintroduced it.
        #
        # So the cap is gone and the read moved to wire(): every usable
        # tablet is listed, and selecting one costs a single file read.
        for idx, entry in enumerate(chosen):
            tape_id = self._index_to_letter(idx)
            self._entries[tape_id] = entry
            self._tapes[tape_id] = _Tape(
                tape_id=tape_id,
                label=self._make_label(tape_id, entry.asset, str(entry.year)),
                source_file=f"{entry.asset}_{entry.exchange_id}_"
                f"{entry.timeframe}_{entry.year}.json",
                symbol_source=entry.asset,
                period_source=str(entry.year),
                candles=[],
                declared_candles=int(entry.candle_count),
                noise_enabled=self._noise_enabled,
            )
        logger.info(
            "NuclearCandleSource: %d tape(s) indexed from Stone Tablets "
            "(%d in archive); bodies load on wire()",
            len(self._tapes),
            len(entries),
        )

    def _load_body(self, tape_id: str) -> bool:
        """Read one tape's candles from disk. Idempotent.

        Returns False when the tablet is missing or unusable, so the
        caller can refuse the run rather than silently playing an empty
        tape.
        """
        tape = self._tapes.get(tape_id)
        entry = self._entries.get(tape_id)
        if tape is None or entry is None:
            return False
        if tape.candles:
            return True
        try:
            from src.trading.stone_tablets.storage import (
                read_tablet,
                tablet_path,
            )

            # Keyword args deliberately: the positional signature is
            # (asset, timeframe, year, root, exchange_id) and calling it
            # positionally put exchange_id in the timeframe slot, which
            # surfaced as int('5m').
            tab = read_tablet(
                tablet_path(
                    entry.asset,
                    entry.timeframe,
                    entry.year,
                    exchange_id=entry.exchange_id,
                )
            )
        except (OSError, ValueError, ImportError) as exc:
            logger.warning(
                "NuclearCandleSource: tape %s (%s) load failed: %s",
                tape_id,
                entry.asset,
                exc,
            )
            return False
        if tab is None:
            logger.warning(
                "NuclearCandleSource: tape %s (%s) tablet unreadable",
                tape_id,
                entry.asset,
            )
            return False
        clean = self._sanitize_candles(tab.candles)
        if len(clean) < _MIN_TAPE_CANDLES:
            logger.warning(
                "NuclearCandleSource: tape %s (%s) has %d valid candles "
                "after sanitization — below the %d needed for TA warm-up",
                tape_id,
                entry.asset,
                len(clean),
                _MIN_TAPE_CANDLES,
            )
            return False
        tape.candles = clean
        if self._noise_enabled:
            # Seed the FIRST pass too. Without this the opening forward
            # run would be the unmodified tablet and only later passes
            # would vary, so the bot would meet clean data exactly once
            # — the least useful ordering.
            tape.reroll_noise(self._rng)
        logger.info(
            "NuclearCandleSource: tape %s (%s) loaded — %d candles",
            tape_id,
            entry.asset,
            len(clean),
        )
        return True

    @staticmethod
    def _sanitize_candles(candles) -> list:
        """Coerce raw OHLCV rows to ``(int, float x5)`` tuples, dropping
        malformed rows. Shared by both discovery paths so a tablet-backed
        tape and a cache-backed tape are indistinguishable downstream."""
        clean = []
        for c in candles or []:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            try:
                clean.append(
                    (
                        int(c[0]),
                        float(c[1]),
                        float(c[2]),
                        float(c[3]),
                        float(c[4]),
                        float(c[5]),
                    )
                )
            except (TypeError, ValueError):
                continue
        return clean

    def _load_tape(self, tape_id: str, path: Path) -> Optional[_Tape]:
        """Load one cache file into a Tape. Returns None if the file
        is malformed or has too few candles to be useful.
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "NuclearCandleSource: skipping %s — read failed: %s", path.name, exc
            )
            return None
        candles = data.get("candles")
        symbol = str(data.get("symbol", path.stem))
        period = str(data.get("year", "?"))
        if not isinstance(candles, list) or len(candles) < 20:
            logger.warning(
                "NuclearCandleSource: skipping %s — only %d candles "
                "(need >= 20 for TA warmup)",
                path.name,
                len(candles) if isinstance(candles, list) else 0,
            )
            return None
        # Each candle: [ts, o, h, l, c, v]. Coerce to tuple of floats
        # so consumers don't have to handle two shapes.
        clean = []
        for c in candles:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            try:
                clean.append(
                    (
                        int(c[0]),
                        float(c[1]),
                        float(c[2]),
                        float(c[3]),
                        float(c[4]),
                        float(c[5]),
                    )
                )
            except (TypeError, ValueError):
                continue
        if len(clean) < 20:
            logger.warning(
                "NuclearCandleSource: skipping %s — after sanitization, "
                "only %d valid candles",
                path.name,
                len(clean),
            )
            return None
        label = self._make_label(tape_id, symbol, period)
        return _Tape(
            tape_id=tape_id,
            label=label,
            source_file=path.name,
            symbol_source=symbol,
            period_source=period,
            candles=clean,
        )

    @staticmethod
    def _make_label(tape_id: str, symbol: str, period: str) -> str:
        """Operator-facing label: "Tape A — BTC 2023" or
        "Tape B — GLD (equity) 2024" etc.
        """
        # EQ_XXX prefix means equity (from RAIntSimBat.fetch_ohlcv_yahoo)
        if symbol.upper().startswith("EQ_"):
            symbol = symbol[3:] + " (equity)"
        return f"Tape {tape_id} — {symbol} {period}"

    @staticmethod
    def _index_to_letter(idx: int) -> str:
        """0→A, 1→B, ..., 25→Z, 26→AA, 27→AB, ..."""
        if idx < 0:
            raise ValueError(idx)
        chars = []
        n = idx
        while True:
            chars.append(chr(ord("A") + (n % 26)))
            n = n // 26
            if n == 0:
                break
            n -= 1
        return "".join(reversed(chars))

    # ─── Tape querying ──────────────────────────────────────────────────

    def list_tapes(self) -> list[str]:
        """All discovered tape ids, in assignment order.

        v3.24.28 — was ``sorted(self._tapes.keys())``. That was fine at
        12 tapes (A..L) but wrong past Z: a string sort orders them
        A, AA, AB, ... AZ, B, BA — so the second entry in a 406-tape
        dropdown was "Tape AA", not "Tape B".

        Ids are assigned by candle count descending, and dict insertion
        order preserves that, so returning keys as-is puts the fullest
        histories at the top where the operator expects them.
        """
        return list(self._tapes.keys())

    def tape_label(self, tape_id: str) -> str:
        tape = self._tapes.get(tape_id)
        return tape.label if tape is not None else f"Tape {tape_id} — (missing)"

    def tape_info(self, tape_id: str) -> dict:
        """Snapshot of one tape's state for diagnostics."""
        tape = self._tapes.get(tape_id)
        if tape is None:
            return {}
        return {
            "tape_id": tape.tape_id,
            "label": tape.label,
            "source_file": tape.source_file,
            "symbol_source": tape.symbol_source,
            "period_source": tape.period_source,
            "n_candles": (len(tape.candles) if tape.candles else tape.declared_candles),
            "loaded": bool(tape.candles),
            "cursor": tape.cursor,
            "direction": tape.direction,
            "wrap_count": tape.wrap_count,
        }

    def has_any_tapes(self) -> bool:
        return bool(self._tapes)

    def cache_dir(self) -> Path:
        """The cache directory path used for discovery. Surfaced for
        the empty-cache GUI message so the operator sees exactly which
        directory needs to be populated.
        """
        return self._cache_dir

    # ─── Wiring + playback ──────────────────────────────────────────────

    def wire(self, tape_id: str) -> None:
        """Mark a tape as in-use. Idempotent.

        ``advance``/``current``/``history`` operate only on wired
        tapes; this is just bookkeeping so ``stats()`` knows which
        tapes the controller has subscribed to.
        """
        if tape_id not in self._tapes:
            raise KeyError(
                f"NuclearCandleSource.wire: unknown tape_id "
                f"{tape_id!r}. Available: {self.list_tapes()}"
            )
        # v3.24.28 — this is where a tape's candles are actually read.
        # Discovery is metadata-only so all usable tablets can be listed
        # without paying the whole archive's load cost up front.
        if not self._load_body(tape_id):
            raise ValueError(
                f"NuclearCandleSource.wire: tape {tape_id!r} has no "
                f"usable candle data — see log for the cause."
            )
        self._wired.add(tape_id)

    def active_tapes(self) -> list[str]:
        return sorted(self._wired)

    def advance(self, tape_id: str) -> None:
        """Move the cursor forward one candle (or backward, if the
        tape is currently in reverse direction). Auto-flips direction
        when the cursor hits either boundary — gives an infinite
        ping-pong stream from the bot's POV.
        """
        tape = self._tapes.get(tape_id)
        if tape is None:
            raise KeyError(
                f"NuclearCandleSource.advance: unknown tape_id " f"{tape_id!r}"
            )
        if not tape.candles:
            return
        if tape.direction == "forward":
            tape.cursor += 1
            if tape.cursor >= len(tape.candles) - 1:
                tape.cursor = len(tape.candles) - 1
                tape.direction = "reverse"
                tape.wrap_count += 1
                tape.reroll_noise(self._rng)
        else:  # reverse
            tape.cursor -= 1
            if tape.cursor <= 0:
                tape.cursor = 0
                tape.direction = "forward"
                tape.wrap_count += 1
                tape.reroll_noise(self._rng)

    def current(self, tape_id: str) -> Optional[tuple]:
        tape = self._tapes.get(tape_id)
        return tape.current if tape is not None else None

    def current_price(self, tape_id: str) -> float:
        c = self.current(tape_id)
        return float(c[4]) if c is not None else 0.0

    def history(self, tape_id: str, limit: int = 100) -> list:
        tape = self._tapes.get(tape_id)
        return tape.history(limit) if tape is not None else []

    # ─── Diagnostics ────────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "cache_dir": str(self._cache_dir),
            "cache_exists": self._cache_dir.is_dir(),
            "n_tapes_discovered": len(self._tapes),
            "n_tapes_wired": len(self._wired),
            "tapes": {tid: self.tape_info(tid) for tid in self._tapes},
        }
