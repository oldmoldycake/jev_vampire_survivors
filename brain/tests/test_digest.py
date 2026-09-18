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


# ----------------------------------------------------------------- xp awareness

@pytest.mark.parametrize("xp,xp_to_next,expected", [
    (0, 0, "just levelled"),
    (5, 0, "just levelled"),           # guard: xp_to_next <= 0
    (0, 50, "just levelled"),
    (12, 50, "just levelled"),         # 0.24 < xp_partway(0.25)
    (12.5, 50, "partway to the next level"),  # 0.25 boundary
    (29, 50, "partway to the next level"),    # 0.58 < xp_close(0.6)
    (30, 50, "close to the next level"),      # 0.6 boundary
    (44, 50, "close to the next level"),      # 0.88 < xp_imminent(0.9)
    (45, 50, "a level up is imminent"),       # 0.9 boundary
    (50, 50, "a level up is imminent"),
])
def test_xp_bucket_boundaries(xp, xp_to_next, expected):
    assert digest.xp_bucket(xp, xp_to_next, TH) == expected


def test_player_summary_carries_xp_bucket():
    st = make_state()
    st["player"]["xp"] = 45
    st["player"]["xp_to_next"] = 50
    d = digest.digest_state(st, TH)
    assert d.player.xp_bucket == "a level up is imminent"


# ----------------------------------------------------------------- objective awareness

def test_sector_with_two_pickups_lists_both_categories_sorted_and_deduped():
    st = make_state(pickups=[
        {"x": 2, "y": 2, "kind": "TREASURE"},
        {"x": 2.1, "y": 2.1, "kind": "COIN"},
        {"x": 2.2, "y": 2.2, "kind": "COINBAG1"},
    ])
    d = digest.digest_state(st, TH)
    ne = d.sectors["north_east"]
    assert ne.objects == ["chest", "coins"]
    assert ne.chest is True


def test_unknown_pickup_kind_is_item_category():
    st = make_state(pickups=[{"x": 2, "y": 2, "kind": "MYSTERY_THING"}])
    d = digest.digest_state(st, TH)
    assert d.sectors["north_east"].objects == ["item"]


# ----------------------------------------------------------------- obstacle awareness

def test_blocked_when_applied_direction_matches_and_barely_moved():
    st = make_state()
    st["player"]["applied_direction"] = "north"
    st["player"]["moved"] = 0.01
    d = digest.digest_state(st, TH)
    assert d.sectors["north"].blocked is True
    assert d.sectors["south"].blocked is False


def test_not_blocked_when_moved_past_threshold():
    st = make_state()
    st["player"]["applied_direction"] = "north"
    st["player"]["moved"] = 1.0
    d = digest.digest_state(st, TH)
    assert d.sectors["north"].blocked is False


def test_not_blocked_when_applied_direction_is_stay():
    st = make_state()
    st["player"]["applied_direction"] = "stay"
    st["player"]["moved"] = 0.0
    d = digest.digest_state(st, TH)
    assert all(not s.blocked for s in d.sectors.values())


def test_not_blocked_when_applied_direction_missing():
    st = make_state()
    st["player"]["moved"] = 0.0
    d = digest.digest_state(st, TH)
    assert all(not s.blocked for s in d.sectors.values())


def test_not_blocked_when_moved_is_absent():
    st = make_state()
    st["player"]["applied_direction"] = "north"   # valid compass direction, but no "moved" field at all
    d = digest.digest_state(st, TH)
    assert all(not s.blocked for s in d.sectors.values())


# ----------------------------------------------------------------- block memory

def test_block_memory_reports_blocked_before_expiry_and_not_after():
    mem = digest.BlockMemory(TH)
    mem.record("north", 10.0)
    assert "north" in mem.blocked(10.0 + TH.block_memory_s - 0.1)
    assert "north" not in mem.blocked(10.0 + TH.block_memory_s + 0.1)


def test_block_memory_repeat_refreshes_the_timer():
    mem = digest.BlockMemory(TH)
    mem.record("north", 10.0)
    mem.record("north", 10.0 + TH.block_memory_s - 0.1)   # refresh just before it would have expired
    # more than block_memory_s after the *first* record, but well within it of the refresh
    assert "north" in mem.blocked(10.0 + TH.block_memory_s + 0.5)


def test_block_memory_clear_empties_it():
    mem = digest.BlockMemory(TH)
    mem.record("north", 10.0)
    mem.note_position(10.0, 0.0, 0.0, "north")
    mem.clear()
    assert mem.blocked(10.0) == set()
    assert mem.is_stuck(4.0, TH) is False


def test_digest_state_with_memory_marks_remembered_direction_blocked_on_a_later_tick():
    mem = digest.BlockMemory(TH)
    st1 = make_state()
    st1["player"]["applied_direction"] = "north"
    st1["player"]["moved"] = 0.0
    st1["player"]["seconds"] = 10.0
    digest.digest_state(st1, TH, memory=mem)

    st2 = make_state()
    st2["player"]["applied_direction"] = "east"   # a different direction is applied this tick
    st2["player"]["moved"] = 1.0                  # east itself moved fine, not newly blocked
    st2["player"]["seconds"] = 11.0                # still within block_memory_s of the first block
    d2 = digest.digest_state(st2, TH, memory=mem)
    assert d2.sectors["north"].blocked is True     # remembered from the earlier tick
    assert d2.sectors["east"].blocked is False


def test_digest_state_without_memory_behaves_exactly_as_before():
    st = make_state()
    st["player"]["applied_direction"] = "north"
    st["player"]["moved"] = 0.01
    d = digest.digest_state(st, TH)   # no memory passed at all
    assert d.sectors["north"].blocked is True
    assert d.player.stuck is False


def test_digest_state_sets_player_stuck_from_memory():
    mem = digest.BlockMemory(TH)
    d = None
    for i in range(3):
        st = make_state()
        st["player"]["seconds"] = float(i) * (TH.stuck_window_s / 2)
        st["player"]["x"] = 0.001 * i
        st["player"]["y"] = 0.0
        st["player"]["applied_direction"] = "north"
        st["player"]["moved"] = 1.0
        d = digest.digest_state(st, TH, memory=mem)
    assert d.player.stuck is True


# ----------------------------------------------------------------- stuck detection

def test_is_stuck_true_for_barely_moving_trail_with_a_real_direction_applied():
    mem = digest.BlockMemory(TH)
    mem.note_position(0.0, 0.0, 0.0, "north")
    mem.note_position(1.0, 0.01, 0.0, "north")
    mem.note_position(TH.stuck_window_s, 0.02, 0.0, "north")
    assert mem.is_stuck(4.0, TH) is True


def test_is_stuck_false_when_every_sample_applied_stay():
    mem = digest.BlockMemory(TH)
    mem.note_position(0.0, 0.0, 0.0, "stay")
    mem.note_position(1.0, 0.0, 0.0, "stay")
    mem.note_position(TH.stuck_window_s, 0.0, 0.0, "stay")
    assert mem.is_stuck(4.0, TH) is False


def test_is_stuck_false_when_survivor_actually_moved():
    mem = digest.BlockMemory(TH)
    mem.note_position(0.0, 0.0, 0.0, "north")
    mem.note_position(1.0, 1.0, 0.0, "north")
    mem.note_position(TH.stuck_window_s, 2.0, 0.0, "north")   # well past stuck_move_frac * half_h
    assert mem.is_stuck(4.0, TH) is False


def test_is_stuck_false_when_trail_is_shorter_than_the_window():
    mem = digest.BlockMemory(TH)
    mem.note_position(0.0, 0.0, 0.0, "north")
    mem.note_position(TH.stuck_window_s - 0.5, 0.0, 0.0, "north")
    assert mem.is_stuck(4.0, TH) is False


def test_is_stuck_true_for_a_realistic_jittered_trail():
    # Real ticks land roughly every 0.25s with frame jitter, and the run clock is rounded to two
    # decimals -- so the oldest sample within exactly stuck_window_s is often a hair short of it.
    # This is the exact shape that broke the original oldest-sample-in-trail implementation
    # (see fix(brain): make the stuck check reachable with real tick timing).
    mem = digest.BlockMemory(TH)
    seconds = [0.0, 0.26, 0.49, 0.77, 1.01, 1.24, 1.53, 1.76, 2.02, 2.24, 2.51, 2.78, 3.0]
    for i, t in enumerate(seconds):
        mem.note_position(t, 0.001 * i, 0.0, "north")   # barely moving, a real direction applied throughout
    assert mem.is_stuck(4.0, TH) is True
