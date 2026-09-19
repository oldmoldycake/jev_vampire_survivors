# Pinned character and stage: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A human can pin a character and a stage from the dashboard, and the brain applies the
pin instead of asking Jev — no restart, no plugin change, and today's behaviour unchanged when
nothing is pinned.

**Architecture:** A new `PinStore` (`brain/jev_vs/pins.py`) holds the two pins and a cache of the
last option list seen per menu, persisted to one JSON file. `server.py` decides whether a pin is
honourable — it has the options and owns the event log — and passes a `pinned_index` down to
`Decider.pick`, whose contract becomes "this index is offered, use it". A pinned pick returns an
ordinary `Decision` with `source="human"`, so the run log, the dashboard card, the plugin reply
and `current_run` all work unchanged downstream.

**Tech Stack:** Python 3.12, asyncio, aiohttp, pytest (`asyncio_mode = "auto"`), ruff, uv.

**Spec:** `docs/superpowers/specs/2026-09-18-windows-support-and-pinned-picks-design.md` — Part A
is §3. Read §3 alongside this plan; every task cites the subsection it implements.

## Global Constraints

- **Zero `mod/` changes.** Pinning is a decision, and decisions live in the brain (CLAUDE.md
  architecture rule). The plugin keeps sending the same `character_select` / `stage_select`
  events and applying the same `pick` reply; it never learns a human was involved.
- **Zero `questions.py` changes.** Pinning removes a question rather than adding wording or a
  threshold. No new prompt text and no new cut-off anywhere in this plan.
- **No raw numbers reach the model.** Nothing in this plan builds an `Ask.state` or a
  `Choice.criteria` string, so this rule is satisfied by construction — do not add one.
- **Never run `pytest -m live`.** Those tests bill a real TypeSafe API key per call. The default
  `addopts = "-m 'not live'"` already deselects them; don't override it.
- **Never print, log, echo or interpolate `TYPESAFE_API_KEY`.** It lives in the git-ignored
  repo-root `.env`; hand it to processes with `uv run --env-file ../.env`.
- **Working directory matters.** `uv run pytest`, `uv run ruff check .` and
  `uv run ruff format --check .` all run from `brain/`. `scripts/fake_plugin.py` runs from the
  repository root. `log_dir` and the new `state_file` both resolve relative to the working
  directory.
- **Style:** ruff, `line-length = 120`, `select = ["E", "F", "I", "UP", "B"]`. The brain is laid
  out wide on purpose. Comments explain *why*. Match the surrounding file.
- **Commits:** Conventional Commits, lowercase imperative subject, no trailing period, scope
  `brain` for code and no scope for `docs:`. Every commit ends with the two attribution trailers
  shown in the commit steps.
- **Do not edit anything under `docs/superpowers/plans/` or `docs/superpowers/ledgers/` other
  than this file.** They are historical records.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `brain/jev_vs/pins.py` (new) | `PinStore`: the two pins, the roster cache, JSON persistence, and pin→index resolution against an offered option list. Holds no policy about *when* a pin applies. |
| `brain/jev_vs/config.py` | One new key: `state_file`, default `"pins.json"`, read from `[brain]`. |
| `brain/jev_vs/decide.py` | `Decider.pick` gains `pinned_index`; a pinned pick becomes a `Decision(source="human")` without an API call. |
| `brain/jev_vs/stats.py` | `record()` gains a third branch so a human pick is neither a Jev call nor a fallback. |
| `brain/jev_vs/server.py` | Owns the policy: cache and broadcast the roster, resolve the pin, warn when a pin is not offered, expose `set_pin()` for the dashboard. |
| `brain/jev_vs/dashboard.py` | Routes an inbound `pin` message to `server.set_pin()`; adds `pins` and `rosters` to the WS snapshot. |
| `brain/jev_vs/static/index.html` | Two `<select>` elements in the HUD bar, populated from the snapshot and `roster` messages. |
| `brain/jev_vs/__main__.py` | Builds the `PinStore` from `config.state_file` and loads it at startup. |
| `brain/tests/test_pins.py` (new) | `PinStore` unit tests, including the corrupt-state-file path. |
| `.gitignore`, `brain/config.toml`, `README.md`, `CHANGELOG.md` | The state file is git-ignored; the new key is documented; the feature is documented. |

`CLAUDE.md` needs no change: every architecture rule it states stays true, and it lists no
per-file inventory. Don't edit it.

---

## Task 0: Branch

- [ ] **Step 1: Confirm the working tree is clean and branch off main**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git status --short          # expect only the untracked spec + this plan
git switch -c feat/pinned-character-and-stage
```

Expected: `Switched to a new branch 'feat/pinned-character-and-stage'`. Every commit below lands
on this branch; nothing is committed to `main`.

---

## Task 1: `PinStore` and the `state_file` config key

Implements spec §3.2. Pure data plus persistence — no policy about when a pin applies.

**Files:**
- Create: `brain/jev_vs/pins.py`
- Create: `brain/tests/test_pins.py`
- Modify: `brain/jev_vs/config.py:12-20` (dataclass), `:31-41` (`load_config`)
- Modify: `brain/config.toml` (add the key under `[brain]`)
- Modify: `brain/tests/test_config.py:6-22`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `jev_vs.pins.PIN_KINDS: tuple[str, str]` == `("character", "stage")`
  - `jev_vs.pins.PinStore(path: Path | None = None)` with attributes
    `pins: dict[str, str | None]` and `rosters: dict[str, list[dict]]` (both keyed by
    `PIN_KINDS`), and methods `load() -> None`, `save() -> None`, `to_dict() -> dict`,
    `pin_for(kind: str) -> str | None`, `set_pin(kind: str, option_id: str | None) -> bool`,
    `remember_options(kind: str, options: list[dict]) -> list[dict]`,
    `index_of(kind: str, options: list[dict]) -> int | None`
  - `jev_vs.config.Config.state_file: str` (default `"pins.json"`)

- [ ] **Step 1: Write the failing tests**

Create `brain/tests/test_pins.py`:

```python
import json

from jev_vs.pins import PIN_KINDS, PinStore


def test_new_store_has_no_pins_and_no_rosters():
    store = PinStore()
    assert PIN_KINDS == ("character", "stage")
    assert store.pins == {"character": None, "stage": None}
    assert store.rosters == {"character": [], "stage": []}
    assert store.pin_for("character") is None
    assert store.pin_for("level_up") is None


def test_set_pin_accepts_the_two_pinnable_kinds_and_rejects_the_rest():
    store = PinStore()
    assert store.set_pin("level_up", "SPINACH") is False
    assert store.set_pin("character", 7) is False
    assert store.set_pin("character", "ANTONIO") is True
    assert store.pin_for("character") == "ANTONIO"
    assert store.set_pin("character", None) is True
    assert store.pin_for("character") is None


def test_remember_options_keeps_only_id_and_name():
    store = PinStore()
    cached = store.remember_options(
        "stage",
        [
            {"id": "FOREST", "name": "Mad Forest", "description": "a long description a dropdown does not need"},
            {"name": "no id at all"},
            "not even a dict",
        ],
    )
    assert cached == [{"id": "FOREST", "name": "Mad Forest"}]
    assert store.rosters["stage"] == cached
    assert store.remember_options("level_up", [{"id": "SPINACH", "name": "Spinach"}]) == []


def test_index_of_finds_the_pin_and_reports_one_that_is_not_offered():
    store = PinStore()
    opts = [{"id": "ANTONIO", "name": "Antonio"}, {"id": "IMELDA", "name": "Imelda"}]
    assert store.index_of("character", opts) is None  # nothing pinned
    store.set_pin("character", "IMELDA")
    assert store.index_of("character", opts) == 1
    store.set_pin("character", "POE")  # pinned, but not unlocked yet
    assert store.index_of("character", opts) is None
    assert store.pin_for("character") == "POE"  # the pin survives not being offered


def test_pin_and_roster_round_trip_through_the_state_file(tmp_path):
    path = tmp_path / "pins.json"
    store = PinStore(path)
    store.set_pin("character", "ANTONIO")
    store.remember_options("stage", [{"id": "FOREST", "name": "Mad Forest"}])
    again = PinStore(path)
    again.load()
    assert again.pin_for("character") == "ANTONIO"
    assert again.rosters["stage"] == [{"id": "FOREST", "name": "Mad Forest"}]
    assert json.loads(path.read_text())["pins"]["character"] == "ANTONIO"


def test_a_corrupt_state_file_yields_an_empty_store(tmp_path, caplog):
    path = tmp_path / "pins.json"
    path.write_text("{not json at all")
    store = PinStore(path)
    store.load()
    assert store.pins == {"character": None, "stage": None}
    assert store.rosters == {"character": [], "stage": []}
    assert "ignoring unreadable pin state" in caplog.text


def test_a_state_file_holding_junk_shapes_yields_an_empty_store(tmp_path):
    path = tmp_path / "pins.json"
    path.write_text(json.dumps({"pins": {"character": 7, "stage": None}, "rosters": {"stage": "nope"}}))
    store = PinStore(path)
    store.load()
    assert store.pin_for("character") is None
    assert store.rosters["stage"] == []


def test_a_missing_state_file_is_not_an_error(tmp_path):
    store = PinStore(tmp_path / "never-written.json")
    store.load()
    assert store.pin_for("stage") is None


def test_a_store_with_no_path_never_writes(tmp_path):
    store = PinStore()
    store.set_pin("stage", "FOREST")
    store.save()
    assert list(tmp_path.iterdir()) == []
    assert store.pin_for("stage") == "FOREST"
```

Add to `brain/tests/test_config.py` — inside `test_defaults_when_no_file`, after the `log_dir`
assertion:

```python
    assert cfg.state_file == "pins.json"
```

and change `test_file_overrides_defaults` to write and assert the new key:

```python
def test_file_overrides_defaults(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[plugin]\nport = 5000\n[brain]\ntick_hz = 2.5\nmodel = "jev-1.13.0"\nstate_file = "pins-test.json"\n')
    cfg = load_config(p)
    assert cfg.plugin_port == 5000
    assert cfg.tick_hz == 2.5
    assert cfg.model == "jev-1.13.0"
    assert cfg.state_file == "pins-test.json"
    assert cfg.dashboard_port == 48232
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_pins.py tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jev_vs.pins'` for `test_pins.py`, and
`AttributeError: 'Config' object has no attribute 'state_file'` for the two config tests.

- [ ] **Step 3: Write `brain/jev_vs/pins.py`**

```python
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
```

- [ ] **Step 4: Add the config key**

In `brain/jev_vs/config.py`, add the field after `log_dir`:

```python
    log_dir: str = "runs"
    state_file: str = "pins.json"
```

and the corresponding line in `load_config`'s `replace(...)` call, after `log_dir=...`:

```python
        state_file=str(brain.get("state_file", cfg.state_file)),
```

In `brain/config.toml`, under `[brain]`, after `log_dir = "runs"`:

```toml
# Dashboard pins (character/stage) and the menu rosters behind their dropdowns.
# Relative to the working directory, exactly like log_dir.
state_file = "pins.json"
```

- [ ] **Step 5: Git-ignore the state file**

In `.gitignore`, change the first block to:

```
# run logs, saved pins and decompiled game code
runs/
pins.json
decompiled/
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_pins.py tests/test_config.py -v`
Expected: PASS, 11 tests.

Then the whole suite and the lint contract:

Run: `cd brain && uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: all pass, nothing reformatted.

- [ ] **Step 7: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add brain/jev_vs/pins.py brain/tests/test_pins.py brain/jev_vs/config.py brain/config.toml brain/tests/test_config.py .gitignore
git commit -m "feat(brain): add a store for human-pinned character and stage picks

Remembers the two pins and the last option list each menu offered, persisted to
the file named by the new [brain] state_file key. A state file that cannot be
read degrades to an empty store so a bad file never stops the brain playing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Task 2: `Decider.pick` honours a pinned index

Implements spec §3.3 step 3. The `Ask` is still built — it is pure, does no I/O, and the
dashboard card needs its `labels` — but `_ask` is skipped entirely.

**Files:**
- Modify: `brain/jev_vs/decide.py:33` (the `source` comment), `:154-184` (`pick`)
- Test: `brain/tests/test_decide.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Decider.pick(kind: str, options: list[dict], build: dict | None = None,
  recent: list[str] | None = None, pinned_index: int | None = None) -> Decision`. When
  `pinned_index` is not None the returned `Decision` has `source == "human"`,
  `index == pinned_index`, `probabilities == {choice: 1.0}`, `confidence == 1.0`,
  `latency_ms == 0.0`, `input_tokens == 0` and `sampled is False`.

- [ ] **Step 1: Write the failing tests**

Append to `brain/tests/test_decide.py`:

```python
async def test_pick_with_a_pinned_index_never_asks_jev():
    fake = FakeJev(script={"character": ("ANTONIO", {"ANTONIO": 1.0}, 0.9)})
    dec = decide.Decider(fake, TH)
    opts = [
        {"id": "ANTONIO", "name": "Antonio", "description": "d"},
        {"id": "IMELDA", "name": "Imelda", "description": "d"},
    ]
    decision = await dec.pick("character", opts, pinned_index=1)
    assert decision.choice == "IMELDA" and decision.index == 1
    assert decision.source == "human"
    assert decision.probabilities == {"IMELDA": 1.0}
    assert decision.confidence == 1.0
    assert decision.latency_ms == 0.0 and decision.input_tokens == 0
    assert decision.sampled is False
    assert decision.labels["IMELDA"] == "Imelda"  # the dashboard card still gets its labels
    assert decision.instructions  # ... and the question text
    assert fake.calls == []  # no API call, so no cost and no menu latency


async def test_pick_with_a_pinned_index_skips_the_variety_sampler():
    # Left to itself the sampler would sometimes return ANTONIO here; pinned, it never can.
    fake = FakeJev(script={"character": ("ANTONIO", {"ANTONIO": 0.5, "IMELDA": 0.5}, 0.9)})
    dec = decide.Decider(fake, TH, rng=random.Random(1))
    opts = [
        {"id": "ANTONIO", "name": "Antonio", "description": "d"},
        {"id": "IMELDA", "name": "Imelda", "description": "d"},
    ]
    for _ in range(10):
        decision = await dec.pick("character", opts, recent=["IMELDA"], pinned_index=0)
        assert decision.choice == "ANTONIO" and decision.sampled is False
    assert fake.calls == []


async def test_pick_without_a_pinned_index_is_unchanged():
    fake = FakeJev(script={"stage": ("LIBRARY", {"LIBRARY": 1.0}, 0.7)})
    dec = decide.Decider(fake, TH)
    opts = [
        {"id": "FOREST", "name": "Mad Forest", "description": "d"},
        {"id": "LIBRARY", "name": "Inlaid Library", "description": "d"},
    ]
    decision = await dec.pick("stage", opts)
    assert decision.source == "jev" and decision.choice == "LIBRARY"
    assert len(fake.calls) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_decide.py -k pinned -v`
Expected: FAIL — `TypeError: Decider.pick() got an unexpected keyword argument 'pinned_index'`.

- [ ] **Step 3: Implement**

In `brain/jev_vs/decide.py`, widen the `source` comment on the dataclass field:

```python
    source: str  # "jev" | "human" | "fallback"
```

and replace the signature and opening of `pick`:

```python
    async def pick(
        self,
        kind: str,
        options: list[dict],
        build: dict | None = None,
        recent: list[str] | None = None,
        pinned_index: int | None = None,
    ) -> Decision:
        """Choose one option. `pinned_index`'s contract is "this index is offered, use it" —
        whether a human's pin is honourable for this menu is decided in server.py, which has
        the options and the event log (spec section 3.3)."""
        if not options:
            raise ValueError(f"{kind}: no options to pick from")
        ask = options_question(kind, options, build, recent=recent)
        if pinned_index is not None:
            # A human already decided. The Ask above is pure and the dashboard card needs its
            # labels, but asking Jev would spend money and menu latency to confirm a foregone
            # conclusion, so we don't; variety sampling is bypassed by construction.
            choice = ask.keys[pinned_index]
            return Decision(
                kind=kind,
                choice=choice,
                index=pinned_index,
                probabilities={choice: 1.0},
                confidence=1.0,
                latency_ms=0.0,
                source="human",
                input_tokens=0,
                instructions=ask.instructions,
                labels=ask.labels,
            )
        choice, probs, conf, latency, tokens = await self._ask(ask)
```

The rest of `pick` — the `source = "jev"` line onward — is untouched.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_decide.py -v`
Expected: PASS, every test in the file including the three new ones.

- [ ] **Step 5: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add brain/jev_vs/decide.py brain/tests/test_decide.py
git commit -m "feat(brain): let a pinned index short-circuit a Jev pick

pick() still builds the Ask, which is pure and carries the labels the dashboard
card needs, then returns a source=\"human\" Decision without calling the API.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Task 3: `Stats.record` stops counting a human pick as a fallback

Implements spec §3.4. This is the trap the spec calls out: `record()` currently has two branches,
and a `"human"` decision falling into the `else` would increment `fallback_calls` and set
`jev_ok = False`, lighting the dashboard's JEV lamp red for an API problem that never happened.

**Files:**
- Modify: `brain/jev_vs/stats.py:26-36`
- Test: `brain/tests/test_hub_stats.py`

**Interfaces:**
- Consumes: `Decision.source == "human"` from Task 2.
- Produces: no signature change. `snapshot()` is unchanged, so `calls` deliberately stops
  equalling `jev_calls + fallback_calls` once a pin is used.

- [ ] **Step 1: Write the failing tests**

Append to `brain/tests/test_hub_stats.py`:

```python
def test_stats_counts_a_human_pick_as_neither_jev_nor_fallback():
    s = Stats()
    s.record(_decision(source="jev", latency=100.0, tokens=500))
    s.record(_decision(source="human", latency=0.0, tokens=0))
    snap = s.snapshot()
    assert snap["calls"] == 2  # it was still a decision
    assert snap["jev_calls"] == 1 and snap["fallback_calls"] == 0
    assert snap["jev_ok"] is True  # a pinned pick is not an API failure
    assert snap["last_latency_ms"] == 100.0 and snap["avg_latency_ms"] == 100.0


def test_a_human_pick_does_not_clear_a_fallback_warning():
    s = Stats()
    s.record(_decision(source="fallback", latency=0.0, tokens=0))
    assert s.snapshot()["jev_ok"] is False
    s.record(_decision(source="human", latency=0.0, tokens=0))
    assert s.snapshot()["jev_ok"] is False  # the lamp stays on the last thing Jev actually did
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_hub_stats.py -v`
Expected: FAIL — `assert 0 == 1` on `fallback_calls`, and `assert False is True` on `jev_ok`.

- [ ] **Step 3: Implement**

In `brain/jev_vs/stats.py`, replace the body of `record`:

```python
    def record(self, d: Decision) -> None:
        self.calls += 1
        if d.source == "jev":
            self.jev_calls += 1
            self.jev_ok = True
            self.last_latency_ms = d.latency_ms
            self._latency_sum += d.latency_ms
        elif d.source == "human":
            # A human pinned this pick, so no API call was made and nothing went wrong.
            # Counting it as a fallback would light the dashboard's jev lamp for a failure
            # that did not happen (spec section 3.4). It stays in `calls` and nowhere else.
            pass
        else:
            self.fallback_calls += 1
            self.jev_ok = False
        self.input_tokens += d.input_tokens
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_hub_stats.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add brain/jev_vs/stats.py brain/tests/test_hub_stats.py
git commit -m "fix(brain): stop counting a human pick as a Jev fallback

A source=\"human\" decision fell into record()'s else branch, which incremented
fallback_calls and cleared jev_ok, reporting an API problem that never happened.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Task 4: the server resolves pins and broadcasts rosters

Implements spec §3.3 steps 1, 2 and 4. This task changes `PluginServer.__init__`, so it also
updates the two test helpers that construct one.

**Files:**
- Modify: `brain/jev_vs/server.py` — imports, `__init__:42-56`, a new `_resolve_pin` and
  `set_pin`, and the pick call in `_on_event:240-241`
- Modify: `brain/jev_vs/__main__.py:36-39` (`build`)
- Test: `brain/tests/test_server.py` (helper `_start:30-36`, plus four new tests)
- Modify: `brain/tests/test_dashboard.py:20-27` (fixture), `brain/tests/test_main.py:14-25`

**Interfaces:**
- Consumes: `PinStore`, `PIN_KINDS` (Task 1); `Decider.pick(..., pinned_index=...)` (Task 2);
  `Stats.record`'s human branch (Task 3).
- Produces:
  - `PluginServer(config, decider, runlog, hub, stats, pins: PinStore)` — `pins` is a new
    required sixth positional argument, reachable afterwards as `server.pins`.
  - `PluginServer.set_pin(kind: str, option_id: str | None) -> bool`
  - Hub message `{"type": "roster", "kind": "character" | "stage", "options": [{"id", "name"}]}`
  - Hub message `{"type": "pin", "kind": "character" | "stage", "id": str | None}`

- [ ] **Step 1: Write the failing tests**

In `brain/tests/test_server.py`, add the import:

```python
from jev_vs.pins import PinStore
```

replace the `_start` helper so it builds a store and accepts a prepared one:

```python
async def _start(tmp_path: Path, jev, pins: PinStore | None = None):
    hub = Hub()
    stats = Stats()
    store = pins if pins is not None else PinStore(tmp_path / "pins.json")
    srv = PluginServer(
        Config(plugin_port=0, log_dir=str(tmp_path)), Decider(jev, TH), RunLog(tmp_path), hub, stats, store
    )
    port = await srv.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    return srv, hub, stats, reader, writer
```

and append these four tests:

```python
async def test_pinned_character_is_applied_without_asking_jev(tmp_path):
    jev = FakeJev(script={"character": ("ANTONIO", {"ANTONIO": 1.0}, 0.9)})
    pins = PinStore(tmp_path / "pins.json")
    pins.set_pin("character", "IMELDA")
    srv, _hub, stats, reader, writer = await _start(tmp_path, jev, pins)
    chars = [
        {"id": "ANTONIO", "name": "Antonio", "description": "d"},
        {"id": "IMELDA", "name": "Imelda", "description": "d"},
    ]
    await _send(writer, {"id": 1, "type": "event", "event": "character_select", "options": chars})
    reply = await _recv(reader)
    assert reply["index"] == 1 and reply["choice"] == "IMELDA" and reply["source"] == "human"
    assert jev.calls == []  # the pin cost nothing
    snap = stats.snapshot()
    assert snap["calls"] == 1 and snap["jev_calls"] == 0 and snap["fallback_calls"] == 0
    assert snap["jev_ok"] is True
    assert srv.current_run["character"] == "IMELDA"
    writer.close()
    await srv.stop()


async def test_a_pin_that_is_not_offered_falls_through_to_jev(tmp_path):
    jev = FakeJev(script={"stage": ("LIBRARY", {"LIBRARY": 1.0}, 0.9)})
    pins = PinStore(tmp_path / "pins.json")
    pins.set_pin("stage", "MOONGOLOW")  # a stage this save has not unlocked
    srv, _hub, _stats, reader, writer = await _start(tmp_path, jev, pins)
    opts = [
        {"id": "FOREST", "name": "Mad Forest", "description": "d"},
        {"id": "LIBRARY", "name": "Inlaid Library", "description": "d"},
    ]
    await _send(writer, {"id": 1, "type": "event", "event": "stage_select", "options": opts})
    reply = await _recv(reader)
    assert reply["choice"] == "LIBRARY" and reply["source"] == "jev"
    assert len(jev.calls) == 1
    assert any("pinned MOONGOLOW not offered" in e["text"] for e in srv.recent_log)
    assert pins.pin_for("stage") == "MOONGOLOW"  # kept for when it does unlock
    writer.close()
    await srv.stop()


async def test_menu_options_are_cached_and_broadcast_as_a_roster(tmp_path):
    srv, hub, _stats, reader, writer = await _start(tmp_path, FakeJev())
    q = hub.subscribe()
    chars = [{"id": "ANTONIO", "name": "Antonio", "description": "a long description"}]
    await _send(writer, {"id": 1, "type": "event", "event": "character_select", "options": chars})
    await _recv(reader)
    msgs = [q.get_nowait() for _ in range(q.qsize())]
    roster = next(m for m in msgs if m["type"] == "roster")
    assert roster == {"type": "roster", "kind": "character", "options": [{"id": "ANTONIO", "name": "Antonio"}]}
    assert srv.pins.rosters["character"] == [{"id": "ANTONIO", "name": "Antonio"}]
    writer.close()
    await srv.stop()


async def test_set_pin_persists_broadcasts_and_refuses_other_kinds(tmp_path):
    srv, hub, _stats, reader, writer = await _start(tmp_path, FakeJev())
    q = hub.subscribe()
    assert srv.set_pin("character", "ANTONIO") is True
    assert srv.set_pin("level_up", "SPINACH") is False
    msgs = [q.get_nowait() for _ in range(q.qsize())]
    assert {"type": "pin", "kind": "character", "id": "ANTONIO"} in msgs
    reloaded = PinStore(tmp_path / "pins.json")
    reloaded.load()
    assert reloaded.pin_for("character") == "ANTONIO"
    assert srv.set_pin("character", None) is True
    assert any("pin cleared" in e["text"] for e in srv.recent_log)
    writer.close()
    await srv.stop()
```

In `brain/tests/test_dashboard.py`, add the import `from jev_vs.pins import PinStore` and give
the fixture a store:

```python
@pytest.fixture
async def plugin_server(tmp_path):
    srv = PluginServer(
        Config(plugin_port=0, log_dir=str(tmp_path)),
        Decider(FakeJev(), TH),
        RunLog(tmp_path),
        Hub(maxsize=4),
        Stats(),
        PinStore(tmp_path / "pins.json"),
    )
    await srv.start()
    yield srv
    await srv.stop()
```

In `brain/tests/test_main.py`, point `build()` at a state file inside `tmp_path` so a test run
never writes one into the repository, and assert the store was wired:

```python
async def test_build_wires_server_and_app(tmp_path):
    cfg = Config(plugin_port=0, log_dir=str(tmp_path), state_file=str(tmp_path / "pins.json"))
    srv, app = build(cfg)
    assert srv.config.plugin_port == 0
    routes = {r.resource.canonical for r in app.router.routes()}
    assert "/" in routes and "/ws" in routes
    assert srv.decider.jev is not None
    assert srv.pins.path == tmp_path / "pins.json"

    from tests.conftest import FakeJev

    fake = FakeJev()
    srv2, _ = build(cfg, jev=fake)
    assert srv2.decider.jev is fake
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_server.py tests/test_main.py -v`
Expected: FAIL — `TypeError: PluginServer.__init__() takes 6 positional arguments but 7 were
given`, and `AttributeError: 'PluginServer' object has no attribute 'set_pin'`.

- [ ] **Step 3: Implement the server changes**

In `brain/jev_vs/server.py`, add to the imports (alphabetical, after `.hub`):

```python
from .pins import PIN_KINDS, PinStore
```

Extend `__init__` — the new parameter is required and positional, like every other collaborator:

```python
    def __init__(self, config: Config, decider: Decider, runlog: RunLog, hub: Hub, stats: Stats, pins: PinStore):
        self.config = config
        self.decider = decider
        self.runlog = runlog
        self.hub = hub
        self.stats = stats
        self.pins = pins
```

(the rest of `__init__` is unchanged)

Add these two methods to the "helpers" section, after `send_control`:

```python
    def set_pin(self, kind: str, option_id: str | None) -> bool:
        """Pin a menu choice from the dashboard, or clear it with None. Re-broadcast either way so
        every open tab agrees. Pins apply from the next menu onward; a run in progress asked its
        character and stage questions long ago and has nothing to disturb."""
        if not self.pins.set_pin(kind, option_id):
            log.warning("ignoring pin request for kind %r id %r", kind, option_id)
            return False
        self.hub.publish({"type": "pin", "kind": kind, "id": option_id})
        self._note(f"{kind} pinned to {option_id}" if option_id else f"{kind} pin cleared; Jev decides")
        return True

    def _resolve_pin(self, kind: str, options: list[dict]) -> int | None:
        """Cache what this menu offered, tell the dashboards, and resolve any pin against it.
        Returns the index to apply, or None to ask Jev as usual."""
        if kind not in PIN_KINDS:
            return None
        self.hub.publish({"type": "roster", "kind": kind, "options": self.pins.remember_options(kind, options)})
        pinned = self.pins.pin_for(kind)
        if pinned is None:
            return None
        index = self.pins.index_of(kind, options)
        if index is None:
            # Leave the pin set: a character you are about to unlock stays pinned (spec 3.3).
            self._note(f"pinned {pinned} not offered; asked Jev")
        return index
```

In `_on_event`, replace the two lines that currently read

```python
        recent = _recent_values(self.run_history, kind) if kind in VARIETY_KINDS else None
        decision = await self.decider.pick(kind, options, msg.get("build"), recent=recent)
```

with

```python
        pinned_index = self._resolve_pin(kind, options)
        # A pinned pick never varies, so the "recently played" nudge would be wasted wording.
        varies = kind in VARIETY_KINDS and pinned_index is None
        recent = _recent_values(self.run_history, kind) if varies else None
        decision = await self.decider.pick(
            kind, options, msg.get("build"), recent=recent, pinned_index=pinned_index
        )
```

Place `pinned_index = self._resolve_pin(...)` after the `if event == "character_select":`
run-start block, so a run still opens before the pick is made.

- [ ] **Step 4: Wire the store in `__main__.build`**

In `brain/jev_vs/__main__.py`, add `from .pins import PinStore` to the imports (alphabetical,
after `.jev_client`) and replace `build`:

```python
def build(config: Config, jev=None) -> tuple[PluginServer, web.Application]:
    jev = jev or JevClient(model=config.model, timeout_s=config.request_timeout_s, max_retries=config.max_retries)
    pins = PinStore(Path(config.state_file))
    pins.load()  # a pin set in a previous session, and the rosters its dropdowns showed
    server = PluginServer(config, Decider(jev, DEFAULT_THRESHOLDS), RunLog(Path(config.log_dir)), Hub(), Stats(), pins)
    return server, make_app(server)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd brain && uv run pytest -v`
Expected: PASS — the whole offline suite, including the four new server tests and the untouched
`test_events_drive_run_log_and_picks` (which pins nothing and must still show `source == "jev"`).

Run: `cd brain && uv run ruff check . && uv run ruff format --check .`
Expected: both clean. If `ruff format` wants to reflow the long `PluginServer(...)` line in
`build`, run `uv run ruff format .` and take its output.

- [ ] **Step 6: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add brain/jev_vs/server.py brain/jev_vs/__main__.py brain/tests/test_server.py brain/tests/test_dashboard.py brain/tests/test_main.py
git commit -m "feat(brain): honour a pinned character or stage instead of asking Jev

The server caches what each menu offered, broadcasts it as a roster, and resolves
the pin against it. A pin that is not on offer warns in the event log and falls
through to Jev with the pin intact, for the character you are about to unlock.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Task 5: pin from the dashboard

Implements spec §3.5. Same socket, same trust model as the existing PAUSE control: the socket is
loopback and unauthenticated already, and a pin is strictly less powerful than pausing.

**Files:**
- Modify: `brain/jev_vs/dashboard.py:43-54` (snapshot), `:79-80` (inbound routing)
- Modify: `brain/jev_vs/static/index.html` (CSS block, HUD bar, JS)
- Test: `brain/tests/test_dashboard.py`

**Interfaces:**
- Consumes: `PluginServer.set_pin`, `server.pins` (Task 4).
- Produces: WS snapshot gains `"pins": {kind: id | null}` and
  `"rosters": {kind: [{"id", "name"}]}`; the page accepts inbound
  `{"type": "pin", "kind": ..., "id": ... | null}`.

- [ ] **Step 1: Write the failing tests**

Append to `brain/tests/test_dashboard.py`:

```python
async def _wait_for(predicate, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def test_index_offers_a_character_and_a_stage_select(client):
    body = await (await client.get("/")).text()
    assert 'id="pin-character"' in body and 'id="pin-stage"' in body
    assert "JEV DECIDES" in body


async def test_snapshot_carries_pins_and_rosters(client, plugin_server):
    plugin_server.pins.set_pin("character", "ANTONIO")
    plugin_server.pins.remember_options("stage", [{"id": "FOREST", "name": "Mad Forest"}])
    ws = await client.ws_connect("/ws")
    snap = json.loads((await ws.receive()).data)
    assert snap["pins"] == {"character": "ANTONIO", "stage": None}
    assert snap["rosters"]["stage"] == [{"id": "FOREST", "name": "Mad Forest"}]
    await ws.close()


async def test_ws_pin_message_reaches_the_store_and_can_clear_it(client, plugin_server):
    ws = await client.ws_connect("/ws")
    await ws.receive()  # snapshot
    await ws.send_str(json.dumps({"type": "pin", "kind": "character", "id": "IMELDA"}))
    assert await _wait_for(lambda: plugin_server.pins.pin_for("character") == "IMELDA")
    await ws.send_str(json.dumps({"type": "pin", "kind": "character", "id": None}))
    assert await _wait_for(lambda: plugin_server.pins.pin_for("character") is None)
    await ws.close()


async def test_ws_ignores_a_malformed_pin_message(client, plugin_server):
    ws = await client.ws_connect("/ws")
    await ws.receive()  # snapshot
    await ws.send_str(json.dumps({"type": "pin", "kind": 7, "id": "ANTONIO"}))
    await ws.send_str(json.dumps({"type": "pin", "kind": "character", "id": 12}))
    await ws.send_str(json.dumps({"type": "pin", "kind": "stage", "id": "FOREST"}))
    # the good one lands, which proves the bad two were dropped rather than fatal
    assert await _wait_for(lambda: plugin_server.pins.pin_for("stage") == "FOREST")
    assert plugin_server.pins.pin_for("character") is None
    await ws.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd brain && uv run pytest tests/test_dashboard.py -v`
Expected: FAIL — `KeyError: 'pins'` on the snapshot test, `assert 'id="pin-character"' in body`
on the page test, and the two routing tests timing out in `_wait_for`.

- [ ] **Step 3: Implement the dashboard server changes**

In `brain/jev_vs/dashboard.py`, add two keys to the snapshot payload, after `"runs"`:

```python
                    "runs": server.run_history,
                    "pins": server.pins.pins,
                    "rosters": server.pins.rosters,
```

and route the inbound message, replacing the `if data.get("type") == "control":` block:

```python
                if data.get("type") == "control":
                    await server.send_control(bool(data.get("automation", True)))
                elif data.get("type") == "pin":
                    kind, pin = data.get("kind"), data.get("id")
                    # Same trust model as control: loopback, unauthenticated, and a pin is
                    # strictly less powerful than the pause button. Shape-check and drop.
                    if isinstance(kind, str) and (pin is None or isinstance(pin, str)):
                        server.set_pin(kind, pin)
```

- [ ] **Step 4: Implement the page changes**

In `brain/jev_vs/static/index.html`, add to the `<style>` block, after the `button.paused` rule:

```css
  .pin { display:inline-flex; align-items:center; gap:5px; color:var(--dim); font:400 11px/1 var(--pixel); }
  .pin select {
    padding:3px 5px; max-width:150px; border:0;
    font:12px/1.3 var(--data); color:var(--bone); background:var(--void);
    box-shadow:inset 0 0 0 1px var(--gold-dim);
  }
```

and extend the existing `button:focus-visible` rule to cover the selects:

```css
  button:focus-visible, canvas:focus-visible, select:focus-visible { outline:2px solid var(--xp); outline-offset:2px; }
```

In the HUD bar, between the `dot-jev` lamp and the PAUSE button:

```html
    <span class="lamp" id="dot-jev"><i></i>jev</span>
    <label class="pin">character<select id="pin-character"><option value="">JEV DECIDES</option></select></label>
    <label class="pin">stage<select id="pin-stage"><option value="">JEV DECIDES</option></select></label>
    <button id="pause">PAUSE</button>
```

In the `<script>`, after the `let automation = true;` line:

```js
  const pins = { character: null, stage: null };
  const rosters = { character: [], stage: [] };
```

Add this function next to `renderStats`:

```js
  function renderPins() {
    Object.keys(pins).forEach(kind => {
      const sel = $(`pin-${kind}`), chosen = pins[kind] || "", seen = rosters[kind] || [];
      const opts = [`<option value="">JEV DECIDES</option>`]
        .concat(seen.map(o => `<option value="${esc(o.id)}">${esc(o.name || o.id)}</option>`));
      // A pin set before this menu was ever seen still needs a row, or the select would
      // silently snap back to JEV DECIDES and lie about what the brain will do.
      if (chosen && !seen.some(o => o.id === chosen)) opts.push(`<option value="${esc(chosen)}">${esc(chosen)}</option>`);
      sel.innerHTML = opts.join("");
      sel.value = chosen;
    });
  }
```

In `connect()`'s `onmessage`, extend the snapshot branch and add two message types:

```js
      if (m.type === "snapshot") {
        renderStats(m.stats || {});
        $("log").replaceChildren();
        document.querySelector("#runs tbody").replaceChildren();
        Object.values(m.decisions || {}).forEach(renderDecision);
        (m.log || []).slice().reverse().forEach(addLog);
        (m.runs || []).forEach(addRun);
        Object.assign(pins, m.pins || {});
        Object.assign(rosters, m.rosters || {});
        renderPins();
        $("s-run").textContent = (m.run && m.run.character) || "—";
      } else if (m.type === "stats") renderStats(m);
      else if (m.type === "decision") renderDecision(m);
      else if (m.type === "event") addLog(m);
      else if (m.type === "roster") { rosters[m.kind] = m.options || []; renderPins(); }
      else if (m.type === "pin") { pins[m.kind] = m.id; renderPins(); }
```

And register the change handlers next to the `$("pause").onclick` handler, before `connect();`:

```js
  Object.keys(pins).forEach(kind => {
    $(`pin-${kind}`).onchange = (ev) => {
      const id = ev.target.value || null;
      pins[kind] = id;
      if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "pin", kind, id }));
    };
  });
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd brain && uv run pytest tests/test_dashboard.py -v`
Expected: PASS, 11 tests — the four new ones plus the seven that already existed, including
`test_index_serves_page`'s four-panel check.

Run: `cd brain && uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: the whole offline suite green and both lint commands clean.

- [ ] **Step 6: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add brain/jev_vs/dashboard.py brain/jev_vs/static/index.html brain/tests/test_dashboard.py
git commit -m "feat(brain): pin the character and stage from the dashboard

Two selects in the HUD bar, populated from the snapshot and kept current by
roster broadcasts. A pin travels on the socket the pause button already uses.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Task 6: end-to-end verification and documentation

Implements spec §3.6's "all offline" promise at the process level: the fake plugin walks the whole
protocol, so this exercises every brain path without Steam.

**Files:**
- Modify: `README.md` (Play section, Tuning section, Repository layout)
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Create (scratch, not committed):
  `/tmp/claude-1000/-home-oldmoldycake-Projects-jev-vampire-survivors/f0b55e44-fddb-405b-b871-9d6ec2787076/scratchpad/set_pin.py`

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Start a brain**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors/brain
uv run --env-file ../.env jev-vs
```

Run it in the background and keep its log. Expected: `brain ready: plugin port 48231, dashboard
http://127.0.0.1:48232/`. Never echo the key; `--env-file` is the only way it is handed over.

- [ ] **Step 2: Pin a character and a stage the way the dashboard does**

Write this to the scratchpad as `set_pin.py` — it speaks the same WebSocket the page does, so it
proves the dashboard route rather than reaching into the store:

```python
import asyncio
import json
import sys

import aiohttp


async def main() -> None:
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("http://127.0.0.1:48232/ws") as ws:
            snap = json.loads((await ws.receive()).data)
            print("snapshot pins:", snap.get("pins"), "rosters:", snap.get("rosters"))
            for kind, value in zip(sys.argv[1::2], sys.argv[2::2], strict=True):
                await ws.send_str(json.dumps({"type": "pin", "kind": kind, "id": None if value == "-" else value}))
            await asyncio.sleep(0.3)


asyncio.run(main())
```

Run: `uv run --project brain python <scratchpad>/set_pin.py character IMELDA stage LIBRARY`
Expected: prints the snapshot's `pins` and `rosters` (empty on a first run), and the brain's log
shows `character pinned to IMELDA` and `stage pinned to LIBRARY`.

- [ ] **Step 3: Drive the whole protocol with the fake plugin**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
uv run --project brain python scripts/fake_plugin.py --ticks 40 --hz 4
```

Expected, in the printed replies:
- the first `pick` reply is `"choice":"IMELDA"`, `"index":1`, `"source":"human"`;
- the second `pick` reply is `"choice":"LIBRARY"`, `"index":1`, `"source":"human"`;
- the `level_up` pick is still `"source":"jev"` — level-up picks stay Jev's (spec §5);
- 40 `move` replies, then `{"type":"noop"}` for game over.

Check the brain's log shows no `pinned ... not offered` warning, and that the pins survived:

```bash
cat brain/pins.json        # pins IMELDA/LIBRARY, rosters holding both menus' options
git status --short brain/  # pins.json must NOT appear: it is git-ignored
```

- [ ] **Step 4: Verify the not-offered path and the unpinned path**

Clear the stage pin, pin a stage the fake plugin does not offer, and run again:

```bash
uv run --project brain python <scratchpad>/set_pin.py character - stage MOONGOLOW
uv run --project brain python scripts/fake_plugin.py --ticks 8 --hz 4
```

Expected: the character pick is `"source":"jev"` again (pin cleared), the stage pick is
`"source":"jev"` (pin not offered), and the brain's log carries
`pinned MOONGOLOW not offered; asked Jev`. Then clear it: `... set_pin.py stage -`, and stop the
brain.

- [ ] **Step 5: Document the feature**

In `README.md`, add a bullet to the "A few things worth knowing while it's running" list in
**Play**, after the F9/Pause bullet:

```markdown
- **Pin a character or a stage** from the dashboard's CHARACTER and STAGE dropdowns and the brain
  applies your choice instead of asking Jev, from the next menu onward — the run in progress is
  not disturbed. Leave them on JEV DECIDES (the default) and nothing changes. A dropdown lists
  what the game last offered, so it fills in the first time a menu opens; a pin the game does not
  offer that run is kept, noted in the dashboard log, and that one pick goes back to Jev.
```

In **Tuning**, extend the `brain/config.toml` bullet:

```markdown
- **Brain ports, model, timeouts:** `brain/config.toml`. The tick rate is *not* set here — the
  plugin drives the cadence, so change `TickHz` in the plugin config below. `state_file` names
  where dashboard pins are remembered (`brain/pins.json` by default, git-ignored).
```

In **Repository layout**, add the module and the state file:

```
    decide.py            turns a Jev answer (or a failure) into an applied Decision
    pins.py              human-pinned character/stage and the rosters behind the dropdowns
    runlog.py            JSONL run logs
```

```
  runs/                  git-ignored run logs
  pins.json              git-ignored dashboard pins (created on first use)
  config.toml            ports, model, timeouts (tick rate lives in the plugin config)
```

In `CHANGELOG.md`, replace the `## [Unreleased]` body:

```markdown
## [Unreleased]

### Added

- **Pin a character or a stage from the dashboard.** Two dropdowns beside the Pause button
  override Jev's choice for the next run: the pinned pick is applied directly, costs no API
  call, and is marked `human` in the run log and on the decision card. Leaving both on
  "JEV DECIDES" is the default and keeps the previous behaviour exactly. Pins survive a brain
  restart in `brain/pins.json`, and a pin the game does not offer that run falls back to Jev
  with a note in the dashboard log rather than being silently dropped. No plugin change: the
  game never learns a human was involved.

### Fixed

- A human-pinned pick is no longer counted as a Jev fallback in the dashboard's run stats,
  which would have reported an API problem that never happened.
```

- [ ] **Step 6: Final verification**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors/brain
uv run pytest && uv run ruff check . && uv run ruff format --check .
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git status --short          # no pins.json, no runs/, no .env
git diff --stat main
```

Expected: the offline suite green, both ruff commands clean, and the diff touching only
`brain/jev_vs/{pins,config,decide,stats,server,dashboard,__main__}.py`,
`brain/jev_vs/static/index.html`, `brain/tests/*`, `brain/config.toml`, `.gitignore`,
`README.md`, `CHANGELOG.md` and this plan. **Zero files under `mod/`.**

- [ ] **Step 7: Commit**

```bash
cd /home/oldmoldycake/Projects/jev_vampire_survivors
git add README.md CHANGELOG.md
git commit -m "docs: document pinning a character or stage from the dashboard

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019VzgtSAh31zbf8s8GCuyaE"
```

---

## Spec coverage

| Spec §3 requirement | Task |
| --- | --- |
| No `mod/` changes, no `questions.py` changes (§3.1) | Global constraints; verified in Task 6 step 6 |
| `PinStore` with pins + roster cache, JSON-persisted, `state_file` config key, corrupt file degrades (§3.2) | Task 1 |
| Record options into the roster cache and broadcast `roster` (§3.3.1) | Task 4 |
| Pin set and offered → `pinned_index`; set and absent → warn and continue with the pin intact; unset → unchanged (§3.3.2) | Task 4 |
| `Decider.pick(pinned_index=...)` builds the `Ask`, skips `_ask`, returns `source="human"` (§3.3.3) | Task 2 |
| Downstream unchanged: run log, `current_run`, dashboard card, plugin reply (§3.3.4) | Task 4 (asserted in `test_pinned_character_is_applied_without_asking_jev`) |
| `stats.record()` third branch, `snapshot()` unchanged (§3.4) | Task 3 |
| Two selects with a "JEV DECIDES" first entry, populated from snapshot + `roster`, `pin` message routed like `control`, re-broadcast (§3.5) | Task 5 |
| Tests: pin honoured / not offered / roster cached / round-trip + corrupt file / stats untouched / `pin` over the WS (§3.6) | Tasks 1, 3, 4, 5 |

## Known deviations from the spec

1. **`calls` no longer equals `jev_calls + fallback_calls`** once a pin is used. That is the
   direct consequence of §3.4's "touches neither counter" plus "`snapshot()` is unchanged", so
   the plan implements it as written. A `human_calls` counter and a matching dashboard chip
   would close the gap, and would be a change to `snapshot()` — raise it before adding it.
2. **`.gitignore`, the `config.toml` comment, the README and the CHANGELOG** are not named in
   §3; they are the ordinary cost of adding a persisted file and a user-visible control.
