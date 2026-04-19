from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gap_analysis_agent.models import Gap


class ModelNormalizationTests(unittest.TestCase):
    def test_gap_type_normalization_collapses_nonstandard_labels(self):
        gap = Gap.from_dict(
            {
                "gap_id": "GAP-999",
                "type": "ambiguity_/_unaddressed_requirement",
                "requirement_refs": ["REQ-001"],
                "solution_refs": ["SOL-001"],
            }
        )

        self.assertEqual("ambiguity", gap.type)


if __name__ == "__main__":
    unittest.main()
