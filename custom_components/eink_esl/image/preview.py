"""PNG preview of a quantized frame (same pixels the device would show)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from .errors import ImageError


def preview_png_bytes(preview_rgba: bytes, width: int, height: int) -> bytes:
    """Encode ``preview_rgba`` (RGBA) to a PNG for the sidebar / clients."""
    if width < 1 or height < 1:
        raise ImageError("Panel width and height must be positive")
    expected = width * height * 4
    if len(preview_rgba) < expected:
        raise ImageError("Preview buffer is shorter than width × height")
    image = Image.frombytes("RGBA", (width, height), bytes(preview_rgba[:expected]))
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
