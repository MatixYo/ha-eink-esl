"""Decode service image inputs (base64 or a path under the HA config dir)."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


def decode_image_payload(hass: HomeAssistant, raw: str) -> bytes:
    """Turn a service ``image`` string into PNG/JPEG/… bytes.

    Accepts:
    - ``data:image/...;base64,...`` data URLs
    - raw base64
    - a file path relative to the Home Assistant config directory
    """
    value = raw.strip()
    if not value:
        raise HomeAssistantError("Image payload is empty")

    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1].strip()

    try:
        decoded = base64.b64decode(value, validate=False)
    except binascii.Error:
        decoded = b""

    # Prefer base64 when it looks like an image; otherwise try a config path.
    if _looks_like_image(decoded):
        return decoded

    path = Path(value)
    if not path.is_absolute():
        path = Path(hass.config.path(value))
    try:
        path = path.resolve(strict=True)
    except FileNotFoundError as err:
        raise HomeAssistantError(
            "Image must be base64 data or an existing file under the "
            "Home Assistant config directory"
        ) from err

    config_root = Path(hass.config.config_dir).resolve()
    if config_root not in path.parents and path != config_root:
        raise HomeAssistantError(
            "Image path must be inside the Home Assistant config directory"
        )

    try:
        data = path.read_bytes()
    except OSError as err:
        raise HomeAssistantError(f"Could not read image file: {err}") from err
    if not _looks_like_image(data):
        raise HomeAssistantError(f"File does not look like an image: {path}")
    return data


def _looks_like_image(data: bytes) -> bool:
    if len(data) < 8:
        return False
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"GIF8")
        or data.startswith(b"RIFF")
        or data.startswith(b"BM")
        or data.startswith(b"\x00\x00\x00\x0cjP")
    )
