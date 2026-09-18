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
        "id": id,
        "type": "move",
        "dx": dx,
        "dy": dy,
        "choice": choice,
        "probabilities": probabilities,
        "confidence": confidence,
        "source": source,
    }


def pick_reply(
    id: int, index: int, choice: str, probabilities: dict[str, float], confidence: float, source: str
) -> dict:
    return {
        "id": id,
        "type": "pick",
        "index": index,
        "choice": choice,
        "probabilities": probabilities,
        "confidence": confidence,
        "source": source,
    }


def noop_reply(id: int) -> dict:
    return {"id": id, "type": "noop"}


def control(automation: bool) -> dict:
    return {"type": "control", "automation": automation}
