import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from agent.perception import KeyframeObserver


def png_bytes(color=(20, 30, 40)):
    output = io.BytesIO()
    Image.new("RGB", (256, 224), color).save(output, format="PNG")
    return output.getvalue()


def event(index, outcome="blocked_now", x=10, y=10):
    return {
        "index": index,
        "outcome": outcome,
        "new_room": False,
        "source": f"05:{x},{y}",
        "target": f"05:{x},{y}",
        "direction": "north",
        "after": {"map_id": 5, "x": x, "y": y, "blocked_attempt": 0},
    }


class KeyframeObserverTests(unittest.TestCase):
    def test_queues_first_collision_and_throttles_near_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            observer = KeyframeObserver(Path(root), min_action_gap=4)
            first = observer.capture(event(1), png_bytes())
            second = observer.capture(event(2), png_bytes())
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertTrue(Path(first["image"]).exists())

    def test_open_move_is_not_a_visual_event(self):
        with tempfile.TemporaryDirectory() as root:
            observer = KeyframeObserver(Path(root))
            self.assertIsNone(observer.capture(event(1, outcome="open"), png_bytes()))


if __name__ == "__main__":
    unittest.main()
