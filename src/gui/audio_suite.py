"""
audio_suite.py - Music Player + Multi-Layer Ambient Drone Engine
=================================================================
4 simultaneous drone layers, musical key system, crossfade looping,
customizable effects (detune, LFO, harmonic richness).
"""

from __future__ import annotations
import math, struct, wave, os, tempfile, logging

from . import design_system as ds

logger = logging.getLogger("acervator.audio")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QComboBox,
        QSlider,
        QGroupBox,
        QFrame,
        QFileDialog,
        QListWidget,
        QSplitter,
    )
    from PySide6.QtCore import Qt, QTimer, QUrl, QRectF, Signal
    from PySide6.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient

    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_HAS_MEDIA = False
_MEDIA_ERROR = ""
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

    _HAS_MEDIA = True
except Exception as _exc:
    _MEDIA_ERROR = str(_exc)
    QMediaPlayer = None
    QAudioOutput = None
from src.gui.qt_safe_events import safe_process_events  # v3.15.99 P4.1

#: The volume ``MusicPlayerPanel`` opens its ``QAudioOutput`` at.
MUSIC_VOLUME = 0.5

KEY_MULT = {
    "C": 1.0,
    "C#": 1.05946,
    "D": 1.12246,
    "D#": 1.18921,
    "E": 1.25992,
    "F": 1.33484,
    "F#": 1.41421,
    "G": 1.49831,
    "G#": 1.58740,
    "A": 1.68179,
    "A#": 1.78180,
    "B": 1.88775,
}


class ToneGenerator:
    SR = 44100
    PRESETS = {
        "Deep Space": [
            (1.0, 0.30),
            (1.5, 0.15),
            (2.0, 0.10),
            (3.0, 0.05),
            (1.003, 0.10),
        ],
        "Theta Waves": [(1.0, 0.20), (1.03, 0.20), (0.5, 0.10), (0.515, 0.10)],
        "Crystal Cave": [
            (1.0, 0.15),
            (1.222, 0.10),
            (1.479, 0.08),
            (0.5, 0.12),
            (0.611, 0.06),
        ],
        "Ocean Floor": [
            (1.0, 0.25),
            (1.5, 0.15),
            (2.0, 0.10),
            (1.007, 0.15),
            (3.0, 0.05),
        ],
        "Quantum Field": [
            (1.0, 0.20),
            (2.0, 0.10),
            (0.5, 0.15),
            (1.002, 0.10),
            (1.5, 0.08),
        ],
        "Solar Wind": [
            (1.0, 0.15),
            (1.636, 0.10),
            (2.273, 0.08),
            (1.002, 0.10),
            (0.5, 0.12),
        ],
        "Meditation Bell": [
            (1.0, 0.20),
            (2.0, 0.08),
            (3.0, 0.04),
            (0.5, 0.10),
            (1.001, 0.05),
        ],
        "White Noise Pad": [
            (1.0, 0.05),
            (2.0, 0.05),
            (3.0, 0.04),
            (4.0, 0.03),
            (5.0, 0.03),
        ],
    }

    @classmethod
    def generate_wav(
        cls,
        preset_name,
        duration=30.0,
        master_volume=0.5,
        key="C",
        base_freq=55.0,
        detune=1.0,
        lfo_speed=1.0,
        richness=1.0,
    ):
        intervals = cls.PRESETS.get(preset_name, cls.PRESETS["Deep Space"])
        km = KEY_MULT.get(key, 1.0)
        n = int(cls.SR * duration)
        xf = int(cls.SR * 2)
        total = n + xf
        buf = bytearray()
        for i in range(total):
            t = i / cls.SR
            s = 0.0
            for iv, amp in intervals:
                f = base_freq * iv * km
                fd = f * (1.0 + (detune - 1.0) * 0.003 * math.sin(0.1 * t + f * 0.01))
                lfo = 1.0 + 0.1 * math.sin(
                    2 * math.pi * 0.05 * lfo_speed * t + f * 0.01
                )
                s += amp * lfo * math.sin(2 * math.pi * fd * t)
                if richness > 0.5:
                    s += (
                        amp
                        * 0.1
                        * (richness - 0.5)
                        * math.sin(2 * math.pi * fd * 2 * t)
                    )
            s = max(-1.0, min(1.0, s * master_volume))
            if i >= n:
                s *= 1.0 - ((i - n) / xf)
            v = int(s * 32767)
            buf.extend(struct.pack("<hh", v, v))
        bps = 4
        for i in range(xf):
            fi = i / xf
            ep = (n + i) * bps
            sp = i * bps
            if ep + 3 < len(buf) and sp + 3 < len(buf):
                el = struct.unpack_from("<h", buf, ep)[0]
                sl = struct.unpack_from("<h", buf, sp)[0]
                bl = int(sl * (1 - fi * 0.3) + el * fi * 0.3)
                bl = max(-32767, min(32767, bl))
                struct.pack_into("<hh", buf, sp, bl, bl)
        safe = preset_name.replace(" ", "_").replace("#", "s")
        path = os.path.join(tempfile.gettempdir(), f"qat_{safe}_{key}.wav")
        with wave.open(path, "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(cls.SR)
            wf.writeframes(bytes(buf[: n * bps]))
        return path


def media_pair() -> tuple:
    """A ``QAudioOutput`` and a ``QMediaPlayer`` wired together, or two Nones without QtMultimedia."""
    if not _HAS_MEDIA:
        return None, None
    from PySide6.QtMultimedia import QAudioOutput as _Output
    from PySide6.QtMultimedia import QMediaPlayer as _Player

    audio_out = _Output()
    player = _Player()
    player.setAudioOutput(audio_out)
    return audio_out, player


def _sc(func, *a, **kw):
    # v3.13.6 R61 CBF — was bare `except:` (catches KeyboardInterrupt
    # and SystemExit). This is a Qt safe-call helper used all over this
    # module to call deleted-object-prone Qt methods; swallowing is
    # deliberate (helper's purpose IS to suppress the common "wrapped
    # C/C++ object deleted" RuntimeError after widget teardown). But
    # scope to Exception so Ctrl-C still works.
    try:
        return func(*a, **kw)
    except Exception:
        return None  # sadp: R61 ACCEPT (Qt safe-call)


if _HAS_QT:

    class WaveformWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Waveform Widget")
            self._phase = 0.0
            self._layers = 0
            self._key = "C"
            self.setMinimumHeight(50)
            self.setMaximumHeight(70)

        def set_state(self, layers, key="C"):
            self._layers = layers
            self._key = key
            self.update()

        def animate(self, dt):
            if self._layers > 0:
                self._phase += dt * 2
                self.update()

        def paintEvent(self, event):
            super().paintEvent(event)
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            bg = QLinearGradient(0, 0, 0, h)
            bg.setColorAt(0, QColor(8, 8, 14))
            bg.setColorAt(1, QColor(12, 12, 22))
            p.fillRect(0, 0, w, h, bg)
            if self._layers == 0:
                p.setPen(QPen(QColor(50, 50, 70)))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "Audio idle")
                p.end()
                return
            cy = h / 2
            colors = [
                QColor(0, 200, 255),
                QColor(0, 255, 160),
                QColor(255, 180, 0),
                QColor(200, 100, 255),
            ]
            for j in range(min(self._layers, 4)):
                c = QColor(colors[j])
                c.setAlpha(100)
                p.setPen(QPen(c, 1.2))
                prev = None
                for i in range(0, w, 2):
                    t = self._phase + i / w * 4
                    y = cy + (15 + j * 5) * math.sin(
                        2 * math.pi * (0.8 + j * 0.4) * t + j * 1.2
                    )
                    if prev:
                        p.drawLine(prev[0], prev[1], i, int(y))
                    prev = (i, int(y))
            p.setPen(QPen(QColor(100, 100, 140)))
            p.setFont(QFont("Consolas", 8))
            p.drawText(w - 60, int(cy + 4), f"Key: {self._key}")
            p.end()

    class DroneLayer(QFrame):
        state_changed = Signal()

        def __init__(self, index, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Drone Layer")
            self._index = index
            self._wav = ""
            self._playing = False
            self._player = None
            self._audio_out = None
            self.setFrameShape(QFrame.StyledPanel)
            self.setStyleSheet(
                f"QFrame{{border:1px solid {ds.SETTINGS_DISABLED_DEEP};"
                f"border-radius:3px;}}"
            )
            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(2)
            h = QHBoxLayout()
            h.addWidget(QLabel(f"Layer {index+1}"))
            self._preset = QComboBox()
            self._preset.addItem("(off)", "")
            for name in ToneGenerator.PRESETS:
                self._preset.addItem(name, name)
            h.addWidget(self._preset)
            layout.addLayout(h)
            vr = QHBoxLayout()
            vr.addWidget(QLabel("Vol:"))
            self._volume = QSlider(Qt.Horizontal)
            self._volume.setRange(0, 100)
            self._volume.setValue(50 if index == 0 else 30)
            self._volume.valueChanged.connect(self._on_vol)
            vr.addWidget(self._volume)
            self._vl = QLabel(f"{self._volume.value()}%")
            self._vl.setFixedWidth(30)
            vr.addWidget(self._vl)
            layout.addLayout(vr)
            if _HAS_MEDIA:
                try:
                    self._audio_out, self._player = media_pair()
                    self._audio_out.setVolume(self._volume.value() / 100)
                    self._player.mediaStatusChanged.connect(self._on_end)
                    self._player.errorOccurred.connect(self._on_error)
                    self._player.playbackStateChanged.connect(self._on_state)
                except Exception as exc:
                    self._player = None
                    logger.error("DroneLayer %d init failed: %s", index, exc)

        def _on_error(self, error, msg=""):
            logger.error("DroneLayer %d error: %s %s", self._index, error, msg)
            self._playing = False
            self.state_changed.emit()

        def _on_state(self, state):
            try:
                if state == QMediaPlayer.PlaybackState.StoppedState and self._playing:
                    err = self._player.errorString() if self._player else ""
                    if err:
                        logger.warning("DroneLayer %d stopped: %s", self._index, err)
                        self._playing = False
                        self.state_changed.emit()
            except Exception as _sf_exc:  # noqa: BLE001
                logger.debug("audio suite preview failed: %s", _sf_exc)

        def _on_vol(self, v):
            self._vl.setText(f"{v}%")
            if self._audio_out:
                _sc(self._audio_out.setVolume, v / 100)

        def gen_play(self, key, base_freq, detune, lfo_speed, richness):
            preset = self._preset.currentData()
            if not preset or not self._player:
                self.stop()
                return
            try:
                self._wav = ToneGenerator.generate_wav(
                    preset, 30.0, 0.8, key, base_freq, detune, lfo_speed, richness
                )
                file_size = (
                    os.path.getsize(self._wav) if os.path.exists(self._wav) else 0
                )
                logger.info(
                    "DroneLayer %d: generated %s (%dKB)",
                    self._index,
                    self._wav,
                    file_size // 1024,
                )
                self._player.setSource(QUrl.fromLocalFile(self._wav))
                self._player.play()
                self._playing = True
                self.state_changed.emit()
            except Exception as e:
                logger.error("Layer %d gen_play failed: %s", self._index, e)

        def stop(self):
            if self._player:
                _sc(self._player.stop)
            self._playing = False
            self.state_changed.emit()

        @property
        def is_active(self):
            return self._playing and bool(self._preset.currentData())

        def _on_end(self, status):
            try:
                if status == QMediaPlayer.MediaStatus.EndOfMedia and self._wav:
                    self._player.setSource(QUrl.fromLocalFile(self._wav))
                    self._player.play()
            except Exception as exc:
                # v3.13.6 R28 FL + R61 CBF — was bare `except:` which
                # catches BaseException (KeyboardInterrupt, SystemExit).
                # Now Exception-scoped + logged.
                logger.warning(
                    "drone EndOfMedia handler: %s: %s", type(exc).__name__, exc
                )

    class MusicPlayerPanel(QGroupBox):
        def __init__(self, parent=None):
            super().__init__("Music Player", parent)
            self.setAccessibleName("Music Player Panel")
            layout = QVBoxLayout(self)
            layout.setSpacing(4)
            if not _HAS_MEDIA:
                layout.addWidget(
                    QLabel(
                        "Qt Multimedia not available.\npip install PySide6-Multimedia"
                    )
                )
                self._player = None
                self._files = []
                return
            self._pl = QListWidget()
            self._pl.setMaximumHeight(100)
            layout.addWidget(self._pl)
            br = QHBoxLayout()
            ab = QPushButton("Add")
            ab.clicked.connect(self._add)
            br.addWidget(ab)
            self._pb = QPushButton("Play")
            self._pb.clicked.connect(self._tog)
            self._pb.setStyleSheet("font-weight:bold;")
            br.addWidget(self._pb)
            sb = QPushButton("Stop")
            sb.clicked.connect(self._stp)
            br.addWidget(sb)
            nb = QPushButton("Next")
            nb.clicked.connect(self._nxt)
            br.addWidget(nb)
            layout.addLayout(br)
            vr = QHBoxLayout()
            vr.addWidget(QLabel("Vol:"))
            self._vol = QSlider(Qt.Horizontal)
            self._vol.setRange(0, 100)
            self._vol.setValue(50)
            self._vol.valueChanged.connect(self._sv)
            vr.addWidget(self._vol)
            layout.addLayout(vr)
            self._now = QLabel("Nothing playing")
            self._now.setStyleSheet(f"color:{ds.FOLD_SOURCE_MANUAL};font-size:10px;")
            layout.addWidget(self._now)
            self._playing = False
            self._files = []
            try:
                self._ao, self._player = media_pair()
                self._ao.setVolume(MUSIC_VOLUME)
                self._player.mediaStatusChanged.connect(self._oe)
            except Exception as exc:
                # v3.13.6 R28 FL + R61 CBF — was bare `except:`
                logger.warning(
                    "MusicPlayer Qt init failed: %s: %s", type(exc).__name__, exc
                )
                self._player = None

        def _add(self):
            fs, _ = QFileDialog.getOpenFileNames(
                self, "Music", "", "Audio (*.mp3 *.wav *.ogg *.flac *.m4a)"
            )
            for f in fs:
                self._files.append(f)
                self._pl.addItem(os.path.basename(f))

        def _tog(self):
            if not self._player:
                return
            if self._playing:
                _sc(self._player.pause)
                self._pb.setText("Play")
                self._playing = False
            else:
                if not self._files:
                    return
                self._pi(max(0, self._pl.currentRow()))

        def _pi(self, i):
            if not self._player or i >= len(self._files):
                return
            try:
                self._player.setSource(QUrl.fromLocalFile(self._files[i]))
                self._player.play()
                self._pb.setText("Pause")
                self._playing = True
                self._now.setText(f"Playing: {os.path.basename(self._files[i])}")
                self._pl.setCurrentRow(i)
            except Exception as exc:
                # v3.13.6 R28 FL + R61 CBF — was bare `except:`
                logger.warning(
                    "music play track %d failed: %s: %s", i, type(exc).__name__, exc
                )

        def _stp(self):
            if self._player:
                _sc(self._player.stop)
            self._pb.setText("Play")
            self._playing = False

        def _nxt(self):
            if self._files:
                self._pi((self._pl.currentRow() + 1) % len(self._files))

        def _sv(self, v):
            if hasattr(self, "_ao") and self._ao:
                _sc(self._ao.setVolume, v / 100)

        def _oe(self, st):
            try:
                if st == QMediaPlayer.MediaStatus.EndOfMedia:
                    self._nxt()
            except Exception as exc:
                # v3.13.6 R28 FL + R61 CBF — was bare `except:`
                logger.warning(
                    "music EndOfMedia handler: %s: %s", type(exc).__name__, exc
                )

    class DroneEnginePanel(QGroupBox):
        drone_state = Signal(int, str)

        def __init__(self, parent=None):
            super().__init__("Ambient Drone Engine", parent)
            layout = QVBoxLayout(self)
            layout.setSpacing(4)
            cr = QHBoxLayout()
            cr.addWidget(QLabel("Key:"))
            self._key = QComboBox()
            for k in KEY_MULT:
                self._key.addItem(k, k)
            cr.addWidget(self._key)
            cr.addWidget(QLabel("Base:"))
            self._bf = QComboBox()
            for l, v in [
                ("27.5Hz", 27.5),
                ("55Hz", 55),
                ("110Hz", 110),
                ("220Hz", 220),
            ]:
                self._bf.addItem(l, v)
            self._bf.setCurrentIndex(1)
            cr.addWidget(self._bf)
            layout.addLayout(cr)
            fx = QHBoxLayout()
            fx.addWidget(QLabel("Detune:"))
            self._det = QSlider(Qt.Horizontal)
            self._det.setRange(0, 100)
            self._det.setValue(50)
            self._det.setToolTip("0=none, 100=heavy chorus")
            fx.addWidget(self._det)
            fx.addWidget(QLabel("LFO:"))
            self._lfo = QSlider(Qt.Horizontal)
            self._lfo.setRange(10, 300)
            self._lfo.setValue(100)
            self._lfo.setToolTip("Speed: 10=slow, 300=fast")
            fx.addWidget(self._lfo)
            fx.addWidget(QLabel("Rich:"))
            self._rich = QSlider(Qt.Horizontal)
            self._rich.setRange(0, 100)
            self._rich.setValue(30)
            self._rich.setToolTip("0=pure sine, 100=rich overtones")
            fx.addWidget(self._rich)
            layout.addLayout(fx)
            self._layers = []
            for i in range(4):
                ly = DroneLayer(i)
                ly.state_changed.connect(self._es)
                self._layers.append(ly)
                layout.addWidget(ly)
            br = QHBoxLayout()
            gb = QPushButton("Generate All")
            gb.clicked.connect(self._gen_all)
            br.addWidget(gb)
            pb = QPushButton("Play All")
            pb.setStyleSheet(f"font-weight:bold;color:{ds.FOLD_SOURCE_MANUAL};")
            pb.clicked.connect(self._gen_all)
            br.addWidget(pb)
            sb = QPushButton("Stop All")
            sb.clicked.connect(self._stop_all)
            br.addWidget(sb)
            ks = QPushButton("Key +1")
            ks.setToolTip("Shift key up and regenerate")
            ks.clicked.connect(self._key_up)
            br.addWidget(ks)
            layout.addLayout(br)
            self._st = QLabel("Select presets per layer, then Generate All")
            self._st.setStyleSheet(f"color:{ds.CARD_METRIC_LABEL};font-size:10px;")
            self._st.setWordWrap(True)
            layout.addWidget(self._st)

        def _fx(self):
            return dict(
                key=self._key.currentData(),
                base_freq=self._bf.currentData(),
                detune=self._det.value() / 50,
                lfo_speed=self._lfo.value() / 100,
                richness=self._rich.value() / 100,
            )

        def _gen_all(self):
            fx = self._fx()
            a = 0
            errors = []
            self._st.setText("Generating...")
            safe_process_events("legacy P4.1 site")
            for ly in self._layers:
                if ly._preset.currentData():
                    ly.gen_play(**fx)
                    a += 1
                    if ly._wav and os.path.exists(ly._wav):
                        os.path.getsize(ly._wav) // 1024
                    else:
                        errors.append(f"L{ly._index+1}: no WAV")
            if errors:
                self._st.setText(f"{a} layer(s) — ERRORS: {'; '.join(errors)}")
            else:
                self._st.setText(
                    f"{a} layer(s) playing in {fx['key']} | "
                    f"det={self._det.value()}% lfo={self._lfo.value()}% "
                    f"rich={self._rich.value()}%"
                    f" | Media: {'OK' if _HAS_MEDIA else 'UNAVAILABLE'}"
                )

        def _stop_all(self):
            for ly in self._layers:
                ly.stop()
            self._st.setText("Stopped")

        def _key_up(self):
            self._key.setCurrentIndex(
                (self._key.currentIndex() + 1) % self._key.count()
            )
            self._st.setText(f"Shifting to {self._key.currentData()}...")
            safe_process_events("legacy P4.1 site")
            self._gen_all()

        def _es(self):
            c = sum(1 for l in self._layers if l.is_active)
            self.drone_state.emit(c, self._key.currentData())

    class AudioSuiteTab(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Audio Suite Tab")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(4)
            self._wf = WaveformWidget()
            layout.addWidget(self._wf)
            sp = QSplitter(Qt.Horizontal)
            sp.setHandleWidth(5)
            sp.setChildrenCollapsible(False)
            self._mp = MusicPlayerPanel()
            sp.addWidget(self._mp)
            self._de = DroneEnginePanel()
            self._de.drone_state.connect(lambda n, k: self._wf.set_state(n, k))
            sp.addWidget(self._de)
            sp.setSizes([300, 500])
            layout.addWidget(sp)
            self._at = QTimer(self)
            self._at.timeout.connect(lambda: self._wf.animate(0.033))
            self._at.start(33)
