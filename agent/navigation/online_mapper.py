"""WRAM-observed navigation graph for deterministic online exploration."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path


DIRECTIONS = {
    "north": (0, -1),
    "east": (1, 0),
    "west": (-1, 0),
    "south": (0, 1),
}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
BLOCKED_CODES = {0x00: "north", 0x01: "south", 0x02: "west", 0x03: "east"}
FACING_CODES = {0x00: "south", 0x02: "west", 0x04: "north", 0x06: "east"}


@dataclass(frozen=True)
class LiveNavigationObservation:
    map_id: int
    previous_map_id: int
    x: int
    y: int
    sprite_id: int
    movement_state: int
    direction: int
    blocked_attempt: int
    map_context: int
    exploration_mode: int
    battle_mode: int
    global_x: int
    global_y: int
    transport_flag: int = 0
    overworld_x: int = 0
    overworld_y: int = 0

    @property
    def position(self) -> tuple[int, int]:
        return self.x, self.y

    @property
    def moving(self) -> bool:
        return bool(self.movement_state & 0x01)

    @property
    def in_battle(self) -> bool:
        return self.battle_mode == 0x01

    @classmethod
    def from_wram(cls, data: bytes, actor_slot: int = 0) -> "LiveNavigationObservation":
        if len(data) < 0x1273:
            raise ValueError("A full or sufficiently large SNES WRAM snapshot is required.")
        if not 0 <= actor_slot < 0x28:
            raise ValueError("actor_slot must be between 0 and 39")
        transport_flag = data[0x09E1]
        walk_x = data[0x146B] | (data[0x146C] << 8)
        walk_y = data[0x146E] | (data[0x146F] << 8)
        ship_x = data[0x1488] | (data[0x1489] << 8)
        ship_y = data[0x148B] | (data[0x148C] << 8)
        return cls(
            map_id=data[0x05AC],
            previous_map_id=data[0x05AE],
            x=data[0x06BA + actor_slot],
            y=data[0x06E2 + actor_slot],
            sprite_id=data[0x05D2 + actor_slot],
            movement_state=data[0x066A + actor_slot],
            direction=data[0x0692 + actor_slot],
            blocked_attempt=data[0x1272],
            map_context=data[0x09A7],
            exploration_mode=data[0x09A9],
            battle_mode=data[0x09AA],
            global_x=data[0x121E],
            global_y=data[0x1226],
            transport_flag=transport_flag,
            overworld_x=ship_x if transport_flag == 0xFF else walk_x,
            overworld_y=ship_y if transport_flag == 0xFF else walk_y,
        )


class OnlineNavigationMapper:
    SCHEMA = "lufia2-online-navigation-graph-v2"
    LEGACY_SCHEMA = "lufia2-online-navigation-graph-v1"

    def __init__(self, objective: dict | None = None, state: dict | None = None):
        self.objective = objective or {}
        self.state = state or {
            "schema": self.SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "objective": self.objective,
            "nodes": {},
            "edges": {},
            "events": [],
            "visited_rooms": [],
            "current_room": None,
            "room_history": [],
            "left_start_room": False,
            "current_node": None,
            "action_count": 0,
            "completed_landmarks": {},
        }
        if self.state.get("schema") == self.LEGACY_SCHEMA:
            self._migrate_v1_state()
        if self.state.get("schema") != self.SCHEMA:
            raise ValueError("Unsupported online navigation graph schema")
        self.state.setdefault("objective", self.objective)
        self.objective = self.state.get("objective") or self.objective
        self.state.setdefault("current_room", None)
        self.state.setdefault("room_history", [])
        self.state.setdefault("left_start_room", False)
        self.state.setdefault("completed_landmarks", {})
        # A failed movement proves only a directed, momentary collision. It does
        # not prove a wall: doors, actors, movable blocks and puzzle state can
        # all produce the same WRAM evidence. Migrate early probe graphs that
        # used the overly strong name "blocked".
        for edges in self.state.get("edges", {}).values():
            for edge in edges.values():
                if edge.get("outcome") == "blocked":
                    edge["outcome"] = "blocked_now"
                    edge.setdefault("traversability", "impassable_now")
                    edge.setdefault("structural_type", "unknown")
        for event in self.state.get("events", []):
            if event.get("outcome") == "blocked":
                event["outcome"] = "blocked_now"

    def _migrate_v1_state(self) -> None:
        """Re-key legacy nodes so overlapping subrooms cannot alias each other."""
        old_nodes = dict(self.state.get("nodes", {}))
        key_map = {}
        new_nodes = {}
        for old_key, node in old_nodes.items():
            room = node.get("room")
            new_key = self.node_key(node["map_id"], node["x"], node["y"], room)
            key_map[old_key] = new_key
            new_nodes[new_key] = node
        new_edges = {}
        for old_source, directions in self.state.get("edges", {}).items():
            source = key_map.get(old_source, old_source)
            new_edges[source] = {}
            for direction, edge in directions.items():
                migrated = dict(edge)
                migrated["from"] = source
                if migrated.get("to"):
                    migrated["to"] = key_map.get(migrated["to"], migrated["to"])
                new_edges[source][direction] = migrated
        for event in self.state.get("events", []):
            for field in ("source", "target", "node"):
                if event.get(field):
                    event[field] = key_map.get(event[field], event[field])
            if event.get("traversed_nodes"):
                event["traversed_nodes"] = [
                    key_map.get(key, key) for key in event["traversed_nodes"]
                ]
        self.state["nodes"] = new_nodes
        self.state["edges"] = new_edges
        if self.state.get("current_node"):
            self.state["current_node"] = key_map.get(
                self.state["current_node"], self.state["current_node"]
            )
        self.state["current_room"] = (
            new_nodes.get(self.state.get("current_node"), {}).get("room")
        )
        self.state["schema"] = self.SCHEMA

    @staticmethod
    def node_key(map_id: int, x: int, y: int, room: str | None = None) -> str:
        namespace = room or "unknown_room"
        return f"{int(map_id):02X}:{namespace}:{int(x)},{int(y)}"

    @staticmethod
    def parse_node_key(key: str) -> tuple[int, int, int]:
        parts = key.split(":")
        if len(parts) == 2:  # v1 compatibility for imported references
            map_text, point = parts
        elif len(parts) == 3:
            map_text, _, point = parts
        else:
            raise ValueError(f"Invalid navigation node key: {key!r}")
        x_text, y_text = point.split(",", 1)
        return int(map_text, 16), int(x_text), int(y_text)

    def room_candidates(self, observation: LiveNavigationObservation) -> list[str]:
        candidates = []
        for room in self.objective.get("rooms", []):
            if int(room.get("map_id", self.objective.get("map_id", -1))) != observation.map_id:
                continue
            bounds = room["bounds"]
            if (
                int(bounds["min_x"]) <= observation.x <= int(bounds["max_x"])
                and int(bounds["min_y"]) <= observation.y <= int(bounds["max_y"])
            ):
                candidates.append(str(room["id"]))
        return candidates

    def _room_record(self, room_id: str | None) -> dict | None:
        return next(
            (room for room in self.objective.get("rooms", []) if str(room["id"]) == room_id),
            None,
        )

    def room_for(
        self,
        observation: LiveNavigationObservation,
        previous_room: str | None = None,
    ) -> str | None:
        """Resolve overlapping WRAM room bounds without inventing a global image projection."""
        candidates = self.room_candidates(observation)
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            return None
        prior = previous_room if previous_room is not None else self.state.get("current_room")
        # Remaining inside the same candidate is stronger evidence than a
        # graph edge; this prevents repeated observations from oscillating.
        if prior in candidates:
            return prior
        prior_record = self._room_record(prior)
        successors = set(prior_record.get("successors", [])) if prior_record else set()
        reachable = [candidate for candidate in candidates if candidate in successors]
        return reachable[0] if len(reachable) == 1 else None

    def observe(self, observation: LiveNavigationObservation) -> tuple[str, bool]:
        previous_room = self.state.get("current_room")
        room = self.room_for(observation, previous_room=previous_room)
        key = self.node_key(observation.map_id, observation.x, observation.y, room)
        node = self.state["nodes"].setdefault(
            key,
            {
                "map_id": observation.map_id,
                "x": observation.x,
                "y": observation.y,
                "visits": 0,
                "room": room,
                "first_observation": asdict(observation),
            },
        )
        node["visits"] += 1
        node["last_observation"] = asdict(observation)
        if room and not node.get("room"):
            node["room"] = room
        new_room = False
        if room and room not in self.state["visited_rooms"]:
            self.state["visited_rooms"].append(room)
            new_room = True
        if room != previous_room:
            self.state["room_history"].append(
                {
                    "from": previous_room,
                    "to": room,
                    "map_id": observation.map_id,
                    "position": [observation.x, observation.y],
                }
            )
            start_room = self.objective.get("start", {}).get("room_id")
            if previous_room == start_room and room not in {None, start_room}:
                self.state["left_start_room"] = True
        self.state["current_room"] = room
        self.state["current_node"] = key
        return key, new_room

    def record_move(
        self,
        before: LiveNavigationObservation,
        direction: str,
        after: LiveNavigationObservation,
    ) -> dict:
        if direction not in DIRECTIONS:
            raise ValueError(f"Unknown direction: {direction}")
        source, _ = self.observe(before)
        target, new_room = self.observe(after)
        moved = before.map_id != after.map_id or before.position != after.position
        delta = (after.x - before.x, after.y - before.y)
        expected_delta = DIRECTIONS[direction]
        directional_move = (
            (expected_delta[0] == 0 and delta[0] == 0 and delta[1] * expected_delta[1] > 0)
            or (expected_delta[1] == 0 and delta[1] == 0 and delta[0] * expected_delta[0] > 0)
        )
        transition = moved and (before.map_id != after.map_id or not directional_move)
        blocked_direction = BLOCKED_CODES.get(after.blocked_attempt)
        if after.in_battle and not moved:
            outcome = "encounter"
        elif moved:
            outcome = "transition" if transition else "open"
        else:
            outcome = "blocked_now"
        edge = {
            "from": source,
            "direction": direction,
            "to": target if moved else None,
            "outcome": outcome,
            "blocked_byte": after.blocked_attempt,
            "blocked_byte_direction": blocked_direction,
            "blocked_byte_matches_attempt": blocked_direction == direction,
            "traversability": "impassable_now" if outcome == "blocked_now" else "passable",
            "structural_type": "unknown",
            "directional": True,
            "delta": {"x": delta[0], "y": delta[1]},
            "observations": 1,
        }
        if outcome != "encounter" and not (moved and not transition):
            previous = self.state["edges"].setdefault(source, {}).get(direction)
            if previous and previous.get("outcome") == outcome and previous.get("to") == edge.get("to"):
                edge["observations"] = int(previous.get("observations", 1)) + 1
            self.state["edges"].setdefault(source, {})[direction] = edge

        traversed_nodes = [source]
        if moved and not transition:
            # A human-sized held direction can cross multiple WRAM coordinates.
            # Preserve every proven coordinate instead of storing one long edge
            # which the pathfinder would later treat like a teleport.
            step_x, step_y = expected_delta
            step_count = abs(delta[0]) + abs(delta[1])
            previous_node = source
            for index in range(1, step_count + 1):
                point_x = before.x + step_x * index
                point_y = before.y + step_y * index
                if index == step_count:
                    next_node = target
                else:
                    intermediate = replace(after, x=point_x, y=point_y)
                    next_node, intermediate_new_room = self.observe(intermediate)
                    new_room = new_room or intermediate_new_room
                traversed_nodes.append(next_node)

                segment = {
                    "from": previous_node,
                    "direction": direction,
                    "to": next_node,
                    "outcome": "open",
                    "blocked_byte": after.blocked_attempt,
                    "blocked_byte_direction": blocked_direction,
                    "blocked_byte_matches_attempt": blocked_direction == direction,
                    "traversability": "passable",
                    "structural_type": "unknown",
                    "directional": True,
                    "delta": {"x": step_x, "y": step_y},
                    "observations": 1,
                }
                previous_segment = self.state["edges"].setdefault(previous_node, {}).get(direction)
                if previous_segment and previous_segment.get("outcome") == "open" and previous_segment.get("to") == next_node:
                    segment["observations"] = int(previous_segment.get("observations", 1)) + 1
                self.state["edges"].setdefault(previous_node, {})[direction] = segment

                reverse = {
                    "from": next_node,
                    "direction": OPPOSITE[direction],
                    "to": previous_node,
                    "outcome": "open",
                    "inferred_reverse": True,
                    "observations": 0,
                }
                self.state["edges"].setdefault(next_node, {}).setdefault(OPPOSITE[direction], reverse)
                previous_node = next_node

            # observe(intermediate) changes current_node; the live endpoint wins.
            self.state["current_node"] = target

        event = {
            "index": len(self.state["events"]) + 1,
            "type": "move",
            "direction": direction,
            "source": source,
            "target": target,
            "traversed_nodes": traversed_nodes,
            "outcome": outcome,
            "new_room": new_room,
            "before": asdict(before),
            "after": asdict(after),
        }
        self.state["events"].append(event)
        self.state["action_count"] = int(self.state.get("action_count", 0)) + 1
        return event

    def unknown_directions(self, node: str) -> list[str]:
        known = self.state["edges"].get(node, {})
        return [direction for direction in DIRECTIONS if direction not in known]

    def _missing_room_bounds(self, map_id: int) -> list[dict]:
        visited = set(self.state.get("visited_rooms", []))
        return [
            room["bounds"]
            for room in self.objective.get("rooms", [])
            if str(room["id"]) not in visited
            and int(room.get("map_id", self.objective.get("map_id", -1))) == map_id
        ]

    @staticmethod
    def _distance_to_bounds(x: int, y: int, bounds: dict) -> int:
        dx = max(int(bounds["min_x"]) - x, 0, x - int(bounds["max_x"]))
        dy = max(int(bounds["min_y"]) - y, 0, y - int(bounds["max_y"]))
        return dx + dy

    def _frontier_score(self, node: str, direction: str, path_length: int = 0) -> float:
        map_id, x, y = self.parse_node_key(node)
        dx, dy = DIRECTIONS[direction]
        target_x, target_y = x + dx, y + dy
        targets = self._missing_room_bounds(map_id)
        if not targets:
            return float(path_length)
        distance = min(self._distance_to_bounds(target_x, target_y, bounds) for bounds in targets)
        return distance + path_length * 0.5

    def _path_to_frontier(self, start: str) -> list[str] | None:
        queue = deque([(start, [])])
        visited = {start}
        candidates: list[tuple[float, list[str]]] = []
        while queue:
            node, path = queue.popleft()
            unknown = self.unknown_directions(node)
            for direction in unknown:
                candidates.append((self._frontier_score(node, direction, len(path)), path + [direction]))
            for direction, edge in self.state["edges"].get(node, {}).items():
                target = edge.get("to")
                if edge.get("outcome") not in {"open", "transition"} or not target or target in visited:
                    continue
                visited.add(target)
                queue.append((target, path + [direction]))
        if not candidates:
            return None
        return min(candidates, key=lambda candidate: (candidate[0], len(candidate[1])))[1]

    def next_move(
        self,
        direction_priors: dict[str, str] | None = None,
        exploration_distance: int = 2,
    ) -> tuple[str, int, str] | None:
        current = self.state.get("current_node")
        if not current:
            return None
        unknown = self.unknown_directions(current)
        if unknown:
            priors = direction_priors or {}
            prior_cost = {
                "confirmed_walkable": -4,
                "partially_known": -1,
                "unknown": 0,
                "conditional": 4,
                "blocked": 20,
            }
            direction = min(
                unknown,
                key=lambda direction: (
                    prior_cost.get(priors.get(direction, "unknown"), 0),
                    self._frontier_score(current, direction),
                ),
            )
            return direction, max(1, int(exploration_distance)), "frontier_probe"
        path = self._path_to_frontier(current)
        return (path[0], 1, "known_route_to_frontier") if path else None

    def next_direction(self, direction_priors: dict[str, str] | None = None) -> str | None:
        move = self.next_move(direction_priors)
        return move[0] if move else None

    def progress(self) -> dict:
        expected = [str(room["id"]) for room in self.objective.get("rooms", [])]
        visited = list(self.state.get("visited_rooms", []))
        missing = [room for room in expected if room not in visited]
        completion_mode = self.objective.get("completion", "visit_all_room_bounds")
        all_visited = bool(expected) and not missing
        start = self.objective.get("start", {})
        start_room = start.get("room_id")
        current_room = self.state.get("current_room")
        at_start_position = True
        start_position = start.get("position")
        if start_position and self.state.get("current_node"):
            _, current_x, current_y = self.parse_node_key(self.state["current_node"])
            radius = max(0, int(start.get("radius", 0)))
            at_start_position = (
                abs(current_x - int(start_position[0]))
                + abs(current_y - int(start_position[1]))
                <= radius
            )
        returned_to_start = (
            bool(self.state.get("left_start_room"))
            and current_room == start_room
            and at_start_position
        )
        if completion_mode == "visit_all_rooms_and_return_to_start":
            complete = all_visited and returned_to_start
        else:
            complete = all_visited
        return {
            "objective": self.objective.get("name", "open exploration"),
            "rooms_expected": len(expected),
            "rooms_visited": len([room for room in visited if room in expected]),
            "visited_rooms": visited,
            "missing_rooms": missing,
            "current_room": current_room,
            "room_history": self.state.get("room_history", [])[-12:],
            "all_rooms_visited": all_visited,
            "returned_to_start": returned_to_start,
            "at_start_position": at_start_position,
            "complete": complete,
            "nodes": len(self.state["nodes"]),
            "directed_edges": sum(len(edges) for edges in self.state["edges"].values()),
            "actions": int(self.state.get("action_count", 0)),
        }

    def context_for_llm(self) -> dict:
        current = self.state.get("current_node")
        observed_edges = {}
        if current:
            for direction, edge in self.state.get("edges", {}).get(current, {}).items():
                observed_edges[direction] = {
                    "outcome": edge.get("outcome"),
                    "to": edge.get("to"),
                    "blocked_byte_matches_attempt": edge.get("blocked_byte_matches_attempt"),
                }
        return {
            "current_node": current,
            "current_room": self.current_room_context(),
            "room_candidates": (
                [self.state.get("current_room")] if self.state.get("current_room") else []
            ),
            "unknown_directions": self.unknown_directions(current) if current else [],
            "observed_edges": observed_edges,
            "progress": self.progress(),
            "map_scoped_rules": self.objective.get("cave_visual_rules", []),
            "semantics_sources": {
                "global": self.objective.get("global_semantics_source"),
                "map": self.objective.get("map_semantics_source"),
            },
            "policy": (
                "This is memory, not a route recommendation. The LLM alone chooses directions. "
                "A failed WRAM movement is only impassable_now in that direction; "
                "never infer a wall or a blocked reverse edge without semantic evidence."
            ),
        }

    def current_room_context(self) -> dict:
        room_id = self.state.get("current_room")
        room = self._room_record(room_id)
        if room is None:
            return {
                "resolved": False,
                "policy": "Room is ambiguous; use live vision or a transition before applying a room lesson.",
            }
        current = self.state.get("current_node")
        _, x, y = self.parse_node_key(current) if current else (0, 0, 0)
        current_node = self.state.get("nodes", {}).get(current, {}) if current else {}
        facing = FACING_CODES.get(
            int(current_node.get("last_observation", {}).get("direction", -1))
        )
        landmarks = []
        for landmark in room.get("reference_landmarks", []):
            live = landmark.get("live")
            if not live:
                continue
            item = dict(landmark)
            dx, dy = int(live[0]) - x, int(live[1]) - y
            item["relative"] = [dx, dy]
            steps = []
            if dx:
                steps.append({"direction": "east" if dx > 0 else "west", "tiles": abs(dx)})
            if dy:
                steps.append({"direction": "south" if dy > 0 else "north", "tiles": abs(dy)})
            at_landmark = dx == 0 and dy == 0
            required_facing = landmark.get("facing")
            completion_key = f"{room_id}:{landmark.get('id')}"
            completion = self.state.get("completed_landmarks", {}).get(completion_key)
            item["completed"] = bool(completion)
            if completion:
                item["completion_evidence"] = completion
            item["derived_relation"] = {
                "at_landmark": at_landmark,
                "manhattan_tiles": abs(dx) + abs(dy),
                "steps_to_reach": steps,
                "coordinate_rule": "x increases east; y increases south",
            }
            if landmark.get("action"):
                item["action_readiness"] = {
                    "completed": bool(completion),
                    "position_ready": at_landmark,
                    "facing_now": facing,
                    "required_facing": required_facing,
                    "facing_ready": not required_facing or facing == required_facing,
                    "next_precondition": (
                        None
                        if completion or (at_landmark and (not required_facing or facing == required_facing))
                        else (
                            f"face {required_facing}"
                            if at_landmark and required_facing
                            else "reach the landmark first"
                        )
                    ),
                }
            landmarks.append(item)
        landmarks.sort(key=lambda item: abs(item["relative"][0]) + abs(item["relative"][1]))
        return {
            "resolved": True,
            "id": room_id,
            "live_position": [x, y],
            "facing": facing,
            "objective": room.get("objective"),
            "success_evidence": room.get("success_evidence"),
            "predecessors": room.get("predecessors", []),
            "successors": room.get("successors", []),
            "elevation_rules": room.get("elevation_rules", []),
            "nearby_live_landmarks": landmarks[:8],
            "coordinate_policy": (
                "Landmark live coordinates use WRAM feet positions. Curated chess coordinates, when present, "
                "name the visual annotation only and are not a global transform."
            ),
        }

    def record_action_landmark_effect(
        self,
        action: str,
        observation: LiveNavigationObservation,
        tile_diff: dict,
    ) -> dict | None:
        """Complete an action landmark only from a semantic map-buffer change.

        Visual motion and generic WRAM churn are deliberately insufficient. The
        actor must be on the curated feet coordinate, face the required direction,
        execute the matching action, and change at least one semantic map tile.
        """
        if int(tile_diff.get("semantic_count", 0)) <= 0:
            return None
        room_id = self.room_for(observation, previous_room=self.state.get("current_room"))
        room = self._room_record(room_id)
        if room is None:
            return None
        facing = FACING_CODES.get(int(observation.direction))
        for landmark in room.get("reference_landmarks", []):
            if landmark.get("action") != action:
                continue
            live = landmark.get("live")
            if not live or [int(live[0]), int(live[1])] != [observation.x, observation.y]:
                continue
            required_facing = landmark.get("facing")
            if required_facing and facing != required_facing:
                continue
            key = f"{room_id}:{landmark.get('id')}"
            existing = self.state["completed_landmarks"].get(key)
            if existing:
                return existing
            changes = tile_diff.get("changes", [])
            completion = {
                "room_id": room_id,
                "landmark_id": landmark.get("id"),
                "action": action,
                "position": [observation.x, observation.y],
                "facing": facing,
                "semantic_tile_change_count": int(tile_diff.get("semantic_count", 0)),
                "tile_changes": changes[:12],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.state["completed_landmarks"][key] = completion
            self.state["events"].append({
                "index": len(self.state["events"]) + 1,
                "type": "action_landmark_completed",
                **completion,
            })
            return completion
        return None

    def record_room_reset(self, observation: LiveNavigationObservation) -> dict:
        """Expire only momentary collisions in the current curated room."""
        current_room = self.room_for(observation, previous_room=self.state.get("current_room"))
        expired = []
        for node_key, edges in self.state["edges"].items():
            node = self.state["nodes"].get(node_key, {})
            if int(node.get("map_id", -1)) != observation.map_id:
                continue
            if current_room is not None:
                if node.get("room") != current_room:
                    continue
            elif (
                abs(int(node.get("x", -999)) - observation.x) > 8
                or abs(int(node.get("y", -999)) - observation.y) > 8
            ):
                continue
            for direction in list(edges):
                if edges[direction].get("outcome") == "blocked_now":
                    expired.append({"source": node_key, "direction": direction, "edge": edges.pop(direction)})
        node, _ = self.observe(observation)
        event = {
            "index": len(self.state["events"]) + 1,
            "type": "room_reset",
            "node": node,
            "room": current_room,
            "expired_blocked_now": expired,
        }
        self.state["events"].append(event)
        return event

    def render_ascii(self, map_id: int | None = None) -> str:
        points = []
        for key, node in self.state["nodes"].items():
            if map_id is None or int(node["map_id"]) == int(map_id):
                points.append((key, int(node["x"]), int(node["y"])))
        if not points:
            return ""
        min_x = min(x for _, x, _ in points)
        max_x = max(x for _, x, _ in points)
        min_y = min(y for _, _, y in points)
        max_y = max(y for _, _, y in points)
        width = (max_x - min_x) * 2 + 1
        height = (max_y - min_y) * 2 + 1
        rows = [[" " for _ in range(width)] for _ in range(height)]
        for key, x, y in points:
            gx = (x - min_x) * 2
            gy = (y - min_y) * 2
            rows[gy][gx] = "@" if key == self.state.get("current_node") else "."
            for direction, edge in self.state["edges"].get(key, {}).items():
                dx, dy = DIRECTIONS[direction]
                ex, ey = gx + dx, gy + dy
                if 0 <= ex < width and 0 <= ey < height:
                    if edge.get("outcome") == "blocked_now":
                        rows[ey][ex] = "!"
                    elif edge.get("outcome") in {"open", "transition"}:
                        target = edge.get("to")
                        if target:
                            _, target_x, target_y = self.parse_node_key(target)
                            target_gx = (target_x - min_x) * 2
                            target_gy = (target_y - min_y) * 2
                            if dx:
                                for fill_x in range(min(gx, target_gx) + 1, max(gx, target_gx)):
                                    rows[gy][fill_x] = "-"
                            else:
                                for fill_y in range(min(gy, target_gy) + 1, max(gy, target_gy)):
                                    rows[fill_y][gx] = "|"
                        else:
                            rows[ey][ex] = "-" if dx else "|"
        return "\n".join("".join(row).rstrip() for row in rows)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "OnlineNavigationMapper":
        return cls(state=json.loads(path.read_text(encoding="utf-8")))
