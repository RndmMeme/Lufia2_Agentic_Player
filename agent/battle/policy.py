"""Rank an externally verified legal battle action set."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.battle.state import BattlePhase, BattleState


@dataclass(frozen=True)
class BattleOption:
    kind: str
    actor_slot: int
    name: str
    target_mask: int
    usable: bool = True
    mp_cost: int = 0
    ip_cost: int = 0
    estimated_damage: int = 0
    estimated_healing: int = 0
    revives: bool = False
    element: str | None = None
    consumes_item: bool = False
    all_targets: bool = False
    supports_group_toggle: bool = False
    option_id: str = ""
    menu_index: int | None = None
    storage_slot: int | None = None
    ability_id: int | None = None
    description: str = ""
    target_side: str = "unknown"
    quantity: int | None = None
    item_categories: tuple[str, ...] = ()

    @property
    def resolved_id(self) -> str:
        return self.option_id or f"{self.actor_slot}:{self.kind}:{self.name}:{self.target_mask:02X}"


@dataclass(frozen=True)
class BattleRecommendation:
    option: BattleOption | None
    score: float
    reasons: tuple[str, ...]
    requires_tactical_reasoning: bool


@dataclass
class CombatMemory:
    physical_zero_hits: dict[int, int] = field(default_factory=dict)
    element_damage: dict[tuple[int, str], list[int]] = field(default_factory=dict)

    def record_damage(self, enemy_identity: int, kind: str, damage: int, element: str | None = None):
        if kind == "attack" and damage <= 0:
            self.physical_zero_hits[enemy_identity] = self.physical_zero_hits.get(enemy_identity, 0) + 1
        if element:
            self.element_damage.setdefault((enemy_identity, element), []).append(max(0, damage))

    def physical_ineffective(self, enemy_identity: int) -> bool:
        return self.physical_zero_hits.get(enemy_identity, 0) >= 2

    def element_mean(self, enemy_identity: int, element: str) -> float | None:
        values = self.element_damage.get((enemy_identity, element))
        return sum(values) / len(values) if values else None


class BattlePolicy:
    """Produce tactical advisories; the LLM, not this class, chooses the action."""

    def __init__(self, critical_ratio: float = 0.25, low_ratio: float = 0.45):
        self.critical_ratio = critical_ratio
        self.low_ratio = low_ratio

    def situation(self, state: BattleState, memory: CombatMemory | None = None) -> dict:
        memory = memory or CombatMemory()
        return {
            "party_hp_ratios": {
                member.name: round(member.hp / member.max_hp, 3) if member.max_hp else 0
                for member in state.game.party
            },
            "critical_party_slots": [
                member.slot for member in state.game.party
                if member.alive and member.max_hp and member.hp / member.max_hp <= self.critical_ratio
            ],
            "disabled_party_slots": [member.slot for member in state.game.party if not member.alive],
            "enemy_total_hp": sum(enemy.hp for enemy in state.game.enemies if enemy.alive),
            "learned_physical_ineffective_enemy_ids": [
                enemy.identity for enemy in state.game.enemies
                if memory.physical_ineffective(enemy.identity)
            ],
            "initiative_queue": [
                {"actor_mask": entry.actor_mask, "enemy": entry.enemy, "initiative": entry.initiative}
                for entry in state.initiative
            ] if state.phase == BattlePhase.EXECUTION else [],
            "initiative_authoritative": state.phase == BattlePhase.EXECUTION,
            "active_action": {
                "actor_mask": state.active_action.actor_mask,
                "target_mask": state.active_action.target_mask,
                "command": state.active_action.command,
                "action_id": state.active_action.action_id,
            } if state.phase == BattlePhase.EXECUTION else None,
            "advisory_only": True,
        }

    def rank(
        self,
        state: BattleState,
        actor_slot: int,
        legal_options: list[BattleOption],
        memory: CombatMemory | None = None,
    ) -> list[BattleRecommendation]:
        memory = memory or CombatMemory()
        options = [option for option in legal_options if option.usable and option.actor_slot == actor_slot]
        if not options or actor_slot >= len(state.game.party):
            return []

        party = state.game.party
        enemies = state.game.enemies
        actor = party[actor_slot]
        alive_enemies = [enemy for enemy in enemies if enemy.alive]
        total_enemy_hp = sum(enemy.hp for enemy in alive_enemies)
        physical_bad = bool(alive_enemies) and all(memory.physical_ineffective(e.identity) for e in alive_enemies)
        dead_allies = [member for member in party if not member.alive]
        critical = [
            member for member in party
            if member.alive and member.max_hp and member.hp / member.max_hp <= self.critical_ratio
        ]
        low = [
            member for member in party
            if member.alive and member.max_hp and member.hp / member.max_hp <= self.low_ratio
        ]
        best_finisher = max((option.estimated_damage for option in options), default=0)
        enemy_finishable = total_enemy_hp > 0 and best_finisher >= total_enemy_hp

        ranked = []
        for option in options:
            score = 0.0
            reasons = []
            if dead_allies and option.revives:
                score += 160
                reasons.append("revive_disabled_ally")
            if critical and option.estimated_healing > 0:
                score += 120
                reasons.append("critical_party_healing")
                if option.all_targets and len(low) > 1:
                    score += 35
                    reasons.append("multi_target_healing_efficiency")
            elif low and option.estimated_healing > 0:
                score += 55
                reasons.append("low_party_healing")

            if option.estimated_damage > 0:
                score += min(70, option.estimated_damage / max(1, total_enemy_hp) * 70)
                reasons.append("damage_progress")
                if enemy_finishable and option.estimated_damage >= total_enemy_hp:
                    score += 90
                    reasons.append("confirmed_finisher")
            if physical_bad and option.kind == "attack":
                score -= 140
                reasons.append("learned_physical_ineffective")
            if physical_bad and option.kind == "spell" and option.element:
                score += 80
                reasons.append("magic_over_ineffective_physical")
            if option.element and alive_enemies:
                means = [memory.element_mean(enemy.identity, option.element) for enemy in alive_enemies]
                known = [value for value in means if value is not None]
                if known:
                    score += min(60, sum(known) / len(known) / 10)
                    reasons.append("learned_element_effectiveness")

            if option.mp_cost and actor.max_mp:
                reserve = actor.mp - option.mp_cost
                if reserve < max(5, actor.max_mp * 0.1):
                    score -= 25
                    reasons.append("low_mp_reserve")
            if option.consumes_item:
                score -= 12
                reasons.append("consumable_cost")
                if critical or dead_allies:
                    score += 25
                    reasons.append("consumable_justified_by_survival")
            if option.kind == "defend":
                score += 65 if critical and not any(item.estimated_healing for item in options) else 5
                reasons.append("defensive_fallback")
            if option.kind == "flee":
                score += 100 if len(critical) >= 2 and not enemy_finishable else -30
                reasons.append("party_survival_escape_check")

            ranked.append(
                BattleRecommendation(
                    option=option,
                    score=round(score, 3),
                    reasons=tuple(reasons),
                    requires_tactical_reasoning=(
                        physical_bad or bool(critical) or bool(dead_allies) or len(alive_enemies) > 1
                    ),
                )
            )
        return sorted(ranked, key=lambda item: (-item.score, item.option.kind, item.option.name))
