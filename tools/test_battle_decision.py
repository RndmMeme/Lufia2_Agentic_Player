import unittest

from agent.battle import BattleDecision, BattleOption


class BattleDecisionTests(unittest.TestCase):
    def test_llm_must_choose_offered_option_id(self):
        options = [BattleOption("attack", 0, "Attack", 0x81, option_id="guy_attack_enemy_1")]
        decision = BattleDecision.from_dict(
            {
                "option_id": "guy_attack_enemy_1",
                "rationale": "Finish the weakened enemy.",
                "risk_assessment": "Enemy may act first.",
                "contingency": "Heal next command phase if the attack misses.",
            },
            options,
        )
        self.assertEqual(decision.option_id, "guy_attack_enemy_1")

    def test_rejects_invented_option(self):
        options = [BattleOption("defend", 0, "Defend", 0, option_id="guy_defend")]
        with self.assertRaises(ValueError):
            BattleDecision.from_dict(
                {
                    "option_id": "cast_unlearned_spell",
                    "rationale": "Invented.",
                    "risk_assessment": "Unknown.",
                    "contingency": "None.",
                },
                options,
            )


if __name__ == "__main__":
    unittest.main()
