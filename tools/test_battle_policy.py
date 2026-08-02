import unittest

from agent.battle import BattleOption, BattlePolicy, BattleState, CombatMemory
from agent.game_state import CHARACTER_BASE, CHARACTER_STRIDE


def put_u16(data, offset, value):
    data[offset] = value & 0xFF
    data[offset + 1] = value >> 8


def battle_state(party_hp=100, enemy_hp=500):
    data = bytearray(0x20000)
    data[0x09AA] = 1
    data[0x0A7B:0x0A7F] = bytes((2, 3, 1, 4))
    for identity in (2, 3, 1, 4):
        base = CHARACTER_BASE + identity * CHARACTER_STRIDE
        data[base + 0x11] = 99
        put_u16(data, base + 0x14, party_hp)
        put_u16(data, base + 0x16, 100)
        put_u16(data, base + 0x28, 400)
        put_u16(data, base + 0x2A, 200)
    enemy = 0x1618
    data[enemy + 0x53] = 0x54
    put_u16(data, enemy + 0x14, enemy_hp)
    put_u16(data, enemy + 0x28, 500)
    return BattleState.from_wram(bytes(data))


class BattlePolicyTests(unittest.TestCase):
    def test_critical_health_prefers_verified_heal(self):
        state = battle_state(party_hp=80, enemy_hp=500)
        options = [
            BattleOption("attack", 0, "Attack", 0x81, estimated_damage=100),
            BattleOption("spell", 0, "Champion", 0x0F, mp_cost=17, estimated_healing=999, all_targets=True),
        ]
        ranked = BattlePolicy().rank(state, 0, options)
        self.assertEqual(ranked[0].option.name, "Champion")

    def test_near_dead_enemy_prefers_finisher_when_no_heal_exists(self):
        state = battle_state(party_hp=80, enemy_hp=60)
        options = [
            BattleOption("attack", 0, "Attack", 0x81, estimated_damage=100),
            BattleOption("defend", 0, "Defend", 0),
        ]
        ranked = BattlePolicy().rank(state, 0, options)
        self.assertEqual(ranked[0].option.kind, "attack")
        self.assertIn("confirmed_finisher", ranked[0].reasons)

    def test_learned_physical_immunity_prefers_magic(self):
        state = battle_state(party_hp=300, enemy_hp=500)
        memory = CombatMemory()
        memory.record_damage(0x54, "attack", 0)
        memory.record_damage(0x54, "attack", 0)
        options = [
            BattleOption("attack", 0, "Attack", 0x81, estimated_damage=120),
            BattleOption("spell", 0, "Fireball", 0x81, mp_cost=6, estimated_damage=90, element="fire"),
        ]
        ranked = BattlePolicy().rank(state, 0, options, memory)
        self.assertEqual(ranked[0].option.name, "Fireball")

    def test_non_caster_with_ineffective_attack_can_defend_or_use_item(self):
        state = battle_state(party_hp=80, enemy_hp=500)
        memory = CombatMemory(physical_zero_hits={0x54: 2})
        options = [
            BattleOption("attack", 0, "Attack", 0x81, estimated_damage=100),
            BattleOption("defend", 0, "Defend", 0),
            BattleOption("item", 0, "Hi-Potion", 0x01, estimated_healing=90, consumes_item=True),
        ]
        ranked = BattlePolicy().rank(state, 0, options, memory)
        self.assertNotEqual(ranked[0].option.kind, "attack")


if __name__ == "__main__":
    unittest.main()
