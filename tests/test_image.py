"""Unit tests for image quantize and encode (ported from the web app)."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from custom_components.eink_esl.image import (
    ImageError,
    prepare_for_panel,
    prepare_image,
    preview_png_bytes,
    quantize,
)
from custom_components.eink_esl.protocol import COLOR_WHITE, DEFAULT_PANEL_ID


def _solid_rgba(
    width: int, height: int, rgb: tuple[int, int, int]
) -> bytes:
    pixel = bytes((*rgb, 255))
    return pixel * (width * height)


def _png_bytes(
    width: int, height: int, rgb: tuple[int, int, int]
) -> bytes:
    image = Image.new("RGB", (width, height), rgb)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_pure_pigments_stay_on_their_own_palette_codes() -> None:
    cases: list[tuple[tuple[int, int, int], int]] = [
        ((0, 0, 0), 0),
        ((255, 255, 255), 1),
        ((255, 255, 0), 2),
        ((255, 0, 0), 3),
        ((12, 10, 8), 0),
        ((250, 248, 245), 1),
        ((255, 220, 0), 2),
        ((210, 16, 12), 3),
    ]
    for rgb, code in cases:
        result = quantize(_solid_rgba(2, 2, rgb), 2, 2, "nearest", "bwry")
        assert list(result.codes) == [code, code, code, code], f"{rgb} → {code}"


def test_bwr_panel_never_emits_yellow() -> None:
    result = quantize(
        _solid_rgba(3, 3, (255, 255, 0)), 3, 3, "nearest", "bwr"
    )
    assert all(code != 2 for code in result.codes)


def test_flat_mid_gray_stays_one_color_until_error_is_diffused() -> None:
    gray = _solid_rgba(32, 32, (128, 128, 128))
    nearest = quantize(gray, 32, 32, "nearest", "bwry")
    dithered = quantize(gray, 32, 32, "floyd-steinberg", "bwry")
    assert len(set(nearest.codes)) == 1
    assert 0 in dithered.codes and 1 in dithered.codes


def test_prepare_white_png_for_default_panel_packs_to_0x55() -> None:
    panel_id = DEFAULT_PANEL_ID
    encoded = prepare_for_panel(
        _png_bytes(10, 10, (255, 255, 255)),
        panel_id,
        mode="nearest",
        fit="stretch",
    )
    assert encoded.panel_id == panel_id
    assert encoded.width == 384
    assert encoded.height == 184
    assert encoded.type_code == 0x0A
    expected_bytes = (384 * 184 + 3) // 4
    assert len(encoded.packed) == expected_bytes
    assert all(byte == 0x55 for byte in encoded.packed)


def test_prepare_image_rejects_bad_dimensions() -> None:
    with pytest.raises(ImageError, match="positive"):
        prepare_image(
            _png_bytes(2, 2, (0, 0, 0)),
            width=0,
            height=10,
            colors="bw",
        )


def test_prepare_image_rejects_undecodable_bytes() -> None:
    with pytest.raises(ImageError, match="Could not decode"):
        prepare_image(b"not-an-image", width=2, height=2, colors="bw")


def test_contain_fit_letterboxes_on_background() -> None:
    # Tall red image on a wide white canvas → sides stay background white.
    encoded = prepare_image(
        _png_bytes(10, 40, (255, 0, 0)),
        width=40,
        height=20,
        colors="bwr",
        mode="nearest",
        fit="contain",
        background=(255, 255, 255),
    )
    assert encoded.preview_rgba[0:3] == bytes((255, 255, 255))
    assert COLOR_WHITE == 1


def test_preview_png_bytes_round_trips_quantized_rgba() -> None:
    encoded = prepare_image(
        _png_bytes(4, 2, (255, 0, 0)),
        width=4,
        height=2,
        colors="bwr",
        mode="nearest",
        fit="stretch",
    )
    png = preview_png_bytes(encoded.preview_rgba, encoded.width, encoded.height)
    with Image.open(BytesIO(png)) as opened:
        assert opened.size == (4, 2)
        assert opened.convert("RGB").getpixel((0, 0)) == (255, 0, 0)
