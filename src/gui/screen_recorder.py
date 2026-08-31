"""
screen_recorder.py — Embedded Widget Screen Recorder
======================================================
Records any QWidget to video with zero frame pile-up.

Engine priority:
  1. OpenCV (cv2)   → direct MP4 stream, no temp files
  2. ffmpeg chunks  → 30s rolling chunks encoded + PNGs deleted immediately,
                      chunks concatenated to final MP4 at stop
  3. Pillow GIF     → frames sampled at 10fps, written as animated GIF at stop
                      (capped at MAX_GIF_FRAMES to bound memory)
  4. Rolling PNG    → at most one 30s window of PNGs on disk at any time;
                      older frames deleted as new ones arrive

All engines guarantee bounded disk usage during recording.

"""

from __future__ import annotations

import os
import sys
import time
import shutil
import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.gui.recorder")

log = logging.getLogger("acervator.recorder")

# ── Tuning constants ──────────────────────────────────────────────────────────
CHUNK_SECONDS = 30  # encode a new chunk every this many seconds
GIF_SAMPLE_RATE = 3  # keep 1 in every N frames for GIF (= fps/N effective fps)
MAX_GIF_FRAMES = 600  # max frames held in memory for GIF (~60s at 10fps)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from PySide6.QtWidgets import (
        QWidget,
        QHBoxLayout,
        QPushButton,
        QLabel,
    )
    from PySide6.QtCore import QTimer, Signal, QObject
    from PySide6.QtGui import QImage

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


# ── Capability detection ──────────────────────────────────────────────────────


def _has_cv2() -> bool:
    try:
        import cv2  # noqa

        return True
    except ImportError:
        return False


def _has_ffmpeg() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def _has_pillow() -> bool:
    try:
        from PIL import Image  # noqa

        return True
    except ImportError:
        return False


def _best_engine() -> str:
    if _has_cv2():
        return "cv2"
    if _has_ffmpeg():
        return "ffmpeg"
    if _has_pillow():
        return "gif"
    return "png"


# ── Signals ───────────────────────────────────────────────────────────────────

if _HAS_QT:

    class _RecorderSignals(QObject):
        status_changed = Signal(str, str)
        frame_captured = Signal(int)

else:

    class _RecorderSignals:  # type: ignore
        def __init__(self):
            pass


# ── Core recorder ─────────────────────────────────────────────────────────────


class ScreenRecorder:
    """
    Captures a QWidget at fixed FPS with bounded disk/memory usage.

    cv2   → writes directly to MP4, no temp files ever
    ffmpeg→ rolling 30s chunks: PNGs encoded + deleted every 30s,
            chunks concatenated to final MP4 at stop()
    gif   → frames sampled at GIF_SAMPLE_RATE, held in memory,
            written as animated GIF at stop()
    png   → rolling window: only the last CHUNK_SECONDS of PNGs kept,
            older frames deleted as recording continues
    """

    def __init__(self, target, fps: int = 30, output_dir: str = ""):
        self._target = target
        self._fps = fps
        if not output_dir:
            import sys as _sr_sys

            if getattr(_sr_sys, "frozen", False):
                _proj = Path(_sr_sys.executable).parent
            else:
                _proj = Path(__file__).resolve().parent.parent.parent
            output_dir = str(_proj / "logs" / "simulator" / "recordings")
        self._out_dir = Path(output_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._engine = _best_engine()

        # cv2 state
        self._writer = None

        # ffmpeg chunk state
        self._frame_dir: Optional[Path] = None
        self._chunk_dir: Optional[Path] = None
        self._chunks: list[Path] = []
        self._chunk_frame_start = 0  # frame_n when current chunk started
        self._chunk_n = 0  # chunk counter

        # GIF state
        self._gif_frames: list = []  # PIL Image objects (sampled)

        # Common
        self._timer = None
        self._running = False
        self._frame_n = 0
        self._start_ts = 0.0
        self.last_output: str = ""
        self.signals = _RecorderSignals()
        log.info(f"ScreenRecorder engine: {self._engine}")

    @property
    def is_recording(self) -> bool:
        return self._running

    # ── Chunk size in frames ──────────────────────────────────────────────────
    @property
    def _chunk_frames(self) -> int:
        return max(1, CHUNK_SECONDS * self._fps)

    # ── Start ─────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return False
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self._engine == "cv2":
            ok = self._start_cv2(ts)
        elif self._engine == "ffmpeg":
            ok = self._start_ffmpeg(ts)
        elif self._engine == "gif":
            ok = self._start_gif(ts)
        else:
            ok = self._start_png_rolling(ts)

        if not ok:
            return False

        self._running = True
        self._frame_n = 0
        self._start_ts = time.time()
        self._timer = QTimer()
        self._timer.setInterval(max(1, 1000 // self._fps))
        self._timer.timeout.connect(self._capture_frame)
        self._timer.start()
        self.signals.status_changed.emit("● REC  0s", "#ff3366")
        return True

    def _start_cv2(self, ts: str) -> bool:
        import cv2

        out_path = self._out_dir / f"ACV_Sim_{ts}.mp4"
        self.last_output = str(out_path)
        px = self._grab_pixmap()
        if px is None:
            self.signals.status_changed.emit("Grab failed", "#ff3366")
            return False
        w, h = px.width(), px.height()
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(out_path), fourcc, self._fps, (w, h))
        if not self._writer.isOpened():
            self.signals.status_changed.emit("Encoder failed", "#ff3366")
            return False
        log.info(f"cv2 → {out_path} ({w}x{h} @ {self._fps}fps)")
        return True

    def _start_ffmpeg(self, ts: str) -> bool:
        # Working dir for current chunk's PNGs
        self._frame_dir = self._out_dir / f"_frames_{ts}"
        self._frame_dir.mkdir(parents=True, exist_ok=True)
        # Separate dir for encoded chunks (not PNGs)
        self._chunk_dir = self._out_dir / f"_chunks_{ts}"
        self._chunk_dir.mkdir(parents=True, exist_ok=True)
        self._chunks = []
        self._chunk_n = 0
        self._chunk_frame_start = 0
        self.last_output = str(self._out_dir / f"ACV_Sim_{ts}.mp4")
        px = self._grab_pixmap()
        if px is None:
            self.signals.status_changed.emit("Grab failed", "#ff3366")
            return False
        log.info(f"ffmpeg chunks → {self.last_output} @ {self._fps}fps")
        return True

    def _start_gif(self, ts: str) -> bool:
        self._gif_frames = []
        self.last_output = str(self._out_dir / f"ACV_Sim_{ts}.gif")
        px = self._grab_pixmap()
        if px is None:
            self.signals.status_changed.emit("Grab failed", "#ff3366")
            return False
        log.info(f"Pillow GIF → {self.last_output}")
        return True

    def _start_png_rolling(self, ts: str) -> bool:
        self._frame_dir = self._out_dir / f"_frames_{ts}"
        self._frame_dir.mkdir(parents=True, exist_ok=True)
        self._chunk_frame_start = 0
        self.last_output = str(self._frame_dir)
        px = self._grab_pixmap()
        if px is None:
            self.signals.status_changed.emit("Grab failed", "#ff3366")
            return False
        log.info(f"PNG rolling window → {self._frame_dir}")
        return True

    # ── Stop ──────────────────────────────────────────────────────────────────

    def stop(self) -> str:
        if not self._running:
            return self.last_output
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        elapsed = time.time() - self._start_ts

        if self._engine == "cv2":
            self._stop_cv2(elapsed)

        elif self._engine == "ffmpeg":
            self._stop_ffmpeg(elapsed)

        elif self._engine == "gif":
            self._stop_gif(elapsed)

        else:
            self._stop_png_rolling(elapsed)

        return self.last_output

    def _stop_cv2(self, elapsed: float):
        if self._writer:
            self._writer.release()
            self._writer = None
        log.info(f"Saved: {self.last_output} ({self._frame_n}f {elapsed:.1f}s)")
        self.signals.status_changed.emit(
            f"Saved {Path(self.last_output).name}", "#00ff88"
        )

    def _stop_ffmpeg(self, elapsed: float):
        # Encode any remaining frames in the current partial chunk
        remaining = self._frame_n - self._chunk_frame_start
        if remaining > 0 and self._frame_dir:
            self.signals.status_changed.emit("Encoding final chunk...", "#ffaa00")
            chunk = self._encode_chunk(self._chunk_frame_start, remaining)
            if chunk:
                self._chunks.append(chunk)

        # Clean up frame dir (all PNGs should be gone by now, but ensure)
        if self._frame_dir:
            shutil.rmtree(self._frame_dir, ignore_errors=True)
            self._frame_dir = None

        if not self._chunks:
            self.signals.status_changed.emit("No chunks encoded", "#ff3366")
            return

        if len(self._chunks) == 1:
            # Single chunk — just rename it
            try:
                shutil.move(str(self._chunks[0]), self.last_output)
                if self._chunk_dir:
                    shutil.rmtree(self._chunk_dir, ignore_errors=True)
                log.info(f"Saved (1 chunk): {self.last_output}")
                self.signals.status_changed.emit(
                    f"Saved {Path(self.last_output).name}", "#00ff88"
                )
            except Exception as e:
                log.error(f"Chunk rename failed: {e}")
                self.last_output = str(self._chunks[0])
                self.signals.status_changed.emit(
                    f"Saved {Path(self._chunks[0]).name}", "#00ff88"
                )
        else:
            # Concatenate all chunks
            self.signals.status_changed.emit(
                f"Joining {len(self._chunks)} chunks...", "#ffaa00"
            )
            ok = self._concat_chunks()
            if self._chunk_dir:
                shutil.rmtree(self._chunk_dir, ignore_errors=True)
            if ok:
                self.signals.status_changed.emit(
                    f"Saved {Path(self.last_output).name}", "#00ff88"
                )
            else:
                # Keep first chunk as fallback
                self.last_output = str(self._chunks[0])
                self.signals.status_changed.emit(
                    f"Partial: {Path(self._chunks[0]).name}", "#ffaa00"
                )

        self._chunks = []
        self._chunk_dir = None

    def _stop_gif(self, elapsed: float):
        if not self._gif_frames:
            self.signals.status_changed.emit("No frames", "#ff3366")
            return
        self.signals.status_changed.emit(
            f"Writing GIF ({len(self._gif_frames)}f)...", "#ffaa00"
        )
        try:
            pass

            duration = max(50, int(1000 / (self._fps / GIF_SAMPLE_RATE)))
            self._gif_frames[0].save(
                self.last_output,
                save_all=True,
                append_images=self._gif_frames[1:],
                optimize=False,
                duration=duration,
                loop=0,
            )
            log.info(
                f"GIF saved: {self.last_output} "
                f"({len(self._gif_frames)}f {elapsed:.1f}s)"
            )
            self.signals.status_changed.emit(
                f"Saved {Path(self.last_output).name}", "#00ff88"
            )
        except Exception as e:
            log.error(f"GIF write failed: {e}")
            self.signals.status_changed.emit(f"GIF failed: {e}", "#ff3366")
        finally:
            self._gif_frames = []

    def _stop_png_rolling(self, elapsed: float):
        if self._frame_dir and self._frame_dir.exists():
            count = len(list(self._frame_dir.glob("*.png")))
            log.info(f"PNG rolling: {count} frames kept in {self._frame_dir}")
            self.signals.status_changed.emit(
                f"{count}f → {self._frame_dir.name}/", "#ffaa00"
            )
        self._frame_dir = None

    # ── Chunk encoding helpers ─────────────────────────────────────────────────

    def _encode_chunk(self, frame_start: int, frame_count: int) -> Optional[Path]:
        """Encode frames [frame_start .. frame_start+frame_count) to a chunk MP4.
        Deletes the source PNGs on success."""
        if not self._frame_dir or not self._chunk_dir:
            return None
        chunk_path = self._chunk_dir / f"chunk_{self._chunk_n:04d}.mp4"
        self._chunk_n += 1
        try:
            # Build input pattern — frames are named frame_NNNNNN.png
            # We pass the starting number so ffmpeg picks up the right subset
            cmd = [
                "ffmpeg",
                "-y",
                "-framerate",
                str(self._fps),
                "-start_number",
                str(frame_start),
                "-i",
                str(self._frame_dir / "frame_%06d.png"),
                "-frames:v",
                str(frame_count),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(chunk_path),
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            if r.returncode != 0:
                log.error(
                    f"Chunk encode failed: "
                    f"{r.stderr.decode(errors="replace")[-300:]}"
                )
                return None

            # Delete the PNGs that were just encoded
            for i in range(frame_start, frame_start + frame_count):
                p = self._frame_dir / f"frame_{i:06d}.png"
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass

            log.info(
                f"Chunk {self._chunk_n-1} encoded: "
                f"{frame_count}f → {chunk_path.name}"
            )
            return chunk_path
        except Exception as e:
            log.error(f"Chunk encode error: {e}")
            return None

    def _concat_chunks(self) -> bool:
        """Concatenate all chunk MP4s into self.last_output using ffmpeg concat."""
        try:
            list_path = self._chunk_dir / "concat.txt"
            with open(list_path, "w") as f:
                for chunk in self._chunks:
                    f.write("file '" + str(chunk.resolve()) + "'\n")
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                self.last_output,
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=300)
            if r.returncode == 0:
                log.info(
                    f"Concatenated {len(self._chunks)} chunks → " f"{self.last_output}"
                )
                return True
            log.error(f"Concat failed: {r.stderr.decode(errors="replace")[-300:]}")
            return False
        except Exception as e:
            log.error(f"Concat error: {e}")
            return False

    # ── Frame capture ─────────────────────────────────────────────────────────

    def _grab_pixmap(self):
        try:
            px = self._target.grab()
            return px if not px.isNull() else None
        except Exception as e:
            log.debug(f"grab: {e}")
            return None

    def _capture_frame(self):
        if not self._running:
            return

        px = self._grab_pixmap()
        if px is None:
            return

        if self._engine == "cv2":
            self._write_cv2(px)

        elif self._engine == "ffmpeg":
            self._write_png_frame(px)
            # Rolling chunk: encode and purge every CHUNK_FRAMES frames
            frames_in_chunk = self._frame_n - self._chunk_frame_start + 1
            if frames_in_chunk >= self._chunk_frames:
                # Encode in a background thread so recording doesn't stutter
                start = self._chunk_frame_start
                count = frames_in_chunk
                self._chunk_frame_start = self._frame_n + 1
                t = threading.Thread(
                    target=self._encode_chunk_async,
                    args=(start, count),
                    name="screen-recorder",
                    daemon=True,
                )
                t.start()

        elif self._engine == "gif":
            # Sample every GIF_SAMPLE_RATE frames, cap total in memory
            if self._frame_n % GIF_SAMPLE_RATE == 0:
                try:
                    from PIL import Image

                    img = px.toImage().convertToFormat(QImage.Format.Format_RGB888)
                    pil = Image.frombytes(
                        "RGB",
                        (img.width(), img.height()),
                        bytes(img.bits()),
                        "raw",
                        "RGB",
                        img.bytesPerLine(),
                        1,
                    )
                    # Halve resolution to keep GIF manageable
                    pil = pil.resize(
                        (img.width() // 2, img.height() // 2), Image.LANCZOS
                    )
                    self._gif_frames.append(pil)
                    # Cap memory usage
                    if len(self._gif_frames) > MAX_GIF_FRAMES:
                        self._gif_frames.pop(0)
                except Exception as e:
                    log.debug(f"gif frame: {e}")

        else:  # rolling PNG
            self._write_png_frame(px)
            # Delete oldest frame to keep window bounded
            oldest = self._frame_n - self._chunk_frames
            if oldest >= 0:
                old_path = self._frame_dir / f"frame_{oldest:06d}.png"
                try:
                    old_path.unlink()
                except FileNotFoundError:
                    pass

        self._frame_n += 1
        elapsed = int(time.time() - self._start_ts)
        if self._frame_n % (max(1, self._fps) * 2) == 0:
            self.signals.status_changed.emit(
                f"● REC  {elapsed}s  ({self._frame_n}f)", "#ff3366"
            )

    def _write_cv2(self, pixmap):
        try:
            import cv2, numpy as np

            img = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
            arr = np.frombuffer(img.bits(), dtype=np.uint8).reshape(
                img.height(), img.width(), 3
            )
            self._writer.write(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        except Exception as e:
            log.debug(f"cv2 write: {e}")

    def _write_png_frame(self, pixmap):
        try:
            path = self._frame_dir / f"frame_{self._frame_n:06d}.png"
            pixmap.save(str(path), "PNG")
        except Exception as e:
            log.debug(f"png write: {e}")

    def _encode_chunk_async(self, frame_start: int, frame_count: int):
        """Background thread: encode chunk and append to self._chunks."""
        chunk = self._encode_chunk(frame_start, frame_count)
        if chunk:
            self._chunks.append(chunk)


# ── Toolbar widget ────────────────────────────────────────────────────────────

if _HAS_QT:

    class RecorderToolbarWidget(QWidget):
        """Compact recorder control bar for embedding in the simulator toolbar."""

        _BG = "#070710"
        _BORDER = "#1a1a3f"
        _GREY = "#667799"
        _RED = "#ff3366"
        _GREEN = "#00ff88"
        _CYAN = "#00FFEE"
        _GOLD = "#ffaa00"

        def __init__(
            self, target_widget=None, fps: int = 30, output_dir: str = "", parent=None
        ):
            super().__init__(parent)
            self._target_ref = target_widget
            self._fps = fps
            self._output_dir = output_dir
            self._recorder = None
            self._flash_state = False
            self._engine = _best_engine()
            self._setup_ui()
            self._setup_flash_timer()

        def set_target(self, widget):
            self._target_ref = widget
            if self._recorder:
                self._recorder._target = widget

        def _setup_ui(self):
            lay = QHBoxLayout(self)
            lay.setContentsMargins(2, 0, 2, 0)
            lay.setSpacing(3)

            ss = (
                "QPushButton{{background:{bg};color:{fg};"
                "border:1px solid {bd};border-radius:3px;"
                "font-size:8px;font-weight:bold;padding:1px 6px;"
                "font-family:Consolas;}}"
                "QPushButton:hover{{border-color:{hv};}}"
            )

            self._rec_btn = QPushButton("● REC")
            self._rec_btn.setFixedHeight(20)
            self._rec_btn.setStyleSheet(
                ss.format(bg=self._BG, fg=self._RED, bd=self._RED, hv=self._CYAN)
            )
            tips = {
                "cv2": "Record → MP4 (OpenCV — direct stream, no temp files)",
                "ffmpeg": "Record → MP4 (ffmpeg — 30s rolling chunks, auto-purge)",
                "gif": "Record → GIF (Pillow — sampled at 10fps, held in memory)",
                "png": "Record → PNG rolling window (last 30s kept on disk)",
            }
            self._rec_btn.setToolTip(tips.get(self._engine, "Record"))
            self._rec_btn.clicked.connect(self._toggle_recording)
            lay.addWidget(self._rec_btn)

            self._open_btn = QPushButton("📁")
            self._open_btn.setFixedSize(22, 20)
            self._open_btn.setStyleSheet(
                ss.format(bg=self._BG, fg=self._GREY, bd=self._BORDER, hv=self._CYAN)
            )
            self._open_btn.setToolTip("Open recordings folder")
            self._open_btn.clicked.connect(self._open_folder)
            lay.addWidget(self._open_btn)

            self._status_lbl = QLabel("")
            self._status_lbl.setStyleSheet(
                f"color:{self._GREY};font-size:7px;font-family:Consolas;"
                f"background:transparent;"
            )
            self._status_lbl.setFixedHeight(20)
            self._status_lbl.setMinimumWidth(55)
            lay.addWidget(self._status_lbl)

            col = {
                "cv2": self._GREEN,
                "ffmpeg": self._GOLD,
                "gif": self._CYAN,
                "png": self._GREY,
            }.get(self._engine, self._GREY)
            self._set_status(self._engine, col)

        def _setup_flash_timer(self):
            self._flash_timer = QTimer(self)
            self._flash_timer.setInterval(600)
            self._flash_timer.timeout.connect(self._flash_rec)

        def _flash_rec(self):
            self._flash_state = not self._flash_state
            bg = "#2a0008" if self._flash_state else self._BG
            self._rec_btn.setStyleSheet(
                f"QPushButton{{background:{bg};color:{self._RED};"
                f"border:1px solid {self._RED};border-radius:3px;"
                f"font-size:8px;font-weight:bold;padding:1px 6px;"
                f"font-family:Consolas;}}"
            )

        def _toggle_recording(self):
            if self._recorder and self._recorder.is_recording:
                self._stop_recording()
            else:
                self._start_recording()

        def _start_recording(self):
            target = self._target_ref or self.parent()
            if target is None:
                self._set_status("No target", self._RED)
                return
            self._recorder = ScreenRecorder(
                target, fps=self._fps, output_dir=self._output_dir
            )
            self._recorder.signals.status_changed.connect(self._set_status)
            if self._recorder.start():
                self._rec_btn.setText("■ STOP")
                self._rec_btn.setStyleSheet(
                    f"QPushButton{{background:#1a0008;color:{self._RED};"
                    f"border:1px solid {self._RED};border-radius:3px;"
                    f"font-size:8px;font-weight:bold;padding:1px 6px;"
                    f"font-family:Consolas;}}"
                    f"QPushButton:hover{{border-color:{self._CYAN};}}"
                )
                self._flash_timer.start()
            else:
                self._recorder = None

        def _stop_recording(self):
            self._flash_timer.stop()
            self._rec_btn.setText("● REC")
            self._rec_btn.setStyleSheet(
                f"QPushButton{{background:{self._BG};color:{self._RED};"
                f"border:1px solid {self._RED};border-radius:3px;"
                f"font-size:8px;font-weight:bold;padding:1px 6px;"
                f"font-family:Consolas;}}"
                f"QPushButton:hover{{border-color:{self._CYAN};}}"
            )
            if self._recorder:
                self._recorder.stop()
                self._recorder = None

        def _open_folder(self):
            folder = str(Path(self._output_dir).resolve())
            try:
                if sys.platform == "win32":
                    os.startfile(folder)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", folder])
                else:
                    subprocess.Popen(["xdg-open", folder])
            except Exception as _sf_exc:  # noqa: BLE001
                logger.warning(
                    "screen recorder cleanup failed — temp capture files may remain: %s",
                    _sf_exc,
                )

        def _set_status(self, msg: str, color: str = None):
            self._status_lbl.setText(msg)
            if color:
                self._status_lbl.setStyleSheet(
                    f"color:{color};font-size:7px;font-family:Consolas;"
                    f"background:transparent;"
                )
