from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import is_dataclass
from typing import Any

from .config import Settings
from .crewai_runtime import get_crewai_objects
from .models import serialize
from .specs import AgentSpec, TaskSpec


class _PromptState(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if is_dataclass(value) or isinstance(value, (dict, list, tuple)):
        return json.dumps(serialize(value), indent=2)
    return str(value)


class CrewComponentFactory:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()

    def create_agent(self, spec: AgentSpec):
        Agent, _, _, _ = get_crewai_objects()
        self.settings.prepare_runtime_environment()
        kwargs = {
            "role": spec.role,
            "goal": spec.goal,
            "backstory": spec.backstory,
            "allow_delegation": spec.allow_delegation,
            "verbose": self.settings.verbose or spec.verbose,
        }
        resolved_model = self.settings.resolved_model()
        if resolved_model:
            kwargs["llm"] = resolved_model
        return Agent(**kwargs)

    def create_task(self, spec: TaskSpec, agent: Any, state: Mapping[str, Any], context: list[Any] | None = None):
        _, Task, _, _ = get_crewai_objects()
        prompt_state = _PromptState({key: _stringify(value) for key, value in state.items()})
        return Task(
            description=spec.description_template.format_map(prompt_state),
            expected_output=spec.expected_output,
            agent=agent,
            context=context or [],
            markdown=spec.markdown,
        )
