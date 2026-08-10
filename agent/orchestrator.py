"""Bounded Mesen-first control loop for autonomous Lufia II play."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.intent import Intent, gate_intent
from agent.context_harness import ContextHarness, ModelDriftError, ThinkingGate
from agent.dungeon_context import DungeonContextRegistry
from agent.knowledge import KnowledgeRetriever
from agent.mesen_controller import MesenController
from agent.model_client import LocalModelClient
from agent.navigation.online_mapper import OnlineNavigationMapper
from agent.navigation.tile_buffer import TileBufferRegistry
from agent.action_recorder import ActionOutcomeRecorder
from agent.perception import KeyframeObserver
from agent.progression import ProgressionPlanner
from agent.tutorial_guide import TutorialGuide
from agent.feedback import FeedbackLedger
from agent.watchdog import DecisionWatchdog, ModelStallError
from agent.battle import BattleCoordinator, BattleDecision, BattleOption
from agent.dungeons import get_dungeon
from agent.context_builder import ContextBuilder
from agent.feedback_manager import FeedbackManager
from agent.model_gateway import ModelGateway
from agent.battle_runner import BattleRunner
from agent.short_term_memory import ShortTermMemory
from agent.adaptation import ContinualHarnessManager


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OBJECTIVES = {
    0x05: PROJECT_ROOT / "data/navigation_objectives/secret_skills_cave_room_sweep.json",
}


class RunJournal:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = run_dir / "journal.jsonl"

    def write(self, event: str, **payload) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class MesenOrchestrator:
    def __init__(
        self,
        config: dict,
        goal: str,
        run_dir: Path,
        execute: bool = False,
        resume_battle_stage: str | None = None,
        resume_battle_actor: int = 0,
    ):
        self.config = config
        self.goal = goal
        self.run_dir = run_dir
        self.execute = execute
        self.resume_battle_stage = resume_battle_stage
        self.resume_battle_actor = resume_battle_actor
        self.controller = MesenController(config["emulator"])
        self.model = LocalModelClient(config["llm"])
        self.knowledge = KnowledgeRetriever(config["knowledge"])
        self.progression = ProgressionPlanner()
        self.dungeons = DungeonContextRegistry()
        self.tutorial = TutorialGuide()
        self.journal = RunJournal(run_dir)
        self.action_recorder = ActionOutcomeRecorder(run_dir / "action_outcomes.jsonl")
        self.feedback = FeedbackLedger(run_dir / "feedback_ledger.json")
        self.short_term_memory = ShortTermMemory(
            run_dir / "short_term_memory.json", goal
        )
        self.keyframes = KeyframeObserver(run_dir, min_action_gap=5)
        self.context_harness = ContextHarness(config["llm"], run_dir)
        self.thinking_gate = ThinkingGate(config["llm"])
        self.watchdog = DecisionWatchdog(
            config["llm"].get("watchdog_warning_seconds", 30),
            config["llm"].get("watchdog_bark_interval_seconds", 30),
            config["llm"].get("max_thinking_seconds", 120),
        )
        self.mapper = None
        self.tile_buffers = TileBufferRegistry()
        self.battle = BattleCoordinator(self.controller, self._ask_battle_model)
        self.actions = 0
        self.last_model_action = -10_000
        self.last_exploration_inventory_read: float | None = None
        self.last_intent_frame: Path | None = None
        self.active_navigation_target: dict | None = None
        self.suppress_generic_movement_reward = False
        self.last_decision_context: dict | None = None
        # Modular components
        self.context_builder = ContextBuilder(self.progression, self.dungeons, self.tutorial, self.tile_buffers)
        self.feedback_manager = FeedbackManager(
            self.feedback, self.action_recorder, self.mapper, self.tile_buffers,
            run_dir, memory=self.short_term_memory,
        )
        self.model_gateway = ModelGateway(
            self.model,
            self.watchdog,
            self.journal,
            self.thinking_gate,
            action_count=lambda: self.actions,
        )
        self.battle_runner = BattleRunner(self.battle, self.model_gateway, self.journal, self.feedback_manager)
        self.harness_refiner = ContinualHarnessManager(
            config.get("harness_evolution", {}),
            run_dir,
            self.model,
            self.journal,
            PROJECT_ROOT,
        )

    @property
    def reasoning_evidence(self) -> list:
        return self.feedback_manager.reasoning_evidence

    @reasoning_evidence.setter
    def reasoning_evidence(self, value: list) -> None:
        self.feedback_manager.reasoning_evidence = value

    @property
    def recent_agent_actions(self) -> list:
        return self.feedback_manager.recent_agent_actions

    @recent_agent_actions.setter
    def recent_agent_actions(self, value: list) -> None:
        self.feedback_manager.recent_agent_actions = value

    @property
    def reasoning_steps(self) -> int:
        return self.feedback_manager.reasoning_steps

    @reasoning_steps.setter
    def reasoning_steps(self, value: int) -> None:
        self.feedback_manager.reasoning_steps = value

    @property
    def stall_repeats(self) -> int:
        return self.feedback_manager.stall_repeats

    @stall_repeats.setter
    def stall_repeats(self, value: int) -> None:
        self.feedback_manager.stall_repeats = value

    def _load_mapper(self, map_id: int) -> OnlineNavigationMapper:
        graph_path = self.run_dir / "online_navigation_graph.json"
        objective_path = OBJECTIVES.get(map_id)
        objective = (
            json.loads(objective_path.read_text(encoding="utf-8"))
            if objective_path and objective_path.exists()
            else {"name": self.goal, "allowed_map_ids": []}
        )
        if graph_path.exists():
            return OnlineNavigationMapper.load(graph_path, objective=objective)
        return OnlineNavigationMapper(objective)

    def _context(self, observation) -> dict:
        raw = self.context_builder.build(
            observation, self.goal, self.mapper, self.feedback, self.reasoning_evidence, self.recent_agent_actions
        )
        self.short_term_memory.update_context(raw, self.actions)
        memory_snapshot = self.short_term_memory.recall()
        room_episode = memory_snapshot.get("room_episode", {})
        if (
            room_episode.get("origin") in {"reset_room", "external_reset"}
            and room_episode.get("intent_status") == "none"
        ):
            raw["room_episode"] = room_episode
        visual_exit = self._visual_exit_hypothesis(memory_snapshot)
        if visual_exit:
            raw.setdefault("navigation", {})["visual_progress_hypothesis"] = visual_exit
        remembered_changes = memory_snapshot.get("confirmed_world_changes", [])
        if remembered_changes:
            navigation = raw.setdefault("navigation", {})
            navigation["confirmed_world_changes"] = remembered_changes
            tracked_change = next(
                (
                    change for change in reversed(remembered_changes)
                    if change.get("movable_object_after")
                ),
                None,
            )
            if tracked_change:
                target = list(tracked_change["movable_object_after"])
                current = raw.get("position_update", {}).get("current", target)
                tracking = {
                    "estimated_live": target,
                    "last_actor_after_push": tracked_change.get("actor_after"),
                    "last_push_direction": tracked_change.get("direction"),
                    "delta_from_current": [
                        target[0] - current[0], target[1] - current[1]
                    ],
                    "status": (
                        "intermediate movable-object position, not puzzle success; approach an adjacent side, "
                        "then push only in a direction supported by the separate receiver/switch geometry"
                    ),
                    "authority": tracked_change.get("tracking_authority"),
                }
                tracking["direct_distance_reducing_directions"] = (
                    self._directions_reducing_delta(tracking["delta_from_current"])
                )
                tracking["manhattan_distance"] = sum(
                    abs(value) for value in tracking["delta_from_current"]
                )
                interaction_direction = self._direction_for_adjacent_delta(
                    tracking["delta_from_current"]
                )
                blocked_direction = interaction_direction or tracked_change.get("direction")
                blocked_push = self._blocked_push_evidence(
                    target,
                    blocked_direction,
                    memory_snapshot.get("recent_actions", []),
                )
                wall_confirmation = self._wall_confirmation(memory_snapshot)
                post_push_assessment_required = self._post_push_assessment_required(
                    memory_snapshot, self.actions
                )
                if blocked_push:
                    tracking["blocked_push_evidence"] = blocked_push
                if blocked_push and wall_confirmation:
                    tracking["wall_confirmation"] = wall_confirmation
                if post_push_assessment_required:
                    tracking["post_push_assessment_required"] = True
                tracking["action_readiness"] = (
                    {
                        "ready": False,
                        "action": "reset_room" if wall_confirmation else "inspect_then_recover",
                        "instruction": (
                            "Repeated directed pushes had no effect and vision confirms the object is "
                            "against a wall. Reset this room; further movement or inspection adds no evidence."
                            if wall_confirmation else
                            "The same directed push from the exact adjacent tile repeatedly had no effect. "
                            "Do not repeat it. Inspect whether the object is against a wall; reset only if "
                            "the arrangement is visibly unsalvageable."
                        ),
                    }
                    if blocked_push else ({
                        "ready": False,
                        "action": "look",
                        "instruction": (
                            "A single push just changed the object position. Before any further push, "
                            "visually locate the pillar and the separate floor switch. Check whether the pillar "
                            "moved closer to that switch, whether it now occupies it, and whether the door changed."
                        ),
                    } if post_push_assessment_required else
                    {
                        "ready": True,
                        "action": "interact",
                        "direction": interaction_direction,
                        "instruction": (
                            "A directed push is mechanically possible from this adjacent side. Choose it "
                            "only if the visible floor-switch geometry makes this push useful."
                        ),
                    }
                    if interaction_direction else
                    {"ready": False, "action": "approach_adjacent_tile"})
                )
                navigation["tracked_movable_object"] = tracking
                raw.setdefault("position_update", {})["tracked_movable_object"] = tracking
                room = navigation.get("current_room", {})
                reset_policy = room.get("reset_policy", {})
                if blocked_push and reset_policy.get("enabled"):
                    raw["room_reset_recovery"] = {
                        "eligible": True,
                        "reason": (
                            "a directed push from the exact adjacent tile repeatedly produced no actor "
                            "or object movement"
                        ),
                        "evidence": blocked_push,
                        "use_when": reset_policy.get("use_when"),
                        "do_not_use_when": reset_policy.get("do_not_use_when"),
                        "vision_requirement": (
                            "current screenshot must confirm the movable object is against a wall and "
                            "the arrangement is unsalvageable"
                        ),
                    }
                    if wall_confirmation:
                        raw["room_reset_recovery"]["vision_confirmation"] = wall_confirmation
                        raw["room_reset_recovery"]["next_action"] = "reset_room"
                    reset_action = "reset_room (conditional puzzle recovery)"
                    actions = raw.setdefault("available_actions", [])
                    if reset_action not in actions:
                        actions.append(reset_action)
        raw["memory_access"] = self.short_term_memory.prompt_hint()
        raw = self.harness_refiner.enrich_context(raw)
        return self.context_harness.compact(raw)

    @staticmethod
    def _directions_reducing_delta(delta: list[int]) -> list[str]:
        candidates = []
        if delta[0]:
            candidates.append((abs(delta[0]), "east" if delta[0] > 0 else "west"))
        if delta[1]:
            candidates.append((abs(delta[1]), "south" if delta[1] > 0 else "north"))
        return [direction for _, direction in sorted(candidates, reverse=True)]

    @staticmethod
    def _direction_for_adjacent_delta(delta: list[int]) -> str | None:
        return {
            (0, -1): "north",
            (0, 1): "south",
            (-1, 0): "west",
            (1, 0): "east",
        }.get(tuple(delta))

    @staticmethod
    def _blocked_push_evidence(
        object_position: list[int],
        interaction_direction: str | None,
        remembered_actions: list[dict],
    ) -> dict | None:
        if interaction_direction is None:
            return None
        delta = {
            "north": (0, -1), "south": (0, 1),
            "west": (-1, 0), "east": (1, 0),
        }[interaction_direction]
        actor_position = [
            object_position[0] - delta[0],
            object_position[1] - delta[1],
        ]
        count = 0
        for action in reversed(remembered_actions):
            if (
                action.get("kind") == "interact"
                and action.get("direction") == interaction_direction
                and action.get("from") == actor_position
                and action.get("to") == actor_position
                and int(action.get("semantic_tile_changes", 0)) == 0
            ):
                count += 1
                continue
            if count:
                break
        if count < 2:
            return None
        return {
            "actor_live": actor_position,
            "object_live": object_position,
            "direction": interaction_direction,
            "consecutive_no_effect_pushes": count,
            "interpretation": (
                "push destination is impassable; vision must distinguish wall from temporary obstruction"
            ),
        }

    @staticmethod
    def _post_push_assessment_required(memory_snapshot: dict, action_count: int) -> bool:
        actions = memory_snapshot.get("recent_actions", [])
        if not actions:
            return False
        latest = actions[-1]
        if not (
            latest.get("kind") == "interact"
            and int(latest.get("semantic_tile_changes", 0)) > 0
            and latest.get("from") != latest.get("to")
        ):
            return False
        perceptions = memory_snapshot.get("recent_perceptions", [])
        return not (
            perceptions
            and perceptions[-1].get("kind") in {"look", "look_map"}
            and perceptions[-1].get("action_count") == action_count
        )

    @staticmethod
    def _wall_confirmation(memory_snapshot: dict) -> dict | None:
        strong_phrases = (
            "blocked by a wall",
            "against a wall",
            "against the wall",
            "wall-trapped",
            "at the wall",
        )
        for perception in reversed(memory_snapshot.get("recent_perceptions", [])):
            result = perception.get("result", {})
            hypothesis = str(result.get("navigation_hypothesis", ""))
            normalized = hypothesis.casefold()
            objects = " ".join(str(item) for item in result.get("relevant_objects", [])).casefold()
            if any(phrase in normalized for phrase in (
                "not a wall", "not against a wall", "can be moved", "still movable"
            )):
                return None
            if (
                ("pillar" in normalized or "pillar" in objects or "movable" in normalized)
                and any(phrase in normalized for phrase in strong_phrases)
            ):
                return {
                    "confirmed": True,
                    "source": perception.get("kind"),
                    "evidence": hypothesis[:300],
                }
        return None

    @staticmethod
    def _visual_exit_hypothesis(memory_snapshot: dict) -> dict | None:
        positive = []
        negative = []
        for perception in memory_snapshot.get("recent_perceptions", []):
            hypothesis = str(
                perception.get("result", {}).get("navigation_hypothesis", "")
            )
            normalized = hypothesis.casefold()
            on_switch = "pillar is on the floor switch" in normalized
            door_passable = any(phrase in normalized for phrase in (
                "door is passable", "door is open", "door opened"
            ))
            if on_switch and door_passable:
                positive.append(hypothesis)
            if any(phrase in normalized for phrase in (
                "not yet on the floor switch", "door is blocked", "door is not passable"
            )):
                negative.append(hypothesis)
        if len(positive) < 2:
            return None
        combined = " ".join(positive).casefold()
        direction = next(
            (name for name in ("north", "south", "east", "west") if f"{name} door" in combined),
            None,
        )
        return {
            "status": "corroborated_visual_hypothesis_pending_wram_traversal_test",
            "positive_observations": len(positive),
            "conflicting_observations": len(negative),
            "exit_direction": direction,
            "next_step": (
                f"attempt movement {direction} through the visibly passable door"
                if direction else
                "attempt movement through the visibly passable door"
            ),
            "success_evidence": "WRAM-confirmed room transition",
            "do_not_repeat": "pillar manipulation unless the current door traversal test is blocked",
            "evidence": positive[-1][:300],
        }

    def _default_look_question(self) -> str:
        memory = self.short_term_memory.recall()
        actions = memory.get("recent_actions", [])
        if actions and (
            actions[-1].get("kind") == "interact"
            and int(actions[-1].get("semantic_tile_changes", 0)) > 0
        ):
            return (
                "After the last single push, separately locate (1) the movable pillar and (2) the floor button "
                "in the middle of the brick floor. Did the pillar move closer to that separate button, does the "
                "pillar itself now occupy it, and did the door change? Guy is only the pusher and must not step "
                "onto the button as a test. "
                "If another push is needed, name the push direction and the actor approach side that move the "
                "pillar toward the button."
            )
        provisional = (
            (self.last_decision_context or {})
            .get("navigation", {})
            .get("provisional_object_target", {})
        )
        if provisional.get("live"):
            return (
                f"Correlate the screenshot with the established map-buffer object candidate at live "
                f"{provisional.get('live')}, relative {provisional.get('relative')}. Is it the visible "
                "movable object? Do not invent a nearer coordinate; identify a cardinally adjacent contact side."
            )
        return "What blocks progress?"

    @staticmethod
    def _movement_feedback_target(context: dict) -> dict | None:
        navigation = context.get("navigation", {})
        active = navigation.get("active_landmark")
        if active:
            return active
        current_step = context.get("task_progress", {}).get("current_step") or {}
        if (
            current_step.get("target_type") == "actor_position_for_final_push"
            and current_step.get("target")
        ):
            return {
                "id": "current_step_actor_target",
                "live": current_step["target"],
            }
        # Reaching a movable object is necessary setup, but it is not puzzle
        # progress. Rewarding actor distance to it made short loops look
        # successful while the object stayed off its receiver.
        return None

    def _ask_model(self, observation) -> Intent:
        if not self.config["llm"].get("enabled", False):
            return Intent("look", question="What prevents deterministic progress here?")
        minimum_gap = int(self.config["llm"].get("min_actions_between_calls", 0))
        if self.actions - self.last_model_action < minimum_gap and not self.reasoning_evidence:
            return Intent("wait", rationale="LLM call cooldown")
        context = self._context(observation)
        self.last_decision_context = context
        self.active_navigation_target = self._movement_feedback_target(context)
        navigation = context.get("navigation", {})
        self.suppress_generic_movement_reward = bool(
            not self.active_navigation_target
            and (
                navigation.get("tracked_movable_object")
                or navigation.get("provisional_object_target")
            )
        )
        frames = self._intent_frames(context)
        started = time.monotonic()
        try:
            intent = self.model_gateway.ask_intent(
                context,
                int(self.config["limits"]["max_move_batch"]),
                frames=frames,
            )
        except (ModelDriftError, ModelStallError, RuntimeError, ValueError, OSError) as exc:
            self.journal.write(
                "thinking_gate_rejected",
                error=str(exc),
                elapsed_seconds=round(time.monotonic() - started, 3),
                context_budget=context.get("context_budget"),
            )
            self.reasoning_evidence.append({
                "type": "gate_rejection",
                "error": str(exc),
                "instruction": "Choose a different legal action using the unchanged observed state.",
            })
            self.feedback.penalize("model_rejection", str(exc))
            return Intent("wait", rationale="model watchdog or drift gate requested a safe pause")
        finally:
            if self.config.get("llm", {}).get("cleanup_intent_frames_after_call", False):
                self._cleanup_intent_frames(frames)
        self.last_model_action = self.actions
        return intent

    def _cleanup_intent_frames(self, frames: list[Path]) -> None:
        for frame in frames:
            try:
                if frame.is_file() and frame.parent == self.run_dir / "intent_frames":
                    frame.unlink()
            except OSError:
                pass
        self.last_intent_frame = None

    def _intent_frames(self, context: dict) -> list[Path]:
        llm_config = self.config.get("llm", {})
        if (
            context.get("game", {}).get("mode") != "exploration"
            or not llm_config.get("exploration_visual_context", False)
        ):
            return []
        frame_dir = self.run_dir / "intent_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        current = frame_dir / f"intent_{self.actions:05d}_{time.monotonic_ns()}.png"
        current.write_bytes(self.controller.screenshot())
        frames = [current]
        history_count = max(1, int(llm_config.get("exploration_visual_history_frames", 2)))
        if self.last_intent_frame is not None and self.last_intent_frame.exists() and history_count > 1:
            frames.insert(0, self.last_intent_frame)
        if (
            context.get("game", {}).get("blocked_direction")
            and int(llm_config.get("exploration_visual_burst_on_blocked", 2)) > len(frames)
        ):
            burst = frame_dir / f"intent_{self.actions:05d}_{time.monotonic_ns()}_burst.png"
            burst.write_bytes(self.controller.screenshot())
            frames.append(burst)
        max_frames = max(
            history_count,
            int(llm_config.get("exploration_visual_burst_on_blocked", history_count)),
        )
        frames = frames[-max_frames:]
        self.last_intent_frame = frames[-1]
        return frames

    @staticmethod
    def _is_inventory_query(query: str) -> bool:
        normalized = " ".join(query.casefold().replace("_", " ").split())
        phrases = (
            "current inventory", "full inventory", "inventory list",
            "aktuelles inventar", "vollständiges inventar", "inventarliste",
            "item list", "itemliste", "gegenstandsliste",
        )
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _is_short_term_memory_query(query: str) -> bool:
        normalized = " ".join(query.casefold().replace("_", " ").split())
        return any(phrase in normalized for phrase in (
            "short term memory", "recent memory", "recent actions",
            "current run memory", "kurzzeitgedächtnis", "letzte aktionen",
        ))

    def _retrieve(self, observation, query: str) -> list[dict]:
        if self._is_short_term_memory_query(query):
            return [{
                "type": "short_term_memory",
                "snapshot": self.short_term_memory.recall(),
            }]
        if observation.game.mode == "exploration" and self._is_inventory_query(query):
            cooldown = float(
                self.config.get("llm", {}).get("exploration_inventory_cooldown_seconds", 600)
            )
            now = time.monotonic()
            elapsed = (
                None if self.last_exploration_inventory_read is None
                else now - self.last_exploration_inventory_read
            )
            if elapsed is not None and elapsed < cooldown:
                return [{
                    "type": "inventory_cooldown",
                    "message": "The full exploration inventory was already read recently.",
                    "retry_after_seconds": max(1, round(cooldown - elapsed)),
                }]
            self.last_exploration_inventory_read = now
            return [{
                "type": "live_wram_inventory",
                "items": [
                    {"name": item.name, "quantity": item.quantity}
                    for item in observation.game.inventory
                    if item.quantity > 0
                ],
            }]
        return self.knowledge.search(query or self.goal)

    def _look(self, observation, question: str) -> dict:
        frame = self.run_dir / f"look_{self.actions:05d}.png"
        frame.write_bytes(self.controller.screenshot())
        context = self._context(observation)
        if not self.config["llm"].get("enabled", False):
            result = {"status": "queued_no_model", "frame": str(frame), "question": question}
        else:
            try:
                result = self.model.look(frame, context, question)
            except (RuntimeError, ValueError, OSError) as exc:
                result = {
                    "status": "vision_response_invalid",
                    "error": str(exc)[:500],
                    "safe_next_test": (
                        "Use WRAM, local map context and reversible movement; vision supplied no reliable evidence."
                    ),
                }
        self.journal.write("look", question=question, frame=str(frame), result=result)
        self.short_term_memory.record_perception("look", question, result, self.actions)
        return result

    def _look_map(self, observation, question: str) -> dict:
        frame = self.run_dir / f"look_map_{self.actions:05d}.png"
        frame.write_bytes(self.controller.screenshot())
        context = self._context(observation)
        map_value = context.get("navigation_map", {}).get("full_map_image")
        map_path = Path(str(map_value)) if map_value else None
        if map_path is None or not map_path.is_file():
            result = {"status": "map_unavailable", "frame": str(frame), "question": question}
        elif not self.config["llm"].get("enabled", False):
            result = {
                "status": "queued_no_model",
                "frame": str(frame),
                "map": str(map_path),
                "question": question,
            }
        else:
            try:
                result = self.model.look(frame, context, question, map_frame=map_path)
            except (RuntimeError, ValueError, OSError) as exc:
                result = {
                    "status": "vision_response_invalid",
                    "error": str(exc)[:500],
                    "safe_next_test": (
                        "Use WRAM and curated map context; vision supplied no reliable evidence."
                    ),
                }
        self.journal.write(
            "look_map",
            question=question,
            frame=str(frame),
            map=str(map_path) if map_path is not None else None,
            result=result,
        )
        self.short_term_memory.record_perception("look_map", question, result, self.actions)
        return result

    def _ask_battle_model(
        self,
        battle_state: dict,
        legal_options: list[BattleOption],
        tactical_advisory: dict,
    ) -> BattleDecision:
        if not self.config["llm"].get("enabled", False):
            raise RuntimeError("Battle tactics require the configured LLM")
        return self.model_gateway.ask_battle(battle_state, legal_options, tactical_advisory)

    def _dungeon_feedback(self, hook: str, before, after, **kwargs) -> str | None:
        """Delegate to the active dungeon module for feedback, if registered."""
        dungeon_cls = get_dungeon(before.game.map_id)
        if dungeon_cls is None:
            return None
        dungeon = dungeon_cls(self.controller)
        method = getattr(dungeon, hook, None)
        if method is None:
            return None
        return method(before, after, **kwargs)

    def _clear_reasoning(self, action_feedback: dict | None = None) -> None:
        self.feedback_manager.clear_reasoning(action_feedback)

    def _reset_room_cognition(self) -> None:
        """Start a clean decision episode after the emulator restored the room."""
        self.recent_agent_actions = self.recent_agent_actions[-1:]
        self.active_navigation_target = None
        self.last_decision_context = None
        self.last_intent_frame = None
        self.context_harness.reset_room_episode()
        self.thinking_gate.reset_room_episode()
        self._clear_reasoning()
        self.reasoning_evidence.append({
            "type": "room_episode_reset",
            "message": (
                "The room was reset. Its puzzle is unsolved again. All pre-reset "
                "perceptions, object hypotheses, progress assumptions, and intentions are invalid; "
                "reobserve the live room and form a new plan."
            ),
        })

    def _remember_action(
        self, kind: str, before, after, navigation_event: dict | None = None, **details
    ) -> dict:
        feedback = self.feedback_manager.remember_action(
            kind, before, after, navigation_event, **details
        )
        self.harness_refiner.observe_latest_action()
        return feedback

    def run(self) -> dict:
        info = self.controller.connect()
        observation = self.controller.observe()
        self.mapper = self._load_mapper(observation.game.map_id)
        self.feedback_manager.mapper = self.mapper
        self.mapper.observe(observation.navigation)
        self.journal.write("start", goal=self.goal, execute=self.execute, emulator=info, state=observation.game.compact())
        if not self.execute:
            summary = {"stop_reason": "dry_run", "state": observation.game.compact()}
            self.journal.write("stop", **summary)
            return summary

        started = time.monotonic()
        limits = self.config["limits"]
        stop_reason = "action_limit"
        started_inside_battle = observation.game.in_battle
        while self.actions < int(limits["max_actions_per_run"]):
            if time.monotonic() - started >= float(limits["max_minutes_per_run"]) * 60:
                stop_reason = "time_limit"
                break

            progress = self.mapper.progress()
            if progress["complete"]:
                self.harness_refiner.maybe_refine(
                    self.action_recorder.index,
                    explicit_reason="objective_complete",
                )
                stop_reason = "objective_complete"
                self.journal.write("objective_complete", navigation=progress)
                break

            if observation.game.in_battle:
                if not self.config.get("battle", {}).get("execution_enabled", False):
                    self.journal.write(
                        "battle_gate",
                        result="execution_disabled",
                        state=observation.game.compact(),
                    )
                    stop_reason = "battle_execution_disabled"
                    break
                if not self.config["llm"].get("enabled", False):
                    stop_reason = "battle_model_required"
                    self.journal.write("battle_gate", result=stop_reason)
                    break
                observation, inputs, stop_reason = self.battle_runner.step(
                    observation, started_inside_battle, self.actions, self.resume_battle_stage, self.resume_battle_actor
                )
                self.actions += inputs
                if stop_reason:
                    break
                if not observation.game.in_battle:
                    started_inside_battle = False
                    self.mapper.observe(observation.navigation)
                    self._clear_reasoning()
                elif inputs == 0:
                    time.sleep(float(self.config["emulator"].get("settle_seconds", 0.32)))
                continue

            # Shadow refinement runs only between complete exploration actions.
            # It has no controller tool and cannot mutate active harness state.
            self.harness_refiner.maybe_refine(self.action_recorder.index)

            if self.reasoning_steps >= int(self.config["llm"].get("max_reasoning_steps_per_stall", 4)):
                self.harness_refiner.maybe_refine(
                    self.action_recorder.index,
                    explicit_reason="reasoning_step_limit",
                )
                stop_reason = "reasoning_step_limit"
                self.journal.write(
                    "reasoning_step_limit",
                    evidence=self.reasoning_evidence,
                    state=observation.game.compact(),
                )
                break

            intent = self._ask_model(observation)
            if intent.kind == "look":
                result = self._look(observation, intent.question or self._default_look_question())
                if not self.config["llm"].get("enabled"):
                    stop_reason = "needs_model_or_user_review"
                    break
                self.reasoning_evidence.append(
                    {"type": "look", "question": intent.question, "result": result}
                )
                self.reasoning_steps += 1
                continue
            if intent.kind == "look_map":
                result = self._look_map(
                    observation, intent.question or "Relate the current view to the curated dungeon map."
                )
                if not self.config["llm"].get("enabled"):
                    stop_reason = "needs_model_or_user_review"
                    break
                self.reasoning_evidence.append(
                    {"type": "look_map", "question": intent.question, "result": result}
                )
                self.reasoning_steps += 1
                continue
            if intent.kind == "retrieve":
                hits = self._retrieve(observation, intent.query or self.goal)
                self.journal.write("retrieval", query=intent.query, hits=hits)
                self.reasoning_evidence.append(
                    {"type": "retrieval", "query": intent.query, "hits": hits}
                )
                self.reasoning_steps += 1
                continue
            if intent.kind == "interact":
                before_action = observation
                observation = self.controller.interact(intent.direction)
                self.actions += 1
                action_feedback = self._remember_action(
                    "interact", before_action, observation,
                    requested_direction=intent.direction,
                    suppress_generic_movement_reward=self.suppress_generic_movement_reward,
                )
                self.mapper.observe(observation.navigation)
                self.journal.write(
                    "interact", action=self.actions, direction=intent.direction,
                    state=observation.game.compact(),
                )
                self._clear_reasoning(action_feedback)
                continue
            if intent.kind == "face":
                before_action = observation
                observation = self.controller.face(intent.direction)
                self.actions += 1
                action_feedback = self._remember_action("face", before_action, observation, requested_direction=intent.direction)
                self.mapper.observe(observation.navigation)
                self.journal.write(
                    "face", action=self.actions, direction=intent.direction,
                    state=observation.game.compact(),
                )
                self._clear_reasoning(action_feedback)
                continue
            if intent.kind == "select_tool":
                before_action = observation
                observation = self.controller.select_tool(intent.tool)
                self.actions += 1
                action_feedback = self._remember_action(
                    "select_tool", before_action, observation, tool=intent.tool, verified=True
                )
                self.mapper.observe(observation.navigation)
                self.journal.write(
                    "select_tool", action=self.actions, tool=intent.tool,
                    state=observation.game.compact(),
                )
                self._clear_reasoning(action_feedback)
                continue
            if intent.kind == "use_tool":
                before_action = observation
                before_frame = self.controller.screenshot()
                observation = self.controller.use_tool()
                after_frame = self.controller.screenshot()
                self.actions += 1
                visual_change = self.feedback.visual_change_ratio(before_frame, after_frame)
                action_feedback = self._remember_action(
                    "use_tool", before_action, observation, visual_change_ratio=visual_change
                )
                self.mapper.observe(observation.navigation)
                self.journal.write("use_tool", action=self.actions, state=observation.game.compact())
                self.keyframes.capture(
                    {"type": "use_tool", "outcome": "observe_effect", "action": self.actions},
                    after_frame,
                )
                # Dungeon-specific feedback (e.g. bridge status in Secret Skills Cave)
                dungeon_msg = self._dungeon_feedback("on_use_tool", before_action, observation)
                self._clear_reasoning(action_feedback)
                if dungeon_msg:
                    self.reasoning_evidence.append({
                        "type": "dungeon_feedback",
                        "message": dungeon_msg,
                    })
                continue
            if intent.kind == "sword":
                before_action = observation
                observation = self.controller.swing_sword()
                self.actions += 1
                action_feedback = self._remember_action("sword", before_action, observation)
                self.mapper.observe(observation.navigation)
                self.journal.write("sword", action=self.actions, state=observation.game.compact())
                self._clear_reasoning(action_feedback)
                continue
            if intent.kind == "reset_room":
                before_reset, observation = self.controller.reset_room()
                self.actions += 3
                reset_event = self.mapper.record_room_reset(observation.navigation)
                action_feedback = self._remember_action(
                    "reset_room", before_reset, observation, navigation_event=reset_event
                )
                # A room reset is a hard cognitive episode boundary.
                self._reset_room_cognition()
                self.journal.write(
                    "room_reset",
                    before=before_reset.game.compact(),
                    after=observation.game.compact(),
                    navigation_event=reset_event,
                )
                # Keep dungeon-specific reset evidence as diagnostics only. It
                # must not override the fresh "puzzle unsolved" decision state.
                reset_msg = self._dungeon_feedback("on_reset_room", before_reset, observation)
                if reset_msg:
                    self.journal.write("room_reset_observation", message=reset_msg)
                continue
            if intent.kind == "move":
                before_action = observation
                before = observation.navigation
                observation = self.controller.move(intent.direction, tiles=intent.count)
                self.actions += 1
                event = self.mapper.record_move(before, intent.direction, observation.navigation)
                completed_traversal = self.mapper.record_traversal_segment_result(
                    self.active_navigation_target, event
                )
                action_feedback = self._remember_action(
                    "move", before_action, observation, navigation_event=event,
                    requested_direction=intent.direction, requested_tiles=intent.count,
                    objective_target=(
                        (self.active_navigation_target or {}).get("effective_live")
                        or (self.active_navigation_target or {}).get("live")
                    ),
                    objective_landmark=(self.active_navigation_target or {}).get("id"),
                    objective_traversal=(self.active_navigation_target or {}).get("traversal"),
                    objective_checkpoint=(self.active_navigation_target or {}).get("checkpoint"),
                    completed_checkpoint=completed_traversal,
                    suppress_generic_movement_reward=self.suppress_generic_movement_reward,
                )
                self.mapper.save(self.run_dir / "online_navigation_graph.json")
                self.journal.write(
                    "move",
                    action=self.actions,
                    requested_tiles=intent.count,
                    movement_reason="llm_direction",
                    navigation_event=event,
                )
                if event["outcome"] in {"blocked_now", "transition", "encounter"} or event["new_room"]:
                    self.keyframes.capture(event, self.controller.screenshot())
                self._clear_reasoning(action_feedback)
                allowed_maps = {int(value) for value in self.mapper.objective.get("allowed_map_ids", [])}
                if allowed_maps and observation.game.map_id not in allowed_maps:
                    stop_reason = "objective_map_boundary"
                    self.journal.write(
                        "objective_map_boundary",
                        allowed_map_ids=sorted(allowed_maps),
                        observed_map_id=observation.game.map_id,
                    )
                    break
                continue
            if intent.kind == "wait":
                self.feedback.penalize("wait", "no emulator action was chosen", delta=-1)
                self.stall_repeats += 1
                if self.stall_repeats > int(limits.get("max_stall_repeats", 2)):
                    self.journal.write(
                        "model_wait_warning",
                        repeats=self.stall_repeats,
                        feedback=self.feedback.context(),
                    )
                    self.reasoning_evidence.append({
                        "type": "anti_stall",
                        "instruction": "Waiting produced no progress. Choose a reversible executable action, look_map, or retrieve next.",
                    })
                    current_context = self.last_decision_context or self._context(observation)
                    self.reasoning_evidence.extend(
                        self.harness_refiner.subagent_advice(
                            "model_wait_loop",
                            current_context,
                            read_tools={
                                "retrieve": lambda query: self._retrieve(observation, query),
                                "look": lambda question: self._look(observation, question),
                                "look_map": lambda question: self._look_map(observation, question),
                            },
                        )
                    )
                    self.harness_refiner.maybe_refine(
                        self.action_recorder.index,
                        explicit_reason="model_wait_loop",
                    )
                    self.stall_repeats = 0
                time.sleep(float(self.config["emulator"].get("settle_seconds", 0.32)))
                observation = self.controller.observe_stable()
                self.mapper.observe(observation.navigation)
                self.reasoning_steps += 1
                continue
            stop_reason = "unsupported_model_intent"
            break

        summary = {
            "stop_reason": stop_reason,
            "actions": self.actions,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "state": observation.game.compact(),
            "navigation": self.mapper.progress(),
            "harness": self.harness_refiner.summary(),
        }
        self.mapper.save(self.run_dir / "online_navigation_graph.json")
        (self.run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self.journal.write("stop", **summary)
        return summary
