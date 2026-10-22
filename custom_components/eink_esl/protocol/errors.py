"""Domain errors for the Leeka-compatible transfer protocol."""

from __future__ import annotations


class ProtocolError(Exception):
    """Raised when packet build/parse or pixel packing input is invalid."""
