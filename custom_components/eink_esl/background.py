"""Letterbox fill colors shared by upload service and preview websocket."""

from __future__ import annotations

BACKGROUND_RGB: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}
