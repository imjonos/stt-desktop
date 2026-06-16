import sys
import types
import unittest

from app.ai_client import AIClientConfig, OpenAIClient


class FakeChatCompletions:
    def create(self, **_kwargs):
        message = types.SimpleNamespace(content="processed")
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice])


class FakeOpenAI:
    calls = []

    def __init__(self, **kwargs):
        self.calls.append(kwargs)
        self.chat = types.SimpleNamespace(
            completions=FakeChatCompletions(),
        )


class OpenAIClientTest(unittest.TestCase):
    def setUp(self):
        FakeOpenAI.calls.clear()
        self.original_openai = sys.modules.get("openai")
        openai_module = types.ModuleType("openai")
        openai_module.OpenAI = FakeOpenAI
        sys.modules["openai"] = openai_module

    def tearDown(self):
        if self.original_openai is None:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = self.original_openai

    def test_uses_dummy_key_for_local_openai_compatible_base_url(self):
        client = OpenAIClient(
            AIClientConfig(
                provider="openai",
                api_key="",
                model="llama3",
                base_url="http://localhost:11434/v1",
            )
        )

        self.assertEqual(client.process_text("prompt", "text"), "processed")

        self.assertEqual(FakeOpenAI.calls[-1]["base_url"], "http://localhost:11434/v1")
        self.assertEqual(FakeOpenAI.calls[-1]["api_key"], "local-openai-compatible")

    def test_keeps_empty_key_unset_without_base_url(self):
        client = OpenAIClient(
            AIClientConfig(
                provider="openai",
                api_key="",
                model="gpt-4o-mini",
                base_url=None,
            )
        )

        self.assertEqual(client.process_text("prompt", "text"), "processed")

        self.assertNotIn("api_key", FakeOpenAI.calls[-1])
        self.assertNotIn("base_url", FakeOpenAI.calls[-1])


if __name__ == "__main__":
    unittest.main()
