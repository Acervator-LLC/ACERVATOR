"""Synthesized audio notifications for trading events.

``SoundEngine`` writes every clip into ``_temp_dir`` on first ``play`` and
caches the paths in ``_cache``. ``SoundConfig`` carries the per-event
switches and the master ``volume``. Each generator imports ``wave``,
``struct`` and ``math`` inside its own body.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, fields
from typing import Optional

logger = logging.getLogger("acervator.sound")


@dataclass
class SoundConfig:
    enabled: bool = True
    buy_sound: bool = True
    sell_sound: bool = True
    error_sound: bool = True
    bot_state_sound: bool = True
    fire_sound: bool = True
    track_sound: bool = True
    profit_sound: bool = True
    drip_sound: bool = True
    volume: float = 0.7


VOLUME_FIELD = "volume"

#: Every ``SoundConfig`` field ``play`` reads as a switch, taken off the
#: dataclass so the two cannot drift.
SOUND_SWITCHES: tuple[str, ...] = tuple(
    one.name for one in fields(SoundConfig) if one.name != VOLUME_FIELD
)

MIN_VOLUME = 0.0
MAX_VOLUME = 1.0


def sound_config_from_settings(stored: Optional[dict]) -> SoundConfig:
    """The ten sound values, with every entry ``stored`` carries over the defaults.

    ``stored`` is the ``sound`` mapping the settings file holds. A switch that is
    not ``True`` or ``False``, and a ``volume`` outside ``MIN_VOLUME`` to
    ``MAX_VOLUME``, are dropped with a warning rather than reaching the engine:
    each generator multiplies ``volume`` into every sample before ``struct.pack``,
    which raises outside that range, and ``play`` reads a switch for truth, so a
    non-empty string would open a sound the operator had closed.
    """
    taken = SoundConfig()
    for name, value in (stored or {}).items():
        if name in SOUND_SWITCHES:
            if isinstance(value, bool):
                setattr(taken, name, value)
            else:
                logger.warning(
                    "sound %s=%r is not on or off; default kept", name, value
                )
            continue
        if name == VOLUME_FIELD:
            if isinstance(value, bool):
                logger.warning("sound volume %r is not a number; default kept", value)
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                logger.warning("sound volume %r is not a number; default kept", value)
                continue
            if not math.isfinite(number):
                logger.warning(
                    "sound volume %r is not a finite number; default kept", value
                )
                continue
            if not MIN_VOLUME <= number <= MAX_VOLUME:
                logger.warning("sound volume %r is out of range; default kept", value)
                continue
            taken.volume = number
            continue
        logger.warning("sound %r is not a sound setting; ignored", name)
    return taken


class SoundEngine:

    def __init__(self, config: Optional[SoundConfig] = None):
        self._config = config or SoundConfig()
        self._cache: dict[str, str] = {}
        self._available = False
        self._temp_dir: Optional[str] = None

    def _ensure_sounds(self) -> None:
        """Write every clip into a fresh ``_temp_dir`` and set ``_available``."""
        if self._available:
            return
        try:
            import tempfile

            self._temp_dir = tempfile.mkdtemp(prefix="qat_sounds_")
            self._gen_tone(
                "buy", [(180, 60), (220, 50), (280, 50), (350, 70), (440, 80)]
            )
            self._gen_tone(
                "sell", [(880, 80), (1100, 60), (1320, 60), (1100, 50), (1320, 100)]
            )
            self._gen_tone("error", [(600, 100), (400, 100), (300, 150)])
            self._gen_tone("state", [(800, 30)])
            self._gen_tone("track", [(1400, 35)])
            self._gen_sniper("fire")
            self._gen_coins_in_bucket("profit")
            self._gen_water_drip("drip")
            self._available = True
        except Exception as exc:
            logger.warning("Sound engine unavailable: %s", exc)

    def _gen_sniper(self, name: str) -> None:
        """Write a rifle-shot WAV into ``_temp_dir`` and cache it under ``name``.

        Concatenates a 6ms ``crack``, an 18ms ``blast``, a 120ms ``body`` and
        a 260ms ``tail``.
        """
        import math, struct, wave, io, os, random

        rng = random.SystemRandom()
        sample_rate = 22050

        crack_ms = 6
        crack_n = int(sample_rate * crack_ms / 1000)
        crack = []
        # hp subtracts a running mean of wn, approximating a high-pass filter.
        _prev = 0.0
        for i in range(crack_n):
            wn = (rng.random() * 2) - 1
            hp = wn - _prev
            _prev = 0.85 * _prev + 0.15 * wn
            env = 1.0 - (i / max(crack_n, 1)) ** 0.5
            crack.append(hp * env * 0.85)

        blast_ms = 18
        blast_n = int(sample_rate * blast_ms / 1000)
        blast = []
        _lp_state = 0.0
        for i in range(blast_n):
            wn = (rng.random() * 2) - 1
            # _lp_state is a one-pole low-pass over wn.
            _lp_state = 0.55 * _lp_state + 0.45 * wn
            t = i / max(blast_n, 1)
            if t < 0.1:
                env = 1.0
            else:
                env = math.exp(-6 * (t - 0.1))
            blast.append(_lp_state * env * 1.0)

        body_ms = 120
        body_n = int(sample_rate * body_ms / 1000)
        body = []
        for i in range(body_n):
            t = i / sample_rate
            tone = (
                math.sin(2 * math.pi * 90 * t) * 0.6
                + math.sin(2 * math.pi * 63 * t) * 0.4
            )
            wn = (rng.random() * 2) - 1
            body_env = math.exp(-6 * t)
            body.append((tone * 0.7 + wn * 0.3) * body_env * 0.75)

        tail_ms = 260
        tail_n = int(sample_rate * tail_ms / 1000)
        tail = []
        for i in range(tail_n):
            t = i / sample_rate
            wn = (rng.random() * 2) - 1
            tail.append(wn * math.exp(-5 * t) * 0.12)

        all_float = crack + blast + body + tail
        all_samples = []
        for v in all_float:
            v = max(-1.0, min(1.0, v))
            all_samples.append(int(v * self._config.volume * 32767))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f"<{len(all_samples)}h", *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, "wb") as f:
            f.write(buf.getvalue())
        self._cache[name] = path

    def _gen_coins_in_bucket(self, name: str) -> None:
        """Write a coins-in-bucket WAV into ``_temp_dir`` and cache it under
        ``name``.

        Each entry of ``coins`` strikes at 0, 135 and 280ms inside a 500ms
        buffer, layering a noise tink, a detuned ring and a bucket body.
        """
        import math, struct, wave, io, os, random

        rng = random.SystemRandom()
        sample_rate = 22050
        total_ms = 500
        total_n = int(sample_rate * total_ms / 1000)
        buf_out = [0.0] * total_n

        # One coin = (strike_time_ms, ring_f1_Hz, ring_f2_Hz, amp)
        coins = [
            (0, 2650.0, 2710.0, 0.85),
            (135, 2380.0, 2460.0, 0.65),
            (280, 2820.0, 2890.0, 0.50),
        ]

        for strike_ms, f1, f2, amp in coins:
            strike_i = int(sample_rate * strike_ms / 1000)

            tink_ms = 2
            tink_n = int(sample_rate * tink_ms / 1000)
            _prev = 0.0
            for i in range(tink_n):
                idx = strike_i + i
                if idx >= total_n:
                    break
                wn = (rng.random() * 2) - 1
                # hp subtracts a running mean of wn, approximating a high-pass filter.
                hp = wn - _prev
                _prev = 0.8 * _prev + 0.2 * wn
                env = 1.0 - (i / max(tink_n, 1))
                buf_out[idx] += hp * env * amp * 0.95

            ring_ms = 140
            ring_n = int(sample_rate * ring_ms / 1000)
            for i in range(ring_n):
                idx = strike_i + i
                if idx >= total_n:
                    break
                t = i / sample_rate
                s1 = math.sin(2 * math.pi * f1 * t)
                s2 = math.sin(2 * math.pi * f2 * t)
                env = math.exp(-14 * t)
                buf_out[idx] += (s1 * 0.55 + s2 * 0.45) * env * amp * 0.40

            body_ms = 80
            body_n = int(sample_rate * body_ms / 1000)
            body_freq = 380.0 + rng.uniform(-30, 30)
            for i in range(body_n):
                idx = strike_i + i
                if idx >= total_n:
                    break
                t = i / sample_rate
                s1 = math.sin(2 * math.pi * body_freq * t)
                s2 = math.sin(2 * math.pi * (body_freq * 1.5) * t) * 0.4
                env = math.exp(-22 * t)
                buf_out[idx] += (s1 + s2) * env * amp * 0.30

        all_samples = []
        for v in buf_out:
            v = max(-1.0, min(1.0, v))
            all_samples.append(int(v * self._config.volume * 32767))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f"<{len(all_samples)}h", *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, "wb") as f:
            f.write(buf.getvalue())
        self._cache[name] = path

    def _gen_water_drip(self, name: str) -> None:
        """Write a water-drip WAV into ``_temp_dir`` and cache it under ``name``.

        A 1.5ms impact burst is followed by a sine sweeping ``f_start`` down to
        ``f_end`` over 55ms, then a 100ms ring tail, inside a 200ms buffer.
        """
        import math, struct, wave, io, os, random

        rng = random.SystemRandom()
        sample_rate = 22050
        total_ms = 200
        total_n = int(sample_rate * total_ms / 1000)
        buf_out = [0.0] * total_n

        impact_ms = 1.5
        impact_n = int(sample_rate * impact_ms / 1000)
        for i in range(impact_n):
            if i >= total_n:
                break
            wn = (rng.random() * 2) - 1
            env = 1.0 - (i / max(impact_n, 1))
            buf_out[i] += wn * env * 0.35

        sweep_ms = 55
        sweep_n = int(sample_rate * sweep_ms / 1000)
        f_start = 1400.0
        f_end = 800.0
        phase = 0.0
        for i in range(sweep_n):
            if i >= total_n:
                break
            t_frac = i / max(sweep_n, 1)
            f_now = f_start * math.exp(math.log(f_end / f_start) * t_frac)
            # phase is integrated per sample; f_now alone would not track the sweep.
            phase += 2 * math.pi * f_now / sample_rate
            t = i / sample_rate
            if i < int(sample_rate * 0.002):
                env = i / max(int(sample_rate * 0.002), 1)
            else:
                env = math.exp(-18 * (t - 0.002))
            buf_out[i] += math.sin(phase) * env * 0.70

        tail_start = sweep_n
        tail_ms = 100
        tail_n = int(sample_rate * tail_ms / 1000)
        for i in range(tail_n):
            idx = tail_start + i
            if idx >= total_n:
                break
            t = i / sample_rate
            s = math.sin(2 * math.pi * 800.0 * (idx / sample_rate))
            env = math.exp(-28 * t)
            buf_out[idx] += s * env * 0.15

        all_samples = []
        for v in buf_out:
            v = max(-1.0, min(1.0, v))
            all_samples.append(int(v * self._config.volume * 32767))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f"<{len(all_samples)}h", *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, "wb") as f:
            f.write(buf.getvalue())
        self._cache[name] = path

    def _gen_tone(self, name: str, tones: list[tuple[int, int]]) -> None:
        import math, struct, wave, io, os

        sample_rate = 22050
        all_samples = []
        for freq, dur_ms in tones:
            n = int(sample_rate * dur_ms / 1000)
            fade = min(int(sample_rate * 15 / 1000), n // 4)
            for i in range(n):
                t = i / sample_rate
                val = math.sin(2.0 * math.pi * freq * t)
                env = 1.0
                if i < fade:
                    env = i / max(fade, 1)
                elif i > n - fade:
                    env = (n - i) / max(fade, 1)
                all_samples.append(int(val * env * self._config.volume * 32767))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f"<{len(all_samples)}h", *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, "wb") as f:
            f.write(buf.getvalue())
        self._cache[name] = path

    def play(self, sound_name: str) -> None:
        if not self._config.enabled:
            return
        if sound_name == "buy" and not self._config.buy_sound:
            return
        if sound_name == "sell" and not self._config.sell_sound:
            return
        if sound_name == "error" and not self._config.error_sound:
            return
        if sound_name == "state" and not self._config.bot_state_sound:
            return
        if sound_name == "fire" and not getattr(self._config, "fire_sound", True):
            return
        if sound_name == "track" and not getattr(self._config, "track_sound", True):
            return
        if sound_name == "profit" and not getattr(self._config, "profit_sound", True):
            return
        if sound_name == "drip" and not getattr(self._config, "drip_sound", True):
            return

        self._ensure_sounds()
        if not self._available:
            return

        path = self._cache.get(sound_name)
        if not path:
            return

        try:
            import sys

            if sys.platform == "win32":
                import winsound

                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as exc:
            logger.debug("Sound playback failed: %s", exc)

    def play_buy(self) -> None:
        self.play("buy")

    def play_sell(self) -> None:
        self.play("sell")

    def play_error(self) -> None:
        self.play("error")

    def play_state_change(self) -> None:
        self.play("state")

    def play_fire(self) -> None:
        """Play the ``fire`` clip when ``SoundConfig.fire_sound`` is set."""
        self.play("fire")

    def play_track(self) -> None:
        """Play the ``track`` clip when ``SoundConfig.track_sound`` is set."""
        self.play("track")

    def play_profit(self) -> None:
        """Play the ``profit`` clip when ``SoundConfig.profit_sound`` is set."""
        self.play("profit")

    def play_drip(self) -> None:
        """Play the ``drip`` clip when ``SoundConfig.drip_sound`` is set."""
        self.play("drip")

    def update_config(self, config: SoundConfig) -> None:
        self._config = config

    def cleanup(self) -> None:
        if self._temp_dir:
            import shutil

            shutil.rmtree(self._temp_dir, ignore_errors=True)


_global_sound: Optional[SoundEngine] = None


def get_sound_engine() -> SoundEngine:
    global _global_sound
    if _global_sound is None:
        _global_sound = SoundEngine()
    return _global_sound
