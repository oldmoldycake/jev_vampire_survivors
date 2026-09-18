"""Temporary stub; Task 3 replaces this file."""
import math
from dataclasses import dataclass

_D = 1 / math.sqrt(2)
DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "north": (0.0, 1.0), "north_east": (_D, _D), "east": (1.0, 0.0), "south_east": (_D, -_D),
    "south": (0.0, -1.0), "south_west": (-_D, -_D), "west": (-1.0, 0.0), "north_west": (-_D, _D),
    "stay": (0.0, 0.0),
}


@dataclass(frozen=True)
class Thresholds:
    """Every numeric cut-off the brain uses to turn geometry into words.

    Distances are fractions of the visible half-height (screen.half_h).
    Pressure is a distance-weighted enemy count per sector.
    """
    touching: float = 0.15
    close: float = 0.4
    mid: float = 0.8
    pressure_light: float = 3.0
    pressure_moderate: float = 8.0
    gems_few: int = 3
    hp_critical: float = 0.25
    hp_low: float = 0.5
    hp_ok: float = 0.9


DEFAULT_THRESHOLDS = Thresholds()
