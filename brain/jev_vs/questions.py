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
    xp_partway: float = 0.25
    xp_close: float = 0.6
    xp_imminent: float = 0.9
    blocked_move: float = 0.05
    block_memory_s: float = 3.0
    stuck_window_s: float = 2.0
    stuck_move_frac: float = 0.1


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
    "quarter second, described by what lies that way. "
    "Never choose a direction described as blocked: the survivor cannot move that way at all. "
    "If the state says you are shuffling in place, commit to a single direction that is not blocked "
    "and keep choosing it until the survivor is clear. "
    "Never walk into heavy or touching enemy pressure. "
    "When hp is critical, choose the safest direction and ignore everything else. "
    "When hp is low, go for healing if a direction has it and its pressure is none or light, "
    "otherwise choose the safest direction. "
    "When hp is ok or full, prefer a direction with gems whose pressure is none or light, and prefer "
    "gems more strongly when a level up is close or imminent, because leveling up is how the survivor "
    "gets stronger. Chests, coffin unlocks and relics are worth walking to when that direction's "
    "pressure is none or light. Coins are the lowest priority and never worth a detour. "
    "Avoid a direction with a boss unless hp is full. "
    "Choose stay only when every direction is worse than standing still."
)


# Pickup kind (as the game reports it) -> word category Jev is shown.
PICKUP_CATEGORIES: dict[str, str] = {
    "TREASURE": "chest", "STATS_TREASURE_1": "chest", "STATS_TREASURE_2": "chest", "STATS_TREASURE_3": "chest",
    "COFFIN": "unlock", "COFFINX": "unlock", "COFFIN_EMPTY": "unlock",
    "MOONGATE": "relic", "MERCHANT": "relic", "DIRECTER": "relic", "EGGMAN": "relic", "COSMO_PAVONE": "relic",
    "ROAST": "healing", "ALWAYS_ROAST": "healing", "LITTLEHEART": "healing", "HEALER": "healing",
    "PURIFY": "healing", "PURIFY2": "healing",
    "VACUUM": "power", "ROSARY": "power", "ROSARYX": "power", "OROLOGION": "power", "CLOVER": "power", "GILDED": "power",
    "COIN": "coins", "COINBAG1": "coins", "COINBAG2": "coins", "COINBAGMAX": "coins", "ALWAYS_COINBAG2": "coins", "NFT": "coins",
}

_OBJECT_TEXT: dict[str, str] = {
    "chest": "a chest is here",
    "unlock": "a coffin unlock is here",
    "relic": "a relic is here",
    "healing": "healing is here",
    "power": "a power-up is here",
    "coins": "coins are here",
    "item": "an item is here",
}


def pickup_category(kind: str) -> str:
    """Word category for a pickup's kind. Unknown or empty kinds, and anything else, are just 'item'."""
    k = str(kind or "").strip().upper()
    if not k:
        return "item"
    if k in PICKUP_CATEGORIES:
        return PICKUP_CATEGORIES[k]
    if k.startswith("RELIC"):
        return "relic"
    return "item"


def sector_text(s: SectorSummary) -> str:
    """Words only. Never a digit."""
    parts: list[str] = []
    if s.blocked:
        parts.append("blocked, the survivor cannot get through that way")
    if s.enemy_count == 0 and s.gem_count == 0 and not s.objects and not s.boss:
        parts.append("no enemies, no gems")
        return ", ".join(parts)
    if s.enemy_count == 0:
        parts.append("no enemies")
    else:
        parts.append(f"{s.pressure} enemy pressure, nearest enemy {s.nearest}")
    parts.append("no gems" if s.gems == "none" else f"{s.gems} gems")
    if s.boss:
        parts.append("a boss is here")
    for category in s.objects:
        parts.append(_OBJECT_TEXT.get(category, "an item is here"))
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
    player_state = {
        "hp": d.player.hp_bucket,
        "level_progress": d.player.xp_bucket,
        "minute_of_run": _minute_words(d.player.minute),
        "weapons": d.player.weapons,
        "passives": d.player.passives,
    }
    if d.player.stuck:
        player_state["movement"] = "you are shuffling in place and not getting anywhere"
    state = {
        "player": player_state,
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

# Kinds where the run history is fed back in, so the same pick isn't made every time.
VARIETY_KINDS = ("character", "stage")
VARIETY_INSTRUCTIONS = (
    " The recently_played list shows what was picked in recent runs, most recent first. Prefer an "
    "option that does not appear in recently_played; only repeat one when every option was played recently."
)


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


def _build_item_text(item) -> str:
    """A build entry as words: dict-shaped items (the wire format) show id and level; anything else is str()'d."""
    if isinstance(item, dict):
        return f"{item.get('id', '?')} L{item.get('level', '?')}"
    return str(item)


def options_question(kind: str, options: list[dict], build: dict | None, recent: list[str] | None = None) -> Ask:
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
            "weapons": [_build_item_text(w) for w in build.get("weapons", [])],
            "passives": [_build_item_text(p) for p in build.get("passives", [])],
            "run_phase": _minute_words(int(build.get("minute", 0))),
        }
    instructions = _PICK_INSTRUCTIONS[kind]
    if kind in VARIETY_KINDS and recent:
        state["recently_played"] = list(recent)
        instructions = instructions + VARIETY_INSTRUCTIONS
    return Ask(
        name=kind,
        state=state,
        question=Choice(instructions=instructions, criteria=criteria),
        keys=keys,
        instructions=instructions,
        labels=labels,
    )
