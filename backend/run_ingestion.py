#!/usr/bin/env python3
"""Run ingestion pipeline for a local file.

Canonical local runner for manual ingestion testing.
"""
import argparse
import asyncio
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.resource import Resource
from app.services.embedding.factory import create_embedding_provider
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.llm.openai_provider import OpenAICompatibleProvider
from app.services.storage.factory import create_storage_provider


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TutorAI ingestion for a PDF/resource file")
    parser.add_argument(
        "--pdf-path",
        default="/tmp/MTL106.pdf",
        help="Absolute path to the source file",
    )
    parser.add_argument(
        "--filename",
        default="MTL106.pdf",
        help="Logical filename stored in resource metadata",
    )
    parser.add_argument(
        "--topic",
        default="General",
        help="Resource topic label",
    )
    return parser


async def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    source_path = Path(args.pdf_path)
    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")

    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    llm = OpenAICompatibleProvider(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE_URL,
        model=settings.LLM_MODEL,
    )
    embedding = create_embedding_provider(settings)
    storage = create_storage_provider(settings)

    try:
        resource_id = uuid.uuid4()
        async with async_session() as session:
            resource = Resource(
                id=resource_id,
                filename=args.filename,
                file_path_or_uri=str(source_path),
                topic=args.topic,
                status="processing",
            )
            session.add(resource)
            await session.commit()

        async with async_session() as session:
            pipeline = IngestionPipeline(session, llm, embedding, storage)
            result = await pipeline.run(resource_id)

        print("\n" + "=" * 60)
        print("INGESTION COMPLETE")
        print("=" * 60)
        print(f"Resource ID: {resource_id}")
        print(f"Status: {result.get('status')}")
        print("\nMetrics:")
        metrics = result.get("quality", {})
        for key, value in sorted(metrics.items()):
            print(f"  {key}: {value}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
