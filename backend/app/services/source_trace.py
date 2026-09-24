from __future__ import annotations

import re
from typing import Iterable


NUMERIC_CLAUSE = re.compile(
    r"(?m)^[ \t]*(\d{1,2}(?:\.\d{1,2}){0,3})[.、]?[ \t]*(?=[\u4e00-\u9fff“《])"
)
CHINESE_ARTICLE = re.compile(
    r"(?m)^[ \t]*第([一二三四五六七八九十百零〇0-9]+)条[、，：: \t]*"
)
SECTION_HEADING = re.compile(
    r"(?m)^[ \t]*((?:附件[一二三四五六七八九十0-9]+|第[一二三四五六七八九十百零〇0-9]+章|[一二三四五六七八九十]+、)[^\n]{0,80})"
)


def clause_label_at(text: str, offset: int) -> str:
    """Return the nearest structural clause label preceding ``offset``."""
    source = text or ""
    safe_offset = max(0, min(len(source), int(offset or 0)))
    start = max(0, safe_offset - 6000)
    window = source[start:safe_offset]
    candidates: list[tuple[int, str]] = []
    for match in NUMERIC_CLAUSE.finditer(window):
        candidates.append((match.start(), match.group(1)))
    for match in CHINESE_ARTICLE.finditer(window):
        candidates.append((match.start(), f"第{match.group(1)}条"))
    for match in SECTION_HEADING.finditer(window):
        candidates.append((match.start(), match.group(1).strip()[:40]))
    return max(candidates, default=(-1, ""), key=lambda item: item[0])[1]


def locate_source_span(
    source_map: Iterable[dict] | None,
    start: int,
    end: int,
    *,
    source_file: str = "",
) -> dict:
    """Resolve a text span to a stable source file/page locator."""
    best: tuple[int, dict] | None = None
    for item in source_map or []:
        item_start = int(item.get("start_offset") or 0)
        item_end = int(item.get("end_offset") or item_start)
        overlap = max(0, min(end, item_end) - max(start, item_start))
        contains_start = item_start <= start < item_end
        score = overlap * 10 + (1 if contains_start else 0)
        if score and (best is None or score > best[0]):
            best = (score, item)
    item = best[1] if best else {}
    return {
        "source_file": str(item.get("source_file") or source_file or ""),
        "page_no": item.get("page_no"),
        "page_method": str(item.get("page_method") or ""),
        "block_type": str(item.get("block_type") or ""),
    }


def find_text_span(source: str, quote: str) -> tuple[int, int] | None:
    """Locate an exact or whitespace-insensitive quote in source text."""
    value = str(quote or "").strip()
    if len(value) < 6:
        return None
    direct = source.find(value)
    if direct >= 0:
        return direct, direct + len(value)
    compact_source: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(source):
        if char.isspace():
            continue
        compact_source.append(char)
        offsets.append(index)
    compact_quote = re.sub(r"\s+", "", value)
    compact_index = "".join(compact_source).find(compact_quote)
    if compact_index < 0 or compact_index + len(compact_quote) > len(offsets):
        return None
    start = offsets[compact_index]
    end = offsets[compact_index + len(compact_quote) - 1] + 1
    return start, end
