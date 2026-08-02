"""Bounded Mesen-first control loop for autonomous Lufia II play."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
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
        self.reasoning_evidence = []
        self.recent_agent_actions = []
        self.reasoning_steps = 0
        self.stall_repeats = 0

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
        compact = observation.game.compact()
        navigation_progress = self.mapper.progress() if self.mapper else {}
        local_objective_active = (
            int(navigation_progress.get("rooms_expected", 0)) > 0
            and not navigation_progress.get("complete", False)
        )
        strategic_progression = (
            {
                "deferred": True,
                "reason": "Finish the active room-scoped dungeon objective before choosing another world destination.",
            }
            if local_objective_active
            else self.progression.choose_goal(compact["progression_items"])
        )
        selected_tool = {
            0xA7: "hook", 0xA8: "bomb", 0xA9: "arrow", 0xAA: "fire_arrow", 0xAB: "hammer"
        }.get(observation.wram[0x0A06])
        raw = {
            "goal": self.goal,
            "game": compact,
            "strategic_progression": strategic_progression,
            "dungeon_context": self.dungeons.context(
                observation.game.map_id, observation.game.x, observation.game.y, radius=9
            ),
            "navigation_map": self.dungeons.navigation_briefing(
                observation.game.map_id, observation.game.x, observation.game.y
            ),
            "tile_buffer": self.tile_buffers.context(
                observation.game.map_id,
                observation.game.x,
                observation.game.y,
                observation.wram,
                radius=2,
            ),
            "tutorial": self.tutorial.context(
                observation.game.map_id, observation.game.x, observation.game.y
            ),
            "selected_dungeon_tool": selected_tool,
            "available_actions": [
                "move(direction,count=1..4)",
                "face(direction) using R+direction without moving",
                "interact using A",
                "sword using B",
                "select_tool(tool)",
                "use_tool using Y",
                "look at current frame",
                "look_map at current frame plus full curated dungeon map",
                "retrieve(query)",
                "reset_room",
            ],
            "recent_agent_actions": self.recent_agent_actions,
            "feedback": self.feedback.context(),
            "navigation": self.mapper.context_for_llm() if self.mapper else {},
            "recent_events": self.mapper.state["events"][-6:] if self.mapper else [],
            "reasoning_evidence": self.reasoning_evidence,
        }
        return self.context_harness.compact(raw)

    def _ask_model(self, observation) -> Intent:
        if not self.config["llm"].get("enabled", False):
            return Intent("look", question="What prevents deterministic progress here?")
        minimum_gap = int(self.config["llm"].get("min_actions_between_calls", 0))
        if self.actions - self.last_model_action < minimum_gap and not self.reasoning_evidence:
            return Intent("wait", rationale="LLM call cooldown")
        context = self._context(observation)
        started = time.monotonic()
        try:
            def bark(elapsed: float) -> None:
                message = (
                    f"[LLM watchdog] {elapsed:.0f}s without a decision; "
                    "emulator input remains paused."
                )
                print(message, flush=True)
                self.journal.write(
                    "model_watchdog_bark",
                    elapsed_seconds=round(elapsed, 3),
                    action=self.actions,
                    state_fingerprint=list(self.thinking_gate.fingerprint(context)),
                )

            intent, elapsed = self.watchdog.run(
                lambda: self.model.choose_intent(
                    context, int(self.config["limits"]["max_move_batch"])
                ),
                bark,
            )
            self.thinking_gate.validate(intent, context, elapsed)
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
        self.journal.write(
            "model_intent",
            intent=asdict(intent),
            elapsed_seconds=round(time.monotonic() - started, 3),
            context_budget=context.get("context_budget"),
            perception="structured_state_only; use look or look_map for an on-demand screenshot",
        )
        return intent

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
        map_path = Path(str(context.get("navigation_map", {}).get("full_map_image", "")))
        if not map_path.exists():
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
            "look_map", question=question, frame=str(frame), map=str(map_path), result=result
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
        started = time.monotonic()

        def bark(elapsed: float) -> None:
            print(
                f"[Battle LLM watchdog] {elapsed:.0f}s without a decision; "
                "emulator input remains paused.",
                flush=True,
            )
            self.journal.write(
                "battle_model_watchdog_bark",
                elapsed_seconds=round(elapsed, 3),
                ui_stage=battle_state.get("ui_stage"),
            )

        decision, elapsed = self.watchdog.run(
            lambda: self.model.choose_battle_action(
                battle_state,
                legal_options,
                tactical_advisory,
            ),
            bark,
        )
        self.journal.write(
            "battle_model_decision",
            decision=asdict(decision),
            legal_option_ids=[option.resolved_id for option in legal_options],
            ui_stage=battle_state.get("ui_stage"),
            elapsed_seconds=round(elapsed, 3),
            total_elapsed_seconds=round(time.monotonic() - started, 3),
        )
        return decision

    def _clear_reasoning(self, action_feedback: dict | None = None) -> None:
        if action_feedback is not None and int(action_feedback.get("delta", 0)) <= 0:
            self.reasoning_evidence = self.reasoning_evidence[-2:] + [{
                "type": "action_no_progress",
                "feedback": action_feedback.get("feedback"),
                "instruction": "The last emulator action had no confirmed effect. Do not repeat it unchanged; inspect, retrieve, or choose a different reversible action.",
            }]
            self.reasoning_steps += 1
            return
        self.reasoning_evidence = []
        self.reasoning_steps = 0
        self.stall_repeats = 0

    def _remember_action(
        self, kind: str, before, after, navigation_event: dict | None = None, **details
    ) -> dict:
        previous_action = self.recent_agent_actions[-1] if self.recent_agent_actions else None
        if (
            kind == "move"
            and previous_action
            and previous_action.get("kind") == "move"
            and previous_action.get("before", {}).get("position") == [after.game.x, after.game.y]
            and previous_action.get("after", {}).get("position") == [before.game.x, before.game.y]
            and not (navigation_event or {}).get("new_room")
        ):
            details["immediate_backtrack"] = True
        tile_diff = self.tile_buffers.diff(
            before.game.map_id,
            before.wram,
            after.wram,
            ignore_live_points={
                (before.game.x, before.game.y),
                (after.game.x, after.game.y),
            },
        ) if before.game.map_id == after.game.map_id else {
            "available": False, "count": 0, "changes": []
        }
        details = {
            **details,
            "map_tile_change_count": int(tile_diff.get("semantic_count", 0)),
            "map_tile_observation_count": int(tile_diff.get("count", 0)),
            "map_tile_changes": tile_diff.get("changes", []),
        }
        completed_landmark = None
        if self.mapper is not None:
            completed_landmark = self.mapper.record_action_landmark_effect(
                kind, before.navigation, tile_diff
            )
        if completed_landmark:
            details["completed_landmark"] = completed_landmark
            self.mapper.save(self.run_dir / "online_navigation_graph.json")
        feedback = self.feedback.record(
            kind, before, after, navigation_event=navigation_event, **details
        )
        self.recent_agent_actions.append({
            "kind": kind,
            "before": {
                "position": [before.game.x, before.game.y],
                "direction": before.game.direction,
                "mode": before.game.mode,
            },
            "after": {
                "position": [after.game.x, after.game.y],
                "direction": after.game.direction,
                "mode": after.game.mode,
                "blocked_direction": after.game.blocked_direction,
            },
            "feedback": feedback,
            **details,
        })
        self.recent_agent_actions = self.recent_agent_actions[-6:]
        self.action_recorder.record(
            kind,
            before,
            after,
            feedback,
            navigation_event=navigation_event,
            tile_diff=tile_diff,
            **details,
        )
        return feedback

    def run(self) -> dict:
        info = self.controller.connect()
        observation = self.controller.observe()
        self.mapper = self._load_mapper(observation.game.map_id)
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
        battle_active = False
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
                if not battle_active:
                    if started_inside_battle and self.actions == 0:
                        if self.resume_battle_stage == "pre_menu":
                            self.battle.driver.begin_at_pre_menu()
                        elif self.resume_battle_stage == "action_cross":
                            self.battle.driver.resume_at_action_cross(self.resume_battle_actor)
                        elif self.resume_battle_stage == "results":
                            self.battle.driver.resume_at_results()
                        else:
                            stop_reason = "battle_resume_stage_required"
                            self.journal.write(
                                "battle_gate",
                                result=stop_reason,
                                reason="A mid-battle launch does not guess pre-menu versus action cross.",
                            )
                            break
                        self.journal.write(
                            "battle_resumed",
                            ui_stage=self.resume_battle_stage,
                            actor_slot=self.resume_battle_actor,
                        )
                    else:
                        self.battle.begin_new_battle()
                    battle_active = True
                    self.journal.write("battle_started", state=observation.game.compact())
                before_battle_step = observation
                try:
                    result = self.battle.step(observation)
                except (ModelStallError, RuntimeError, ValueError, OSError) as exc:
                    attempted_inputs = self.battle.driver.last_input_count
                    self.actions += attempted_inputs
                    stop_reason = "battle_step_rejected"
                    self.journal.write(
                        "battle_step_rejected",
                        error=str(exc),
                        ui_stage=self.battle.driver.session.stage.value,
                        attempted_inputs=attempted_inputs,
                    )
                    break
                observation = result.observation
                self.actions += result.inputs
                if result.inputs:
                    self._remember_action(
                        "battle_step",
                        before_battle_step,
                        observation,
                        battle_event=result.event,
                        ui_stage=self.battle.driver.session.stage.value,
                        inputs=result.inputs,
                    )
                self.journal.write(
                    "battle_step",
                    battle_event=result.event,
                    inputs=result.inputs,
                    ui_stage=self.battle.driver.session.stage.value,
                    state=observation.game.compact(),
                )
                if not observation.game.in_battle:
                    battle_active = False
                    started_inside_battle = False
                    self.mapper.observe(observation.navigation)
                    self._clear_reasoning()
                elif result.inputs == 0:
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
                hits = self.knowledge.search(intent.query or self.goal)
                self.journal.write("retrieval", query=intent.query, hits=hits)
                self.reasoning_evidence.append(
                    {"type": "retrieval", "query": intent.query, "hits": hits}
                )
                self.reasoning_steps += 1
                continue
            if intent.kind == "interact":
                before_action = observation
                observation = self.controller.interact()
                self.actions += 1
                action_feedback = self._remember_action("interact", before_action, observation)
                self.mapper.observe(observation.navigation)
                self.journal.write("interact", action=self.actions, state=observation.game.compact())
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
                self._clear_reasoning(action_feedback)
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
                self._clear_reasoning(action_feedback)
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
