from __future__ import annotations

from .models import GapReport


def _gap_ref(value: list[str]) -> str:
    return ", ".join(value) if value else "None"


def render_markdown_report(report: GapReport) -> str:
    lines = [
        "# Gap Analysis Report",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Business transcripts: `{report.business_transcript_count}`",
        f"- Engineering transcripts: `{report.engineering_transcript_count}`",
    ]

    if report.summary:
        lines.extend(["", "## Summary", "", report.summary])

    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)

    lines.extend(["", "## Requirements", ""])
    if report.requirements:
        for item in report.requirements:
            lines.extend(
                [
                    f"### {item.requirement_id}",
                    f"- Statement: {item.statement}",
                    f"- Priority: {item.priority}",
                    f"- Transcript: {item.transcript_id}",
                    f"- Speaker: {item.speaker}",
                    f"- Constraints: {', '.join(item.constraints) if item.constraints else 'None'}",
                    "",
                ]
            )
    else:
        lines.append("No requirements extracted.")

    lines.extend(["", "## Solutions", ""])
    if report.solutions:
        for item in report.solutions:
            lines.extend(
                [
                    f"### {item.solution_id}",
                    f"- Statement: {item.statement}",
                    f"- Transcript: {item.transcript_id}",
                    f"- Speaker: {item.speaker}",
                    f"- Requirement Refs: {', '.join(item.related_requirement_refs) if item.related_requirement_refs else 'None'}",
                    f"- Tech Choices: {', '.join(item.tech_choices) if item.tech_choices else 'None'}",
                    f"- Scope Limitations: {', '.join(item.scope_limitations) if item.scope_limitations else 'None'}",
                    f"- Deferred Items: {', '.join(item.deferred_items) if item.deferred_items else 'None'}",
                    "",
                ]
            )
    else:
        lines.append("No solutions extracted.")

    lines.extend(["", "## Gaps", ""])
    if report.gaps:
        for item in report.gaps:
            lines.extend(
                [
                    f"### {item.gap_id}",
                    f"- gap_id: `{item.gap_id}`",
                    f"- type: `{item.type}`",
                    f"- requirement_ref: `{_gap_ref(item.requirement_refs)}`",
                    f"- solution_ref: `{_gap_ref(item.solution_refs)}`",
                    f'- description: "{item.description}"',
                    f'- suggested_action: "{item.suggested_action}"',
                    f"- confidence: `{item.confidence}`",
                    f'- reasoning: "{item.reasoning or "Not provided"}"',
                    "",
                ]
            )
    else:
        lines.append("No gaps identified.")

    return "\n".join(lines).strip() + "\n"
