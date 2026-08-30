"""pulse_manager_surface.py -- the opacity pulse as plain data.

Describes the driver that fades the accent widgets on the main window:
the stylesheet text it carries, the one timer it runs and that timer's
delay, the phase it advances on every fire, the opacity that phase
produces, the one method it calls on each registered widget, and the
one error it swallows so a dead widget cannot stop the rest.

The driver reads no clock. One fire is one call to ``tick``, and
``ticks_for`` turns an elapsed time the caller hands in into the number
of fires that time covers at the timer's delay.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``pulse_manager.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import math

METHOD = "pulse_manager.state"

PULSE_CSS = """
    @keyframes pulse { 0% { opacity: 1.0; } 50% { opacity: 0.7; } 100% { opacity: 1.0; } }
    QPushButton[accent="true"], QTabBar::tab:selected, QProgressBar::chunk,
    QSlider::handle:horizontal, QLabel[heading="true"] {
        animation: pulse 2s ease-in-out infinite;
    }
    """

STYLE_SHEET_APPLIED = False

TIMER_NAME = "opacity_pulse"
TIMER_INTERVAL_MS = 50

TIMERS = {TIMER_NAME: TIMER_INTERVAL_MS}
TIMER_DELAYS_MS = (TIMER_INTERVAL_MS,)
ACTIONS = {"opacity_pulse.timeout": "tick"}

SIGNALS: tuple = ()
BUS_TOPICS: tuple = ()
WIDGETS: tuple = ()
PAINTS = False

PHASE_START = 0.0
PHASE_STEP = 0.05

OPACITY_MID = 0.925
OPACITY_SWING = 0.075
OPACITY_FLOOR = 0.85
OPACITY_CEILING = 1.0

OPACITY_SETTER = "setWindowOpacity"
SWALLOWED_ERROR = "RuntimeError"

TIMER_STARTED = "timer_started"
TIMER_STOPPED = "timer_stopped"
TARGET_REGISTERED = "target_registered"
PHASE_ADVANCED = "phase_advanced"
OPACITY_COMPUTED = "opacity_computed"
TARGET_HAS_SETTER = "target_has_setter"
TARGET_SET = "target_set"
TARGET_SKIPPED = "target_skipped"
TARGET_FAILED = "target_failed"

CALL_NAMES = (
    TIMER_STARTED,
    TIMER_STOPPED,
    TARGET_REGISTERED,
    PHASE_ADVANCED,
    OPACITY_COMPUTED,
    TARGET_HAS_SETTER,
    TARGET_SET,
    TARGET_SKIPPED,
    TARGET_FAILED,
)


def opacity_at(phase: float) -> float:
    """The opacity one phase produces, centred on the midpoint."""
    return OPACITY_MID + OPACITY_SWING * math.sin(phase)


class OpacityTarget:
    """One registered widget, keeping every opacity its setter received."""

    def __init__(self, name: object = "") -> None:
        self.name = name
        self.opacities: list = []

    def setWindowOpacity(self, opacity: float) -> None:
        """Take one opacity the way a window takes one."""
        self.opacities.append(opacity)


class PulseModel:
    """One pulse driver, with no Qt object behind it.

    Holds the timer state, the phase, the widgets registered with it and
    what each fire did to each of them.
    """

    def __init__(self) -> None:
        self.targets: list = []
        self.phase: float = PHASE_START
        self.phase_start: float = PHASE_START
        self.interval_ms: int = TIMER_INTERVAL_MS
        self.timer_active = False
        self.starts = 0
        self.stops = 0
        self.applied: list = []
        self.skipped: list = []
        self.failed: list = []
        self.calls: list = []
        self.start()

    def start(self) -> None:
        """Run the timer. A timer already running stays running."""
        self.timer_active = True
        self.starts += 1
        self.calls.append(TIMER_STARTED)

    def stop(self) -> None:
        """Stop the timer. A timer already stopped stays stopped."""
        self.timer_active = False
        self.stops += 1
        self.calls.append(TIMER_STOPPED)

    def register(self, widget) -> None:
        """Add one widget to the set every fire sets the opacity on."""
        self.targets.append(widget)
        self.calls.append(TARGET_REGISTERED)

    def ticks_for(self, elapsed_ms: float) -> int:
        """The number of fires `elapsed_ms` covers at this timer's delay."""
        return int(elapsed_ms // self.interval_ms)

    def advance(self, elapsed_ms: float) -> int:
        """Fire once for each whole delay in `elapsed_ms`, and say how many."""
        fires = self.ticks_for(elapsed_ms)
        for _ in range(fires):
            self.tick()
        return fires

    def tick(self) -> None:
        """One fire: move the phase on, then set every widget's opacity.

        A widget with no opacity setter is passed over. A widget whose
        setter reports its underlying object is gone is passed over and
        the rest still receive the value. Every other refusal ends the
        fire where it is raised.
        """
        self.phase += PHASE_STEP
        self.calls.append(PHASE_ADVANCED)
        opacity = opacity_at(self.phase)
        self.calls.append(OPACITY_COMPUTED)
        for index, widget in enumerate(self.targets):
            setter = getattr(widget, OPACITY_SETTER, None)
            if setter is None:
                self.skipped.append(index)
                self.calls.append(TARGET_SKIPPED)
                continue
            self.calls.append(TARGET_HAS_SETTER)
            try:
                setter(opacity)
            except RuntimeError:
                self.failed.append(index)
                self.calls.append(TARGET_FAILED)
                continue
            self.applied.append(opacity)
            self.calls.append(TARGET_SET)


def seen_by_targets(model: PulseModel) -> list:
    """What each registered widget received, in registration order."""
    return [
        {
            "target": getattr(widget, "name", None),
            "opacities": list(getattr(widget, "opacities", [])),
        }
        for widget in model.targets
    ]


def build_view_model(model: PulseModel) -> dict:
    """Return the whole pulse state as one serialisable dict."""
    return {
        "css": PULSE_CSS,
        "style_sheet_applied": STYLE_SHEET_APPLIED,
        "timer": {
            "name": TIMER_NAME,
            "interval_ms": model.interval_ms,
            "active": model.timer_active,
            "starts": model.starts,
            "stops": model.stops,
        },
        "phase_start": model.phase_start,
        "phase": model.phase,
        "phase_step": PHASE_STEP,
        "opacity_mid": OPACITY_MID,
        "opacity_swing": OPACITY_SWING,
        "opacity_floor": OPACITY_FLOOR,
        "opacity_ceiling": OPACITY_CEILING,
        "setter": OPACITY_SETTER,
        "swallows": SWALLOWED_ERROR,
        "registered": len(model.targets),
        "applied": list(model.applied),
        "skipped": list(model.skipped),
        "failed": list(model.failed),
        "seen": seen_by_targets(model),
        "paints": PAINTS,
        "widgets": list(WIDGETS),
        "signals": list(SIGNALS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": list(model.calls),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``pulse_manager.state``.

    Registers the widgets the request names, runs the fires it asks for
    -- a count, or an elapsed time turned into a count -- and returns the
    state those fires left. ``stop`` stops the timer before they run.
    """
    asked = params or {}
    model = PulseModel()
    for name in asked.get("targets", []):
        model.register(OpacityTarget(name))
    if asked.get("stop"):
        model.stop()
    if "elapsed_ms" in asked:
        model.advance(asked["elapsed_ms"])
    else:
        for _ in range(int(asked.get("ticks", 0))):
            model.tick()
    return build_view_model(model)
