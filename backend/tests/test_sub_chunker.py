from app.services.ingestion.ingestion_types import ChunkData, token_len
from app.services.ingestion.sub_chunker import SubChunker


def test_sub_chunker_stays_below_500_tokens():
    chunk = ChunkData(
        chunk_index=0,
        text=" ".join(
            [
                f"Sentence {i}. This is a longer sentence for splitting."
                for i in range(120)
            ]
        ),
        section_heading="Intro",
        page_start=1,
        page_end=2,
        metadata={},
    )

    result = SubChunker(target_tokens=448, min_tokens=128, overlap_tokens=64).sub_chunk(
        [chunk]
    )

    assert result.sub_chunks
    assert max(token_len(sc.text) for sc in result.sub_chunks) < 500


def test_sub_chunker_splits_oversized_single_sentence_below_500_tokens():
    chunk = ChunkData(
        chunk_index=0,
        text=" ".join([f"thermodynamics_token_{i}" for i in range(1200)]),
        section_heading="Intro",
        page_start=1,
        page_end=1,
        metadata={},
    )

    result = SubChunker(target_tokens=448, min_tokens=128, overlap_tokens=64).sub_chunk(
        [chunk]
    )

    assert len(result.sub_chunks) > 1
    assert max(token_len(sc.text) for sc in result.sub_chunks) < 500
