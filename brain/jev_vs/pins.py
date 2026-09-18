"""Human-pinned character and stage, and the menu rosters the dashboard offers.

Holds no policy: this module only remembers what a human asked for and what a menu
offered. Whether a pin is honourable for a given menu is server.py's call, because
that is where the options and the event log are (spec section 3.2).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

PIN_KINDS = ("character", "stage")


def _clean_options(options) -> list[dict]:
    """Reduce an option list to the {id, name} pairs a dropdown needs, dropping anything malformed."""
    out: list[dict] = []
    for o in options if isinstance(options, list) else []:
        if not isinstance(o, dict):
            continue
        oid = o.get("id")
        if isinstance(oid, str) and oid:
            out.append({"id": oid, "name": str(o.get("name", oid))})
    return out


class PinStore:
    """The two pins plus the last option list seen per kind, persisted as one JSON file.

    The roster cache exists because the brain only learns which characters and stages are
    unlocked when the matching menu opens. Without it the dashboard's dropdowns would be
    empty until the first run of the session.

    `path` of None means an in-memory store that never touches the disk; the tests and any
    caller that has no state file use it.
    """

    def __init__(self, path: Path | None = None):
        self._path = Path(path) if path is not None else None
        self.pins: dict[str, str | None] = {k: None for k in PIN_KINDS}
        self.rosters: dict[str, list[dict]] = {k: [] for k in PIN_KINDS}

    @property
    def path(self) -> Path | None:
        return self._path

    def load(self) -> None:
        """Read the state file if there is one. Missing, corrupt, unreadable and wrong-shaped all
        degrade to an empty store and a warning: a bad state file must never stop the brain from
        playing (spec section 3.2)."""
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("state file must hold a JSON object")
        except (OSError, ValueError) as e:
            log.warning("ignoring unreadable pin state %s: %s", self._path, e)
            return
        pins = data.get("pins") if isinstance(data.get("pins"), dict) else {}
        rosters = data.get("rosters") if isinstance(data.get("rosters"), dict) else {}
        for kind in PIN_KINDS:
            value = pins.get(kind)
            self.pins[kind] = value if isinstance(value, str) and value else None
            self.rosters[kind] = _clean_options(rosters.get(kind))

    def save(self) -> None:
        """Best effort: a state file we cannot write is a warning, never a crash."""
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except OSError as e:
            log.warning("could not write pin state %s: %s", self._path, e)

    def to_dict(self) -> dict:
        return {"pins": dict(self.pins), "rosters": {k: list(v) for k, v in self.rosters.items()}}

    def pin_for(self, kind: str) -> str | None:
        return self.pins.get(kind)

    def set_pin(self, kind: str, option_id: str | None) -> bool:
        """Pin `kind` to a game id, or clear it with None. False means the request was ignored."""
        if kind not in PIN_KINDS:
            return False
        if option_id is not None and (not isinstance(option_id, str) or not option_id):
            return False
        self.pins[kind] = option_id
        self.save()
        return True

    def remember_options(self, kind: str, options: list[dict]) -> list[dict]:
        """Cache what a menu offered so the dashboard can list it; returns the cached form."""
        if kind not in PIN_KINDS:
            return []
        self.rosters[kind] = _clean_options(options)
        self.save()
        return self.rosters[kind]

    def index_of(self, kind: str, options: list[dict]) -> int | None:
        """Index of the pinned option in `options`; None when nothing is pinned, or when the pin
        is not on offer. The pin is left alone either way — a character you are about to unlock
        stays pinned (spec section 3.3)."""
        pinned = self.pin_for(kind)
        if not pinned:
            return None
        for i, o in enumerate(options):
            if isinstance(o, dict) and o.get("id") == pinned:
                return i
        return None
