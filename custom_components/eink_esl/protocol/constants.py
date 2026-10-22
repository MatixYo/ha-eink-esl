"""Wire-level constants for the Leeka-compatible ESL protocol."""

from __future__ import annotations

# 2-bit pigment codes packed four pixels per byte (MSB = first pixel).
COLOR_BLACK = 0
COLOR_WHITE = 1
COLOR_YELLOW = 2
COLOR_RED = 3

CMD_CLEAR = 0x00
CMD_DISPLAY = 0x01
CMD_START = 0x02
CMD_CHUNK = 0x03
CMD_ACK = 0x05

CLEAR_BLACK = 0x00
CLEAR_WHITE = 0xFF

# Chunk frame: command (1) + packet number (2) + payload.
MAX_PACKET_BYTES = 200
PACKET_HEADER_BYTES = 3
DEFAULT_PAYLOAD_BYTES = MAX_PACKET_BYTES - PACKET_HEADER_BYTES

ACK_TIMEOUT_MS = 2000
MAX_RETRIES = 3

# Status ACK: 0x00 means success; anything else is failure.
ACK_STATUS_OK = 0x00
