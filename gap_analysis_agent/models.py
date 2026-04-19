from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import re


class Priority(str, Enum):
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"
    UNKNOWN = "unknown"


class GapType(str, Enum):
    UNADDRESSED = "unaddressed"
    SCOPE_MISMATCH = "scope_mismatch"
    IMPLICIT_ASSUMPTION = "implicit_assumption"
    AMBIGUITY = "ambiguity"


@dataclass
class Transcript:
    transcript_id: str
    source_type: str
    file_name: str
    text: str

    def to_prompt_block(self) -> str:
        return (
            f"Transcript ID: {self.transcript_id}\n"
            f"Source Type: {self.source_type}\n"
            f"File Name: {self.file_name}\n"
            f"Transcript:\n{self.text.strip()}"
        )


@dataclass
class Requirement:
    requirement_id: str
    transcript_id: str
    statement: str
    priority: str = Priority.UNKNOWN.value
    constraints: list[str] = field(default_factory=list)
    speaker: str = "unknown"
    source_excerpt: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Requirement":
        return cls(
            requirement_id=str(data.get("requirement_id", "")).strip(),
            transcript_id=str(data.get("transcript_id", "")).strip(),
            statement=str(data.get("statement", "")).strip(),
            priority=_normalize_priority(data.get("priority", Priority.UNKNOWN.value)),
            constraints=_coerce_string_list(data.get("constraints", []), split_sentences=True),
            speaker=str(data.get("speaker", "unknown")).strip() or "unknown",
            source_excerpt=str(data.get("source_excerpt", "")).strip(),
        )


@dataclass
class Solution:
    solution_id: str
    transcript_id: str
    statement: str
    related_requirement_refs: list[str] = field(default_factory=list)
    scope_limitations: list[str] = field(default_factory=list)
    tech_choices: list[str] = field(default_factory=list)
    deferred_items: list[str] = field(default_factory=list)
    speaker: str = "unknown"
    source_excerpt: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Solution":
        return cls(
            solution_id=str(data.get("solution_id", "")).strip(),
            transcript_id=str(data.get("transcript_id", "")).strip(),
            statement=str(data.get("statement", "")).strip(),
            related_requirement_refs=_coerce_string_list(data.get("related_requirement_refs", [])),
            scope_limitations=_coerce_string_list(data.get("scope_limitations", []), split_sentences=True),
            tech_choices=_coerce_string_list(data.get("tech_choices", [])),
            deferred_items=_coerce_string_list(data.get("deferred_items", []), split_sentences=True),
            speaker=str(data.get("speaker", "unknown")).strip() or "unknown",
            source_excerpt=str(data.get("source_excerpt", "")).strip(),
        )


@dataclass
class Gap:
    gap_id: str
    type: str
    requirement_refs: list[str] = field(default_factory=list)
    solution_refs: list[str] = field(default_factory=list)
    description: str = ""
    suggested_action: str = ""
    confidence: str = "medium"
    reasoning: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Gap":
        return cls(
            gap_id=str(data.get("gap_id", "")).strip(),
            type=_normalize_gap_type(data.get("type", GapType.UNADDRESSED.value)),
            requirement_refs=_coerce_string_list(data.get("requirement_refs", [])),
            solution_refs=_coerce_string_list(data.get("solution_refs", [])),
            description=str(data.get("description", "")).strip(),
            suggested_action=str(data.get("suggested_action", "")).strip(),
            confidence=str(data.get("confidence", "medium")).strip() or "medium",
            reasoning=str(data.get("reasoning", "")).strip(),
        )


@dataclass
class GapAnalysisResult:
    summary: str = ""
    gaps: list[Gap] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GapAnalysisResult":
        return cls(
            summary=str(data.get("summary", "")).strip(),
            gaps=[Gap.from_dict(item) for item in data.get("gaps", []) if isinstance(item, dict)],
        )


@dataclass
class GapReport:
    business_transcript_count: int
    engineering_transcript_count: int
    requirements: list[Requirement]
    solutions: list[Solution]
    gaps: list[Gap]
    warnings: list[str] = field(default_factory=list)
    summary: str = ""
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "business_transcript_count": self.business_transcript_count,
            "engineering_transcript_count": self.engineering_transcript_count,
            "summary": self.summary,
            "warnings": list(self.warnings),
            "requirements": serialize(self.requirements),
            "solutions": serialize(self.solutions),
            "gaps": serialize(self.gaps),
        }


def serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, tuple):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value


def _coerce_string_list(value: Any, *, split_sentences: bool = False) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
        if items and all(isinstance(item, str) and len(item) == 1 for item in items):
            raw_items = ["".join(items)]
        else:
            raw_items = [str(item) for item in items]
    else:
        raw_items = [str(value)]

    normalized: list[str] = []
    for item in raw_items:
        text = re.sub(r"\s+", " ", item).strip()
        if not text:
            continue
        if split_sentences:
            parts = [part.strip(" .") for part in re.split(r"[;\n]+", text) if part.strip(" .")]
            normalized.extend(parts or [text])
        else:
            normalized.append(text)
    return normalized


def _normalize_priority(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "must_have": Priority.MUST_HAVE.value,
        "must": Priority.MUST_HAVE.value,
        "required": Priority.MUST_HAVE.value,
        "high": Priority.MUST_HAVE.value,
        "nice_to_have": Priority.NICE_TO_HAVE.value,
        "nice": Priority.NICE_TO_HAVE.value,
        "optional": Priority.NICE_TO_HAVE.value,
        "unknown": Priority.UNKNOWN.value,
    }
    return aliases.get(normalized, normalized or Priority.UNKNOWN.value)


def _normalize_gap_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "unaddressed_requirement": GapType.UNADDRESSED.value,
        "unaddressed": GapType.UNADDRESSED.value,
        "scope_mismatch": GapType.SCOPE_MISMATCH.value,
        "implicit_assumption": GapType.IMPLICIT_ASSUMPTION.value,
        "ambiguity": GapType.AMBIGUITY.value,
    }
    if normalized in aliases:
        return aliases[normalized]
    if "scope" in normalized:
        return GapType.SCOPE_MISMATCH.value
    if "implicit" in normalized or "assumption" in normalized:
        return GapType.IMPLICIT_ASSUMPTION.value
    if "ambigu" in normalized:
        return GapType.AMBIGUITY.value
    if "unaddress" in normalized:
        return GapType.UNADDRESSED.value
    return normalized or GapType.UNADDRESSED.value
