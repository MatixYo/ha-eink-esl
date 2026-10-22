"""Known ESL panel sizes and display type codes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PanelColors = Literal["bw", "bwr", "bwry"]


@dataclass(frozen=True, slots=True)
class Panel:
    """One shelf-label panel model.

    Pixel sizes are the usual ESL panels for these diagonals. The type code is
    what the display command sends; some batches ship a different resolution
    under the same size name, so callers may still override width/height later.
    """

    id: str
    label: str
    type_code: int
    width: int
    height: int
    colors: PanelColors


PANELS: tuple[Panel, ...] = (
    Panel("bwr-154", '1.54" BWR', 0x01, 200, 200, "bwr"),
    Panel("bwry-154", '1.54" BWRY', 0x02, 200, 200, "bwry"),
    Panel("bwr-213", '2.13" BWR', 0x03, 250, 122, "bwr"),
    Panel("bw-213", '2.13" BW', 0x03, 250, 122, "bw"),
    Panel("bwry-213", '2.13" BWRY', 0x04, 250, 122, "bwry"),
    Panel("bwr-266", '2.66" BWR', 0x05, 296, 152, "bwr"),
    Panel("bwry-266", '2.66" BWRY', 0x06, 296, 152, "bwry"),
    Panel("bwr-290", '2.90" BWR', 0x07, 296, 128, "bwr"),
    Panel("bwry-290", '2.90" BWRY', 0x08, 296, 128, "bwry"),
    Panel("bwr-350", '3.50" BWR', 0x09, 384, 184, "bwr"),
    Panel("bwry-350", '3.50" BWRY', 0x0A, 384, 184, "bwry"),
    Panel("bwr-420", '4.20" BWR', 0x0B, 400, 300, "bwr"),
    Panel("bwry-420", '4.20" BWRY', 0x0F, 400, 300, "bwry"),
    Panel("bwr-750", '7.50" BWR', 0x0D, 800, 480, "bwr"),
    Panel("bwry-750", '7.50" BWRY', 0x10, 800, 480, "bwry"),
)

DEFAULT_PANEL_ID = "bwry-350"

_PANELS_BY_ID = {panel.id: panel for panel in PANELS}


def panel_by_id(panel_id: str) -> Panel:
    """Return the panel for ``panel_id``, falling back to the default model."""
    return _PANELS_BY_ID.get(panel_id) or _PANELS_BY_ID[DEFAULT_PANEL_ID]
