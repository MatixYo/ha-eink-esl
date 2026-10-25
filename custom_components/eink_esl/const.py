"""Constants for the E-Ink ESL integration."""

from __future__ import annotations

DOMAIN = "eink_esl"
# Keep in sync with manifest.json (HACS / panel cache-bust).
VERSION = "0.1.32"

# GATT (Leeka-compatible protocol). See docs/ble_transfer_protocol_en.md.
INK_SERVICE_UUID = "13187b10-eba9-a3ba-044e-83d3217d9a38"
INK_CHARACTERISTIC_UUID = "4b646063-6264-f3a7-8941-e65356ea82fe"
BATTERY_SERVICE_UUID = "0000181a-0000-1000-8000-00805f9b34fb"

CONF_ADDRESS = "address"
CONF_PANEL_ID = "panel_id"

# Fired during upload so the sidebar panel can show status/progress.
EVENT_TRANSFER_PROGRESS = f"{DOMAIN}_transfer_progress"
