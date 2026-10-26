"""Translation using Google Gemini API (free tier via Google AI Studio).

Get a free API key at: https://aistudio.google.com/apikey

Free tier limits (Gemini 2.0 Flash):
- 15 requests per minute
- 1 million tokens per day
- No credit card required
"""

from __future__ import annotations

import json
import logging
import threading

from comic_translator.config import TranslatorConfig
from comic_translator.exceptions import TranslationError
from comic_translator.translator.base import TranslationProvider, parse_json_response

logger = logging.getLogger(__name__)

# genai.configure() is process-global in google-generativeai; two job threads
# using different keys would race and one job's requests could be billed to
# the other's account. Serialize every configure+generate pair.
_gemini_global_lock = threading.Lock()

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]


class GeminiProvider(TranslationProvider):
    """Translate via Google Gemini API (free tier)."""

    def __init__(self, config: TranslatorConfig) -> None:
        self.config = config
        if not config.gemini_api_key:
            raise TranslationError(
                "Gemini API key not set. "
                "Get a free key at https://aistudio.google.com/apikey\n"
                "Set GEMINI_API_KEY env var or gemini.api_key in config.json"
            )

    def translate_batch(
        self,
        dialogs: dict[str, str],
        system_prompt: str,
        context: str = "",
    ) -> dict[str, str]:
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise TranslationError(
                "google-generativeai not installed. Run: pip install google-generativeai"
            ) from e

        try:
            genai.configure(api_key=self.config.gemini_api_key)
        except Exception as e:
            raise TranslationError(f"Failed to configure Gemini API: {e}") from e

        model_name = self.config.gemini_model or GEMINI_MODELS[0]

        user_prompt = self.config.user_prompt.replace(
            "{dialogs}", json.dumps(dialogs, ensure_ascii=False)
        )
        if context:
            user_prompt = f"{context}\n\n{user_prompt}"

        models_to_try = [model_name] + [
            m for m in GEMINI_MODELS if m != model_name
        ]

        last_error = ""
        # Hold the global lock across configure+generate: configure() rebinds
        # the process-wide client, so releasing between batches of concurrent
        # jobs would let one job's key be used for another's requests.
        with _gemini_global_lock:
            for m_name in models_to_try:
                try:
                    logger.info("Gemini: trying model=%s", m_name)
                    model = genai.GenerativeModel(
                        model_name=m_name,
                        system_instruction=system_prompt,
                    )
                    response = model.generate_content(
                        user_prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=self.config.temperature,
                        ),
                    )
                    if not hasattr(response, 'text') or not response.text:
                        raise TranslationError(f"Gemini returned empty response for model {m_name}")
                    raw = response.text
                    logger.info("Gemini: model=%s returned %d chars", m_name, len(raw))
                    return parse_json_response(raw, dialogs)

                except Exception as e:
                    last_error = str(e)[:200]
                    logger.warning("Gemini: model=%s failed: %s", m_name, last_error)

        raise TranslationError(
            f"Gemini translation failed. Last error: {last_error}\n"
            f"Check your API key and quota at https://aistudio.google.com/apikey"
        )



