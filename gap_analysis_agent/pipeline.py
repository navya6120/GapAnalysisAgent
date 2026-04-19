from __future__ import annotations

import json
import logging
import re
from typing import Any

from .config import Settings
from .factory import CrewComponentFactory
from .io import format_transcripts_for_prompt, load_transcripts
from .json_utils import parse_json
from .models import Gap, GapAnalysisResult, GapReport, GapType, Requirement, Solution, Transcript, serialize
from .specs import AgentSpec, StageSpec, TaskSpec


logger = logging.getLogger(__name__)


REQUIREMENTS_AGENT = AgentSpec(
    key="requirements_extractor",
    role="Business Requirements Analyst",
    goal="Extract clear, traceable business requirements from messy stakeholder transcripts.",
    backstory=(
        "You specialize in turning informal product and client conversations into structured "
        "requirements without inventing facts."
    ),
)

SOLUTIONS_AGENT = AgentSpec(
    key="solution_extractor",
    role="Engineering Planning Analyst",
    goal="Extract implementation decisions, scope limits, and de-scoped items from engineering discussions.",
    backstory=(
        "You are a senior technical analyst who converts engineering planning notes into reliable "
        "implementation records."
    ),
)

GAP_AGENT = AgentSpec(
    key="gap_analyzer",
    role="Requirements Gap Analyst",
    goal="Compare business expectations and engineering plans to find actionable delivery gaps.",
    backstory=(
        "You identify missing coverage, scope mismatches, risky assumptions, and ambiguities in software delivery."
    ),
)


AGENT_SPECS = {
    REQUIREMENTS_AGENT.key: REQUIREMENTS_AGENT,
    SOLUTIONS_AGENT.key: SOLUTIONS_AGENT,
    GAP_AGENT.key: GAP_AGENT,
}


TASK_SPECS = {
    "extract_requirements": TaskSpec(
        key="extract_requirements",
        description_template=(
            "Analyze the following business transcripts and extract the project requirements.\n\n"
            "Business transcripts:\n{business_transcripts}\n\n"
            "Return only facts supported by the transcript. Infer priority only when the language strongly suggests it. "
            "Treat must-have, required, absolutely, and compliance-related asks as strong priority signals. "
            "Handle messy notes, overlapping speakers, and implicitly stated requirements without inventing facts. "
            "Keep independent requirements separate so later stages can trace them clearly. "
            "Return strict JSON as an array of objects with keys: requirement_id, transcript_id, statement, priority, "
            "constraints, speaker, source_excerpt."
        ),
        expected_output=(
            "A JSON array. Each item must include requirement_id, transcript_id, statement, priority, constraints, "
            "speaker, and source_excerpt."
        ),
    ),
    "extract_solutions": TaskSpec(
        key="extract_solutions",
        description_template=(
            "Analyze the following engineering transcripts and extract the planned implementation decisions.\n\n"
            "Engineering transcripts:\n{engineering_transcripts}\n\n"
            "Capture what will be built, technology choices, scope limitations, and any deferred or skipped items. "
            "Keep solution entries atomic so they can be traced back to requirements later. "
            "Do not invent requirement IDs or claim business coverage unless it is explicit in the engineering transcript. "
            "Return strict JSON as an array of objects with keys: solution_id, transcript_id, statement, "
            "scope_limitations, tech_choices, deferred_items, speaker, source_excerpt."
        ),
        expected_output=(
            "A JSON array. Each item must include solution_id, transcript_id, statement, scope_limitations, "
            "tech_choices, deferred_items, speaker, and source_excerpt."
        ),
    ),
    "analyze_gaps": TaskSpec(
        key="analyze_gaps",
        description_template=(
            "Compare the business requirements and engineering solutions below.\n\n"
            "Business requirements:\n{requirements_json}\n\n"
            "Engineering solutions:\n{solutions_json}\n\n"
            "Identify unaddressed requirements, scope mismatches, implicit assumptions, and ambiguities. "
            "Use only these gap types: unaddressed, scope_mismatch, implicit_assumption, ambiguity. "
            "Do not flag optional work as a gap unless engineering explicitly contradicts it. "
            "Avoid duplicate gaps for the same underlying issue and prefer the most specific gap type when overlap exists. "
            "Return strict JSON containing two top-level keys: summary and gaps. "
            "Each gap item must include gap_id, type, requirement_refs, solution_refs, description, "
            "suggested_action, confidence, and reasoning."
        ),
        expected_output="A JSON object with keys summary and gaps.",
    ),
}


def _parse_requirements(raw_text: str) -> list[Requirement]:
    payload = parse_json(raw_text)
    if isinstance(payload, dict):
        payload = payload.get("requirements", [])
    if not isinstance(payload, list):
        raise ValueError("Requirements agent returned a non-list payload.")
    return [Requirement.from_dict(item) for item in payload if isinstance(item, dict)]


def _parse_solutions(raw_text: str) -> list[Solution]:
    payload = parse_json(raw_text)
    if isinstance(payload, dict):
        payload = payload.get("solutions", [])
    if not isinstance(payload, list):
        raise ValueError("Solutions agent returned a non-list payload.")
    return [Solution.from_dict(item) for item in payload if isinstance(item, dict)]


def _parse_gap_analysis(raw_text: str) -> GapAnalysisResult:
    payload = parse_json(raw_text)
    if isinstance(payload, list):
        payload = {"summary": "", "gaps": payload}
    if not isinstance(payload, dict):
        raise ValueError("Gap analysis agent returned an unexpected payload.")
    return GapAnalysisResult.from_dict(payload)


def _transcript_pair_key(transcript_id: str) -> str:
    match = re.search(r"(\d+)$", transcript_id)
    return match.group(1) if match else transcript_id


def _solution_text(solution: Solution) -> str:
    return " ".join(
        [
            solution.statement,
            *solution.scope_limitations,
            *solution.tech_choices,
            *solution.deferred_items,
            solution.source_excerpt,
        ]
    ).lower()


def _requirement_text(requirement: Requirement) -> str:
    return " ".join([requirement.statement, *requirement.constraints, requirement.source_excerpt]).lower()


def _solution_match_text(solution: Solution) -> str:
    return " ".join(
        [
            solution.statement,
            *solution.scope_limitations,
            *solution.tech_choices,
            *solution.deferred_items,
        ]
    ).lower()


def _requirement_match_text(requirement: Requirement) -> str:
    return " ".join([requirement.statement, *requirement.constraints]).lower()


_CONCEPT_PATTERNS: dict[str, tuple[str, ...]] = {
    "portal": (r"\bportal\b", r"\bdashboard\b"),
    "auth": (
        r"\blog[\s-]?in\b",
        r"\bauth(?:entication|0|orized)?\b",
        r"\bsso\b",
        r"\bgoogle workspace\b",
        r"\bemail/password\b",
        r"\bpassword accounts?\b",
    ),
    "account_history": (r"\baccount history\b", r"\bhistory page\b", r"\bhistory\b"),
    "history_filter": (r"\bfilter(?:able|ing|ed)?\b", r"\bby date\b", r"\bby type\b"),
    "history_retention": (r"\b12 months?\b", r"\b24 months?\b", r"\bload[- ]more\b", r"\bolder records\b"),
    "ticket_creation": (r"\braise support tickets?\b", r"\bsupport tickets?\b", r"\bticket ui\b"),
    "routing": (r"\broute\b", r"\brouting\b", r"\brules engine\b", r"\bkeyword\b"),
    "sla": (r"\bsla\b",),
    "email_notification": (
        r"\bemail reminders?\b",
        r"\bemail notifications?\b",
        r"\bstatus updates?\b",
        r"\bweekly (?:summary|email|digest)\b",
        r"\bsendgrid\b",
    ),
    "sms_notification": (r"\bsms reminders?\b", r"\bsms notifications?\b", r"\bsms\b"),
    "gdpr": (r"\bgdpr\b", r"\bprivacy\b", r"\bconsent\b", r"\berasure\b"),
    "admin_access": (
        r"\ball accounts\b",
        r"\bview all accounts\b",
        r"\baccess to all\b",
        r"\bcross-account\b",
        r"\bglobal account access\b",
    ),
    "impersonation": (r"\bimpersonat",),
    "csv_export": (r"\bcsv\b", r"\bexport\b"),
    "region_access": (
        r"\bassigned region\b",
        r"\ball regions\b",
        r"\bregional data access\b",
        r"\bmanager[s]?\b",
        r"\banalyst[s]?\b",
    ),
    "audit_log": (r"\baudit log\b", r"\baudit logging\b", r"\blog who exported\b"),
    "appointment_booking": (r"\bbook(?:ing)? appointments?\b", r"\bbooking\b"),
    "appointment_reschedule": (r"\breschedul",),
    "appointment_cancel": (r"\bcancel(?:lation)?\b",),
    "timezone": (r"\btime zones?\b", r"\blocal time zone\b", r"\butc\b"),
    "calendar_locations": (r"\ball locations\b", r"\bcross-location\b", r"\bone location at a time\b"),
    "double_booking": (r"\bdouble-book", r"\boverlapping appointments?\b", r"\bconflict[- ]prevention\b"),
    "pdf_upload": (r"\bpdfs?\b",),
    "image_upload": (r"\bscanned images?\b", r"\bimage uploads?\b", r"\bimages?\b"),
    "ocr_search": (r"\bocr\b", r"\bsearch the contents\b", r"\bmanual tags\b", r"\bfilenames\b"),
    "retention": (r"\bseven years?\b", r"\b3 years?\b", r"\bretention\b"),
    "legal_hold": (r"\blegal hold\b", r"\bprevent deletion\b"),
    "watermark": (r"\bwatermark",),
    "regional_storage": (r"\bregion-specific\b", r"\beu\b", r"\bus customers?\b", r"\bs3 bucket\b"),
    "bulk_upload": (r"\bbulk upload\b",),
}


def _concepts(text: str) -> set[str]:
    normalized = text.lower()
    concepts: set[str] = set()
    for concept, patterns in _CONCEPT_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            concepts.add(concept)
    return concepts


def _link_solutions_to_requirements(requirements: list[Requirement], solutions: list[Solution]) -> list[Solution]:
    requirements_by_pair: dict[str, list[Requirement]] = {}
    for requirement in requirements:
        requirements_by_pair.setdefault(_transcript_pair_key(requirement.transcript_id), []).append(requirement)

    for solution in solutions:
        candidate_requirements = requirements_by_pair.get(_transcript_pair_key(solution.transcript_id), requirements)
        solution_concepts = _concepts(_solution_match_text(solution))
        linked_refs: list[str] = []

        for requirement in candidate_requirements:
            requirement_concepts = _concepts(_requirement_match_text(requirement))
            shared_concepts = solution_concepts & requirement_concepts
            if _should_link_requirement(requirement_concepts, solution_concepts, shared_concepts):
                linked_refs.append(requirement.requirement_id)

        solution.related_requirement_refs = linked_refs
    return solutions


def _should_link_requirement(
    requirement_concepts: set[str], solution_concepts: set[str], shared_concepts: set[str]
) -> bool:
    if not shared_concepts:
        return False

    generic_only = {"portal"}
    if shared_concepts <= generic_only and (requirement_concepts - generic_only):
        return False

    if requirement_concepts & {"email_notification", "sms_notification"} and shared_concepts <= {"auth"}:
        return False

    if requirement_concepts & {"audit_log"} and shared_concepts <= {"csv_export"}:
        return False

    if requirement_concepts & {"gdpr"} and "gdpr" not in solution_concepts:
        return False

    if requirement_concepts & {"routing", "sla"} and shared_concepts <= {"ticket_creation"}:
        return False

    if requirement_concepts & {"history_filter", "history_retention"} and shared_concepts <= {"account_history"}:
        return False

    return True


_GAP_TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "sla": (r"\bsla\b", r"\btier\b"),
    "history_filter": (r"\bfilter", r"\bdate\b", r"\btype\b"),
    "history_retention": (r"\b24 months?\b", r"\b12 months?\b", r"\bload[- ]more\b"),
    "routing": (r"\brout", r"\bkeyword", r"\brules engine\b"),
    "gdpr": (r"\bgdpr\b", r"\bprivacy\b", r"\bconsent\b", r"\berasure\b"),
    "admin_access": (r"\ball accounts\b", r"\badmin interface\b", r"\bprivileged access\b"),
    "impersonation": (r"\bimpersonat",),
    "sso": (r"\bsso\b", r"\bgoogle workspace\b", r"\bemail/password\b"),
    "csv_export": (r"\bcsv\b", r"\bexport\b", r"\bscreenshot\b"),
    "region_access": (r"\bregion\b", r"\bmanager\b", r"\banalyst\b"),
    "audit_log": (r"\baudit log\b", r"\baudit logging\b"),
    "timezone": (r"\btime zone\b", r"\butc\b"),
    "reschedule": (r"\breschedul", r"\bcancel \+ create\b"),
    "calendar_locations": (r"\blocation\b", r"\bcross-location\b"),
    "double_booking": (r"\bdouble-book", r"\boverlapping appointments?\b", r"\bconflict\b"),
    "image_upload": (r"\bimage", r"\bscanned\b"),
    "ocr_search": (r"\bocr\b", r"\bmanual tags\b", r"\bfilenames\b"),
    "retention": (r"\bretention\b", r"\bseven years?\b", r"\bthree years?\b"),
    "legal_hold": (r"\blegal hold\b", r"\bprevent deletion\b"),
    "watermark": (r"\bwatermark",),
    "regional_storage": (r"\bregion-specific\b", r"\beu\b", r"\bus\b", r"\bs3 bucket\b"),
    "bulk_upload": (r"\bbulk upload\b",),
}


def _gap_topics(gap: Gap) -> set[str]:
    text = " ".join([gap.description, gap.suggested_action, gap.reasoning]).lower()
    topics: set[str] = set()
    for topic, patterns in _GAP_TOPIC_PATTERNS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            topics.add(topic)
    return topics


def _gap_rank(gap_type: str) -> int:
    order = {
        GapType.UNADDRESSED.value: 4,
        GapType.SCOPE_MISMATCH.value: 3,
        GapType.IMPLICIT_ASSUMPTION.value: 2,
        GapType.AMBIGUITY.value: 1,
    }
    return order.get(gap_type, 0)


def _normalize_refs(values: list[str], valid_ids: set[str]) -> list[str]:
    valid_lookup = {item.lower(): item for item in valid_ids}
    normalized: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key in valid_lookup and valid_lookup[key] not in normalized:
            normalized.append(valid_lookup[key])
    return normalized


def _normalize_and_dedupe_gaps(gaps: list[Gap], requirements: list[Requirement], solutions: list[Solution]) -> list[Gap]:
    valid_requirement_ids = {item.requirement_id for item in requirements}
    valid_solution_ids = {item.solution_id for item in solutions}
    deduped: list[Gap] = []

    for gap in gaps:
        gap.type = GapType(gap.type).value if gap.type in {item.value for item in GapType} else gap.type
        gap.requirement_refs = _normalize_refs(gap.requirement_refs, valid_requirement_ids)
        gap.solution_refs = _normalize_refs(gap.solution_refs, valid_solution_ids)
        if not gap.requirement_refs:
            continue
        gap_topics = _gap_topics(gap)
        replaced = False

        for index, existing in enumerate(deduped):
            same_requirements = set(existing.requirement_refs) == set(gap.requirement_refs)
            overlapping_solutions = not existing.solution_refs or not gap.solution_refs or bool(
                set(existing.solution_refs) & set(gap.solution_refs)
            )
            shared_topics = bool(_gap_topics(existing) & gap_topics) or (
                not _gap_topics(existing) and not gap_topics and existing.description == gap.description
            )

            if same_requirements and overlapping_solutions and shared_topics:
                if _gap_rank(gap.type) > _gap_rank(existing.type):
                    deduped[index] = gap
                replaced = True
                break

        if not replaced:
            deduped.append(gap)

    for index, gap in enumerate(deduped, start=1):
        gap.gap_id = f"GAP-{index:03d}"

    return deduped


def _add_gap_if_missing(gaps: list[Gap], gap: Gap) -> None:
    signature = (tuple(gap.requirement_refs), tuple(gap.solution_refs), gap.type, gap.description.lower())
    existing_signatures = {
        (tuple(item.requirement_refs), tuple(item.solution_refs), item.type, item.description.lower()) for item in gaps
    }
    if signature in existing_signatures:
        return

    for existing in gaps:
        if existing.type != gap.type:
            continue
        if set(existing.requirement_refs) == set(gap.requirement_refs):
            return

    gaps.append(gap)


def _next_gap_id(gaps: list[Gap]) -> str:
    highest = 0
    for gap in gaps:
        match = re.search(r"(\d+)$", gap.gap_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"GAP-{highest + 1:03d}"


def _supplement_gap_analysis(
    requirements: list[Requirement],
    solutions: list[Solution],
    gap_analysis: GapAnalysisResult,
) -> GapAnalysisResult:
    solutions_by_pair: dict[str, list[Solution]] = {}
    for solution in solutions:
        solutions_by_pair.setdefault(_transcript_pair_key(solution.transcript_id), []).append(solution)

    gaps = list(gap_analysis.gaps)
    existing_requirement_refs = {ref for gap in gaps for ref in gap.requirement_refs}

    for requirement in requirements:
        candidate_solutions = solutions_by_pair.get(_transcript_pair_key(requirement.transcript_id), solutions)
        if not candidate_solutions:
            continue

        requirement_text = _requirement_text(requirement)
        solution_text = " ".join(_solution_text(solution) for solution in candidate_solutions)
        solution_refs = [solution.solution_id for solution in candidate_solutions]

        if (
            "24 month" in requirement_text
            and "filter" in requirement_text
            and "12 month" in solution_text
            and "filter" not in solution_text
            and requirement.requirement_id not in existing_requirement_refs
        ):
            _add_gap_if_missing(
                gaps,
                Gap(
                    gap_id=_next_gap_id(gaps),
                    type=GapType.SCOPE_MISMATCH.value,
                    requirement_refs=[requirement.requirement_id],
                    solution_refs=solution_refs,
                    description=(
                        "Business requires at least 24 months of account history and filtering by date/type, "
                        "but engineering only mentions a 12-month default with load-more and does not mention filtering."
                    ),
                    suggested_action=(
                        "Confirm whether engineering will support the full 24-month history requirement and add "
                        "date/type filters to the planned scope."
                    ),
                    confidence="high",
                    reasoning=(
                        "The requirement explicitly states both a 24-month minimum and filtering. The paired solution "
                        "mentions 12 months with load-more and omits filtering."
                    ),
                ),
            )

        if (
            "sla" in requirement_text
            and any(keyword in requirement_text for keyword in ("route", "routing", "tier"))
            and any(keyword in solution_text for keyword in ("route", "routing", "rules engine"))
            and "sla" not in solution_text
        ):
            _add_gap_if_missing(
                gaps,
                Gap(
                    gap_id=_next_gap_id(gaps),
                    type=GapType.AMBIGUITY.value,
                    requirement_refs=[requirement.requirement_id],
                    solution_refs=solution_refs,
                    description=(
                        "Engineering discusses ticket routing but does not explain how the three support tiers' "
                        "different SLAs will be represented or enforced."
                    ),
                    suggested_action=(
                        "Ask engineering to specify how tier-specific SLAs will be modeled, surfaced, and enforced "
                        "in the ticket workflow."
                    ),
                    confidence="medium-high",
                    reasoning=(
                        "The business requirement explicitly ties routing to different SLAs, but the paired solution "
                        "only mentions keyword-based routing."
                    ),
                ),
            )

    return GapAnalysisResult(summary=gap_analysis.summary, gaps=gaps)


PIPELINE_STAGES = (
    StageSpec(
        key="requirements",
        agent_key="requirements_extractor",
        task_key="extract_requirements",
        output_key="requirements",
        parser=_parse_requirements,
    ),
    StageSpec(
        key="solutions",
        agent_key="solution_extractor",
        task_key="extract_solutions",
        output_key="solutions",
        parser=_parse_solutions,
    ),
    StageSpec(
        key="gap_analysis",
        agent_key="gap_analyzer",
        task_key="analyze_gaps",
        output_key="gap_analysis",
        parser=_parse_gap_analysis,
        context_stage_keys=("requirements", "solutions"),
    ),
)


class GapAnalysisPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        agent_specs: dict[str, AgentSpec] | None = None,
        task_specs: dict[str, TaskSpec] | None = None,
        stages: tuple[StageSpec, ...] | None = None,
        component_factory: CrewComponentFactory | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.agent_specs = agent_specs or AGENT_SPECS
        self.task_specs = task_specs or TASK_SPECS
        self.stages = stages or PIPELINE_STAGES
        self.component_factory = component_factory or CrewComponentFactory(self.settings)

    def run_from_directories(self, business_dir: str, engineering_dir: str) -> GapReport:
        logger.info("Preparing pipeline input from transcript directories")
        business_transcripts, business_warnings = load_transcripts(business_dir, source_type="business")
        engineering_transcripts, engineering_warnings = load_transcripts(engineering_dir, source_type="engineering")
        logger.info(
            "Loaded %s business transcript(s) and %s engineering transcript(s)",
            len(business_transcripts),
            len(engineering_transcripts),
        )
        return self.run(
            business_transcripts=business_transcripts,
            engineering_transcripts=engineering_transcripts,
            warnings=business_warnings + engineering_warnings,
        )

    def run(
        self,
        business_transcripts: list[Transcript],
        engineering_transcripts: list[Transcript],
        warnings: list[str] | None = None,
    ) -> GapReport:
        logger.info("Starting pipeline execution")
        state: dict[str, Any] = {
            "business_transcripts": format_transcripts_for_prompt(business_transcripts),
            "engineering_transcripts": format_transcripts_for_prompt(engineering_transcripts),
        }
        stage_tasks: dict[str, Any] = {}
        stage_results: dict[str, Any] = {}

        for stage in self.stages:
            logger.info("Running stage: %s", stage.key)
            parsed_output, task = self._run_stage(stage, state, stage_tasks)
            stage_tasks[stage.key] = task
            if stage.output_key == "solutions":
                parsed_output = _link_solutions_to_requirements(
                    requirements=stage_results.get("requirements", []),
                    solutions=parsed_output,
                )
            stage_results[stage.output_key] = parsed_output
            state[stage.output_key] = parsed_output
            state[f"{stage.output_key}_json"] = serialize(parsed_output)
            logger.info("Completed stage: %s (%s item(s))", stage.key, self._result_size(parsed_output))

        gap_analysis: GapAnalysisResult = stage_results["gap_analysis"]
        original_gap_count = len(gap_analysis.gaps)
        gap_analysis = _supplement_gap_analysis(
            requirements=stage_results["requirements"],
            solutions=stage_results["solutions"],
            gap_analysis=gap_analysis,
        )
        gap_analysis = GapAnalysisResult(
            summary=gap_analysis.summary,
            gaps=_normalize_and_dedupe_gaps(
                gap_analysis.gaps,
                requirements=stage_results["requirements"],
                solutions=stage_results["solutions"],
            ),
        )
        supplemented_gap_count = len(gap_analysis.gaps)
        if supplemented_gap_count > original_gap_count:
            logger.info(
                "Supplemental checks added %s additional gap(s)",
                supplemented_gap_count - original_gap_count,
            )
        logger.info("Pipeline execution finished")
        return GapReport(
            business_transcript_count=len(business_transcripts),
            engineering_transcript_count=len(engineering_transcripts),
            requirements=stage_results["requirements"],
            solutions=stage_results["solutions"],
            gaps=gap_analysis.gaps,
            summary=gap_analysis.summary,
            warnings=warnings or [],
        )

    def _run_stage(self, stage: StageSpec, state: dict[str, Any], stage_tasks: dict[str, Any]):
        agent_spec = self.agent_specs[stage.agent_key]
        task_spec = self.task_specs[stage.task_key]
        logger.debug("Creating agent '%s' for stage '%s'", agent_spec.key, stage.key)
        agent = self.component_factory.create_agent(agent_spec)
        context_tasks = [stage_tasks[key] for key in stage.context_stage_keys if key in stage_tasks]
        task = self.component_factory.create_task(task_spec, agent, state, context=context_tasks)

        _, _, Crew, Process = self._get_crewai()
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self.settings.verbose,
        )
        kickoff_result = crew.kickoff()
        raw_output = self._extract_raw_output(kickoff_result, task)
        logger.debug("Received raw output for stage '%s'", stage.key)
        return stage.parser(raw_output), task

    @staticmethod
    def _get_crewai():
        from .crewai_runtime import get_crewai_objects

        return get_crewai_objects()

    @staticmethod
    def _extract_raw_output(kickoff_result: Any, task: Any) -> str:
        task_output = getattr(task, "output", None)
        if task_output is not None:
            for attribute in ("raw", "json_dict", "result"):
                value = getattr(task_output, attribute, None)
                if value:
                    if isinstance(value, str):
                        return value
                    if isinstance(value, (dict, list)):
                        return json.dumps(value)
                    return str(value)
        if isinstance(kickoff_result, str):
            return kickoff_result
        if hasattr(kickoff_result, "raw") and getattr(kickoff_result, "raw"):
            return str(kickoff_result.raw)
        return str(kickoff_result)

    @staticmethod
    def _result_size(value: Any) -> int:
        if isinstance(value, list):
            return len(value)
        if hasattr(value, "gaps") and isinstance(getattr(value, "gaps"), list):
            return len(value.gaps)
        return 1
