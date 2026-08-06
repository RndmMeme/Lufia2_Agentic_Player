"""Transparent outcome feedback for the LLM exploration policy."""

from __future__ import annotations

import json
import io
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops


class FeedbackLedger:
    def __init__(self, path: Path):
        self.path = path
        self.state = {"schema": 1, "score": 0, "entries": []}
        if path.exists():
            self.state.update(json.loads(path.read_text(encoding="utf-8")))

    def _append(self, kind: str, delta: int, reason: str, **details) -> dict:
        self.state["score"] = int(self.state.get("score", 0)) + int(delta)
        if delta >= 8:
            message = f"Strong success: {reason}"
        elif delta > 0:
            message = f"Good progress: {reason}"
        elif delta < 0:
            message = f"Correction needed: {reason}"
        else:
            message = f"Neutral observation: {reason}"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "delta": delta,
            "score_after": self.state["score"],
            "feedback": message,
            **details,
        }
        self.state.setdefault("entries", []).append(entry)
        self.state["entries"] = self.state["entries"][-100:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return entry

    def record(self, kind: str, before, after, navigation_event: dict | None = None, **details) -> dict:
        before_pos = (before.game.x, before.game.y)
        after_pos = (after.game.x, after.game.y)
        distance = abs(after_pos[0] - before_pos[0]) + abs(after_pos[1] - before_pos[1])
        delta = 0
        reasons = []
        if before.game.map_id != after.game.map_id:
            delta += 15
            reasons.append("map transition reached")
        elif distance:
            target = details.get("objective_target")
            if isinstance(target, (list, tuple)) and len(target) == 2:
                before_distance = abs(before_pos[0] - int(target[0])) + abs(before_pos[1] - int(target[1]))
                after_distance = abs(after_pos[0] - int(target[0])) + abs(after_pos[1] - int(target[1]))
                improvement = before_distance - after_distance
                details["objective_distance_before"] = before_distance
                details["objective_distance_after"] = after_distance
                if improvement > 0:
                    delta += min(8, improvement * 2)
                    reasons.append(f"distance to active landmark decreased by {improvement} tile(s)")
                elif improvement < 0:
                    reasons.append(
                        f"distance to active landmark increased by {abs(improvement)} tile(s); "
                        "this may be a valid detour or backtrack"
                    )
                else:
                    reasons.append("movement did not reduce distance to the active landmark")
            else:
                delta += min(8, distance * 2)
                reasons.append(f"position advanced by {distance} tile(s)")
        if before.game.event_flags != after.game.event_flags or before.game.dungeon_flags != after.game.dungeon_flags:
            delta += 8
            reasons.append("persistent game or dungeon state changed")
        if before.game.mode != after.game.mode:
            delta += 3
            reasons.append(f"mode changed {before.game.mode}->{after.game.mode}")
        if navigation_event:
            outcome = navigation_event.get("outcome")
            if outcome == "blocked_now":
                delta -= 4
                reasons.append("movement was blocked and must not be repeated unchanged")
            elif outcome == "transition":
                delta += 6
                reasons.append("room transition reached")
            elif outcome == "encounter":
                delta += 2
                reasons.append("intentional encounter reached")
            if navigation_event.get("new_room"):
                delta += 10
                reasons.append("new tutorial room reached")
        if kind == "face" and before.game.direction != after.game.direction:
            delta += 1
            reasons.append("facing changed without moving")
        if kind == "select_tool" and details.get("verified"):
            delta += 2
            reasons.append(f"tool selection verified: {details.get('tool')}")
        if details.get("immediate_backtrack"):
            reasons.append("backtracking observed; valid for route testing or dungeon topology")
        visual_change_ratio = float(details.get("visual_change_ratio", 0.0))
        if visual_change_ratio >= 0.005:
            delta += 5
            reasons.append(f"visible scene changed ({visual_change_ratio:.1%} of pixels)")
        tile_change_count = int(details.get("map_tile_change_count", 0))
        if tile_change_count:
            delta += min(8, 4 + tile_change_count)
            reasons.append(f"registered map buffer changed at {tile_change_count} non-actor tile(s)")
        if not reasons:
            reasons.append("no confirmed effect yet; observe before judging the attempt")
        return self._append(
            kind, delta, "; ".join(reasons),
            before_position=list(before_pos), after_position=list(after_pos), **details,
        )

    @staticmethod
    def visual_change_ratio(before_png: bytes, after_png: bytes) -> float:
        """Return the share of visibly changed pixels in equal-sized frames."""
        with Image.open(io.BytesIO(before_png)) as left_image, Image.open(io.BytesIO(after_png)) as right_image:
            left = left_image.convert("RGB")
            right = right_image.convert("RGB")
            if left.size != right.size:
                return 1.0
            difference = ImageChops.difference(left, right)
            changed = 0
            for red, green, blue in difference.getdata():
                if max(red, green, blue) >= 8:
                    changed += 1
            return changed / max(1, left.width * left.height)

    def penalize(self, kind: str, reason: str, delta: int = -2) -> dict:
        return self._append(kind, delta, reason)

    def context(self) -> dict:
        return {
            "score": int(self.state.get("score", 0)),
            "recent": self.state.get("entries", [])[-6:],
            "policy": (
                "Positive points praise verified progress. Negative points flag ineffective or invalid choices. "
                "Use this feedback to adapt; do not become passive or afraid to test a reversible action."
            ),
        }
