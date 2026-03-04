import asyncio
from types import SimpleNamespace

import pytest

from app.services.tutor_runtime.retrieval_runner import retrieve_knowledge


class _NoopRetriever:
    async def retrieve(self, **kwargs):  # pragma: no cover
        return SimpleNamespace(chunks=[])


def test_retrieve_knowledge_rejects_session_resource_outside_notebook_scope():
    retriever = _NoopRetriever()
    session = SimpleNamespace(resource_id="resource-outside-notebook")
    plan = {}

    with pytest.raises(ValueError, match="outside notebook scope"):
        asyncio.run(
            retrieve_knowledge(
                retriever=retriever,
                session=session,
                plan=plan,
                student_message="Explain this concept",
                target_concepts=["heat_transfer"],
                step_type="explain",
                step_goal="Explain heat transfer fundamentals",
                notebook_id="nb-123",
                notebook_resource_ids=["resource-inside-notebook"],
                lf=None,
            )
        )
