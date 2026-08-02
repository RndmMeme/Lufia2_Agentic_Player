"""Bounded local model client with Ollama and OpenAI-compatible transports."""

from __future__ import annotations

import base64
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
    {"name": "ollama", "base_url": "http://127.0.0.1:11434"},
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
        "relevant_objects": {"type": "array"},
        "navigation_hypothesis": {"type": "string"},
        "confidence": {"type": "number"},
        "safe_next_test": {"type": "string"},
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
                    models = [item.get("id") for item in response.json().get("data", [])]
                models = [model for model in models if model]
                model = candidate.get("model") or self.config.get("model") or (models[0] if models else None)
                if not model:
                    failures.append(f"{name}: service reachable, but no model is loaded")
                    continue
                resolved = dict(candidate)
                resolved["model"] = model
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
            "max_tokens": int(self.config.get("max_tokens", 220)),
            "temperature": float(self.config.get("temperature", 0.1)),
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

    def choose_intent(self, context: dict, max_move_batch: int, frame: Path | None = None) -> Intent:
        system = (
            "You are the bounded decision layer for a Lufia II randomizer speedrun agent. "
            "You alone choose exploration directions; map and WRAM code never choose for you. "
            "Return JSON only. Choose one reversible intent. Never invent memory values. "
            "A directed blocked_now observation is not automatically a wall or reverse block. "
            "Valid exploration kinds: move, face, interact, sword, select_tool, use_tool, "
            "look, look_map, reset_room, wait, retrieve. "
            "If mode is dialog, choose interact. If mode is battle, choose battle_attack unless evidence "
            "requires fleeing. Use reset_room only to reset a failed puzzle state or intentionally respawn room actors. "
            "Use face to turn without walking. select_tool requires tool=hook|bomb|arrow|fire_arrow|hammer; "
            "use_tool presses Y; sword presses B; interact presses A. "
            "Facing only turns in place. Never choose face when already facing that direction; "
            "move to align the actor's row or column with a visible ranged target before use_tool. "
            "Only use an ASCII @ marker when coordinate_semantics_available is true. When runtime alignment is "
            "room_landmarks, the stitched map is visual reference only and active-room live landmarks are authoritative. "
            "Curated markers are evidence, not commands. "
            "tile_buffer is a small actor-centered, map-scoped WRAM view: @ is the actor's feet. "
            "Use it as local tile-family evidence only; unknown values and occupancy do not prove walkability. "
            "For live landmarks, trust derived_relation: x increases east and y increases south. "
            "Never move north to reach a landmark whose derived step says south. At an action landmark, stop moving; "
            "satisfy action_readiness (facing/tool) and then execute the stated action. "
            "If the current frame and context are insufficient, ask look_map or retrieve rather than guessing. "
            "Use the feedback ledger: repeat positively rewarded behavior when relevant and change choices after "
            "negative feedback. Reversible experiments are better than passive waiting; use wait only for an active animation. "
            "Do not immediately return to the prior position after a rewarded open move unless new evidence requires it; "
            "a known reverse edge is not forward progress toward the room objective. "
            "Your output budget is scarce: decide within the supplied evidence and keep the rationale short. "
            "If reasoning_evidence contains LOOK or retrieval results, use them and choose an executable next intent."
        )
        user = {
            "state_and_goal": context,
            "schema": {
                "kind": "valid kind",
                "direction": "north|south|east|west for move",
                "count": f"1..{max_move_batch}",
                "question": "for look",
                "query": "for retrieve",
                "tool": "for select_tool",
                "rationale": "short",
            },
        }
        role = "deliberate" if len(context.get("reasoning_evidence", [])) >= 2 else "planner"
        content: str | list[dict] = json.dumps(user, ensure_ascii=False)
        if frame is not None:
            encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
            content = [
                {"type": "text", "text": json.dumps(user, ensure_ascii=False)},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ]
            role = "vision"
        raw = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            role=role,
            response_format=INTENT_FORMAT,
        )
        parsed = self._json_object(raw)
        try:
            return Intent.from_dict(parsed, max_move_batch=max_move_batch)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{exc}; model_json={json.dumps(parsed, ensure_ascii=False)[:700]}") from exc

    def look(self, frame: Path, context: dict, question: str, map_frame: Path | None = None) -> dict:
        encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
        prompt = (
            f"Question: {question}\n"
            "Classify only visible navigation semantics. The WRAM x/y anchor is at the feet. "
            "Do not claim permanent blockage from one failed movement. Return JSON with "
            "scene_type, relevant_objects, navigation_hypothesis, confidence, safe_next_test.\n"
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
