"""Compose a readable mini-meteorogram for ESL panels (Pillow + BWYR dither)."""

from __future__ import annotations

import math
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from ..image.palette import BLACK, RED, WHITE, quantize
from .errors import WeatherError
from .fonts import load_font
from .icons import draw_condition_icon
from .models import DayForecast, HourlyForecast, WeatherSnapshot

_FALLBACK_TZ = ZoneInfo("UTC")
# Near-white gray for hairlines only — OKLab nearest stays B/W under dither.
# Body ink is pure black so text does not speck into yellow/red.
_INK = BLACK
_MUTED = (55, 55, 55)
_RULE = (200, 200, 200)


def render_weather_png(
    snapshot: WeatherSnapshot,
    width: int,
    height: int,
    *,
    timezone: str | None = None,
) -> bytes:
    """Render a mini-meteorogram (current + hourly spark + 3–4 days)."""
    if width < 64 or height < 64:
        raise WeatherError("Panel is too small for a weather layout")

    try:
        tz = ZoneInfo(timezone) if timezone else _FALLBACK_TZ
    except Exception:  # noqa: BLE001
        tz = _FALLBACK_TZ

    # Draw at 2× then downscale — TrueType AA survives better before dither.
    scale = 2 if width <= 500 else 1
    canvas_w = width * scale
    canvas_h = height * scale
    image = Image.new("RGB", (canvas_w, canvas_h), WHITE)
    draw = ImageDraw.Draw(image)

    margin = max(8, min(canvas_w, canvas_h) // 24)
    # Fixed bands keep the wind block out of the hourly spark.
    header_h = int(canvas_h * 0.36)
    day_h = int(canvas_h * 0.34)
    spark_h = canvas_h - header_h - day_h

    _draw_header(draw, snapshot, margin, header_h, canvas_w, tz, scale)
    y_spark = header_h
    _hairline(draw, margin, y_spark, canvas_w - margin)
    if spark_h >= 24 * scale and snapshot.hours:
        _draw_hourly_spark(
            draw,
            snapshot.hours,
            margin,
            y_spark + 2 * scale,
            canvas_w - 2 * margin,
            max(8, spark_h - 4 * scale),
            tz,
            scale,
        )
    y_days = header_h + spark_h
    _hairline(draw, margin, y_days, canvas_w - margin)
    _draw_day_columns(
        draw,
        snapshot.days,
        margin,
        y_days + 3 * scale,
        canvas_w - 2 * margin,
        max(8, day_h - margin),
        tz,
        scale,
        today=_local_now(snapshot.observed_at, tz),
    )

    if scale > 1:
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    image = _dither_to_bwyr(image)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _dither_to_bwyr(image: Image.Image) -> Image.Image:
    """Map to panel pigments after 2× downscale.

    Nearest (not Floyd–Steinberg): FS error from red precip bars bled into the
    temp polyline. Softness comes from LANCZOS downscale of AA glyphs instead.
    """
    width, height = image.size
    rgba = image.convert("RGBA").tobytes()
    quantized = quantize(rgba, width, height, "nearest", "bwry")
    return Image.frombytes("RGBA", (width, height), quantized.preview_rgba).convert(
        "RGB"
    )


def _hairline(
    draw: ImageDraw.ImageDraw, x0: int, y: int, x1: int
) -> None:
    draw.line((x0, y, x1, y), fill=_RULE, width=1)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    snapshot: WeatherSnapshot,
    margin: int,
    header_h: int,
    width: int,
    tz: ZoneInfo,
    scale: int,
) -> None:
    date = _local_now(snapshot.observed_at, tz)
    date_font = load_font(max(12, 8 * scale))
    temp_font = load_font(max(40, 24 * scale), bold=True)
    meta_font = load_font(max(12, 8 * scale))

    date_line = (
        date.strftime("%a %-d %b")
        if _supports_minus_fmt()
        else date.strftime("%a %d %b")
    )
    draw.text((margin, margin // 2), date_line, fill=_MUTED, font=date_font)

    temp = _format_temp(snapshot.temperature)
    draw.text((margin, margin // 2 + 14 * scale), temp, fill=_INK, font=temp_font)

    # Dew · humidity under the big number.
    meta_bits: list[str] = []
    if snapshot.dew_point is not None:
        meta_bits.append(f"dew {_format_temp(snapshot.dew_point)}")
    if snapshot.humidity is not None:
        meta_bits.append(f"{int(round(snapshot.humidity))}%")
    if snapshot.pressure is not None:
        meta_bits.append(
            f"{_format_number(snapshot.pressure)} {snapshot.pressure_unit}"
        )
    if meta_bits:
        draw.text(
            (margin, header_h - 16 * scale),
            "  ·  ".join(meta_bits),
            fill=_MUTED,
            font=meta_font,
        )

    # Wind block — kept inside the header band.
    wind_cx = width * 55 // 100
    wind_cy = margin + 22 * scale
    _draw_wind_arrow(
        draw,
        wind_cx,
        wind_cy,
        snapshot.wind_bearing,
        radius=max(12, 9 * scale),
    )
    if snapshot.wind_speed is not None:
        wind_txt = (
            f"{_format_number(snapshot.wind_speed)} {snapshot.wind_speed_unit}"
        )
        tw = draw.textlength(wind_txt, font=meta_font)
        draw.text(
            (wind_cx - tw / 2, wind_cy + 14 * scale),
            wind_txt,
            fill=_INK,
            font=meta_font,
        )

    # Condition + cloud marks (far right).
    icon_size = max(26, 16 * scale)
    icon_cx = width - margin - icon_size // 2 - 2
    icon_cy = margin + icon_size // 2 + 2 * scale
    draw_condition_icon(draw, snapshot.condition, icon_cx, icon_cy, icon_size)
    marks_y = min(
        header_h - 10 * scale,
        icon_cy + icon_size // 2 + 6 * scale,
    )
    _draw_cloud_marks(draw, icon_cx, marks_y, snapshot.cloud_coverage, scale)


def _draw_hourly_spark(
    draw: ImageDraw.ImageDraw,
    hours: tuple[HourlyForecast, ...],
    x0: int,
    y0: int,
    strip_w: int,
    strip_h: int,
    tz: ZoneInfo,
    scale: int,
) -> None:
    """Temp polyline + precip bars + sparse wind ticks (next ~18–24 h)."""
    rows = list(hours[:24])
    if len(rows) < 2:
        return

    label_font = load_font(max(9, 6 * scale))
    chart_top = y0 + 10 * scale
    chart_bottom = y0 + strip_h - 2 * scale
    chart_h = max(8, chart_bottom - chart_top)

    temps = [h.temperature for h in rows if h.temperature is not None]
    precip = [h.precipitation or 0.0 for h in rows]
    if not temps:
        return
    t_min = min(temps)
    t_max = max(temps)
    if abs(t_max - t_min) < 0.5:
        t_max = t_min + 1.0
    p_max = max(precip) if precip else 0.0
    p_max = max(p_max, 1.0)

    n = len(rows)
    step = strip_w / max(1, n - 1)

    # Precip bars (behind temp line) — red when wet.
    bar_w = max(1, int(step * 0.45))
    for index, hour in enumerate(rows):
        amount = hour.precipitation or 0.0
        if amount <= 0.05:
            continue
        x = int(x0 + index * step)
        bar_h = int((amount / p_max) * (chart_h * 0.55))
        fill = RED if amount >= 0.4 else _MUTED
        draw.rectangle(
            (
                x - bar_w // 2,
                chart_bottom - bar_h,
                x + bar_w // 2,
                chart_bottom,
            ),
            fill=fill,
        )

    # Temperature polyline.
    points: list[tuple[float, float]] = []
    for index, hour in enumerate(rows):
        if hour.temperature is None:
            continue
        x = x0 + index * step
        norm = (hour.temperature - t_min) / (t_max - t_min)
        y = chart_bottom - norm * (chart_h * 0.85) - chart_h * 0.05
        points.append((x, y))
    if len(points) >= 2:
        draw.line(points, fill=_INK, width=max(1, scale))

    # Hour labels + wind ticks every 3 hours.
    for index, hour in enumerate(rows):
        if index % 3 != 0:
            continue
        x = int(x0 + index * step)
        local = _as_local(hour.when, tz)
        label = local.strftime("%H") if local else ""
        if label:
            lw = draw.textlength(label, font=label_font)
            draw.text(
                (x - lw / 2, y0),
                label,
                fill=_MUTED,
                font=label_font,
            )
        if hour.wind_bearing is not None:
            _draw_wind_arrow(
                draw,
                x,
                chart_top + 4 * scale,
                hour.wind_bearing,
                radius=max(5, 4 * scale),
                color=_MUTED,
            )


def _draw_day_columns(
    draw: ImageDraw.ImageDraw,
    days: tuple[DayForecast, ...],
    x0: int,
    y0: int,
    strip_w: int,
    strip_h: int,
    tz: ZoneInfo,
    scale: int,
    *,
    today: datetime,
) -> None:
    if not days:
        font = load_font(max(10, 7 * scale))
        draw.text((x0, y0 + strip_h // 3), "No forecast", fill=_MUTED, font=font)
        return

    columns = min(4, len(days))
    col_w = strip_w // columns
    label_font = load_font(max(10, 7 * scale))
    temp_font = load_font(max(12, 8 * scale))
    small_font = load_font(max(9, 6 * scale))

    for index in range(columns):
        day = days[index]
        left = x0 + col_w * index
        cx = left + col_w // 2
        if index > 0:
            draw.line(
                (left, y0 + 2 * scale, left, y0 + strip_h - 2 * scale),
                fill=_RULE,
                width=1,
            )

        label = _day_label(day.when, tz, today)
        lw = draw.textlength(label, font=label_font)
        draw.text((cx - lw / 2, y0), label, fill=_INK, font=label_font)

        icon_size = max(16, min(col_w // 3, 14 * scale))
        icon_y = y0 + 14 * scale + icon_size // 2
        draw_condition_icon(draw, day.condition, cx, icon_y, icon_size)

        high = _format_temp_short(day.temperature)
        low = _format_temp_short(day.templow)
        temps = f"{high}/{low}" if high and low else (high or low or "—")
        tw = draw.textlength(temps, font=temp_font)
        temps_y = icon_y + icon_size // 2 + 3 * scale
        draw.text((cx - tw / 2, temps_y), temps, fill=_INK, font=temp_font)

        # Precip + wind on one quiet line.
        bits: list[str] = []
        if day.precipitation is not None and day.precipitation >= 0.1:
            bits.append(f"{_format_number(day.precipitation)} mm")
        if day.wind_speed is not None:
            bits.append(f"{_format_number(day.wind_speed)}")
        detail = " · ".join(bits)
        detail_y = y0 + strip_h - 12 * scale
        if detail:
            fill = RED if _is_wet(day) else _MUTED
            dw = draw.textlength(detail, font=small_font)
            text_x = cx - dw / 2
            if day.wind_bearing is not None:
                _draw_wind_arrow(
                    draw,
                    int(text_x - 8 * scale),
                    int(detail_y + 5 * scale),
                    day.wind_bearing,
                    radius=max(4, 3 * scale),
                    color=_MUTED,
                )
            draw.text((text_x, detail_y), detail, fill=fill, font=small_font)


def _draw_wind_arrow(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    bearing: float | str | None,
    *,
    radius: int,
    color: tuple[int, int, int] = _INK,
) -> None:
    """Arrow tip points where the wind blows (HA bearing is meteorological from)."""
    degrees = _bearing_degrees(bearing)
    if degrees is None:
        return
    # From → to
    radians = math.radians(degrees + 180.0)
    tip_x = cx + radius * math.sin(radians)
    tip_y = cy - radius * math.cos(radians)
    tail_x = cx - radius * 0.65 * math.sin(radians)
    tail_y = cy + radius * 0.65 * math.cos(radians)
    draw.line((tail_x, tail_y, tip_x, tip_y), fill=color, width=max(1, radius // 7))

    # Small chevron head.
    left = radians + math.radians(150)
    right = radians - math.radians(150)
    head = max(3, radius // 2)
    draw.line(
        (
            tip_x,
            tip_y,
            tip_x + head * math.sin(left),
            tip_y - head * math.cos(left),
        ),
        fill=color,
        width=max(1, radius // 8),
    )
    draw.line(
        (
            tip_x,
            tip_y,
            tip_x + head * math.sin(right),
            tip_y - head * math.cos(right),
        ),
        fill=color,
        width=max(1, radius // 8),
    )


def _draw_cloud_marks(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    coverage: float | None,
    scale: int,
) -> None:
    """Four light dots/rings — not oktas, just a cloudiness hint."""
    if coverage is None:
        return
    filled = int(round(max(0.0, min(100.0, coverage)) / 25.0))
    r = max(2, 2 * scale)
    gap = r * 3
    start = cx - int(1.5 * gap)
    for index in range(4):
        x = start + index * gap
        box = (x - r, cy - r, x + r, cy + r)
        if index < filled:
            draw.ellipse(box, fill=_MUTED)
        else:
            draw.ellipse(box, outline=_RULE, width=1)


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


def _is_wet(day: DayForecast) -> bool:
    if day.condition in (
        "rainy",
        "pouring",
        "lightning-rainy",
        "snowy-rainy",
        "hail",
    ):
        return True
    return bool(day.precipitation is not None and day.precipitation >= 1.0)


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
        return observed.astimezone(tz) if observed.tzinfo else observed.replace(tzinfo=tz)
    return datetime.now(tz)


def _supports_minus_fmt() -> bool:
    try:
        datetime(2026, 1, 5).strftime("%-d")
        return True
    except ValueError:
        return False
