import json
import tempfile
import unittest
from pathlib import Path

from agent.navigation.online_mapper import LiveNavigationObservation, OnlineNavigationMapper
from agent.navigation.town_poi import load_town_pois


def observation(x=10, y=10, map_id=5, blocked=0xFF, battle=0):
    return LiveNavigationObservation(
        map_id=map_id,
        previous_map_id=0,
        x=x,
        y=y,
        sprite_id=2,
        movement_state=4,
        direction=4,
        blocked_attempt=blocked,
        map_context=0x11,
        exploration_mode=1,
        battle_mode=battle,
        global_x=0,
        global_y=0,
    )


class OnlineNavigationMapperTests(unittest.TestCase):
    def setUp(self):
        self.objective = {
            "name": "test sweep",
            "map_id": 5,
            "rooms": [
                {"id": "room_1", "bounds": {"min_x": 0, "min_y": 0, "max_x": 19, "max_y": 19}},
                {"id": "room_2", "bounds": {"min_x": 20, "min_y": 0, "max_x": 39, "max_y": 19}},
            ],
        }

    def test_wram_decoder_reads_confirmed_offsets(self):
        data = bytearray(0x20000)
        data[0x05AC] = 5
        data[0x05AE] = 0
        data[0x05D2] = 2
        data[0x066A] = 4
        data[0x0692] = 4
        data[0x06BA] = 28
        data[0x06E2] = 55
        data[0x1272] = 0xFF
        result = LiveNavigationObservation.from_wram(bytes(data))
        self.assertEqual((result.map_id, result.x, result.y), (5, 28, 55))
        self.assertFalse(result.moving)

    def test_open_move_records_edge_and_reverse(self):
        mapper = OnlineNavigationMapper(self.objective)
        event = mapper.record_move(observation(), "north", observation(y=9))
        start = mapper.node_key(5, 10, 10, "room_1")
        target = mapper.node_key(5, 10, 9, "room_1")
        self.assertEqual(event["outcome"], "open")
        self.assertEqual(mapper.state["edges"][start]["north"]["to"], target)
        self.assertEqual(mapper.state["edges"][target]["south"]["to"], start)

    def test_room_change_cleanup_preserves_coordinate_node_key(self):
        mapper = OnlineNavigationMapper(self.objective)
        mapper.observe(observation(x=19, y=10))
        mapper.state["completed_traversal_segments"]["room_1:door"] = {
            "id": "door", "status": "segment_boundary_reached"
        }
        event = mapper.record_move(
            observation(x=19, y=10), "east", observation(x=20, y=10)
        )
        expected = mapper.node_key(5, 20, 10, "room_2")
        self.assertEqual(expected, event["target"])
        self.assertEqual(expected, mapper.state["current_node"])
        self.assertEqual((5, 20, 10), mapper.parse_node_key(expected))
        self.assertNotIn("room_1:door", mapper.state["completed_traversal_segments"])

    def test_two_unit_cardinal_move_is_open_not_transition(self):
        mapper = OnlineNavigationMapper(self.objective)
        event = mapper.record_move(observation(), "north", observation(y=8))
        keys = [mapper.node_key(5, 10, y, "room_1") for y in (10, 9, 8)]
        self.assertEqual(event["outcome"], "open")
        self.assertEqual(event["traversed_nodes"], keys)
        self.assertEqual(mapper.state["edges"][keys[0]]["north"]["to"], keys[1])
        self.assertEqual(mapper.state["edges"][keys[1]]["north"]["to"], keys[2])
        self.assertEqual(mapper.state["edges"][keys[2]]["south"]["to"], keys[1])
        self.assertEqual(mapper.state["current_node"], keys[2])

        mapper.record_move(observation(), "north", observation(y=8))
        self.assertEqual(mapper.state["edges"][keys[0]]["north"]["observations"], 2)

    def test_encounter_without_position_change_does_not_create_wall(self):
        mapper = OnlineNavigationMapper(self.objective)
        event = mapper.record_move(observation(), "north", observation(battle=1))
        self.assertEqual(event["outcome"], "encounter")
        self.assertNotIn("north", mapper.state["edges"].get("05:10,10", {}))

    def test_blocked_move_uses_blocked_direction_byte(self):
        mapper = OnlineNavigationMapper(self.objective)
        event = mapper.record_move(observation(), "south", observation(blocked=1))
        start = mapper.node_key(5, 10, 10, "room_1")
        edge = mapper.state["edges"][start]["south"]
        self.assertEqual(event["outcome"], "blocked_now")
        self.assertTrue(edge["blocked_byte_matches_attempt"])
        self.assertEqual(edge["structural_type"], "unknown")
        self.assertEqual(edge["traversability"], "impassable_now")
        self.assertNotIn("north", mapper.state["edges"].get(start, {}))

    def test_room_objective_completes_without_revealing_route(self):
        mapper = OnlineNavigationMapper(self.objective)
        mapper.observe(observation(x=10))
        self.assertFalse(mapper.progress()["complete"])
        mapper.observe(observation(x=20))
        self.assertTrue(mapper.progress()["complete"])

    def test_curated_direction_prior_changes_only_unknown_edge_order(self):
        mapper = OnlineNavigationMapper(self.objective)
        mapper.observe(observation())
        self.assertEqual(
            mapper.next_direction({"north": "blocked", "east": "confirmed_walkable"}),
            "east",
        )
        mapper.record_move(observation(), "east", observation(x=12))
        # Once observed, the live edge remains authoritative regardless of priors.
        self.assertNotIn("east", mapper.unknown_directions(mapper.node_key(5, 10, 10, "room_1")))

    def test_frontier_probe_is_long_but_known_route_uses_single_tile(self):
        mapper = OnlineNavigationMapper(self.objective)
        mapper.record_move(observation(), "north", observation(y=8))
        endpoint = mapper.node_key(5, 10, 8, "room_1")
        mapper.state["edges"][endpoint].update({
            "east": {"outcome": "blocked_now", "to": None},
            "west": {"outcome": "blocked_now", "to": None},
            "north": {"outcome": "blocked_now", "to": None},
        })
        self.assertEqual(mapper.next_move(), ("south", 1, "known_route_to_frontier"))

    def test_room_reset_expires_only_current_room_momentary_collisions(self):
        mapper = OnlineNavigationMapper(self.objective)
        mapper.record_move(observation(x=10), "north", observation(x=10, blocked=0))
        mapper.record_move(observation(x=20), "south", observation(x=20, blocked=1))
        event = mapper.record_room_reset(observation(x=10))
        self.assertEqual(event["room"], "room_1")
        self.assertNotIn("north", mapper.state["edges"][mapper.node_key(5, 10, 10, "room_1")])
        self.assertIn("south", mapper.state["edges"][mapper.node_key(5, 20, 10, "room_2")])

    def test_room_reset_expires_only_resettable_landmark_completions(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_1",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 19, "max_y": 19},
                "reference_landmarks": [
                    {"id": "bridge_switch", "resettable": True},
                    {"id": "opened_chest"},
                ],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.state["completed_landmarks"] = {
            "room_1:bridge_switch": {"landmark_id": "bridge_switch"},
            "room_1:opened_chest": {"landmark_id": "opened_chest"},
        }
        event = mapper.record_room_reset(observation(x=10))
        self.assertNotIn("room_1:bridge_switch", mapper.state["completed_landmarks"])
        self.assertIn("room_1:opened_chest", mapper.state["completed_landmarks"])
        self.assertEqual(
            ["bridge_switch"],
            [item["landmark_id"] for item in event["expired_completed_landmarks"]],
        )

    def test_overlap_uses_prior_room_then_directed_successor(self):
        objective = {
            "map_id": 5,
            "rooms": [
                {
                    "id": "room_3", "bounds": {"min_x": 0, "min_y": 0, "max_x": 20, "max_y": 20},
                    "successors": ["room_4"],
                },
                {
                    "id": "room_4", "bounds": {"min_x": 10, "min_y": 0, "max_x": 30, "max_y": 20},
                    "successors": [],
                },
            ],
        }
        mapper = OnlineNavigationMapper(objective)
        # With no history, an overlapping coordinate remains honestly ambiguous.
        self.assertIsNone(mapper.room_for(observation(x=15)))
        mapper.observe(observation(x=5))
        self.assertEqual(mapper.room_for(observation(x=15)), "room_3")
        mapper.observe(observation(x=25))
        self.assertEqual(mapper.state["current_room"], "room_4")
        self.assertEqual(mapper.room_for(observation(x=15)), "room_4")

    def test_verified_entry_holds_predecessor_through_overlapping_transit(self):
        objective = {
            "map_id": 5,
            "rooms": [
                {
                    "id": "room_1",
                    "bounds": {"min_x": 0, "min_y": 0, "max_x": 19, "max_y": 19},
                    "successors": ["room_2"],
                },
                {
                    "id": "room_2",
                    "bounds": {"min_x": 20, "min_y": 0, "max_x": 39, "max_y": 19},
                    "predecessors": ["room_1"],
                    "entry_verification": {
                        "position": [20, 10], "global_position": [0, 0]
                    },
                },
            ],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=19, y=10))
        mapper.observe(observation(x=20, y=11))
        self.assertEqual("room_1", mapper.state["current_room"])
        mapper.observe(observation(x=20, y=10))
        self.assertEqual("room_2", mapper.state["current_room"])
        self.assertIn("room_2", mapper.state["verified_room_entries"])

    def test_secret_cave_threshold_stays_room_two_until_verified_room_three_tile(self):
        path = Path("data/navigation_objectives/secret_skills_cave_room_sweep.json")
        mapper = OnlineNavigationMapper(json.loads(path.read_text(encoding="utf-8")))
        mapper.observe(observation(x=28, y=33))
        mapper.observe(observation(x=28, y=32))
        self.assertEqual("room_2", mapper.state["current_room"])
        mapper.observe(observation(x=28, y=31))
        self.assertEqual("room_3", mapper.state["current_room"])
        self.assertIn("room_3", mapper.state["verified_room_entries"])

    def test_exact_successor_entry_overrides_overlapping_predecessor_bounds(self):
        objective = {
            "map_id": 5,
            "rooms": [
                {
                    "id": "room_5",
                    "bounds": {"min_x": 1, "min_y": 1, "max_x": 23, "max_y": 17},
                    "successors": ["room_6"],
                },
                {
                    "id": "room_6",
                    "bounds": {"min_x": 19, "min_y": 2, "max_x": 50, "max_y": 16},
                    "predecessors": ["room_5"],
                    "entry_verification": {"position": [19, 8]},
                },
            ],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=16, y=8))
        mapper.observe(observation(x=19, y=6))
        self.assertEqual("room_5", mapper.state["current_room"])
        mapper.observe(observation(x=19, y=8))
        self.assertEqual("room_6", mapper.state["current_room"])
        self.assertIn("room_6", mapper.state["verified_room_entries"])

    def test_verified_entry_prunes_false_room_nodes_before_first_entry(self):
        objective = {
            "map_id": 5,
            "rooms": [
                {
                    "id": "room_1",
                    "bounds": {"min_x": 0, "min_y": 0, "max_x": 19, "max_y": 19},
                    "successors": ["room_2"],
                },
                {
                    "id": "room_2",
                    "bounds": {"min_x": 20, "min_y": 0, "max_x": 39, "max_y": 19},
                    "predecessors": ["room_1"],
                    "entry_verification": {"position": [20, 10]},
                },
            ],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=19, y=10))
        false_key = mapper.node_key(5, 20, 11, "room_2")
        mapper.state["nodes"][false_key] = {
            "map_id": 5, "x": 20, "y": 11, "room": "room_2", "visits": 1
        }
        mapper.state["current_room"] = "room_2"
        mapper.state["current_node"] = false_key
        mapper.state["visited_rooms"].append("room_2")
        mapper.state["room_history"].append({"from": "room_1", "to": "room_2"})

        correct_key, new_room = mapper.observe(observation(x=20, y=10))

        self.assertNotIn(false_key, mapper.state["nodes"])
        self.assertEqual(mapper.node_key(5, 20, 10, "room_2"), correct_key)
        self.assertTrue(new_room)
        self.assertEqual(
            {"from": "room_1", "to": "room_2", "map_id": 5, "position": [20, 10]},
            mapper.state["room_history"][-1],
        )

    def test_load_refreshes_embedded_objective(self):
        old = {"name": "old", "map_id": 5, "rooms": []}
        current = {"name": "current", "map_id": 5, "rooms": []}
        mapper = OnlineNavigationMapper(old)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.json"
            mapper.save(path)
            loaded = OnlineNavigationMapper.load(path, objective=current)
        self.assertEqual("current", loaded.objective["name"])
        self.assertEqual("current", loaded.state["objective"]["name"])

    def test_load_expires_traversal_completion_when_curated_direction_changed(self):
        old = {
            "map_id": 5,
            "rooms": [{
                "id": "room_3",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 20, "max_y": 20},
                "reference_landmarks": [{
                    "id": "west_door", "live": [10, 10], "kind": "door", "facing": "north",
                }],
            }],
        }
        current = json.loads(json.dumps(old))
        current["rooms"][0]["reference_landmarks"][0]["facing"] = "west"
        mapper = OnlineNavigationMapper(old)
        mapper.state["completed_traversal_segments"] = {
            "room_3:west_door": {"direction": "north"}
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.json"
            mapper.save(path)
            loaded = OnlineNavigationMapper.load(path, objective=current)
        self.assertEqual({}, loaded.state["completed_traversal_segments"])

    def test_secret_cave_west_door_approach_stays_in_room_three(self):
        objective_path = (
            Path(__file__).resolve().parent.parent
            / "data/navigation_objectives/secret_skills_cave_room_sweep.json"
        )
        mapper = OnlineNavigationMapper(json.loads(objective_path.read_text(encoding="utf-8")))
        mapper.observe(observation(x=28, y=33))
        mapper.observe(observation(x=28, y=31))
        mapper.observe(observation(x=28, y=25))
        mapper.observe(observation(x=21, y=25))
        event = mapper.record_move(
            observation(x=21, y=25), "west", observation(x=20, y=25)
        )
        self.assertEqual("room_3", mapper.state["current_room"])
        self.assertFalse(event.get("new_room", False))

        # Live-run regression: (17,23) is the approach tile below the west
        # door.  The cave door itself is traversed north-south, despite its
        # location on the west side of the room.
        mapper.observe(observation(x=17, y=23))
        landmark = next(
            item
            for item in mapper.current_room_context()["nearby_live_landmarks"]
            if item["id"] == "west_door_approach"
        )
        self.assertEqual("threshold_ready", landmark["traversal"]["phase"])
        self.assertEqual("north", landmark["traversal"]["direction"])
        self.assertEqual([17, 22], landmark["effective_live"])

    def test_loop_completion_requires_return_to_start(self):
        objective = dict(self.objective)
        objective["completion"] = "visit_all_rooms_and_return_to_start"
        objective["start"] = {"room_id": "room_1", "position": [10, 10], "radius": 1}
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=10))
        mapper.observe(observation(x=20))
        self.assertTrue(mapper.progress()["all_rooms_visited"])
        self.assertFalse(mapper.progress()["complete"])
        mapper.observe(observation(x=2))
        self.assertFalse(mapper.progress()["returned_to_start"])
        mapper.observe(observation(x=10))
        self.assertTrue(mapper.progress()["returned_to_start"])
        self.assertTrue(mapper.progress()["complete"])

    def test_landmark_context_derives_cardinal_steps_and_action_readiness(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_1",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [{
                    "id": "switch", "live": [10, 12], "facing": "west", "action": "use_tool"
                }],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=10, y=10))
        landmark = mapper.current_room_context()["nearby_live_landmarks"][0]
        self.assertEqual(
            landmark["derived_relation"]["steps_to_reach"],
            [{"direction": "south", "tiles": 2}],
        )
        mapper.observe(observation(x=10, y=12))
        landmark = mapper.current_room_context()["nearby_live_landmarks"][0]
        self.assertTrue(landmark["derived_relation"]["at_landmark"])
        self.assertEqual(landmark["action_readiness"]["next_precondition"], "face west")

    def test_coordinate_checkpoint_remains_complete_after_leaving_tile(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_1",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [
                    {"id": "alignment", "live": [10, 11], "kind": "push_alignment"},
                    {"id": "push", "live": [10, 11], "facing": "north", "action": "push"},
                ],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=10, y=11))
        checkpoint = mapper.current_room_context()["nearby_live_landmarks"][0]["checkpoint"]
        mapper.record_coordinate_checkpoint(checkpoint, observation(x=10, y=11))
        mapper.observe(observation(x=10, y=10))

        room_context = mapper.current_room_context()
        self.assertTrue(
            next(item for item in room_context["nearby_live_landmarks"] if item["id"] == "alignment")["completed"]
        )
        self.assertEqual("push", mapper.next_room_landmark(room_context)["id"])

    def test_door_landmark_exposes_data_driven_traversal_at_anchor(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_3",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [{
                    "id": "west_door_approach",
                    "live": [17, 23],
                    "facing": "north",
                    "kind": "door",
                }],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=17, y=23))
        landmark = mapper.current_room_context()["nearby_live_landmarks"][0]
        self.assertEqual("move", landmark["traversal"]["action"])
        self.assertEqual("north", landmark["traversal"]["direction"])
        self.assertTrue(landmark["traversal"]["position_ready"])
        self.assertEqual("threshold_ready", landmark["traversal"]["phase"])
        self.assertEqual([17, 22], landmark["effective_live"])
        self.assertEqual("traversal", landmark["checkpoint"]["type"])
        self.assertFalse(landmark["traversal"]["interaction_required"])
        self.assertIn("map_id may remain unchanged", landmark["traversal"]["success_signal"])

        # Run-49 regression: after entering the doorway, the next target must
        # remain forward instead of pulling the actor back to the anchor.
        mapper.observe(observation(x=17, y=22))
        landmark = mapper.current_room_context()["nearby_live_landmarks"][0]
        self.assertEqual("crossing_threshold", landmark["traversal"]["phase"])
        self.assertEqual([17, 21], landmark["effective_live"])
        self.assertEqual(
            [{"direction": "north", "tiles": 1}],
            landmark["derived_relation"]["steps_to_reach"],
        )
        self.assertIn("continue north", landmark["traversal"]["next_step"])

    def test_explicit_directional_traversal_is_location_agnostic(self):
        objective = {
            "map_id": 12,
            "rooms": [{
                "id": "town_square",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [{
                    "id": "inn_entrance",
                    "live": [8, 9],
                    "kind": "poi",
                    "traversal": {
                        "direction": "east",
                        "success_signal": "interior layout is observed",
                    },
                }],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=9, y=9, map_id=12))
        landmark = mapper.current_room_context()["nearby_live_landmarks"][0]
        self.assertEqual("crossing_threshold", landmark["traversal"]["phase"])
        self.assertEqual([10, 9], landmark["effective_live"])
        self.assertEqual("interior layout is observed", landmark["checkpoint"]["success_when"])

    def test_forward_collision_finishes_only_the_transit_segment(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_3",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [{
                    "id": "door_approach",
                    "live": [17, 23],
                    "facing": "north",
                    "kind": "door",
                }],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=17, y=18))
        active = mapper.current_room_context()["nearby_live_landmarks"][0]
        self.assertEqual("crossing_threshold", active["traversal"]["phase"])
        event = mapper.record_move(
            observation(x=17, y=18),
            "north",
            observation(x=17, y=18, blocked=0),
        )
        result = mapper.record_traversal_segment_result(active, event)
        self.assertEqual("segment_boundary_reached", result["status"])
        self.assertEqual([17, 18], result["boundary_live"])
        self.assertEqual(
            result,
            mapper.completed_traversal_segment("room_3", "door_approach"),
        )

        reset = mapper.record_room_reset(observation(x=17, y=18))
        self.assertEqual(1, len(reset["expired_traversal_segments"]))
        self.assertIsNone(
            mapper.completed_traversal_segment("room_3", "door_approach")
        )

    def test_semantic_map_change_completes_matching_action_landmark(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_1",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [{
                    "id": "bridge_switch",
                    "live": [10, 12],
                    "facing": "north",
                    "action": "use_tool",
                }],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        at_switch = observation(x=10, y=12)
        mapper.observe(at_switch)
        self.assertIsNone(
            mapper.record_action_landmark_effect(
                "use_tool", at_switch, {"semantic_count": 0, "changes": []}
            )
        )
        completion = mapper.record_action_landmark_effect(
            "use_tool",
            at_switch,
            {
                "semantic_count": 1,
                "changes": [{"live": [9, 12], "before": "02", "after": "00"}],
            },
        )
        self.assertEqual(completion["landmark_id"], "bridge_switch")
        landmark = mapper.current_room_context()["nearby_live_landmarks"][0]
        self.assertTrue(landmark["completed"])
        self.assertTrue(landmark["action_readiness"]["completed"])
        self.assertIsNone(landmark["action_readiness"]["next_precondition"])

    def test_curated_push_is_executable_interact_and_keeps_authored_sequence(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_4",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [
                    {"id": "alignment", "live": [9, 21]},
                    {"id": "final_push", "live": [4, 22], "facing": "north", "action": "push"},
                    {"id": "exit", "live": [6, 17], "facing": "north", "kind": "door"},
                ],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        mapper.observe(observation(x=14, y=18))
        room = mapper.current_room_context()
        first = mapper.next_room_landmark(room)
        self.assertEqual("alignment", first["id"])
        self.assertEqual(0, first["sequence_index"])

        mapper.observe(observation(x=9, y=21))
        room = mapper.current_room_context()
        second = mapper.next_room_landmark(room)
        self.assertEqual("final_push", second["id"])
        self.assertEqual("push", second["semantic_action"])
        self.assertEqual("interact", second["action"])
        self.assertEqual("action", second["checkpoint"]["type"])

    def test_interact_completes_curated_push_landmark(self):
        objective = {
            "map_id": 5,
            "rooms": [{
                "id": "room_4",
                "bounds": {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 30},
                "reference_landmarks": [{
                    "id": "final_push", "live": [4, 22], "facing": "north", "action": "push"
                }],
            }],
        }
        mapper = OnlineNavigationMapper(objective)
        at_push = observation(x=4, y=22)
        completion = mapper.record_action_landmark_effect(
            "interact", at_push, {"semantic_count": 1, "changes": [{"live": [4, 21]}]}
        )
        self.assertEqual("final_push", completion["landmark_id"])


class TownPoiParserTests(unittest.TestCase):
    def test_parses_standard_and_wrapped_x_coordinates(self):
        payload = """Town  map_id  Building  (ext / int)  coords
Elcid   3    Inn entrance    ext    120, 128
Elcid   4    Inn keeper      int    248-40, 240
"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pois.txt"
            path.write_text(payload, encoding="utf-8")
            entries = load_town_pois(path)
        self.assertEqual((entries[0]["map_id"], entries[0]["x"], entries[0]["y"]), (3, 120, 128))
        self.assertEqual((entries[1]["x"], entries[1]["y"]), (248, 240))
        self.assertEqual(entries[1]["wrapped_x_range"], [248, 40])


if __name__ == "__main__":
    unittest.main()
