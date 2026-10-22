"""Build and parse GATT command / ACK frames."""

from __future__ import annotations

from .constants import (
    CMD_ACK,
    CMD_CHUNK,
    CMD_CLEAR,
    CMD_DISPLAY,
    CMD_START,
    DEFAULT_PAYLOAD_BYTES,
    MAX_PACKET_BYTES,
    PACKET_HEADER_BYTES,
)
from .errors import ProtocolError


def build_clear(color: int) -> bytes:
    """Clear-screen command: ``0x00`` + fill color."""
    return bytes((CMD_CLEAR, color & 0xFF))


def build_start(image_size: int) -> bytes:
    """Start-transfer command: ``0x02`` + big-endian image byte length."""
    if image_size < 0 or image_size > 0xFFFFFFFF:
        raise ProtocolError(f"Image size out of range: {image_size}")
    return bytes(
        (
            CMD_START,
            (image_size >> 24) & 0xFF,
            (image_size >> 16) & 0xFF,
            (image_size >> 8) & 0xFF,
            image_size & 0xFF,
        )
    )


def build_display(device_type: int) -> bytes:
    """Display command: ``0x01`` + panel type code."""
    return bytes((CMD_DISPLAY, device_type & 0xFF))


def build_chunk(packet_number: int, data: bytes | bytearray) -> bytes:
    """Chunk-transfer command: ``0x03`` + packet number + payload."""
    if packet_number < 0 or packet_number > 0xFFFF:
        raise ProtocolError(f"Packet number out of range: {packet_number}")
    length = PACKET_HEADER_BYTES + len(data)
    if length > MAX_PACKET_BYTES:
        raise ProtocolError(
            f"Packet is {length} B, limit is {MAX_PACKET_BYTES} B"
        )
    return bytes(
        (
            CMD_CHUNK,
            (packet_number >> 8) & 0xFF,
            packet_number & 0xFF,
        )
    ) + bytes(data)


def split_payload(
    data: bytes | bytearray,
    payload_size: int = DEFAULT_PAYLOAD_BYTES,
) -> list[bytes]:
    """Split packed image bytes into chunk payloads of at most ``payload_size``."""
    if payload_size < 1 or payload_size > DEFAULT_PAYLOAD_BYTES:
        raise ProtocolError(
            f"Packet payload must be 1–{DEFAULT_PAYLOAD_BYTES} B"
        )
    if not data:
        return []
    return [
        bytes(data[offset : offset + payload_size])
        for offset in range(0, len(data), payload_size)
    ]


def read_status_ack(payload: bytes | bytearray) -> int | None:
    """Parse a non-chunk ACK (``0x05`` + status). Returns status or ``None``."""
    if len(payload) < 2 or payload[0] != CMD_ACK:
        return None
    return payload[1]


def read_chunk_ack(payload: bytes | bytearray) -> int | None:
    """Parse a chunk ACK (``0x05`` + packet number). Returns number or ``None``."""
    if len(payload) < 3 or payload[0] != CMD_ACK:
        return None
    return (payload[1] << 8) | payload[2]


def battery_percent_from_service_data(data: bytes | bytearray) -> int | None:
    """Read battery % from advertising service data for the battery UUID.

    The firmware places the percentage at byte index 9 of the manufacturer /
    service data blob (hex digits 18–19 in the protocol doc examples).
    """
    if len(data) < 10:
        return None
    return data[9]


def to_hex(data: bytes | bytearray, limit: int | None = None) -> str:
    """Format bytes as space-separated hex for logs."""
    end = len(data) if limit is None else min(limit, len(data))
    return " ".join(f"{byte:02x}" for byte in data[:end])
