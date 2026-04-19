from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gap_analysis_agent.io import load_transcripts


class TranscriptLoaderTests(unittest.TestCase):
    def test_load_transcripts_skips_empty_files_and_collects_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "BT-001.txt").write_text("Business transcript", encoding="utf-8")
            (temp_path / "BT-002.txt").write_text("   ", encoding="utf-8")

            transcripts, warnings = load_transcripts(temp_path, source_type="business")

            self.assertEqual(1, len(transcripts))
            self.assertEqual("BT-001", transcripts[0].transcript_id)
            self.assertTrue(any("Skipped empty transcript file" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
