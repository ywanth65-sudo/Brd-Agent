"""Prompt template functions for LLM operations in the BRD Agent.

All prompt templates are implemented as pure, deterministic string generator functions.
"""

import json
from typing import Any, Optional, Sequence
from pydantic import BaseModel, Field

from app.models.document import SourceChunk
from app.models.question import Question
from app.models.requirement import Requirement
from app.models.validation import ValidationIssue


def _limit_prompt_text(value: str, limit: int, label: str) -> str:
    """Keep provider requests within the model context window without hiding truncation."""
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n\n[{label} truncated to fit the model context window]"


def build_extraction_prompt(
    idea_text: Optional[str] = None,
    existing_requirements: Optional[list[Requirement]] = None,
    answered_context: Optional[str] = None,
    chunks: Optional[list[SourceChunk]] = None,
) -> str:
    """Build the extraction prompt instructing the LLM to analyze the business idea and source chunks.

    Acts as a senior business analyst extracting requirements across all 4 types
    (business, functional, nonfunctional, constraint) and proposing assumptions.

    Args:
        idea_text: Optional raw business idea prompt submitted by the stakeholder.
        existing_requirements: Any requirements already extracted in previous iterations.
        answered_context: Formatted string of questions and stakeholder answers.
        chunks: Optional list of SourceChunk records from uploaded source documents.

    Returns:
        Formatted prompt string.
    """
    existing_str = "None"
    if existing_requirements:
        existing_data = [
            {
                "id": req.id,
                "type": req.type.value,
                "title": req.title,
                "statement": req.statement,
                "actor": req.actor,
                "outcome": req.outcome,
                "priority": req.priority.value,
                "acceptance_criteria": req.acceptance_criteria,
                "confidence": req.confidence,
                "source_chunk_ids": req.source_chunk_ids,
            }
            for req in existing_requirements
        ]
        existing_str = _limit_prompt_text(
            json.dumps(existing_data, indent=2),
            6000,
            "Previously extracted requirements",
        )

    answered_str = (
        _limit_prompt_text(answered_context.strip(), 4000, "Resolved clarification answers")
        if answered_context
        else "None"
    )

    # Format source document chunks if available
    chunks_formatted: list[str] = []
    if chunks:
        for c in chunks:
            doc_label = f"Doc: {c.document_id}"
            page_label = f"Page: {c.page_number}" if c.page_number is not None else "Page: N/A"
            section_label = f" | Section: {c.heading}" if c.heading else ""
            chunks_formatted.append(
                f"[CHUNK_ID: {c.id} | {doc_label} | {page_label}{section_label}]\n{c.text.strip()}"
            )
    chunks_str = (
        _limit_prompt_text("\n\n".join(chunks_formatted), 10000, "Source document chunks")
        if chunks_formatted
        else "None"
    )

    idea_str = (
        _limit_prompt_text(idea_text.strip(), 4000, "Business idea")
        if idea_text and idea_text.strip()
        else "None provided (derive requirements primarily from source document chunks)."
    )

    return f"""You are a Principal Business Systems Analyst. Your goal is to synthesize raw business ideas and source document chunks into structured requirement specifications and explicit assumptions for a formal Business Requirements Document (BRD).

### INPUT BUSINESS IDEA:
\"\"\"
{idea_str}
\"\"\"

### SOURCE DOCUMENT CHUNKS:
{chunks_str}

### PREVIOUSLY EXTRACTED REQUIREMENTS:
{existing_str}

### RESOLVED CLARIFICATION ANSWERS:
{answered_str}

### INSTRUCTIONS:
1. Extract candidate requirements categorized into four distinct types:
   - 'business': High-level business objectives, ROI goals, or strategic outcomes.
   - 'functional': Specific features, workflows, and system capabilities ('The system shall...'). Must identify primary actor, outcome, and measurable acceptance criteria.
   - 'nonfunctional': Quality attributes (performance, latency, security, uptime, scalability, compliance) with quantifiable targets where known.
   - 'constraint': Regulatory, architectural, technology, or budgetary boundaries with explicit rationale.
2. Incorporate answered clarifications from the RESOLVED CLARIFICATION ANSWERS section. Do not re-extract stale or conflicting interpretations.
3. If an existing requirement matches, preserve its ID and refine its fields. If new, provide a clean ID like 'REQ-001', 'REQ-002'.
4. Do NOT invent 'trace_refs' (leave them empty []). Traceability references are managed by the backend engine.
5. PROPOSE EXPLICIT ASSUMPTIONS: When filling unavoidable gaps with reasonable industry defaults (e.g., standard business hours, standard web browser support), do NOT guess silently. Instead, formulate an explicit Assumption with rationale and impact level ('LOW' or 'MEDIUM').
6. CRITICAL COMPLETENESS RULES:
   - If key information is genuinely missing or ambiguous (such as the specific user role, exact numerical SLA, or system outcome), DO NOT INVENT OR HALLUCINATE specifics (such as random numbers, exact dates, third-party vendor names, or APIs not mentioned in the input).
   - If an actor, outcome, or acceptance criterion was not specified, leave that field empty (None or []) or assign a low confidence score (< 0.5) so that the validation engine can generate a targeted clarification question.
7. STRICT SOURCE CHUNK CITATIONS & TRACEABILITY:
   - When extracting any requirement derived from or justified by the provided SOURCE DOCUMENT CHUNKS, you MUST populate the `source_chunk_ids` list with the exact matching chunk IDs (e.g. `source_chunk_ids: ["CHUNK-12345-0"]`).
   - You may also provide a concise `rationale` explaining how the cited chunks justify the requirement.
   - NEVER invent or hallucinate chunk IDs. Only cite chunk IDs that appear verbatim in the `[CHUNK_ID: <id> ...]` headers above. If a requirement is derived solely from the general business idea without document grounding, leave `source_chunk_ids` as an empty list [].

Output strictly according to the ExtractionResult schema.
"""


def build_gap_analysis_prompt(requirements: list[Requirement]) -> str:
    """Build the advisory gap analysis prompt for Gemini to inspect requirement sets.

    Note: Gemini's gap analysis is treated as advisory review candidate input only;
    concrete validation decisions are enforced by Python rules.

    Args:
        requirements: List of requirements to analyze for contradictions or ambiguities.

    Returns:
        Formatted prompt string.
    """
    reqs_dump = json.dumps(
        [
            {
                "id": req.id,
                "type": req.type.value,
                "title": req.title,
                "statement": req.statement,
                "actor": req.actor,
                "outcome": req.outcome,
                "confidence": req.confidence,
            }
            for req in requirements
        ],
        indent=2,
    )

    return f"""You are an expert Requirements Quality Assurance Auditor. Review the following set of requirements for ambiguities, contradictions, or overlapping duplicates.

### REQUIREMENTS SET:
{reqs_dump}

### INSTRUCTIONS:
- Identify possible contradictions, vague quality attributes, or duplicate statements across requirements.
- Flag each issue as a review candidate.
- Provide a concise description, list the related requirement IDs, and suggest a severity ('warning' or 'blocker').
- These findings serve as advisory inputs to the engineering rule engine.

Output strictly according to the GapAnalysisResult schema.
"""


def build_question_text_prompt(
    issue: ValidationIssue,
    related_requirement: Optional[Requirement] = None,
) -> str:
    """Build a deterministic prompt asking Gemini to draft one clarification question for a single issue.

    Python decides which issues warrant questions prior to invoking this prompt.

    Args:
        issue: The specific ValidationIssue flagged by the rule engine.
        related_requirement: The corresponding Requirement object, if applicable.

    Returns:
        Formatted prompt string.
    """
    req_context = "None"
    if related_requirement:
        req_context = json.dumps(
            {
                "id": related_requirement.id,
                "type": related_requirement.type.value,
                "title": related_requirement.title,
                "statement": related_requirement.statement,
                "actor": related_requirement.actor,
                "outcome": related_requirement.outcome,
            },
            indent=2,
        )

    return f"""You are a professional Business Analyst conducting a stakeholder discovery interview. A concrete information gap has been detected that prevents generating a complete Business Requirements Document.

### VALIDATION ISSUE DETAILS:
- Issue Code: {issue.code}
- Severity: {issue.severity.value}
- Affected Field: {issue.field_path}
- Diagnostic Message: {issue.message}

### ASSOCIATED REQUIREMENT:
{req_context}

### TASK:
Draft ONE clear, concise, and non-technical clarification question that a non-technical business stakeholder can easily answer.

Requirements for your output:
1. 'question_text': Phrased clearly and politely, avoiding internal jargon or code identifiers.
2. 'why_it_matters': Exactly ONE sentence explaining why this information is essential for the system architecture or business workflow.
3. 'answer_format': Choose the most appropriate format: 'TEXT', 'CHOICE', 'DATE', 'NUMBER', or 'YES_NO'.
4. 'options': If 'answer_format' is 'CHOICE', provide a helpful list of 2 to 5 realistic options. Otherwise, set to null.

Output strictly according to the QuestionDraft schema.
"""


class ChatTurnEvaluation(BaseModel):
    """Structured response from the LLM evaluating a conversational chat turn."""

    answered_question_id: Optional[str] = Field(
        default=None,
        description="The exact ID of the open question that the user's message answered, or null if no question was answered",
    )
    extracted_answer: Optional[str] = Field(
        default=None,
        description="The clean, specific answer extracted from the user's message, or null if no question was answered",
    )
    reply: str = Field(
        ...,
        description="Natural, conversational response to the user. Acknowledge any answer provided, answer user queries, and ask the next highest priority clarification question if any remain.",
    )


def build_clarification_chat_prompt(
    project: Any,
    requirements: Sequence[Requirement],
    open_questions: Sequence[Question],
    history: Sequence[Any],
    new_message: str,
    chunks: Optional[Sequence[SourceChunk]] = None,
) -> str:
    """Build the prompt instructing the LLM to converse as an expert Requirements Engineer.

    Evaluates user messages against open clarification questions and conducts a natural,
    step-by-step stakeholder interview.
    """
    proj_title = getattr(project, "title", "Untitled Project")
    proj_idea = getattr(project, "idea", "No idea summary provided")
    proj_status = getattr(project, "status", "DRAFT")
    if hasattr(proj_status, "value"):
        proj_status = proj_status.value

    # Format current requirements summary
    req_lines = []
    for r in requirements:
        req_lines.append(
            f"- [{r.id}] ({r.type.value.upper()}) {r.title}: {r.statement} "
            f"[Actor: {r.actor or 'Unspecified'} | Outcome: {r.outcome or 'Unspecified'}]"
        )
    reqs_str = "\n".join(req_lines) if req_lines else "No requirements extracted yet."

    # Format open questions prioritized
    sorted_qs = sorted(open_questions, key=lambda q: getattr(q, "priority", 0), reverse=True)
    q_lines = []
    for q in sorted_qs:
        opts_str = f" Options: {q.options}" if q.options else ""
        q_lines.append(
            f"- [QUESTION_ID: {q.id}] (Priority: {q.priority}, Impact: {q.impact})\n"
            f"  Question: {q.question_text}\n"
            f"  Why it matters: {q.why_it_matters}\n"
            f"  Target Field: {q.field_path}{opts_str}"
        )
    questions_str = "\n".join(q_lines) if q_lines else "None! All requirements are currently clear."

    # Format source chunks if any
    chunks_str = "None"
    if chunks:
        chunks_str = "\n".join(f"- [{c.id}]: {c.text[:200]}..." for c in chunks[:5])

    # Format conversation history
    history_lines = []
    for h in history:
        role = getattr(h, "role", None) or (h.get("role") if isinstance(h, dict) else "user")
        content = getattr(h, "content", None) or (h.get("content") if isinstance(h, dict) else "")
        history_lines.append(f"{str(role).upper()}: {content}")
    history_str = "\n".join(history_lines) if history_lines else "No previous conversation history."

    sample_qid = sorted_qs[0].id if sorted_qs else "Q-SAMPLE"

    return f"""You are a helpful, expert Requirements Engineer and Lead Business Analyst conducting an interactive stakeholder discovery interview.
Your goal is to converse naturally, answer user inquiries, and systematically resolve open requirement gaps so a complete, high-quality Business Requirements Document (BRD) can be generated.

### PROJECT CONTEXT:
- Title: {proj_title}
- Status: {proj_status}
- Business Idea:
{proj_idea}

### SOURCE DOCUMENTS (Grounding):
{chunks_str}

### CURRENT REQUIREMENTS:
{reqs_str}

### OPEN CLARIFICATION QUESTIONS (Prioritized):
{questions_str}

### CONVERSATION HISTORY:
{history_str}

### LATEST USER MESSAGE:
USER: {new_message}

### INSTRUCTIONS:
1. Speak naturally, warmly, and concisely like Gemini or Claude. Be encouraging, professional, and clear.
2. Analyze the LATEST USER MESSAGE in the context of the conversation:
   - Does this message provide an answer to one of the OPEN CLARIFICATION QUESTIONS listed above?
     - If YES:
       - Set `answered_question_id` to the EXACT question ID (e.g. '{sample_qid}').
       - Set `extracted_answer` to the concise, normalized answer value provided by the user.
       - In `reply`, warmly acknowledge their answer, and then seamlessly introduce the NEXT highest-priority open question (if any questions remain).
     - If NO:
       - Set `answered_question_id` to null.
       - Set `extracted_answer` to null.
3. If the user is asking a question, asking for ideas, or asking for clarification on what you need:
   - Answer their question thoroughly and helpfully using the project context.
   - Then guide them to the next clarification gap that needs resolving.
4. Focus on ONE question at a time so the user does not feel overwhelmed by a giant questionnaire.
5. If NO open questions remain (or all have just been resolved):
   - Set `answered_question_id` (if one was just answered, otherwise null).
   - In `reply`, congratulate the user, summarize that all requirements and acceptance criteria are clear and validated, and let them know they can click 'Generate BRD' to produce the formal document!

Output strictly conforming to the ChatTurnEvaluation JSON schema.
"""
