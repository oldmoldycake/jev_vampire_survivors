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
