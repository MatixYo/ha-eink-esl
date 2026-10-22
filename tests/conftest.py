"""Import domain packages without a full Home Assistant install."""

from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = []  # mark as package when needed
        sys.modules[name] = module
    return module


def _install_homeassistant_stubs() -> None:
    """Satisfy integration imports when unit-testing protocol/image/ble."""
    ha = _module("homeassistant")
    ha.__path__ = []

    config_entries = _module("homeassistant.config_entries")
    config_entries.ConfigEntry = type("ConfigEntry", (), {})
    config_entries.ConfigFlow = type("ConfigFlow", (), {})
    config_entries.ConfigFlowResult = dict

    const = _module("homeassistant.const")
    const.Platform = type("Platform", (), {})
    const.CONF_ADDRESS = "address"
    const.CONF_DEVICE_ID = "device_id"

    core = _module("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    core.ServiceCall = type("ServiceCall", (), {})
    core.callback = lambda fn: fn

    exceptions = _module("homeassistant.exceptions")
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})

    helpers = _module("homeassistant.helpers")
    helpers.__path__ = []
    device_registry = _module("homeassistant.helpers.device_registry")
    device_registry.CONNECTION_BLUETOOTH = "bluetooth"
    device_registry.DeviceRegistry = type("DeviceRegistry", (), {})
    device_registry.async_get = lambda hass: None

    cv = _module("homeassistant.helpers.config_validation")
    cv.string = str
    cv.ensure_list = lambda value: value if isinstance(value, list) else [value]

    components = _module("homeassistant.components")
    components.__path__ = []
    bluetooth = _module("homeassistant.components.bluetooth")
    bluetooth.async_ble_device_from_address = lambda *args, **kwargs: None
    bluetooth.async_discovered_service_info = lambda *args, **kwargs: []
    bluetooth.BluetoothServiceInfoBleak = type("BluetoothServiceInfoBleak", (), {})

    config_entries = sys.modules["homeassistant.config_entries"]
    config_entries.OptionsFlow = type("OptionsFlow", (), {})


_install_homeassistant_stubs()
