"""Turn a raw tick state into words. Pure functions, no I/O.

Coordinates are relative to the player, y up. Distances are compared to the
visible half-height so the buckets mean the same thing at any zoom.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .questions import Thresholds, pickup_category

SECTORS: list[str] = [
    "north", "north_east", "east", "south_east", "south", "south_west", "west", "north_west",
]

_DISTANCE_WEIGHT = {"touching": 4.0, "close": 2.0, "mid": 1.0, "far": 0.5}
_DISTANCE_ORDER = ["touching", "close", "mid", "far"]


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


def xp_bucket(xp: float, xp_to_next: float, th: Thresholds) -> str:
    if xp_to_next <= 0:
        return "just levelled"
    frac = xp / xp_to_next
    if frac < th.xp_partway:
        return "just levelled"
    if frac < th.xp_close:
        return "partway to the next level"
    if frac < th.xp_imminent:
        return "close to the next level"
    return "a level up is imminent"


@dataclass
class SectorSummary:
    pressure: str = "none"
    nearest: str | None = None
    gems: str = "none"
    boss: bool = False
    objects: list[str] = field(default_factory=list)
    blocked: bool = False
    enemy_count: int = 0
    gem_count: int = 0
    weight: float = 0.0

    @property
    def chest(self) -> bool:
        """Kept for anything that still expects the old boolean flag; derived from objects."""
        return "chest" in self.objects


@dataclass
class PlayerSummary:
    hp_bucket: str
    hp: float
    max_hp: float
    level: int
    minute: int
    xp_bucket: str = "just levelled"
    stuck: bool = False
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


class BlockMemory:
    """Remembers which compass directions recently failed to move the survivor, and whether the
    survivor is stuck shuffling in place.

    A block expires on time only -- never because the survivor moved away in some other
    direction. Walking east along a long wall does not make north passable again; the wall is
    still there. If a block were forgotten just because the player is now making progress in a
    different direction, whatever originally pulled the survivor toward the wall would pull it
    straight back the moment it let go, and the survivor would shuffle back and forth against the
    wall forever -- exactly the bug this class exists to fix. So blocks only clear once
    `Thresholds.block_memory_s` of run-clock time has passed since they were last (re)recorded.
    """

    def __init__(self, th: Thresholds) -> None:
        self._th = th
        self._blocked_at: dict[str, float] = {}
        self._trail: list[tuple[float, float, float, str | None]] = []   # (seconds, x, y, applied_direction)

    def record(self, direction: str, now: float) -> None:
        """Remember (or refresh) that `direction` failed to move the survivor at run-clock `now`."""
        self._blocked_at[direction] = now

    def blocked(self, now: float) -> set[str]:
        """Every direction whose most recent block is still within block_memory_s of `now`."""
        return {d for d, t in self._blocked_at.items() if now - t < self._th.block_memory_s}

    def note_position(self, seconds: float, x: float, y: float, applied_direction: str | None) -> None:
        """Feed one tick's position sample; drops anything older than stuck_window_s."""
        self._trail.append((seconds, x, y, applied_direction))
        cutoff = seconds - self._th.stuck_window_s
        self._trail = [sample for sample in self._trail if sample[0] >= cutoff]

    def is_stuck(self, half_h: float, th: Thresholds) -> bool:
        """True when the trail spans the full stuck window, barely moved, and wasn't just standing still."""
        if not self._trail:
            return False
        oldest, newest = self._trail[0], self._trail[-1]
        if newest[0] - oldest[0] < th.stuck_window_s:
            return False
        dist = math.hypot(newest[1] - oldest[1], newest[2] - oldest[2])
        frac = dist / half_h if half_h > 0 else float("inf")
        if frac >= th.stuck_move_frac:
            return False
        return any(sample[3] in SECTORS for sample in self._trail)

    def clear(self) -> None:
        """Forget everything; call at the start of a new run."""
        self._blocked_at.clear()
        self._trail.clear()


def digest_state(state: dict, th: Thresholds, memory: BlockMemory | None = None) -> Digest:
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
        category = pickup_category(pk.get("kind", ""))
        sectors[sector_of(float(pk.get("x", 0.0)), float(pk.get("y", 0.0)))].objects.append(category)

    applied_direction = p.get("applied_direction")
    moved = p.get("moved")
    newly_blocked = applied_direction in SECTORS and moved is not None and float(moved) < th.blocked_move

    stuck = False
    if memory is not None:
        seconds = float(p.get("seconds", 0.0))
        if newly_blocked:
            memory.record(applied_direction, seconds)
        memory.note_position(seconds, float(p.get("x", 0.0)), float(p.get("y", 0.0)), applied_direction)
        for name in memory.blocked(seconds):
            if name in sectors:
                sectors[name].blocked = True
        stuck = memory.is_stuck(half_h, th)
    elif newly_blocked:
        sectors[applied_direction].blocked = True

    for s in sectors.values():
        s.pressure = pressure_bucket(s.weight, th)
        s.gems = gems_bucket(s.gem_count, th)
        s.objects = sorted(set(s.objects))

    player = PlayerSummary(
        hp_bucket=hp_bucket(float(p.get("hp", 0.0)), float(p.get("max_hp", 0.0)), th),
        hp=float(p.get("hp", 0.0)),
        max_hp=float(p.get("max_hp", 0.0)),
        level=int(p.get("level", 0)),
        minute=int(p.get("minute", 0)),
        xp_bucket=xp_bucket(float(p.get("xp", 0.0)), float(p.get("xp_to_next", 0.0)), th),
        stuck=stuck,
        weapons=_equip_words(p.get("weapons", [])),
        passives=_equip_words(p.get("passives", [])),
    )
    return Digest(player=player, sectors=sectors)
