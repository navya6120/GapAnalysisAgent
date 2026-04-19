from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import GapReport, Transcript


logger = logging.getLogger(__name__)


def load_transcripts(directory: str | Path, source_type: str) -> tuple[list[Transcript], list[str]]:
    path = Path(directory)
    warnings: list[str] = []

    if not path.exists():
        raise FileNotFoundError(f"Transcript directory does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Transcript path is not a directory: {path}")

    logger.info("Loading %s transcripts from %s", source_type, path)
    transcripts: list[Transcript] = []
    for file_path in sorted(item for item in path.iterdir() if item.is_file()):
        try:
            text = file_path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8-sig", errors="ignore").strip()
            warnings.append(f"Recovered non-standard encoding while reading {file_path.name}.")
            logger.warning("Recovered non-standard encoding while reading %s", file_path.name)
        except OSError as exc:
            warnings.append(f"Failed to read {file_path.name}: {exc}")
            logger.warning("Failed to read %s: %s", file_path.name, exc)
            continue

        if not text:
            warnings.append(f"Skipped empty transcript file: {file_path.name}")
            logger.warning("Skipped empty transcript file: %s", file_path.name)
            continue

        transcripts.append(
            Transcript(
                transcript_id=file_path.stem,
                source_type=source_type,
                file_name=file_path.name,
                text=text,
            )
        )
        logger.info("Loaded %s transcript: %s", source_type, file_path.name)

    logger.info("Finished loading %s transcripts: %s file(s)", source_type, len(transcripts))
    return transcripts, warnings


def format_transcripts_for_prompt(transcripts: list[Transcript]) -> str:
    return "\n\n---\n\n".join(item.to_prompt_block() for item in transcripts)


def write_report(report: GapReport, output_path: str | Path, output_format: str = "json") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Writing %s report to %s", output_format, path)

    if output_format == "json":
        path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    elif output_format == "markdown":
        from .reporting import render_markdown_report

        path.write_text(render_markdown_report(report), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    logger.info("Report written successfully to %s", path)
    return path
