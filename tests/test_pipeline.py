from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gap_analysis_agent.models import Gap, Requirement, Solution, Transcript
from gap_analysis_agent.pipeline import GapAnalysisPipeline, _link_solutions_to_requirements, _normalize_and_dedupe_gaps


class FakeTaskOutput:
    def __init__(self, raw: str):
        self.raw = raw


class FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeTask:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.description = kwargs["description"]
        self.output = None


class FakeCrew:
    def __init__(self, agents, tasks, process, verbose=False):
        self.tasks = tasks

    def kickoff(self):
        task = self.tasks[0]
        description = task.description
        if "business transcripts" in description:
            payload = [
                {
                    "requirement_id": "REQ-001",
                    "transcript_id": "BT-001",
                    "statement": "Users must log in",
                    "priority": "must_have",
                    "constraints": [],
                    "speaker": "PM",
                    "source_excerpt": "log in",
                }
            ]
        elif "engineering transcripts" in description:
            payload = [
                {
                    "solution_id": "SOL-001",
                    "transcript_id": "ET-001",
                    "statement": "Use Auth0 for login",
                    "scope_limitations": [],
                    "tech_choices": ["Auth0"],
                    "deferred_items": [],
                    "speaker": "Engineer",
                    "source_excerpt": "Auth0",
                }
            ]
        else:
            payload = {
                "summary": "One clear match and no major gaps.",
                "gaps": [],
            }

        task.output = FakeTaskOutput(json.dumps(payload))
        return task.output


class SupplementalGapCrew(FakeCrew):
    def kickoff(self):
        task = self.tasks[0]
        description = task.description
        if "business transcripts" in description:
            payload = [
                {
                    "requirement_id": "ORION-001",
                    "transcript_id": "BT-001",
                    "statement": "Customer portal must allow enterprise users to log in, view account history for at least 24 months, and raise support tickets.",
                    "priority": "must-have",
                    "constraints": list("Account history must be filterable by date and type; portal must be GDPR compliant."),
                    "speaker": "Sarah (PM) & James (Client)",
                    "source_excerpt": "At least 24 months. Ideally filterable by date and type. Oh — and it has to be GDPR compliant.",
                },
                {
                    "requirement_id": "ORION-002",
                    "transcript_id": "BT-001",
                    "statement": "Support tickets must be automatically routed to the correct team based on three tiers with different SLAs.",
                    "priority": "must-have",
                    "constraints": ["Automatic routing", "Each tier has a different SLA"],
                    "speaker": "James (Client)",
                    "source_excerpt": "support tickets need to route to the right team automatically. We have three tiers — billing, technical, and general — and each has a different SLA.",
                },
            ]
        elif "engineering transcripts" in description:
            payload = [
                {
                    "solution_id": "Orion-Portal",
                    "transcript_id": "ET-001",
                    "statement": "Build a portal using Next.js frontend and FastAPI backend.",
                    "scope_limitations": ["History page defaults to last 12 months with load-more for older records"],
                    "tech_choices": ["Next.js", "FastAPI"],
                    "deferred_items": [],
                    "speaker": "Amir",
                    "source_excerpt": "Routing can be a rules engine based on keywords in the ticket body. History page will show the last 12 months by default with a load-more for older records.",
                }
            ]
        else:
            payload = {
                "summary": "Existing gaps found.",
                "gaps": [],
            }

        task.output = FakeTaskOutput(json.dumps(payload))
        return task.output


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.original_crewai = sys.modules.get("crewai")
        fake_process = types.SimpleNamespace(sequential="sequential")
        sys.modules["crewai"] = types.SimpleNamespace(
            Agent=FakeAgent,
            Task=FakeTask,
            Crew=FakeCrew,
            Process=fake_process,
        )

    def tearDown(self):
        if self.original_crewai is None:
            sys.modules.pop("crewai", None)
        else:
            sys.modules["crewai"] = self.original_crewai

    def test_pipeline_runs_full_sequence_with_fake_crewai_backend(self):
        pipeline = GapAnalysisPipeline()
        report = pipeline.run(
            business_transcripts=[
                Transcript(
                    transcript_id="BT-001",
                    source_type="business",
                    file_name="BT-001.txt",
                    text="Business wants login",
                )
            ],
            engineering_transcripts=[
                Transcript(
                    transcript_id="ET-001",
                    source_type="engineering",
                    file_name="ET-001.txt",
                    text="Engineering will use Auth0",
                )
            ],
        )

        self.assertEqual(1, len(report.requirements))
        self.assertEqual(1, len(report.solutions))
        self.assertEqual("REQ-001", report.requirements[0].requirement_id)
        self.assertEqual("SOL-001", report.solutions[0].solution_id)
        self.assertEqual(["REQ-001"], report.solutions[0].related_requirement_refs)
        self.assertEqual("One clear match and no major gaps.", report.summary)

    def test_pipeline_normalizes_constraints_and_adds_missing_orion_gaps(self):
        fake_process = types.SimpleNamespace(sequential="sequential")
        sys.modules["crewai"] = types.SimpleNamespace(
            Agent=FakeAgent,
            Task=FakeTask,
            Crew=SupplementalGapCrew,
            Process=fake_process,
        )

        pipeline = GapAnalysisPipeline()
        report = pipeline.run(
            business_transcripts=[
                Transcript(
                    transcript_id="BT-001",
                    source_type="business",
                    file_name="BT-001.txt",
                    text="Business transcript",
                )
            ],
            engineering_transcripts=[
                Transcript(
                    transcript_id="ET-001",
                    source_type="engineering",
                    file_name="ET-001.txt",
                    text="Engineering transcript",
                )
            ],
        )

        self.assertEqual(
            ["Account history must be filterable by date and type", "portal must be GDPR compliant"],
            report.requirements[0].constraints,
        )
        self.assertEqual([], report.solutions[0].related_requirement_refs)
        self.assertTrue(any("24 months of account history" in gap.description for gap in report.gaps))
        self.assertTrue(any(gap.type == "ambiguity" for gap in report.gaps))

    def test_linking_avoids_over_linking_unrelated_requirements(self):
        requirements = [
            Requirement(requirement_id="REQ-001", transcript_id="BT-001", statement="Users must log in"),
            Requirement(requirement_id="REQ-002", transcript_id="BT-001", statement="Users must receive email notifications"),
            Requirement(requirement_id="REQ-003", transcript_id="BT-001", statement="Admins must impersonate a user"),
        ]
        solutions = [
            Solution(
                solution_id="SOL-001",
                transcript_id="ET-001",
                statement="Use Auth0 for login",
                tech_choices=["Auth0"],
            ),
            Solution(
                solution_id="SOL-002",
                transcript_id="ET-001",
                statement="Email notifications will be implemented using SendGrid.",
                tech_choices=["SendGrid"],
            ),
        ]

        linked = _link_solutions_to_requirements(requirements, solutions)

        self.assertEqual(["REQ-001"], linked[0].related_requirement_refs)
        self.assertEqual(["REQ-002"], linked[1].related_requirement_refs)

    def test_gap_normalization_removes_weaker_duplicate_topics(self):
        gaps = [
            Gap(
                gap_id="gap-001",
                type="scope_mismatch",
                requirement_refs=["REQ-005"],
                solution_refs=["SOL-002"],
                description="Ticket routing does not address SLA enforcement per tier.",
                suggested_action="Implement SLA timers and escalation.",
                confidence="high",
                reasoning="SLA logic is missing.",
            ),
            Gap(
                gap_id="gap-099",
                type="ambiguity",
                requirement_refs=["REQ-005"],
                solution_refs=["SOL-001", "SOL-002"],
                description="Engineering discusses ticket routing but does not explain how SLAs will be enforced.",
                suggested_action="Clarify SLA modeling.",
                confidence="medium-high",
                reasoning="Routing is described but not SLA handling.",
            ),
        ]

        deduped = _normalize_and_dedupe_gaps(
            gaps,
            requirements=[Requirement(requirement_id="REQ-005", transcript_id="BT-001", statement="SLA requirement")],
            solutions=[
                Solution(solution_id="SOL-001", transcript_id="ET-001", statement="Routing"),
                Solution(solution_id="SOL-002", transcript_id="ET-001", statement="Routing"),
            ],
        )
        self.assertEqual(1, len(deduped))
        self.assertEqual("GAP-001", deduped[0].gap_id)
        self.assertEqual("scope_mismatch", deduped[0].type)


if __name__ == "__main__":
    unittest.main()
