from __future__ import annotations

import json


def extract_json_payload(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start_candidates = [idx for idx in (text.find("{"), text.find("[")) if idx != -1]
    if not start_candidates:
        raise ValueError("No JSON object or array found in model output.")

    start = min(start_candidates)
    object_end = text.rfind("}")
    array_end = text.rfind("]")
    end = max(object_end, array_end)
    if end == -1 or end < start:
        raise ValueError("JSON payload appears to be incomplete.")

    return text[start : end + 1]


def parse_json(raw_text: str):
    return json.loads(extract_json_payload(raw_text))
