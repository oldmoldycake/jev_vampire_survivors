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
