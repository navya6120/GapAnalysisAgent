from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gap_analysis_agent.models import Gap, GapReport, Solution
from gap_analysis_agent.reporting import render_markdown_report


class ReportingTests(unittest.TestCase):
    def test_render_markdown_report_formats_gap_entries_as_markdown_list(self):
        report = GapReport(
            business_transcript_count=1,
            engineering_transcript_count=1,
            requirements=[],
            solutions=[
                Solution(
                    solution_id="SOL-003",
                    transcript_id="ET-001",
                    statement="History page shows last 12 months.",
                    related_requirement_refs=["REQ-004"],
                )
            ],
            gaps=[
                Gap(
                    gap_id="GAP-001",
                    type="scope_mismatch",
                    requirement_refs=["REQ-004"],
                    solution_refs=["SOL-003"],
                    description="Business requires 24 months.",
                    suggested_action="Add filtering to scope.",
                    confidence="high",
                    reasoning="Engineering only mentions 12 months.",
                )
            ],
        )

        rendered = render_markdown_report(report)

        self.assertIn("- Requirement Refs: REQ-004", rendered)
        self.assertIn("### GAP-001", rendered)
        self.assertIn("- gap_id: `GAP-001`", rendered)
        self.assertIn("- type: `scope_mismatch`", rendered)
        self.assertIn("- requirement_ref: `REQ-004`", rendered)
        self.assertIn("- solution_ref: `SOL-003`", rendered)
        self.assertIn('- description: "Business requires 24 months."', rendered)


if __name__ == "__main__":
    unittest.main()
