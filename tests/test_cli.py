from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gap_analysis_agent.cli import _pair_key, _render_pairwise_reports
from gap_analysis_agent.models import GapReport


class FakePipeline:
    def run(self, business_transcripts, engineering_transcripts, warnings=None):
        return GapReport(
            business_transcript_count=len(business_transcripts),
            engineering_transcript_count=len(engineering_transcripts),
            requirements=[],
            solutions=[],
            gaps=[],
            warnings=warnings or [],
            summary="ok",
        )


class CliTests(unittest.TestCase):
    def test_pair_key_uses_numeric_suffix(self):
        self.assertEqual("001", _pair_key("BT-001"))
        self.assertEqual("123", _pair_key("ET_123"))

    def test_render_pairwise_reports_writes_one_report_per_matched_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            business_dir = root / "business"
            engineering_dir = root / "engineering"
            output_dir = root / "reports"
            business_dir.mkdir()
            engineering_dir.mkdir()

            (business_dir / "BT-002.txt").write_text("Business transcript", encoding="utf-8")
            (engineering_dir / "ET-002.txt").write_text("Engineering transcript", encoding="utf-8")

            count = _render_pairwise_reports(
                pipeline=FakePipeline(),
                business_dir=str(business_dir),
                engineering_dir=str(engineering_dir),
                output_dir=output_dir,
                output_format="markdown",
                logger=logging.getLogger("test"),
            )

            self.assertEqual(1, count)
            self.assertTrue((output_dir / "BT-002__ET-002.md").exists())


if __name__ == "__main__":
    unittest.main()
