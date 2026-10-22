"""Narrow GATT transport used by the transfer session."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class InkTransport(Protocol):
    """Write + notify surface for the ink characteristic."""

    @property
    def supports_write_with_response(self) -> bool: ...

    @property
    def supports_write_without_response(self) -> bool: ...

    def drain_notifications(self) -> None:
        """Drop queued notifies before a retry attempt."""

    async def write(self, data: bytes, *, response: bool) -> None:
        """Write one GATT packet (``response`` selects write-with-response)."""

    async def next_notification(self, timeout_s: float) -> bytes:
        """Wait for the next notify payload or raise ``TimeoutError``."""
