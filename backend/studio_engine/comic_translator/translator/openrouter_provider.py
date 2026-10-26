"""Translation using OpenRouter API (via requests, no extra package needed)."""

from __future__ import annotations

import json
import logging
import time

import requests

from comic_translator.config import TranslatorConfig
from comic_translator.exceptions import TranslationError
from comic_translator.translator.base import TranslationProvider, parse_json_response

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Substrings that indicate non-chat models we should never pick as fallback
_NON_CHAT = ("safety", "lyria", "clip", "embed", "whisper", "tts", "rerank")

# Used when the live /models lookup is unreachable (flaky networks / proxies)
_STATIC_FREE_FALLBACKS = [
    "z-ai/glm-5.2:free",
    "minimax/minimax-m2.7:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
]


class OpenRouterProvider(TranslationProvider):
    """Translate via OpenRouter API using requests."""

    def __init__(self, config: TranslatorConfig) -> None:
        self.config = config
        self._free_models: list[str] | None = None
        if not config.openrouter_api_key:
            raise TranslationError(
                "OpenRouter API key not set. "
                "Set OPENROUTER_API_KEY env var or openrouter.api_key in config.json"
            )

    def _fetch_free_models(self) -> list[str]:
        """Fetch the current list of $0/$0 chat models from OpenRouter."""
        if self._free_models is not None:
            return self._free_models
        try:
            resp = None
            for attempt in range(2):
                try:
                    resp = requests.get(_MODELS_URL, timeout=20)
                    resp.raise_for_status()
                    break
                except requests.RequestException as e:
                    logger.warning("openrouter: models list attempt %d failed: %s",
                                   attempt + 1, str(e)[:120])
                    time.sleep(1)
            if resp is None or resp.status_code != 200:
                self._free_models = []
                return self._free_models
            out: list[str] = []
            for m in resp.json().get("data", []):
                mid = m.get("id", "")
                pricing = m.get("pricing", {})
                if pricing.get("prompt") == "0" and pricing.get("completion") == "0":
                    low = mid.lower()
                    if any(x in low for x in _NON_CHAT):
                        continue
                    out.append(mid)
            # Prefer well-known instruct families first for translation quality
            priority = ("deepseek", "qwen", "glm", "mistral", "llama", "gemma",
                        "nemotron", "minimax")
            out.sort(key=lambda x: next(
                (i for i, p in enumerate(priority) if p in x.lower()), len(priority)))
            self._free_models = out
            logger.info("openrouter: %d free models available", len(out))
        except Exception as e:
            logger.warning("openrouter: failed to list models: %s", e)
            self._free_models = []
        return self._free_models

    def _models_to_try(self) -> list[str]:
        models = [self.config.openrouter_model]
        live = self._fetch_free_models()
        pool = live if live else list(_STATIC_FREE_FALLBACKS)
        for m in pool:
            if m != self.config.openrouter_model:
                models.append(m)
            if len(models) >= 8:
                break
        return models

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

        headers = {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/comic-translator",
        }

        last_error = ""
        tried = 0
        for model in self._models_to_try():
            tried += 1
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.config.temperature,
            }
            try:
                resp = requests.post(
                    _OPENROUTER_URL, headers=headers, json=payload, timeout=90
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("openrouter: model=%s returned %d chars", model, len(content))
                result = parse_json_response(content, dialogs)
                if any(v.strip() for v in result.values()):
                    return result
                last_error = f"model {model} returned empty translations"
                logger.warning("openrouter: %s", last_error)
                continue

            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                body = e.response.text[:180] if e.response is not None else ""
                last_error = f"HTTP {status}: {body}"
                logger.warning("openrouter: model=%s failed (%s)", model, last_error)
                if status == 429:
                    delay = 2.0
                    try:
                        delay = float(e.response.headers.get("Retry-After", "2"))
                    except (TypeError, ValueError):
                        pass
                    time.sleep(min(delay, 10))
                continue

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"[:180]
                logger.warning("openrouter: model=%s error: %s", model, last_error)
                time.sleep(1)
                continue

        raise TranslationError(
            f"OpenRouter failed on {tried} models. Last error: {last_error}"
        )
