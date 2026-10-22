"""Domain errors for BLE transfer."""

from __future__ import annotations


class TransferError(Exception):
    """Raised when a clear/upload fails after retries or the link drops."""


class PacketMismatchError(TransferError):
    """Device ACK packet number did not match the chunk we sent."""

    def __init__(self, received: int, expected: int) -> None:
        self.received = received
        self.expected = expected
        super().__init__(f"ACK {received}, expected {expected}")


class TransferAborted(TransferError):
    """Caller cancelled the transfer."""

    def __init__(self) -> None:
        super().__init__("Transfer cancelled")
