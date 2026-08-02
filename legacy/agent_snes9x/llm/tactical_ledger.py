import json
import os
import logging
from datetime import datetime


class TacticalLedger:
    def __init__(self, file_path="agent/memory/tactical_ledger.json"):
        if not os.path.isabs(file_path):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            file_path = os.path.join(project_root, file_path)
        self.file_path = file_path
        self.data = self._load()

    def _default_data(self):
        return {
            "total_rounds": 0,
            "perfect_rounds": 0,
            "hall_of_fame": [],
            "encounter_reports": {}
        }

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = self._default_data()
                if isinstance(data, dict):
                    merged.update(data)
                if not isinstance(merged.get("encounter_reports"), dict):
                    merged["encounter_reports"] = {}
                return merged
            except Exception as e:
                logging.error(f"Failed to load tactical ledger: {e}")
        return self._default_data()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save tactical ledger: {e}")

    def _encounter_key(self, location, enemy_names):
        loc = (location or "Unknown Location").strip()
        cleaned = [str(n).strip() for n in (enemy_names or []) if str(n).strip()]
        sig = ", ".join(sorted(cleaned)) if cleaned else "Unknown Encounter"
        return f"{loc} || {sig}", sig

    def record_round(self, is_perfect, enemy_context=None, thought=None, command=None):
        self.data["total_rounds"] += 1
        if is_perfect:
            self.data["perfect_rounds"] += 1
            if enemy_context and thought and command:
                self.data["hall_of_fame"].insert(0, {
                    "enemy": enemy_context,
                    "thought": thought,
                    "command": command,
                })
                self.data["hall_of_fame"] = self.data["hall_of_fame"][:5]
        self._save()

    def record_encounter_outcome(self, location, enemy_names, outcome, assessment="unknown", note=None, pre_snapshot=None, post_snapshot=None):
        key, signature = self._encounter_key(location, enemy_names)
        reports = self.data.setdefault("encounter_reports", {})
        report = reports.get(key, {
            "location": location or "Unknown Location",
            "enemy_signature": signature,
            "times_seen": 0,
            "times_won": 0,
            "times_fled": 0,
            "times_failed": 0,
            "worst_assessment": "unknown",
            "last_outcome": None,
            "last_note": "",
            "history": [],
        })

        report["times_seen"] += 1
        if outcome == "victory":
            report["times_won"] += 1
        elif outcome == "fled":
            report["times_fled"] += 1
        elif outcome in ("wipe", "loss"):
            report["times_failed"] += 1

        severity_rank = {"unknown": 0, "manageable": 1, "risky": 2, "severe": 3}
        if severity_rank.get(assessment, 0) >= severity_rank.get(report.get("worst_assessment", "unknown"), 0):
            report["worst_assessment"] = assessment
        report["last_outcome"] = outcome
        report["last_note"] = note or report.get("last_note", "")
        report.setdefault("history", []).insert(0, {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "outcome": outcome,
            "assessment": assessment,
            "note": note or "",
            "pre": pre_snapshot or {},
            "post": post_snapshot or {},
        })
        report["history"] = report["history"][:8]
        reports[key] = report
        self._save()

    def get_encounter_warning(self, location, enemy_names):
        key, signature = self._encounter_key(location, enemy_names)
        report = self.data.get("encounter_reports", {}).get(key)
        if not report:
            return None

        assessment = report.get("worst_assessment", "unknown")
        if assessment == "severe":
            return {
                "severity": "severe",
                "enemy_signature": signature,
                "summary": f"Past report: this encounter at {report.get('location')} was severe. Avoid unless the party is clearly stronger.",
                "note": report.get("last_note", ""),
            }
        if assessment == "risky":
            return {
                "severity": "risky",
                "enemy_signature": signature,
                "summary": f"Past report: this encounter at {report.get('location')} was costly. Fight only if resources are healthy.",
                "note": report.get("last_note", ""),
            }
        return {
            "severity": assessment,
            "enemy_signature": signature,
            "summary": f"Past report: this encounter at {report.get('location')} was previously manageable.",
            "note": report.get("last_note", ""),
        }

    def get_precision_stats(self):
        if self.data["total_rounds"] == 0:
            return "TACTICAL PRECISION: N/A (Fresh Unit)"
        perc = (self.data["perfect_rounds"] / self.data["total_rounds"]) * 100
        return f"TACTICAL PRECISION: {perc:.1f}% ({self.data['perfect_rounds']}/{self.data['total_rounds']} Perfect Rounds)"

    def get_hall_of_fame_string(self):
        if not self.data["hall_of_fame"]:
            return ""
        lines = ["### YOUR PAST EXCELLENCE (Proven Tactics)"]
        for entry in self.data["hall_of_fame"][:3]:
            lines.append(f"- Against {entry['enemy']}: \"{entry['thought']}\" -> {entry['command']}")
        return "\n".join(lines)
