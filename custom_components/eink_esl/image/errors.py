"""Domain errors for image preparation."""

from __future__ import annotations


class ImageError(Exception):
    """Raised when an image cannot be loaded, sized, or quantized."""
