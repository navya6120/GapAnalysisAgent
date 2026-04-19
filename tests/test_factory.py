from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gap_analysis_agent.config import Settings
from gap_analysis_agent.factory import CrewComponentFactory
from gap_analysis_agent.specs import AgentSpec, TaskSpec


class FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeTask:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.original_crewai = sys.modules.get("crewai")
        fake_process = types.SimpleNamespace(sequential="sequential")
        sys.modules["crewai"] = types.SimpleNamespace(
            Agent=FakeAgent,
            Task=FakeTask,
            Crew=object,
            Process=fake_process,
        )

    def tearDown(self):
        if self.original_crewai is None:
            sys.modules.pop("crewai", None)
        else:
            sys.modules["crewai"] = self.original_crewai

    def test_factory_renders_state_without_repeating_boilerplate(self):
        factory = CrewComponentFactory(Settings(llm_model="gpt-test", verbose=False))
        agent = factory.create_agent(
            AgentSpec(
                key="requirements",
                role="Role",
                goal="Goal",
                backstory="Backstory",
            )
        )
        task = factory.create_task(
            TaskSpec(
                key="task",
                description_template="Use {business_transcripts} and {requirements_json}",
                expected_output="json",
            ),
            agent=agent,
            state={
                "business_transcripts": "BT content",
                "requirements_json": [{"id": "REQ-001"}],
            },
        )

        self.assertEqual("gpt-test", agent.kwargs["llm"])
        self.assertIn("BT content", task.kwargs["description"])
        self.assertIn('"REQ-001"', task.kwargs["description"])

    def test_factory_supports_azure_style_configuration(self):
        factory = CrewComponentFactory(
            Settings(
                llm_deployment="gap-analysis-deployment",
                api_key="secret",
                api_base="https://example.openai.azure.com/",
                api_version="2023-05-15",
                api_type="azure",
            )
        )

        agent = factory.create_agent(
            AgentSpec(
                key="gap",
                role="Role",
                goal="Goal",
                backstory="Backstory",
            )
        )

        self.assertEqual("azure/gap-analysis-deployment", agent.kwargs["llm"])


if __name__ == "__main__":
    unittest.main()
