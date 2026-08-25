"""
mini_display.py — AcervatorOS Mini Display Manager
====================================================
Detects connected mini displays on I2C / SPI, routes platform messages
to each detected display, and excludes messages that are fundamentally
incompatible with the display's hardware capabilities.

SUPPORTED DISPLAY TYPES
-----------------------
  OLED_MONO    SSD1306 128×64 or 128×32 — I2C addr 0x3C / 0x3D
               Fast refresh. Pixel graphics. Monochrome.
               Library: luma.oled

  OLED_COLOR   SSD1351 128×128 — I2C or SPI (configured)
               Fast refresh. Pixel graphics. Full color.
               Library: luma.oled

  TFT_COLOR    ST7789 / ILI9341 — SPI (configured)
               Fast refresh. Pixel graphics. Full color.
               Library: luma.lcd or st7789-python

  CHAR_LCD     HD44780 16×2 or 20×4 — I2C via PCF8574 (0x27 / 0x3F)
               Character-only. No pixel graphics. No color.
               Library: RPLCD

  E_PAPER      WaveShare e-Paper — SPI (configured)
               2–30 second refresh. Pixel graphics. Mono / greyscale.
               No animation. No live price ticker.
               Library: waveshare_epd

MESSAGE COMPATIBILITY
---------------------
  MessageType           OLED_MONO  OLED_COLOR  TFT_COLOR  CHAR_LCD  E_PAPER
  TRADE_ALERT               ✓          ✓           ✓          ✓        ✓
  BOT_STATE                 ✓          ✓           ✓          ✓        ✓
  STATUS_LINE               ✓          ✓           ✓          ✓        ✓
  PRICE_TICKER              ✓          ✓           ✓          ✓        ✗  (too slow)
  NOTIFICATION              ✓          ✓           ✓          ✓        ✓
  ERROR                     ✓          ✓           ✓          ✓        ✓
  STARTUP_SPLASH            ✓          ✓           ✓          ✓        ✓
  CHART_MINI                ✓          ✓           ✓          ✗        ✗
  RICH_TEXT                 ✗          ✓           ✓          ✗        ✓  (stripped)
  ANIMATION                 ✗          ✓           ✓          ✗        ✗

INCOMPATIBILITY RATIONALE
--------------------------
  CHAR_LCD  + CHART_MINI    Character cell matrix cannot render pixel graphics.
  CHAR_LCD  + RICH_TEXT     Character set limited to ASCII + custom glyphs.
  CHAR_LCD  + ANIMATION     No frame buffer; each write repaints the full display.
  E_PAPER   + PRICE_TICKER  2–30s refresh cycle makes live prices meaningless and
                            causes accelerated e-ink wear.
  E_PAPER   + ANIMATION     Physical refresh cycle incompatible with animation.
  OLED_MONO + RICH_TEXT     Monochrome renders HTML formatting invisible.
  OLED_MONO + ANIMATION     Low-res mono buffer makes animation impractical.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("acervator.mini_display")

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DisplayType(Enum):
    OLED_MONO = "oled_mono"  # SSD1306 monochrome OLED
    OLED_COLOR = "oled_color"  # SSD1351 color OLED
    TFT_COLOR = "tft_color"  # ST7789 / ILI9341 TFT LCD
    CHAR_LCD = "char_lcd"  # HD44780 character LCD
    E_PAPER = "e_paper"  # WaveShare e-Paper / e-ink


class MessageType(Enum):
    TRADE_ALERT = "trade_alert"  # Order placed, filled, cancelled
    BOT_STATE = "bot_state"  # TRADING / PAUSED / STOPPED / ERROR
    STATUS_LINE = "status_line"  # Single-line status string
    PRICE_TICKER = "price_ticker"  # Live price update (frequent)
    NOTIFICATION = "notification"  # General notification text
    ERROR = "error"  # System or exchange error
    STARTUP_SPLASH = "startup_splash"  # Boot / startup message
    CHART_MINI = "chart_mini"  # Compact price chart (pixel-based)
    RICH_TEXT = "rich_text"  # HTML / formatted text
    ANIMATION = "animation"  # Frame-based animation


# ---------------------------------------------------------------------------
# Compatibility matrix
# INCOMPATIBLE[(MessageType, DisplayType)] = reason string
# ---------------------------------------------------------------------------

INCOMPATIBLE: dict[tuple[MessageType, DisplayType], str] = {
    # CHAR_LCD limitations
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
    # E_PAPER limitations
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
    # OLED_MONO limitations
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
    """Return (True, '') if compatible, (False, reason) if not."""
    reason = INCOMPATIBLE.get((msg_type, disp_type), "")
    return (reason == "", reason)


# ---------------------------------------------------------------------------
# Message dataclass
# ---------------------------------------------------------------------------


@dataclass
class DisplayMessage:
    """A platform message to be routed to mini displays."""

    msg_type: MessageType
    title: str = ""
    body: str = ""
    value: str = ""  # e.g. price, P&L, state string
    symbol: str = ""
    timestamp: float = field(default_factory=time.time)
    priority: int = 5  # 1 (highest) – 10 (lowest)
    duration_s: float = 0.0  # 0 = persistent until next message

    def plain_text(self, max_cols: int = 20) -> list[str]:
        """
        Render message as a list of plain-text lines trimmed to max_cols.
        Used by CHAR_LCD adapter.
        """
        lines = []
        if self.title:
            lines.append(self.title[:max_cols])
        if self.value:
            lines.append(self.value[:max_cols])
        if self.body:
            # Wrap body into max_cols segments
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


# ---------------------------------------------------------------------------
# Abstract adapter base
# ---------------------------------------------------------------------------


class DisplayAdapter:
    """
    Base class for all display adapters.
    Subclasses implement connect(), render(), and disconnect().
    """

    display_type: DisplayType = NotImplemented

    def __init__(self, config: dict):
        self.config = config
        self.connected = False
        self._lock = threading.Lock()

    def connect(self) -> bool:
        """Open connection to the display hardware. Return True on success."""
        raise NotImplementedError

    def render(self, msg: DisplayMessage) -> bool:
        """Render a message to the display. Return True on success."""
        raise NotImplementedError

    def clear(self):
        """Clear the display."""

    def disconnect(self):
        """Close the hardware connection."""
        self.connected = False

    def is_compatible(self, msg_type: MessageType) -> tuple[bool, str]:
        return is_compatible(msg_type, self.display_type)

    def show(self, msg: DisplayMessage) -> bool:
        """Thread-safe render with compatibility check."""
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


# ---------------------------------------------------------------------------
# OLED Mono adapter (SSD1306) via luma.oled
# ---------------------------------------------------------------------------


class OledMonoAdapter(DisplayAdapter):
    """SSD1306 128×64 / 128×32 monochrome OLED via I2C."""

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
                pass  # sadp: R61 ACCEPT — hardware cleanup on disconnect is best-effort (device may already be powered off / bus disconnected / adapter removed)
        super().disconnect()


# ---------------------------------------------------------------------------
# Color OLED adapter (SSD1351) via luma.oled
# ---------------------------------------------------------------------------


class OledColorAdapter(DisplayAdapter):
    """SSD1351 128×128 color OLED."""

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
                pass  # sadp: R61 ACCEPT — hardware cleanup on disconnect is best-effort (device may already be powered off / bus disconnected / adapter removed)
        super().disconnect()


# ---------------------------------------------------------------------------
# TFT Color adapter (ST7789 / ILI9341)
# ---------------------------------------------------------------------------


class TftColorAdapter(DisplayAdapter):
    """ST7789 / ILI9341 SPI TFT display."""

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
            # Word wrap for larger display
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
                pass  # sadp: R61 ACCEPT — hardware cleanup on disconnect is best-effort (device may already be powered off / bus disconnected / adapter removed)
        super().disconnect()


# ---------------------------------------------------------------------------
# Character LCD adapter (HD44780 via I2C PCF8574)
# ---------------------------------------------------------------------------


class CharLcdAdapter(DisplayAdapter):
    """HD44780 16×2 or 20×4 character LCD via I2C PCF8574 backpack."""

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
            # HD44780 does not support Unicode — replace non-ASCII
            safe = line.encode("ascii", errors="replace").decode("ascii")
            self._lcd.write_string(safe[: self._cols])
        return True

    def clear(self):
        if self.connected:
            try:
                self._lcd.clear()
            except Exception:
                pass  # sadp: R61 ACCEPT — hardware cleanup on disconnect is best-effort (device may already be powered off / bus disconnected / adapter removed)

    def disconnect(self):
        if self.connected:
            try:
                self._lcd.clear()
                self._lcd.close(clear=True)
            except Exception:
                pass  # sadp: R61 ACCEPT — hardware cleanup on disconnect is best-effort (device may already be powered off / bus disconnected / adapter removed)
        super().disconnect()


# ---------------------------------------------------------------------------
# e-Paper adapter (WaveShare)
# ---------------------------------------------------------------------------


class EPaperAdapter(DisplayAdapter):
    """WaveShare e-Paper / e-ink display via SPI."""

    display_type = DisplayType.E_PAPER

    # e-paper renders are expensive — deduplicate identical messages
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
        # De-duplicate: don't re-render the same content (saves panel life)
        key = f"{msg.title}|{msg.value}|{msg.body}"
        if key == self._last_rendered:
            return True
        self._last_rendered = key

        from PIL import Image, ImageDraw, ImageFont

        w = getattr(self._epd, "width", 122)
        h = getattr(self._epd, "height", 250)
        img = Image.new("1", (w, h), 255)  # white background for e-paper
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
        # Timestamp bottom right
        ts = time.strftime("%H:%M")
        draw.text((w - 28, h - 14), ts, fill=0, font=font_sm)

        self._epd.display(self._epd.getbuffer(img))
        return True

    def disconnect(self):
        if self.connected:
            try:
                self._epd.sleep()
            except Exception:
                pass  # sadp: R61 ACCEPT — hardware cleanup on disconnect is best-effort (device may already be powered off / bus disconnected / adapter removed)
        super().disconnect()


# ---------------------------------------------------------------------------
# Display detection
# ---------------------------------------------------------------------------

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
    """Return list of responding I2C addresses on the given bus."""
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
    """
    Auto-detect I2C displays and merge with any SPI/configured displays
    from extra_config.

    extra_config format:
        [{"type": "tft_color", "width": "240", "height": "240"},
         {"type": "e_paper",   "model": "epd2in13_V3"},
         {"type": "oled_color"}]

    Returns a list of connected DisplayAdapter instances.
    """
    adapters: list[DisplayAdapter] = []
    seen_types: set[DisplayType] = set()

    # 1. I2C scan
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

    # 2. Configured SPI / additional displays
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


# ---------------------------------------------------------------------------
# Display Manager — routes platform messages to all active displays
# ---------------------------------------------------------------------------


class MiniDisplayManager:
    """
    Central manager for all connected mini displays.
    Receives DisplayMessage objects and routes them to each adapter,
    skipping incompatible combinations with a logged explanation.

    Thread-safe. Non-blocking (messages queued).
    """

    def __init__(self, extra_config: Optional[list[dict]] = None):
        self._adapters: list[DisplayAdapter] = []
        self._queue: list[DisplayMessage] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._extra_cfg = extra_config or []

    def start(self):
        """Detect displays and start the routing thread."""
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
        """Flush queue, clear displays, disconnect all adapters."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        for adapter in self._adapters:
            try:
                adapter.clear()
                adapter.disconnect()
            except Exception:
                pass  # sadp: R61 ACCEPT — hardware cleanup on disconnect is best-effort (device may already be powered off / bus disconnected / adapter removed)
        self._adapters = []

    def send(self, msg: DisplayMessage):
        """Enqueue a message for display. Non-blocking."""
        if not self._adapters:
            return
        with self._lock:
            # Priority queue — lower number = higher priority
            self._queue.append(msg)
            self._queue.sort(key=lambda m: m.priority)
            # Cap queue size — drop lowest-priority excess
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
        """Convenience method — build and enqueue a DisplayMessage."""
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

    # ── Pre-built message helpers ─────────────────────────────────────────────

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
            body=f"{arrow} {change_pct:+.2f}%%",
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

    # ── Internal routing loop ─────────────────────────────────────────────────

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
            adapter.show(msg)  # show() handles compatibility internally

    # ── Status reporting ──────────────────────────────────────────────────────

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
        """Human-readable compatibility matrix for detected displays."""
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


# ---------------------------------------------------------------------------
# Module-level singleton (initialised lazily by AcervatorOS)
# ---------------------------------------------------------------------------

_manager: Optional[MiniDisplayManager] = None


def get_manager() -> MiniDisplayManager:
    """Return the module-level MiniDisplayManager (create if needed)."""
    global _manager
    if _manager is None:
        _manager = MiniDisplayManager()
    return _manager


def init_displays(extra_config: Optional[list[dict]] = None) -> MiniDisplayManager:
    """Initialise, detect, and start the global display manager."""
    global _manager
    _manager = MiniDisplayManager(extra_config=extra_config)
    _manager.start()
    return _manager
