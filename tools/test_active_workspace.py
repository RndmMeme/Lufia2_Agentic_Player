import unittest

from tools.audit_active_workspace import audit


class ActiveWorkspaceTests(unittest.TestCase):
    def test_active_workspace_has_no_legacy_runtime_dependencies(self):
        report = audit()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["dungeons"], 29)


if __name__ == "__main__":
    unittest.main()
