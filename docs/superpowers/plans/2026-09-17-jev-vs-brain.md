# Jev Vampire Survivors Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python "brain" that receives raw Vampire Survivors state from the game plugin over TCP, turns it into words, asks Jev, replies with typed actions, logs every decision, and shows them live on a browser dashboard.

**Architecture:** One asyncio process. A TCP server speaks newline-delimited JSON with the game plugin. A `Decider` digests raw state into eight labelled sectors, builds `Choice` questions, calls the TypeSafe SDK with a short timeout, and falls back to a heuristic when Jev is unavailable. Every decision is written to JSONL run logs and published to an in-process hub that an aiohttp WebSocket dashboard streams to browsers. All Jev questions and every threshold live in one module, `jev_vs/questions.py`.

**Tech Stack:** Python 3.12+ (3.14 installed), uv, `typesafe-sdk` 0.6.0 (`AsyncTypeSafeClient`, `Choice`, `RetryPolicy`), `aiohttp` 3.14, `pytest` 9 with `pytest-asyncio` 1.4 in auto mode, stdlib `tomllib`, `asyncio`, `json`.

**Spec:** `docs/superpowers/specs/2026-09-17-jev-vampire-survivors-design.md` (sections 3, 4, 5, 9, 10, 11, 12)

**Companion plan:** `docs/superpowers/plans/2026-09-17-jev-vs-plugin.md` builds the C# plugin that talks to this brain. This plan needs no game install; `scripts/fake_plugin.py` stands in for the plugin.

## Global Constraints

- Python `>=3.12`; run everything with `uv run` from `brain/`.
- Jev never receives raw coordinates or numbers to compare; the brain converts all geometry to words before asking (spec section 5).
- Model id default `jev-latest`; API key from env `TYPESAFE_API_KEY`; the SDK reads it itself.
- Plugin protocol port default `48231`, dashboard port default `48232`, tick rate default `4` Hz, tick reply budget `400` ms, menu reply budget `3000` ms.
- Protocol messages are one JSON object per line, UTF-8; every reply echoes the request `id`; replies carry `source` equal to `jev`, `fallback`, or `reused`.
- Every Jev question and every threshold lives in `brain/jev_vs/questions.py` and nowhere else.
- No test outside `tests/test_live.py` touches the network. `test_live.py` is marked `live` and skipped by default.
- Commit after every task with a message in the form `feat(brain): ...` or `test(brain): ...`.

---

## File Structure

```
brain/
  pyproject.toml              project, deps, pytest config
  config.toml                 runtime defaults the user edits
  jev_vs/
    __init__.py
    config.py                 Config dataclass + load_config(path)
    protocol.py               decode/encode lines, reply builders, ProtocolError
    questions.py              Thresholds, DIRECTIONS, vectors, wording, Ask builders  <- humans review this
    digest.py                 geometry -> SectorSummary/PlayerSummary/Digest
    jev_client.py             JevClient wrapping AsyncTypeSafeClient, ChoicePick, JevResult
    decide.py                 Decision, Decider, fallbacks
    runlog.py                 RunLog: JSONL writers per run
    hub.py                    Hub: fan-out queues for dashboard clients
    stats.py                  Stats: counters, latency, cost
    server.py                 PluginServer: TCP protocol loop
    dashboard.py              aiohttp app: GET /, GET /ws
    static/index.html         the dashboard page
    __main__.py               CLI entry: python -m jev_vs [--config path]
  tests/
    conftest.py               shared fixtures: sample states, FakeJev
    test_protocol.py
    test_digest.py
    test_questions.py
    test_decide.py
    test_runlog.py
    test_hub_stats.py
    test_server.py
    test_dashboard.py
    test_live.py
scripts/
  fake_plugin.py              replays ticks/events to a running brain
```

---

### Task 1: Project scaffold and protocol codec

**Files:**
- Create: `brain/pyproject.toml`
- Create: `brain/config.toml`
- Create: `brain/jev_vs/__init__.py`
- Create: `brain/jev_vs/protocol.py`
- Create: `brain/jev_vs/config.py`
- Create: `brain/tests/__init__.py` (empty)
- Create: `brain/tests/test_protocol.py`
- Create: `brain/tests/test_config.py`

**Interfaces:**
- Produces: `protocol.decode(line: bytes) -> dict`, `protocol.encode(msg: dict) -> bytes`, `protocol.ProtocolError(ValueError)`, `protocol.move_reply(id, choice, probabilities, confidence, source) -> dict`, `protocol.pick_reply(id, index, choice, probabilities, confidence, source) -> dict`, `protocol.noop_reply(id) -> dict`, `protocol.control(automation: bool) -> dict`
- Produces: `config.Config` (frozen dataclass), `config.load_config(path: Path | None) -> Config`
- Consumes: `questions.DIRECTION_VECTORS` (Task 3) via a lazy import inside `move_reply`; until Task 3 exists the test below defines the expected vectors itself, so write `protocol.py` exactly as shown and it will pass once Task 3 lands. To keep Task 1 green on its own, `move_reply` imports `DIRECTION_VECTORS` lazily and the Task 1 test only checks `north`, `stay`, and `north_east`, which Task 1 defines in a temporary `questions.py` stub created in Step 3.

- [ ] **Step 1: Create the project files**

`brain/pyproject.toml`:

```toml
[project]
name = "jev-vs"
version = "0.1.0"
description = "Jev plays Vampire Survivors: the decision brain"
requires-python = ">=3.12"
dependencies = [
    "typesafe-sdk>=0.6.0",
    "aiohttp>=3.14",
]

[project.scripts]
jev-vs = "jev_vs.__main__:main"

[dependency-groups]
dev = [
    "pytest>=9",
    "pytest-asyncio>=1.4",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["live: calls the real TypeSafe API (needs TYPESAFE_API_KEY)"]
addopts = "-m 'not live'"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["jev_vs"]
```

`brain/config.toml`:

```toml
# Runtime settings for the Jev Vampire Survivors brain.
# Question wording and thresholds are NOT here: see jev_vs/questions.py.

[plugin]
host = "127.0.0.1"
port = 48231

[dashboard]
host = "127.0.0.1"
port = 48232

[brain]
tick_hz = 4.0
model = "jev-latest"
request_timeout_s = 0.8
max_retries = 1
log_dir = "runs"
```

`brain/jev_vs/__init__.py`:

```python
"""Jev plays Vampire Survivors: the decision brain."""
```

`brain/tests/__init__.py`: empty file.

- [ ] **Step 2: Write the failing protocol and config tests**

`brain/tests/test_protocol.py`:

```python
import json

import pytest

from jev_vs import protocol


def test_decode_parses_json_object():
    msg = protocol.decode(b'{"id": 3, "type": "tick", "state": {}}\n')
    assert msg == {"id": 3, "type": "tick", "state": {}}


def test_decode_rejects_bad_json():
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(b"{not json\n")


def test_decode_rejects_missing_type():
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(b'{"id": 1}\n')


def test_encode_appends_newline_and_is_single_line():
    out = protocol.encode({"type": "noop", "id": 1})
    assert out.endswith(b"\n")
    assert out.count(b"\n") == 1
    assert json.loads(out) == {"type": "noop", "id": 1}


def test_move_reply_has_unit_vector_and_echoes_id():
    reply = protocol.move_reply(7, "north", {"north": 0.9, "stay": 0.1}, 0.8, "jev")
    assert reply["type"] == "move"
    assert reply["id"] == 7
    assert (reply["dx"], reply["dy"]) == (0.0, 1.0)
    assert reply["choice"] == "north"
    assert reply["source"] == "jev"


def test_move_reply_stay_is_zero_vector():
    reply = protocol.move_reply(1, "stay", {"stay": 1.0}, 1.0, "fallback")
    assert (reply["dx"], reply["dy"]) == (0.0, 0.0)


def test_move_reply_diagonal_is_normalised():
    reply = protocol.move_reply(1, "north_east", {"north_east": 1.0}, 1.0, "jev")
    assert reply["dx"] == pytest.approx(0.7071, abs=1e-3)
    assert reply["dy"] == pytest.approx(0.7071, abs=1e-3)


def test_pick_reply_carries_index():
    reply = protocol.pick_reply(9, 2, "SPINACH", {"SPINACH": 0.6, "WHIP": 0.4}, 0.3, "jev")
    assert reply == {
        "id": 9, "type": "pick", "index": 2, "choice": "SPINACH",
        "probabilities": {"SPINACH": 0.6, "WHIP": 0.4}, "confidence": 0.3, "source": "jev",
    }


def test_noop_and_control():
    assert protocol.noop_reply(4) == {"id": 4, "type": "noop"}
    assert protocol.control(False) == {"type": "control", "automation": False}
```

`brain/tests/test_config.py`:

```python
from pathlib import Path

from jev_vs.config import Config, load_config


def test_defaults_when_no_file():
    cfg = load_config(None)
    assert cfg.plugin_port == 48231
    assert cfg.dashboard_port == 48232
    assert cfg.tick_hz == 4.0
    assert cfg.model == "jev-latest"
    assert cfg.log_dir == "runs"


def test_file_overrides_defaults(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[plugin]\nport = 5000\n[brain]\ntick_hz = 2.5\nmodel = "jev-1.13.0"\n')
    cfg = load_config(p)
    assert cfg.plugin_port == 5000
    assert cfg.tick_hz == 2.5
    assert cfg.model == "jev-1.13.0"
    assert cfg.dashboard_port == 48232


def test_config_is_frozen():
    cfg = Config()
    try:
        cfg.tick_hz = 1.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Config must be frozen")
```

- [ ] **Step 3: Run tests to verify they fail**

Run from `brain/`: `uv sync && uv run pytest tests/test_protocol.py tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jev_vs.protocol'` (and the config equivalent).

- [ ] **Step 4: Implement protocol.py, config.py, and a temporary questions stub**

`brain/jev_vs/protocol.py`:

```python
"""Line protocol between the game plugin and the brain.

One JSON object per line. Replies echo the request id. See spec section 4.
"""
from __future__ import annotations

import json


class ProtocolError(ValueError):
    """Raised for lines that are not a JSON object with a string 'type'."""


def decode(line: bytes) -> dict:
    try:
        msg = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ProtocolError(f"bad json: {e}") from e
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise ProtocolError("message must be an object with a string 'type'")
    return msg


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def move_reply(id: int, choice: str, probabilities: dict[str, float], confidence: float, source: str) -> dict:
    from .questions import DIRECTION_VECTORS  # lazy: questions imports nothing from protocol

    dx, dy = DIRECTION_VECTORS[choice]
    return {
        "id": id, "type": "move", "dx": dx, "dy": dy, "choice": choice,
        "probabilities": probabilities, "confidence": confidence, "source": source,
    }


def pick_reply(id: int, index: int, choice: str, probabilities: dict[str, float], confidence: float, source: str) -> dict:
    return {
        "id": id, "type": "pick", "index": index, "choice": choice,
        "probabilities": probabilities, "confidence": confidence, "source": source,
    }


def noop_reply(id: int) -> dict:
    return {"id": id, "type": "noop"}


def control(automation: bool) -> dict:
    return {"type": "control", "automation": automation}
```

`brain/jev_vs/questions.py` (temporary stub, replaced in Task 3):

```python
"""Temporary stub; Task 3 replaces this file."""
import math

_D = 1 / math.sqrt(2)
DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "north": (0.0, 1.0), "north_east": (_D, _D), "east": (1.0, 0.0), "south_east": (_D, -_D),
    "south": (0.0, -1.0), "south_west": (-_D, -_D), "west": (-1.0, 0.0), "north_west": (-_D, _D),
    "stay": (0.0, 0.0),
}
```

`brain/jev_vs/config.py`:

```python
"""Runtime configuration loaded from config.toml. Thresholds live in questions.py."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Config:
    plugin_host: str = "127.0.0.1"
    plugin_port: int = 48231
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 48232
    tick_hz: float = 4.0
    model: str = "jev-latest"
    request_timeout_s: float = 0.8
    max_retries: int = 1
    log_dir: str = "runs"


def load_config(path: Path | None) -> Config:
    cfg = Config()
    if path is None:
        return cfg
    data = tomllib.loads(Path(path).read_text())
    plugin = data.get("plugin", {})
    dash = data.get("dashboard", {})
    brain = data.get("brain", {})
    return replace(
        cfg,
        plugin_host=plugin.get("host", cfg.plugin_host),
        plugin_port=int(plugin.get("port", cfg.plugin_port)),
        dashboard_host=dash.get("host", cfg.dashboard_host),
        dashboard_port=int(dash.get("port", cfg.dashboard_port)),
        tick_hz=float(brain.get("tick_hz", cfg.tick_hz)),
        model=str(brain.get("model", cfg.model)),
        request_timeout_s=float(brain.get("request_timeout_s", cfg.request_timeout_s)),
        max_retries=int(brain.get("max_retries", cfg.max_retries)),
        log_dir=str(brain.get("log_dir", cfg.log_dir)),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_protocol.py tests/test_config.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/pyproject.toml brain/config.toml brain/jev_vs brain/tests brain/uv.lock
git commit -m "feat(brain): scaffold project with protocol codec and config loader"
```

---

### Task 2: State digest (geometry to words)

**Files:**
- Create: `brain/jev_vs/digest.py`
- Modify: `brain/jev_vs/questions.py` (add `Thresholds` and `DEFAULT_THRESHOLDS` to the stub; Task 3 fills in the rest)
- Create: `brain/tests/conftest.py`
- Create: `brain/tests/test_digest.py`

**Interfaces:**
- Produces: `questions.Thresholds` frozen dataclass with fields `touching=0.15, close=0.4, mid=0.8, pressure_light=3.0, pressure_moderate=8.0, gems_few=3, hp_critical=0.25, hp_low=0.5, hp_ok=0.9`; `questions.DEFAULT_THRESHOLDS`
- Produces: `digest.SECTORS` (list of 8 names, north first, clockwise), `digest.sector_of(dx, dy) -> str`, `digest.distance_bucket(dist, half_h, th) -> str`, `digest.pressure_bucket(weight, th) -> str`, `digest.gems_bucket(n, th) -> str`, `digest.hp_bucket(hp, max_hp, th) -> str`, dataclasses `SectorSummary`, `PlayerSummary`, `Digest` (with `to_dict()`), `digest.digest_state(state: dict, th: Thresholds) -> Digest`
- Consumes: raw tick `state` shape from spec section 4.

- [ ] **Step 1: Add Thresholds to the questions stub**

Append to `brain/jev_vs/questions.py`:

```python
from dataclasses import dataclass


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
```

- [ ] **Step 2: Write shared fixtures and the failing digest tests**

`brain/tests/conftest.py`:

```python
import pytest


def make_state(enemies=(), gems=(), pickups=(), hp=80, max_hp=100, level=5, minute=3):
    return {
        "player": {
            "x": 0.0, "y": 0.0, "hp": hp, "max_hp": max_hp, "level": level, "xp": 10, "xp_to_next": 50,
            "minute": minute, "seconds": minute * 60, "character": "ANTONIO",
            "weapons": [{"id": "WHIP", "level": 3, "max": False}],
            "passives": [{"id": "SPINACH", "level": 1, "max": False}],
        },
        "enemies": [dict(e) for e in enemies],
        "gems": [dict(g) for g in gems],
        "pickups": [dict(p) for p in pickups],
        "screen": {"half_w": 8.0, "half_h": 4.0},
    }


def enemy(x, y, boss=False, type="BAT", hp=10):
    return {"x": x, "y": y, "hp": hp, "type": type, "boss": boss}


def gem(x, y, value=1):
    return {"x": x, "y": y, "value": value}


@pytest.fixture
def empty_state():
    return make_state()


class FakeJev:
    """Stands in for JevClient. `script` maps question name -> (choice, probabilities, confidence)."""

    def __init__(self, script=None, fail=False, latency_ms=12.0):
        self.script = script or {}
        self.fail = fail
        self.latency_ms = latency_ms
        self.calls = []

    async def ask(self, state, questions):
        from jev_vs.jev_client import ChoicePick, JevResult

        self.calls.append((state, questions))
        if self.fail:
            raise RuntimeError("jev down")
        answers = {}
        for name, q in questions.items():
            keys = list(q.criteria.keys())
            if name in self.script:
                choice, probs, conf = self.script[name]
            else:
                choice, probs, conf = keys[0], {k: (1.0 if k == keys[0] else 0.0) for k in keys}, 1.0
            answers[name] = ChoicePick(choice=choice, probabilities=probs, confidence=conf)
        return JevResult(answers=answers, latency_ms=self.latency_ms, input_tokens=100)

    async def aclose(self):
        return None


@pytest.fixture
def fake_jev():
    return FakeJev()
```

`brain/tests/test_digest.py`:

```python
import pytest

from jev_vs import digest
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from tests.conftest import enemy, gem, make_state


def test_sectors_are_eight_clockwise_from_north():
    assert digest.SECTORS == [
        "north", "north_east", "east", "south_east", "south", "south_west", "west", "north_west",
    ]


@pytest.mark.parametrize("dx,dy,expected", [
    (0, 1, "north"), (1, 1, "north_east"), (1, 0, "east"), (1, -1, "south_east"),
    (0, -1, "south"), (-1, -1, "south_west"), (-1, 0, "west"), (-1, 1, "north_west"),
    (0.3, 1, "north"), (1, 0.3, "east"),
])
def test_sector_of(dx, dy, expected):
    assert digest.sector_of(dx, dy) == expected


def test_distance_buckets_are_fractions_of_half_height():
    assert digest.distance_bucket(0.2, 4.0, TH) == "touching"   # 0.05
    assert digest.distance_bucket(1.0, 4.0, TH) == "close"      # 0.25
    assert digest.distance_bucket(2.4, 4.0, TH) == "mid"        # 0.6
    assert digest.distance_bucket(4.0, 4.0, TH) == "far"        # 1.0


def test_pressure_buckets():
    assert digest.pressure_bucket(0.0, TH) == "none"
    assert digest.pressure_bucket(1.0, TH) == "light"
    assert digest.pressure_bucket(5.0, TH) == "moderate"
    assert digest.pressure_bucket(20.0, TH) == "heavy"


def test_gem_and_hp_buckets():
    assert digest.gems_bucket(0, TH) == "none"
    assert digest.gems_bucket(2, TH) == "few"
    assert digest.gems_bucket(9, TH) == "many"
    assert digest.hp_bucket(10, 100, TH) == "critical"
    assert digest.hp_bucket(40, 100, TH) == "low"
    assert digest.hp_bucket(80, 100, TH) == "ok"
    assert digest.hp_bucket(100, 100, TH) == "full"
    assert digest.hp_bucket(5, 0, TH) == "critical"


def test_empty_state_has_all_sectors_quiet(empty_state):
    d = digest.digest_state(empty_state, TH)
    assert set(d.sectors) == set(digest.SECTORS)
    for s in d.sectors.values():
        assert s.pressure == "none" and s.nearest is None and s.gems == "none"
        assert s.boss is False and s.chest is False
    assert d.player.hp_bucket == "ok"
    assert d.player.weapons == ["WHIP L3"]
    assert d.player.passives == ["SPINACH L1"]


def test_enemies_north_make_north_heavy_and_touching():
    st = make_state(enemies=[enemy(0, 0.3), enemy(0.1, 0.4), enemy(0, 0.5)])
    d = digest.digest_state(st, TH)
    north = d.sectors["north"]
    assert north.enemy_count == 3
    assert north.pressure == "heavy"      # 3 touching enemies * weight 4 = 12 >= 8
    assert north.nearest == "touching"
    assert d.sectors["south"].pressure == "none"


def test_far_enemies_are_light():
    st = make_state(enemies=[enemy(3.9, 0.0)])   # 3.9 / 4.0 -> far, weight 0.5
    d = digest.digest_state(st, TH)
    assert d.sectors["east"].pressure == "light"
    assert d.sectors["east"].nearest == "far"


def test_boss_and_chest_flags_and_gems():
    st = make_state(
        enemies=[enemy(-2, 0, boss=True)],
        gems=[gem(0, -1), gem(0.2, -1.5), gem(-0.1, -2), gem(0, -2.5)],
        pickups=[{"x": 2, "y": 2, "kind": "TREASURE"}],
    )
    d = digest.digest_state(st, TH)
    assert d.sectors["west"].boss is True
    assert d.sectors["south"].gems == "many"
    assert d.sectors["south"].gem_count == 4
    assert d.sectors["north_east"].chest is True


def test_to_dict_is_json_ready(empty_state):
    import json
    d = digest.digest_state(empty_state, TH)
    json.dumps(d.to_dict())
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jev_vs.digest'`.

- [ ] **Step 4: Implement digest.py**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_digest.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/jev_vs/digest.py brain/jev_vs/questions.py brain/tests/conftest.py brain/tests/test_digest.py
git commit -m "feat(brain): digest raw tick state into labelled sectors"
```

---

### Task 3: Questions module (the file humans review)

**Files:**
- Rewrite: `brain/jev_vs/questions.py`
- Create: `brain/tests/test_questions.py`

**Interfaces:**
- Produces: `DIRECTIONS` (SECTORS plus `"stay"`), `DIRECTION_VECTORS`, `Thresholds`, `DEFAULT_THRESHOLDS`, `sector_text(SectorSummary) -> str`, dataclass `Ask(name, state, question: Choice, keys: list[str], instructions: str, labels: dict[str, str])`, `direction_question(d: Digest) -> Ask`, `options_question(kind: str, options: list[dict], build: dict | None) -> Ask` where `kind` is one of `level_up`, `weapon_select`, `arcana_select`, `character`, `stage`.
- Consumes: `digest.Digest`, `digest.SectorSummary`, `typesafe_sdk.Choice`.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_questions.py`:

```python
from typesafe_sdk import Choice

from jev_vs import questions as q
from jev_vs.digest import SectorSummary, digest_state
from tests.conftest import enemy, gem, make_state


def test_directions_are_sectors_plus_stay():
    assert q.DIRECTIONS[:-1] == [
        "north", "north_east", "east", "south_east", "south", "south_west", "west", "north_west",
    ]
    assert q.DIRECTIONS[-1] == "stay"
    assert set(q.DIRECTION_VECTORS) == set(q.DIRECTIONS)


def test_sector_text_is_words_only():
    s = SectorSummary(pressure="heavy", nearest="touching", gems="few", boss=True, chest=False, enemy_count=12, gem_count=2)
    text = q.sector_text(s)
    assert "heavy" in text and "touching" in text and "few" in text and "boss" in text
    assert not any(ch.isdigit() for ch in text), "no numbers may reach Jev"


def test_sector_text_quiet():
    assert q.sector_text(SectorSummary()) == "no enemies, no gems"


def test_direction_question_shape():
    st = make_state(enemies=[enemy(0, 0.3)], gems=[gem(0, -1)], hp=20)
    ask = q.direction_question(digest_state(st, q.DEFAULT_THRESHOLDS))
    assert ask.name == "direction"
    assert isinstance(ask.question, Choice)
    assert list(ask.question.criteria) == q.DIRECTIONS
    assert ask.keys == q.DIRECTIONS
    assert "heavy" in ask.question.criteria["north"] or "moderate" in ask.question.criteria["north"]
    assert ask.state["player"]["hp"] == "critical"
    assert "WHIP L3" in ask.state["player"]["weapons"]
    assert "safety" in ask.instructions.lower() or "away" in ask.instructions.lower()


def test_options_question_keys_follow_option_order_and_are_unique():
    opts = [
        {"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 5, "is_new": False, "description": "Attacks horizontally."},
        {"index": 1, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 2, "is_new": False, "description": "Raises damage."},
        {"index": 2, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 5, "is_new": False, "description": "dup"},
    ]
    ask = q.options_question("level_up", opts, {"weapons": ["WHIP L4"], "passives": [], "level": 9, "minute": 6})
    assert ask.name == "level_up"
    assert len(ask.keys) == 3 and len(set(ask.keys)) == 3
    assert ask.keys[0] == "WHIP" and ask.keys[2] == "WHIP_3"
    assert list(ask.question.criteria) == ask.keys
    assert "Whip" in ask.labels["WHIP"]
    assert ask.state["build"]["weapons"] == ["WHIP L4"]


def test_options_question_mentions_evolution_and_new():
    opts = [{"index": 0, "id": "KNIFE", "name": "Knife", "kind": "weapon", "level": 1, "is_new": True,
             "description": "Fires quickly.", "evolution_ready": True}]
    ask = q.options_question("level_up", opts, None)
    desc = ask.question.criteria["KNIFE"]
    assert "new" in desc.lower() and "evolution" in desc.lower()


def test_character_and_stage_questions():
    chars = [{"id": "ANTONIO", "name": "Antonio Belpaese", "description": "Gains 10% damage.", "starting_weapon": "WHIP"}]
    ask = q.options_question("character", chars, None)
    assert ask.name == "character" and ask.keys == ["ANTONIO"]
    stages = [{"id": "FOREST", "name": "Mad Forest", "description": "The Castle is a lie."}]
    ask2 = q.options_question("stage", stages, None)
    assert ask2.name == "stage" and "Mad Forest" in ask2.question.criteria["FOREST"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_questions.py -v`
Expected: FAIL (`AttributeError: module 'jev_vs.questions' has no attribute 'DIRECTIONS'`).

- [ ] **Step 3: Rewrite questions.py**

```python
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
        state["build"] = build
    instructions = _PICK_INSTRUCTIONS[kind]
    return Ask(
        name=kind,
        state=state,
        question=Choice(instructions=instructions, criteria=criteria),
        keys=keys,
        instructions=instructions,
        labels=labels,
    )
```

Note: `"would reach level {o.get('level')}"` puts a small integer in an option description. That is a label, not a quantity Jev must compare, and matches how the game itself shows it; keep it.

- [ ] **Step 4: Run all tests to verify they pass**

Run: `uv run pytest -v`
Expected: all PASS, including Task 1 and 2 tests (the protocol test's diagonal check now uses the real `DIRECTION_VECTORS`).

- [ ] **Step 5: Commit**

```bash
git add brain/jev_vs/questions.py brain/tests/test_questions.py
git commit -m "feat(brain): define all Jev questions, wording, and thresholds in one module"
```

---

### Task 4: Jev client and decider with fallbacks

**Files:**
- Create: `brain/jev_vs/jev_client.py`
- Create: `brain/jev_vs/decide.py`
- Create: `brain/tests/test_decide.py`

**Interfaces:**
- Produces: `jev_client.ChoicePick(choice: str, probabilities: dict[str, float], confidence: float)`, `jev_client.JevResult(answers: dict[str, ChoicePick], latency_ms: float, input_tokens: int)`, `jev_client.JevClient(model, timeout_s, max_retries, api_key=None)` with `async ask(state, questions) -> JevResult` and `async aclose()`.
- Produces: `decide.Decision` dataclass with fields `kind, choice, index, probabilities, confidence, latency_ms, source, input_tokens, instructions, labels`, `decide.Decider(jev, thresholds)` with `async direction(state) -> tuple[Digest, Decision]` and `async pick(kind, options, build=None) -> Decision`, `decide.fallback_direction(d: Digest) -> str`, `decide.fallback_pick(options) -> int`.
- Consumes: `questions.Ask`, `digest.digest_state`, `tests.conftest.FakeJev`.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_decide.py`:

```python
import pytest

from jev_vs import decide
from jev_vs.digest import digest_state
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from tests.conftest import FakeJev, enemy, gem, make_state


async def test_direction_uses_jev_answer():
    fake = FakeJev(script={"direction": ("south", {"south": 0.7, "north": 0.3}, 0.5)})
    dec = decide.Decider(fake, TH)
    d, decision = await dec.direction(make_state())
    assert decision.kind == "direction"
    assert decision.choice == "south" and decision.index == 4
    assert decision.source == "jev"
    assert decision.probabilities["south"] == 0.7
    assert decision.latency_ms == 12.0
    assert decision.input_tokens == 100
    assert len(fake.calls) == 1


async def test_direction_falls_back_when_jev_fails():
    fake = FakeJev(fail=True)
    dec = decide.Decider(fake, TH)
    st = make_state(enemies=[enemy(0, 0.3), enemy(0, 0.4)], gems=[gem(0, -1)])
    _, decision = await dec.direction(st)
    assert decision.source == "fallback"
    assert decision.choice == "south"
    assert decision.probabilities[decision.choice] == 1.0
    assert decision.confidence == 0.0


async def test_direction_rejects_unknown_choice_with_fallback():
    fake = FakeJev(script={"direction": ("sideways", {"sideways": 1.0}, 0.9)})
    dec = decide.Decider(fake, TH)
    _, decision = await dec.direction(make_state())
    assert decision.source == "fallback"
    assert decision.choice in decide.DIRECTIONS


def test_fallback_direction_prefers_least_pressure_then_gems():
    st = make_state(enemies=[enemy(0, 0.3)] * 3 + [enemy(1, 0)], gems=[gem(-1, 0), gem(-1.2, 0)])
    d = digest_state(st, TH)
    assert decide.fallback_direction(d) == "west"


def test_fallback_direction_stays_when_all_quiet():
    assert decide.fallback_direction(digest_state(make_state(), TH)) == "stay"


async def test_pick_maps_choice_to_index():
    opts = [
        {"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 5},
        {"index": 1, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 2},
    ]
    fake = FakeJev(script={"level_up": ("SPINACH", {"SPINACH": 0.8, "WHIP": 0.2}, 0.6)})
    dec = decide.Decider(fake, TH)
    decision = await dec.pick("level_up", opts, {"weapons": ["WHIP L4"], "passives": []})
    assert decision.index == 1 and decision.choice == "SPINACH" and decision.source == "jev"
    assert decision.labels["SPINACH"] == "Spinach"


async def test_pick_falls_back_to_first_option():
    opts = [{"index": 0, "id": "A", "name": "A"}, {"index": 1, "id": "B", "name": "B"}]
    dec = decide.Decider(FakeJev(fail=True), TH)
    decision = await dec.pick("character", opts)
    assert decision.index == 0 and decision.choice == "A" and decision.source == "fallback"


async def test_pick_with_no_options_raises():
    dec = decide.Decider(FakeJev(), TH)
    with pytest.raises(ValueError):
        await dec.pick("stage", [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_decide.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jev_vs.decide'`.

- [ ] **Step 3: Implement jev_client.py**

```python
"""Thin wrapper over the TypeSafe SDK so the rest of the brain never sees SDK types."""
from __future__ import annotations

import time
from dataclasses import dataclass

from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy


@dataclass(frozen=True)
class ChoicePick:
    choice: str
    probabilities: dict[str, float]
    confidence: float


@dataclass(frozen=True)
class JevResult:
    answers: dict[str, ChoicePick]
    latency_ms: float
    input_tokens: int


class JevClient:
    """Async client. `ask` raises on any API failure; callers decide what to do."""

    def __init__(self, *, model: str, timeout_s: float, max_retries: int, api_key: str | None = None):
        self._client = AsyncTypeSafeClient(
            api_key=api_key,
            model=model,
            retry=RetryPolicy(max_retries=max_retries, backoff_initial=0.05, backoff_max=0.2, timeout=timeout_s),
            timeout=timeout_s,
        )

    async def ask(self, state: dict | str | list, questions: dict[str, Choice]) -> JevResult:
        t0 = time.perf_counter()
        resp = await self._client.system_one(state, questions)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        answers: dict[str, ChoicePick] = {}
        for name, ans in resp.answers.items():
            answers[name] = ChoicePick(
                choice=str(ans.choice),
                probabilities={str(k): float(v) for k, v in dict(ans.probabilities).items()},
                confidence=float(ans.confidence),
            )
        tokens = int(getattr(resp.usage, "input_tokens", 0) or 0)
        return JevResult(answers=answers, latency_ms=latency_ms, input_tokens=tokens)

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
```

- [ ] **Step 4: Implement decide.py**

```python
"""Decider: digest -> Ask -> Jev -> Decision, with heuristic fallbacks."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .digest import Digest, digest_state
from .questions import DIRECTIONS, Ask, Thresholds, direction_question, options_question

log = logging.getLogger(__name__)

_PRESSURE_RANK = {"none": 0, "light": 1, "moderate": 2, "heavy": 3}
_GEM_RANK = {"none": 0, "few": 1, "many": 2}


@dataclass
class Decision:
    kind: str
    choice: str
    index: int
    probabilities: dict[str, float]
    confidence: float
    latency_ms: float
    source: str                       # "jev" | "fallback"
    input_tokens: int = 0
    instructions: str = ""
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "choice": self.choice, "index": self.index,
            "probabilities": self.probabilities, "confidence": self.confidence,
            "latency_ms": round(self.latency_ms, 1), "source": self.source,
            "input_tokens": self.input_tokens, "instructions": self.instructions, "labels": self.labels,
        }


def fallback_direction(d: Digest) -> str:
    """Least pressure wins; ties broken by most gems; all quiet means stay."""
    best = None
    for name in DIRECTIONS[:-1]:
        s = d.sectors[name]
        key = (_PRESSURE_RANK[s.pressure], -_GEM_RANK[s.gems], -s.gem_count)
        if best is None or key < best[0]:
            best = (key, name)
    assert best is not None
    if best[0][0] == 0 and best[0][1] == 0:
        return "stay"
    return best[1]


def fallback_pick(options: list[dict]) -> int:
    return 0


class Decider:
    def __init__(self, jev, thresholds: Thresholds):
        self._jev = jev
        self._th = thresholds

    async def _ask(self, ask: Ask) -> tuple[str | None, dict, float, float, int]:
        """Returns (choice or None on failure, probabilities, confidence, latency_ms, tokens)."""
        try:
            result = await self._jev.ask(ask.state, {ask.name: ask.question})
        except Exception as e:  # any SDK/network error becomes a fallback, never a crash
            log.warning("jev %s failed: %s", ask.name, e)
            return None, {}, 0.0, 0.0, 0
        pick = result.answers.get(ask.name)
        if pick is None or pick.choice not in ask.keys:
            log.warning("jev %s returned unusable choice %r", ask.name, getattr(pick, "choice", None))
            return None, {}, 0.0, result.latency_ms, result.input_tokens
        return pick.choice, pick.probabilities, pick.confidence, result.latency_ms, result.input_tokens

    async def direction(self, state: dict) -> tuple[Digest, Decision]:
        d = digest_state(state, self._th)
        ask = direction_question(d)
        choice, probs, conf, latency, tokens = await self._ask(ask)
        source = "jev"
        if choice is None:
            choice, probs, conf, source = fallback_direction(d), {}, 0.0, "fallback"
            probs = {k: (1.0 if k == choice else 0.0) for k in ask.keys}
        return d, Decision(
            kind="direction", choice=choice, index=ask.keys.index(choice), probabilities=probs,
            confidence=conf, latency_ms=latency, source=source, input_tokens=tokens,
            instructions=ask.instructions, labels=ask.labels,
        )

    async def pick(self, kind: str, options: list[dict], build: dict | None = None) -> Decision:
        if not options:
            raise ValueError(f"{kind}: no options to pick from")
        ask = options_question(kind, options, build)
        choice, probs, conf, latency, tokens = await self._ask(ask)
        source = "jev"
        if choice is None:
            idx = fallback_pick(options)
            choice, conf, source = ask.keys[idx], 0.0, "fallback"
            probs = {k: (1.0 if k == choice else 0.0) for k in ask.keys}
        return Decision(
            kind=kind, choice=choice, index=ask.keys.index(choice), probabilities=probs,
            confidence=conf, latency_ms=latency, source=source, input_tokens=tokens,
            instructions=ask.instructions, labels=ask.labels,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_decide.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/jev_vs/jev_client.py brain/jev_vs/decide.py brain/tests/test_decide.py
git commit -m "feat(brain): Jev client wrapper and Decider with heuristic fallbacks"
```

---

### Task 5: Run logs, broadcast hub, and stats

**Files:**
- Create: `brain/jev_vs/runlog.py`
- Create: `brain/jev_vs/hub.py`
- Create: `brain/jev_vs/stats.py`
- Create: `brain/tests/test_runlog.py`
- Create: `brain/tests/test_hub_stats.py`

**Interfaces:**
- Produces: `runlog.RunLog(root: Path)` with `start_run(meta: dict) -> Path`, `tick(record: dict)`, `event(record: dict)`, `end_run(summary: dict) -> dict`, property `run_dir: Path | None`, property `active: bool`.
- Produces: `hub.Hub(maxsize=64)` with `subscribe() -> asyncio.Queue`, `unsubscribe(q)`, `publish(msg: dict) -> int` (returns number of clients dropped for being full), `is_subscribed(q) -> bool`, property `client_count`.
- Produces: `stats.Stats` with `record(decision: Decision)`, `reset_run()`, `snapshot() -> dict` containing `calls, jev_calls, fallback_calls, reused, last_latency_ms, avg_latency_ms, input_tokens, cost_usd, cost_per_hour_usd, plugin_connected, jev_ok, run_started_at`, and `mark_reused()`, `set_plugin_connected(bool)`. Cost is `input_tokens / 1e6 * 0.042`.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_runlog.py`:

```python
import json
from pathlib import Path

from jev_vs.runlog import RunLog


def test_runlog_writes_jsonl_and_summary(tmp_path: Path):
    log = RunLog(tmp_path)
    assert log.active is False
    run_dir = log.start_run({"character": "ANTONIO"})
    assert log.active is True and run_dir.is_dir() and run_dir.parent == tmp_path
    log.tick({"id": 1, "choice": "north"})
    log.tick({"id": 2, "choice": "stay"})
    log.event({"event": "level_up", "index": 0})
    summary = log.end_run({"seconds": 42})
    assert log.active is False
    ticks = [json.loads(l) for l in (run_dir / "ticks.jsonl").read_text().splitlines()]
    assert [t["id"] for t in ticks] == [1, 2]
    events = [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines()]
    assert events[0]["event"] == "level_up"
    written = json.loads((run_dir / "summary.json").read_text())
    assert written["seconds"] == 42 and written["character"] == "ANTONIO" and written["ticks"] == 2
    assert summary == written


def test_tick_before_start_is_buffered_into_next_run(tmp_path: Path):
    log = RunLog(tmp_path)
    log.tick({"id": 0})
    run_dir = log.start_run({})
    log.end_run({})
    assert (run_dir / "ticks.jsonl").read_text().count("\n") == 1
```

`brain/tests/test_hub_stats.py`:

```python
import asyncio

from jev_vs.decide import Decision
from jev_vs.hub import Hub
from jev_vs.stats import Stats


async def test_hub_fans_out_and_drops_full_clients():
    hub = Hub(maxsize=2)
    fast = hub.subscribe()
    slow = hub.subscribe()
    assert hub.publish({"n": 1}) == 0
    await fast.get()
    assert hub.publish({"n": 2}) == 0
    await fast.get()
    dropped = hub.publish({"n": 3})   # slow now has 3 pending -> over maxsize 2
    assert dropped == 1
    assert hub.client_count == 1
    assert (await fast.get()) == {"n": 3}
    hub.unsubscribe(fast)
    assert hub.client_count == 0
    assert isinstance(slow, asyncio.Queue)


def _decision(source="jev", latency=100.0, tokens=1000):
    return Decision(kind="direction", choice="north", index=0, probabilities={"north": 1.0},
                    confidence=0.5, latency_ms=latency, source=source, input_tokens=tokens)


def test_stats_counts_and_cost():
    s = Stats()
    s.record(_decision(latency=100.0, tokens=1_000_000))
    s.record(_decision(source="fallback", latency=0.0, tokens=0))
    s.record(_decision(latency=300.0, tokens=1_000_000))
    s.mark_reused()
    snap = s.snapshot()
    assert snap["calls"] == 3 and snap["jev_calls"] == 2 and snap["fallback_calls"] == 1 and snap["reused"] == 1
    assert snap["last_latency_ms"] == 300.0
    assert snap["avg_latency_ms"] == 200.0
    assert snap["input_tokens"] == 2_000_000
    assert abs(snap["cost_usd"] - 0.084) < 1e-9
    assert snap["plugin_connected"] is False
    s.set_plugin_connected(True)
    assert s.snapshot()["plugin_connected"] is True
    s.reset_run()
    assert s.snapshot()["calls"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runlog.py tests/test_hub_stats.py -v`
Expected: FAIL with `ModuleNotFoundError` for `jev_vs.runlog` and `jev_vs.hub`.

- [ ] **Step 3: Implement runlog.py, hub.py, stats.py**

`brain/jev_vs/runlog.py`:

```python
"""JSONL run logs: runs/<YYYYMMDD-HHMMSS>/{ticks.jsonl,events.jsonl,summary.json}."""
from __future__ import annotations

import json
import time
from pathlib import Path


class RunLog:
    def __init__(self, root: Path):
        self._root = Path(root)
        self._run_dir: Path | None = None
        self._meta: dict = {}
        self._ticks = None
        self._events = None
        self._tick_count = 0
        self._event_count = 0
        self._pending: list[tuple[str, dict]] = []

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir

    @property
    def active(self) -> bool:
        return self._run_dir is not None

    def start_run(self, meta: dict) -> Path:
        if self.active:
            self.end_run({"aborted": True})
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run_dir = self._root / stamp
        n = 1
        while run_dir.exists():
            n += 1
            run_dir = self._root / f"{stamp}-{n}"
        run_dir.mkdir(parents=True)
        self._run_dir = run_dir
        self._meta = {"started_at": time.time(), **meta}
        self._ticks = (run_dir / "ticks.jsonl").open("a", encoding="utf-8")
        self._events = (run_dir / "events.jsonl").open("a", encoding="utf-8")
        self._tick_count = self._event_count = 0
        for kind, rec in self._pending:
            (self.tick if kind == "tick" else self.event)(rec)
        self._pending.clear()
        return run_dir

    def _write(self, fh, record: dict) -> None:
        fh.write(json.dumps({"t": time.time(), **record}, separators=(",", ":"), ensure_ascii=False) + "\n")
        fh.flush()

    def tick(self, record: dict) -> None:
        if not self.active:
            self._pending.append(("tick", record))
            return
        self._tick_count += 1
        self._write(self._ticks, record)

    def event(self, record: dict) -> None:
        if not self.active:
            self._pending.append(("event", record))
            return
        self._event_count += 1
        self._write(self._events, record)

    def update_meta(self, **fields) -> None:
        self._meta.update(fields)

    def end_run(self, summary: dict) -> dict:
        if not self.active:
            return {}
        written = {**self._meta, **summary, "ended_at": time.time(),
                   "ticks": self._tick_count, "events": self._event_count}
        (self._run_dir / "summary.json").write_text(json.dumps(written, indent=2))
        self._ticks.close()
        self._events.close()
        self._run_dir = None
        self._ticks = self._events = None
        return written
```

`brain/jev_vs/hub.py`:

```python
"""Fan-out of dashboard messages. A client that cannot keep up is dropped, never awaited."""
from __future__ import annotations

import asyncio


class Hub:
    def __init__(self, maxsize: int = 64):
        self._maxsize = maxsize
        self._clients: set[asyncio.Queue] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    def publish(self, msg: dict) -> int:
        dropped = 0
        for q in list(self._clients):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                self._clients.discard(q)
                dropped += 1
        return dropped

    def is_subscribed(self, q: asyncio.Queue) -> bool:
        return q in self._clients
```

`brain/jev_vs/stats.py`:

```python
"""Per-run counters shown in the dashboard header."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .decide import Decision

USD_PER_MILLION_INPUT_TOKENS = 0.042


@dataclass
class Stats:
    calls: int = 0
    jev_calls: int = 0
    fallback_calls: int = 0
    reused: int = 0
    last_latency_ms: float = 0.0
    input_tokens: int = 0
    plugin_connected: bool = False
    jev_ok: bool = True
    run_started_at: float = field(default_factory=time.time)
    _latency_sum: float = 0.0

    def record(self, d: Decision) -> None:
        self.calls += 1
        if d.source == "jev":
            self.jev_calls += 1
            self.jev_ok = True
            self.last_latency_ms = d.latency_ms
            self._latency_sum += d.latency_ms
        else:
            self.fallback_calls += 1
            self.jev_ok = False
        self.input_tokens += d.input_tokens

    def mark_reused(self) -> None:
        self.reused += 1

    def set_plugin_connected(self, connected: bool) -> None:
        self.plugin_connected = connected

    def reset_run(self) -> None:
        self.calls = self.jev_calls = self.fallback_calls = self.reused = 0
        self.last_latency_ms = 0.0
        self.input_tokens = 0
        self._latency_sum = 0.0
        self.run_started_at = time.time()

    def snapshot(self) -> dict:
        elapsed_h = max(time.time() - self.run_started_at, 1e-6) / 3600.0
        cost = self.input_tokens / 1e6 * USD_PER_MILLION_INPUT_TOKENS
        return {
            "calls": self.calls, "jev_calls": self.jev_calls, "fallback_calls": self.fallback_calls,
            "reused": self.reused, "last_latency_ms": round(self.last_latency_ms, 1),
            "avg_latency_ms": round(self._latency_sum / self.jev_calls, 1) if self.jev_calls else 0.0,
            "input_tokens": self.input_tokens, "cost_usd": round(cost, 6),
            "cost_per_hour_usd": round(cost / elapsed_h, 4),
            "plugin_connected": self.plugin_connected, "jev_ok": self.jev_ok,
            "run_started_at": self.run_started_at,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runlog.py tests/test_hub_stats.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add brain/jev_vs/runlog.py brain/jev_vs/hub.py brain/jev_vs/stats.py brain/tests/test_runlog.py brain/tests/test_hub_stats.py
git commit -m "feat(brain): JSONL run logs, dashboard hub, and per-run stats"
```

---

### Task 6: Plugin TCP server

**Files:**
- Create: `brain/jev_vs/server.py`
- Create: `brain/tests/test_server.py`

**Interfaces:**
- Produces: `server.PluginServer(config: Config, decider: Decider, runlog: RunLog, hub: Hub, stats: Stats)` with `async start() -> int` (returns bound port; `config.plugin_port == 0` binds an ephemeral port), `async stop()`, `async send_control(automation: bool) -> bool` (False when no plugin connected), property `port`, property `last_direction: dict | None`, `latest_decisions: dict[str, dict]` (kind -> last decision dict for dashboard snapshots), `recent_log: list[dict]` (last 50 event lines).
- Behaviour (spec sections 4, 5, 9): `hello` sets stats connected; `tick` runs `decider.direction` unless one is in flight, in which case it replies immediately with the last move marked `source: "reused"`; `event` with `event` in `{character_select, stage_select, level_up, weapon_select, arcana_select}` runs `decider.pick` and replies `pick`; `event: game_over` replies `noop`, ends the run log, publishes `run` end; `character_select` starts a new run log; malformed lines are logged and skipped; a closed socket ends the loop and marks the plugin disconnected.
- Consumes: everything from Tasks 1 to 5.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_server.py`:

```python
import asyncio
import json
from pathlib import Path

import pytest

from jev_vs.config import Config
from jev_vs.decide import Decider
from jev_vs.hub import Hub
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from jev_vs.runlog import RunLog
from jev_vs.server import PluginServer
from jev_vs.stats import Stats
from tests.conftest import FakeJev, make_state


class SlowJev(FakeJev):
    """First call blocks until released, so the second tick overlaps it."""

    def __init__(self):
        super().__init__(script={"direction": ("east", {"east": 1.0}, 0.9)})
        self.gate = asyncio.Event()
        self.n = 0

    async def ask(self, state, questions):
        self.n += 1
        if self.n == 1:
            await self.gate.wait()
        return await super().ask(state, questions)


async def _start(tmp_path: Path, jev):
    hub = Hub()
    stats = Stats()
    srv = PluginServer(Config(plugin_port=0, log_dir=str(tmp_path)), Decider(jev, TH), RunLog(tmp_path), hub, stats)
    port = await srv.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    return srv, hub, stats, reader, writer


async def _send(writer, msg):
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()


async def _recv(reader):
    return json.loads(await asyncio.wait_for(reader.readline(), 2))


async def test_hello_and_tick_round_trip(tmp_path):
    jev = FakeJev(script={"direction": ("west", {"west": 0.6, "stay": 0.4}, 0.2)})
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    q = hub.subscribe()
    await _send(writer, {"type": "hello", "game_version": "1.16.107", "plugin_version": "0.1.0"})
    await _send(writer, {"id": 1, "type": "tick", "t": 0.25, "state": make_state()})
    reply = await _recv(reader)
    assert reply["id"] == 1 and reply["type"] == "move" and reply["choice"] == "west"
    assert (reply["dx"], reply["dy"]) == (-1.0, 0.0) and reply["source"] == "jev"
    msgs = [await q.get() for _ in range(3)]
    kinds = [m["type"] for m in msgs]
    assert "stats" in kinds and "decision" in kinds
    dec = next(m for m in msgs if m["type"] == "decision")
    assert dec["kind"] == "direction" and "digest" in dec and "entities" in dec
    assert stats.snapshot()["plugin_connected"] is True and stats.snapshot()["calls"] == 1
    writer.close()
    await srv.stop()


async def test_overlapping_tick_gets_reused_reply(tmp_path):
    jev = SlowJev()
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    await _send(writer, {"id": 1, "type": "tick", "t": 0.0, "state": make_state()})
    await asyncio.sleep(0.05)
    await _send(writer, {"id": 2, "type": "tick", "t": 0.25, "state": make_state()})
    second = await _recv(reader)
    assert second["id"] == 2 and second["source"] == "reused" and second["choice"] == "stay"
    jev.gate.set()
    first = await _recv(reader)
    assert first["id"] == 1 and first["choice"] == "east" and first["source"] == "jev"
    assert stats.snapshot()["reused"] == 1
    writer.close()
    await srv.stop()


async def test_events_drive_run_log_and_picks(tmp_path):
    jev = FakeJev(script={"character": ("IMELDA", {"IMELDA": 0.9, "ANTONIO": 0.1}, 0.8),
                         "level_up": ("SPINACH", {"SPINACH": 1.0}, 1.0)})
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    chars = [{"id": "ANTONIO", "name": "Antonio", "description": "d"}, {"id": "IMELDA", "name": "Imelda", "description": "d"}]
    await _send(writer, {"id": 10, "type": "event", "event": "character_select", "options": chars})
    r = await _recv(reader)
    assert r == {"id": 10, "type": "pick", "index": 1, "choice": "IMELDA",
                 "probabilities": {"IMELDA": 0.9, "ANTONIO": 0.1}, "confidence": 0.8, "source": "jev"}
    assert srv.runlog.active is True
    await _send(writer, {"id": 11, "type": "event", "event": "stage_select",
                         "options": [{"id": "FOREST", "name": "Mad Forest", "description": "d"}]})
    assert (await _recv(reader))["choice"] == "FOREST"
    await _send(writer, {"id": 12, "type": "event", "event": "level_up",
                         "options": [{"index": 0, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 1}],
                         "build": {"weapons": [], "passives": []}})
    assert (await _recv(reader))["index"] == 0
    await _send(writer, {"id": 13, "type": "event", "event": "game_over",
                         "summary": {"character": "IMELDA", "stage": "FOREST", "seconds": 90, "level": 4, "kills": 12, "stage_complete": False}})
    assert (await _recv(reader)) == {"id": 13, "type": "noop"}
    assert srv.runlog.active is False
    run_dirs = [p for p in Path(tmp_path).iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "summary.json").read_text())
    assert summary["character"] == "IMELDA" and summary["stage"] == "FOREST" and summary["seconds"] == 90
    events = (run_dirs[0] / "events.jsonl").read_text().splitlines()
    assert len(events) == 4
    writer.close()
    await srv.stop()


async def test_bad_line_is_skipped_and_connection_survives(tmp_path):
    srv, hub, stats, reader, writer = await _start(tmp_path, FakeJev())
    writer.write(b"garbage\n")
    await _send(writer, {"id": 5, "type": "tick", "t": 0.0, "state": make_state()})
    assert (await _recv(reader))["id"] == 5
    writer.close()
    await srv.stop()


async def test_send_control_reaches_plugin_and_reports_absence(tmp_path):
    srv, hub, stats, reader, writer = await _start(tmp_path, FakeJev())
    await _send(writer, {"type": "hello"})
    await asyncio.sleep(0.05)
    assert await srv.send_control(False) is True
    assert (await _recv(reader)) == {"type": "control", "automation": False}
    writer.close()
    await asyncio.sleep(0.05)
    assert await srv.send_control(True) is False
    assert stats.snapshot()["plugin_connected"] is False
    await srv.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jev_vs.server'`.

- [ ] **Step 3: Implement server.py**

```python
"""TCP server the game plugin connects to. One connection at a time is expected."""
from __future__ import annotations

import asyncio
import logging
import time

from . import protocol
from .config import Config
from .decide import Decider, Decision
from .hub import Hub
from .runlog import RunLog
from .stats import Stats

log = logging.getLogger(__name__)

PICK_EVENTS = {"character_select": "character", "stage_select": "stage", "level_up": "level_up",
               "weapon_select": "weapon_select", "arcana_select": "arcana_select"}


class PluginServer:
    def __init__(self, config: Config, decider: Decider, runlog: RunLog, hub: Hub, stats: Stats):
        self.config = config
        self.decider = decider
        self.runlog = runlog
        self.hub = hub
        self.stats = stats
        self._server: asyncio.AbstractServer | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._in_flight = False
        self.last_direction: dict | None = None
        self.latest_decisions: dict[str, dict] = {}
        self.recent_log: list[dict] = []
        self.current_run: dict = {}

    # ------------------------------------------------------------ lifecycle
    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.config.plugin_host, self.config.plugin_port)
        log.info("plugin server listening on %s:%d", self.config.plugin_host, self.port)
        return self.port

    async def stop(self) -> None:
        if self._writer is not None:
            self._writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    # ------------------------------------------------------------ helpers
    def _note(self, text: str, **extra) -> None:
        entry = {"t": time.time(), "text": text, **extra}
        self.recent_log.append(entry)
        del self.recent_log[:-50]
        self.hub.publish({"type": "event", **entry})

    def _publish_stats(self) -> None:
        self.hub.publish({"type": "stats", **self.stats.snapshot()})

    async def _reply(self, writer: asyncio.StreamWriter, msg: dict) -> None:
        try:
            writer.write(protocol.encode(msg))
            await writer.drain()
        except (ConnectionError, RuntimeError) as e:
            log.warning("reply failed: %s", e)

    async def send_control(self, automation: bool) -> bool:
        if self._writer is None or self._writer.is_closing():
            return False
        await self._reply(self._writer, protocol.control(automation))
        self._note(f"automation {'resumed' if automation else 'paused'} from dashboard")
        return True

    def _record_decision(self, d: Decision, **extra) -> dict:
        payload = {"type": "decision", **d.to_dict(), **extra}
        self.latest_decisions[d.kind] = payload
        self.stats.record(d)
        self.hub.publish(payload)
        self._publish_stats()
        return payload

    # ------------------------------------------------------------ connection
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info("plugin connected from %s", peer)
        self._writer = writer
        self.stats.set_plugin_connected(True)
        self._publish_stats()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = protocol.decode(line)
                except protocol.ProtocolError as e:
                    log.warning("skipping bad line: %s", e)
                    continue
                await self._dispatch(msg, writer)
        except (ConnectionError, asyncio.IncompleteReadError) as e:
            log.info("plugin connection error: %s", e)
        finally:
            log.info("plugin disconnected")
            if self._writer is writer:
                self._writer = None
            self.stats.set_plugin_connected(False)
            self._publish_stats()
            writer.close()

    async def _dispatch(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        t = msg["type"]
        if t == "hello":
            self._note(f"plugin hello: game {msg.get('game_version')} plugin {msg.get('plugin_version')}")
        elif t == "tick":
            asyncio.create_task(self._on_tick(msg, writer))
        elif t == "event":
            asyncio.create_task(self._on_event(msg, writer))
        else:
            log.warning("unknown message type %r", t)

    async def _on_tick(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        mid = msg.get("id", 0)
        if self._in_flight:
            self.stats.mark_reused()
            last = self.last_direction
            reply = protocol.move_reply(mid, last["choice"] if last else "stay",
                                        last["probabilities"] if last else {"stay": 1.0},
                                        last["confidence"] if last else 0.0, "reused")
            await self._reply(writer, reply)
            return
        self._in_flight = True
        try:
            state = msg.get("state", {})
            digest, decision = await self.decider.direction(state)
            reply = protocol.move_reply(mid, decision.choice, decision.probabilities, decision.confidence, decision.source)
            self.last_direction = reply
            await self._reply(writer, reply)
            entities = {k: state.get(k, []) for k in ("enemies", "gems", "pickups")}
            entities["screen"] = state.get("screen", {})
            self._record_decision(decision, digest=digest.to_dict(), entities=entities, t=msg.get("t"))
            self.runlog.tick({"id": mid, "t": msg.get("t"), "state": state, "digest": digest.to_dict(), **decision.to_dict()})
        finally:
            self._in_flight = False

    async def _on_event(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        mid = msg.get("id", 0)
        event = str(msg.get("event", ""))
        if event == "game_over":
            await self._reply(writer, protocol.noop_reply(mid))
            summary = msg.get("summary", {})
            self.runlog.event({"id": mid, "event": event, "summary": summary})
            written = self.runlog.end_run(summary)
            self._note(f"game over: {summary.get('character')} on {summary.get('stage')} survived {summary.get('seconds')}s level {summary.get('level')}")
            self.hub.publish({"type": "run", "phase": "end", "summary": written})
            self.current_run = {}
            return
        kind = PICK_EVENTS.get(event)
        if kind is None:
            log.warning("unknown event %r", event)
            await self._reply(writer, protocol.noop_reply(mid))
            return
        options = list(msg.get("options", []))
        if not options:
            await self._reply(writer, protocol.noop_reply(mid))
            self._note(f"{event} with no options; noop")
            return
        if event == "character_select":
            self.stats.reset_run()
            self.runlog.start_run({})
            self.current_run = {"started_at": time.time()}
            self.hub.publish({"type": "run", "phase": "start", "meta": self.current_run})
        decision = await self.decider.pick(kind, options, msg.get("build"))
        await self._reply(writer, protocol.pick_reply(mid, decision.index, decision.choice, decision.probabilities,
                                                      decision.confidence, decision.source))
        chosen = options[decision.index]
        if event == "character_select":
            self.current_run["character"] = chosen.get("id")
            self.runlog.update_meta(character=chosen.get("id"))
        elif event == "stage_select":
            self.current_run["stage"] = chosen.get("id")
            self.runlog.update_meta(stage=chosen.get("id"))
        self._record_decision(decision, options=options)
        self.runlog.event({"id": mid, "event": event, "options": options, **decision.to_dict()})
        self._note(f"{event}: picked {chosen.get('name', chosen.get('id'))} ({decision.source}, conf {decision.confidence:.2f})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_server.py -v`
Expected: all PASS. If `test_overlapping_tick_gets_reused_reply` is flaky on the 50 ms sleep, raise it to 100 ms; the ordering it checks does not depend on the exact value.

- [ ] **Step 5: Commit**

```bash
git add brain/jev_vs/server.py brain/tests/test_server.py
git commit -m "feat(brain): TCP plugin server with tick, event, and control handling"
```

---

### Task 7: Dashboard (aiohttp + WebSocket + page)

**Files:**
- Create: `brain/jev_vs/dashboard.py`
- Create: `brain/jev_vs/static/index.html`
- Create: `brain/tests/test_dashboard.py`

**Interfaces:**
- Produces: `dashboard.make_app(server: PluginServer) -> aiohttp.web.Application` with routes `GET /` (serves `static/index.html`) and `GET /ws`. On connect the socket receives `{"type":"snapshot","stats":..., "decisions": server.latest_decisions, "log": server.recent_log, "run": server.current_run}` then every hub message. A client text message `{"type":"control","automation":bool}` calls `server.send_control`.
- Produces: `dashboard.run_dashboard(app, host, port) -> aiohttp.web.AppRunner` (started) for `__main__`.
- Consumes: `server.PluginServer`, `hub.Hub`.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_dashboard.py`:

```python
import asyncio
import json

import pytest
from aiohttp import WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from jev_vs.config import Config
from jev_vs.dashboard import make_app
from jev_vs.decide import Decider, Decision
from jev_vs.hub import Hub
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from jev_vs.runlog import RunLog
from jev_vs.server import PluginServer
from jev_vs.stats import Stats
from tests.conftest import FakeJev


@pytest.fixture
async def plugin_server(tmp_path):
    srv = PluginServer(Config(plugin_port=0, log_dir=str(tmp_path)), Decider(FakeJev(), TH), RunLog(tmp_path), Hub(maxsize=4), Stats())
    await srv.start()
    yield srv
    await srv.stop()


@pytest.fixture
async def client(plugin_server):
    app = make_app(plugin_server)
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_index_serves_page(client):
    resp = await client.get("/")
    assert resp.status == 200
    body = await resp.text()
    assert "<title>" in body and "judgments" in body.lower() and "WebSocket" in body


async def test_ws_snapshot_then_decision(client, plugin_server):
    ws = await client.ws_connect("/ws")
    snap = json.loads((await ws.receive()).data)
    assert snap["type"] == "snapshot" and "stats" in snap and "decisions" in snap
    d = Decision(kind="direction", choice="north", index=0, probabilities={"north": 1.0}, confidence=0.4,
                 latency_ms=90.0, source="jev", input_tokens=50)
    plugin_server._record_decision(d, digest={}, entities={})
    got = json.loads((await ws.receive()).data)
    assert got["type"] == "decision" and got["choice"] == "north"
    await ws.close()


async def test_ws_control_forwards_to_plugin(client, plugin_server):
    reader, writer = await asyncio.open_connection("127.0.0.1", plugin_server.port)
    await asyncio.sleep(0.05)
    ws = await client.ws_connect("/ws")
    await ws.receive()   # snapshot
    await ws.send_str(json.dumps({"type": "control", "automation": False}))
    line = json.loads(await asyncio.wait_for(reader.readline(), 2))
    assert line == {"type": "control", "automation": False}
    writer.close()
    await ws.close()


async def test_slow_ws_client_is_dropped_without_blocking(client, plugin_server):
    ws = await client.ws_connect("/ws")
    await ws.receive()
    for i in range(20):   # hub maxsize is 4; the client never reads
        plugin_server.hub.publish({"type": "stats", "n": i})
    await asyncio.sleep(0.1)
    assert plugin_server.hub.client_count == 0
    msg = await ws.receive()
    assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.TEXT)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dashboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jev_vs.dashboard'`.

- [ ] **Step 3: Implement dashboard.py**

```python
"""Live dashboard: one static page plus a WebSocket fed by the Hub."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import WSMsgType, web

from .server import PluginServer

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def make_app(server: PluginServer) -> web.Application:
    app = web.Application()

    async def index(_request: web.Request) -> web.Response:
        return web.Response(text=(STATIC / "index.html").read_text(encoding="utf-8"), content_type="text/html")

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        q = server.hub.subscribe()
        await ws.send_str(json.dumps({
            "type": "snapshot", "stats": server.stats.snapshot(), "decisions": server.latest_decisions,
            "log": server.recent_log, "run": server.current_run,
        }))

        async def pump() -> None:
            try:
                while True:
                    msg = await q.get()
                    if not server.hub.is_subscribed(q):
                        break   # dropped by the hub for falling behind
                    await ws.send_str(json.dumps(msg))
            except (ConnectionResetError, RuntimeError):
                pass
            finally:
                await ws.close()

        pump_task = asyncio.create_task(pump())
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "control":
                    await server.send_control(bool(data.get("automation", True)))
        finally:
            server.hub.unsubscribe(q)
            pump_task.cancel()
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    return app


async def run_dashboard(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("dashboard at http://%s:%d/", host, port)
    return runner
```

- [ ] **Step 4: Write static/index.html**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jev Survivors Ops</title>
<style>
  :root { --bg:#050806; --panel:#0b120d; --line:#1d3a25; --ink:#b8f0c3; --dim:#5f8a68; --hot:#39ff7a; --warn:#ffb347; --bad:#ff5c5c; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; }
  header { display:flex; flex-wrap:wrap; gap:14px; align-items:center; padding:8px 14px; border-bottom:1px solid var(--line); background:var(--panel); position:sticky; top:0; }
  header b { color:var(--hot); }
  .stat { color:var(--dim); } .stat span { color:var(--ink); }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--bad); margin-right:4px; }
  .dot.on { background:var(--hot); }
  button { background:transparent; color:var(--hot); border:1px solid var(--hot); padding:3px 10px; font:inherit; cursor:pointer; }
  button.paused { color:var(--warn); border-color:var(--warn); }
  main { display:grid; grid-template-columns: 1fr 1fr; gap:12px; padding:12px 14px; }
  @media (max-width:900px) { main { grid-template-columns:1fr; } }
  section { background:var(--panel); border:1px solid var(--line); padding:10px; }
  h2 { margin:0 0 8px; font-size:11px; letter-spacing:.14em; color:var(--dim); text-transform:uppercase; }
  .card { border:1px solid var(--line); padding:8px; margin-bottom:8px; }
  .card .q { color:var(--dim); margin-bottom:6px; white-space:pre-wrap; }
  .tag { display:inline-block; border:1px solid var(--hot); color:var(--hot); padding:0 5px; margin-right:6px; font-size:10px; }
  .row { display:grid; grid-template-columns: 120px 1fr 48px; gap:6px; align-items:center; margin:2px 0; color:var(--dim); }
  .row.win { color:var(--hot); }
  .bar { height:8px; background:#122117; border:1px solid var(--line); }
  .bar i { display:block; height:100%; background:var(--dim); }
  .row.win .bar i { background:var(--hot); }
  .meta { color:var(--dim); margin-top:4px; }
  canvas { width:100%; aspect-ratio:1; background:#070c09; border:1px solid var(--line); display:block; }
  #status { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:8px; }
  #log { max-height:220px; overflow:auto; }
  #log div { border-bottom:1px dashed var(--line); padding:2px 0; }
  #runs td, #runs th { padding:2px 6px; text-align:left; color:var(--dim); } #runs th { color:var(--ink); }
  .src-fallback { color:var(--warn); } .src-reused { color:var(--dim); }
</style>
</head>
<body>
<header>
  <b>JEV // SURVIVORS OPS</b>
  <span class="stat"><i class="dot" id="dot-plugin"></i>plugin</span>
  <span class="stat"><i class="dot" id="dot-jev"></i>jev</span>
  <span class="stat">run <span id="s-run">-</span></span>
  <span class="stat">calls <span id="s-calls">0</span></span>
  <span class="stat">last <span id="s-last">0</span>ms</span>
  <span class="stat">avg <span id="s-avg">0</span>ms</span>
  <span class="stat">cost $<span id="s-cost">0</span> (<span id="s-rate">0</span>/h)</span>
  <span class="stat">jev/fallback/reused <span id="s-mix">0/0/0</span></span>
  <button id="pause">PAUSE</button>
</header>
<main>
  <section>
    <h2>Judgments</h2>
    <div id="cards"></div>
  </section>
  <section>
    <h2>Radar</h2>
    <div id="status"></div>
    <canvas id="radar" width="480" height="480"></canvas>
    <h2 style="margin-top:12px">Log</h2>
    <div id="log"></div>
    <h2 style="margin-top:12px">Runs this session</h2>
    <table id="runs"><thead><tr><th>character</th><th>stage</th><th>seconds</th><th>level</th><th>jev</th><th>fallback</th></tr></thead><tbody></tbody></table>
  </section>
</main>
<script>
(() => {
  const KINDS = ["direction", "level_up", "weapon_select", "arcana_select", "character", "stage"];
  const SECTORS = ["north","north_east","east","south_east","south","south_west","west","north_west"];
  const PRESSURE_ALPHA = { none: 0.0, light: 0.15, moderate: 0.35, heavy: 0.6 };
  let automation = true;
  const $ = (id) => document.getElementById(id);

  function renderStats(s) {
    $("dot-plugin").classList.toggle("on", !!s.plugin_connected);
    $("dot-jev").classList.toggle("on", !!s.jev_ok);
    $("s-calls").textContent = s.calls; $("s-last").textContent = s.last_latency_ms; $("s-avg").textContent = s.avg_latency_ms;
    $("s-cost").textContent = (s.cost_usd || 0).toFixed(4); $("s-rate").textContent = (s.cost_per_hour_usd || 0).toFixed(2);
    $("s-mix").textContent = `${s.jev_calls}/${s.fallback_calls}/${s.reused}`;
  }

  function card(kind) {
    let el = document.querySelector(`.card[data-kind="${kind}"]`);
    if (!el) { el = document.createElement("div"); el.className = "card"; el.dataset.kind = kind; $("cards").appendChild(el); }
    return el;
  }

  function renderDecision(d) {
    const el = card(d.kind);
    const keys = Object.keys(d.probabilities || {});
    keys.sort((a, b) => (d.probabilities[b] - d.probabilities[a]));
    const rows = keys.map(k => {
      const p = d.probabilities[k] || 0;
      const label = (d.labels && d.labels[k]) || k;
      return `<div class="row ${k === d.choice ? "win" : ""}"><span title="${label}">${label.slice(0, 18)}</span><div class="bar"><i style="width:${(p * 100).toFixed(1)}%"></i></div><span>${p.toFixed(2)}</span></div>`;
    }).join("");
    el.innerHTML = `<span class="tag">${d.kind.toUpperCase()}</span><span class="q">${(d.instructions || "").slice(0, 220)}</span>${rows}
      <div class="meta">conf ${(d.confidence || 0).toFixed(2)} · ${d.latency_ms || 0}ms · <span class="src-${d.source}">${d.source}</span></div>`;
    if (d.kind === "direction") renderRadar(d);
  }

  function renderStatus(p) {
    if (!p) return;
    $("status").innerHTML = [`hp ${p.hp_bucket} (${Math.round(p.hp)}/${Math.round(p.max_hp)})`, `level ${p.level}`, `minute ${p.minute}`,
      `weapons: ${(p.weapons || []).join(", ") || "-"}`, `passives: ${(p.passives || []).join(", ") || "-"}`].map(t => `<span>${t}</span>`).join("");
  }

  function renderRadar(d) {
    const cv = $("radar"), ctx = cv.getContext("2d"), W = cv.width, H = cv.height, cx = W / 2, cy = H / 2, R = W / 2 - 6;
    ctx.clearRect(0, 0, W, H);
    const sectors = (d.digest && d.digest.sectors) || {};
    renderStatus(d.digest && d.digest.player);
    SECTORS.forEach((name, i) => {
      const a0 = (i * 45 - 22.5 - 90) * Math.PI / 180, a1 = a0 + Math.PI / 4;
      const s = sectors[name] || {};
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, R, a0, a1); ctx.closePath();
      ctx.fillStyle = `rgba(255,92,92,${PRESSURE_ALPHA[s.pressure] || 0})`; ctx.fill();
      ctx.strokeStyle = "#1d3a25"; ctx.stroke();
      if (s.gems && s.gems !== "none") { ctx.fillStyle = "rgba(57,255,122,0.12)"; ctx.fill(); }
    });
    const ent = d.entities || {}, half = (ent.screen && ent.screen.half_h) || 1;
    const scale = R / (half * 1.6);
    const dot = (list, color, r) => (list || []).forEach(e => {
      ctx.beginPath(); ctx.arc(cx + e.x * scale, cy - e.y * scale, r, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
    });
    dot(ent.gems, "#39ff7a", 2); dot(ent.pickups, "#ffb347", 4);
    dot((ent.enemies || []).filter(e => !e.boss), "#ff5c5c", 3); dot((ent.enemies || []).filter(e => e.boss), "#ff2b2b", 7);
    ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2); ctx.fillStyle = "#b8f0c3"; ctx.fill();
    if (d.choice && d.choice !== "stay") {
      const idx = SECTORS.indexOf(d.choice), ang = (idx * 45 - 90) * Math.PI / 180;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(ang) * R * 0.5, cy + Math.sin(ang) * R * 0.5);
      ctx.strokeStyle = "#39ff7a"; ctx.lineWidth = 3; ctx.stroke(); ctx.lineWidth = 1;
    }
  }

  function addLog(e) {
    const div = document.createElement("div");
    div.textContent = `${new Date((e.t || Date.now() / 1000) * 1000).toLocaleTimeString()}  ${e.text}`;
    $("log").prepend(div);
    while ($("log").childElementCount > 50) $("log").lastElementChild.remove();
  }

  function addRun(summary) {
    if (!summary) return;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${summary.character || "-"}</td><td>${summary.stage || "-"}</td><td>${summary.seconds || 0}</td><td>${summary.level || 0}</td><td>${summary.jev_calls ?? "-"}</td><td>${summary.fallback_calls ?? "-"}</td>`;
    document.querySelector("#runs tbody").prepend(tr);
  }

  let ws;
  function connect() {
    ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "snapshot") {
        renderStats(m.stats); Object.values(m.decisions || {}).forEach(renderDecision);
        (m.log || []).slice().reverse().forEach(addLog); $("s-run").textContent = (m.run && m.run.character) || "-";
      } else if (m.type === "stats") renderStats(m);
      else if (m.type === "decision") renderDecision(m);
      else if (m.type === "event") addLog(m);
      else if (m.type === "run") { if (m.phase === "end") addRun(m.summary); $("s-run").textContent = m.phase === "start" ? "starting" : "-"; }
    };
    ws.onclose = () => setTimeout(connect, 1000);
  }
  $("pause").onclick = () => {
    automation = !automation;
    $("pause").textContent = automation ? "PAUSE" : "RESUME"; $("pause").classList.toggle("paused", !automation);
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "control", automation }));
  };
  KINDS.forEach(card);
  connect();
})();
</script>
</body>
</html>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_dashboard.py -v`
Expected: all PASS. If `test_slow_ws_client_is_dropped_without_blocking` fails because the hub drop is not observed by `pump`, check that `Hub.publish` discards the queue before returning and that `pump` checks `is_subscribed` after every `get`.

- [ ] **Step 6: Commit**

```bash
git add brain/jev_vs/dashboard.py brain/jev_vs/static/index.html brain/tests/test_dashboard.py
git commit -m "feat(brain): live ops dashboard over WebSocket"
```

---

### Task 8: CLI entry point and fake plugin script

**Files:**
- Create: `brain/jev_vs/__main__.py`
- Create: `scripts/fake_plugin.py`
- Create: `brain/tests/test_main.py`

**Interfaces:**
- Produces: `jev_vs.__main__.build(config: Config) -> tuple[PluginServer, web.Application]`, `jev_vs.__main__.main(argv: list[str] | None = None) -> int` accepting `--config PATH` (default `config.toml` next to `pyproject.toml` if present) and `--log-level`.
- Produces: `scripts/fake_plugin.py` with `--port`, `--ticks N`, `--hz`, `--replay RUN_DIR`; prints every reply; sends `hello`, then either synthetic ticks or the `state` field of each line of `RUN_DIR/ticks.jsonl`, one `level_up` event, and `game_over`.

- [ ] **Step 1: Write the failing test**

`brain/tests/test_main.py`:

```python
from jev_vs.__main__ import build, parse_args
from jev_vs.config import Config


def test_parse_args_defaults_and_overrides(tmp_path):
    a = parse_args([])
    assert a.log_level == "INFO"
    p = tmp_path / "x.toml"
    p.write_text("[plugin]\nport = 1\n")
    a = parse_args(["--config", str(p), "--log-level", "DEBUG"])
    assert a.config == p and a.log_level == "DEBUG"


async def test_build_wires_server_and_app(tmp_path):
    srv, app = build(Config(plugin_port=0, log_dir=str(tmp_path)))
    assert srv.config.plugin_port == 0
    routes = {r.resource.canonical for r in app.router.routes()}
    assert "/" in routes and "/ws" in routes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL with `ImportError: cannot import name 'build'`.

- [ ] **Step 3: Implement __main__.py**

```python
"""python -m jev_vs  |  uv run jev-vs"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiohttp import web

from .config import Config, load_config
from .dashboard import make_app, run_dashboard
from .decide import Decider
from .hub import Hub
from .jev_client import JevClient
from .questions import DEFAULT_THRESHOLDS
from .runlog import RunLog
from .server import PluginServer
from .stats import Stats

log = logging.getLogger("jev_vs")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    default_cfg = Path(__file__).resolve().parent.parent / "config.toml"
    p = argparse.ArgumentParser(prog="jev-vs", description="Jev plays Vampire Survivors: brain")
    p.add_argument("--config", type=Path, default=default_cfg if default_cfg.exists() else None)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def build(config: Config, jev=None) -> tuple[PluginServer, web.Application]:
    jev = jev or JevClient(model=config.model, timeout_s=config.request_timeout_s, max_retries=config.max_retries)
    server = PluginServer(config, Decider(jev, DEFAULT_THRESHOLDS), RunLog(Path(config.log_dir)), Hub(), Stats())
    return server, make_app(server)


async def run(config: Config) -> None:
    if not os.environ.get("TYPESAFE_API_KEY"):
        log.warning("TYPESAFE_API_KEY is not set; every decision will be a fallback")
    server, app = build(config)
    await server.start()
    runner = await run_dashboard(app, config.dashboard_host, config.dashboard_port)
    log.info("brain ready: plugin port %d, dashboard http://%s:%d/", server.port, config.dashboard_host, config.dashboard_port)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    log.info("shutting down")
    await server.stop()
    await runner.cleanup()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    asyncio.run(run(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write scripts/fake_plugin.py**

```python
#!/usr/bin/env python3
"""Pretend to be the game plugin. Usage:

  uv run --project brain python scripts/fake_plugin.py --ticks 20 --hz 4
  uv run --project brain python scripts/fake_plugin.py --replay runs/20260917-220000

Prints each reply. Needs a running brain (uv run --project brain jev-vs).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
from pathlib import Path


def synthetic_state(i: int) -> dict:
    ang = i * 0.3
    enemies = [{"x": 3 * math.cos(ang + k), "y": 3 * math.sin(ang + k), "hp": 10, "type": "BAT", "boss": False} for k in range(6)]
    gems = [{"x": random.uniform(-4, 4), "y": random.uniform(-3, 3), "value": 1} for _ in range(5)]
    return {
        "player": {"x": 0, "y": 0, "hp": 60 + 20 * math.sin(i / 5), "max_hp": 100, "level": 1 + i // 10, "xp": 5,
                   "xp_to_next": 30, "minute": i // 240, "seconds": i / 4, "character": "ANTONIO",
                   "weapons": [{"id": "WHIP", "level": 2, "max": False}], "passives": []},
        "enemies": enemies, "gems": gems, "pickups": [], "screen": {"half_w": 8.0, "half_h": 4.5},
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=48231)
    ap.add_argument("--ticks", type=int, default=20)
    ap.add_argument("--hz", type=float, default=4.0)
    ap.add_argument("--replay", type=Path, default=None)
    args = ap.parse_args()

    reader, writer = await asyncio.open_connection(args.host, args.port)
    mid = 0

    async def send(msg: dict) -> dict | None:
        nonlocal mid
        if "id" not in msg and msg["type"] != "hello":
            mid += 1
            msg["id"] = mid
        writer.write((json.dumps(msg) + "\n").encode())
        await writer.drain()
        if msg["type"] == "hello":
            return None
        reply = json.loads(await asyncio.wait_for(reader.readline(), 5))
        print(json.dumps(reply))
        return reply

    await send({"type": "hello", "game_version": "fake", "plugin_version": "fake"})
    await send({"type": "event", "event": "character_select", "options": [
        {"id": "ANTONIO", "name": "Antonio Belpaese", "description": "Gains 10% more damage every 10 levels.", "starting_weapon": "WHIP"},
        {"id": "IMELDA", "name": "Imelda Belpaese", "description": "Gains 10% more experience every 5 levels.", "starting_weapon": "MAGIC_MISSILE"},
    ]})
    await send({"type": "event", "event": "stage_select", "options": [
        {"id": "FOREST", "name": "Mad Forest", "description": "The Castle is a lie, but there's plenty of things to do."},
        {"id": "LIBRARY", "name": "Inlaid Library", "description": "Corridors, few open spaces."},
    ]})
    states = [synthetic_state(i) for i in range(args.ticks)]
    if args.replay:
        states = [json.loads(l)["state"] for l in (args.replay / "ticks.jsonl").read_text().splitlines()]
    for i, st in enumerate(states):
        await send({"type": "tick", "t": i / args.hz, "state": st})
        await asyncio.sleep(1.0 / args.hz)
        if i == len(states) // 2:
            await send({"type": "event", "event": "level_up", "options": [
                {"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 3, "is_new": False, "description": "Attacks horizontally, passes through enemies."},
                {"index": 1, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 1, "is_new": True, "description": "Raises inflicted damage by 10%."},
            ], "build": {"weapons": ["WHIP L2"], "passives": [], "level": 2, "minute": 0}})
    await send({"type": "event", "event": "game_over", "summary": {"character": "ANTONIO", "stage": "FOREST", "seconds": len(states) / args.hz, "level": 3, "kills": 40, "stage_complete": False}})
    writer.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Run tests to verify they pass, then a manual end-to-end check**

Run: `uv run pytest -v`
Expected: all PASS.

Manual check (two terminals, from the repo root):

```bash
# terminal 1
cd brain && uv run jev-vs
# terminal 2
uv run --project brain python scripts/fake_plugin.py --ticks 12
```

Expected: terminal 2 prints `pick` replies for character and stage, twelve `move` replies (source `fallback` if `TYPESAFE_API_KEY` is unset, `jev` if set), one `pick` for the level-up, and one `noop`. Open `http://127.0.0.1:48232/` and confirm the direction card's bars and the radar animate, the character and stage cards fill, the log shows the picks, and the runs table gains one row after the `game_over`. Confirm `brain/runs/<stamp>/summary.json` exists with `ticks: 12`.

- [ ] **Step 6: Commit**

```bash
git add brain/jev_vs/__main__.py brain/tests/test_main.py scripts/fake_plugin.py
git commit -m "feat(brain): CLI entry point and fake plugin replay script"
```

---

### Task 9: Live replay tests against the real Jev API

**Files:**
- Create: `brain/tests/test_live.py`

**Interfaces:**
- Consumes: `JevClient`, `Decider`, `questions`, recorded ticks under `brain/runs/*/ticks.jsonl` when present, else synthetic states.

- [ ] **Step 1: Write the live tests**

```python
"""Real API calls. Run with:  TYPESAFE_API_KEY=... uv run pytest -m live -v"""
import json
import os
import time
from pathlib import Path

import pytest

from jev_vs.decide import Decider
from jev_vs.jev_client import JevClient
from jev_vs.questions import DEFAULT_THRESHOLDS, DIRECTIONS
from tests.conftest import enemy, gem, make_state

pytestmark = pytest.mark.live
needs_key = pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="TYPESAFE_API_KEY not set")


def _states() -> list[dict]:
    runs = sorted(Path("runs").glob("*/ticks.jsonl"))
    if runs:
        lines = runs[-1].read_text().splitlines()[:8]
        return [json.loads(l)["state"] for l in lines]
    return [
        make_state(enemies=[enemy(0, 0.3), enemy(0.2, 0.4), enemy(-0.1, 0.5)], gems=[gem(0, -1.5)], hp=30),
        make_state(gems=[gem(2, 0), gem(2.2, 0.1)], hp=95),
        make_state(),
    ]


@needs_key
async def test_direction_answers_are_well_formed_and_fast():
    jev = JevClient(model="jev-latest", timeout_s=2.0, max_retries=1)
    dec = Decider(jev, DEFAULT_THRESHOLDS)
    try:
        for st in _states():
            t0 = time.perf_counter()
            _, d = await dec.direction(st)
            assert d.source == "jev", "live call fell back"
            assert d.choice in DIRECTIONS
            assert abs(sum(d.probabilities.values()) - 1.0) < 0.02
            assert 0.0 <= d.confidence <= 1.0
            assert (time.perf_counter() - t0) < 2.0
    finally:
        await jev.aclose()


@needs_key
async def test_danger_north_with_low_hp_does_not_walk_north():
    jev = JevClient(model="jev-latest", timeout_s=2.0, max_retries=1)
    dec = Decider(jev, DEFAULT_THRESHOLDS)
    try:
        st = make_state(enemies=[enemy(0, 0.3), enemy(0.2, 0.4), enemy(-0.1, 0.5), enemy(0, 0.6)], hp=15)
        _, d = await dec.direction(st)
        assert d.choice not in ("north", "north_east", "north_west")
    finally:
        await jev.aclose()


@needs_key
async def test_level_up_prefers_owned_weapon_over_random_new_item():
    jev = JevClient(model="jev-latest", timeout_s=2.0, max_retries=1)
    dec = Decider(jev, DEFAULT_THRESHOLDS)
    try:
        opts = [
            {"index": 0, "id": "SKULL_O_MANIAC", "name": "Skull O'Maniac", "kind": "passive", "level": 1, "is_new": True, "description": "Increases enemy speed, health, quantity and frequency."},
            {"index": 1, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 4, "is_new": False, "description": "Attacks horizontally, passes through enemies. Fires one more projectile."},
        ]
        d = await dec.pick("level_up", opts, {"weapons": ["WHIP L3"], "passives": [], "level": 4, "minute": 2})
        assert d.source == "jev" and d.choice == "WHIP"
    finally:
        await jev.aclose()
```

- [ ] **Step 2: Run without a key to verify the tests skip, then with a key**

Run: `uv run pytest -m live -v`
Expected without key: 3 SKIPPED. With `TYPESAFE_API_KEY` exported: 3 PASSED. If the second or third test fails, that is a signal to tune wording in `questions.py`, not a code bug; record the observed choice and probabilities in the commit message.

- [ ] **Step 3: Confirm the default run still excludes live tests**

Run: `uv run pytest -q`
Expected: live tests not collected as failures (deselected by `addopts`).

- [ ] **Step 4: Commit**

```bash
git add brain/tests/test_live.py
git commit -m "test(brain): live replay tests against the Jev API behind the live marker"
```

---

## Self-review notes

- Spec coverage: protocol (Task 1, 6), digest and wording (2, 3), Jev client and fallbacks (4), run logs and stats (5), server behaviours including reused ticks and run lifecycle (6), dashboard panels and control button (7), CLI and fake plugin (8), live replay tests (9). The `weapon_select` event and `evolution_ready` flag are handled in Task 3 and 6.
- The plugin plan defines the raw state shape the brain consumes; the two plans agree on every field name listed in spec section 4.
