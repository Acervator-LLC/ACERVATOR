"""Chart and PDF rendering tokens for a white page.

``COLORS``, ``TYPE`` and ``GRID`` carry the hex values, point sizes and
spacing that ``apply_rcparams`` writes into matplotlib rcParams.
``cover_page``, ``section_page``, ``chart_page`` and ``paginated_table``
each draw pages into a ``PdfPages``. ``contrast_self_test`` measures the
ink tokens against ``COLORS["bg"]`` through ``contrast_ratio``.
"""

from __future__ import annotations

import math

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

COLORS = {
    "bg": "#ffffff",
    "bg_subtle": "#fafafa",
    "rule": "#d4d4d4",  # hairline dividers; measures 1.48:1 on white
    "ink": "#1a1a1a",
    "ink_strong": "#000000",
    "ink_mute": "#6b6b6b",
    "ink_faint": "#9e9e9e",  # 2.68:1 on white, under the 4.5:1 AA floor
    "accent": "#1f3a68",
    "win": "#1b5e20",
    "loss": "#b71c1c",
    "warn": "#bf360c",
    "info": "#0d47a1",
    "win_soft": "#e8f5e9",
    "loss_soft": "#ffebee",
    "warn_soft": "#fff3e0",
    "info_soft": "#e3f2fd",
    # Okabe-Ito palette; "#F0E442" measures 1.32:1 on white
    "series": [
        "#0072B2",
        "#E69F00",
        "#009E73",
        "#CC79A7",
        "#56B4E9",
        "#D55E00",
        "#F0E442",
        "#000000",
    ],
}

TYPE = {
    "h1": {"size": 28, "weight": "bold", "family": "sans"},
    "h2": {"size": 18, "weight": "bold", "family": "sans"},
    "h3": {"size": 13, "weight": "bold", "family": "sans"},
    "h4": {"size": 11, "weight": "bold", "family": "sans"},
    "body": {"size": 10, "weight": "regular", "family": "sans"},
    "cap": {"size": 9, "weight": "regular", "family": "sans"},
    "mono": {"size": 9, "weight": "regular", "family": "mono"},
    "num": {"size": 24, "weight": "bold", "family": "sans"},
}

GRID = {
    "unit": 8,
    "pad_xs": 4,
    "pad_s": 8,
    "pad_m": 16,
    "pad_l": 32,
    "pad_xl": 64,
    # page_w_in and page_h_in are US Letter, landscape
    "page_w_in": 11.0,
    "page_h_in": 8.5,
    "margin_in": 0.75,
}

FAMILY_SANS = "DejaVu Sans"
FAMILY_MONO = "DejaVu Sans Mono"


def apply_rcparams():
    """Write the ``COLORS``, ``TYPE`` and ``GRID`` tokens into matplotlib rcParams."""
    matplotlib.rcParams.update(
        {
            "figure.figsize": (GRID["page_w_in"], GRID["page_h_in"]),
            "figure.dpi": 150,
            "savefig.dpi": 150,
            "figure.facecolor": COLORS["bg"],
            "axes.facecolor": COLORS["bg"],
            "axes.edgecolor": COLORS["rule"],
            "axes.linewidth": 0.6,
            "axes.labelcolor": COLORS["ink_mute"],
            "axes.labelsize": TYPE["cap"]["size"],
            "axes.titlesize": TYPE["h3"]["size"],
            "axes.titleweight": TYPE["h3"]["weight"],
            "axes.titlelocation": "left",
            "axes.titlepad": 14,
            "axes.grid": True,
            "axes.grid.axis": "y",  # horizontal grid lines only
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.spines.bottom": True,
            "grid.color": COLORS["rule"],
            "grid.linewidth": 0.4,
            "grid.alpha": 0.8,
            "xtick.color": COLORS["ink_mute"],
            "ytick.color": COLORS["ink_mute"],
            "xtick.labelsize": TYPE["cap"]["size"],
            "ytick.labelsize": TYPE["cap"]["size"],
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "xtick.minor.size": 0,
            "ytick.minor.size": 0,
            "font.family": FAMILY_SANS,
            "font.size": TYPE["body"]["size"],
            "legend.frameon": False,
            "legend.fontsize": TYPE["cap"]["size"],
            "pdf.fonttype": 42,  # 42 is TrueType; PDF text stays searchable
        }
    )


def _hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def _relative_luminance(rgb):
    """Return the WCAG 2.1 relative luminance of ``rgb``."""

    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """Return the contrast ratio of ``fg`` against ``bg``, from 1 to 21."""
    l1 = _relative_luminance(_hex_to_rgb(fg))
    l2 = _relative_luminance(_hex_to_rgb(bg))
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def validate_contrast(fg: str, bg: str, large_text: bool = False) -> tuple[bool, float]:
    """Return whether ``fg`` on ``bg`` clears the AA floor, and the measured ratio.

    ``large_text`` lowers that floor from 4.5 to 3.0.
    """
    ratio = contrast_ratio(fg, bg)
    threshold = 3.0 if large_text else 4.5
    return ratio >= threshold, round(ratio, 2)


def contrast_self_test() -> list[tuple]:
    """Return one row per ink token: its name, hex, ratio and pass mark.

    ``ink_faint`` and ``rule`` are absent from the list and clear neither
    floor ``validate_contrast`` applies.
    """
    results = []
    for name in [
        "ink",
        "ink_strong",
        "ink_mute",
        "accent",
        "win",
        "loss",
        "warn",
        "info",
    ]:
        ok, r = validate_contrast(COLORS[name], COLORS["bg"])
        results.append((name, COLORS[name], r, "✓" if ok else "✗"))
    return results


def blank_page():
    """Return a ``GRID``-sized figure and an axes with the frame off, limits 0 to 1."""
    fig = plt.figure(figsize=(GRID["page_w_in"], GRID["page_h_in"]))
    ax = fig.add_subplot(111)
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    return fig, ax


def _put(
    ax,
    x,
    y,
    text,
    *,
    level="body",
    color=None,
    align="left",
    valign="baseline",
    weight_override=None,
):
    """Draw ``text`` on ``ax`` at the size and family ``TYPE[level]`` carries.

    ``x`` and ``y`` are axes-fraction coordinates from 0 to 1.
    """
    t = TYPE[level]
    ax.text(
        x,
        y,
        text,
        fontsize=t["size"],
        fontweight=weight_override or t["weight"],
        fontfamily=FAMILY_MONO if t["family"] == "mono" else FAMILY_SANS,
        color=color or COLORS["ink"],
        ha=align,
        va=valign,
        transform=ax.transAxes,
    )


def hline(ax, y, color=None, width=0.6, x_start=0.0, x_end=1.0):
    """Draw a rule on ``ax`` from ``x_start`` to ``x_end`` at height ``y``."""
    ax.plot(
        [x_start, x_end],
        [y, y],
        color=color or COLORS["rule"],
        lw=width,
        transform=ax.transAxes,
        clip_on=False,
    )


def cover_page(
    pdf: PdfPages,
    *,
    eyebrow: str = "",
    title: str,
    subtitle: str = "",
    stats: list[tuple[str, str]] | None = None,
    footer: str = "",
    footer_detail: str = "",
):
    """Draw one cover page into ``pdf`` from ``eyebrow``, ``title`` and ``subtitle``.

    ``stats`` holds (label, value) pairs and lays out four to a row.
    """
    fig, ax = blank_page()

    if eyebrow:
        _put(ax, 0.08, 0.90, eyebrow.upper(), level="cap", color=COLORS["ink_mute"])
        hline(ax, 0.885, x_start=0.08, x_end=0.30)

    _put(ax, 0.08, 0.74, title, level="h1", color=COLORS["ink_strong"])

    if subtitle:
        _put(
            ax,
            0.08,
            0.66,
            subtitle,
            level="h3",
            color=COLORS["ink_mute"],
            weight_override="regular",
        )

    if stats:
        rows_of_stats = [stats[i : i + 4] for i in range(0, len(stats), 4)]
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
                hline(ax, y_lab + 0.07, x_start=gutter_start, x_end=gutter_end)
            for i, (label, value) in enumerate(row_stats):
                x = gutter_start + col_w * (i + 0.5)
                _put(
                    ax,
                    x,
                    y_val,
                    str(value),
                    level="num",
                    color=COLORS["accent"],
                    align="center",
                )
                _put(
                    ax,
                    x,
                    y_lab,
                    label.upper(),
                    level="cap",
                    color=COLORS["ink_mute"],
                    align="center",
                )

    hline(ax, 0.14, x_start=0.08, x_end=0.92)
    if footer:
        _put(ax, 0.08, 0.10, footer, level="cap", color=COLORS["ink_mute"])
    if footer_detail:
        _put(
            ax,
            0.92,
            0.10,
            footer_detail,
            level="cap",
            color=COLORS["ink_mute"],
            align="right",
        )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def section_page(pdf: PdfPages, *, heading: str, body_lines: list[str] | None = None):
    """Draw one page into ``pdf`` from ``heading`` and each entry of ``body_lines``."""
    fig, ax = blank_page()
    _put(ax, 0.08, 0.70, heading, level="h1", color=COLORS["ink_strong"])
    hline(ax, 0.65, x_start=0.08, x_end=0.30)
    if body_lines:
        y = 0.58
        for line in body_lines:
            _put(ax, 0.08, y, line, level="body", color=COLORS["ink"])
            y -= 0.045
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def chart_page(
    pdf: PdfPages,
    *,
    title: str,
    xlabel: str = "",
    ylabel: str = "",
    plot_fn,
    takeaway: str = "",
    source: str = "",
):
    """Draw one chart page into ``pdf``; ``plot_fn`` receives the chart axes.

    ``title``, ``xlabel``, ``ylabel``, ``takeaway`` and ``source`` frame it.
    """
    fig = plt.figure(figsize=(GRID["page_w_in"], GRID["page_h_in"]))
    ax_chart = fig.add_axes((0.08, 0.20, 0.84, 0.64))
    ax_chrome = fig.add_axes((0.0, 0.0, 1.0, 1.0), frame_on=False)
    ax_chrome.set_axis_off()
    ax_chrome.set_xlim(0, 1)
    ax_chrome.set_ylim(0, 1)

    _put(ax_chrome, 0.08, 0.92, title, level="h2", color=COLORS["ink_strong"])
    hline(ax_chrome, 0.885, x_start=0.08, x_end=0.92)

    plot_fn(ax_chart)
    if xlabel:
        ax_chart.set_xlabel(
            xlabel, fontsize=TYPE["cap"]["size"], color=COLORS["ink_mute"]
        )
    if ylabel:
        ax_chart.set_ylabel(
            ylabel, fontsize=TYPE["cap"]["size"], color=COLORS["ink_mute"]
        )

    if takeaway:
        _put(ax_chrome, 0.08, 0.12, takeaway, level="h4", color=COLORS["accent"])
    hline(ax_chrome, 0.09, x_start=0.08, x_end=0.92)
    if source:
        _put(
            ax_chrome,
            0.92,
            0.06,
            source,
            level="cap",
            color=COLORS["ink_mute"],
            align="right",
        )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def paginated_table(
    pdf: PdfPages,
    *,
    title: str,
    columns: list[dict],
    rows: list[dict],
    rows_per_page: int = 32,
    takeaway: str = "",
    source: str = "",
):
    """Draw ``rows`` into ``pdf``, ``rows_per_page`` at a time, dropping none.

    Each entry of ``columns`` carries ``key``, ``label``, ``x``, ``align`` and ``fmt``.
    """
    if not rows:
        fig, ax = blank_page()
        _put(ax, 0.08, 0.92, title, level="h2", color=COLORS["ink_strong"])
        _put(
            ax,
            0.5,
            0.5,
            "(no data)",
            level="body",
            color=COLORS["ink_mute"],
            align="center",
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
        return

    total_pages = math.ceil(len(rows) / rows_per_page)
    for page_i in range(total_pages):
        fig, ax = blank_page()
        page_rows = rows[page_i * rows_per_page : (page_i + 1) * rows_per_page]

        page_note = f" ({page_i + 1} of {total_pages})" if total_pages > 1 else ""
        _put(ax, 0.08, 0.92, title + page_note, level="h2", color=COLORS["ink_strong"])
        hline(ax, 0.905, x_start=0.08, x_end=0.92)

        header_y = 0.86
        for col in columns:
            _put(
                ax,
                col["x"],
                header_y,
                col["label"].upper(),
                level="cap",
                color=COLORS["ink_mute"],
                align=col.get("align", "left"),
                weight_override="bold",
            )
        hline(ax, header_y - 0.015, x_start=0.08, x_end=0.92)

        row_h = 0.74 / rows_per_page
        y = header_y - 0.04
        for i, row in enumerate(page_rows):
            if i % 2 == 1:
                rect = Rectangle(
                    (0.08, y - row_h * 0.7),
                    0.84,
                    row_h,
                    facecolor=COLORS["bg_subtle"],
                    edgecolor="none",
                    transform=ax.transAxes,
                )
                ax.add_patch(rect)
            for col in columns:
                value = row.get(col["key"], "")
                if "fmt" in col and col["fmt"] is not None:
                    value = col["fmt"](value)
                color = row.get("_color_" + col["key"], COLORS["ink"])
                _put(
                    ax,
                    col["x"],
                    y,
                    str(value),
                    level="body",
                    color=color,
                    align=col.get("align", "left"),
                )
            y -= row_h

        hline(ax, 0.09, x_start=0.08, x_end=0.92)
        if takeaway and page_i == total_pages - 1:
            _put(ax, 0.08, 0.12, takeaway, level="h4", color=COLORS["accent"])
        if source:
            _put(
                ax,
                0.92,
                0.06,
                source,
                level="cap",
                color=COLORS["ink_mute"],
                align="right",
            )

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def bar_h(
    ax,
    *,
    labels,
    values,
    colors=None,
    direct_labels=True,
    label_fmt=None,
    value_at_bar_end=True,
):
    """Draw a horizontal bar chart on ``ax`` from ``labels`` and ``values``.

    ``direct_labels`` prints a value beside its bar only when ``label_fmt`` is given.
    """
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
            ax.text(
                v + (offset if v >= 0 else -offset),
                i,
                label_fmt(v),
                va="center",
                ha="left" if v >= 0 else "right",
                fontsize=TYPE["cap"]["size"] - 1,
                color=COLORS["ink"],
            )


def callout_value(ax, *, label: str, value: str, context: str = ""):
    """Draw ``value`` centred on ``ax`` under ``label``.

    ``context`` sits below both in body type.
    """
    ax.set_axis_off()
    _put(
        ax,
        0.5,
        0.66,
        label.upper(),
        level="cap",
        color=COLORS["ink_mute"],
        align="center",
    )
    _put(
        ax,
        0.5,
        0.50,
        value,
        level="h1",
        color=COLORS["accent"],
        align="center",
        weight_override="bold",
    )
    # 54 is above every size in TYPE
    ax.text(
        0.5,
        0.50,
        value,
        fontsize=54,
        fontweight="bold",
        fontfamily=FAMILY_SANS,
        color=COLORS["accent"],
        ha="center",
        va="center",
        transform=ax.transAxes,
    )
    if context:
        _put(
            ax,
            0.5,
            0.34,
            context,
            level="body",
            color=COLORS["ink_mute"],
            align="center",
        )


def fmt_usd(v, short=True, signed=True) -> str:
    """Format ``v`` as USD, ``short`` collapsing thousands to K, M and B.

    ``signed`` prefixes a plus on a value at or above zero.
    """
    if v is None:
        return "—"
    try:
        v = float(v)
    except (ValueError, TypeError):
        return str(v)
    sign = "+" if signed and v >= 0 else ("" if v >= 0 else "-")
    absv = abs(v)
    if short:
        if absv >= 1e9:
            return f"{sign}${absv/1e9:,.1f}B"
        if absv >= 1e6:
            return f"{sign}${absv/1e6:,.1f}M"
        if absv >= 1e3:
            return f"{sign}${absv/1e3:,.1f}K"
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


if __name__ == "__main__":
    print("WCAG 2.1 AA contrast check (foreground on white):")
    for name, hex_, ratio, ok in contrast_self_test():
        print(f"  {ok} {name:12s} {hex_}  ratio={ratio:5.2f}:1")
    print()
    print("Type ramp:")
    for k, v in TYPE.items():
        print(f"  {k:6s} {v['size']:2d}pt {v['weight']:<8s} {v['family']}")
    print()
    print(f"Grid unit: {GRID['unit']}pt")
    print(f"Series palette: {len(COLORS['series'])} colors (Okabe-Ito)")
