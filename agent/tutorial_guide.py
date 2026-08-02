"""Location-scoped tutorial lessons supplied as evidence, never as commands."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LESSONS_PATH = ROOT / "data/tutorials/secret_skills_cave.json"


class TutorialGuide:
    def __init__(self, path: Path = LESSONS_PATH):
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def context(self, map_id: int, x: int, y: int) -> dict:
        if int(self.data.get("map_id", -1)) != int(map_id):
            return {"active": False}
        matching = []
        for lesson in self.data.get("lessons", []):
            bounds = lesson.get("bounds", {})
            if (
                int(bounds.get("min_x", -1)) <= x <= int(bounds.get("max_x", -1))
                and int(bounds.get("min_y", -1)) <= y <= int(bounds.get("max_y", -1))
            ):
                matching.append({key: value for key, value in lesson.items() if key != "bounds"})
        return {
            "active": True,
            "teaching_style": self.data.get("teaching_style"),
            "current_lessons": matching,
            "question_policy": self.data.get("question_policy"),
        }
