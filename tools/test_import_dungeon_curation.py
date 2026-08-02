import csv
import tempfile
import unittest
from pathlib import Path

from tools.import_dungeon_curation import normalized_rows


class ImportDungeonCurationTests(unittest.TestCase):
    def test_normalizes_coordinate_and_accepts_conditional_object(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "curation.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "dungeon",
                        "coordinate",
                        "traversal",
                        "object",
                        "required_action",
                        "notes",
                    ]
                )
                writer.writerow(
                    [
                        "Secret_Skills_Cave",
                        "bk7",
                        "conditional",
                        "bush",
                        "sword",
                        "",
                    ]
                )
            rows = normalized_rows(path)
        self.assertEqual(rows[0]["coordinate"], "BK7")
        self.assertEqual(rows[0]["required_action"], "sword")


if __name__ == "__main__":
    unittest.main()
