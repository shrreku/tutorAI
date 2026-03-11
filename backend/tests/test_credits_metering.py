"""Tests for credit metering and model-task health services (CM-019)."""
import uuid

import pytest

from app.config import settings


# ---------------------------------------------------------------------------
# Unit tests for CreditMeter helper methods (no DB required)
# ---------------------------------------------------------------------------


class TestUsdToCredits:
    """Test the _usd_to_credits rounding logic."""

    def _make_meter(self):
        """Create a CreditMeter with a None db (won't hit DB in these tests)."""
        from app.services.credits.meter import CreditMeter
        return CreditMeter(db=None)  # type: ignore[arg-type]

    def test_zero_usd_returns_floor(self):
        meter = self._make_meter()
        result = meter._usd_to_credits(0.0, "economy")
        assert result == 50  # economy floor

    def test_small_usd_rounds_to_fifty(self):
        meter = self._make_meter()
        # $0.0001 / $0.008 per credit = 0.0125 credits → rounds to 50 (floor)
        result = meter._usd_to_credits(0.0001, "economy")
        assert result == 50

    def test_standard_floor(self):
        meter = self._make_meter()
        result = meter._usd_to_credits(0.0001, "standard")
        assert result == 100

    def test_premium_floor(self):
        meter = self._make_meter()
        result = meter._usd_to_credits(0.0001, "premium_small")
        assert result == 200

    def test_larger_amount_rounds_to_fifty(self):
        meter = self._make_meter()
        # $0.01 / $0.008 = 1.25 credits → round_to_50(1.25) = 50
        result = meter._usd_to_credits(0.01, "economy")
        assert result % 50 == 0
        assert result >= 50

    def test_unknown_class_gets_economy_floor(self):
        meter = self._make_meter()
        result = meter._usd_to_credits(0.0, "unknown_class")
        assert result == 50


class TestGetModelClassFloor:
    """Test model class floor determination from usage lines."""

    def _make_meter(self):
        from app.services.credits.meter import CreditMeter
        return CreditMeter(db=None)  # type: ignore[arg-type]

    def test_empty_lines_returns_economy(self):
        meter = self._make_meter()
        result = meter._get_model_class_floor([])
        assert result == "economy"

    def test_none_lines_returns_economy(self):
        meter = self._make_meter()
        result = meter._get_model_class_floor(None)
        assert result == "economy"


class TestEstimateIngestionV2:
    """Test the ingestion estimation v2 logic."""

    def _make_meter(self):
        from app.services.credits.meter import CreditMeter
        return CreditMeter(db=None)  # type: ignore[arg-type]

    def test_basic_estimate(self):
        meter = self._make_meter()
        result = meter.estimate_ingestion_v2(
            file_size_bytes=50_000,
            filename="test.pdf",
        )
        assert "estimated_credits_low" in result
        assert "estimated_credits_high" in result
        assert result["estimated_credits_low"] <= result["estimated_credits_high"]
        assert result["estimated_credits_low"] > 0

    def test_txt_file_estimate(self):
        meter = self._make_meter()
        result = meter.estimate_ingestion_v2(
            file_size_bytes=10_000,
            filename="notes.txt",
        )
        assert result["estimated_credits_low"] > 0

    def test_small_file(self):
        meter = self._make_meter()
        result = meter.estimate_ingestion_v2(
            file_size_bytes=100,
            filename="tiny.md",
        )
        assert result["estimated_credits_low"] > 0
        assert result["confidence"] in ("low", "medium", "high")


# ---------------------------------------------------------------------------
# Billing telemetry event format tests
# ---------------------------------------------------------------------------


class TestBillingTelemetry:
    """Test that billing telemetry events are well-formed."""

    def test_emit_billing_event(self, capsys):
        import json
        import logging
        from app.services.telemetry.billing_events import emit_billing_event

        # Set up logging to capture output
        billing_logger = logging.getLogger("billing.telemetry")
        billing_logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        billing_logger.addHandler(handler)

        try:
            emit_billing_event(
                "billing.operation.finalized",
                user_id="test-user",
                operation_id="op-123",
                metadata={"final_credits": 100, "final_usd": 0.8},
            )
        finally:
            billing_logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# Model health service logic tests (no DB)
# ---------------------------------------------------------------------------


class TestModelHealthServiceUnit:
    """Test ModelHealthService threshold logic without DB."""

    def test_health_thresholds_from_config(self):
        assert settings.HEALTH_CONSECUTIVE_ERROR_THRESHOLD == 3
        assert settings.HEALTH_COOLDOWN_SECONDS == 300
        assert settings.HEALTH_RECOVERY_SUCCESSES == 5

    def test_feature_flags_exist(self):
        assert hasattr(settings, "MODEL_SELECTION_ENABLED")
        assert hasattr(settings, "OPERATION_METERING_ENABLED")
        assert hasattr(settings, "MODEL_TASK_HEALTH_ROUTING_ENABLED")
        assert hasattr(settings, "INGESTION_ESTIMATION_V2_ENABLED")


# ---------------------------------------------------------------------------
# Model import tests
# ---------------------------------------------------------------------------


class TestModelImports:
    """Verify all new models are importable."""

    def test_import_model_pricing(self):
        from app.models.credits import ModelPricing
        assert ModelPricing.__tablename__ == "model_pricing"

    def test_import_task_model_assignment(self):
        from app.models.credits import TaskModelAssignment
        assert TaskModelAssignment.__tablename__ == "task_model_assignment"

    def test_import_billing_operation(self):
        from app.models.credits import BillingOperation
        assert BillingOperation.__tablename__ == "billing_operation"

    def test_import_billing_usage_line(self):
        from app.models.credits import BillingUsageLine
        assert BillingUsageLine.__tablename__ == "billing_usage_line"

    def test_import_model_task_health(self):
        from app.models.credits import ModelTaskHealth
        assert ModelTaskHealth.__tablename__ == "model_task_health"

    def test_models_init_exports(self):
        from app.models import (
            ModelPricing,
            TaskModelAssignment,
            BillingOperation,
            BillingUsageLine,
            ModelTaskHealth,
        )
        assert ModelPricing is not None

    def test_user_profile_model_preferences(self):
        from app.models.session import UserProfile
        # Check column exists on the mapper
        assert "model_preferences" in UserProfile.__table__.columns.keys()


# ---------------------------------------------------------------------------
# CM-018: Observability helper tests
# ---------------------------------------------------------------------------


class TestObservabilityHelpers:
    """Test structured telemetry helpers emit valid payloads."""

    def test_emit_cost_drift(self, caplog):
        import logging
        from app.services.telemetry.billing_events import emit_cost_drift

        with caplog.at_level(logging.INFO, logger="billing.telemetry"):
            emit_cost_drift(
                user_id="u1",
                operation_id="op1",
                operation_type="tutor_turn",
                estimated_credits=100,
                actual_credits=150,
                model_id="gpt-5-mini",
            )
        assert "cost_drift" in caplog.text
        assert "50.0" in caplog.text  # 50% drift

    def test_emit_cost_drift_zero_estimate(self, caplog):
        import logging
        from app.services.telemetry.billing_events import emit_cost_drift

        with caplog.at_level(logging.INFO, logger="billing.telemetry"):
            emit_cost_drift(
                user_id="u1",
                operation_id="op1",
                operation_type="tutor_turn",
                estimated_credits=0,
                actual_credits=50,
                model_id="gpt-5-mini",
            )
        assert "cost_drift" in caplog.text

    def test_emit_reroute(self, caplog):
        import logging
        from app.services.telemetry.billing_events import emit_reroute

        with caplog.at_level(logging.INFO, logger="billing.telemetry"):
            emit_reroute(
                user_id="u1",
                task="tutor_turn",
                selected_model_id="gpt-5",
                routed_model_id="gemini-3.1-flash-lite",
                reason="cooldown",
            )
        assert "model_reroute" in caplog.text
        assert "cooldown" in caplog.text

    def test_emit_cooldown_event(self, caplog):
        import logging
        from app.services.telemetry.billing_events import emit_cooldown_event

        with caplog.at_level(logging.INFO, logger="billing.telemetry"):
            emit_cooldown_event(
                model_id="gpt-5",
                task="tutor_turn",
                action="entered",
                error_rate=3.0,
                cooldown_until="2026-03-12T00:05:00+00:00",
            )
        assert "cooldown.entered" in caplog.text

    def test_emit_estimation_quality_within_range(self, caplog):
        import logging
        from app.services.telemetry.billing_events import emit_estimation_quality

        with caplog.at_level(logging.INFO, logger="billing.telemetry"):
            emit_estimation_quality(
                operation_type="ingestion",
                model_id="gpt-5-mini",
                estimated_low=50.0,
                estimated_high=200.0,
                actual=150.0,
            )
        assert "estimation_quality" in caplog.text
        assert '"within_range": true' in caplog.text

    def test_emit_estimation_quality_out_of_range(self, caplog):
        import logging
        from app.services.telemetry.billing_events import emit_estimation_quality

        with caplog.at_level(logging.INFO, logger="billing.telemetry"):
            emit_estimation_quality(
                operation_type="ingestion",
                model_id="gpt-5-mini",
                estimated_low=50.0,
                estimated_high=200.0,
                actual=500.0,
            )
        assert "estimation_quality" in caplog.text
        assert '"within_range": false' in caplog.text


# ---------------------------------------------------------------------------
# CM-015: TutorTurnResponse schema tests
# ---------------------------------------------------------------------------


class TestTutorTurnResponseSchema:
    """Test that the turn response includes model routing fields."""

    def test_model_routing_fields_in_response(self):
        from app.schemas.api import TutorTurnResponse
        resp = TutorTurnResponse(
            turn_id=uuid.uuid4(),
            response="Hello",
            selected_model_id="gpt-5",
            routed_model_id="gemini-3.1-flash-lite",
            reroute_reason="cooldown",
        )
        assert resp.selected_model_id == "gpt-5"
        assert resp.routed_model_id == "gemini-3.1-flash-lite"
        assert resp.reroute_reason == "cooldown"

    def test_model_routing_fields_optional(self):
        from app.schemas.api import TutorTurnResponse
        resp = TutorTurnResponse(
            turn_id=uuid.uuid4(),
            response="Hello",
        )
        assert resp.selected_model_id is None
        assert resp.routed_model_id is None
        assert resp.reroute_reason is None

    def test_model_routing_serialization(self):
        from app.schemas.api import TutorTurnResponse
        resp = TutorTurnResponse(
            turn_id=uuid.uuid4(),
            response="Hello",
            selected_model_id="gpt-5",
        )
        data = resp.model_dump()
        assert "selected_model_id" in data
        assert "routed_model_id" in data
        assert "reroute_reason" in data


# ---------------------------------------------------------------------------
# CM-005: TurnResult token field tests
# ---------------------------------------------------------------------------


class TestTurnResultTokenFields:
    """Test that TurnResult includes token tracking fields."""

    def test_token_fields_default(self):
        from app.services.tutor_runtime.types import TurnResult
        result = TurnResult(
            turn_id="t1",
            tutor_response="Hello",
            tutor_question=None,
            current_step=None,
            current_step_index=0,
            step_transition=None,
            mastery_delta=None,
            session_complete=False,
            focus_concepts=[],
            awaiting_evaluation=False,
            action="explain",
            concept="test",
            mastery={},
            objective_progress={},
        )
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.stage_token_usage == {}

    def test_token_fields_set(self):
        from app.services.tutor_runtime.types import TurnResult
        result = TurnResult(
            turn_id="t1",
            tutor_response="Hello",
            tutor_question=None,
            current_step=None,
            current_step_index=0,
            step_transition=None,
            mastery_delta=None,
            session_complete=False,
            focus_concepts=[],
            awaiting_evaluation=False,
            action="explain",
            concept="test",
            mastery={},
            objective_progress={},
            prompt_tokens=800,
            completion_tokens=400,
            stage_token_usage={"policy": {"prompt": 200, "completion": 100}},
        )
        assert result.prompt_tokens == 800
        assert result.completion_tokens == 400
        assert "policy" in result.stage_token_usage


# ---------------------------------------------------------------------------
# BaseLLMProvider total_tokens_used property test
# ---------------------------------------------------------------------------


class TestBaseLLMProviderTokens:
    """Test BaseLLMProvider.total_tokens_used property."""

    def test_total_tokens_used_default(self):
        from app.services.llm.base import BaseLLMProvider
        # BaseLLMProvider has abstract methods so we can't instantiate it directly,
        # but we can test the property is defined
        assert hasattr(BaseLLMProvider, "total_tokens_used")

    def test_total_tokens_used_structure(self):
        """Verify the interface contract of total_tokens_used."""
        from app.services.llm.base import BaseLLMProvider

        class DummyProvider(BaseLLMProvider):
            async def generate(self, *args, **kwargs):
                return ""
            async def generate_json(self, *args, **kwargs):
                return {}
            async def count_tokens(self, text: str) -> int:
                return 0
            @property
            def model_id(self) -> str:
                return "dummy"

        provider = DummyProvider.__new__(DummyProvider)
        tokens = provider.total_tokens_used
        assert "prompt_tokens" in tokens
        assert "completion_tokens" in tokens
        assert "total_tokens" in tokens
