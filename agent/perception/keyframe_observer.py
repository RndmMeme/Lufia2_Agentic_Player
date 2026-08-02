"""Persist sparse visual keyframes without putting screenshots in the control loop."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


class KeyframeObserver:
    """Queues only semantically useful frames for later VLM interpretation."""

    def __init__(self, run_dir: Path, min_action_gap: int = 4):
        self.output_dir = run_dir / "vision_keyframes"
        self.manifest_path = run_dir / "vision_queue.json"
        self.min_action_gap = max(0, int(min_action_gap))
        self.entries = []
        if self.manifest_path.exists():
            self.entries = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    @staticmethod
    def _visual_hash(png: bytes) -> str:
        with Image.open(io.BytesIO(png)) as image:
            pixels = list(image.convert("L").resize((16, 16)).getdata())
        average = sum(pixels) / len(pixels)
        bits = "".join("1" if value >= average else "0" for value in pixels)
        return f"{int(bits, 2):064x}"

    @staticmethod
    def _hamming(left: str, right: str) -> int:
        return (int(left, 16) ^ int(right, 16)).bit_count()

    def _reason(self, event: dict) -> str | None:
        if event.get("outcome") == "encounter":
            return "encounter"
        if event.get("new_room"):
            return "room_entry"
        if event.get("outcome") == "transition":
            return "transition"
        if event.get("outcome") == "blocked_now":
            return "unresolved_collision"
        return None

    def capture(self, event: dict, png: bytes) -> dict | None:
        reason = self._reason(event)
        if reason is None:
            return None
        action = int(event.get("index", 0))
        if reason == "unresolved_collision" and self.entries:
            last_action = int(self.entries[-1].get("action", -10_000))
            if action - last_action < self.min_action_gap:
                return None

        fingerprint = self._visual_hash(png)
        after = event.get("after", {})
        for prior in reversed(self.entries[-12:]):
            if prior.get("reason") != reason:
                continue
            if abs(int(prior.get("x", -999)) - int(after.get("x", 0))) > 2:
                continue
            if abs(int(prior.get("y", -999)) - int(after.get("y", 0))) > 2:
                continue
            if self._hamming(prior["visual_hash"], fingerprint) <= 8:
                return None

        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{action:04d}_{reason}.png"
        image_path = self.output_dir / filename
        image_path.write_bytes(png)
        entry = {
            "action": action,
            "reason": reason,
            "source": event.get("source"),
            "direction": event.get("direction"),
            "target": event.get("target"),
            "map_id": after.get("map_id"),
            "x": after.get("x"),
            "y": after.get("y"),
            "blocked_byte": after.get("blocked_attempt"),
            "image": str(image_path),
            "visual_hash": fingerprint,
            "sha256": hashlib.sha256(png).hexdigest(),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "semantic_status": "pending",
        }
        self.entries.append(entry)
        self.manifest_path.write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return entry
