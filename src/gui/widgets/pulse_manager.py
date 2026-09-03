"""Opacity pulse driver for the accent widgets on the main window."""

from __future__ import annotations

try:
    from PySide6.QtCore import QTimer

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # PULSE_CSS is carried here and applied by nothing that imports it.
    PULSE_CSS = """
    @keyframes pulse { 0% { opacity: 1.0; } 50% { opacity: 0.7; } 100% { opacity: 1.0; } }
    QPushButton[accent="true"], QTabBar::tab:selected, QProgressBar::chunk,
    QSlider::handle:horizontal, QLabel[heading="true"] {
        animation: pulse 2s ease-in-out infinite;
    }
    """

    # Qt runs no CSS keyframes, so PulseManager steps the opacity on a QTimer.
    class PulseManager:
        """Manages a subtle opacity pulse on accent widgets."""

        def __init__(self):
            self._widgets = []
            self._timer = QTimer()
            self._timer.timeout.connect(self._tick)
            self._phase = 0.0
            self._timer.start(50)

        def register(self, widget):
            self._widgets.append(widget)

        def _tick(self):
            import math

            self._phase += 0.05
            # Subtle pulse between 0.85 and 1.0 opacity
            opacity = 0.925 + 0.075 * math.sin(self._phase)
            for w in self._widgets:
                setter = getattr(w, "setWindowOpacity", None)
                if setter is None:
                    continue
                try:
                    setter(opacity)
                except RuntimeError:
                    pass
