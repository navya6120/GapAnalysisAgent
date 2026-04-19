from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class AgentSpec:
    key: str
    role: str
    goal: str
    backstory: str
    allow_delegation: bool = False
    verbose: bool = False


@dataclass(frozen=True)
class TaskSpec:
    key: str
    description_template: str
    expected_output: str
    markdown: bool = False


@dataclass(frozen=True)
class StageSpec:
    key: str
    agent_key: str
    task_key: str
    output_key: str
    parser: Callable[[str], Any]
    context_stage_keys: tuple[str, ...] = field(default_factory=tuple)
