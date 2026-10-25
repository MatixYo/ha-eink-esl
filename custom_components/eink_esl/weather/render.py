"""Readable weather frame for small ESL panels (pure B/W/Y/R, large type)."""

from __future__ import annotations

import math
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from ..image.palette import BLACK, RED, WHITE, YELLOW
from .errors import WeatherError
from .fonts import load_font
from .icons import draw_condition_icon
from .models import DayForecast, WeatherSnapshot

_FALLBACK_TZ = ZoneInfo("UTC")


def render_weather_png(
    snapshot: WeatherSnapshot,
    width: int,
    height: int,
    *,
    timezone: str | None = None,
) -> bytes:
    """Render a sparse, high-contrast weather card (today + 2 days)."""
    if width < 64 or height < 64:
        raise WeatherError("Panel is too small for a weather layout")

    try:
        tz = ZoneInfo(timezone) if timezone else _FALLBACK_TZ
    except Exception:  # noqa: BLE001
        tz = _FALLBACK_TZ

    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)

    margin = max(8, min(width, height) // 20)
    split = int(height * 0.58)
    _draw_current(draw, snapshot, margin, split, width, tz)
    draw.line((margin, split, width - margin, split), fill=BLACK, width=2)
    _draw_days(
        draw,
        snapshot.days,
        margin,
        split + 6,
        width - 2 * margin,
        height - split - margin - 6,
        tz,
        today=_local_now(snapshot.observed_at, tz),
    )

    image = _snap_to_bwyr(image)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _snap_to_bwyr(image: Image.Image) -> Image.Image:
    """Map pixels to B/W/Y/R without turning gray font AA into red.

    OKLab nearest can prefer red for dark-gray antialias fringes — for near-
    achromatic pixels use luminance → black/white only.
    """
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            chroma = max(r, g, b) - min(r, g, b)
            if chroma < 40:
                # Gray / AA fringe → B or W only.
                pixels[x, y] = BLACK if (r + g + b) < 400 else WHITE
                continue
            # Chromatic: pick among the four pigments by squared RGB distance.
            best = WHITE
            best_dist = 1 << 30
            for swatch in (BLACK, WHITE, YELLOW, RED):
                dr = r - swatch[0]
                dg = g - swatch[1]
                db = b - swatch[2]
                dist = dr * dr + dg * dg + db * db
                if dist < best_dist:
                    best_dist = dist
                    best = swatch
            pixels[x, y] = best
    return image


def _draw_current(
    draw: ImageDraw.ImageDraw,
    snapshot: WeatherSnapshot,
    margin: int,
    top_h: int,
    width: int,
    tz: ZoneInfo,
) -> None:
    date = _local_now(snapshot.observed_at, tz)
    date_font = load_font(15)
    temp_font = load_font(58, bold=True)
    meta_font = load_font(14)

    date_line = (
        date.strftime("%a %-d %b")
        if _supports_minus_fmt()
        else date.strftime("%a %d %b")
    )
    draw.text((margin, margin - 2), date_line, fill=BLACK, font=date_font)
    draw.text(
        (margin, margin + 14),
        _format_temp(snapshot.temperature),
        fill=BLACK,
        font=temp_font,
    )

    parts: list[str] = []
    if snapshot.dew_point is not None:
        parts.append(f"dew {_format_temp(snapshot.dew_point)}")
    if snapshot.humidity is not None:
        parts.append(f"{int(round(snapshot.humidity))}%")
    if snapshot.wind_speed is not None:
        parts.append(
            f"{_format_number(snapshot.wind_speed)} {snapshot.wind_speed_unit}"
        )
    meta_y = top_h - 24
    if snapshot.wind_bearing is not None:
        _draw_wind_arrow(draw, margin + 10, meta_y + 8, snapshot.wind_bearing, 9)
    if parts:
        draw.text(
            (margin + 24, meta_y),
            "  ·  ".join(parts),
            fill=BLACK,
            font=meta_font,
        )

    # Icon only on the right — no condition word (was colliding with the rule).
    icon_size = min(64, top_h - margin * 2 - 4)
    icon_cx = width - margin - icon_size // 2 - 2
    icon_cy = margin + 4 + icon_size // 2
    draw_condition_icon(draw, snapshot.condition, icon_cx, icon_cy, icon_size)


def _draw_days(
    draw: ImageDraw.ImageDraw,
    days: tuple[DayForecast, ...],
    x0: int,
    y0: int,
    strip_w: int,
    strip_h: int,
    tz: ZoneInfo,
    *,
    today: datetime,
) -> None:
    if not days:
        font = load_font(14)
        draw.text((x0, y0 + strip_h // 3), "No forecast", fill=BLACK, font=font)
        return

    columns = min(3, len(days))
    col_w = strip_w // columns
    label_font = load_font(14, bold=True)
    temp_font = load_font(18, bold=True)
    small_font = load_font(12)

    for index in range(columns):
        day = days[index]
        left = x0 + col_w * index
        cx = left + col_w // 2
        if index > 0:
            draw.line((left, y0 + 2, left, y0 + strip_h - 2), fill=BLACK, width=1)

        label = _day_label(day.when, tz, today)
        lw = draw.textlength(label, font=label_font)
        draw.text((cx - lw / 2, y0), label, fill=BLACK, font=label_font)

        # Compact stack: label → icon → hi/lo → optional precip (no wind clutter).
        icon_size = min(24, col_w - 24)
        icon_y = y0 + 16 + icon_size // 2
        draw_condition_icon(draw, day.condition, cx, icon_y, icon_size)

        high = _format_temp_short(day.temperature)
        low = _format_temp_short(day.templow)
        temps = f"{high}/{low}" if high and low else (high or low or "—")
        tw = draw.textlength(temps, font=temp_font)
        temps_y = min(icon_y + icon_size // 2 + 2, y0 + strip_h - 28)
        draw.text((cx - tw / 2, temps_y), temps, fill=BLACK, font=temp_font)

        if day.precipitation is not None and day.precipitation >= 0.5:
            detail = f"{_format_number(day.precipitation)}mm"
            dw = draw.textlength(detail, font=small_font)
            detail_y = temps_y + 18
            if detail_y + 12 <= y0 + strip_h:
                draw.text(
                    (cx - dw / 2, detail_y), detail, fill=RED, font=small_font
                )


def _draw_wind_arrow(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    bearing: float | str | None,
    radius: int,
) -> None:
    degrees = _bearing_degrees(bearing)
    if degrees is None:
        return
    radians = math.radians(degrees + 180.0)
    tip_x = cx + radius * math.sin(radians)
    tip_y = cy - radius * math.cos(radians)
    tail_x = cx - radius * 0.7 * math.sin(radians)
    tail_y = cy + radius * 0.7 * math.cos(radians)
    width = max(2, radius // 3)
    draw.line((tail_x, tail_y, tip_x, tip_y), fill=BLACK, width=width)
    head = max(4, radius // 2)
    for angle in (radians + math.radians(145), radians - math.radians(145)):
        draw.line(
            (
                tip_x,
                tip_y,
                tip_x + head * math.sin(angle),
                tip_y - head * math.cos(angle),
            ),
            fill=BLACK,
            width=width,
        )


def _bearing_degrees(bearing: float | str | None) -> float | None:
    if bearing is None:
        return None
    if isinstance(bearing, (int, float)):
        return float(bearing) % 360.0
    text = str(bearing).strip().upper()
    compass = {
        "N": 0,
        "NNE": 22.5,
        "NE": 45,
        "ENE": 67.5,
        "E": 90,
        "ESE": 112.5,
        "SE": 135,
        "SSE": 157.5,
        "S": 180,
        "SSW": 202.5,
        "SW": 225,
        "WSW": 247.5,
        "W": 270,
        "WNW": 292.5,
        "NW": 315,
        "NNW": 337.5,
    }
    if text in compass:
        return compass[text]
    try:
        return float(text) % 360.0
    except ValueError:
        return None


def _day_label(when: datetime | None, tz: ZoneInfo, today: datetime) -> str:
    local = _as_local(when, tz)
    if local is None:
        return "—"
    if local.date() == today.date():
        return "Today"
    return local.strftime("%a")


def _format_temp(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{int(round(value))}°"


def _format_temp_short(value: float | None) -> str | None:
    if value is None:
        return None
    return str(int(round(value)))


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.0f}" if abs(value) >= 10 else f"{value:.1f}"


def _as_local(when: datetime | None, tz: ZoneInfo) -> datetime | None:
    if when is None:
        return None
    return when.astimezone(tz) if when.tzinfo else when.replace(tzinfo=tz)


def _local_now(observed: datetime | None, tz: ZoneInfo) -> datetime:
    if observed is not None:
        return (
            observed.astimezone(tz)
            if observed.tzinfo
            else observed.replace(tzinfo=tz)
        )
    return datetime.now(tz)


def _supports_minus_fmt() -> bool:
    try:
        datetime(2026, 1, 5).strftime("%-d")
        return True
    except ValueError:
        return False
