from __future__ import annotations

import argparse
import logging
import re
from dataclasses import replace
from pathlib import Path

from .config import Settings
from .io import load_transcripts, write_report
from .pipeline import GapAnalysisPipeline


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CrewAI requirements gap analysis pipeline.")
    parser.add_argument("--business", required=True, help="Directory containing business transcript files.")
    parser.add_argument("--engineering", required=True, help="Directory containing engineering transcript files.")
    parser.add_argument("--output", help="Path for the generated report.")
    parser.add_argument(
        "--pairwise-output-dir",
        help="Optional directory for generating one report per matched BT/ET transcript pair.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the report file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose terminal logging while the pipeline runs.",
    )
    return parser


def _pair_key(transcript_id: str) -> str:
    match = re.search(r"(\d+)$", transcript_id)
    return match.group(1) if match else transcript_id


def _extension(output_format: str) -> str:
    return "md" if output_format == "markdown" else "json"


def _render_pairwise_reports(
    pipeline: GapAnalysisPipeline,
    business_dir: str,
    engineering_dir: str,
    output_dir: Path,
    output_format: str,
    logger: logging.Logger,
) -> int:
    business_transcripts, business_warnings = load_transcripts(business_dir, source_type="business")
    engineering_transcripts, engineering_warnings = load_transcripts(engineering_dir, source_type="engineering")

    business_by_pair = {_pair_key(item.transcript_id): item for item in business_transcripts}
    engineering_by_pair = {_pair_key(item.transcript_id): item for item in engineering_transcripts}

    unmatched_business = sorted(set(business_by_pair) - set(engineering_by_pair))
    unmatched_engineering = sorted(set(engineering_by_pair) - set(business_by_pair))
    for key in unmatched_business:
        logger.warning("No engineering transcript found for business pair %s", key)
    for key in unmatched_engineering:
        logger.warning("No business transcript found for engineering pair %s", key)

    matched_keys = sorted(set(business_by_pair) & set(engineering_by_pair))
    if not matched_keys:
        raise ValueError("No matching business/engineering transcript pairs were found.")

    output_dir.mkdir(parents=True, exist_ok=True)
    common_warnings = business_warnings + engineering_warnings
    report_count = 0

    for key in matched_keys:
        business = business_by_pair[key]
        engineering = engineering_by_pair[key]
        logger.info("Running pairwise report for %s and %s", business.transcript_id, engineering.transcript_id)
        report = pipeline.run(
            business_transcripts=[business],
            engineering_transcripts=[engineering],
            warnings=common_warnings,
        )
        output_path = output_dir / f"{business.transcript_id}__{engineering.transcript_id}.{_extension(output_format)}"
        write_report(report, output_path, output_format=output_format)
        logger.info("Pairwise report written to %s", output_path)
        report_count += 1

    return report_count


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.output and not args.pairwise_output_dir:
        parser.error("one of --output or --pairwise-output-dir is required")

    settings = Settings.from_env()
    if args.verbose:
        settings = replace(settings, verbose=True)

    configure_logging(verbose=settings.verbose)
    logger = logging.getLogger(__name__)
    logger.info("Starting gap analysis pipeline")
    logger.info("Business transcripts directory: %s", args.business)
    logger.info("Engineering transcripts directory: %s", args.engineering)

    pipeline = GapAnalysisPipeline(settings=settings)
    if args.pairwise_output_dir:
        report_count = _render_pairwise_reports(
            pipeline=pipeline,
            business_dir=args.business,
            engineering_dir=args.engineering,
            output_dir=Path(args.pairwise_output_dir),
            output_format=args.format,
            logger=logger,
        )
        print(f"Generated {report_count} pairwise report(s) in {args.pairwise_output_dir}")
        return 0

    report = pipeline.run_from_directories(args.business, args.engineering)

    output_path = write_report(report, Path(args.output), output_format=args.format)
    logger.info(
        "Pipeline completed with %s requirements, %s solutions, and %s gaps",
        len(report.requirements),
        len(report.solutions),
        len(report.gaps),
    )
    print(f"Gap report written to {output_path}")
    return 0
