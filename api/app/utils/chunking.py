from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class TextChunk:
    text: str
    metadata: dict
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def _split_long_block(text: str, chunk_size: int = 700, overlap: int = 100) -> list[str]:
    words = text.split()
    if len(words) <= chunk_size:
        return [text.strip()]

    out: list[str] = []
    i = 0
    while i < len(words):
        block = words[i : i + chunk_size]
        if not block:
            break
        out.append(" ".join(block).strip())
        if i + chunk_size >= len(words):
            break
        i = max(0, i + chunk_size - overlap)
    return out


def chunk_markdown_heading_aware(text: str) -> list[TextChunk]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading = "Document"
    current_lines: list[str] = []

    for line in lines:
        if line.strip().startswith("#"):
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line.strip().lstrip("#").strip() or "Section"
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))

    chunks: list[TextChunk] = []
    idx = 0
    for heading, content_lines in sections:
        block = "\n".join(content_lines).strip()
        if not block:
            continue
        for sub in _split_long_block(block):
            chunks.append(
                TextChunk(
                    text=sub,
                    metadata={"heading": heading, "section_index": idx},
                    token_count=estimate_tokens(sub),
                )
            )
            idx += 1
    return chunks


def chunk_pdf_pages(pages: Iterable[str]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for i, page in enumerate(pages, start=1):
        if not page.strip():
            continue
        for sub in _split_long_block(page):
            chunks.append(TextChunk(text=sub, metadata={"page": i}, token_count=estimate_tokens(sub)))
    return chunks


def chunk_slides(slides: Iterable[str]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for i, slide in enumerate(slides, start=1):
        content = slide.strip()
        if not content:
            continue
        chunks.append(TextChunk(text=content, metadata={"slide": i}, token_count=estimate_tokens(content)))
    return chunks


def chunk_transcript_turns(
    turns: list[dict],
    speaker_map: dict[str, dict],
    min_seconds: int = 45,
    max_seconds: int = 90,
    max_tokens: int = 700,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    window: list[str] = []
    start_sec: int | None = None
    end_sec: int | None = None

    def flush() -> None:
        nonlocal window, start_sec, end_sec
        if not window or start_sec is None or end_sec is None:
            return
        text = "\n".join(window).strip()
        chunks.append(
            TextChunk(
                text=text,
                metadata={"start_time_sec": start_sec, "end_time_sec": end_sec},
                token_count=estimate_tokens(text),
            )
        )
        window = []
        start_sec = None
        end_sec = None

    for turn in turns:
        speaker_id = turn.get("speaker_id", "UNK")
        speaker = speaker_map.get(speaker_id, {}).get("role") or speaker_map.get(speaker_id, {}).get("name") or speaker_id
        t0 = int(turn.get("start_time_sec", 0))
        t1 = int(turn.get("end_time_sec", t0))
        if start_sec is None:
            start_sec = t0
        end_sec = t1
        hh = t0 // 3600
        mm = (t0 % 3600) // 60
        ss = t0 % 60
        line = f"{hh:02d}:{mm:02d}:{ss:02d} {speaker}: {turn.get('text', '').strip()}"
        window.append(line)

        duration = (end_sec - start_sec) if start_sec is not None and end_sec is not None else 0
        token_count = estimate_tokens("\n".join(window))
        if duration >= min_seconds and (duration >= max_seconds or token_count >= max_tokens):
            flush()

    flush()
    return chunks
