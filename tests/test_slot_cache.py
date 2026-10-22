"""Unit tests for HA Store slot helpers (Store stubbed)."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from custom_components.eink_esl import slot_cache


class _FakeStore:
    def __init__(self) -> None:
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data) -> None:
        self.data = data


@pytest.mark.asyncio
async def test_save_and_get_slot_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    hass = SimpleNamespace(data={"eink_esl": {}})
    store = _FakeStore()

    async def fake_get_store(_hass):
        return store

    monkeypatch.setattr(slot_cache, "async_get_store", fake_get_store)

    png = b"\x89PNG\r\n\x1a\n" + b"fake"
    await slot_cache.async_save_slot(
        hass,
        "entry-1",
        png_bytes=png,
        width=384,
        height=184,
        label="weather.forecast_home",
        weather_entity_id="weather.forecast_home",
    )

    loaded = await slot_cache.async_get_slot(hass, "entry-1")
    assert loaded is not None
    assert loaded["width"] == 384
    assert loaded["height"] == 184
    assert loaded["weather_entity_id"] == "weather.forecast_home"
    assert base64.b64decode(loaded["content_b64"]) == png

    payload = slot_cache.slot_to_api_payload(loaded)
    assert payload["content"] == loaded["content_b64"]
    assert payload["label"] == "weather.forecast_home"


def test_slot_to_api_payload_shapes_fields() -> None:
    payload = slot_cache.slot_to_api_payload(
        {
            "content_b64": "abc",
            "content_type": "image/png",
            "width": 10,
            "height": 20,
            "fit": "stretch",
            "mode": "nearest",
            "background": "white",
            "label": "x",
            "weather_entity_id": "weather.home",
            "saved_at": "t",
        }
    )
    assert payload["content"] == "abc"
    assert payload["weather_entity_id"] == "weather.home"
