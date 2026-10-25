"""Load a TrueType font (bundled DejaVu first — HA images often lack system fonts)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_ASSETS = Path(__file__).resolve().parent / "assets"

_CANDIDATES = (
    # Bundled with the integration (reliable on HA OS / Container).
    str(_ASSETS / "DejaVuSans.ttf"),
    str(_ASSETS / "DejaVuSans-Bold.ttf"),
    # Home Assistant OS / Debian
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # macOS (local pytest / preview)
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)


@lru_cache(maxsize=32)
def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Return a scalable font, falling back to Pillow's bitmap default."""
    size = max(8, int(size))
    preferred: list[str] = []
    if bold:
        preferred.extend(
            (
                str(_ASSETS / "DejaVuSans-Bold.ttf"),
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            )
        )
    preferred.extend(_CANDIDATES)
    for path in preferred:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()
