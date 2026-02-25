from __future__ import annotations

from app.utils.chunking import chunk_markdown_heading_aware, chunk_transcript_turns


def test_heading_aware_chunking():
    text = "# A\nOne two three\n# B\nFour five six"
    chunks = chunk_markdown_heading_aware(text)
    assert len(chunks) == 2
    assert chunks[0].metadata["heading"] == "A"


def test_transcript_chunking_with_timestamps():
    turns = [
        {"speaker_id": "S1", "start_time_sec": 0, "end_time_sec": 40, "text": "hello"},
        {"speaker_id": "S2", "start_time_sec": 41, "end_time_sec": 100, "text": "world"},
    ]
    speaker_map = {"S1": {"role": "rep"}, "S2": {"role": "customer"}}
    chunks = chunk_transcript_turns(turns, speaker_map)
    assert len(chunks) >= 1
    assert "start_time_sec" in chunks[0].metadata
