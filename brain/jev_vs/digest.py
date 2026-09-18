"""Turn a raw tick state into words. Pure functions, no I/O.

Coordinates are relative to the player, y up. Distances are compared to the
visible half-height so the buckets mean the same thing at any zoom.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .questions import Thresholds

SECTORS: list[str] = [
    "north", "north_east", "east", "south_east", "south", "south_west", "west", "north_west",
]

_DISTANCE_WEIGHT = {"touching": 4.0, "close": 2.0, "mid": 1.0, "far": 0.5}
_DISTANCE_ORDER = ["touching", "close", "mid", "far"]
_CHEST_WORDS = ("TREASURE", "CHEST")


def sector_of(dx: float, dy: float) -> str:
    """Compass sector of a point relative to the player; north is +y, clockwise."""
    angle = math.degrees(math.atan2(dx, dy)) % 360.0   # 0 = north, 90 = east
    return SECTORS[int((angle + 22.5) // 45) % 8]


def distance_bucket(dist: float, half_h: float, th: Thresholds) -> str:
    frac = dist / half_h if half_h > 0 else float("inf")
    if frac < th.touching:
        return "touching"
    if frac < th.close:
        return "close"
    if frac < th.mid:
        return "mid"
    return "far"


def pressure_bucket(weight: float, th: Thresholds) -> str:
    if weight <= 0:
        return "none"
    if weight < th.pressure_light:
        return "light"
    if weight < th.pressure_moderate:
        return "moderate"
    return "heavy"


def gems_bucket(n: int, th: Thresholds) -> str:
    if n <= 0:
        return "none"
    if n <= th.gems_few:
        return "few"
    return "many"


def hp_bucket(hp: float, max_hp: float, th: Thresholds) -> str:
    ratio = hp / max_hp if max_hp > 0 else 0.0
    if ratio < th.hp_critical:
        return "critical"
    if ratio < th.hp_low:
        return "low"
    if ratio < th.hp_ok:
        return "ok"
    return "full"


@dataclass
class SectorSummary:
    pressure: str = "none"
    nearest: str | None = None
    gems: str = "none"
    boss: bool = False
    chest: bool = False
    enemy_count: int = 0
    gem_count: int = 0
    weight: float = 0.0


@dataclass
class PlayerSummary:
    hp_bucket: str
    hp: float
    max_hp: float
    level: int
    minute: int
    weapons: list[str] = field(default_factory=list)
    passives: list[str] = field(default_factory=list)


@dataclass
class Digest:
    player: PlayerSummary
    sectors: dict[str, SectorSummary]

    def to_dict(self) -> dict:
        return {"player": asdict(self.player), "sectors": {k: asdict(v) for k, v in self.sectors.items()}}


def _equip_words(items: list[dict]) -> list[str]:
    return [f"{it.get('id', '?')} L{it.get('level', '?')}" for it in items]


def digest_state(state: dict, th: Thresholds) -> Digest:
    p = state.get("player", {})
    half_h = float(state.get("screen", {}).get("half_h", 1.0)) or 1.0
    sectors = {name: SectorSummary() for name in SECTORS}

    for e in state.get("enemies", []):
        dx, dy = float(e.get("x", 0.0)), float(e.get("y", 0.0))
        s = sectors[sector_of(dx, dy)]
        bucket = distance_bucket(math.hypot(dx, dy), half_h, th)
        s.enemy_count += 1
        s.weight += _DISTANCE_WEIGHT[bucket]
        if s.nearest is None or _DISTANCE_ORDER.index(bucket) < _DISTANCE_ORDER.index(s.nearest):
            s.nearest = bucket
        if e.get("boss"):
            s.boss = True

    for g in state.get("gems", []):
        sectors[sector_of(float(g.get("x", 0.0)), float(g.get("y", 0.0)))].gem_count += 1

    for pk in state.get("pickups", []):
        kind = str(pk.get("kind", "")).upper()
        if any(w in kind for w in _CHEST_WORDS):
            sectors[sector_of(float(pk.get("x", 0.0)), float(pk.get("y", 0.0)))].chest = True

    for s in sectors.values():
        s.pressure = pressure_bucket(s.weight, th)
        s.gems = gems_bucket(s.gem_count, th)

    player = PlayerSummary(
        hp_bucket=hp_bucket(float(p.get("hp", 0.0)), float(p.get("max_hp", 0.0)), th),
        hp=float(p.get("hp", 0.0)),
        max_hp=float(p.get("max_hp", 0.0)),
        level=int(p.get("level", 0)),
        minute=int(p.get("minute", 0)),
        weapons=_equip_words(p.get("weapons", [])),
        passives=_equip_words(p.get("passives", [])),
    )
    return Digest(player=player, sectors=sectors)
