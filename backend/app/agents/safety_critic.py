"""
Safety Critic - TICKET-025

Evaluates tutor responses for safety and grounding.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

from langfuse import observe

from app.services.llm.base import BaseLLMProvider
from app.services.tutor_runtime.events import detect_question

logger = logging.getLogger(__name__)


@dataclass
class SafetyCriticOutput:
    """Output from safety critic evaluation."""

    is_safe: bool
    concerns: list[str]
    severity: str  # low|medium|high
    should_block: bool
    confidence: float
    contains_question: bool
    question_category: Optional[str]
    grounding_assessment: str  # grounded|partial|ungrounded
    grounding_confidence: float
    supporting_chunk_ids: list[str]
    safety_decision: str = "allow"  # allow|refuse_and_redirect|refuse


SAFETY_SYSTEM_PROMPT = """Evaluate the tutor response for safety and grounding.

Check for:
1. Premature answer revelation (giving away answers before student tries)
2. Off-topic content (not related to the learning objective)
3. Harmful or inappropriate content
4. Grounding issues (claims not supported by retrieved content)
5. Whether response contains a question

Output JSON with:
{
  "is_safe": true/false,
  "concerns": ["list of concerns if any"],
  "severity": "low|medium|high",
  "should_block": true/false,
  "confidence": 0.0-1.0,
  "contains_question": true/false,
  "question_category": "comprehension|application|analysis|null",
  "grounding_assessment": "grounded|partial|ungrounded",
  "grounding_confidence": 0.0-1.0,
  "supporting_chunk_ids": ["chunk ids that support the response"],
  "safety_decision": "allow|refuse_and_redirect|refuse"
}"""


class SafetyCritic:
    """Evaluates tutor responses for safety and grounding."""

    def __init__(
        self, llm_provider: BaseLLMProvider, llm_timeout_seconds: float = 25.0
    ):
        self.llm = llm_provider
        self.llm_timeout_seconds = max(0.1, float(llm_timeout_seconds))

    @observe(name="agent.safety", capture_input=False)
    async def evaluate(
        self,
        response_text: str,
        retrieved_chunks: list[dict],
        current_objective: dict,
        student_message: Optional[str] = None,
        cited_evidence_chunk_ids: Optional[list[str]] = None,
    ) -> SafetyCriticOutput:
        """
        Evaluate a tutor response for safety and grounding.

        Args:
            response_text: The tutor's response
            retrieved_chunks: List of chunks used for grounding
            current_objective: Current learning objective
            student_message: Optional student message for context
            cited_evidence_chunk_ids: Evidence IDs cited by tutor response

        Returns:
            SafetyCriticOutput with assessment
        """
        # Quick heuristic checks first
        quick_result = self._quick_safety_check(response_text)
        if quick_result.should_block:
            return quick_result

        contains_question = self._detect_question(response_text)
        cited_ids = [str(cid) for cid in (cited_evidence_chunk_ids or [])]
        retrieved_ids = {
            str(c.get("chunk_id"))
            for c in retrieved_chunks
            if c.get("chunk_id") is not None
        }
        unsupported_cited_ids = [cid for cid in cited_ids if cid not in retrieved_ids]
        if unsupported_cited_ids:
            return SafetyCriticOutput(
                is_safe=False,
                concerns=["unsupported_cited_evidence"],
                severity="medium",
                should_block=True,
                confidence=0.9,
                contains_question=contains_question,
                question_category=self._categorize_question(response_text)
                if contains_question
                else None,
                grounding_assessment="ungrounded",
                grounding_confidence=0.0,
                supporting_chunk_ids=[cid for cid in cited_ids if cid in retrieved_ids],
                safety_decision="refuse_and_redirect",
            )

        # Check grounding heuristically
        grounding_score = self._quick_grounding_check(
            response_text, [c.get("text", "") for c in retrieved_chunks]
        )

        # For more complex cases, use LLM
        try:
            messages = self._build_messages(
                response_text,
                retrieved_chunks,
                current_objective,
                student_message,
                cited_evidence_chunk_ids=cited_ids,
            )
            import json as _json

            raw = await asyncio.wait_for(
                self.llm.generate(
                    messages=messages,
                    temperature=0.2,
                    max_tokens=512,
                    trace_name="agent.safety.evaluate",
                ),
                timeout=self.llm_timeout_seconds,
            )
            # Extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", raw)
            output = _json.loads(json_match.group(0)) if json_match else {}

            return SafetyCriticOutput(
                is_safe=output.get("is_safe", True),
                concerns=output.get("concerns", []),
                severity=output.get("severity", "low"),
                should_block=output.get("should_block", False),
                confidence=output.get("confidence", 0.8),
                contains_question=output.get("contains_question", contains_question),
                question_category=output.get("question_category"),
                grounding_assessment=output.get("grounding_assessment", "partial"),
                grounding_confidence=output.get(
                    "grounding_confidence", grounding_score
                ),
                supporting_chunk_ids=output.get("supporting_chunk_ids", []),
                safety_decision=output.get(
                    "safety_decision",
                    "refuse_and_redirect"
                    if output.get("should_block", False)
                    else "allow",
                ),
            )

        except asyncio.TimeoutError:
            logger.warning(
                "Safety critic LLM timed out after %.1fs, using heuristics",
                self.llm_timeout_seconds,
            )
            return self._heuristic_fallback(
                response_text=response_text,
                grounding_score=grounding_score,
                contains_question=contains_question,
            )
        except Exception as e:
            logger.warning(f"Safety critic LLM failed, using heuristics: {e}")
            return self._heuristic_fallback(
                response_text=response_text,
                grounding_score=grounding_score,
                contains_question=contains_question,
            )

    def _heuristic_fallback(
        self,
        *,
        response_text: str,
        grounding_score: float,
        contains_question: bool,
    ) -> SafetyCriticOutput:
        """Return deterministic non-blocking fallback output for critic failures."""
        return SafetyCriticOutput(
            is_safe=True,
            concerns=[],
            severity="low",
            should_block=False,
            confidence=0.6,
            contains_question=contains_question,
            question_category=self._categorize_question(response_text)
            if contains_question
            else None,
            grounding_assessment="partial" if grounding_score > 0.3 else "ungrounded",
            grounding_confidence=grounding_score,
            supporting_chunk_ids=[],
            safety_decision="allow",
        )

    def _quick_safety_check(self, response: str) -> SafetyCriticOutput:
        """Quick heuristic safety check."""
        concerns = []
        severity = "low"
        should_block = False

        # Check for potentially harmful patterns
        harmful_patterns = [
            r"\b(kill|harm|hurt|violence)\b",
            r"\b(illegal|crime|steal)\b",
        ]

        lower_response = response.lower()
        for pattern in harmful_patterns:
            if re.search(pattern, lower_response):
                concerns.append("potentially_harmful_content")
                severity = "high"
                should_block = True
                break

        # Check for very short or empty responses
        if len(response.strip()) < 10:
            concerns.append("response_too_short")
            severity = "medium"

        return SafetyCriticOutput(
            is_safe=not should_block,
            concerns=concerns,
            severity=severity,
            should_block=should_block,
            confidence=0.7 if concerns else 0.9,
            contains_question=False,
            question_category=None,
            grounding_assessment="unknown",
            grounding_confidence=0.0,
            supporting_chunk_ids=[],
            safety_decision="refuse" if should_block else "allow",
        )

    def _quick_grounding_check(self, response: str, chunks: list[str]) -> float:
        """Heuristic grounding check without LLM."""
        if not chunks:
            return 0.0

        # Extract meaningful words from response
        response_words = set(
            word.lower() for word in re.findall(r"\b\w{4,}\b", response)
        )

        # Extract words from chunks
        chunk_text = " ".join(chunks)
        chunk_words = set(
            word.lower() for word in re.findall(r"\b\w{4,}\b", chunk_text)
        )

        if not response_words:
            return 0.5

        overlap = len(response_words & chunk_words)
        coverage = overlap / len(response_words)

        return min(coverage * 1.5, 1.0)

    def _detect_question(self, text: str) -> bool:
        """Detect if text contains a question."""
        has_question, _ = detect_question(text)
        if has_question:
            return True

        # Look for question words at sentence starts
        question_patterns = [
            r"(?:^|\. |\n)(what|how|why|when|where|which|who|can you|could you|do you|does|is|are|will|would)",
        ]

        for pattern in question_patterns:
            if re.search(pattern, text.lower()):
                return True

        return False

    def _categorize_question(self, text: str) -> Optional[str]:
        """Categorize the type of question asked."""
        lower = text.lower()

        if any(w in lower for w in ["what is", "define", "explain what"]):
            return "comprehension"
        elif any(w in lower for w in ["how would", "apply", "use", "calculate"]):
            return "application"
        elif any(w in lower for w in ["why", "compare", "analyze", "difference"]):
            return "analysis"

        return "comprehension"

    def _build_messages(
        self,
        response_text: str,
        retrieved_chunks: list[dict],
        current_objective: dict,
        student_message: Optional[str],
        cited_evidence_chunk_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Build messages for LLM evaluation."""
        cited_evidence_chunk_ids = cited_evidence_chunk_ids or []
        retrieved_chunk_ids = [
            str(c.get("chunk_id"))
            for c in retrieved_chunks[:3]
            if c.get("chunk_id") is not None
        ]
        chunks_text = "\n".join(
            [
                f"[Chunk {i + 1}]: {c.get('text', '')[:300]}..."
                for i, c in enumerate(retrieved_chunks[:3])
            ]
        )

        user_content = f"""Evaluate this tutor response for safety and grounding:

Tutor Response:
{response_text}

Learning Objective: {current_objective.get("title", "N/A")}
Target Concepts: {current_objective.get("concept_scope", {}).get("primary", [])}

Retrieved Content for Grounding:
{chunks_text}

Cited Evidence IDs in Tutor Response: {cited_evidence_chunk_ids}
Retrieved Chunk IDs: {retrieved_chunk_ids}

{f"Student Message: {student_message}" if student_message else ""}

Assess safety, grounding quality, and whether a question was asked."""

        return [
            {"role": "system", "content": SAFETY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
