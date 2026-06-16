from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AIClientConfig:
    """Конфигурация для AI клиента."""
    provider: str  # "gigachat", "openai"
    api_key: str
    model: str
    base_url: str | None = None  # Для OpenAI-совместимых API (Lamy и т.д.)


class AIClient(ABC):
    """Базовый класс для AI клиентов."""

    @abstractmethod
    def process_text(self, prompt: str, text: str) -> str:
        """Отправляет текст на обработку и возвращает результат."""
        pass


class GigaChatClient(AIClient):
    def __init__(self, config: AIClientConfig):
        self.config = config
        try:
            from gigachat import GigaChat
            from gigachat.models import Chat, Messages
            self._GigaChat = GigaChat
            self._Chat = Chat
            self._Messages = Messages
        except ImportError as e:
            raise ImportError("gigachat не установлен. Установите: pip install gigachat") from e

    def process_text(self, prompt: str, text: str) -> str:
        with self._GigaChat(credentials=self.config.api_key, verify_ssl_certs=False) as giga:
            chat = self._Chat(
                model=self.config.model,
                messages=[
                    self._Messages(role="system", content=prompt),
                    self._Messages(role="user", content=text),
                ]
            )
            response = giga.chat(chat)
            return response.choices[0].message.content.strip()


class OpenAIClient(AIClient):
    def __init__(self, config: AIClientConfig):
        self.config = config
        try:
            from openai import OpenAI
            self._OpenAI = OpenAI
        except ImportError as e:
            raise ImportError("openai не установлен. Установите: pip install openai") from e

    def process_text(self, prompt: str, text: str) -> str:
        client_kwargs: dict = {}
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url
        if self.config.api_key:
            client_kwargs["api_key"] = self.config.api_key
        elif self.config.base_url:
            # The OpenAI SDK requires a non-empty key even for local
            # OpenAI-compatible servers such as Ollama.
            client_kwargs["api_key"] = "local-openai-compatible"

        client = self._OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()


def create_ai_client(config: AIClientConfig) -> AIClient:
    """Фабрика для создания AI клиента по конфигурации."""
    provider = config.provider.lower().strip()
    if provider == "gigachat":
        return GigaChatClient(config)
    elif provider in ("openai", "lamy", "local"):
        return OpenAIClient(config)
    else:
        raise ValueError(f"Неизвестный AI провайдер: {provider}")
