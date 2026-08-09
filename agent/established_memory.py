"""Small run-independent memory containing only established global mechanics."""

from __future__ import annotations


GLOBAL_EXPERIENCES = (
    {
        "id": "feet_are_live_anchor",
        "form": "atomic",
        "fact": "Live x/y coordinates identify the actor's feet tile; head or sprite overlap is not collision depth.",
        "authority": "curated and repeatedly WRAM-verified",
    },
    {
        "id": "blocked_is_state_local",
        "form": "binary",
        "when": "movement produces no coordinate delta and blocked_now",
        "then": "that directed edge is impassable in the current state; it is not automatically a permanent wall",
        "authority": "curated and repeatedly WRAM-verified",
    },
    {
        "id": "push_requires_world_change",
        "form": "binary",
        "when": "interact(direction) is used against a movable object",
        "then": "a real push/correction requires actor displacement plus object/map-state displacement; walking in place is not a correction",
        "authority": "curated controller and WRAM evidence",
    },
    {
        "id": "reset_is_new_unsolved_episode",
        "form": "binary",
        "when": "reset_room completes",
        "then": "the room puzzle is unsolved and all pre-reset perception, object hypotheses and intentions are invalid",
        "authority": "game mechanic confirmed by user and emulator",
    },
    {
        "id": "threshold_is_not_room_entry",
        "form": "binary",
        "when": "a door opens or the actor reaches its threshold",
        "then": "room entry is unconfirmed until the actor reaches the first stable live feet tile beyond the threshold",
        "authority": "curated transition semantics and live verification",
    },
)


def global_memory_context(
    mode: str,
    *,
    blocked: bool = False,
    movable_object: bool = False,
    after_reset: bool = False,
    at_threshold: bool = False,
) -> list[dict]:
    """Retrieve only mechanics triggered by the current live decision state."""
    if mode != "exploration":
        return []
    selected = {"feet_are_live_anchor"}
    if blocked:
        selected.add("blocked_is_state_local")
    if movable_object:
        selected.add("push_requires_world_change")
    if after_reset:
        selected.add("reset_is_new_unsolved_episode")
    if at_threshold:
        selected.add("threshold_is_not_room_entry")
    return [dict(item) for item in GLOBAL_EXPERIENCES if item["id"] in selected]
