"""Load a TrueType font that exists on HA hosts and developer machines."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_CANDIDATES = (
    # Home Assistant OS / Debian
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # macOS (local pytest)
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


@lru_cache(maxsize=32)
def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Return a scalable font, falling back to Pillow's bitmap default."""
    size = max(8, int(size))
    preferred = list(_CANDIDATES)
    if bold:
        preferred = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            *preferred,
        ]
    for path in preferred:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()
