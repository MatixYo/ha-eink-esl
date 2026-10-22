"""OKLab nearest-color quantize and Floyd–Steinberg dither (ported from the web app)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..protocol.panels import PanelColors
from .errors import ImageError

QuantizeMode = Literal["nearest", "floyd-steinberg"]

Rgb = tuple[int, int, int]
Lab = tuple[float, float, float]

BLACK: Rgb = (0, 0, 0)
WHITE: Rgb = (255, 255, 255)
YELLOW: Rgb = (255, 255, 0)
RED: Rgb = (255, 0, 0)


@dataclass(frozen=True, slots=True)
class Swatch:
    code: int
    rgb: Rgb
    lab: Lab


def _srgb_to_linear(channel: int) -> float:
    value = channel / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def rgb_to_oklab(r: int, g: int, b: int) -> Lab:
    lr = _srgb_to_linear(r)
    lg = _srgb_to_linear(g)
    lb = _srgb_to_linear(b)
    l = (0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb) ** (1.0 / 3.0)
    m = (0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb) ** (1.0 / 3.0)
    s = (0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb) ** (1.0 / 3.0)
    return (
        0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
    )


def _swatch(code: int, rgb: Rgb) -> Swatch:
    return Swatch(code=code, rgb=rgb, lab=rgb_to_oklab(*rgb))


_SWATCHES = {
    "black": _swatch(0, BLACK),
    "white": _swatch(1, WHITE),
    "yellow": _swatch(2, YELLOW),
    "red": _swatch(3, RED),
}


def palette_for(name: PanelColors) -> list[Swatch]:
    if name == "bw":
        return [_SWATCHES["black"], _SWATCHES["white"]]
    if name == "bwr":
        return [_SWATCHES["black"], _SWATCHES["white"], _SWATCHES["red"]]
    return [
        _SWATCHES["black"],
        _SWATCHES["white"],
        _SWATCHES["yellow"],
        _SWATCHES["red"],
    ]


def _nearest(lab: Lab, palette: list[Swatch]) -> Swatch:
    best = palette[0]
    best_distance = float("inf")
    for color in palette:
        d_l = lab[0] - color.lab[0]
        d_a = lab[1] - color.lab[1]
        d_b = lab[2] - color.lab[2]
        distance = d_l * d_l + d_a * d_a + d_b * d_b
        if distance < best_distance:
            best = color
            best_distance = distance
    return best


def _clamp_lab(lab: Lab) -> Lab:
    return (
        min(1.0, max(0.0, lab[0])),
        min(0.5, max(-0.5, lab[1])),
        min(0.5, max(-0.5, lab[2])),
    )


def _write_preview(preview: bytearray, index: int, rgb: Rgb) -> None:
    offset = index * 4
    preview[offset] = rgb[0]
    preview[offset + 1] = rgb[1]
    preview[offset + 2] = rgb[2]
    preview[offset + 3] = 255


def _diffuse(
    error: list[float],
    width: int,
    height: int,
    x: int,
    y: int,
    leftover: Lab,
    weight: float,
) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    index = (y * width + x) * 3
    error[index] += leftover[0] * weight
    error[index + 1] += leftover[1] * weight
    error[index + 2] += leftover[2] * weight


@dataclass(frozen=True, slots=True)
class QuantizeResult:
    codes: bytes
    preview_rgba: bytes


def quantize(
    rgba: bytes | bytearray,
    width: int,
    height: int,
    mode: QuantizeMode,
    palette_name: PanelColors,
) -> QuantizeResult:
    """Map RGBA pixels to 2-bit pigment codes (and an RGB preview)."""
    pixel_count = width * height
    if len(rgba) < pixel_count * 4:
        raise ImageError("Image buffer is shorter than width × height")

    palette = palette_for(palette_name)
    codes = bytearray(pixel_count)
    preview = bytearray(pixel_count * 4)
    source = [0.0] * (pixel_count * 3)

    for index in range(pixel_count):
        offset = index * 4
        lab = rgb_to_oklab(rgba[offset], rgba[offset + 1], rgba[offset + 2])
        source[index * 3] = lab[0]
        source[index * 3 + 1] = lab[1]
        source[index * 3 + 2] = lab[2]

    if mode == "nearest":
        for index in range(pixel_count):
            color = _nearest(
                (
                    source[index * 3],
                    source[index * 3 + 1],
                    source[index * 3 + 2],
                ),
                palette,
            )
            codes[index] = color.code
            _write_preview(preview, index, color.rgb)
        return QuantizeResult(codes=bytes(codes), preview_rgba=bytes(preview))

    error = [0.0] * (pixel_count * 3)
    for y in range(height):
        left_to_right = y % 2 == 0
        x_range = range(width) if left_to_right else range(width - 1, -1, -1)
        step = 1 if left_to_right else -1

        for x in x_range:
            index = y * width + x
            shifted = _clamp_lab(
                (
                    source[index * 3] + error[index * 3],
                    source[index * 3 + 1] + error[index * 3 + 1],
                    source[index * 3 + 2] + error[index * 3 + 2],
                )
            )
            color = _nearest(shifted, palette)
            codes[index] = color.code
            _write_preview(preview, index, color.rgb)

            leftover: Lab = (
                shifted[0] - color.lab[0],
                shifted[1] - color.lab[1],
                shifted[2] - color.lab[2],
            )
            _diffuse(error, width, height, x + step, y, leftover, 7 / 16)
            _diffuse(error, width, height, x - step, y + 1, leftover, 3 / 16)
            _diffuse(error, width, height, x, y + 1, leftover, 5 / 16)
            _diffuse(error, width, height, x + step, y + 1, leftover, 1 / 16)

    return QuantizeResult(codes=bytes(codes), preview_rgba=bytes(preview))
