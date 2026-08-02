import time
import unittest

from agent.watchdog import DecisionWatchdog, ModelStallError


class DecisionWatchdogTests(unittest.TestCase):
    def test_barks_then_accepts_decision(self):
        barks = []
        watchdog = DecisionWatchdog(0.02, 0.02, 0.2)

        def operation():
            time.sleep(0.055)
            return "intent"

        result, elapsed = watchdog.run(operation, barks.append)
        self.assertEqual(result, "intent")
        self.assertGreaterEqual(elapsed, 0.02)
        self.assertTrue(barks)

    def test_stale_decision_is_discarded_without_joining_worker(self):
        watchdog = DecisionWatchdog(0.02, 0.02, 0.06)
        started = time.monotonic()
        with self.assertRaises(ModelStallError):
            watchdog.run(lambda: time.sleep(0.3), lambda _: None)
        self.assertLess(time.monotonic() - started, 0.2)


if __name__ == "__main__":
    unittest.main()
