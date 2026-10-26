"""Abstract translation provider interface."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


def parse_json_response(raw: str, original: dict[str, str]) -> dict[str, str]:
    """Parse JSON from LLM response, handling code blocks and common malformations.
    Falls back to regex extraction if full JSON parse fails."""
    if not raw:
        return {k: "" for k in original}

    m = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    elif raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"```$", "", raw)
        raw = raw.strip()

    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        raw = raw[brace_start : brace_end + 1]

    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            return {k: "" for k in original}
        for key in original:
            if key not in result:
                result[key] = ""
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    logger.warning("JSON parse failed, attempting regex partial recovery")
    pattern = r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"'
    matches = re.findall(pattern, raw)
    if matches:
        result = {k: v.replace('\\"', '"').replace("\\n", "\n") for k, v in matches}
        recovered = sum(1 for k in result if k in original)
        for key in original:
            if key not in result:
                result[key] = ""
        logger.warning("Partial recovery: %d/%d keys extracted", recovered, len(original))
        return result

    logger.error("All JSON parsing failed, returning empty results")
    return {k: "" for k in original}


class TranslationProvider(ABC):
    """Base class for translation providers."""

    @abstractmethod
    def translate_batch(
        self,
        dialogs: dict[str, str],
        system_prompt: str,
        context: str = "",
    ) -> dict[str, str]:
        """Translate a batch of dialog strings. Keys are preserved, values translated.
        Optional context provides page/conversation info for better translations."""
        ...
