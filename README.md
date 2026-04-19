# GapAnalysisAgent

A simple AI-powered tool that identifies gaps between business requirements and engineering solutions by analyzing meeting transcripts.

## Overview

GapAnalysisAgent helps project stakeholders discover misalignments between what business teams requested and what engineering teams plan to deliver. It uses AI agents to:
1. Extract structured requirements from business meeting transcripts
2. Extract structured solutions from engineering planning transcripts
3. Automatically identify gaps, mismatches, and missing features

## Architecture Overview

The project is implemented as a small sequential pipeline with **three specialized agents**:

1. **Requirements extractor**
   - Input: business transcripts
   - Output: structured `Requirement` objects
2. **Solutions extractor**
   - Input: engineering transcripts
   - Output: structured `Solution` objects
3. **Gap analyzer**
   - Input: extracted requirements + extracted solutions
   - Output: structured `Gap` objects and a summary

The output of one stage becomes the input to the next stage, which makes the data flow easy to explain and easy to debug.

## How Data Flows Through the System

The system follows a simple 3-stage pipeline:

```
Business transcripts ──► Requirements Agent ──► Requirement objects ─┐
                                                                     │
Engineering transcripts ─► Solutions Agent ────► Solution objects ───┼──► Gap Agent ──► Gap report
                                                                     │
                                      Supplementary rule-based checks ┘
```

### Stage 1: Requirements Extraction
An AI agent (`requirements_extractor`) reads business meeting transcripts and extracts structured requirements:
- Requirement ID (R1, R2, R3...)
- Statement (what the business wants)
- Priority (must_have / nice_to_have)
- Source speaker and excerpt

**Input:** Raw business transcripts (e.g., `transcripts/business/BT-001.txt`)  
**Output:** Structured list of requirements

### Stage 2: Solutions Extraction
An AI agent (`solution_extractor`) reads engineering meeting transcripts and extracts:
- Solution ID (SOL-001, SOL-002...)
- Statement (what engineering plans to build)
- Scope limitations (what's NOT included)
- Tech choices and deferred items

**Input:** Raw engineering transcripts (e.g., `transcripts/engineering/ET-001.txt`)  
**Output:** Structured list of solutions

### Stage 3: Gap Analysis
An AI agent (`gap_analyzer`) compares requirements vs solutions to find:
- **Unaddressed requirements** - Business asked for it, engineering didn't mention it
- **Scope mismatches** - Engineering's implementation differs from business ask
- **Implicit assumptions** - Engineering made assumptions not validated by business
- **Ambiguities** - Unclear whether something is covered or not

**Output:** Markdown report with all gaps, confidence levels, and suggested actions

After the LLM-based gap analysis runs, the pipeline also applies a few **deterministic supplement checks** in `pipeline.py` for cases such as:
- 24-month history requirement vs 12-month solution
- SLA requirement mentioned in business transcript but not reflected in engineering solution

This keeps the design simple while improving reliability for known high-value patterns.

## Project Structure

```
GapAnalysisAgent/
├── gap_analysis_agent/
│   ├── __init__.py           # Package init
│   ├── cli.py                # Command-line interface (main entry)
│   ├── config.py             # Settings (API keys, paths, LLM config)
│   ├── crewai_runtime.py     # CrewAI framework integration
│   ├── factory.py            # Creates AI agents and tasks
│   ├── io.py                 # File I/O (read transcripts, write reports)
│   ├── json_utils.py         # JSON parsing helpers
│   ├── models.py             # Data classes (Requirement, Solution, Gap, etc.)
│   ├── pipeline.py           # Core 3-stage pipeline + agent definitions
│   ├── reporting.py          # Report formatting and generation
│   └── specs.py              # AgentSpec, TaskSpec, StageSpec classes
├── transcripts/
│   ├── business/             # Business meeting transcripts
│   │   ├── BT-001.txt
│   │   ├── BT-002.txt
│   │   ├── BT-003.txt
│   │   └── BT-004.txt
│   └── engineering/          # Engineering meeting transcripts
│       ├── ET-001.txt
│       ├── ET-002.txt
│       ├── ET-003.txt
│       └── ET-004.txt
├── reports/
│   └── report.md             # Generated gap analysis report
├── tests/                    # Unit tests
├── main.py                   # Entry point: calls CLI main()
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Key Components

### 1. Agent Specifications (`pipeline.py`)
Three AI agents defined as `AgentSpec` dataclasses:

```python
REQUIREMENTS_AGENT = AgentSpec(
    key="requirements_extractor",
    role="Business Requirements Analyst",
    goal="Extract clear, traceable business requirements from messy stakeholder transcripts",
    backstory="You specialize in turning informal product conversations into structured requirements",
)

SOLUTIONS_AGENT = AgentSpec(...)
GAP_AGENT = AgentSpec(...)
```

### 2. Task Specifications (`pipeline.py`)
Each agent has a specific task with prompt templates:

```python
"extract_requirements": TaskSpec(
    description_template="Analyze business transcripts and extract requirements...",
    expected_output="JSON array with requirement_id, statement, priority, etc."
)
```

### 3. Data Models (`models.py`)

| Class | Fields | Purpose |
|-------|--------|---------|
| `Transcript` | id, source_type, file_name, text | Raw meeting text |
| `Requirement` | id, transcript_id, statement, priority, constraints, speaker, source_excerpt | Business requirement |
| `Solution` | id, transcript_id, statement, scope_limitations, tech_choices, deferred_items, speaker, source_excerpt | Engineering plan |
| `Gap` | id, type, requirement_refs, solution_refs, description, suggested_action, confidence, reasoning | Discovered mismatch |
| `GapReport` | transcript_counts, requirements[], solutions[], gaps[], summary | Final report output |

### 4. Pipeline Execution

The `run()` method in `pipeline.py` executes sequentially:

1. **Load transcripts** from `transcripts/business/` and `transcripts/engineering/`
2. **Stage 1:** Create requirements agent → run extraction → parse results
3. **Stage 2:** Create solutions agent → run extraction → parse results
4. **Stage 3:** Create gap analyzer → compare lists → parse gaps
5. **Generate report** in `reports/report.md`

### 5. Factory Pattern (`factory.py`)

`CrewComponentFactory` creates CrewAI components:
- `create_agent()` - Creates an LLM-powered agent from `AgentSpec`
- `create_task()` - Creates a task from `TaskSpec`
- `create_crew()` - Assembles agents and tasks into a runnable crew

## Agent Design Decisions

### Why three agents instead of one big prompt?

I intentionally chose a **multi-step chain** instead of a single LLM call.

Why:
- **Separation of concerns**: extracting requirements and extracting engineering solutions are different tasks
- **Better traceability**: I can inspect intermediate structured outputs before gap analysis
- **Lower prompt complexity**: each agent gets a narrower job and a simpler prompt
- **Easier debugging**: if output is wrong, I can identify whether extraction failed or comparison failed
- **More maintainable**: future stages can be improved independently

### Why not a looping agent?

I did **not** choose a looping or autonomous agent design because the problem is bounded and predictable:
- input files are static
- the workflow is fixed
- the output format is known in advance

A loop would add complexity without much benefit for this assignment.

### Prompting strategy

Each agent is given:
- a clear role
- a narrow goal
- a short backstory
- a strict output format

The tasks explicitly request **strict JSON**, which makes the downstream parsing predictable. This is important because the pipeline converts LLM output into typed dataclasses such as `Requirement`, `Solution`, and `Gap`.

### Why structured models?

The data models in `models.py` make the system easier to explain:
- `Transcript` holds raw input
- `Requirement` and `Solution` hold extracted facts
- `Gap` represents mismatches
- `GapReport` is the final output

This keeps the code simple and avoids passing around unstructured strings between stages.

### Model/tool structure choice

The implementation uses CrewAI mainly as a lightweight orchestration layer:
- one agent per task
- sequential execution
- typed parsing after each step

This is a good fit for the assignment because it demonstrates agent decomposition without overengineering the system.

## Design Note: Why This Is a Multi-Step Chain

This assignment could be implemented in three ways:

1. **Single LLM call**
   - simplest to write
   - weakest traceability
   - harder to debug and validate
2. **Multi-step chain**
   - balances simplicity and reliability
   - exposes intermediate outputs
3. **Looping agent**
   - most flexible
   - unnecessary complexity for a fixed pipeline

I chose the **multi-step chain** because it gives better modularity and explainability than a single prompt, while remaining much simpler and more predictable than a looping agent.

## Setup & Run Instructions

### 1. Install dependencies

```bash
python -m pip install -r requirements.txt
```

Recommended Python version: **3.10–3.13**. The current CrewAI dependency does not install cleanly on Python 3.14 in this environment.

If `python` is not available on your machine, use:

```bash
python3 -m pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root.

#### Minimal OpenAI-style setup

```env
OPENAI_API_KEY=your-key-here
OPENAI_MODEL_NAME=gpt-4o-mini
```

#### Or use the project-specific variables

```env
GAP_ANALYSIS_API_KEY=your-key-here
GAP_ANALYSIS_LLM_MODEL=gpt-4o-mini
GAP_ANALYSIS_VERBOSE=true
```

#### Azure-style configuration

```env
OPENAI_API_TYPE=azure
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_API_VERSION=2024-02-01
```

### 3. Add transcripts

Place business transcripts in:

```
transcripts/business/
```

Place engineering transcripts in:

```
transcripts/engineering/
```

This repository includes the original sample pair plus **3 additional transcript pairs** (`BT/ET-002` through `BT/ET-004`) to stress-test generalization, as requested in the assignment.

### 4. Run the pipeline

Generate a Markdown report:

```bash
python main.py --business transcripts/business --engineering transcripts/engineering --output reports/report.md --format markdown
```

Generate a JSON report:

```bash
python main.py --business transcripts/business --engineering transcripts/engineering --output reports/report.json --format json
```

Generate one report per matched BT/ET pair:

```bash
python main.py --business transcripts/business --engineering transcripts/engineering --pairwise-output-dir reports/pairs --format markdown
```

### 5. Review the output

Open the generated report in:

```
reports/report.md
```

or:

```
reports/report.json
```

## Gap Types

The system identifies 4 types of gaps:

| Type | Description | Example |
|------|-------------|---------|
| `unaddressed` | Requirement mentioned, no solution exists | Admin impersonation feature requested but not planned |
| `scope_mismatch` | Solution differs from requirement | 12-month history default vs 24-month requirement |
| `implicit_assumption` | Engineering assumed something without validation | Keyword-based routing assumes tier mapping is sufficient |
| `ambiguity` | Unclear if requirement is covered | SLA enforcement mentioned but not implemented |

## Example Report Output

The generated `report.md` includes:
- **Coverage Summary** - Quick view of what's covered vs not covered
- **Requirements Table** - All extracted requirements with priorities
- **Solutions Table** - All engineering solutions with scope limits
- **Gaps Table** - Detailed list of all mismatches with:
  - Type (unaddressed, scope_mismatch, etc.)
  - Confidence level (high, medium-high, medium)
  - Description of the issue
  - Suggested action to resolve

## Known Limitations

- **LLM extraction can still miss nuance**: if wording is vague, the agent may under-extract or over-group requirements
- **Limited deterministic checks**: only a few post-processing rules are implemented; many edge cases still rely entirely on the LLM
- **No transcript normalization stage**: the system relies on prompting rather than explicit cleanup for filler talk, greetings, or noisy formatting
- **No confidence calibration beyond text labels**: confidence is returned as strings like `high` or `medium-high`, not as a validated score
- **No human review workflow**: there is no approval UI for accepting or rejecting extracted requirements/gaps
- **No retrieval/history layer**: the pipeline only analyzes the files provided for a run and does not learn across projects
- **CLI is intentionally minimal**: it is enough for the assignment, but not yet designed for large-scale production use

## What I Would Improve Next

If I had another day, I would improve these first:

1. **Add transcript cleaning/preprocessing**
   - remove greetings, filler text, and repeated speaker labels before extraction
2. **Add evaluation fixtures**
   - create gold-standard transcripts with expected requirements, solutions, and gaps
   - measure extraction accuracy across runs
3. **Strengthen deterministic validation**
   - add rule-based checks for compliance, admin scope, impersonation, and filtering requirements
4. **Further improve output traceability**
   - add stronger source excerpt linking from each gap back to exact requirement and solution evidence
5. **Harden parsing**
   - add retries or repair logic when model output is close to valid JSON but malformed

## Extending the System

To add new capabilities:

1. **New agent:** Add `AgentSpec` to `pipeline.py` + register in `AGENT_SPECS`
2. **New task:** Add `TaskSpec` to `pipeline.py` + register in `TASK_SPECS`
3. **New stage:** Add `StageSpec` to the pipeline sequence in `run()`
4. **New data model:** Add dataclass to `models.py` with `from_dict()` parser

## Dependencies

- `crewai` - Multi-agent orchestration framework
- `openai` - LLM provider (GPT-4o-mini by default)
- `pydantic` - Data validation
- Standard library: `dataclasses`, `json`, `re`, `pathlib`

## Architecture Summary

```
CLI (cli.py)
    │
    ▼
Pipeline (pipeline.py)
    │
    ├──► Stage 1: Requirements Extraction
    │      └─► AI Agent (requirements_extractor)
    │
    ├──► Stage 2: Solutions Extraction  
    │      └─► AI Agent (solution_extractor)
    │
    └──► Stage 3: Gap Analysis
           └─► AI Agent (gap_analyzer)
    │
    ▼
Report Generation (reporting.py)
    │
    ▼
reports/report.md
```

The system is intentionally simple: no database, no complex orchestration, just file-based I/O, typed intermediate models, and sequential AI-powered analysis stages.