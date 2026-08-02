"""Schema gate for LLM-owned tactical battle decisions."""

from __future__ import annotations

from dataclasses import dataclass

from agent.battle.policy import BattleOption


@dataclass(frozen=True)
class BattleDecision:
    option_id: str
    rationale: str
    risk_assessment: str
    contingency: str

    @classmethod
    def from_dict(cls, value: dict, legal_options: list[BattleOption]) -> "BattleDecision":
        if not isinstance(value, dict):
            raise ValueError("Battle decision must be a JSON object")
        option_id = str(value.get("option_id", "")).strip()
        legal_ids = {option.resolved_id for option in legal_options if option.usable}
        if option_id not in legal_ids:
            raise ValueError(f"Battle option is not currently legal: {option_id!r}")
        rationale = str(value.get("rationale", "")).strip()[:800]
        risk = str(value.get("risk_assessment", "")).strip()[:600]
        contingency = str(value.get("contingency", "")).strip()[:600]
        if not rationale or not risk:
            raise ValueError("Battle decision requires rationale and risk_assessment")
        return cls(option_id, rationale, risk, contingency)
