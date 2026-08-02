import unittest
from unittest.mock import Mock, patch

from agent.model_client import LocalModelClient


def response(payload):
    result = Mock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    return result


class LocalModelClientTests(unittest.TestCase):
    def test_auto_detection_falls_through_to_llama_cpp(self):
        client = LocalModelClient({"provider": "auto", "probe_timeout_seconds": 0.1})
        with patch("agent.model_client.requests.get") as get:
            get.side_effect = [
                OSError("offline"),
                response({"data": [{"id": "local-vlm"}]}),
            ]
            resolved = client.detect()
        self.assertEqual(resolved["name"], "llama_cpp")
        self.assertEqual(resolved["model"], "local-vlm")

    def test_ollama_vision_payload_uses_images_field(self):
        client = LocalModelClient({
            "provider": "ollama",
            "vision_model": "gemma-vision",
            "providers": [{"name": "ollama", "base_url": "http://127.0.0.1:11434"}],
        })
        client._resolved = {
            "name": "ollama", "base_url": "http://127.0.0.1:11434", "model": "qwen-vl"
        }
        with patch("agent.model_client.requests.get") as get, patch("agent.model_client.requests.post") as post:
            get.return_value = response({"models": []})
            post.return_value = response({"message": {"content": "ok"}})
            result = client._chat([{"role": "user", "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
            ]}], role="vision")
        self.assertEqual(result, "ok")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "gemma-vision")
        self.assertFalse(post.call_args.kwargs["json"]["think"])
        message = post.call_args.kwargs["json"]["messages"][0]
        self.assertEqual(message["content"], "look")
        self.assertEqual(message["images"], ["QUJD"])

    def test_ollama_unloads_other_resident_model_before_chat(self):
        client = LocalModelClient({
            "resident_policy": "single",
            "planner_model": "planner",
            "planner_keep_alive": "2m",
        })
        client._resolved = {
            "name": "ollama", "base_url": "http://127.0.0.1:11434", "model": "planner"
        }
        with patch("agent.model_client.requests.get") as get, patch("agent.model_client.requests.post") as post:
            get.return_value = response({"models": [{"name": "vision"}]})
            post.side_effect = [
                response({}),
                response({"message": {"content": "ok"}}),
            ]
            client._chat([{"role": "user", "content": "go"}])
        self.assertEqual(post.call_args_list[0].args[0], "http://127.0.0.1:11434/api/generate")
        self.assertEqual(post.call_args_list[0].kwargs["json"], {"model": "vision", "keep_alive": 0})
        self.assertEqual(post.call_args_list[1].kwargs["json"]["keep_alive"], "2m")

    def test_ollama_accepts_schema_json_from_thinking_field(self):
        client = LocalModelClient({
            "provider": "ollama",
            "planner_model": "qwen3-vl:4b",
            "providers": [{"name": "ollama", "base_url": "http://127.0.0.1:11434"}],
        })
        client._resolved = {
            "name": "ollama", "base_url": "http://127.0.0.1:11434", "model": "qwen3-vl:4b"
        }
        with patch("agent.model_client.requests.get") as get, patch("agent.model_client.requests.post") as post:
            get.return_value = response({"models": []})
            post.return_value = response({
                "message": {"content": "", "thinking": '{"kind":"interact"}'}
            })
            result = client._chat([{"role": "user", "content": "go"}])
        self.assertEqual(result, '{"kind":"interact"}')

    def test_openai_compatible_chat_endpoint(self):
        client = LocalModelClient({})
        client._resolved = {
            "name": "koboldcpp", "base_url": "http://127.0.0.1:5001/v1", "model": "qwen"
        }
        with patch("agent.model_client.requests.post") as post:
            post.return_value = response({"choices": [{"message": {"content": " answer "}}]})
            result = client._chat([{"role": "user", "content": "go"}])
        self.assertEqual(result, "answer")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:5001/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
