"""Pixel rotation and 4-pixels-per-byte packing for ESL image payloads."""

from __future__ import annotations

from .constants import COLOR_WHITE
from .errors import ProtocolError


def rotate_for_device(
    codes: bytes | bytearray,
    width: int,
    height: int,
) -> tuple[bytes, int, int]:
    """Apply the device orientation rule used by the firmware/converter.

    Frames with width ≥ 400 or already portrait keep pixel order. Narrow
    landscape frames are rotated 90° counterclockwise then 180° so packed
    bytes match what the tag expects.
    """
    if width >= 400 or width < height:
        return bytes(codes), width, height

    rotated = bytearray(len(codes))
    for y in range(height):
        for x in range(width):
            value = codes[y * width + x]
            next_x = y
            next_y = width - 1 - x
            rotated[next_y * height + next_x] = value

    turned_width = height
    turned_height = width
    turned = bytearray(len(codes))
    for y in range(turned_height):
        for x in range(turned_width):
            value = rotated[y * turned_width + x]
            next_x = turned_width - 1 - x
            next_y = turned_height - 1 - y
            turned[next_y * turned_width + next_x] = value

    return bytes(turned), turned_width, turned_height


def pack_pixels(codes: bytes | bytearray) -> bytes:
    """Pack 2-bit pigment codes into bytes (4 pixels per byte, MSB first)."""
    byte_count = (len(codes) + 3) // 4
    packed = bytearray(byte_count)
    for byte_index, index in enumerate(range(0, len(codes), 4)):
        first = codes[index] if index < len(codes) else COLOR_WHITE
        second = codes[index + 1] if index + 1 < len(codes) else COLOR_WHITE
        third = codes[index + 2] if index + 2 < len(codes) else COLOR_WHITE
        fourth = codes[index + 3] if index + 3 < len(codes) else COLOR_WHITE
        packed[byte_index] = (
            (first << 6) | (second << 4) | (third << 2) | fourth
        ) & 0xFF
    return bytes(packed)


def encode_image(codes: bytes | bytearray, width: int, height: int) -> bytes:
    """Rotate (if needed) and pack a full-frame pigment buffer for transfer."""
    if len(codes) != width * height:
        raise ProtocolError("Pixel buffer does not match the panel size")
    rotated_codes, _, _ = rotate_for_device(codes, width, height)
    return pack_pixels(rotated_codes)
