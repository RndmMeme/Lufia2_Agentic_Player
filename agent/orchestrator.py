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
        # Modular components
        self.context_builder = ContextBuilder(self.progression, self.dungeons, self.tutorial, self.tile_buffers)
        self.feedback_manager = FeedbackManager(self.feedback, self.action_recorder, self.mapper, self.tile_buffers, run_dir)
        self.model_gateway = ModelGateway(
            self.model,
            self.watchdog,
            self.journal,
            self.thinking_gate,
            action_count=lambda: self.actions,
        )
        self.battle_runner = BattleRunner(self.battle, self.model_gateway, self.journal, self.feedback_manager)

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
        if graph_path.exists():
            return OnlineNavigationMapper.load(graph_path)
        objective_path = OBJECTIVES.get(map_id)
        objective = (
            json.loads(objective_path.read_text(encoding="utf-8"))
            if objective_path and objective_path.exists()
            else {"name": self.goal, "allowed_map_ids": []}
        )
        return OnlineNavigationMapper(objective)

    def _context(self, observation) -> dict:
        raw = self.context_builder.build(
            observation, self.goal, self.mapper, self.feedback, self.reasoning_evidence, self.recent_agent_actions
        )
        return self.context_harness.compact(raw)

    def _ask_model(self, observation) -> Intent:
        if not self.config["llm"].get("enabled", False):
            return Intent("look", question="What prevents deterministic progress here?")
        minimum_gap = int(self.config["llm"].get("min_actions_between_calls", 0))
        if self.actions - self.last_model_action < minimum_gap and not self.reasoning_evidence:
            return Intent("wait", rationale="LLM call cooldown")
        context = self._context(observation)
        self.active_navigation_target = context.get("navigation", {}).get("active_landmark")
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
        self.last_model_action = self.actions
        return intent

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

    def _retrieve(self, observation, query: str) -> list[dict]:
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
            result = self.model.look(frame, context, question)
        self.journal.write("look", question=question, frame=str(frame), result=result)
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
            result = self.model.look(frame, context, question, map_frame=map_path)
        self.journal.write(
            "look_map",
            question=question,
            frame=str(frame),
            map=str(map_path) if map_path is not None else None,
            result=result,
        )
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

    def _remember_action(
        self, kind: str, before, after, navigation_event: dict | None = None, **details
    ) -> dict:
        return self.feedback_manager.remember_action(kind, before, after, navigation_event, **details)

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

            if self.reasoning_steps >= int(self.config["llm"].get("max_reasoning_steps_per_stall", 4)):
                stop_reason = "reasoning_step_limit"
                self.journal.write(
                    "reasoning_step_limit",
                    evidence=self.reasoning_evidence,
                    state=observation.game.compact(),
                )
                break

            intent = self._ask_model(observation)
            if intent.kind == "look":
                result = self._look(observation, intent.question or "What blocks progress?")
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
                self.journal.write(
                    "room_reset",
                    before=before_reset.game.compact(),
                    after=observation.game.compact(),
                    navigation_event=reset_event,
                )
                # Dungeon-specific reset feedback
                reset_msg = self._dungeon_feedback("on_reset_room", before_reset, observation)
                self._clear_reasoning(action_feedback)
                if reset_msg:
                    self.reasoning_evidence.append({
                        "type": "dungeon_reset",
                        "message": reset_msg,
                    })
                continue
            if intent.kind == "move":
                before_action = observation
                before = observation.navigation
                observation = self.controller.move(intent.direction, tiles=intent.count)
                self.actions += 1
                event = self.mapper.record_move(before, intent.direction, observation.navigation)
                action_feedback = self._remember_action(
                    "move", before_action, observation, navigation_event=event,
                    requested_direction=intent.direction, requested_tiles=intent.count,
                    objective_target=(self.active_navigation_target or {}).get("live"),
                    objective_landmark=(self.active_navigation_target or {}).get("id"),
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
        }
        self.mapper.save(self.run_dir / "online_navigation_graph.json")
        (self.run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self.journal.write("stop", **summary)
        return summary
