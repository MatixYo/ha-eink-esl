"""Tests for ESL Bluetooth discovery matching."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.eink_esl.const import BATTERY_SERVICE_UUID
from custom_components.eink_esl.discovery import (
    battery_from_discovery,
    discovery_title,
    is_esl_candidate,
)


def test_candidate_with_battery_service_data() -> None:
    data = bytearray(10)
    data[9] = 72
    info = SimpleNamespace(
        service_data={BATTERY_SERVICE_UUID: bytes(data)},
        service_uuids=[],
        name="Label",
        address="AA:BB:CC:DD:EE:FF",
    )
    assert is_esl_candidate(info) is True
    assert battery_from_discovery(info) == 72


def test_candidate_with_service_uuid_only() -> None:
    info = SimpleNamespace(
        service_data={},
        service_uuids=[BATTERY_SERVICE_UUID],
        name="",
        address="AA:BB:CC:DD:EE:FF",
    )
    assert is_esl_candidate(info) is True


def test_rejects_unrelated_advertisement() -> None:
    info = SimpleNamespace(
        service_data={"0000180f-0000-1000-8000-00805f9b34fb": bytes([50])},
        service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"],
        name="Headphones",
        address="11:22:33:44:55:66",
    )
    assert is_esl_candidate(info) is False


def test_discovery_title_prefers_name() -> None:
    info = SimpleNamespace(name="Kitchen", address="AA:BB:CC:DD:EE:FF")
    assert discovery_title(info) == "Kitchen (AA:BB:CC:DD:EE:FF)"
    info.name = ""
    assert discovery_title(info) == "ESL AA:BB:CC:DD:EE:FF"
