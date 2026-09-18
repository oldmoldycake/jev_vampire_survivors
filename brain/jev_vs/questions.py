"""Temporary stub; Task 3 replaces this file."""
import math

_D = 1 / math.sqrt(2)
DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "north": (0.0, 1.0), "north_east": (_D, _D), "east": (1.0, 0.0), "south_east": (_D, -_D),
    "south": (0.0, -1.0), "south_west": (-_D, -_D), "west": (-1.0, 0.0), "north_west": (-_D, _D),
    "stay": (0.0, 0.0),
}
