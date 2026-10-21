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

def repair_llm_json(s: str) -> str:
    """
    Cleans common LLM JSON formatting imperfections:
    - Trailing commas before closing brackets
    - Unescaped inner double quotes on string values
    - Duplicate leading quotes on values (e.g. "text": ""Language...)
    - Missing commas between adjacent objects
    """
    # 1. Clean trailing commas
    s = re.sub(r',\s*([\]}])', r'\1', s)
    
    # 2. Fix unescaped internal quotes and duplicate leading quotes line by line
    lines = s.splitlines()
    fixed_lines = []
    for line in lines:
        m = re.match(r'^(\s*"[^"]+"\s*:\s*)"(.*)"(\s*,?\s*)$', line)
        if m:
            prefix, content, suffix = m.group(1), m.group(2), m.group(3)
            # Remove duplicate leading quote
            if content.startswith('"'):
                content = content[1:]
            # Escape any unescaped double quotes inside content
            fixed_content = re.sub(r'(?<!\\)"', r'\\"', content)
            fixed_lines.append(f'{prefix}"{fixed_content}"{suffix}')
        else:
            fixed_lines.append(line)
            
    res = "\n".join(fixed_lines)
    # Clean trailing commas again
    res = re.sub(r',\s*([\]}])', r'\1', res)
    # Fix missing commas between closing brace and opening brace
    res = re.sub(r'}\s*\n\s*{', '},\n{', res)
    return res

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

    # Stage 1: Direct parse with strict=False
    first_err = ""
    try:
        data = json.loads(json_str, strict=False)
        return data, None
    except json.JSONDecodeError as exc:
        first_err = f"{exc.msg} at line {exc.lineno}, col {exc.colno}"

    # Stage 2: Automated LLM JSON repair
    try:
        repaired = repair_llm_json(json_str)
        data = json.loads(repaired, strict=False)
        return data, None
    except Exception:
        pass

    # Stage 3: Handle incomplete array truncation if closing bracket is missing
    trimmed = json_str.strip()
    if trimmed.startswith("[") and not trimmed.endswith("]"):
        try:
            patched = repair_llm_json(trimmed + "\n]")
            data = json.loads(patched, strict=False)
            return data, None
        except Exception:
            pass

    return None, f"JSON parse error: {first_err}"
