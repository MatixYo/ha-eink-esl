"""Tests for base64 / config-path image decoding."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from custom_components.eink_esl.image_input import decode_image_payload


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _hass(config_dir: Path):
    def path(*parts: str) -> str:
        return str(config_dir.joinpath(*parts))

    return SimpleNamespace(config=SimpleNamespace(path=path, config_dir=str(config_dir)))


def test_decode_raw_base64(tmp_path: Path) -> None:
    import base64

    raw = base64.b64encode(_png_bytes()).decode()
    assert decode_image_payload(_hass(tmp_path), raw).startswith(b"\x89PNG")


def test_decode_data_url(tmp_path: Path) -> None:
    import base64

    raw = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
    assert decode_image_payload(_hass(tmp_path), raw).startswith(b"\x89PNG")


def test_decode_config_relative_path(tmp_path: Path) -> None:
    image_path = tmp_path / "label.png"
    image_path.write_bytes(_png_bytes())
    assert decode_image_payload(_hass(tmp_path), "label.png").startswith(b"\x89PNG")


def test_rejects_path_outside_config(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(_png_bytes())
    with pytest.raises(Exception, match="inside the Home Assistant config"):
        decode_image_payload(_hass(tmp_path), str(outside))


def test_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="empty"):
        decode_image_payload(_hass(tmp_path), "  ")
