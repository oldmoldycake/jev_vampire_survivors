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
