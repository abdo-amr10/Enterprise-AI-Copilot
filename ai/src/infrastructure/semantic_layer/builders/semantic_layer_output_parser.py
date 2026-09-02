"""Parse and validate LLM output for the semantic layer."""

import json
import re
from typing import Any


class SemanticLayerOutputParser:
    """Parses the LLM response into a semantic-layer dictionary with robust recovery."""

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

        parsed = self._try_parse_robust(text)
        if parsed is not None:
            if isinstance(parsed, dict):
                parsed = self._unwrap_semantic_dict(parsed)
            if not isinstance(parsed, dict):
                raise ValueError("Semantic layer output must be a JSON object.")
            return parsed

        raise ValueError("LLM response is not valid JSON.")

    def _unwrap_semantic_dict(self, parsed: Any) -> dict[str, Any]:
        """Unwrap common LLM response envelopes (e.g. {'response': {...}}, {'draft': {...}})."""
        if not isinstance(parsed, dict):
            return parsed

        # If parsed itself has core semantic keys, return it
        core_keys = {"entities", "relationships", "measures", "dimensions", "tables"}
        if any(k in parsed for k in core_keys):
            return parsed

        # Check common wrapper keys
        wrapper_keys = ["response", "semantic_layer", "semanticLayer", "draft", "data", "result", "output"]
        for key in wrapper_keys:
            if key in parsed:
                inner = parsed[key]
                if isinstance(inner, dict):
                    return self._unwrap_semantic_dict(inner)
                elif isinstance(inner, str):
                    try:
                        inner_parsed = json.loads(inner)
                        if isinstance(inner_parsed, dict):
                            return self._unwrap_semantic_dict(inner_parsed)
                    except Exception:
                        pass

        return parsed

    def _try_parse_robust(self, text: str) -> Any:
        cleaned = text.strip()

        # Strategy 1: Direct parse
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        # Strategy 2: Extract from markdown code fences
        fence_extracted = self._extract_from_fences(cleaned)
        if fence_extracted:
            try:
                return json.loads(fence_extracted)
            except Exception:
                pass
            cleaned = fence_extracted

        # Strategy 3: Normalize common LLM syntax defects (comments, trailing commas, python literals)
        normalized = self._normalize_json_syntax(cleaned)
        try:
            return json.loads(normalized)
        except Exception:
            pass

        # Strategy 4: Fix single quotes
        sq_fixed = self._fix_single_quotes(normalized)
        try:
            return json.loads(sq_fixed)
        except Exception:
            pass

        # Strategy 5: Extract outermost balanced JSON or largest candidate
        candidate = self._extract_outermost_json(cleaned)
        if candidate and candidate != cleaned:
            try:
                return json.loads(candidate)
            except Exception:
                cand_norm = self._normalize_json_syntax(candidate)
                try:
                    return json.loads(cand_norm)
                except Exception:
                    pass

        # Strategy 6: Repair truncated / unclosed JSON
        for text_variant in (normalized, sq_fixed, cleaned):
            repaired = self._repair_truncated_json(text_variant)
            if repaired:
                try:
                    return json.loads(repaired)
                except Exception:
                    pass

        return None

    @staticmethod
    def _extract_from_fences(text: str) -> str | None:
        fence_match = re.search(
            r"```(?:json|json5|javascript)?\s*([\s\S]*?)(?:```|$)",
            text,
            re.IGNORECASE,
        )
        if fence_match:
            candidate = fence_match.group(1).strip()
            if candidate:
                return candidate
        return None

    @staticmethod
    def _extract_outermost_json(text: str) -> str | None:
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            return text[first_brace : last_brace + 1].strip()
        return None

    @staticmethod
    def _normalize_json_syntax(text: str) -> str:
        # Strip block comments /* ... */
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", text)

        # Strip line comments // ... outside string literals
        lines = []
        for line in cleaned.splitlines():
            stripped_line = re.sub(r"(?<!:)\/\/.*$", "", line)
            lines.append(stripped_line)
        cleaned = "\n".join(lines)

        # Replace Python literals with JSON equivalents
        cleaned = re.sub(r"\bTrue\b", "true", cleaned)
        cleaned = re.sub(r"\bFalse\b", "false", cleaned)
        cleaned = re.sub(r"\bNone\b", "null", cleaned)

        # Remove trailing commas before } or ]
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return cleaned.strip()

    @staticmethod
    def _fix_single_quotes(text: str) -> str:
        def repl(match: re.Match) -> str:
            inner = match.group(1).replace('"', '\\"')
            return f'"{inner}"'

        return re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", repl, text)

    @staticmethod
    def _repair_truncated_json(text: str) -> str | None:
        s = text.strip()
        if not s:
            return None

        first_brace = s.find("{")
        if first_brace == -1:
            return None
        s = s[first_brace:]

        stack = []
        in_string = False
        escape = False

        for char in s:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char in "{[":
                    stack.append("}" if char == "{" else "]")
                elif char in "}]":
                    if stack and stack[-1] == char:
                        stack.pop()

        if in_string:
            s += '"'

        s = re.sub(r",\s*$", "", s)
        s = re.sub(r":\s*$", ': ""', s)
        s = re.sub(r",\s*([}\]])", r"\1", s)

        while stack:
            closing = stack.pop()
            s = re.sub(r",\s*$", "", s)
            s += closing

        return s