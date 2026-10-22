"""Compose a BWYR weather frame for an ESL panel (Pillow)."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from ..image.palette import BLACK, RED, WHITE, YELLOW
from .errors import WeatherError
from .fonts import load_font
from .icons import draw_condition_icon
from .models import DayForecast, WeatherSnapshot

# Prefer local wall clock for weekday labels when HA timezone is unknown.
_FALLBACK_TZ = ZoneInfo("UTC")


def render_weather_png(
    snapshot: WeatherSnapshot,
    width: int,
    height: int,
    *,
    timezone: str | None = None,
) -> bytes:
    """Render ``snapshot`` to a panel-sized RGB PNG using only B/W/Y/R."""
    if width < 64 or height < 64:
        raise WeatherError("Panel is too small for a weather layout")

    try:
        tz = ZoneInfo(timezone) if timezone else _FALLBACK_TZ
    except Exception:  # noqa: BLE001
        tz = _FALLBACK_TZ

    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)

    margin = max(6, min(width, height) // 28)
    strip_h = max(48, height // 3)
    top_h = height - strip_h - margin

    _draw_current(draw, snapshot, margin, top_h, width, tz)
    _draw_day_strip(
        draw,
        snapshot.days,
        margin,
        height - strip_h,
        width - 2 * margin,
        strip_h - margin,
        tz,
    )

    # Hairline separator — black only, 1px.
    y_sep = height - strip_h
    draw.line((margin, y_sep, width - margin, y_sep), fill=BLACK, width=1)

    # TrueType glyphs antialias to gray — snap every pixel to a panel pigment.
    image = _snap_to_bwyr(image)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


_PALETTE = (BLACK, WHITE, YELLOW, RED)


def _snap_to_bwyr(image: Image.Image) -> Image.Image:
    """Map each RGB pixel to the nearest of black / white / yellow / red."""
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            pixel = pixels[x, y]
            if pixel in _PALETTE:
                continue
            best = WHITE
            best_dist = 1 << 30
            pr, pg, pb = pixel[0], pixel[1], pixel[2]
            for swatch in _PALETTE:
                dr = pr - swatch[0]
                dg = pg - swatch[1]
                db = pb - swatch[2]
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
    icon_size = min(top_h - margin * 2, width // 4, 96)
    icon_cx = width - margin - icon_size // 2 - 4
    icon_cy = margin + icon_size // 2 + 4
    draw_condition_icon(
        draw, snapshot.condition, icon_cx, icon_cy, icon_size
    )

    text_right = icon_cx - icon_size // 2 - margin
    date = _local_now(snapshot.observed_at, tz)
    weekday = date.strftime("%a")
    date_line = date.strftime("%-d %b") if _supports_minus_fmt() else date.strftime("%d %b")

    title_font = load_font(max(12, top_h // 8))
    temp_font = load_font(max(28, top_h // 2), bold=True)
    meta_font = load_font(max(10, top_h // 10))
    cond_font = load_font(max(11, top_h // 9))

    draw.text((margin, margin), f"{weekday}  {date_line}", fill=BLACK, font=title_font)

    temp_text = _format_temp(snapshot.temperature, snapshot.temperature_unit)
    draw.text((margin, margin + top_h // 5), temp_text, fill=BLACK, font=temp_font)

    cond = _condition_label(snapshot.condition)
    # Mild accent: yellow underline for clear/sunny.
    cond_y = margin + int(top_h * 0.62)
    draw.text((margin, cond_y), cond, fill=BLACK, font=cond_font)
    if snapshot.condition in ("sunny", "clear-night"):
        bbox = draw.textbbox((margin, cond_y), cond, font=cond_font)
        draw.line(
            (bbox[0], bbox[3] + 2, bbox[2], bbox[3] + 2),
            fill=YELLOW,
            width=2,
        )

    meta_parts: list[str] = []
    if snapshot.humidity is not None:
        meta_parts.append(f"{int(round(snapshot.humidity))}%")
    if snapshot.wind_speed is not None:
        meta_parts.append(
            f"{_format_number(snapshot.wind_speed)} {snapshot.wind_speed_unit}"
        )
    if snapshot.pressure is not None:
        meta_parts.append(
            f"{_format_number(snapshot.pressure)} {snapshot.pressure_unit}"
        )
    if meta_parts:
        meta = "  ·  ".join(meta_parts)
        # Keep meta from colliding with the icon.
        max_w = max(40, text_right - margin)
        while meta and draw.textlength(meta, font=meta_font) > max_w:
            meta = meta[:-4] + "…"
            if len(meta) < 8:
                break
        meta_size = int(getattr(meta_font, "size", 11))
        draw.text(
            (margin, top_h - margin - meta_size - 2),
            meta,
            fill=BLACK,
            font=meta_font,
        )


def _draw_day_strip(
    draw: ImageDraw.ImageDraw,
    days: tuple[DayForecast, ...],
    x0: int,
    y0: int,
    strip_w: int,
    strip_h: int,
    tz: ZoneInfo,
) -> None:
    if not days:
        font = load_font(max(10, strip_h // 4))
        draw.text((x0, y0 + strip_h // 3), "No forecast", fill=BLACK, font=font)
        return

    columns = min(5, len(days))
    col_w = strip_w // columns
    label_font = load_font(max(9, strip_h // 5))
    temp_font = load_font(max(10, strip_h // 4), bold=True)

    for index in range(columns):
        day = days[index]
        cx = x0 + col_w * index + col_w // 2
        label = _weekday_short(day.when, tz)
        label_w = draw.textlength(label, font=label_font)
        draw.text(
            (cx - label_w / 2, y0 + 4),
            label,
            fill=BLACK,
            font=label_font,
        )

        label_size = int(getattr(label_font, "size", 10))
        temp_size = int(getattr(temp_font, "size", 11))
        # Reserve room for weekday + temps (+ optional rain tick); keep icons inside.
        temp_top = y0 + strip_h - temp_size - 6
        icon_top = y0 + 4 + label_size + 2
        icon_budget = max(12, temp_top - icon_top - 2)
        icon_size = min(col_w - 4, icon_budget)
        # Sun rays extend ~r/5 past the disc — leave a little headroom.
        icon_size = max(12, int(icon_size * 0.82))
        draw_condition_icon(
            draw,
            day.condition,
            cx,
            icon_top + icon_size // 2,
            icon_size,
        )

        high = _format_temp_short(day.temperature)
        low = _format_temp_short(day.templow)
        if high and low:
            temps = f"{high}/{low}"
        else:
            temps = high or low or "—"

        # Rainy days: red temperature text as a quiet alert.
        fill = RED if _is_wet(day) else BLACK
        temps_w = draw.textlength(temps, font=temp_font)
        draw.text(
            (cx - temps_w / 2, temp_top),
            temps,
            fill=fill,
            font=temp_font,
        )

        if day.precipitation is not None and day.precipitation >= 0.5:
            # Tiny red tick under the column for measurable rain.
            draw.rectangle(
                (cx - 6, y0 + strip_h - 2, cx + 6, y0 + strip_h),
                fill=RED,
            )


def _is_wet(day: DayForecast) -> bool:
    if day.condition in ("rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail"):
        return True
    return bool(day.precipitation is not None and day.precipitation >= 1.0)


def _condition_label(condition: str | None) -> str:
    if not condition:
        return "—"
    return condition.replace("-", " ").replace("_", " ")


def _format_temp(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    unit_suffix = unit if unit.startswith("°") else f"°{unit}".replace("°°", "°")
    # Compact: "8°" when unit is °C / °F.
    if "C" in unit.upper() or "F" in unit.upper():
        return f"{int(round(value))}°"
    return f"{int(round(value))}{unit_suffix}"


def _format_temp_short(value: float | None) -> str | None:
    if value is None:
        return None
    return str(int(round(value)))


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.0f}" if abs(value) >= 10 else f"{value:.1f}"


def _weekday_short(when: datetime | None, tz: ZoneInfo) -> str:
    if when is None:
        return "—"
    local = when.astimezone(tz) if when.tzinfo else when.replace(tzinfo=tz)
    return local.strftime("%a")


def _local_now(observed: datetime | None, tz: ZoneInfo) -> datetime:
    if observed is not None:
        return observed.astimezone(tz) if observed.tzinfo else observed.replace(tzinfo=tz)
    return datetime.now(tz)


def _supports_minus_fmt() -> bool:
    """``%-d`` is POSIX-only; Windows uses ``%#d`` — avoid crashes in CI."""
    try:
        datetime(2026, 1, 5).strftime("%-d")
        return True
    except ValueError:
        return False
