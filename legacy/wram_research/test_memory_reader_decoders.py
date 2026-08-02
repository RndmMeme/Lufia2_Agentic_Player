import unittest

from emulator.memory_reader import _decode_battle_target_mask, _decode_combat_status


class MemoryReaderDecoderTests(unittest.TestCase):
    def test_party_and_enemy_target_masks(self):
        party = _decode_battle_target_mask(0x0F)
        enemies = _decode_battle_target_mask(0x87)
        capsule = _decode_battle_target_mask(0x10)

        self.assertEqual(party["side"], "party")
        self.assertEqual(party["indices"], [0, 1, 2, 3])
        self.assertTrue(party["is_multi_target"])
        self.assertEqual(enemies["side"], "enemy")
        self.assertEqual(enemies["indices"], [0, 1, 2])
        self.assertTrue(enemies["is_multi_target"])
        self.assertEqual(capsule["indices"], [4])
        self.assertEqual(capsule["target_labels"], ["capsule"])

    def test_combat_status_bits_are_composable(self):
        self.assertEqual(
            _decode_combat_status(0x2C),
            ["disabled", "paralyze", "sleep"],
        )


if __name__ == "__main__":
    unittest.main()
