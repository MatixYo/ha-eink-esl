"""OKLab nearest-color quantize and Floyd–Steinberg dither (ported from the web app)."""

from __future__ import annotations

from array import array
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


# 256-entry LUT — rgb_to_oklab is called once per pixel; avoid pow() every time.
_LINEAR_LUT = [_srgb_to_linear(i) for i in range(256)]


def rgb_to_oklab(r: int, g: int, b: int) -> Lab:
    lr = _LINEAR_LUT[r]
    lg = _LINEAR_LUT[g]
    lb = _LINEAR_LUT[b]
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


def _nearest_index(
    lab_l: float,
    lab_a: float,
    lab_b: float,
    labs: list[Lab],
) -> int:
    best = 0
    best_distance = float("inf")
    for index, color in enumerate(labs):
        d_l = lab_l - color[0]
        d_a = lab_a - color[1]
        d_b = lab_b - color[2]
        distance = d_l * d_l + d_a * d_a + d_b * d_b
        if distance < best_distance:
            best = index
            best_distance = distance
    return best


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
    labs = [color.lab for color in palette]
    rgb_r = [color.rgb[0] for color in palette]
    rgb_g = [color.rgb[1] for color in palette]
    rgb_b = [color.rgb[2] for color in palette]
    codes_by_index = [color.code for color in palette]

    codes = bytearray(pixel_count)
    preview = bytearray(pixel_count * 4)
    # Flat float buffers beat list[float] for tight inner loops on HA hosts.
    source = array("d", [0.0]) * (pixel_count * 3)

    for index in range(pixel_count):
        offset = index * 4
        lab = rgb_to_oklab(rgba[offset], rgba[offset + 1], rgba[offset + 2])
        base = index * 3
        source[base] = lab[0]
        source[base + 1] = lab[1]
        source[base + 2] = lab[2]

    if mode == "nearest":
        for index in range(pixel_count):
            base = index * 3
            choice = _nearest_index(
                source[base], source[base + 1], source[base + 2], labs
            )
            codes[index] = codes_by_index[choice]
            out = index * 4
            preview[out] = rgb_r[choice]
            preview[out + 1] = rgb_g[choice]
            preview[out + 2] = rgb_b[choice]
            preview[out + 3] = 255
        return QuantizeResult(codes=bytes(codes), preview_rgba=bytes(preview))

    error = array("d", [0.0]) * (pixel_count * 3)
    for y in range(height):
        left_to_right = y % 2 == 0
        step = 1 if left_to_right else -1
        x = 0 if left_to_right else width - 1
        end = width if left_to_right else -1

        while x != end:
            index = y * width + x
            base = index * 3
            lab_l = source[base] + error[base]
            lab_a = source[base + 1] + error[base + 1]
            lab_b = source[base + 2] + error[base + 2]
            if lab_l < 0.0:
                lab_l = 0.0
            elif lab_l > 1.0:
                lab_l = 1.0
            if lab_a < -0.5:
                lab_a = -0.5
            elif lab_a > 0.5:
                lab_a = 0.5
            if lab_b < -0.5:
                lab_b = -0.5
            elif lab_b > 0.5:
                lab_b = 0.5

            choice = _nearest_index(lab_l, lab_a, lab_b, labs)
            codes[index] = codes_by_index[choice]
            out = index * 4
            preview[out] = rgb_r[choice]
            preview[out + 1] = rgb_g[choice]
            preview[out + 2] = rgb_b[choice]
            preview[out + 3] = 255

            target = labs[choice]
            leftover_l = lab_l - target[0]
            leftover_a = lab_a - target[1]
            leftover_b = lab_b - target[2]

            # Floyd–Steinberg weights, serpentine scan.
            for nx, ny, weight in (
                (x + step, y, 7 / 16),
                (x - step, y + 1, 3 / 16),
                (x, y + 1, 5 / 16),
                (x + step, y + 1, 1 / 16),
            ):
                if 0 <= nx < width and 0 <= ny < height:
                    dest = (ny * width + nx) * 3
                    error[dest] += leftover_l * weight
                    error[dest + 1] += leftover_a * weight
                    error[dest + 2] += leftover_b * weight

            x += step

    return QuantizeResult(codes=bytes(codes), preview_rgba=bytes(preview))
