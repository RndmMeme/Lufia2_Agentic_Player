"""Schema and safety gate for model-proposed emulator actions."""

from __future__ import annotations

from dataclasses import dataclass


ALLOWED_KINDS = {
    "move", "face", "interact", "sword", "select_tool", "use_tool",
    "look", "look_map", "reset_room", "battle_attack", "battle_flee", "wait", "retrieve"
}
MOVE_DIRECTIONS = {"north", "south", "east", "west"}
TOOLS = {"hook", "bomb", "arrow", "fire_arrow", "hammer"}


@dataclass(frozen=True)
class Intent:
    kind: str
    direction: str | None = None
    count: int = 1
    question: str | None = None
    query: str | None = None
    tool: str | None = None
    rationale: str = ""

    @classmethod
    def from_dict(cls, value: dict, max_move_batch: int = 4) -> "Intent":
        if not isinstance(value, dict):
            raise ValueError("Intent must be a JSON object")
        kind = str(value.get("kind", "")).strip().casefold()
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"Unsupported intent kind: {kind!r}")
        direction = value.get("direction")
        if direction is not None:
            direction = str(direction).casefold()
        count = int(value.get("count", 1))
        if kind in {"move", "face"}:
            if direction not in MOVE_DIRECTIONS:
                raise ValueError(f"{kind} intent requires north/south/east/west")
        if kind == "move":
            if not 1 <= count <= max_move_batch:
                raise ValueError(f"Move count must be 1..{max_move_batch}")
        else:
            count = 1
        raw_question = value.get("question")
        raw_query = value.get("query")
        raw_tool = value.get("tool")
        question = None if raw_question is None else str(raw_question).strip()[:500] or None
        query = None if raw_query is None else str(raw_query).strip()[:300] or None
        tool = (
            None
            if raw_tool is None
            else str(raw_tool).strip().casefold().replace(" ", "_") or None
        )
        if kind == "select_tool" and tool not in TOOLS:
            raise ValueError(f"select_tool requires one of {sorted(TOOLS)}")
        rationale = str(value.get("rationale", "")).strip()[:500]
        return cls(kind, direction, count, question, query, tool, rationale)


def gate_intent(intent: Intent, mode: str) -> None:
    allowed = {
        "battle": {"battle_attack", "battle_flee", "look", "wait", "retrieve"},
        "dialog": {"interact", "look", "wait", "retrieve"},
        "exploration": {
            "move", "face", "interact", "sword", "select_tool", "use_tool",
            "look", "look_map", "reset_room", "wait", "retrieve"
        },
        "other": {"interact", "look", "look_map", "wait", "retrieve"},
    }[mode]
    if intent.kind not in allowed:
        raise ValueError(f"Intent {intent.kind!r} is not allowed in mode {mode!r}")
