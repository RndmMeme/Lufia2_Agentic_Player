"""Bounded local model client with Ollama and OpenAI-compatible transports."""

from __future__ import annotations

import base64
import copy
import json
import re
import threading
from pathlib import Path
from urllib.parse import urljoin

import requests

from .intent import Intent
from .battle.decision import BattleDecision
from .battle.policy import BattleOption


DEFAULT_PROVIDERS = (
    {"name": "ollama", "base_url": "http://127.0.0.1:11435"},
    {"name": "llama_cpp", "base_url": "http://127.0.0.1:8080/v1"},
    {"name": "koboldcpp", "base_url": "http://127.0.0.1:5001/v1"},
)

INTENT_FORMAT = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": [
            "move", "face", "interact", "sword", "select_tool", "use_tool",
            "look", "look_map", "reset_room", "battle_attack", "battle_flee",
            "wait", "retrieve",
        ]},
        "direction": {"enum": ["north", "south", "east", "west", None]},
        "count": {"type": "integer", "minimum": 1, "maximum": 4},
        "question": {"type": ["string", "null"]},
        "query": {"type": ["string", "null"]},
        "tool": {"enum": ["hook", "bomb", "arrow", "fire_arrow", "hammer", None]},
        "rationale": {"type": "string"},
    },
    "required": ["kind", "direction", "count", "question", "query", "tool", "rationale"],
}

VISION_FORMAT = {
    "type": "object",
    "properties": {
        "scene_type": {"type": "string"},
        "relevant_objects": {
            "type": "array",
            "items": {"type": "string", "maxLength": 64},
            "maxItems": 8,
            "uniqueItems": True,
        },
        "navigation_hypothesis": {"type": "string", "maxLength": 240},
        "confidence": {"type": "number"},
        "safe_next_test": {"type": "string", "maxLength": 160},
    },
    "required": [
        "scene_type", "relevant_objects", "navigation_hypothesis", "confidence", "safe_next_test"
    ],
}

BATTLE_FORMAT = {
    "type": "object",
    "properties": {
        "option_id": {"type": "string", "maxLength": 160},
        "rationale": {"type": "string", "maxLength": 240},
        "risk_assessment": {"type": "string", "maxLength": 240},
        "contingency": {"type": "string", "maxLength": 240},
    },
    "required": ["option_id", "rationale", "risk_assessment", "contingency"],
}


class LocalModelClient:
    def __init__(self, config: dict):
        self.config = config
        self._resolved: dict | None = None
        self._model_lock = threading.Lock()

    @staticmethod
    def _json_object(text: str) -> dict:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"Model response contained no JSON object: {text[:500]!r}")
        return json.loads(match.group(0))

    @staticmethod
    def _join(base_url: str, suffix: str) -> str:
        return urljoin(base_url.rstrip("/") + "/", suffix.lstrip("/"))

    @staticmethod
    def _raise_with_provider_error(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()[:1000]
            raise RuntimeError(
                f"Local model provider returned HTTP {response.status_code}: {detail or exc}"
            ) from exc

    def _candidates(self) -> list[dict]:
        configured = self.config.get("providers") or DEFAULT_PROVIDERS
        requested = str(self.config.get("provider", "auto")).lower()
        candidates = [dict(item) for item in configured]
        if requested != "auto":
            candidates = [item for item in candidates if item.get("name") == requested]
            if not candidates:
                raise RuntimeError(f"Unknown or unconfigured local model provider: {requested}")
        return candidates

    def detect(self, force: bool = False) -> dict:
        """Return the first healthy provider and concrete model without guessing."""
        if self._resolved is not None and not force:
            return dict(self._resolved)

        timeout = float(self.config.get("probe_timeout_seconds", 2.0))
        failures: list[str] = []
        for candidate in self._candidates():
            name = str(candidate["name"])
            base_url = str(candidate["base_url"])
            try:
                if name == "ollama":
                    response = requests.get(self._join(base_url, "api/tags"), timeout=timeout)
                    self._raise_with_provider_error(response)
                    models = [item.get("name") for item in response.json().get("models", [])]
                else:
                    response = requests.get(self._join(base_url, "models"), timeout=timeout)
                    self._raise_with_provider_error(response)
                    provider_payload = response.json()
                    models = [item.get("id") for item in provider_payload.get("data", [])]
                models = [model for model in models if model]
                model = candidate.get("model") or self.config.get("model") or (models[0] if models else None)
                if not model:
                    failures.append(f"{name}: service reachable, but no model is loaded")
                    continue
                resolved = dict(candidate)
                resolved["model"] = model
                if name != "ollama":
                    advertised = provider_payload.get("models", [])
                    matching = next(
                        (
                            item for item in advertised
                            if item.get("name") == model or item.get("model") == model
                        ),
                        advertised[0] if advertised else {},
                    )
                    resolved["capabilities"] = matching.get("capabilities", [])
                self._resolved = resolved
                return dict(resolved)
            except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as exc:
                failures.append(f"{name}: {exc}")
        raise RuntimeError("No usable local model provider. " + " | ".join(failures))

    @staticmethod
    def _ollama_messages(messages: list[dict]) -> list[dict]:
        converted: list[dict] = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                converted.append({"role": message["role"], "content": content})
                continue
            text_parts: list[str] = []
            images: list[str] = []
            for part in content:
                if part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
                elif part.get("type") == "image_url":
                    url = str(part.get("image_url", {}).get("url", ""))
                    images.append(url.split(",", 1)[1] if "," in url else url)
            converted_message = {"role": message["role"], "content": "\n".join(text_parts)}
            if images:
                converted_message["images"] = images
            converted.append(converted_message)
        return converted

    def _chat(self, messages: list[dict], role: str = "planner", response_format: dict | None = None) -> str:
        provider = self.detect()
        model = (
            provider.get(f"{role}_model")
            or self.config.get(f"{role}_model")
            or provider["model"]
        )
        timeout = float(self.config.get("timeout_seconds", 90))
        if provider["name"] == "ollama":
            with self._model_lock:
                self._ollama_unload_other_models(provider, model, timeout)
                payload = {
                    "model": model,
                    "messages": self._ollama_messages(messages),
                    "stream": False,
                    "format": response_format or (VISION_FORMAT if role == "vision" else INTENT_FORMAT),
                    "think": self.config.get(f"{role}_think", False),
                    "keep_alive": self.config.get(f"{role}_keep_alive", "0"),
                    "options": {
                        "num_ctx": int(self.config.get(f"{role}_context_tokens", 4096)),
                        "num_batch": int(self.config.get("ollama_num_batch", 128)),
                        "num_predict": int(
                            self.config.get(f"{role}_max_tokens", self.config.get("max_tokens", 220))
                        ),
                        "temperature": float(self.config.get("temperature", 0.1)),
                    },
                }
                response = requests.post(
                    self._join(provider["base_url"], "api/chat"), json=payload, timeout=timeout
                )
                self._raise_with_provider_error(response)
                message = response.json()["message"]
                # Thinking-capable Ollama models may place schema-constrained
                # output in `thinking` even when think=false, leaving content
                # empty. Prefer normal content but accept that provider-native
                # field so valid Qwen3-VL JSON is not discarded.
                content = str(message.get("content") or "").strip()
                thinking = str(message.get("thinking") or "").strip()
                return content or thinking

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": int(
                self.config.get(f"{role}_max_tokens", self.config.get("max_tokens", 220))
            ),
            "temperature": float(self.config.get("temperature", 0.1)),
        }
        if response_format is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": f"lufia2_{role}", "schema": response_format},
            }
        response = requests.post(
            self._join(provider["base_url"], "chat/completions"),
            json=payload,
            timeout=timeout,
        )
        self._raise_with_provider_error(response)
        return str(response.json()["choices"][0]["message"]["content"]).strip()

    def _ollama_unload_other_models(self, provider: dict, target_model: str, timeout: float) -> None:
        """Enforce one resident Ollama model on VRAM-constrained systems."""
        if self.config.get("resident_policy", "single") != "single":
            return
        response = requests.get(self._join(provider["base_url"], "api/ps"), timeout=min(timeout, 5.0))
        self._raise_with_provider_error(response)
        loaded = response.json().get("models", [])
        for entry in loaded:
            loaded_model = entry.get("name") or entry.get("model")
            if not loaded_model or loaded_model == target_model:
                continue
            unload = requests.post(
                self._join(provider["base_url"], "api/generate"),
                json={"model": loaded_model, "keep_alive": 0},
                timeout=timeout,
            )
            self._raise_with_provider_error(unload)

    def choose_intent(
        self,
        context: dict,
        max_move_batch: int,
        frame: Path | None = None,
        frames: list[Path] | None = None,
    ) -> Intent:
        system = (
            "You are the bounded decision layer for a Lufia II randomizer speedrun agent. "
            "You alone choose exploration directions; map and WRAM code never choose for you. "
            "Return JSON only. Choose one reversible intent from available_actions and never invent state. "
            "If mode is dialog, choose interact. Use position_update.current as the authoritative feet "
            "coordinate. After moving, use last_move.actual_delta and active_target.delta_from_current. "
            "When tracked_movable_object is present, its estimated_live and delta_from_current are the latest "
            "action-linked object-position evidence. Compare estimated_live with the current dungeon "
            "object_intent.required_live: x increases east and y increases south. To push an object in a desired "
            "direction, stand on its opposite side and use interact in the desired object-movement direction. "
            "After a successful push the actor occupies the object's old tile, so after the required visual check "
            "the same interact may be repeated while it still reduces the object-to-target delta. Approach an "
            "adjacent side before directed interact; do not interact from several tiles away. Prefer a listed direct_distance_reducing_direction when that exact "
            "local edge is WRAM-confirmed passable; detour only when direct approach is blocked or unsafe. When "
            "tracked_movable_object.action_readiness.ready only means a push is mechanically available from the "
            "chosen adjacent side; use its interact direction when it reduces the coordinate delta unless current "
            "visual or WRAM evidence proves that push blocked or unsafe. When current_step.action_readiness is ready "
            "and another push in that direction reduces the remaining delta, execute the stated interact instead of making another "
            "approach move. After every successful push, post_push_assessment_required means choose look and inspect "
            "pillar, switch, and door before any further push. If blocked_push_evidence is present, do not repeat "
            "that blocked push. "
            "For a weighted floor-switch puzzle, the movable object and floor switch are separate objects: "
            "Guy standing on the switch or merely reaching the movable object is never placement success. "
            "Guy is only the pusher; never route him onto the receiver as a test or substitute weight. "
            "One successful push is intermediate; the current room success_evidence is the only completion test. "
            "Use the current screenshot or look to distinguish a wall-trapped unsalvageable "
            "object from a temporary obstruction; reset only for the confirmed wall-trapped case. "
            "When room_reset_recovery.vision_confirmation.confirmed is true and next_action is reset_room, the "
            "required evidence is complete: choose reset_room instead of further movement, pushes, or inspection. "
            "After reset_room, room_episode is a hard cognitive boundary: the puzzle is unsolved, all pre-reset "
            "perceptions and intentions are invalid, and the live room must be observed and planned anew. "
            "When visual_progress_hypothesis is present, stop manipulating the solved object and perform its "
            "reversible door traversal test. Only WRAM transition confirms completion; return to the puzzle only "
            "if that current-state traversal test is blocked. "
            "A directed blocked_now observation is not automatically a wall or reverse block. Try other "
            "local edges when needed; backtracking is allowed and often required. "
            "select_tool requires tool=hook|bomb|arrow|fire_arrow|hammer; use_tool presses Y; "
            "sword presses B; interact(null) presses A while interact(direction) holds A then adds one direction impulse for "
            "pushing, pickup, or directional activation. Curated or visual 'push' always means "
            "interact(direction), never plain move. If the rationale says shoot or fire a selected "
            "dungeon tool, the kind is use_tool, never interact. Chests and NPCs use interact. Normal doors "
            "are crossed by movement through their threshold, never by use_tool. "
            "Treat task_progress as the resolved sequence state: completed_steps are finished even if the "
            "original goal still names them. Never repeat a completed step. current_step and "
            "navigation.active_landmark are the single current target; other landmarks are future context. "
            "If current_step.checkpoint_move is present, execute that exact direction and count; it is the "
            "already resolved next step toward the live puzzle stance and overrides a visual direction guess. "
            "If current_step.checkpoint_action is present, execute its exact kind and direction now. "
            "If task_progress.immediate_phase_feedback marks a one-time push as success, its not_advised action "
            "is a poor choice while that exact object_after_live state still holds; prefer the next actor target "
            "or checkpoint. Re-evaluate normally after a later live-state change. "
            "For an action landmark, obey action_readiness: first reach its exact live feet coordinate, then "
            "face the required direction, then execute the named action. Never execute the landmark action "
            "early. When it is fully ready, perform it before leaving. "
            "For directional traversal, the landmark is only an approach anchor. Obey traversal.phase and "
            "current_step.target: at threshold_ready enter in traversal.direction; at crossing_threshold "
            "continue that direction until the success signal. Never return to the anchor merely because "
            "its coordinate is behind you. A completed_traversal_segment means that straight segment is "
            "finished; choose the next local route freely instead of retrying its blocked direction. "
            "When local_layout_resolution is unresolved_after_transit, the previous room map and landmarks "
            "are stale: explore the live local layout from screenshot, actor-local tiles, movement, and "
            "collision feedback until a new stable room is observed. "
            "navigation.local_route_evidence applies only at the exact current feet coordinate. Its passable "
            "edges are WRAM-confirmed movement and override a conflicting visual guess; impassable_now is only "
            "directional and state-local. During stagnation, prefer a passable or untried edge not marked "
            "recent_non_progressing; that mark deprioritizes an A-B-A-B reversal but never forbids backtracking. "
            "A successful one-tile move toward a still-distant visible target is not arrival: continue along a "
            "WRAM-confirmed passable direction while visual distance decreases. Use count 2..4 for a known open "
            "stretch and count 1 near objects, turns, hazards, or uncertain collisions. "
            "Read navigation_map.ascii_crop, tile_buffer, spatial_correlation and the current screenshot "
            "together. visible_object_candidates lists nearby dynamic tile families with live coordinates and "
            "relative deltas; correlate them with the screenshot and objective before assigning sprite identity. "
            "During a puzzle, navigation_map.live_puzzle_overlay is the authoritative ephemeral view of current "
            "anchors: @ is the actor's feet, P the movable anchor, S its receiver, T the next actor stance, and * "
            "means the movable anchor occupies the receiver. Reach T before the stated push. The overlay expires "
            "after this decision and is never persistent map truth. "
            "A sole obstacle candidate may be the visible pillar, but it remains a hypothesis until contact or a "
            "successful push. When provisional_object_target exists, use its live coordinate, relative delta and "
            "distance-reducing directions as the current approach hypothesis; do not invent a nearer object. "
            "When its action_readiness.ready is true, the object is cardinally adjacent: use the stated "
            "interact(direction) contact test instead of moving away while describing an approach side. "
            "Target alignment is a preference, not local path proof. A collision plus tile family "
            "means impassable_now; only curated blocked evidence proves a wall. Room labels are hypotheses "
            "unless a transition confirms them; map_id identifies the dungeon/floor, not an internal room. "
            "established_memory contains curated run-independent facts. Apply a binary fact only when its live "
            "condition is true; dungeon facts belong only to the currently classified dungeon room. "
            "Dungeon tools remain listed during exploration and may solve puzzles or stun enemies. Never "
            "select an unavailable tool. Use retrieve('current inventory') only when needed. Calls are "
            "stateless; retrieve('short term memory') when earlier actions or puzzle changes are needed. "
            "reset_room is destructive and legal only when room_reset_recovery.eligible is true and vision "
            "confirms an unsalvageable arrangement; never reset for uncertainty, collision, transition, or "
            "an already solved puzzle. After neutral or negative feedback, change the attempt. Use look or "
            "look_map when current evidence is insufficient, then act on the returned evidence. "
            "Return exactly kind, direction, count, question, query, tool, rationale. Use null for unused "
            "direction/question/query/tool. Keep rationale below 20 words."
        )
        user = {
            "state_and_goal": context,
            "schema": {
                "kind": "valid kind for the current game mode",
                "direction": "north|south|east|west for move or directed interact",
                "count": f"1..{max_move_batch}",
                "question": "for look",
                "query": "for retrieve",
                "tool": "for select_tool",
                "rationale": "short",
            },
        }
        role = "deliberate" if len(context.get("reasoning_evidence", [])) >= 2 else "planner"
        content: str | list[dict] = json.dumps(user, ensure_ascii=False)
        visual_frames = list(frames or ([] if frame is None else [frame]))
        if visual_frames:
            content = [{
                "type": "text",
                "text": (
                    json.dumps(user, ensure_ascii=False)
                    + "\nScreenshots follow in chronological order (oldest to newest). "
                    "Use the newest as the current visual state."
                ),
            }]
            for index, visual_frame in enumerate(visual_frames, start=1):
                encoded = base64.b64encode(visual_frame.read_bytes()).decode("ascii")
                content.append({
                    "type": "text",
                    "text": f"Frame {index}/{len(visual_frames)}"
                    + (" (CURRENT)" if index == len(visual_frames) else " (PREVIOUS)"),
                })
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                })
            role = "vision"
        intent_format = copy.deepcopy(INTENT_FORMAT)
        available_kinds = {
            str(action).split(" ", 1)[0].split("(", 1)[0]
            for action in context.get("available_actions", [])
        }
        allowed_kinds = [
            kind for kind in INTENT_FORMAT["properties"]["kind"]["enum"]
            if kind in available_kinds
        ]
        if allowed_kinds:
            intent_format["properties"]["kind"]["enum"] = allowed_kinds
        raw = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            role=role,
            response_format=intent_format,
        )
        parsed = self._json_object(raw)
        try:
            return Intent.from_dict(parsed, max_move_batch=max_move_batch)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{exc}; model_json={json.dumps(parsed, ensure_ascii=False)[:700]}") from exc

    def look(self, frame: Path, context: dict, question: str, map_frame: Path | None = None) -> dict:
        provider = self.detect()
        capabilities = provider.get("capabilities", [])
        if capabilities and not ({"vision", "multimodal"} & set(capabilities)):
            raise RuntimeError(
                f"Loaded {provider['name']} model exposes {capabilities}, not vision; "
                "start it with a compatible multimodal projector or configure a vision provider"
            )
        encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
        prompt = (
            f"Question: {question}\n"
            "Classify only visible navigation semantics. The WRAM x/y anchor is at the feet. "
            "Do not claim permanent blockage from one failed movement. Return JSON with "
            "scene_type, relevant_objects, navigation_hypothesis, confidence, safe_next_test. "
            "List at most 8 distinct relevant object categories; consolidate duplicates with a count "
            "instead of repeating the same label.\n"
            f"Context: {json.dumps(context, ensure_ascii=False)}"
        )
        content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ]
        if map_frame is not None:
            map_encoded = base64.b64encode(map_frame.read_bytes()).decode("ascii")
            content[0]["text"] += "\nA second image is the curated full-dungeon navigation map."
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{map_encoded}"}})
        raw = self._chat(
            [{"role": "user", "content": content}],
            role="vision",
            response_format=VISION_FORMAT,
        )
        return self._json_object(raw)

    def choose_battle_action(
        self,
        battle_state: dict,
        legal_options: list[BattleOption],
        tactical_advisory: dict,
    ) -> BattleDecision:
        if not legal_options:
            raise ValueError("No verified legal battle options were supplied")
        system = (
            "You are the tactical commander in a randomized Lufia II battle. You must choose exactly "
            "one supplied option_id. The code determines legality but does not choose tactics for you. "
            "Consider initiative, probable incoming damage, healing timing, HP/MP/IP reserves, status, "
            "items, observed physical or elemental effectiveness, enemy remaining HP, escape, defend, "
            "and RNG risk. A non-caster cannot cast. Do not invent actions, costs, resistances or targets. "
            "At the action cross, available_item_macros contains only curated tactical subsets of items "
            "actually owned. The complete usable battle inventory is intentionally withheld until Item "
            "is selected; then legal_options contains the complete list. "
            "Return concise JSON with your choice, rationale, risk_assessment, and a contingency for the "
            "next command phase if the result is poor. Keep each explanation field below 30 words."
        )
        payload = {
            "battle_state": battle_state,
            "tactical_advisory": tactical_advisory,
            "legal_options": [
                {**option.__dict__, "option_id": option.resolved_id}
                for option in legal_options if option.usable
            ],
        }
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        raw = self._chat(messages, role="battle", response_format=BATTLE_FORMAT)
        try:
            parsed = self._json_object(raw)
        except (ValueError, json.JSONDecodeError):
            repair = (
                "Your previous response was not valid JSON. Make the tactical choice again from "
                "the same supplied state and option IDs. Return only the four required JSON fields; "
                "each explanation must stay below 20 words."
            )
            raw = self._chat(
                [{"role": "system", "content": repair}, messages[1]],
                role="battle",
                response_format=BATTLE_FORMAT,
            )
            parsed = self._json_object(raw)
        return BattleDecision.from_dict(parsed, legal_options)
