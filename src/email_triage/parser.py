"""JSON extraction and validation helpers for LLM triage output."""

import json
import re

from pydantic import ValidationError

from email_triage.models import TriageResult

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


class TriageParseError(ValueError):
    """Raised when raw classifier output cannot be parsed into a TriageResult."""


def extract_json_object(raw_text: str) -> str:
    """Strip markdown code fences and isolate the outermost JSON object."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise TriageParseError("Classifier returned an empty response.")

    cleaned = raw_text.strip()
    fence_match = _CODE_FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    # Scan for the first balanced {...} JSON object if extra prose surrounds it.
    start_idx = cleaned.find("{")
    if start_idx == -1:
        raise TriageParseError("No JSON object found in classifier output.")

    depth = 0
    in_string = False
    escape_next = False
    for idx in range(start_idx, len(cleaned)):
        ch = cleaned[idx]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return cleaned[start_idx : idx + 1]

    raise TriageParseError("Unterminated JSON object in classifier output.")


def parse_triage_json(raw_text: str) -> TriageResult:
    """Parse raw model text into a validated TriageResult."""
    json_payload = extract_json_object(raw_text)
    try:
        parsed = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise TriageParseError(f"Invalid JSON from classifier: {exc}") from exc

    if not isinstance(parsed, dict):
        raise TriageParseError("Classifier JSON payload must be an object.")

    try:
        return TriageResult.model_validate(parsed)
    except ValidationError as exc:
        raise TriageParseError(f"Triage JSON failed schema validation: {exc}") from exc
