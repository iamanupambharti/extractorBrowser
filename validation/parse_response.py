"""
Parser for AI model responses.
Extracts JSON from raw response text, safely handling markdown fences and extraneous text
without modifying the raw response artifact.
"""
import json
import re
from typing import Tuple, Any, Optional

def extract_json_text(raw_text: str) -> str:
    """
    Extracts the JSON substring from raw response text.
    Handles ```json ... ``` markdown blocks, leading/trailing conversational text.
    """
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text.strip()

    # Pattern 1: Fenced code block ```json ... ``` or ``` ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
    matches = fence_pattern.findall(text)
    if matches:
        # Search from largest match or first valid-looking block
        for match in matches:
            candidate = match.strip()
            if (candidate.startswith("[") and candidate.endswith("]")) or (
                candidate.startswith("{") and candidate.endswith("}")
            ):
                return candidate
        # Fallback to the first match if it exists
        return matches[0].strip()

    # Pattern 2: Scan for outermost JSON array [ ... ]
    start_bracket = text.find("[")
    end_bracket = text.rfind("]")
    if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
        return text[start_bracket : end_bracket + 1].strip()

    # Pattern 3: Scan for outermost JSON object { ... }
    start_brace = text.find("{")
    end_brace = text.rfind("}")
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        return text[start_brace : end_brace + 1].strip()

    return text

def parse_raw_response(raw_text: str) -> Tuple[Optional[Any], Optional[str]]:
    """
    Parses a raw response text into Python objects.
    Returns:
        (parsed_object, None) on success
        (None, error_message) on failure
    """
    if not raw_text or not raw_text.strip():
        return None, "Empty response text"

    json_str = extract_json_text(raw_text)
    if not json_str:
        return None, "No JSON content found in response"

    try:
        data = json.loads(json_str)
        return data, None
    except json.JSONDecodeError as exc:
        # Try minor cleanup for common trailing commas before failing
        cleaned = re.sub(r",\s*([\]}])", r"\1", json_str)
        try:
            data = json.loads(cleaned)
            return data, None
        except Exception:
            return None, f"JSON parse error at line {exc.lineno}, col {exc.colno}: {exc.msg}"
