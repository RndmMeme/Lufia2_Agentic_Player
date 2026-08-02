import unittest

from wram_discovery.extract_monster_action_names import (
    POINTER_COUNT,
    POINTER_TABLE_OFFSET,
    extract_action_names,
)


class ExtractMonsterActionNamesTests(unittest.TestCase):
    def test_extracts_control_prefixed_names(self):
        rom = bytearray(POINTER_TABLE_OFFSET + 0x400)
        string_offset = POINTER_TABLE_OFFSET + 0x220
        for action_id in range(POINTER_COUNT):
            pointer_pos = POINTER_TABLE_OFFSET + action_id * 2
            rom[pointer_pos : pointer_pos + 2] = (0x8220).to_bytes(2, "little")
        rom[string_offset : string_offset + 6] = b"\xE0Bite\x00"

        entries = extract_action_names(bytes(rom))

        self.assertEqual(len(entries), 256)
        self.assertEqual(entries[0]["name"], "Bite")
        self.assertEqual(entries[0]["rom_offset"], "280220")


if __name__ == "__main__":
    unittest.main()
