"""Parse and validate LLM output for the semantic layer."""

import json
from typing import Any


class SemanticLayerOutputParser:
    """Parses the LLM response into a semantic-layer dictionary."""

    def parse(self, text: str) -> dict[str, Any]:
        """Parse generated text into a semantic-layer dictionary.

        Args:
            text: Raw text returned by the LLM.

        Returns:
            Parsed semantic-layer dictionary.

        Raises:
            ValueError: If the response is not valid JSON or is not
                a JSON object.
        """
        if not text or not text.strip():
            raise ValueError("LLM response cannot be empty.")

        cleaned_text = self._clean_response(text)

        try:
            parsed = json.loads(cleaned_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "LLM response is not valid JSON."
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError(
                "Semantic layer output must be a JSON object."
            )

        return parsed

    @staticmethod
    def _clean_response(text: str) -> str:
        """Remove common Markdown code fences from LLM output."""
        cleaned = text.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        return cleaned