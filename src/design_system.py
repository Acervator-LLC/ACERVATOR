"""
design_system.py — CHART AND PDF RENDERING TOKENS (light-theme, white bg).

SCOPE: matplotlib + ReportLab + any document emitted on a WHITE surface.
All contrast values in this module are verified WCAG AA against WHITE.

**NOT the same file as `src/gui/design_system.py`.** That sibling module
holds the DARK-THEME Qt GUI tokens (cyan/magenta on near-black surfaces).
The two cannot share concrete color values because they serve opposite
contrast backgrounds. If you are editing a Qt widget, import from
`src.gui.design_system`, not this module. TD-017 audit (2026-04-23)
formalized this relationship — they look like duplicates but aren't.

Single source of truth for all document and chart rendering in Acervator.
Replaces 30+ scattered `fontsize=` literals, 3+ hex color literals, and
ad-hoc `transform=ax.transAxes` placements with a semantic token system.

Authority: R54 DCR — Document & Chart Rendering Discipline (SADP v1.8).

Principles grounded in published research:

- Edward Tufte (1983, 1990) — data-ink ratio, small multiples, no chartjunk
- William Cleveland & McGill (1984) — graphical perception accuracy hierarchy
- Colin Ware (2012) — preattentive processing, semantic use of hue
- Cole Nussbaumer Knaflic (2015) — declutter, strategic contrast, takeaways
- Jonathan Schwabish (2021) — value-ordered categories, direct labels
- Matthew Butterick — type ramp at 1.25×, line height 120-145%
- Swiss / International Typographic Style — 8pt modular grid
- WCAG 2.1 AA — contrast ratios 4.5:1 normal, 3:1 large text

Visual direction: Swiss / Tufte minimal. White bg, hairline rules,
typography-driven hierarchy (not color), sparse semantic color, direct
labels preferred over legends, takeaway line on every chart.

Ordinal series palette: Okabe-Ito 2008 — colorblind-safe 8-color
qualitative palette. Used for multi-series data.

Semantic colors (win/loss/warn/info/accent) chosen for WCAG AA
against white: win ≥4.5:1, loss ≥4.5:1, accent ≥7:1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle  # v3.19.12 removed unused FancyBboxPatch


# ═══════════════════════════════════════════════════════════════════════════
# TOKENS — no hex literals or magic numbers anywhere else in chart code
# ═══════════════════════════════════════════════════════════════════════════

COLORS = {
    # Surfaces
    "bg":          "#ffffff",         # page background
    "bg_subtle":   "#fafafa",         # zebra stripe, callout
    "rule":        "#d4d4d4",         # hairline dividers (WCAG 3:1 non-text)

    # Ink (body text, headings)
    "ink":         "#1a1a1a",         # body text (15:1 on white)
    "ink_strong":  "#000000",         # h1 headings
    "ink_mute":    "#6b6b6b",         # captions, axis labels (5.7:1)
    "ink_faint":   "#9e9e9e",         # deep caption, not for text

    # Semantic (checked for AA on white)
    "accent":      "#1f3a68",         # navy, primary emphasis (10.7:1)
    "win":         "#1b5e20",         # deep green (8.2:1) — positive
    "loss":        "#b71c1c",         # deep red (7.3:1) — negative
    "warn":        "#bf360c",         # deeper orange (6.0:1) — caution
    "info":        "#0d47a1",         # deep blue (9.6:1) — info

    # Soft fills for backgrounds behind text (safe beyond 4.5:1 ink)
    "win_soft":    "#e8f5e9",
    "loss_soft":   "#ffebee",
    "warn_soft":   "#fff3e0",
    "info_soft":   "#e3f2fd",

    # Ordinal series — Okabe-Ito colorblind-safe (8 hues)
    "series": [
        "#0072B2",   # blue
        "#E69F00",   # orange
        "#009E73",   # bluish green
        "#CC79A7",   # reddish purple
        "#56B4E9",   # sky blue
        "#D55E00",   # vermillion
        "#F0E442",   # yellow (use sparingly — low contrast)
        "#000000",   # black
    ],
}

# Type ramp — Butterick 1.25× geometric progression
TYPE = {
    "h1":   {"size": 28, "weight": "bold",    "family": "sans"},
    "h2":   {"size": 18, "weight": "bold",    "family": "sans"},
    "h3":   {"size": 13, "weight": "bold",    "family": "sans"},
    "h4":   {"size": 11, "weight": "bold",    "family": "sans"},
    "body": {"size": 10, "weight": "regular", "family": "sans"},
    "cap":  {"size":  9, "weight": "regular", "family": "sans"},
    "mono": {"size":  9, "weight": "regular", "family": "mono"},
    "num":  {"size": 24, "weight": "bold",    "family": "sans"},  # stat numbers
}

# Base grid unit — 8pt Swiss grid
GRID = {
    "unit":       8,
    "pad_xs":     4,
    "pad_s":      8,
    "pad_m":     16,
    "pad_l":     32,
    "pad_xl":    64,
    # Page geometry — US letter landscape
    "page_w_in":   11.0,
    "page_h_in":    8.5,
    "margin_in":    0.75,
}

FAMILY_SANS = "DejaVu Sans"
FAMILY_MONO = "DejaVu Sans Mono"


# ═══════════════════════════════════════════════════════════════════════════
# MATPLOTLIB RC SETUP
# ═══════════════════════════════════════════════════════════════════════════

def apply_rcparams():
    """Apply design-system tokens to matplotlib rcParams globally."""
    matplotlib.rcParams.update({
        # Figure
        "figure.figsize":   (GRID["page_w_in"], GRID["page_h_in"]),
        "figure.dpi":       150,
        "savefig.dpi":      150,
        "figure.facecolor": COLORS["bg"],

        # Axes
        "axes.facecolor":   COLORS["bg"],
        "axes.edgecolor":   COLORS["rule"],
        "axes.linewidth":   0.6,
        "axes.labelcolor":  COLORS["ink_mute"],
        "axes.labelsize":   TYPE["cap"]["size"],
        "axes.titlesize":   TYPE["h3"]["size"],
        "axes.titleweight": TYPE["h3"]["weight"],
        "axes.titlelocation": "left",
        "axes.titlepad":    14,
        "axes.grid":        True,
        "axes.grid.axis":   "y",     # Tufte — horizontals only
        "axes.axisbelow":   True,    # grid under data
        "axes.spines.top":   False,  # declutter — no top/right frame
        "axes.spines.right": False,
        "axes.spines.left":  False,  # only bottom spine for bars/line
        "axes.spines.bottom": True,

        # Grid
        "grid.color":       COLORS["rule"],
        "grid.linewidth":   0.4,
        "grid.alpha":       0.8,

        # Ticks — understated, Tufte-style
        "xtick.color":      COLORS["ink_mute"],
        "ytick.color":      COLORS["ink_mute"],
        "xtick.labelsize":  TYPE["cap"]["size"],
        "ytick.labelsize":  TYPE["cap"]["size"],
        "xtick.major.size": 0,   # no tick marks
        "ytick.major.size": 0,
        "xtick.minor.size": 0,
        "ytick.minor.size": 0,

        # Font
        "font.family":      FAMILY_SANS,
        "font.size":        TYPE["body"]["size"],

        # Legend — minimal chrome
        "legend.frameon":   False,
        "legend.fontsize":  TYPE["cap"]["size"],

        # PDF output
        "pdf.fonttype":     42,      # TrueType — searchable text
    })


# ═══════════════════════════════════════════════════════════════════════════
# WCAG CONTRAST
# ═══════════════════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def _relative_luminance(rgb):
    """WCAG relative luminance."""
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 contrast ratio. Returns float in [1, 21]."""
    l1 = _relative_luminance(_hex_to_rgb(fg))
    l2 = _relative_luminance(_hex_to_rgb(bg))
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def validate_contrast(fg: str, bg: str, large_text: bool = False) -> tuple[bool, float]:
    """Check WCAG 2.1 AA. Returns (passes, ratio)."""
    ratio = contrast_ratio(fg, bg)
    threshold = 3.0 if large_text else 4.5
    return ratio >= threshold, round(ratio, 2)


def contrast_self_test() -> list[tuple]:
    """Verify all semantic ink colors pass WCAG AA on white."""
    results = []
    for name in ["ink", "ink_strong", "ink_mute", "accent",
                 "win", "loss", "warn", "info"]:
        ok, r = validate_contrast(COLORS[name], COLORS["bg"])
        results.append((name, COLORS[name], r, "✓" if ok else "✗"))
    return results


# ═══════════════════════════════════════════════════════════════════════════
# LAYOUT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def blank_page():
    """Return a blank figure with axes hidden — for full-page layouts."""
    fig = plt.figure(figsize=(GRID["page_w_in"], GRID["page_h_in"]))
    ax = fig.add_subplot(111)
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    return fig, ax


def _put(ax, x, y, text, *, level="body", color=None, align="left",
         valign="baseline", weight_override=None):
    """Place text using type-ramp tokens. All positions in ax fraction
    coords (0-1), so layouts scale with page size."""
    t = TYPE[level]
    ax.text(
        x, y, text,
        fontsize=t["size"],
        fontweight=weight_override or t["weight"],
        fontfamily=FAMILY_MONO if t["family"] == "mono" else FAMILY_SANS,
        color=color or COLORS["ink"],
        ha=align, va=valign,
        transform=ax.transAxes,
    )


def hline(ax, y, color=None, width=0.6, x_start=0.0, x_end=1.0):
    """Draw a hairline rule in ax fraction coords."""
    ax.plot([x_start, x_end], [y, y],
            color=color or COLORS["rule"], lw=width,
            transform=ax.transAxes, clip_on=False)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE TEMPLATES — used by renderers instead of ad-hoc layout
# ═══════════════════════════════════════════════════════════════════════════

def cover_page(pdf: PdfPages, *,
               eyebrow: str = "",
               title: str,
               subtitle: str = "",
               stats: list[tuple[str, str]] | None = None,
               footer: str = "",
               footer_detail: str = ""):
    """Swiss cover: generous whitespace, typography-driven hierarchy,
    no rectangle band. `stats` = [(label, value), ...]."""
    fig, ax = blank_page()

    # Eyebrow (small uppercase) at top — sets context without stealing
    if eyebrow:
        _put(ax, 0.08, 0.90, eyebrow.upper(), level="cap",
             color=COLORS["ink_mute"])
        hline(ax, 0.885, x_start=0.08, x_end=0.30)

    # Title — dominant, left-aligned
    _put(ax, 0.08, 0.74, title, level="h1",
         color=COLORS["ink_strong"])

    # Subtitle
    if subtitle:
        _put(ax, 0.08, 0.66, subtitle, level="h3",
             color=COLORS["ink_mute"], weight_override="regular")

    # Stats row — Swiss grid, generous gutters
    if stats:
        # Clamp to 4 per row — wider columns = room for formatted numbers
        # Multi-row support: first 4 on top, remainder below
        rows_of_stats = [stats[i:i+4] for i in range(0, len(stats), 4)]
        gutter_start = 0.08
        gutter_end = 0.92
        row_y_val_base = 0.42
        row_spacing = 0.18

        for row_i, row_stats in enumerate(rows_of_stats):
            n = len(row_stats)
            col_w = (gutter_end - gutter_start) / n
            y_val = row_y_val_base - row_i * row_spacing
            y_lab = y_val - 0.06
            if row_i == 0:
                hline(ax, y_lab + 0.07,
                      x_start=gutter_start, x_end=gutter_end)
            for i, (label, value) in enumerate(row_stats):
                # Center-anchor in column to avoid overflow collision
                x = gutter_start + col_w * (i + 0.5)
                _put(ax, x, y_val, str(value), level="num",
                     color=COLORS["accent"], align="center")
                _put(ax, x, y_lab, label.upper(), level="cap",
                     color=COLORS["ink_mute"], align="center")

    # Footer
    hline(ax, 0.14, x_start=0.08, x_end=0.92)
    if footer:
        _put(ax, 0.08, 0.10, footer, level="cap",
             color=COLORS["ink_mute"])
    if footer_detail:
        _put(ax, 0.92, 0.10, footer_detail, level="cap",
             color=COLORS["ink_mute"], align="right")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def section_page(pdf: PdfPages, *, heading: str,
                 body_lines: list[str] | None = None):
    """Simple title page for section break."""
    fig, ax = blank_page()
    _put(ax, 0.08, 0.70, heading, level="h1",
         color=COLORS["ink_strong"])
    hline(ax, 0.65, x_start=0.08, x_end=0.30)
    if body_lines:
        y = 0.58
        for line in body_lines:
            _put(ax, 0.08, y, line, level="body",
                 color=COLORS["ink"])
            y -= 0.045
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def chart_page(pdf: PdfPages, *, title: str, xlabel: str = "",
               ylabel: str = "", plot_fn,
               takeaway: str = "", source: str = ""):
    """Standard chart page: title top-left, chart fills middle,
    takeaway + source in footer. plot_fn(ax) renders the actual chart."""
    fig = plt.figure(figsize=(GRID["page_w_in"], GRID["page_h_in"]))
    # Layout: 8% margin top for title, 15% bottom for takeaway/source
    ax_chart = fig.add_axes([0.08, 0.20, 0.84, 0.64])
    ax_chrome = fig.add_axes([0, 0, 1, 1], frame_on=False)
    ax_chrome.set_axis_off()
    ax_chrome.set_xlim(0, 1); ax_chrome.set_ylim(0, 1)

    # Title + subtitle area (top)
    _put(ax_chrome, 0.08, 0.92, title, level="h2",
         color=COLORS["ink_strong"])
    hline(ax_chrome, 0.885, x_start=0.08, x_end=0.92)

    # Chart
    plot_fn(ax_chart)
    if xlabel:
        ax_chart.set_xlabel(xlabel, fontsize=TYPE["cap"]["size"],
                            color=COLORS["ink_mute"])
    if ylabel:
        ax_chart.set_ylabel(ylabel, fontsize=TYPE["cap"]["size"],
                            color=COLORS["ink_mute"])

    # Takeaway (bottom, bold) + source (small caption, right)
    if takeaway:
        _put(ax_chrome, 0.08, 0.12, takeaway, level="h4",
             color=COLORS["accent"])
    hline(ax_chrome, 0.09, x_start=0.08, x_end=0.92)
    if source:
        _put(ax_chrome, 0.92, 0.06, source, level="cap",
             color=COLORS["ink_mute"], align="right")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# TABLES — paginated, never clip
# ═══════════════════════════════════════════════════════════════════════════

def paginated_table(pdf: PdfPages, *,
                    title: str,
                    columns: list[dict],   # [{"key":k,"label":l,"x":0.08,"align":"left","fmt":fn}, ...]
                    rows: list[dict],
                    rows_per_page: int = 32,
                    takeaway: str = "",
                    source: str = ""):
    """Render a table across however many pages are needed.
    Never silently drops rows (R54 DCR)."""
    if not rows:
        fig, ax = blank_page()
        _put(ax, 0.08, 0.92, title, level="h2",
             color=COLORS["ink_strong"])
        _put(ax, 0.5, 0.5, "(no data)", level="body",
             color=COLORS["ink_mute"], align="center")
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)
        return

    total_pages = math.ceil(len(rows) / rows_per_page)
    for page_i in range(total_pages):
        fig, ax = blank_page()
        page_rows = rows[page_i * rows_per_page:(page_i + 1) * rows_per_page]

        # Title + pagination indicator
        page_note = (f" ({page_i + 1} of {total_pages})"
                     if total_pages > 1 else "")
        _put(ax, 0.08, 0.92, title + page_note, level="h2",
             color=COLORS["ink_strong"])
        hline(ax, 0.905, x_start=0.08, x_end=0.92)

        # Header row
        header_y = 0.86
        for col in columns:
            _put(ax, col["x"], header_y, col["label"].upper(),
                 level="cap", color=COLORS["ink_mute"],
                 align=col.get("align", "left"), weight_override="bold")
        hline(ax, header_y - 0.015, x_start=0.08, x_end=0.92)

        # Data rows
        row_h = 0.74 / rows_per_page
        y = header_y - 0.04
        for i, row in enumerate(page_rows):
            # Zebra stripe
            if i % 2 == 1:
                rect = Rectangle((0.08, y - row_h * 0.7), 0.84, row_h,
                                 facecolor=COLORS["bg_subtle"],
                                 edgecolor="none",
                                 transform=ax.transAxes)
                ax.add_patch(rect)
            for col in columns:
                value = row.get(col["key"], "")
                if "fmt" in col and col["fmt"] is not None:
                    value = col["fmt"](value)
                color = row.get("_color_" + col["key"], COLORS["ink"])
                _put(ax, col["x"], y, str(value),
                     level="body", color=color,
                     align=col.get("align", "left"))
            y -= row_h

        # Footer
        hline(ax, 0.09, x_start=0.08, x_end=0.92)
        if takeaway and page_i == total_pages - 1:
            _put(ax, 0.08, 0.12, takeaway, level="h4",
                 color=COLORS["accent"])
        if source:
            _put(ax, 0.92, 0.06, source, level="cap",
                 color=COLORS["ink_mute"], align="right")

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════
# CHART HELPERS — standard forms
# ═══════════════════════════════════════════════════════════════════════════

def bar_h(ax, *, labels, values, colors=None, direct_labels=True,
          label_fmt=None, value_at_bar_end=True):
    """Horizontal bar chart — Swiss style. Labels at left, values at
    bar end by default (direct labels > legend per Schwabish)."""
    y = list(range(len(labels)))
    if colors is None:
        colors = [COLORS["accent"]] * len(values)
    ax.barh(y, values, color=colors, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=TYPE["cap"]["size"])
    ax.invert_yaxis()
    ax.axvline(0, color=COLORS["rule"], lw=0.6)
    if direct_labels and label_fmt:
        for i, v in enumerate(values):
            offset = max(abs(v), 1) * 0.02
            ax.text(v + (offset if v >= 0 else -offset),
                    i, label_fmt(v),
                    va="center",
                    ha="left" if v >= 0 else "right",
                    fontsize=TYPE["cap"]["size"] - 1,
                    color=COLORS["ink"])


def callout_value(ax, *, label: str, value: str, context: str = ""):
    """Big-number callout for a single important value. Use on dedicated
    page when one number dwarfs others (honest > compressed)."""
    ax.set_axis_off()
    _put(ax, 0.5, 0.66, label.upper(), level="cap",
         color=COLORS["ink_mute"], align="center")
    _put(ax, 0.5, 0.50, value, level="h1",
         color=COLORS["accent"], align="center",
         weight_override="bold")
    # Larger than h1 — render at 54pt manually
    ax.text(0.5, 0.50, value,
            fontsize=54, fontweight="bold",
            fontfamily=FAMILY_SANS,
            color=COLORS["accent"],
            ha="center", va="center",
            transform=ax.transAxes)
    if context:
        _put(ax, 0.5, 0.34, context, level="body",
             color=COLORS["ink_mute"], align="center")


# ═══════════════════════════════════════════════════════════════════════════
# NUMBER FORMATTERS
# ═══════════════════════════════════════════════════════════════════════════

def fmt_usd(v, short=True, signed=True) -> str:
    """Tufte-honest USD formatting — magnitudes preserved, not hidden."""
    if v is None:
        return "—"
    try:
        v = float(v)
    except (ValueError, TypeError):
        return str(v)
    sign = "+" if signed and v >= 0 else ("" if v >= 0 else "-")
    absv = abs(v)
    if short:
        if absv >= 1e9:   return f"{sign}${absv/1e9:,.1f}B"
        if absv >= 1e6:   return f"{sign}${absv/1e6:,.1f}M"
        if absv >= 1e3:   return f"{sign}${absv/1e3:,.1f}K"
        return f"{sign}${absv:,.0f}"
    return f"{sign}${absv:,.0f}"


def fmt_pct(v, digits=1) -> str:
    if v is None:
        return "—"
    return f"{float(v):.{digits}f}%"


def fmt_count(v) -> str:
    if v is None:
        return "—"
    return f"{int(v):,}"


# ═══════════════════════════════════════════════════════════════════════════
# SELF-TEST — R53 OPT benchmark validation
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Contrast compliance report
    print("WCAG 2.1 AA contrast check (foreground on white):")
    for name, hex_, ratio, ok in contrast_self_test():
        print(f"  {ok} {name:12s} {hex_}  ratio={ratio:5.2f}:1")
    print()
    print(f"Type ramp:")
    for k, v in TYPE.items():
        print(f"  {k:6s} {v['size']:2d}pt {v['weight']:<8s} {v['family']}")
    print()
    print(f"Grid unit: {GRID['unit']}pt")
    print(f"Series palette: {len(COLORS['series'])} colors (Okabe-Ito)")
