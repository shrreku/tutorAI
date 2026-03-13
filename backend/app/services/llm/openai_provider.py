import json
import logging
from typing import Type, TypeVar, Optional

from langfuse.openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from app.services.llm.base import BaseLLMProvider
from app.services.token_counting import approximate_token_count

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    OpenAI-compatible LLM provider supporting OpenAI, OpenRouter, Ollama, vLLM, etc.

    Uses `langfuse.openai.AsyncOpenAI` – a drop-in replacement that auto-instruments
    every chat.completions.create() call as a Langfuse *generation*.  When called
    inside an active @observe() span or start_as_current_observation() context, the
    generation is automatically nested as a child.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 180.0,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
        self._model = model
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def total_tokens_used(self) -> dict:
        return {
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
        }

    @staticmethod
    def _sanitize_messages(messages: list[dict]) -> list[dict]:
        """Ensure outbound chat messages always have string content."""
        sanitized: list[dict] = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = message.get("role") or "user"
            content = message.get("content")
            if content is None:
                content = ""
            elif not isinstance(content, str):
                content = str(content)
            sanitized.append({**message, "role": role, "content": content})
        return sanitized

    @staticmethod
    def _sanitize_metadata(metadata: Optional[dict]) -> dict:
        """Drop null metadata values that can trigger wrapper edge cases."""
        if not metadata:
            return {}
        sanitized: dict = {}
        for key, value in metadata.items():
            if value is None:
                continue
            sanitized[str(key)] = value
        return sanitized

    @staticmethod
    def _is_empty_response_error(error: Exception | str) -> bool:
        msg = str(error).lower()
        return "nonetype" in msg or "has no len" in msg

    async def _create_completion_with_resilience(
        self,
        create_kwargs: dict,
        *,
        trace_name: str,
    ):
        """Execute completion with compatibility and null-response recovery."""
        kwargs = dict(create_kwargs)
        kwargs["metadata"] = self._sanitize_metadata(kwargs.get("metadata"))

        try:
            return await self.client.chat.completions.create(**kwargs)
        except Exception as first_error:
            err_msg = str(first_error).lower()

            if "response_format" in kwargs and any(
                token in err_msg
                for token in (
                    "response_format",
                    "json_object",
                    "not supported",
                    "invalid",
                    "400",
                )
            ):
                logger.info(
                    "[generate_json] Model doesn't support response_format, retrying without it"
                )
                fallback_kwargs = dict(kwargs)
                fallback_kwargs.pop("response_format", None)
                try:
                    return await self.client.chat.completions.create(**fallback_kwargs)
                except Exception as fallback_error:
                    first_error = fallback_error

            if self._is_empty_response_error(first_error):
                logger.warning(
                    "[%s] LLM returned null content via wrapper, retrying once",
                    trace_name,
                )
                retry_kwargs = dict(kwargs)
                retry_kwargs["metadata"] = {}
                retry_kwargs.pop("response_format", None)
                try:
                    return await self.client.chat.completions.create(**retry_kwargs)
                except Exception as retry_error:
                    if self._is_empty_response_error(retry_error):
                        raise ValueError(
                            f"LLM returned empty/null response ({trace_name})"
                        ) from retry_error
                    raise

            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    )
    async def generate(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        trace_name: str = "llm_generate",
        trace_metadata: Optional[dict] = None,
    ) -> str:
        """Generate a text response. Langfuse generation is auto-created by the wrapped client."""
        used_model = model or self._model
        safe_messages = self._sanitize_messages(messages)
        safe_metadata = self._sanitize_metadata(trace_metadata)

        try:
            response = await self._create_completion_with_resilience(
                {
                    "model": used_model,
                    "messages": safe_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "name": trace_name,
                    "metadata": safe_metadata,
                },
                trace_name=trace_name,
            )

            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = (
                response.usage.completion_tokens if response.usage else 0
            )
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens

            # Null-safe content extraction
            if not response or not response.choices:
                logger.warning(f"[generate] LLM returned no choices for {trace_name}")
                return ""
            content = (
                response.choices[0].message.content
                if response.choices[0].message
                else None
            )
            return content or ""
        except Exception as e:
            # Langfuse wrapper can fail with NoneType errors on empty model responses
            if self._is_empty_response_error(e):
                logger.warning(
                    f"[generate] LLM returned empty/null response ({trace_name}): {e}"
                )
                return ""
            logger.error(f"LLM generation failed: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    )
    async def generate_json(
        self,
        messages: list[dict],
        schema: Type[T],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        trace_name: str = "llm_generate_json",
        trace_metadata: Optional[dict] = None,
    ) -> T:
        """Generate and parse a JSON response into a Pydantic model."""
        used_model = model or self._model
        safe_messages = self._sanitize_messages(messages)
        safe_metadata = self._sanitize_metadata(trace_metadata)

        # Add JSON instruction to system message
        json_instruction = f"\nIMPORTANT: Respond with a single valid JSON object only. No markdown code fences, no explanation text before or after. The JSON must conform to this schema:\n{json.dumps(schema.model_json_schema(), indent=2)}"

        enhanced_messages = safe_messages.copy()
        if enhanced_messages and enhanced_messages[0].get("role") == "system":
            enhanced_messages[0] = {
                **enhanced_messages[0],
                "content": enhanced_messages[0]["content"] + json_instruction,
            }
        else:
            enhanced_messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"You are a helpful assistant.{json_instruction}",
                },
            )

        try:
            create_kwargs = {
                "model": used_model,
                "messages": enhanced_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "name": trace_name,
                "metadata": {**safe_metadata, "schema": schema.__name__},
                "response_format": {"type": "json_object"},
            }
            response = await self._create_completion_with_resilience(
                create_kwargs,
                trace_name=trace_name,
            )

            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = (
                response.usage.completion_tokens if response.usage else 0
            )
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens

            content = response.choices[0].message.content
            if not content or not content.strip():
                logger.warning(
                    f"[generate_json] LLM returned empty content for {schema.__name__}"
                )
                raise ValueError(f"LLM returned empty content for {schema.__name__}")

            logger.debug(
                f"[generate_json] Raw LLM output for {schema.__name__} ({len(content)} chars): {content[:500]}"
            )

            # Extract JSON from response (handles markdown code blocks)
            content = self._extract_json(content)
            logger.debug(
                f"[generate_json] Extracted JSON for {schema.__name__}: {content[:500]}"
            )

            try:
                data = json.loads(content)
                # Apply schema-aware coercion for common LLM mistakes
                data = self._coerce_data(data, schema)
                result = schema.model_validate(data)
                return result
            except json.JSONDecodeError as e:
                repaired = self._repair_json_from_decode_error(content, e)
                if repaired != content:
                    try:
                        data = json.loads(repaired)
                        data = self._coerce_data(data, schema)
                        result = schema.model_validate(data)
                        return result
                    except (json.JSONDecodeError, ValidationError):
                        pass
                logger.warning(
                    f"JSON parse failed for {schema.__name__} at position {e.pos}: {e.msg}"
                )
                logger.warning(f"Extracted content: {content[:300]}")
                raise ValueError(f"Failed to generate valid JSON: {e}")
            except ValidationError as e:
                logger.warning(f"JSON validation failed for {schema.__name__}: {e}")
                logger.warning(
                    f"Parsed data: {json.dumps(data)[:300] if isinstance(data, dict) else str(data)[:300]}"
                )
                raise ValueError(f"Failed to validate JSON: {e}")
        except Exception:
            raise

    def _extract_json(self, text: str) -> str:
        """Extract and clean JSON from text that may contain markdown or syntax errors."""
        import re

        # Try to find JSON in code blocks first
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            text = json_match.group(1).strip()
        else:
            # Try to find raw JSON object — match outermost balanced braces
            # Use a two-pass approach: first try json.loads on the whole text
            stripped = text.strip()
            if stripped.startswith("{"):
                text = stripped
            else:
                json_match = re.search(r"(\{[\s\S]*\})", text)
                if json_match:
                    text = json_match.group(1)

        # Clean common JSON syntax issues from LLMs
        # Remove trailing commas before } or ]
        text = re.sub(r",\s*([}\]])", r"\1", text)
        # Remove control characters EXCEPT newline (\n), tab (\t), carriage return (\r)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        # Escape stray backslashes that would otherwise make JSON invalid.
        text = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)

        # Handle truncated JSON - try to close unclosed brackets
        text = self._repair_truncated_json(text)

        return text.strip()

    def _repair_json_from_decode_error(
        self, text: str, error: json.JSONDecodeError
    ) -> str:
        """Attempt targeted repair using the JSON parser failure position."""
        truncated_messages = {
            "Unterminated string starting at",
            "Expecting value",
            "Expecting ',' delimiter",
        }
        if error.msg not in truncated_messages:
            return text

        candidate_positions = [error.pos]
        scan_start = min(error.pos, len(text) - 1)
        for idx in range(scan_start, -1, -1):
            if text[idx] in {",", "{", "["}:
                candidate_positions.append(idx)

        for pos in candidate_positions:
            truncated = text[:pos].rstrip().rstrip(",")
            if not truncated:
                continue
            repaired = self._repair_truncated_json(truncated)
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                continue

        return text

    def _repair_truncated_json(self, text: str) -> str:
        """Attempt to repair truncated JSON by closing unclosed brackets."""
        import re

        # Remove incomplete trailing content after last complete value
        # Find last valid position
        text = text.rstrip()

        if not text:
            return text

        # If the response was cut off inside a string, close it before sealing braces.
        unescaped_quote_count = len(re.findall(r'(?<!\\)"', text))
        if unescaped_quote_count % 2 == 1:
            text += '"'

        # Remove trailing incomplete string or value
        if text and text[-1] not in '{}[],"0123456789nulltruefalse':
            # Try to find the last complete field
            last_complete = max(
                text.rfind('",'),
                text.rfind('"],'),
                text.rfind("},"),
                text.rfind("],"),
                text.rfind('"'),
                text.rfind("}"),
                text.rfind("]"),
            )
            if last_complete > 0:
                text = text[: last_complete + 1]

        # Remove dangling key/value separators before closing structures.
        text = re.sub(r"[:,]\s*$", "", text)

        # Remove trailing comma if present
        text = text.rstrip().rstrip(",")

        # Close remaining brackets
        open_braces = text.count("{") - text.count("}")
        open_brackets = text.count("[") - text.count("]")

        # Close in reverse order of likely nesting
        text += "]" * max(0, open_brackets)
        text += "}" * max(0, open_braces)

        return text

    def _coerce_data(self, data: dict, schema: Type[T]) -> dict:
        """Apply schema-aware coercion for common LLM output mistakes.

        Handles cases like:
        - concept_deltas returned as list instead of dict
        - progression_decision returned as string instead of int
        - pedagogical_action with different casing
        """
        if not isinstance(data, dict):
            return data

        # --- EnrichmentResponseSchema: normalize concept and relationship keys ---
        concepts_taught = data.get("concepts_taught")
        if isinstance(concepts_taught, list):
            normalized_concepts = []
            for item in concepts_taught:
                if isinstance(item, dict):
                    normalized_item = dict(item)
                    if "name" not in normalized_item:
                        concept_name = normalized_item.pop(
                            "concept_name", None
                        ) or normalized_item.pop("concept", None)
                        if concept_name:
                            normalized_item["name"] = concept_name
                    normalized_concepts.append(normalized_item)
                else:
                    normalized_concepts.append(item)
            data["concepts_taught"] = normalized_concepts

        semantic_relationships = data.get("semantic_relationships")
        if isinstance(semantic_relationships, list):
            relation_aliases = {
                "property_of": "RELATED_TO",
                "has_property": "RELATED_TO",
                "depends_on": "REQUIRES",
                "depends": "REQUIRES",
                "applies": "APPLIES_TO",
                "derived_from": "DERIVES_FROM",
                "derived": "DERIVES_FROM",
                "partof": "PART_OF",
                "type_of": "IS_A",
            }
            normalized_relationships = []
            for item in semantic_relationships:
                if not isinstance(item, dict):
                    normalized_relationships.append(item)
                    continue
                normalized_item = dict(item)
                if "source" not in normalized_item and normalized_item.get(
                    "source_concept"
                ):
                    normalized_item["source"] = normalized_item.pop("source_concept")
                if "target" not in normalized_item and normalized_item.get(
                    "target_concept"
                ):
                    normalized_item["target"] = normalized_item.pop("target_concept")
                relation_type = (
                    normalized_item.get("relation_type")
                    or normalized_item.pop("type", None)
                    or normalized_item.pop("relationship_type", None)
                )
                if isinstance(relation_type, str):
                    normalized_key = (
                        relation_type.strip()
                        .lower()
                        .replace("-", "_")
                        .replace(" ", "_")
                    )
                    normalized_item["relation_type"] = relation_aliases.get(
                        normalized_key,
                        relation_type.strip().upper(),
                    )
                normalized_relationships.append(normalized_item)
            data["semantic_relationships"] = normalized_relationships

        # --- EvaluatorOutput: concept_deltas list → dict ---
        if "concept_deltas" in data and isinstance(data["concept_deltas"], list):
            coerced = {}
            for item in data["concept_deltas"]:
                if isinstance(item, dict):
                    # Try to find the concept name key
                    name = (
                        item.pop("concept", None)
                        or item.pop("concept_name", None)
                        or item.pop("name", None)
                    )
                    if name:
                        coerced[name] = item
                    else:
                        # Use a generic key based on index
                        coerced[f"concept_{len(coerced)}"] = item
            if coerced:
                data["concept_deltas"] = coerced

        # --- PolicyOrchestratorOutput: progression_decision string → int ---
        pd = data.get("progression_decision")
        if isinstance(pd, str):
            mapping = {
                "continue_step": 1,
                "advance_step": 2,
                "skip_to_step": 3,
                "insert_ad_hoc": 4,
                "advance_objective": 5,
                "end_session": 6,
            }
            data["progression_decision"] = mapping.get(pd.lower().strip(), 1)

        # --- pedagogical_action: normalize casing ---
        pa = data.get("pedagogical_action")
        if isinstance(pa, str):
            pa_norm = pa.lower().strip().replace("-", "_").replace(" ", "_")
            alias_map = {
                "scaffold": "hint",
                "scaffolded": "hint",
                "coach": "hint",
                "probe": "question",
                "ask": "question",
                "test": "assess",
                "quiz": "assess",
                "review": "summarize",
            }
            data["pedagogical_action"] = alias_map.get(pa_norm, pa_norm)

        # --- intent: normalize or drop invalid labels ---
        VALID_INTENT = {
            "question",
            "answer",
            "statement",
            "confusion",
            "request_hint",
            None,
        }
        intent = data.get("intent")
        if intent is not None:
            intent_lower = intent.lower().strip() if isinstance(intent, str) else intent
            if intent_lower not in VALID_INTENT:
                # Common LLM drift: labels like "correct"/"incorrect" belong to evaluator, not intent.
                msg = (
                    (data.get("reasoning") or "")
                    + " "
                    + (data.get("planner_guidance") or "")
                )
                msg = msg.lower()
                if "?" in msg:
                    intent_lower = "question"
                elif any(
                    k in msg for k in ("confus", "unclear", "misconception", "stuck")
                ):
                    intent_lower = "confusion"
                else:
                    intent_lower = "statement"
            data["intent"] = intent_lower

        # --- student_intent: normalize or drop invalid labels ---
        VALID_STUDENT_INTENT = {
            "engaged",
            "confused",
            "bored",
            "move_on",
            "asking_question",
            "answer_attempt",
            "off_topic",
            "frustrated",
            None,
        }
        student_intent = data.get("student_intent")
        if student_intent is not None:
            si_lower = (
                student_intent.lower().strip()
                if isinstance(student_intent, str)
                else student_intent
            )
            if si_lower not in VALID_STUDENT_INTENT:
                si_lower = None
            data["student_intent"] = si_lower

        # --- recommended_strategy: normalize or drop ---
        VALID_STRATEGY = {
            "direct",
            "socratic",
            "scaffolded",
            "assessment",
            "review",
            None,
        }
        rs = data.get("recommended_strategy")
        if rs is not None:
            rs_lower = rs.lower().strip() if isinstance(rs, str) else rs
            data["recommended_strategy"] = (
                rs_lower if rs_lower in VALID_STRATEGY else None
            )

        # --- correctness_label: normalize casing ---
        cl = data.get("correctness_label")
        if isinstance(cl, str):
            data["correctness_label"] = cl.lower().strip()

        # --- ready_to_advance: normalize to bool if represented as string ---
        rta = data.get("ready_to_advance")
        if isinstance(rta, str):
            rta_norm = rta.strip().lower()
            if rta_norm in {"true", "yes", "1", "ready", "advance"}:
                data["ready_to_advance"] = True
            elif rta_norm in {"false", "no", "0", "not_ready", "hold"}:
                data["ready_to_advance"] = False

        # --- recommended_intervention: normalize known aliases or drop invalid ---
        ri = data.get("recommended_intervention")
        if isinstance(ri, str):
            ri_norm = ri.strip().lower().replace("-", "_").replace(" ", "_")
            intervention_aliases = {
                "reteach": "reteach",
                "worked_example": "worked_example",
                "example": "worked_example",
                "guided_practice": "guided_practice",
                "practice": "guided_practice",
                "quick_check": "quick_check",
                "checkpoint": "quick_check",
                "advance": "advance",
            }
            data["recommended_intervention"] = intervention_aliases.get(ri_norm)

        # --- turn_plan.interaction_type: normalize ---
        if "turn_plan" in data and isinstance(data["turn_plan"], dict):
            tp = data["turn_plan"]
            it = tp.get("interaction_type")
            if isinstance(it, str):
                # Normalize: map common LLM variants to valid enum values
                it_lower = it.lower().strip().replace(" ", "_")
                VALID_INTERACTION = {
                    "ask_question",
                    "give_hint",
                    "worked_example",
                    "explain_concept",
                    "check_understanding",
                    "reflect_prompt",
                    "correct_mistake",
                }
                if it_lower not in VALID_INTERACTION:
                    tp["interaction_type"] = "explain_concept"
                else:
                    tp["interaction_type"] = it_lower

        return data

    async def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        try:
            import tiktoken

            encoding = tiktoken.encoding_for_model(self._model)
            return len(encoding.encode(text))
        except Exception:
            return approximate_token_count(text)
