"""Tape-based candle feed for Nuclear Mode.

``_discover_tapes_from_tablets`` indexes the Stone Tablet archive, and
``_load_body`` reads one tablet of real exchange OHLCV per wired tape.
``advance`` plays a ``_Tape`` to the end, flips its ``direction`` and plays
back, counting every flip in ``wrap_count``. Only the prices and volumes
``_perturb`` returns are synthesized; ``ts`` and the tablet files never change.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.nuclear_sim")


_NOISE_MIN_PCT = 0.10
_NOISE_MAX_PCT = 0.25
"""Bounds on the amplitude ``reroll_noise`` draws into ``noise_pct``.

``reroll_noise`` draws once per direction flip, never once per candle.
"""

_MIN_PRICE = 1e-12
"""Floor ``_perturb`` applies to each price, keeping every one strictly positive."""

_MIN_TAPE_CANDLES = 20
"""Fewest candles a tape may hold and still warm up TA.

``_load_tape`` and ``_load_body`` both reject a tape below this count.
"""

_DEFAULT_MAX_TAPES: Optional[int] = None
"""Cap on how many tablets ``_discover_tapes_from_tablets`` turns into tapes.

``None`` lists every usable tablet, and ``max_tapes`` overrides it.
"""


def _default_cache_dir() -> Path:
    """Return the legacy cache directory two parents above this file.

    ``_discover_tapes`` falls through to ``_discover_tapes_from_tablets`` when
    the directory is absent.
    """
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    return repo_root / "sadp" / "RAIntSimBat" / "data" / "cache"


@dataclass
class _Tape:
    """One tape of candles and the cursor that walks them.

    ``advance`` runs ``cursor`` to either end and then flips ``direction``,
    giving an endless stream from one finite ``candles`` list.
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
    declared_candles: int = 0
    """Candle count read from the tablet manifest.

    ``tape_info`` reports it while ``candles`` is still empty.
    """
    noise_enabled: bool = True
    noise_pct: float = 0.0  # re-rolled in [MIN,MAX] on each flip
    noise_seed: int = 0  # re-rolled on each flip

    def __len__(self) -> int:
        return len(self.candles)

    def reroll_noise(self, rng) -> None:
        """Draw a fresh ``noise_pct`` and ``noise_seed`` from *rng*.

        ``advance`` calls this on each direction flip, giving successive passes
        over one tape a different structure.
        """
        self.noise_pct = rng.uniform(_NOISE_MIN_PCT, _NOISE_MAX_PCT)
        self.noise_seed = rng.getrandbits(32)

    def _perturb(self, idx: int, candle: tuple) -> tuple:
        """Return ``candle`` with per-pass noise on its prices and volume.

        The result is fixed by ``noise_seed`` and ``idx``, ``ts`` is carried
        through untouched, and the returned high and low bracket every other
        price.
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

        # `drift` moves the whole bar; each price adds its own smaller jitter.
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
        c = max(0, min(self.cursor, len(self.candles) - 1))
        return self._at(c)

    def history(self, limit: int) -> list:
        """Return up to *limit* candles ending at ``cursor``, oldest first.

        Each one comes through ``_at``, and a tape in ``reverse`` has its window
        reversed before it is returned.
        """
        if not self.candles:
            return []
        end = max(0, min(self.cursor + 1, len(self.candles)))
        start = max(0, end - limit)
        # A new list every call; `candles` itself is never written.
        window = [self._at(i) for i in range(start, end)]
        if self.direction == "reverse":
            window = list(reversed(window))
        return window


def noised_series(
    rows: list,
    seed: int,
) -> tuple[list, float]:
    """Return ``(noised_rows, noise_pct)`` for one pass over *rows*.

    A ``_Tape`` seeded from *seed* perturbs a copy through ``_at``; *rows* is
    left as it was and nothing here touches disk.
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
    tape.reroll_noise(random.Random(seed))  # noqa: S311
    out = [list(tape._at(i)) for i in range(len(tape.candles))]
    return out, float(tape.noise_pct)


class NuclearCandleSource:
    """Serve one tape of candles at a time to Nuclear Mode.

    ``_load_body`` reads real exchange OHLCV from a tablet and ``_at`` hands back
    a perturbed copy of it. ``list_tapes``, ``tape_label`` and ``tape_info``
    describe the tapes, and ``active_tapes`` names the ones through ``wire``.
    ``advance``, ``current``, ``current_price``, ``history`` and ``stats`` drive
    and report playback.
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
        # Unseeded in normal use; `noise_rng_seed` makes a run reproducible.
        self._rng = random.Random(noise_rng_seed)  # noqa: S311
        self._tapes: dict[str, _Tape] = {}
        # One manifest row per tape id, kept for `_load_body` to read from.
        self._entries: dict[str, object] = {}
        self._wired: set[str] = set()
        self._discover_tapes()

    def _discover_tapes(self) -> None:
        """Fill ``_tapes`` from ``_cache_dir``, falling back to the tablets.

        ``_load_tape`` reads every JSON file in ``_cache_dir`` when that
        directory exists; otherwise ``_discover_tapes_from_tablets`` runs.
        Calling it again rebuilds ``_tapes``, and ``_index_to_letter`` gives the
        same position the same id every time.
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
        """Index the Stone Tablet archive into ``_tapes`` and ``_entries``.

        ``read_manifest`` supplies the entries, ordered by ``candle_count``
        descending with ties broken on ``asset``; only metadata is stored, and
        ``_load_body`` reads a body when ``wire`` asks.
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
        """Read tape *tape_id*'s candles from its tablet. Idempotent.

        Returns True once ``candles`` is populated, and False when ``_tapes`` or
        ``_entries`` has no row, ``read_tablet`` fails, or ``_sanitize_candles``
        leaves fewer than ``_MIN_TAPE_CANDLES``.
        """
        tape = self._tapes.get(tape_id)
        if tape is not None and tape.candles:
            return True
        entry = self._entries.get(tape_id)
        if tape is None or entry is None:
            return False
        try:
            from src.trading.stone_tablets.storage import (
                read_tablet,
                tablet_path,
            )

            # `tablet_path` takes `root` before `exchange_id`; pass it by name.
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
            # Seeds the first pass; the opening forward run is perturbed too.
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
        """Coerce raw OHLCV rows to ``(int, float x5)`` tuples, dropping bad rows.

        ``_load_body`` and ``_load_tape`` both feed their rows through it, giving
        a tablet-backed and a cache-backed ``_Tape`` the same candle shape.
        """
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
        """Load one legacy cache file at *path* into a ``_Tape``.

        Returns None when the JSON is unreadable or ``_sanitize_candles`` leaves
        fewer than ``_MIN_TAPE_CANDLES``.
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
        if not isinstance(candles, list) or len(candles) < _MIN_TAPE_CANDLES:
            logger.warning(
                "NuclearCandleSource: skipping %s — only %d candles "
                "(need >= %d for TA warmup)",
                path.name,
                len(candles) if isinstance(candles, list) else 0,
                _MIN_TAPE_CANDLES,
            )
            return None
        clean = self._sanitize_candles(candles)
        if len(clean) < _MIN_TAPE_CANDLES:
            logger.warning(
                "NuclearCandleSource: skipping %s — after sanitization, "
                "only %d valid candles (need >= %d)",
                path.name,
                len(clean),
                _MIN_TAPE_CANDLES,
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
        """Return an operator-facing label such as "Tape A — BTC 2023".

        A *symbol* beginning ``EQ_`` renders as "Tape B — GLD (equity) 2024".
        """
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

    def list_tapes(self) -> list[str]:
        """Return every id in ``_tapes``, in the order it was assigned.

        Sorting the keys would order them A, AA, AB, B past twenty-six tapes.
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
        """Return ``_cache_dir``, the legacy directory ``_discover_tapes`` scans."""
        return self._cache_dir

    def wire(self, tape_id: str) -> None:
        """Add *tape_id* to ``_wired`` and load its candles. Idempotent.

        Raises ``KeyError`` for an id absent from ``_tapes`` and ``ValueError``
        when ``_load_body`` finds no usable candles.
        """
        if tape_id not in self._tapes:
            raise KeyError(
                f"NuclearCandleSource.wire: unknown tape_id "
                f"{tape_id!r}. Available: {self.list_tapes()}"
            )
        if not self._load_body(tape_id):
            raise ValueError(
                f"NuclearCandleSource.wire: tape {tape_id!r} has no "
                f"usable candle data — see log for the cause."
            )
        self._wired.add(tape_id)

    def active_tapes(self) -> list[str]:
        return sorted(self._wired)

    def advance(self, tape_id: str) -> None:
        """Move *tape_id*'s ``cursor`` one candle along its ``direction``.

        At either end ``direction`` flips, ``wrap_count`` increments and
        ``reroll_noise`` draws a new amplitude.
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
        else:
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

    def stats(self) -> dict:
        return {
            "cache_dir": str(self._cache_dir),
            "cache_exists": self._cache_dir.is_dir(),
            "n_tapes_discovered": len(self._tapes),
            "n_tapes_wired": len(self._wired),
            "tapes": {tid: self.tape_info(tid) for tid in self._tapes},
        }
