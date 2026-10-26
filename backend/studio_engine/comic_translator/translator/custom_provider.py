"""Translation using any OpenAI-compatible endpoint (custom base URL + key + model).

Works with one-api / new-api relays, LM Studio, Ollama, vLLM, or any service that
exposes an OpenAI-style ``/chat/completions`` endpoint.
"""

from __future__ import annotations

import json
import logging
import time

import requests

from comic_translator.config import TranslatorConfig
from comic_translator.exceptions import TranslationError
from comic_translator.translator.base import TranslationProvider, parse_json_response

logger = logging.getLogger(__name__)


class CustomProvider(TranslationProvider):
    """Translate via a user-defined OpenAI-compatible endpoint."""

    def __init__(self, config: TranslatorConfig) -> None:
        self.config = config
        if not config.custom_base_url:
            raise TranslationError(
                "Custom provider base URL not set. "
                "Set custom.base_url in Settings → Translator, "
                "or the CUSTOM_BASE_URL env var."
            )

    def _endpoint(self) -> str:
        base = self.config.custom_base_url.strip().rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def translate_batch(
        self,
        dialogs: dict[str, str],
        system_prompt: str,
        context: str = "",
    ) -> dict[str, str]:
        user_prompt = self.config.user_prompt.replace(
            "{dialogs}", json.dumps(dialogs, ensure_ascii=False)
        )
        if context:
            user_prompt = f"{context}\n\n{user_prompt}"

        endpoint = self._endpoint()
        headers = {"Content-Type": "application/json"}
        if self.config.custom_api_key:
            headers["Authorization"] = f"Bearer {self.config.custom_api_key}"

        payload = {
            "model": self.config.custom_model or "default",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
        }

        model = payload["model"]
        last_error = ""
        for attempt in range(3):
            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=90)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("custom: %s chars returned (attempt %d)", len(content), attempt + 1)
                result = parse_json_response(content, dialogs)
                if any(v.strip() for v in result.values()):
                    return result
                last_error = "empty translations returned"
                logger.warning("custom: attempt %d: %s", attempt + 1, last_error)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                body = e.response.text[:180] if e.response is not None else ""
                last_error = f"HTTP {status}: {body}"
                logger.warning("custom: attempt %d failed (%s)", attempt + 1, last_error)
                if status == 429:
                    time.sleep(min(float(
                        e.response.headers.get("Retry-After", "2")), 10))
                else:
                    time.sleep(1)
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"[:180]
                logger.warning("custom: attempt %d error: %s", attempt + 1, last_error)
                time.sleep(1)

        raise TranslationError(
            f"Custom provider failed after 3 attempts (model={model!r}). "
            f"Last error: {last_error}"
        )
