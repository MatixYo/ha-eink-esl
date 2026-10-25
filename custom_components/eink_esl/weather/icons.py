"""Geometric weather icons drawn with exact B/W/Y/R pigments."""

from __future__ import annotations

from PIL import ImageDraw

from ..image.palette import BLACK, RED, WHITE, YELLOW

Rgb = tuple[int, int, int]


def draw_condition_icon(
    draw: ImageDraw.ImageDraw,
    condition: str | None,
    cx: int,
    cy: int,
    size: int,
) -> None:
    """Draw a condition glyph centered at ``(cx, cy)`` with diameter ``size``."""
    key = (condition or "exceptional").lower().replace("_", "-")
    r = max(4, size // 2)

    if key in ("sunny",):
        _sun(draw, cx, cy, r, YELLOW)
    elif key in ("clear-night",):
        _moon(draw, cx, cy, r, YELLOW)
    elif key in ("partlycloudy",):
        _sun(draw, cx - r // 3, cy - r // 4, int(r * 0.7), YELLOW)
        _cloud(draw, cx + r // 8, cy + r // 5, int(r * 0.85), BLACK)
    elif key in ("cloudy", "windy-variant"):
        _cloud(draw, cx, cy, r, BLACK)
    elif key in ("fog",):
        _fog(draw, cx, cy, r, BLACK)
    elif key in ("rainy", "pouring"):
        _cloud(draw, cx, cy - r // 5, int(r * 0.85), BLACK)
        _rain(draw, cx, cy + r // 3, r, RED if key == "pouring" else BLACK)
    elif key in ("snowy", "snowy-rainy"):
        _cloud(draw, cx, cy - r // 5, int(r * 0.85), BLACK)
        _snow(draw, cx, cy + r // 3, r, BLACK)
        if key == "snowy-rainy":
            _rain(draw, cx - r // 3, cy + r // 4, int(r * 0.7), RED)
    elif key in ("lightning", "lightning-rainy"):
        _cloud(draw, cx, cy - r // 4, int(r * 0.85), BLACK)
        _bolt(draw, cx, cy + r // 5, r, RED)
        if key == "lightning-rainy":
            _rain(draw, cx + r // 3, cy + r // 3, int(r * 0.6), BLACK)
    elif key in ("hail",):
        _cloud(draw, cx, cy - r // 5, int(r * 0.85), BLACK)
        _hail(draw, cx, cy + r // 3, r, RED)
    elif key in ("windy",):
        _wind(draw, cx, cy, r, BLACK)
    else:
        # exceptional / unknown
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r), outline=RED, width=max(2, r // 8)
        )
        draw.rectangle(
            (cx - max(1, r // 10), cy - r // 2, cx + max(1, r // 10), cy + r // 8),
            fill=RED,
        )
        draw.ellipse(
            (cx - max(1, r // 8), cy + r // 3, cx + max(1, r // 8), cy + r // 2),
            fill=RED,
        )


def _sun(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    # Short rays for e-ink readability.
    ray = max(2, r // 5)
    for dx, dy in (
        (0, -1),
        (0, 1),
        (-1, 0),
        (1, 0),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    ):
        x0 = cx + int(dx * (r + 2))
        y0 = cy + int(dy * (r + 2))
        x1 = cx + int(dx * (r + 2 + ray))
        y1 = cy + int(dy * (r + 2 + ray))
        draw.line((x0, y0, x1, y1), fill=color, width=max(2, r // 8))


def _moon(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    # Cut a white circle to form a crescent (panel background is white).
    ox = cx + r // 3
    draw.ellipse((ox - r, cy - r, ox + r, cy + r), fill=WHITE)


def _cloud(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    # Three overlapping circles + a base bar — reads at small sizes.
    draw.ellipse(
        (cx - r, cy - r // 3, cx - r // 4, cy + r // 2), fill=color
    )
    draw.ellipse(
        (cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 3), fill=color
    )
    draw.ellipse(
        (cx + r // 6, cy - r // 4, cx + r, cy + r // 2), fill=color
    )
    draw.rectangle(
        (cx - r + 2, cy + r // 8, cx + r - 2, cy + r // 2), fill=color
    )


def _rain(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    length = max(4, r // 2)
    for offset in (-r // 2, -r // 6, r // 5):
        draw.line(
            (cx + offset, cy, cx + offset - length // 4, cy + length),
            fill=color,
            width=max(2, r // 6),
        )


def _snow(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    for offset in (-r // 2, 0, r // 3):
        x = cx + offset
        y = cy + (offset % 3)
        s = max(2, r // 8)
        draw.line((x - s, y, x + s, y), fill=color, width=2)
        draw.line((x, y - s, x, y + s), fill=color, width=2)


def _hail(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    for offset in (-r // 2, 0, r // 3):
        x = cx + offset
        y = cy
        s = max(2, r // 7)
        draw.polygon([(x, y - s), (x + s, y + s), (x - s, y + s)], fill=color)


def _bolt(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    s = max(6, r)
    points = [
        (cx - s // 6, cy - s // 2),
        (cx + s // 4, cy - s // 2),
        (cx - s // 12, cy - s // 12),
        (cx + s // 3, cy - s // 12),
        (cx - s // 5, cy + s // 2),
        (cx, cy + s // 12),
        (cx - s // 3, cy + s // 12),
    ]
    draw.polygon(points, fill=color)


def _fog(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    for i, y_off in enumerate((-r // 2, -r // 8, r // 4)):
        inset = (i % 2) * (r // 5)
        draw.line(
            (cx - r + inset, cy + y_off, cx + r - inset, cy + y_off),
            fill=color,
            width=max(2, r // 8),
        )


def _wind(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Rgb
) -> None:
    for i, y_off in enumerate((-r // 3, 0, r // 3)):
        start = cx - r + (i * r // 8)
        draw.arc(
            (start, cy + y_off - r // 4, start + r, cy + y_off + r // 4),
            start=200,
            end=340,
            fill=color,
            width=max(2, r // 8),
        )
