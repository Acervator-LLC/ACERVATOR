"""``MiniDisplayManager.notify_price`` renders the change as the panel shows it."""

from src.core.mini_display import (
    DisplayAdapter,
    DisplayMessage,
    DisplayType,
    MiniDisplayManager,
)


class RecordingAdapter(DisplayAdapter):
    """Records every ``DisplayMessage`` that reaches ``DisplayAdapter.show``."""

    display_type = DisplayType.OLED_MONO

    def __init__(self) -> None:
        super().__init__({})
        self.connected = True
        self.shown: list[DisplayMessage] = []

    def connect(self) -> bool:
        return True

    def render(self, msg: DisplayMessage) -> bool:
        self.shown.append(msg)
        return True


def _manager_with_recorder() -> tuple[MiniDisplayManager, RecordingAdapter]:
    mgr = MiniDisplayManager()
    rec = RecordingAdapter()
    mgr._adapters = [rec]
    return mgr, rec


def test_notify_price_body_ends_with_a_single_percent_sign():
    mgr, rec = _manager_with_recorder()

    mgr.notify_price("BTC-USD", 65000.0, 1.25)
    mgr._dispatch(mgr._queue.pop(0))

    assert rec.shown, "the recorder saw no message; _dispatch never reached render"
    body = rec.shown[0].body
    assert body == "▲ +1.25%", (
        f"notify_price rendered {body!r}; every adapter draws the body verbatim, "
        "so a doubled percent sign reaches the panel"
    )


def test_notify_price_body_carries_the_down_arrow_on_a_negative_change():
    mgr, rec = _manager_with_recorder()

    mgr.notify_price("BTC-USD", 65000.0, -0.5)
    mgr._dispatch(mgr._queue.pop(0))

    body = rec.shown[0].body
    assert body == "▼ -0.50%", f"notify_price rendered {body!r}"
