"""splash_screen_painter.py -- draws the splash with QPainter and builds its still.

``replay`` issues one QPainter call per entry of the list
``splash_screen_surface`` returns, which is how the Qt splash in ``main.py``
draws the mark. ``compose_still`` runs each component generator into its own
layer image through ``bake_groups``, applies a bloom, a blur, grain, a grade and
a vignette, and writes the composed still frame beside the layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
)

from src.gui.main_tabs import splash_screen_surface as surface

LAYER_SIDE = 512
LAYER_SPAN = 2.0
MARK_LAYER_ORDER = (
    "winged caduceus",
    "compass",
    "scythe",
    "scale",
    "fiery aura",
    "reptilian eye",
)
BLOOM_LAYERS = ("fiery aura",)


def _colour(rgba: list) -> QColor:
    return QColor(int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3]))


def _points(raw: list) -> list:
    return [QPointF(float(point[0]), float(point[1])) for point in raw]


def _font(spec: list) -> QFont:
    weight = QFont.Bold if len(spec) > 3 and spec[3] == surface.BOLD else QFont.Normal
    return QFont(str(spec[1]), int(spec[2]), weight)


def _gradient(spec: list) -> QLinearGradient:
    start, end, stops = spec[1], spec[2], spec[3]
    ramp = QLinearGradient(
        float(start[0]), float(start[1]), float(end[0]), float(end[1])
    )
    for at, rgba in stops:
        ramp.setColorAt(float(at), _colour(rgba))
    return ramp


def _mesh(painter: QPainter, faces: list) -> None:
    for face in faces:
        colour = _colour(face[3])
        seam = QPen(colour)
        seam.setWidthF(surface.FACET_SEAM_WIDTH)
        painter.setPen(seam)
        painter.setBrush(QBrush(colour))
        painter.drawPolygon(_points(face[:3]))


def replay(painter: QPainter, ops: list) -> int:
    """Issue one QPainter call per entry of `ops` and return how many it issued."""
    issued = 0
    for op in ops:
        name = op[0]
        if name == "render_hint":
            painter.setRenderHint(QPainter.Antialiasing)
        elif name == "mesh":
            _mesh(painter, op[1])
        elif name == "pen":
            pen = QPen(_colour(op[1]))
            pen.setWidthF(float(op[2]))
            painter.setPen(pen)
        elif name == "pen_colour":
            painter.setPen(_colour(op[1]))
        elif name == "pen_style":
            painter.setPen(Qt.NoPen)
        elif name == "brush_colour":
            painter.setBrush(QBrush(_colour(op[1])))
        elif name == "brush_style":
            painter.setBrush(Qt.NoBrush)
        elif name == "ellipse":
            box = op[1]
            painter.drawEllipse(
                QRectF(float(box[0]), float(box[1]), float(box[2]), float(box[3]))
            )
        elif name == "line":
            painter.drawLine(int(op[1]), int(op[2]), int(op[3]), int(op[4]))
        elif name == "fill_rect":
            painter.fillRect(
                int(op[1]), int(op[2]), int(op[3]), int(op[4]), _gradient(op[5])
            )
        elif name == "font":
            painter.setFont(_font(op))
        elif name == "text":
            box = op[1]
            painter.drawText(
                QRectF(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                Qt.AlignCenter,
                str(op[3]),
            )
        elif name == "save":
            painter.save()
        elif name == "restore":
            painter.restore()
        elif name == "translate":
            painter.translate(float(op[1]), float(op[2]))
        elif name == "rotate":
            painter.rotate(float(op[1]))
        elif name == "end":
            continue
        else:
            raise ValueError(f"splash painter has no call named {name!r}")
        issued += 1
    return issued


def bake_groups(groups: list, side: int = LAYER_SIDE) -> QImage:
    """Rasterise one component's triangle groups into its own transparent image."""
    image = QImage(side, side, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    half = side / 2.0
    radius = side / LAYER_SPAN
    for faces, rgb, part, bias in groups:
        _mesh(
            painter,
            surface.toned_mesh(
                faces, rgb, int(surface.FULL_ALPHA * part), bias, half, half, radius
            ),
        )
    painter.end()
    return image


def mark_ops(cx: Any, cy: Any, alpha: int, spin: Any, pulse: Any, t: Any) -> list:
    """The mark's painter calls, taken from `sigil_ops` in the surface module."""
    return surface.sigil_ops(cx, cy, alpha, spin, pulse, t)


STILL_SIDE = 1024
STILL_MOMENT = 3.0
BACKDROP = (6, 6, 14)
GRAIN_STRENGTH = 7
OUTER_BLUR_RADIUS = 1.1
STILL_BLOOM_RADIUS = 9.0
STILL_BLOOM_STRENGTH = 0.62
GRADE_GAIN = (0.98, 1.02, 1.03)
GRADE_LIFT = (2, 3, 6)
VIGNETTE_STRENGTH = 0.34
VIGNETTE_FLAT = 0.45


def _pillow(layer: QImage):
    from PIL import Image

    raw = layer.convertToFormat(QImage.Format_RGBA8888)
    data = bytes(raw.constBits())[: raw.height() * raw.bytesPerLine()]
    out = Image.frombuffer(
        "RGBA", (raw.width(), raw.height()), data, "raw", "RGBA", raw.bytesPerLine(), 1
    )
    return out.copy()


def with_bloom(layer, radius: float, strength: float):
    """Put a blurred copy of `layer` behind itself so the bright areas glow."""
    from PIL import Image, ImageFilter

    halo = layer.filter(ImageFilter.GaussianBlur(radius))
    faded = halo.copy()
    faded.putalpha(halo.getchannel("A").point(lambda v: int(v * strength)))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(faded)
    out.alpha_composite(layer)
    return out


def with_outer_blur(layer, radius: float):
    """Soften one layer so the outer components sit behind the eye."""
    from PIL import ImageFilter

    return layer.filter(ImageFilter.GaussianBlur(radius))


def with_grain(image, strength: int):
    """Add even noise across the picture so the surface carries texture."""
    import numpy
    from PIL import Image

    pixels = numpy.asarray(image.convert("RGB")).astype(numpy.int16)
    noise = numpy.random.default_rng(0).integers(
        -strength, strength + 1, pixels.shape, dtype=numpy.int16
    )
    return Image.fromarray(
        numpy.clip(pixels + noise, 0, 255).astype(numpy.uint8), "RGB"
    )


def with_grade(image, gain: tuple, lift: tuple):
    """Scale and lift each channel so the whole picture sits in one light."""
    from PIL import Image

    bands = [
        band.point(lambda v, i=index: min(255, int(v * gain[i]) + lift[i]))
        for index, band in enumerate(image.convert("RGB").split())
    ]
    return Image.merge("RGB", bands)


def with_vignette(image, strength: float):
    """Darken the corners so the eye lands on the middle of the mark."""
    import numpy
    from PIL import Image

    width, height = image.size
    rows, columns = numpy.mgrid[0:height, 0:width]
    dx = (columns - width / 2) / (width / 2)
    dy = (rows - height / 2) / (height / 2)
    fall = 1.0 - strength * numpy.clip(
        numpy.sqrt(dx * dx + dy * dy) - VIGNETTE_FLAT, 0, 1
    )
    pixels = numpy.asarray(image.convert("RGB")).astype(numpy.float32)
    return Image.fromarray(
        numpy.clip(pixels * fall[:, :, None], 0, 255).astype(numpy.uint8), "RGB"
    )


def compose_still(
    out_dir: Path, side: int = STILL_SIDE, moment: float = STILL_MOMENT
) -> dict:
    """Run every component generator, write its layer, and write the still frame."""
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    spin = surface.spin_degrees(moment)
    pulse = surface.pulse_scale(moment)
    order = {name: index for index, name in enumerate(MARK_LAYER_ORDER)}
    canvas = Image.new("RGBA", (side, side), BACKDROP + (255,))
    paths: dict = {}
    triangles = 0
    for name, groups in sorted(
        surface.mark_layers(spin, pulse, moment), key=lambda row: order[row[0]]
    ):
        triangles += sum(len(faces) for faces, _rgb, _part, _bias in groups)
        layer = _pillow(bake_groups(groups, side))
        if name in BLOOM_LAYERS:
            layer = with_bloom(layer, STILL_BLOOM_RADIUS, STILL_BLOOM_STRENGTH)
        elif name != "reptilian eye":
            layer = with_outer_blur(layer, OUTER_BLUR_RADIUS)
        path = out_dir / f"splash-mark-layer-{name.replace(' ', '-')}.png"
        layer.save(path)
        paths[name] = path
        canvas.alpha_composite(layer)
    still = with_vignette(
        with_grade(with_grain(canvas, GRAIN_STRENGTH), GRADE_GAIN, GRADE_LIFT),
        VIGNETTE_STRENGTH,
    )
    still_path = out_dir / "splash-mark.png"
    still.save(still_path)
    paths["still"] = still_path
    return {"paths": paths, "triangles": triangles, "side": side}
