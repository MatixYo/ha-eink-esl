"""Mini-meteorogram for ESL panels (PL/EN).

E-ink readability rules applied here:
- Max contrast: black data on white; red only for accents/labels/precip.
- No dither behind text — AA fringes snap hard to B/W (Bayer noise kills glyphs
  at 384×184). Yellow is reserved for sun / rare fills, not chart backgrounds.
- Line art + solid bars beat soft gradients (pigment, not light).
- Edge-to-edge day strip; chart columns share the same dividers.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from ..image.palette import BLACK, RED, WHITE, YELLOW
from .errors import WeatherError
from .fonts import load_font
from .i18n import (
    WeatherLang,
    compass_label,
    condition_label,
    dew_label,
    gust_label,
    humidity_label,
    today_label,
    weekday_short,
    wind_label,
)
from .icons import draw_condition_icon
from .models import DayForecast, HourlyForecast, WeatherSnapshot

_FALLBACK_TZ = ZoneInfo("UTC")
_DAY_COLUMNS = 3


def render_weather_png(
    snapshot: WeatherSnapshot,
    width: int,
    height: int,
    *,
    timezone: str | None = None,
    language: WeatherLang = "pl",
) -> bytes:
    """Render current + 3-day precip/temp chart aligned with day cards."""
    if width < 64 or height < 64:
        raise WeatherError("Panel is too small for a weather layout")

    try:
        tz = ZoneInfo(timezone) if timezone else _FALLBACK_TZ
    except Exception:  # noqa: BLE001
        tz = _FALLBACK_TZ

    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)

    pad = max(4, min(width, height) // 40)
    header_h = max(78, min(86, int(height * 0.44)))
    days_h = max(44, int(height * 0.26))
    spark_h = max(36, height - header_h - days_h)
    if header_h + days_h + spark_h > height:
        spark_h = max(30, height - header_h - days_h)

    now = _local_now(snapshot.observed_at, tz)
    days = tuple(snapshot.days[:_DAY_COLUMNS])
    day_dates = _day_dates(days, tz, now)

    _draw_header(draw, snapshot, pad, header_h, width, now, language)

    y_spark = header_h
    # Thin yellow accent above the chart (small dose of warm pigment).
    draw.line((0, y_spark - 1, width - 1, y_spark - 1), fill=YELLOW, width=1)
    draw.line((0, y_spark, width - 1, y_spark), fill=BLACK, width=1)
    if spark_h >= 30 and snapshot.hours and day_dates:
        _draw_multiday_chart(
            draw,
            snapshot.hours,
            day_dates,
            0,
            y_spark + 1,
            width,
            spark_h - 1,
            tz,
        )

    y_days = header_h + spark_h
    draw.line((0, y_days, width - 1, y_days), fill=BLACK, width=1)
    _draw_days(
        draw,
        days,
        day_dates,
        0,
        y_days + 1,
        width,
        days_h - 1,
        tz,
        now,
        language,
    )

    image = _snap_to_bwyr_sharp(image)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _snap_to_bwyr_sharp(image: Image.Image) -> Image.Image:
    """Hard nearest-pigment snap. Grays → B/W only (keeps glyphs crisp)."""
    palette = (BLACK, WHITE, YELLOW, RED)
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            if max(r, g, b) - min(r, g, b) < 40:
                pixels[x, y] = BLACK if (r + g + b) < 382 else WHITE
                continue
            best = WHITE
            best_dist = 1 << 30
            for swatch in palette:
                dr = r - swatch[0]
                dg = g - swatch[1]
                db = b - swatch[2]
                dist = dr * dr + dg * dg + db * db
                if dist < best_dist:
                    best_dist = dist
                    best = swatch
            pixels[x, y] = best
    return image


def _fill_orange(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
) -> None:
    """Perceptual orange via 50/50 red–yellow checker (no native orange pigment)."""
    x0, y0, x1, y1 = box
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            # Slightly more red than yellow → warmer orange, not pure amber.
            draw.point((x, y), fill=RED if (x + 2 * y) % 3 else YELLOW)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    snapshot: WeatherSnapshot,
    pad: int,
    header_h: int,
    width: int,
    now: datetime,
    lang: WeatherLang,
) -> None:
    title_font = load_font(13, bold=True)
    temp_font = load_font(34, bold=True)
    label_font = load_font(11, bold=True)
    value_font = load_font(13)
    wind_font = load_font(13)
    cond_font = load_font(11)

    location = (snapshot.location_name or "").strip() or snapshot.entity_id
    date_text = _format_date(now, lang)
    if len(location) > 16:
        location = location[:15] + "…"

    icon_size = min(42, header_h - 22)
    icon_cx = width - pad - icon_size // 2
    text_right = icon_cx - icon_size // 2 - 6

    header_line = _fit_text(
        draw,
        f"{location}  ·  {date_text}",
        title_font,
        max(40, text_right - pad),
    )
    draw.text((pad, 2), header_line, fill=BLACK, font=title_font)

    icon_cy = 8 + icon_size // 2
    draw_condition_icon(draw, snapshot.condition, icon_cx, icon_cy, icon_size)
    cond = condition_label(lang, snapshot.condition)
    cw = draw.textlength(cond, font=cond_font)
    cond_y = icon_cy + icon_size // 2 + 1
    if cond_y + 11 <= header_h - 2:
        draw.text(
            (icon_cx - cw / 2, cond_y),
            cond,
            fill=RED if snapshot.condition in ("rainy", "pouring", "lightning", "lightning-rainy") else BLACK,
            font=cond_font,
        )

    temp_y = 18
    temp_text = _format_temp(snapshot.temperature)
    draw.text((pad, temp_y), temp_text, fill=BLACK, font=temp_font)
    temp_w = int(draw.textlength(temp_text, font=temp_font))
    # TrueType ascent ≈ size; keep meta/wind clear of the big digits.
    temp_bottom = temp_y + 32

    # InkNode-style: red LABEL + black value (glanceable hierarchy).
    metrics_x = pad + temp_w + 8
    metrics_y = temp_y + 6
    cursor = metrics_x
    for label, value in _climate_pairs(snapshot, lang):
        if cursor >= text_right - 20:
            break
        draw.text((cursor, metrics_y), label, fill=RED, font=label_font)
        cursor += draw.textlength(label, font=label_font) + 2
        draw.text((cursor, metrics_y - 1), value, fill=BLACK, font=value_font)
        cursor += draw.textlength(value, font=value_font) + 8

    wind_y = temp_bottom + 2
    if wind_y + 14 <= header_h - 2:
        _draw_wind_row(
            draw,
            snapshot,
            lang,
            pad,
            wind_y,
            text_right,
            label_font,
            wind_font,
        )


def _climate_pairs(
    snapshot: WeatherSnapshot, lang: WeatherLang
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if snapshot.dew_point is not None:
        pairs.append((dew_label(lang).upper(), _format_temp(snapshot.dew_point)))
    if snapshot.humidity is not None:
        pairs.append(
            (humidity_label(lang).upper(), f"{int(round(snapshot.humidity))}%")
        )
    if snapshot.pressure is not None:
        pairs.append(
            ("P", f"{_format_number(snapshot.pressure)}")
        )
    return pairs


def _draw_wind_row(
    draw: ImageDraw.ImageDraw,
    snapshot: WeatherSnapshot,
    lang: WeatherLang,
    x0: int,
    y: int,
    x_right: int,
    label_font: object,
    value_font: object,
) -> None:
    cursor = float(x0)
    label = wind_label(lang).upper()
    draw.text((cursor, y), label, fill=RED, font=label_font)
    cursor += draw.textlength(label, font=label_font) + 4

    if snapshot.wind_bearing is not None:
        _draw_wind_arrow(
            draw, int(cursor) + 5, y + 7, snapshot.wind_bearing, 5, color=BLACK
        )
        cursor += 14
        degrees = _bearing_degrees(snapshot.wind_bearing)
        if degrees is not None:
            comp = compass_label(degrees)
            draw.text((cursor, y), comp, fill=BLACK, font=value_font)
            cursor += draw.textlength(comp, font=value_font) + 6

    parts: list[str] = []
    unit = snapshot.wind_speed_unit or "km/h"
    if snapshot.wind_speed is not None:
        kmh = _speed_to_kmh(snapshot.wind_speed, unit)
        parts.append(
            f"{_format_number(snapshot.wind_speed)} {unit} "
            f"({_format_number(kmh / 1.852)} kt)"
        )
    if snapshot.wind_gust_speed is not None:
        gust_kmh = _speed_to_kmh(snapshot.wind_gust_speed, unit)
        parts.append(
            f"{gust_label(lang)} {_format_number(snapshot.wind_gust_speed)} "
            f"({_format_number(gust_kmh / 1.852)} kt)"
        )
    if not parts:
        return
    text = _fit_text(draw, "  ".join(parts), value_font, max(20, x_right - cursor))
    draw.text((cursor, y), text, fill=BLACK, font=value_font)


def _speed_to_kmh(value: float, unit: str | None) -> float:
    text = (unit or "km/h").lower().replace(" ", "")
    if text in ("km/h", "kmh", "kph"):
        return value
    if text in ("m/s", "mps"):
        return value * 3.6
    if text in ("mph",):
        return value * 1.60934
    if text in ("kt", "kts", "kn", "knot", "knots"):
        return value * 1.852
    return value


def _draw_multiday_chart(
    draw: ImageDraw.ImageDraw,
    hours: tuple[HourlyForecast, ...],
    day_dates: list[date],
    x0: int,
    y0: int,
    strip_w: int,
    strip_h: int,
    tz: ZoneInfo,
) -> None:
    columns = len(day_dates)
    if columns < 1:
        return
    col_w = strip_w // columns

    # White ground + hairline noon ticks (no yellow wash — keeps the curve crisp).
    for index in range(1, columns):
        x = x0 + col_w * index
        draw.line((x, y0, x, y0 + strip_h), fill=BLACK, width=1)

    label_font = load_font(10)
    chart_top = y0 + 11
    chart_bottom = y0 + strip_h - 1
    chart_h = max(8, chart_bottom - chart_top)

    dated = _hours_for_days(hours, day_dates, tz)
    if len(dated) < 2:
        return

    temps = [h.temperature for h, _ in dated if h.temperature is not None]
    precip = [h.precipitation or 0.0 for h, _ in dated]
    if not temps:
        return
    t_min = min(temps)
    t_max = max(temps)
    if abs(t_max - t_min) < 0.5:
        t_max = t_min + 1.0
    p_max = max(max(precip), 1.0)

    def x_for(local: datetime) -> float | None:
        try:
            col = day_dates.index(local.date())
        except ValueError:
            return None
        frac = (local.hour + local.minute / 60.0) / 24.0
        return x0 + col * col_w + frac * col_w

    # Hourly precip bars with a 1px gap (meteoblue-style separation).
    bar_w = max(2, col_w // 30)
    for hour, local in dated:
        amount = hour.precipitation or 0.0
        if amount <= 0.05:
            continue
        x = x_for(local)
        if x is None:
            continue
        bar_h = max(2, int((amount / p_max) * (chart_h * 0.50)))
        xi = int(x)
        half = max(1, bar_w // 2)
        draw.rectangle(
            (
                xi - half,
                chart_bottom - bar_h,
                xi + half - 1,
                chart_bottom,
            ),
            fill=RED,
        )

    points: list[tuple[float, float]] = []
    for hour, local in dated:
        if hour.temperature is None:
            continue
        x = x_for(local)
        if x is None:
            continue
        norm = (hour.temperature - t_min) / (t_max - t_min)
        y = chart_bottom - norm * (chart_h * 0.78) - chart_h * 0.10
        points.append((x, y))
    if len(points) >= 2:
        draw.line(points, fill=BLACK, width=2)

    # Sparse noon ticks in yellow (subtle warmth without washing the plot).
    for day in day_dates:
        local = datetime(day.year, day.month, day.day, 12, tzinfo=tz)
        x = x_for(local)
        if x is None:
            continue
        xi = int(x)
        draw.line((xi, chart_top, xi, chart_bottom), fill=YELLOW, width=1)
        label = "12"
        lw = draw.textlength(label, font=label_font)
        draw.text((x - lw / 2, y0), label, fill=BLACK, font=label_font)


def _draw_days(
    draw: ImageDraw.ImageDraw,
    days: tuple[DayForecast, ...],
    day_dates: list[date],
    x0: int,
    y0: int,
    strip_w: int,
    strip_h: int,
    tz: ZoneInfo,
    today: datetime,
    lang: WeatherLang,
) -> None:
    """Edge-to-edge day strip: black title bar + icon + hi/lo."""
    if not days:
        font = load_font(12)
        draw.text((x0 + 4, y0 + strip_h // 3), "—", fill=BLACK, font=font)
        return

    columns = len(day_dates) or min(_DAY_COLUMNS, len(days))
    col_w = strip_w // columns
    bar_h = min(14, max(12, strip_h // 4))
    label_font = load_font(11, bold=True)
    temp_font = load_font(14, bold=True)
    mm_font = load_font(10)

    for index in range(columns):
        day = days[index] if index < len(days) else None
        left = x0 + col_w * index
        right = x0 + strip_w if index == columns - 1 else left + col_w
        cx = (left + right) // 2

        # Orange day bar (R+Y dither) — black type stays readable on e-ink.
        _fill_orange(draw, (left, y0, right - 1, y0 + bar_h - 1))
        if index > 0:
            draw.line((left, y0, left, y0 + strip_h - 1), fill=BLACK, width=1)

        if day is None:
            continue

        label = _day_label(day.when, tz, today, lang)
        lw = draw.textlength(label, font=label_font)
        draw.text(
            (cx - lw / 2, y0 + 1),
            label,
            fill=BLACK,
            font=label_font,
        )

        body_top = y0 + bar_h + 2
        body_h = strip_h - bar_h - 2
        icon_size = min(20, col_w - 16, max(14, body_h - 22))
        icon_y = body_top + icon_size // 2
        draw_condition_icon(draw, day.condition, cx, icon_y, icon_size)

        high = _format_temp_short(day.temperature)
        low = _format_temp_short(day.templow)
        temps_y = min(icon_y + icon_size // 2 + 1, y0 + strip_h - 15)
        if high and low:
            high_t = high
            low_t = f"/{low}"
            total = draw.textlength(high_t + low_t, font=temp_font)
            hx = cx - total / 2
            draw.text((hx, temps_y), high_t, fill=RED, font=temp_font)
            hx += draw.textlength(high_t, font=temp_font)
            draw.text((hx, temps_y), low_t, fill=BLACK, font=temp_font)
        else:
            text = high or low or "—"
            tw = draw.textlength(text, font=temp_font)
            draw.text((cx - tw / 2, temps_y), text, fill=BLACK, font=temp_font)

        if day.precipitation is not None and day.precipitation >= 0.5:
            detail = f"{_format_number(day.precipitation)}mm"
            dw = draw.textlength(detail, font=mm_font)
            detail_y = temps_y + 14
            if detail_y + 10 <= y0 + strip_h:
                draw.text(
                    (cx - dw / 2, detail_y), detail, fill=RED, font=mm_font
                )


def _hours_for_days(
    hours: tuple[HourlyForecast, ...],
    day_dates: list[date],
    tz: ZoneInfo,
) -> list[tuple[HourlyForecast, datetime]]:
    wanted = set(day_dates)
    out: list[tuple[HourlyForecast, datetime]] = []
    for hour in hours:
        local = _as_local(hour.when, tz)
        if local is None or local.date() not in wanted:
            continue
        out.append((hour, local))
    out.sort(key=lambda item: item[1])
    return out


def _day_dates(
    days: tuple[DayForecast, ...],
    tz: ZoneInfo,
    today: datetime,
) -> list[date]:
    dates: list[date] = []
    for day in days[:_DAY_COLUMNS]:
        local = _as_local(day.when, tz)
        if local is not None:
            dates.append(local.date())
    if dates:
        return dates
    start = today.date()
    return [start + timedelta(days=i) for i in range(_DAY_COLUMNS)]


def _draw_wind_arrow(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    bearing: float | str | None,
    radius: int,
    *,
    color: tuple[int, int, int] = BLACK,
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
    draw.line((tail_x, tail_y, tip_x, tip_y), fill=color, width=width)
    head = max(3, radius // 2)
    for angle in (radians + math.radians(145), radians - math.radians(145)):
        draw.line(
            (
                tip_x,
                tip_y,
                tip_x + head * math.sin(angle),
                tip_y - head * math.cos(angle),
            ),
            fill=color,
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
        "NE": 45,
        "E": 90,
        "SE": 135,
        "S": 180,
        "SW": 225,
        "W": 270,
        "NW": 315,
    }
    if text in compass:
        return float(compass[text])
    try:
        return float(text) % 360.0
    except ValueError:
        return None


def _day_label(
    when: datetime | None,
    tz: ZoneInfo,
    today: datetime,
    lang: WeatherLang,
) -> str:
    local = _as_local(when, tz)
    if local is None:
        return "—"
    if local.date() == today.date():
        return today_label(lang)
    return weekday_short(lang, local.weekday())


def _format_date(now: datetime, lang: WeatherLang) -> str:
    if lang == "pl":
        months = (
            "sty",
            "lut",
            "mar",
            "kwi",
            "maj",
            "cze",
            "lip",
            "sie",
            "wrz",
            "paź",
            "lis",
            "gru",
        )
        return f"{now.day} {months[now.month - 1]} {now.year}"
    if _supports_minus_fmt():
        return now.strftime("%-d %b %Y")
    return now.strftime("%d %b %Y")


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


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: object,
    max_width: float,
) -> str:
    if max_width <= 0:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    trimmed = text
    while trimmed and draw.textlength(trimmed + "…", font=font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + "…") if trimmed else ""


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

