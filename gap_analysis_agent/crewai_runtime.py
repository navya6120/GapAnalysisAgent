from __future__ import annotations

from importlib import import_module


def get_crewai_objects():
    try:
        crewai = import_module("crewai")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "CrewAI is not installed. Install project dependencies with `python -m pip install -r requirements.txt`."
        ) from exc

    return crewai.Agent, crewai.Task, crewai.Crew, crewai.Process
