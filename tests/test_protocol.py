"""Unit tests for protocol packing and packet framing (ported from the web app)."""

from __future__ import annotations

import pytest

from custom_components.eink_esl.protocol import (
    COLOR_BLACK,
    COLOR_RED,
    COLOR_WHITE,
    COLOR_YELLOW,
    DEFAULT_PANEL_ID,
    ProtocolError,
    battery_percent_from_service_data,
    build_chunk,
    build_clear,
    build_display,
    build_start,
    encode_image,
    pack_pixels,
    panel_by_id,
    read_chunk_ack,
    read_status_ack,
    split_payload,
)


def test_spec_white_296x128_packs_to_9472_bytes_of_0x55() -> None:
    codes = bytes([COLOR_WHITE]) * (296 * 128)
    packed = encode_image(codes, 296, 128)
    assert len(packed) == 9472
    assert all(byte == 0x55 for byte in packed)


def test_four_pigments_pack_into_one_byte() -> None:
    codes = bytes((COLOR_BLACK, COLOR_WHITE, COLOR_YELLOW, COLOR_RED))
    assert list(pack_pixels(codes)) == [0x1B]


def test_wide_landscape_frame_is_rotated_before_packing() -> None:
    codes = bytes(
        (
            COLOR_BLACK,
            COLOR_WHITE,
            COLOR_YELLOW,
            COLOR_RED,
            COLOR_WHITE,
            COLOR_WHITE,
            COLOR_WHITE,
            COLOR_WHITE,
        )
    )
    assert list(encode_image(codes, 4, 2)) == [0x45, 0x67]


def test_portrait_and_400px_wide_frames_keep_pixel_order() -> None:
    portrait = bytearray([COLOR_WHITE] * (2 * 4))
    portrait[0:4] = (COLOR_BLACK, COLOR_BLACK, COLOR_BLACK, COLOR_BLACK)
    assert encode_image(bytes(portrait), 2, 4)[0] == 0x00

    wide = bytearray([COLOR_WHITE] * 400)
    wide[0] = COLOR_RED
    assert encode_image(bytes(wide), 400, 1)[0] == 0xD5


def test_encode_image_rejects_mismatched_buffer() -> None:
    with pytest.raises(ProtocolError, match="panel size"):
        encode_image(b"\x00\x01", 2, 2)


def test_commands_match_documented_byte_layout() -> None:
    assert list(build_clear(0xFF)) == [0x00, 0xFF]
    assert list(build_start(9472)) == [0x02, 0x00, 0x00, 0x25, 0x00]
    assert list(build_display(0x08)) == [0x01, 0x08]
    assert list(build_chunk(1, bytes((0x55, 0x55)))) == [
        0x03,
        0x00,
        0x01,
        0x55,
        0x55,
    ]


def test_payload_is_split_without_crossing_200_byte_packet_limit() -> None:
    data = bytes([0x55]) * 400
    parts = split_payload(data, 197)
    assert [len(part) for part in parts] == [197, 197, 6]
    assert len(build_chunk(0, parts[0])) == 200


def test_split_payload_rejects_oversized_chunk() -> None:
    with pytest.raises(ProtocolError, match="1–197"):
        split_payload(b"\x55", 198)


def test_acks_and_battery_byte_follow_spec_offsets() -> None:
    assert read_status_ack(bytes((0x05, 0x00))) == 0
    assert read_status_ack(bytes((0x03, 0x00))) is None
    assert read_chunk_ack(bytes((0x05, 0x00, 0x02))) == 2
    assert read_chunk_ack(bytes((0x05, 0x00))) is None

    advertising = bytearray(10)
    advertising[9] = 0x3C
    assert battery_percent_from_service_data(advertising) == 60
    assert battery_percent_from_service_data(bytes(4)) is None


def test_default_panel_catalog_entry() -> None:
    panel = panel_by_id(DEFAULT_PANEL_ID)
    assert panel.id == "bwry-350"
    assert panel.type_code == 0x0A
    assert panel.width == 384
    assert panel.height == 184
    assert panel.colors == "bwry"
    assert panel_by_id("missing").id == DEFAULT_PANEL_ID
