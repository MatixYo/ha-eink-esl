"""Transfer progress reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TransferPhase = Literal["clear", "start", "chunks", "display"]


@dataclass(frozen=True, slots=True)
class TransferProgress:
    phase: TransferPhase
    sent: int
    total: int
