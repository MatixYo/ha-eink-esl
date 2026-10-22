"""Integration version from manifest.json (cache-busting for the panel module)."""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST = Path(__file__).with_name("manifest.json")
INTEGRATION_VERSION: str = json.loads(_MANIFEST.read_text(encoding="utf-8"))[
    "version"
]
