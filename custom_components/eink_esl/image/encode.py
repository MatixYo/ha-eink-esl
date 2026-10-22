"""Load, fit, quantize, and pack images for ESL transfer."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image

from ..protocol import Panel, encode_image, panel_by_id
from ..protocol.panels import PanelColors
from .errors import ImageError
from .palette import QuantizeMode, quantize

FitMode = Literal["contain", "cover", "stretch"]


@dataclass(frozen=True, slots=True)
class EncodedImage:
    """Packed transfer bytes plus a preview of the quantized frame."""

    packed: bytes
    width: int
    height: int
    preview_rgba: bytes
    type_code: int
    panel_id: str


def _fit_image(
    source: Image.Image,
    width: int,
    height: int,
    fit: FitMode,
    background: tuple[int, int, int],
) -> Image.Image:
    canvas = Image.new("RGB", (width, height), background)
    if fit == "stretch":
        resample = (
            Image.Resampling.BILINEAR
            if source.width > width or source.height > height
            else Image.Resampling.NEAREST
        )
        resized = source.resize((width, height), resample)
        canvas.paste(resized, (0, 0))
        return canvas

    if fit == "contain":
        scale = min(width / source.width, height / source.height)
    else:
        scale = max(width / source.width, height / source.height)

    drawn_width = max(1, round(source.width * scale))
    drawn_height = max(1, round(source.height * scale))
    resample = (
        Image.Resampling.BILINEAR if scale < 1 else Image.Resampling.NEAREST
    )
    resized = source.resize((drawn_width, drawn_height), resample)
    offset = ((width - drawn_width) // 2, (height - drawn_height) // 2)
    canvas.paste(resized, offset)
    return canvas


def prepare_image(
    image_bytes: bytes,
    *,
    width: int,
    height: int,
    colors: PanelColors,
    type_code: int = 0,
    panel_id: str = "",
    mode: QuantizeMode = "floyd-steinberg",
    fit: FitMode = "contain",
    background: tuple[int, int, int] = (255, 255, 255),
) -> EncodedImage:
    """Decode ``image_bytes``, fit to the panel size, quantize, and pack."""
    if width < 1 or height < 1:
        raise ImageError("Panel width and height must be positive")

    try:
        with Image.open(BytesIO(image_bytes)) as opened:
            source = opened.convert("RGB")
    except OSError as err:
        raise ImageError(f"Could not decode image: {err}") from err

    fitted = _fit_image(source, width, height, fit, background)
    rgba = fitted.convert("RGBA").tobytes()
    quantized = quantize(rgba, width, height, mode, colors)
    packed = encode_image(quantized.codes, width, height)
    return EncodedImage(
        packed=packed,
        width=width,
        height=height,
        preview_rgba=quantized.preview_rgba,
        type_code=type_code,
        panel_id=panel_id,
    )


def prepare_for_panel(
    image_bytes: bytes,
    panel: Panel | str,
    *,
    mode: QuantizeMode = "floyd-steinberg",
    fit: FitMode = "contain",
    background: tuple[int, int, int] = (255, 255, 255),
    width: int | None = None,
    height: int | None = None,
) -> EncodedImage:
    """Prepare an image for a catalog panel (or panel id string)."""
    resolved = panel_by_id(panel) if isinstance(panel, str) else panel
    return prepare_image(
        image_bytes,
        width=width if width is not None else resolved.width,
        height=height if height is not None else resolved.height,
        colors=resolved.colors,
        type_code=resolved.type_code,
        panel_id=resolved.id,
        mode=mode,
        fit=fit,
        background=background,
    )
