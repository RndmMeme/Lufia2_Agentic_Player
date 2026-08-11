import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import start_or_wait_model_server as starter


class ModelServerStarterTests(unittest.TestCase):
    @patch("tools.start_or_wait_model_server.urllib.request.urlopen")
    def test_endpoint_ready_accepts_success(self, urlopen):
        response = Mock(status=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        urlopen.return_value = response
        self.assertTrue(starter.endpoint_ready("http://127.0.0.1:8080/v1/models"))

    @patch("tools.start_or_wait_model_server.subprocess.run")
    def test_existing_llama_server_is_detected_case_insensitively(self, run):
        run.return_value = Mock(returncode=0, stdout='"llama-server.exe","123"')
        self.assertTrue(starter.llama_server_process_exists())

    @unittest.skipUnless(starter.os.name == "nt", "Windows-only detached launcher")
    @patch("tools.start_or_wait_model_server.subprocess.Popen")
    def test_detached_start_uses_single_configured_batch(self, popen):
        popen.return_value = Mock(pid=1234)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            batch = root / "model.bat"
            batch.write_text("@echo off\n", encoding="utf-8")
            pid = starter.start_detached(batch, root / "server.log")
        self.assertEqual(1234, pid)
        command = popen.call_args.args[0]
        self.assertEqual("/c", command[3])
        self.assertEqual(f'call "{batch}"', command[4])


if __name__ == "__main__":
    unittest.main()
