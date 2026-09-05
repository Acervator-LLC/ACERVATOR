"""Mini display detection and message routing.

``detect_displays`` connects one adapter per ``I2C_ADDRESSES`` match on the bus
and one per ``extra_config`` entry, choosing the class from
``ADAPTER_CLASSES``. ``MiniDisplayManager.send`` queues a ``DisplayMessage``
and ``_loop`` hands it to every adapter's ``show``. ``INCOMPATIBLE`` holds the
``MessageType`` and ``DisplayType`` pairs ``show`` drops.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("acervator.mini_display")


class DisplayType(Enum):
    OLED_MONO = "oled_mono"  # SSD1306 driven by OledMonoAdapter
    OLED_COLOR = "oled_color"  # SSD1351 driven by OledColorAdapter
    TFT_COLOR = "tft_color"  # ST7789 driven by TftColorAdapter
    CHAR_LCD = "char_lcd"  # HD44780 driven by CharLcdAdapter
    E_PAPER = "e_paper"  # WaveShare e-Paper driven by EPaperAdapter


class MessageType(Enum):
    TRADE_ALERT = "trade_alert"
    BOT_STATE = "bot_state"
    STATUS_LINE = "status_line"
    PRICE_TICKER = "price_ticker"
    NOTIFICATION = "notification"
    ERROR = "error"
    STARTUP_SPLASH = "startup_splash"
    CHART_MINI = "chart_mini"  # Pixel-drawn price chart
    RICH_TEXT = "rich_text"  # HTML markup, never stripped by any adapter
    ANIMATION = "animation"


# Every (MessageType, DisplayType) show() refuses, mapped to its reason.
INCOMPATIBLE: dict[tuple[MessageType, DisplayType], str] = {
    (
        MessageType.CHART_MINI,
        DisplayType.CHAR_LCD,
    ): "Character cell matrix cannot render pixel graphics",
    (
        MessageType.RICH_TEXT,
        DisplayType.CHAR_LCD,
    ): "Character LCD limited to ASCII; HTML markup not renderable",
    (
        MessageType.ANIMATION,
        DisplayType.CHAR_LCD,
    ): "No frame buffer; full repaint per write makes animation impractical",
    (
        MessageType.PRICE_TICKER,
        DisplayType.E_PAPER,
    ): "2–30s e-ink refresh cycle makes live prices meaningless; "
    "accelerated panel wear",
    (
        MessageType.ANIMATION,
        DisplayType.E_PAPER,
    ): "Physical refresh cycle (2–30s) is incompatible with animation",
    (
        MessageType.CHART_MINI,
        DisplayType.E_PAPER,
    ): "Frequent chart redraws cause accelerated e-ink panel wear",
    (
        MessageType.RICH_TEXT,
        DisplayType.OLED_MONO,
    ): "Monochrome display cannot render colour/font formatting from HTML",
    (
        MessageType.ANIMATION,
        DisplayType.OLED_MONO,
    ): "Low-res monochrome buffer impractical for animation sequences",
}


def is_compatible(msg_type: MessageType, disp_type: DisplayType) -> tuple[bool, str]:
    """Return ``(True, "")`` unless ``INCOMPATIBLE`` holds the pair.

    A held pair returns ``(False, reason)``.
    """
    reason = INCOMPATIBLE.get((msg_type, disp_type), "")
    return (reason == "", reason)


@dataclass
class DisplayMessage:
    """One message ``MiniDisplayManager.send`` queues for the adapters."""

    msg_type: MessageType
    title: str = ""
    body: str = ""
    value: str = ""
    symbol: str = ""
    timestamp: float = field(default_factory=time.time)
    priority: int = 5  # Lower sorts first in MiniDisplayManager.send
    duration_s: float = 0.0  # Seconds _loop sleeps after dispatch; 0 sleeps none

    def plain_text(self, max_cols: int = 20) -> list[str]:
        """Split ``title``, ``value`` and ``body`` into ``max_cols``-wide lines.

        Three empty fields return ``[""]``.
        """
        lines = []
        if self.title:
            lines.append(self.title[:max_cols])
        if self.value:
            lines.append(self.value[:max_cols])
        if self.body:
            words = self.body.split()
            line = ""
            for w in words:
                if len(line) + len(w) + 1 <= max_cols:
                    line = (line + " " + w).strip()
                else:
                    if line:
                        lines.append(line)
                    line = w[:max_cols]
            if line:
                lines.append(line)
        return lines or [""]


class DisplayAdapter:
    """Base for every adapter in ``ADAPTER_CLASSES``.

    ``connect`` and ``render`` raise ``NotImplementedError`` until a subclass
    defines them; ``show`` wraps ``render`` in ``_lock``.
    """

    display_type: DisplayType = NotImplemented

    def __init__(self, config: dict):
        self.config = config
        self.connected = False
        self._lock = threading.Lock()

    def connect(self) -> bool:
        """Open the panel and set ``connected``, returning True on success."""
        raise NotImplementedError

    def render(self, msg: DisplayMessage) -> bool:
        """Draw *msg* on the panel, returning True on success."""
        raise NotImplementedError

    def clear(self):
        """Blank the panel; the base does nothing."""

    def disconnect(self):
        """Set ``connected`` false; a subclass releases the panel first."""
        self.connected = False

    def is_compatible(self, msg_type: MessageType) -> tuple[bool, str]:
        return is_compatible(msg_type, self.display_type)

    def show(self, msg: DisplayMessage) -> bool:
        """Call ``render`` under ``_lock`` once ``is_compatible`` passes.

        An incompatible *msg* and any exception from ``render`` both log and
        return False.
        """
        ok, reason = self.is_compatible(msg.msg_type)
        if not ok:
            logger.debug(
                "Display %s: skipping %s — %s",
                self.display_type.value,
                msg.msg_type.value,
                reason,
            )
            return False
        with self._lock:
            try:
                return self.render(msg)
            except Exception as e:
                logger.warning(
                    "Display %s render error: %s", self.display_type.value, e
                )
                return False


class OledMonoAdapter(DisplayAdapter):
    """SSD1306 monochrome OLED.

    ``connect`` reads ``i2c_address``, ``i2c_bus``, ``width`` and ``height``
    from ``config``.
    """

    display_type = DisplayType.OLED_MONO

    def connect(self) -> bool:
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306

            addr = int(self.config.get("i2c_address", "0x3C"), 16)
            bus = int(self.config.get("i2c_bus", 1))
            width = int(self.config.get("width", 128))
            height = int(self.config.get("height", 64))
            serial = i2c(port=bus, address=addr)
            self._dev = ssd1306(serial, width=width, height=height)
            self.connected = True
            logger.info("SSD1306 OLED connected at I2C 0x%02X", addr)
            return True
        except Exception as e:
            logger.warning("SSD1306 connect failed: %s", e)
            return False

    def render(self, msg: DisplayMessage) -> bool:
        from PIL import Image, ImageDraw, ImageFont

        w, h = self._dev.width, self._dev.height
        img = Image.new("1", (w, h), 0)
        draw = ImageDraw.Draw(img)

        try:
            font_sm = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9
            )
            font_lg = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14
            )
        except (IOError, OSError):
            font_sm = font_lg = ImageFont.load_default()

        y = 0
        if msg.title:
            draw.text((0, y), msg.title[:21], fill=1, font=font_lg)
            y += 16
        if msg.value:
            draw.text((0, y), msg.value[:21], fill=1, font=font_lg)
            y += 16
        if msg.body and y < h - 10:
            draw.text((0, y), msg.body[:42], fill=1, font=font_sm)

        self._dev.display(img)
        return True

    def clear(self):
        if self.connected:
            self._dev.clear()

    def disconnect(self):
        if self.connected:
            try:
                self._dev.cleanup()
            except Exception:
                pass
        super().disconnect()


class OledColorAdapter(DisplayAdapter):
    """SSD1351 colour OLED.

    ``connect`` opens SPI device 0 port 0 and reads nothing from ``config``.
    """

    display_type = DisplayType.OLED_COLOR

    def connect(self) -> bool:
        try:
            from luma.core.interface.serial import spi
            from luma.oled.device import ssd1351

            self._dev = ssd1351(spi(device=0, port=0))
            self.connected = True
            logger.info("SSD1351 color OLED connected via SPI")
            return True
        except Exception as e:
            logger.warning("SSD1351 connect failed: %s", e)
            return False

    def render(self, msg: DisplayMessage) -> bool:
        from PIL import Image, ImageDraw, ImageFont

        w, h = self._dev.width, self._dev.height
        img = Image.new("RGB", (w, h), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font_sm = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10
            )
            font_lg = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14
            )
        except (IOError, OSError):
            font_sm = font_lg = ImageFont.load_default()

        RED = (204, 0, 0)
        CYAN = (0, 204, 170)
        WHITE = (255, 255, 255)
        GREY = (150, 150, 150)

        y = 4
        if msg.title:
            draw.text((4, y), msg.title[:20], fill=RED, font=font_lg)
            y += 18
        if msg.value:
            col = CYAN if msg.msg_type != MessageType.ERROR else RED
            draw.text((4, y), msg.value[:20], fill=col, font=font_lg)
            y += 18
        if msg.body and y < h - 12:
            draw.text((4, y), msg.body[:40], fill=WHITE, font=font_sm)
        if msg.symbol:
            draw.text((4, h - 12), msg.symbol, fill=GREY, font=font_sm)

        self._dev.display(img)
        return True

    def disconnect(self):
        if self.connected:
            try:
                self._dev.cleanup()
            except Exception:
                pass
        super().disconnect()


class TftColorAdapter(DisplayAdapter):
    """ST7789 SPI TFT panel.

    ``connect`` reads ``width`` and ``height`` from ``config`` and fixes the
    remaining pins.
    """

    display_type = DisplayType.TFT_COLOR

    def connect(self) -> bool:
        try:
            import ST7789 as st

            w = int(self.config.get("width", 240))
            h = int(self.config.get("height", 240))
            self._dev = st.ST7789(
                rotation=0,
                port=0,
                cs=1,
                dc=9,
                backlight=19,
                width=w,
                height=h,
                offset_left=0,
                offset_top=0,
            )
            self.connected = True
            logger.info("ST7789 TFT connected (%dx%d)", w, h)
            return True
        except Exception as e:
            logger.warning("ST7789 connect failed: %s", e)
            return False

    def render(self, msg: DisplayMessage) -> bool:
        from PIL import Image, ImageDraw, ImageFont

        w = getattr(self._dev, "width", 240)
        h = getattr(self._dev, "height", 240)
        img = Image.new("RGB", (w, h), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font_sm = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14
            )
            font_lg = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20
            )
        except (IOError, OSError):
            font_sm = font_lg = ImageFont.load_default()

        RED = (204, 0, 0)
        CYAN = (0, 204, 170)
        WHITE = (240, 240, 240)
        GOLD = (255, 184, 0)

        y = 10
        if msg.title:
            draw.text((10, y), msg.title[:24], fill=RED, font=font_lg)
            y += 28
        if msg.value:
            col = CYAN if msg.msg_type == MessageType.PRICE_TICKER else GOLD
            if msg.msg_type == MessageType.ERROR:
                col = RED
            draw.text((10, y), msg.value[:24], fill=col, font=font_lg)
            y += 28
        if msg.body and y < h - 20:
            words = msg.body.split()
            line = ""
            for w_word in words:
                if len(line) + len(w_word) + 1 <= 28:
                    line = (line + " " + w_word).strip()
                else:
                    if line:
                        draw.text((10, y), line, fill=WHITE, font=font_sm)
                        y += 20
                    line = w_word
                    if y >= h - 20:
                        break
            if line and y < h - 20:
                draw.text((10, y), line, fill=WHITE, font=font_sm)

        self._dev.display(img)
        return True

    def disconnect(self):
        if self.connected:
            try:
                self._dev.set_backlight(0)
            except Exception:
                pass
        super().disconnect()


class CharLcdAdapter(DisplayAdapter):
    """HD44780 character LCD behind a PCF8574 I2C backpack.

    ``connect`` reads ``i2c_address``, ``cols`` and ``rows`` from ``config``.
    """

    display_type = DisplayType.CHAR_LCD

    def connect(self) -> bool:
        try:
            from RPLCD.i2c import CharLCD

            addr = int(self.config.get("i2c_address", "0x27"), 16)
            cols = int(self.config.get("cols", 16))
            rows = int(self.config.get("rows", 2))
            self._lcd = CharLCD(
                i2c_expander="PCF8574",
                address=addr,
                port=1,
                cols=cols,
                rows=rows,
                charmap="A02",
            )
            self._cols = cols
            self._rows = rows
            self.connected = True
            logger.info("HD44780 LCD connected at I2C 0x%02X (%dx%d)", addr, cols, rows)
            return True
        except Exception as e:
            logger.warning("HD44780 connect failed: %s", e)
            return False

    def render(self, msg: DisplayMessage) -> bool:
        lines = msg.plain_text(max_cols=self._cols)
        self._lcd.clear()
        for i, line in enumerate(lines[: self._rows]):
            self._lcd.cursor_pos = (i, 0)
            # HD44780 has no Unicode; every non-ASCII character becomes '?'.
            safe = line.encode("ascii", errors="replace").decode("ascii")
            self._lcd.write_string(safe[: self._cols])
        return True

    def clear(self):
        if self.connected:
            try:
                self._lcd.clear()
            except Exception:
                pass

    def disconnect(self):
        if self.connected:
            try:
                self._lcd.clear()
                self._lcd.close(clear=True)
            except Exception:
                pass
        super().disconnect()


class EPaperAdapter(DisplayAdapter):
    """WaveShare e-Paper panel over SPI.

    ``connect`` imports the ``waveshare_epd`` submodule named by ``config``'s
    ``model``.
    """

    display_type = DisplayType.E_PAPER

    _last_rendered: str = ""

    def connect(self) -> bool:
        try:
            model = self.config.get("model", "epd2in13_V3")
            import importlib

            epd_mod = importlib.import_module(f"waveshare_epd.{model}")
            self._epd = epd_mod.EPD()
            self._epd.init()
            self._epd.Clear()
            self.connected = True
            logger.info("WaveShare e-Paper (%s) connected", model)
            return True
        except Exception as e:
            logger.warning("e-Paper connect failed: %s", e)
            return False

    def render(self, msg: DisplayMessage) -> bool:
        # A repeat of the previous title, value and body redraws nothing.
        key = f"{msg.title}|{msg.value}|{msg.body}"
        if key == self._last_rendered:
            return True
        self._last_rendered = key

        from PIL import Image, ImageDraw, ImageFont

        w = getattr(self._epd, "width", 122)
        h = getattr(self._epd, "height", 250)
        img = Image.new("1", (w, h), 255)  # 255 is white in Pillow mode "1"
        draw = ImageDraw.Draw(img)

        try:
            font_sm = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10
            )
            font_lg = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14
            )
        except (IOError, OSError):
            font_sm = font_lg = ImageFont.load_default()

        y = 4
        if msg.title:
            draw.text((4, y), msg.title[:20], fill=0, font=font_lg)
            draw.line([(0, y + 17), (w, y + 17)], fill=0, width=1)
            y += 22
        if msg.value:
            draw.text((4, y), msg.value[:20], fill=0, font=font_lg)
            y += 18
        if msg.body:
            draw.text((4, y), msg.body[:42], fill=0, font=font_sm)
        ts = time.strftime("%H:%M")
        draw.text((w - 28, h - 14), ts, fill=0, font=font_sm)

        self._epd.display(self._epd.getbuffer(img))
        return True

    def disconnect(self):
        if self.connected:
            try:
                self._epd.sleep()
            except Exception:
                pass
        super().disconnect()


I2C_ADDRESSES = {
    0x3C: (DisplayType.OLED_MONO, {"i2c_address": "0x3C"}),
    0x3D: (DisplayType.OLED_MONO, {"i2c_address": "0x3D"}),
    0x27: (DisplayType.CHAR_LCD, {"i2c_address": "0x27", "cols": "16", "rows": "2"}),
    0x3F: (DisplayType.CHAR_LCD, {"i2c_address": "0x3F", "cols": "20", "rows": "4"}),
}

ADAPTER_CLASSES = {
    DisplayType.OLED_MONO: OledMonoAdapter,
    DisplayType.OLED_COLOR: OledColorAdapter,
    DisplayType.TFT_COLOR: TftColorAdapter,
    DisplayType.CHAR_LCD: CharLcdAdapter,
    DisplayType.E_PAPER: EPaperAdapter,
}


def scan_i2c(bus: int = 1) -> list[int]:
    """Return every address on *bus* that answers ``smbus2.SMBus.read_byte``.

    An absent ``smbus2`` also returns an empty list.
    """
    try:
        import smbus2

        b = smbus2.SMBus(bus)
        found = []
        for addr in range(0x03, 0x78):
            try:
                b.read_byte(addr)
                found.append(addr)
            except OSError:
                pass
        b.close()
        return found
    except Exception:
        return []


def detect_displays(extra_config: Optional[list[dict]] = None) -> list[DisplayAdapter]:
    """Return one connected adapter per ``I2C_ADDRESSES`` hit from ``scan_i2c``,
    then one per ``extra_config`` entry whose ``type`` names a ``DisplayType``.

    Each ``extra_config`` entry is adapter config, such as
    ``{"type": "e_paper", "model": "epd2in13_V3"}``, and one ``DisplayType``
    appears at most once.
    """
    adapters: list[DisplayAdapter] = []
    seen_types: set[DisplayType] = set()

    logger.info("Scanning I2C bus for mini displays...")
    addresses = scan_i2c()
    for addr in addresses:
        if addr in I2C_ADDRESSES:
            dtype, cfg = I2C_ADDRESSES[addr]
            if dtype in seen_types:
                continue
            cls = ADAPTER_CLASSES[dtype]
            adapter = cls(cfg)
            if adapter.connect():
                adapters.append(adapter)
                seen_types.add(dtype)
                logger.info("Auto-detected: %s at I2C 0x%02X", dtype.value, addr)

    for cfg in extra_config or []:
        try:
            dtype = DisplayType(cfg.get("type", ""))
        except ValueError:
            logger.warning("Unknown display type in config: %r", cfg.get("type"))
            continue
        if dtype in seen_types:
            continue
        cls = ADAPTER_CLASSES.get(dtype)
        if cls:
            adapter = cls(cfg)
            if adapter.connect():
                adapters.append(adapter)
                seen_types.add(dtype)

    logger.info(
        "Mini display detection complete — %d display(s) active: %s",
        len(adapters),
        [a.display_type.value for a in adapters],
    )
    return adapters


class MiniDisplayManager:
    """Routes every ``DisplayMessage`` to the adapters ``detect_displays`` found.

    ``send`` appends to ``_queue`` under ``_lock`` without blocking, and
    ``_loop`` pops one message per pass on a daemon thread for ``_dispatch``.
    """

    def __init__(self, extra_config: Optional[list[dict]] = None):
        self._adapters: list[DisplayAdapter] = []
        self._queue: list[DisplayMessage] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._extra_cfg = extra_config or []

    def start(self):
        """Fill ``_adapters`` from ``detect_displays`` and run ``_loop``.

        An empty ``_adapters`` leaves ``_running`` false and starts no thread.
        """
        self._adapters = detect_displays(self._extra_cfg)
        if not self._adapters:
            logger.info("No mini displays detected — display manager idle")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="mini-display"
        )
        self._thread.start()

    def stop(self):
        """Stop ``_loop``, then clear and disconnect every adapter.

        ``_adapters`` ends empty and ``_queue`` keeps whatever it held.
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        for adapter in self._adapters:
            try:
                adapter.clear()
                adapter.disconnect()
            except Exception:
                pass
        self._adapters = []

    def send(self, msg: DisplayMessage):
        """Append *msg* to ``_queue``, ordered by ascending ``priority``.

        ``_queue`` keeps twenty entries and drops everything past them.
        """
        if not self._adapters:
            return
        with self._lock:
            self._queue.append(msg)
            self._queue.sort(key=lambda m: m.priority)
            if len(self._queue) > 20:
                self._queue = self._queue[:20]

    def send_simple(
        self,
        msg_type: MessageType,
        title: str = "",
        body: str = "",
        value: str = "",
        symbol: str = "",
        priority: int = 5,
        duration_s: float = 0.0,
    ):
        """Build a ``DisplayMessage`` from the arguments and pass it to ``send``."""
        self.send(
            DisplayMessage(
                msg_type=msg_type,
                title=title,
                body=body,
                value=value,
                symbol=symbol,
                priority=priority,
                duration_s=duration_s,
            )
        )

    def notify_trade(
        self, side: str, symbol: str, qty: float, price: float, fee: float
    ):
        self.send_simple(
            MessageType.TRADE_ALERT,
            title=f"{'SCRUM' if side.upper()=='SELL' else 'FOLD'}  {symbol}",
            value=f"${price:,.4f}",
            body=f"qty {qty:.6f}  fee ${fee:.4f}",
            priority=1,
        )

    def notify_bot_state(self, state: str, symbol: str = ""):
        self.send_simple(
            MessageType.BOT_STATE,
            title="BOT STATE",
            value=state.upper(),
            body=symbol,
            priority=2,
        )

    def notify_price(self, symbol: str, price: float, change_pct: float):
        arrow = "\u25b2" if change_pct >= 0 else "\u25bc"
        self.send_simple(
            MessageType.PRICE_TICKER,
            title=symbol,
            value=f"${price:,.4f}",
            body=f"{arrow} {change_pct:+.2f}%",
            priority=6,
            duration_s=5.0,
        )

    def notify_error(self, title: str, detail: str):
        self.send_simple(
            MessageType.ERROR,
            title=f"ERROR: {title[:14]}",
            body=detail[:42],
            priority=1,
        )

    def notify_startup(self, version: str):
        self.send_simple(
            MessageType.STARTUP_SPLASH,
            title="ACERVATOR",
            value=f"v{version}",
            body="Starting up...",
            priority=2,
        )

    def notify_status(self, line: str):
        self.send_simple(
            MessageType.STATUS_LINE,
            title="",
            body=line[:40],
            priority=5,
        )

    def _loop(self):
        while self._running:
            msg = None
            with self._lock:
                if self._queue:
                    msg = self._queue.pop(0)
            if msg:
                self._dispatch(msg)
                if msg.duration_s > 0:
                    time.sleep(msg.duration_s)
            else:
                time.sleep(0.05)

    def _dispatch(self, msg: DisplayMessage):
        for adapter in self._adapters:
            adapter.show(msg)

    def status(self) -> dict:
        return {
            "displays": [
                {
                    "type": a.display_type.value,
                    "connected": a.connected,
                }
                for a in self._adapters
            ],
            "queue_depth": len(self._queue),
            "active": self._running,
        }

    def compatibility_report(self) -> str:
        """Return one line per ``MessageType`` for each adapter in ``_adapters``.

        A line for a pair ``INCOMPATIBLE`` holds carries that reason.
        """
        if not self._adapters:
            return "No mini displays detected."
        lines = ["Mini Display Compatibility Report", "=" * 38]
        for adapter in self._adapters:
            lines.append(f"\n  {adapter.display_type.value.upper()}")
            for mt in MessageType:
                ok, reason = adapter.is_compatible(mt)
                sym = "✓" if ok else "✗"
                if ok:
                    lines.append(f"    {sym}  {mt.value}")
                else:
                    lines.append(f"    {sym}  {mt.value}  [{reason[:50]}]")
        return "\n".join(lines)


_manager: Optional[MiniDisplayManager] = None


def get_manager() -> MiniDisplayManager:
    """Return ``_manager``, building an unstarted ``MiniDisplayManager`` if None."""
    global _manager
    if _manager is None:
        _manager = MiniDisplayManager()
    return _manager


def init_displays(extra_config: Optional[list[dict]] = None) -> MiniDisplayManager:
    """Replace ``_manager`` with a ``MiniDisplayManager`` and call its ``start``."""
    global _manager
    _manager = MiniDisplayManager(extra_config=extra_config)
    _manager.start()
    return _manager
