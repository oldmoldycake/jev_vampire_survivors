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
