import pytest


def make_state(enemies=(), gems=(), pickups=(), hp=80, max_hp=100, level=5, minute=3):
    return {
        "player": {
            "x": 0.0,
            "y": 0.0,
            "hp": hp,
            "max_hp": max_hp,
            "level": level,
            "xp": 10,
            "xp_to_next": 50,
            "minute": minute,
            "seconds": minute * 60,
            "character": "ANTONIO",
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
