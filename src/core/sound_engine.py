"""
sound_engine.py - Audio notifications for trading events
=========================================================
All audio/system imports are lazy-loaded inside methods to avoid
triggering AV heuristics when bundled by PyInstaller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("acervator.sound")


@dataclass
class SoundConfig:
    enabled: bool = True
    buy_sound: bool = True
    sell_sound: bool = True
    error_sound: bool = True
    bot_state_sound: bool = True
    fire_sound: bool = True   # MEM-236 — scrum/fold fire SFX
    track_sound: bool = True  # MEM-236 — tracking beep
    profit_sound: bool = True # MEM-238 — coins-in-bucket on P/L increase
    drip_sound: bool = True   # MEM-238 — water drip on accumulation
    volume: float = 0.7


class SoundEngine:

    def __init__(self, config: Optional[SoundConfig] = None):
        self._config = config or SoundConfig()
        self._cache: dict[str, str] = {}
        self._available = False
        self._temp_dir: Optional[str] = None

    def _ensure_sounds(self) -> None:
        """Generate sounds on first use, not at init."""
        if self._available:
            return
        try:
            import tempfile
            self._temp_dir = tempfile.mkdtemp(prefix="qat_sounds_")
            self._gen_tone("buy", [(180, 60), (220, 50), (280, 50), (350, 70), (440, 80)])
            self._gen_tone("sell", [(880, 80), (1100, 60), (1320, 60), (1100, 50), (1320, 100)])
            self._gen_tone("error", [(600, 100), (400, 100), (300, 150)])
            self._gen_tone("state", [(800, 30)])
            # MEM-236 — tracking beep: short clean 1.4kHz pulse, 35ms
            self._gen_tone("track", [(1400, 35)])
            # MEM-236 — sniper rifle fire SFX synthesized via _gen_sniper
            self._gen_sniper("fire")
            # MEM-238 — coins-in-bucket (P/L increase)
            self._gen_coins_in_bucket("profit")
            # MEM-238 — water drip (accumulation)
            self._gen_water_drip("drip")
            self._available = True
        except Exception as exc:
            logger.warning("Sound engine unavailable: %s", exc)

    def _gen_sniper(self, name: str) -> None:
        """MEM-236 — synthesize a sniper rifle shot.

        Layers:
          1. CRACK: ~6ms of high-frequency filtered noise (5-12kHz) — the
             supersonic bullet crack / action snap.
          2. MUZZLE BLAST: ~18ms of mid-low noise (80-800Hz) — the
             explosive propellant report, loudest element.
          3. BODY/BOOM: ~120ms of low-frequency tone + noise (60-140Hz),
             exponential decay — the pressure wave rolling off.
          4. TAIL: ~260ms of very quiet ambient decay noise.

        Total duration ~400ms. Envelope: near-instant attack, exponential
        decay. No reverb (keep it dry — the operator can add space via
        headphones/speakers if desired).

        Pure Python + stdlib (random, math, wave, struct). No numpy
        dependency so this runs in minimal installs.
        """
        import math, struct, wave, io, os, random
        sample_rate = 22050

        # Initial crack (6ms) — high-freq filtered noise spike
        crack_ms = 6
        crack_n = int(sample_rate * crack_ms / 1000)
        crack = []
        # High-pass pseudo-filter: take white noise, subtract a running
        # short mean (approximates a HPF).
        _prev = 0.0
        for i in range(crack_n):
            wn = (random.random() * 2) - 1
            hp = wn - _prev
            _prev = 0.85 * _prev + 0.15 * wn
            env = 1.0 - (i / max(crack_n, 1)) ** 0.5  # fast decay
            crack.append(hp * env * 0.85)

        # Muzzle blast (18ms) — mid noise + sharp attack
        blast_ms = 18
        blast_n = int(sample_rate * blast_ms / 1000)
        blast = []
        _lp_state = 0.0
        for i in range(blast_n):
            wn = (random.random() * 2) - 1
            # Low-pass smoothing (~mid band)
            _lp_state = 0.55 * _lp_state + 0.45 * wn
            # Attack: first 2ms at full, then exp decay
            t = i / max(blast_n, 1)
            if t < 0.1:
                env = 1.0
            else:
                env = math.exp(-6 * (t - 0.1))
            blast.append(_lp_state * env * 1.0)

        # Body/boom (120ms) — 90Hz sine + pink-ish noise, exp decay
        body_ms = 120
        body_n = int(sample_rate * body_ms / 1000)
        body = []
        for i in range(body_n):
            t = i / sample_rate
            # Low tone (slightly detuned 2-freq for weight)
            tone = (math.sin(2 * math.pi * 90 * t) * 0.6
                    + math.sin(2 * math.pi * 63 * t) * 0.4)
            # Pink-ish noise (LPF'd white)
            wn = (random.random() * 2) - 1
            body_env = math.exp(-6 * t)
            body.append((tone * 0.7 + wn * 0.3) * body_env * 0.75)

        # Tail (260ms) — very quiet ambient noise decay
        tail_ms = 260
        tail_n = int(sample_rate * tail_ms / 1000)
        tail = []
        for i in range(tail_n):
            t = i / sample_rate
            wn = (random.random() * 2) - 1
            tail.append(wn * math.exp(-5 * t) * 0.12)

        # Concatenate + clip + apply volume
        all_float = crack + blast + body + tail
        all_samples = []
        for v in all_float:
            v = max(-1.0, min(1.0, v))
            all_samples.append(int(v * self._config.volume * 32767))

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f'<{len(all_samples)}h', *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, 'wb') as f:
            f.write(buf.getvalue())
        self._cache[name] = path

    def _gen_coins_in_bucket(self, name: str) -> None:
        """MEM-238 — synthesize 2-3 coins dropping into a metal bucket.

        Operator directive: "Coins dropping into a bucket for P/L
        increases."

        Anatomy of a coin drop (physical):
          - Metal-on-metal strike: very sharp HF transient (<2ms) —
            the "tink" at the moment of contact.
          - Pitched ring: the coin oscillates; two partials around
            2-3kHz with slight detuning for a brass/copper feel,
            decaying over ~120-180ms.
          - Bucket body: lower-frequency hollow resonance (~280-420Hz)
            excited by the impact, shorter decay.

        We synthesize 2 coins staggered ~130ms apart so the second
        "tink" catches the first's body ring-out, producing the
        characteristic jingly decay of coins settling. A third coin
        at ~260ms adds natural variety without cluttering.

        Frequency bands (per AUDIO_CRAFT.md conventions):
          - Tink:   HIGH (5-12 kHz — noise transient)
          - Ring:   MID (2-3 kHz — pitched sines)
          - Body:   LOW-MID (280-420 Hz — bucket resonance)

        Total duration ~500ms. Pure stdlib.
        """
        import math, struct, wave, io, os, random

        sample_rate = 22050
        total_ms = 500
        total_n = int(sample_rate * total_ms / 1000)
        buf_out = [0.0] * total_n

        # One coin = (strike_time_ms, ring_f1_Hz, ring_f2_Hz, amp)
        # Each coin slightly different so they don't sound identical.
        coins = [
            (0,   2650.0, 2710.0, 0.85),  # first coin — loudest
            (135, 2380.0, 2460.0, 0.65),  # second coin, slightly lower
            (280, 2820.0, 2890.0, 0.50),  # third coin, highest/quietest
        ]

        for strike_ms, f1, f2, amp in coins:
            strike_i = int(sample_rate * strike_ms / 1000)

            # Layer 1: TINK — very sharp HF noise burst, 2ms
            tink_ms = 2
            tink_n = int(sample_rate * tink_ms / 1000)
            _prev = 0.0
            for i in range(tink_n):
                idx = strike_i + i
                if idx >= total_n:
                    break
                wn = (random.random() * 2) - 1
                # High-pass: subtract running mean (keeps high freqs)
                hp = wn - _prev
                _prev = 0.8 * _prev + 0.2 * wn
                env = 1.0 - (i / max(tink_n, 1))  # linear fast decay
                buf_out[idx] += hp * env * amp * 0.95

            # Layer 2: RING — two detuned sines, ~140ms exp decay.
            # Detuning produces beating that sounds like brass/copper
            # rather than a pure tone.
            ring_ms = 140
            ring_n = int(sample_rate * ring_ms / 1000)
            for i in range(ring_n):
                idx = strike_i + i
                if idx >= total_n:
                    break
                t = i / sample_rate
                # Two partials, detuned ~60Hz apart
                s1 = math.sin(2 * math.pi * f1 * t)
                s2 = math.sin(2 * math.pi * f2 * t)
                env = math.exp(-14 * t)  # fast ring decay
                buf_out[idx] += (s1 * 0.55 + s2 * 0.45) * env * amp * 0.40

            # Layer 3: BODY — bucket resonance, 380Hz-ish, 80ms
            body_ms = 80
            body_n = int(sample_rate * body_ms / 1000)
            body_freq = 380.0 + random.uniform(-30, 30)
            for i in range(body_n):
                idx = strike_i + i
                if idx >= total_n:
                    break
                t = i / sample_rate
                # Two close lows for a woodier "thunk"
                s1 = math.sin(2 * math.pi * body_freq * t)
                s2 = math.sin(2 * math.pi * (body_freq * 1.5) * t) * 0.4
                env = math.exp(-22 * t)  # fast body decay
                buf_out[idx] += (s1 + s2) * env * amp * 0.30

        # Normalize and write
        all_samples = []
        for v in buf_out:
            v = max(-1.0, min(1.0, v))
            all_samples.append(int(v * self._config.volume * 32767))

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f'<{len(all_samples)}h', *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, 'wb') as f:
            f.write(buf.getvalue())
        self._cache[name] = path

    def _gen_water_drip(self, name: str) -> None:
        """MEM-238 — synthesize a water drip ("ploink").

        Operator directive: "Dripping water for accumulation."

        Anatomy of a water drip:
          - Impact: very brief noise burst as drop meets surface (1-2ms).
          - Cavity ploink: a sine with FAST DOWNWARD frequency sweep.
            Physical mechanism: an air bubble briefly forms and
            collapses; the oscillation frequency falls as the cavity
            shrinks. This sweep (~1400Hz → ~800Hz over ~40ms) is what
            makes the sound unmistakably "water drop" rather than
            generic bell.
          - Faint ring tail: the final cavity resonance decays, ~100ms.

        Total duration ~200ms. Intentionally short — dripping water
        in a trading app should feel like a passing tick, not an
        event requiring attention. Pure stdlib.
        """
        import math, struct, wave, io, os, random

        sample_rate = 22050
        total_ms = 200
        total_n = int(sample_rate * total_ms / 1000)
        buf_out = [0.0] * total_n

        # Layer 1: IMPACT — tiny noise burst, 1.5ms
        impact_ms = 1.5
        impact_n = int(sample_rate * impact_ms / 1000)
        for i in range(impact_n):
            if i >= total_n:
                break
            wn = (random.random() * 2) - 1
            env = 1.0 - (i / max(impact_n, 1))
            buf_out[i] += wn * env * 0.35

        # Layer 2: CAVITY PLOINK — frequency-swept sine.
        # Starts at ~1400 Hz, sweeps down to ~800 Hz over ~40ms.
        # This is the SIGNATURE of a water drip. Without this sweep
        # it would just sound like a generic tonk.
        sweep_ms = 55
        sweep_n = int(sample_rate * sweep_ms / 1000)
        f_start = 1400.0
        f_end = 800.0
        phase = 0.0
        for i in range(sweep_n):
            if i >= total_n:
                break
            t_frac = i / max(sweep_n, 1)
            # Exponential sweep sounds more natural than linear —
            # frequency halves more quickly early, then stabilizes.
            f_now = f_start * math.exp(math.log(f_end / f_start) * t_frac)
            # Integrate phase: advancing by 2*pi*f_now/sample_rate per sample
            phase += 2 * math.pi * f_now / sample_rate
            # Attack fast (2ms), sustain through sweep, decay at end
            t = i / sample_rate
            if i < int(sample_rate * 0.002):  # first 2ms
                env = i / max(int(sample_rate * 0.002), 1)
            else:
                env = math.exp(-18 * (t - 0.002))
            buf_out[i] += math.sin(phase) * env * 0.70

        # Layer 3: RING TAIL — soft residue at ~800 Hz for 100ms.
        # The sweep ends; a faint resonance lingers.
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

        # Normalize and write
        all_samples = []
        for v in buf_out:
            v = max(-1.0, min(1.0, v))
            all_samples.append(int(v * self._config.volume * 32767))

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f'<{len(all_samples)}h', *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, 'wb') as f:
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
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack(f'<{len(all_samples)}h', *all_samples))

        path = os.path.join(self._temp_dir, f"{name}.wav")
        with open(path, 'wb') as f:
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
        # MEM-236
        if sound_name == "fire" and not getattr(self._config, "fire_sound", True):
            return
        if sound_name == "track" and not getattr(self._config, "track_sound", True):
            return
        # MEM-238
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

    # MEM-236 — operator-requested
    def play_fire(self) -> None:
        """Sniper rifle shot SFX for scrum/fold firing events."""
        self.play("fire")

    def play_track(self) -> None:
        """Short beep for tracking events (repeatedly called at pacing
        determined by GUI based on scrum phase)."""
        self.play("track")

    # MEM-238 — operator-requested
    def play_profit(self) -> None:
        """Coins-in-bucket SFX for P/L increase events."""
        self.play("profit")

    def play_drip(self) -> None:
        """Water drip SFX for accumulation events (fold extra_asset > 0)."""
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
