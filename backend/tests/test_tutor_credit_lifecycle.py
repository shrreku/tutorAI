import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import tutor as tutor_module
from app.config import settings
from app.schemas.api import TutorTurnRequest


class _DummyDb:
    pass


def _build_result():
    return SimpleNamespace(
        turn_id=str(uuid4()),
        tutor_response="response",
        tutor_question="question",
        current_step="step",
        current_step_index=1,
        objective_id=None,
        objective_title=None,
        step_transition="continue",
        mastery_delta=None,
        session_complete=False,
        focus_concepts=["limits"],
        awaiting_evaluation=False,
        session_summary=None,
        study_map_snapshot=None,
        prompt_tokens=120,
        completion_tokens=45,
    )


def _patch_turn_dependencies(monkeypatch, *, result=None, pipeline_error=None):
    session_id = uuid4()
    notebook_id = uuid4()
    user_id = uuid4()

    async def _fake_verify_session_owner(*_args, **_kwargs):
        return None

    async def _fake_verify_notebook_session_link(*_args, **_kwargs):
        return SimpleNamespace(id=uuid4())

    class _SessionRepo:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _session_id):
            return SimpleNamespace(id=session_id, user_id=user_id, status="active")

    class _NotebookResourceRepo:
        def __init__(self, _db):
            pass

        async def list_active_resource_ids(self, _notebook_id):
            return []

    class _Pipeline:
        def __init__(self):
            # CM-005: Mock tutor/evaluator LLM providers for token tracking
            self.tutor = SimpleNamespace(
                llm=SimpleNamespace(
                    total_tokens_used={
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    }
                )
            )
            self.evaluator = SimpleNamespace(
                llm=SimpleNamespace(
                    total_tokens_used={
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    }
                )
            )

        async def execute_turn(self, **_kwargs):
            if pipeline_error is not None:
                raise pipeline_error
            return result or _build_result()

    monkeypatch.setattr(
        tutor_module, "verify_session_owner", _fake_verify_session_owner
    )
    monkeypatch.setattr(
        tutor_module, "verify_notebook_session_link", _fake_verify_notebook_session_link
    )
    monkeypatch.setattr(tutor_module, "SessionRepository", _SessionRepo)
    monkeypatch.setattr(
        tutor_module, "NotebookResourceRepository", _NotebookResourceRepo
    )
    monkeypatch.setattr(
        tutor_module, "get_turn_pipeline", lambda *_args, **_kwargs: _Pipeline()
    )

    return notebook_id, session_id, SimpleNamespace(id=user_id)


def test_notebook_turn_platform_key_reserves_and_finalizes(monkeypatch):
    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)

    calls = {"reserve": [], "finalize": [], "release": []}

    class _Meter:
        def __init__(self, _db):
            pass

        async def estimate_turn_credits(self, model_id, **_kwargs):
            calls.setdefault("estimate", []).append(model_id)
            return 450

        async def reserve_for_turn(self, user_id, turn_id, estimated_credits):
            calls["reserve"].append((user_id, turn_id, estimated_credits))
            return estimated_credits

        async def finalize_turn(
            self,
            user_id,
            turn_id,
            model_id,
            prompt_tokens,
            completion_tokens,
            reserved_credits,
        ):
            calls["finalize"].append(
                (
                    user_id,
                    turn_id,
                    model_id,
                    prompt_tokens,
                    completion_tokens,
                    reserved_credits,
                )
            )
            return 248

        async def release_turn(self, user_id, turn_id, reserved_credits):
            calls["release"].append((user_id, turn_id, reserved_credits))

    monkeypatch.setattr(tutor_module, "CreditMeter", _Meter)
    notebook_id, session_id, user = _patch_turn_dependencies(monkeypatch)

    response = asyncio.run(
        tutor_module.execute_notebook_turn(
            notebook_id=notebook_id,
            request=TutorTurnRequest(session_id=session_id, message="teach me"),
            db=_DummyDb(),
            user=user,
            byok={"api_key": None, "api_base_url": None},
            x_llm_model_tutoring=None,
            x_llm_model_evaluation=None,
        )
    )

    assert response.response == "response"
    assert len(calls["reserve"]) == 1
    assert len(calls["finalize"]) == 1
    assert calls["finalize"][0][-1] == 450
    assert calls["release"] == []


def test_notebook_turn_byok_bypasses_platform_credit_meter(monkeypatch):
    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)

    calls = {"reserve": 0, "finalize": 0, "release": 0}

    class _Meter:
        def __init__(self, _db):
            pass

        async def estimate_turn_credits(self, *_args, **_kwargs):
            return 450

        async def reserve_for_turn(self, *_args, **_kwargs):
            calls["reserve"] += 1
            return 2000

        async def finalize_turn(self, *_args, **_kwargs):
            calls["finalize"] += 1
            return 0

        async def release_turn(self, *_args, **_kwargs):
            calls["release"] += 1

    monkeypatch.setattr(tutor_module, "CreditMeter", _Meter)
    notebook_id, session_id, user = _patch_turn_dependencies(monkeypatch)

    response = asyncio.run(
        tutor_module.execute_notebook_turn(
            notebook_id=notebook_id,
            request=TutorTurnRequest(session_id=session_id, message="teach me"),
            db=_DummyDb(),
            user=user,
            byok={
                "api_key": "sk-user-key",
                "api_base_url": "https://api.example.com/v1",
            },
            x_llm_model_tutoring=None,
            x_llm_model_evaluation=None,
        )
    )

    assert response.response == "response"
    assert calls == {"reserve": 0, "finalize": 0, "release": 0}


def test_notebook_turn_returns_payment_required_on_insufficient_balance(monkeypatch):
    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)

    class _Meter:
        def __init__(self, _db):
            pass

        async def estimate_turn_credits(self, *_args, **_kwargs):
            return 450

        async def reserve_for_turn(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(tutor_module, "CreditMeter", _Meter)
    notebook_id, session_id, user = _patch_turn_dependencies(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            tutor_module.execute_notebook_turn(
                notebook_id=notebook_id,
                request=TutorTurnRequest(session_id=session_id, message="teach me"),
                db=_DummyDb(),
                user=user,
                byok={"api_key": None, "api_base_url": None},
                x_llm_model_tutoring=None,
                x_llm_model_evaluation=None,
            )
        )

    assert exc.value.status_code == 402
    assert "Insufficient credits" in str(exc.value.detail)


def test_notebook_turn_releases_reservation_on_pipeline_failure(monkeypatch):
    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)

    calls = {"release": []}

    class _Meter:
        def __init__(self, _db):
            pass

        async def estimate_turn_credits(self, *_args, **_kwargs):
            return 450

        async def reserve_for_turn(self, *_args, **_kwargs):
            return 450

        async def finalize_turn(self, *_args, **_kwargs):
            raise AssertionError("finalize_turn should not run on failure")

        async def release_turn(self, user_id, turn_id, reserved_credits):
            calls["release"].append((user_id, turn_id, reserved_credits))

    monkeypatch.setattr(tutor_module, "CreditMeter", _Meter)
    notebook_id, session_id, user = _patch_turn_dependencies(
        monkeypatch,
        pipeline_error=RuntimeError("LLM offline"),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            tutor_module.execute_notebook_turn(
                notebook_id=notebook_id,
                request=TutorTurnRequest(session_id=session_id, message="teach me"),
                db=_DummyDb(),
                user=user,
                byok={"api_key": None, "api_base_url": None},
                x_llm_model_tutoring=None,
                x_llm_model_evaluation=None,
            )
        )

    assert exc.value.status_code == 500
    assert calls["release"]
