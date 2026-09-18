"""Every Jev question the brain asks, and every threshold behind its wording.

This is the file a human reviews. Nothing here does I/O. Jev is bad at
numbers, so this module only ever hands it words (spec section 5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from typesafe_sdk import Choice

if TYPE_CHECKING:  # digest imports Thresholds from here; keep the runtime import one-way
    from .digest import Digest, SectorSummary


# ----------------------------------------------------------------- thresholds

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


# ----------------------------------------------------------------- directions

_D = 1 / math.sqrt(2)
DIRECTIONS: list[str] = [
    "north", "north_east", "east", "south_east", "south", "south_west", "west", "north_west", "stay",
]
DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "north": (0.0, 1.0), "north_east": (_D, _D), "east": (1.0, 0.0), "south_east": (_D, -_D),
    "south": (0.0, -1.0), "south_west": (-_D, -_D), "west": (-1.0, 0.0), "north_west": (-_D, _D),
    "stay": (0.0, 0.0),
}

DIRECTION_INSTRUCTIONS = (
    "You steer the survivor in a top-down arena. Each option is a direction to walk for the next "
    "quarter second, described by what lies that way. Walk away from heavy or touching enemy pressure "
    "and never walk into it. When the player's hp is critical or low, choose safety over gems. "
    "When hp is ok or full, prefer the direction with gems as long as its pressure is none or light. "
    "Prefer chests and avoid bosses unless hp is full. Choose stay only when every direction is worse than standing still."
)


def sector_text(s: SectorSummary) -> str:
    """Words only. Never a digit."""
    if s.enemy_count == 0 and s.gem_count == 0 and not s.chest and not s.boss:
        return "no enemies, no gems"
    parts: list[str] = []
    if s.enemy_count == 0:
        parts.append("no enemies")
    else:
        parts.append(f"{s.pressure} enemy pressure, nearest enemy {s.nearest}")
    parts.append("no gems" if s.gems == "none" else f"{s.gems} gems")
    if s.boss:
        parts.append("a boss is here")
    if s.chest:
        parts.append("a chest is here")
    return ", ".join(parts)


@dataclass(frozen=True)
class Ask:
    """One question ready for JevClient.ask plus the bookkeeping to apply its answer."""
    name: str
    state: dict
    question: Choice
    keys: list[str]                 # criteria keys in option order
    instructions: str
    labels: dict[str, str]          # key -> short human label for the dashboard


def direction_question(d: Digest) -> Ask:
    criteria = {name: sector_text(d.sectors[name]) for name in DIRECTIONS if name != "stay"}
    criteria["stay"] = "stand still where the player is now"
    state = {
        "player": {
            "hp": d.player.hp_bucket,
            "minute_of_run": _minute_words(d.player.minute),
            "weapons": d.player.weapons,
            "passives": d.player.passives,
        },
        "surroundings": {name: criteria[name] for name in DIRECTIONS if name != "stay"},
    }
    return Ask(
        name="direction",
        state=state,
        question=Choice(instructions=DIRECTION_INSTRUCTIONS, criteria=criteria),
        keys=list(DIRECTIONS),
        instructions=DIRECTION_INSTRUCTIONS,
        labels={k: k.replace("_", " ") for k in DIRECTIONS},
    )


def _minute_words(minute: int) -> str:
    if minute < 3:
        return "early, first few minutes"
    if minute < 10:
        return "early-mid run"
    if minute < 20:
        return "mid run, enemies getting dense"
    return "late run, very dangerous"


# ----------------------------------------------------------------- picks

LEVEL_UP_INSTRUCTIONS = (
    "The survivor just levelled up and may take exactly one of these upgrades. Pick the one that most "
    "strengthens the current build: prefer levelling weapons already owned, prefer an upgrade marked "
    "evolution ready, and prefer passives that boost the owned weapons. A new weapon is good early in the "
    "run when few weapons are owned, and bad late when slots are precious."
)
CHARACTER_INSTRUCTIONS = (
    "Pick the character to play a full run with. Prefer characters whose starting weapon and bonus make "
    "surviving thirty minutes easiest for a cautious player."
)
STAGE_INSTRUCTIONS = (
    "Pick the stage to play. Prefer the stage that is most forgiving for a cautious player: open space, "
    "slow early enemies, and no instant-death mechanics."
)

_PICK_INSTRUCTIONS = {
    "level_up": LEVEL_UP_INSTRUCTIONS,
    "weapon_select": LEVEL_UP_INSTRUCTIONS,
    "arcana_select": LEVEL_UP_INSTRUCTIONS,
    "character": CHARACTER_INSTRUCTIONS,
    "stage": STAGE_INSTRUCTIONS,
}


def _option_description(kind: str, o: dict) -> str:
    bits: list[str] = [str(o.get("name", o.get("id", "?")))]
    if kind in ("level_up", "weapon_select"):
        bits.append(str(o.get("kind", "item")))
        if o.get("is_new"):
            bits.append("new, not owned yet")
        else:
            bits.append(f"would reach level {o.get('level', '?')}")
        if o.get("evolution_ready"):
            bits.append("evolution ready")
    if kind == "character" and o.get("starting_weapon"):
        bits.append(f"starts with {o['starting_weapon']}")
    desc = str(o.get("description", "")).strip()
    if desc:
        bits.append(desc)
    return "; ".join(bits)


def options_question(kind: str, options: list[dict], build: dict | None) -> Ask:
    if kind not in _PICK_INSTRUCTIONS:
        raise ValueError(f"unknown pick kind {kind!r}")
    keys: list[str] = []
    criteria: dict[str, str] = {}
    labels: dict[str, str] = {}
    for i, o in enumerate(options):
        base = str(o.get("id", f"option_{i}"))
        key = base if base not in criteria else f"{base}_{i + 1}"
        keys.append(key)
        criteria[key] = _option_description(kind, o)
        labels[key] = str(o.get("name", base))
    state: dict = {"decision": kind.replace("_", " ")}
    if build:
        state["build"] = {
            "weapons": list(build.get("weapons", [])),
            "passives": list(build.get("passives", [])),
            "run_phase": _minute_words(int(build.get("minute", 0))),
        }
    instructions = _PICK_INSTRUCTIONS[kind]
    return Ask(
        name=kind,
        state=state,
        question=Choice(instructions=instructions, criteria=criteria),
        keys=keys,
        instructions=instructions,
        labels=labels,
    )
