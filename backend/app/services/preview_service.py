from __future__ import annotations

from html import escape
from pathlib import Path
import re
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET

import fitz


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}

AI_HIGHLIGHT_HEX = "#4fcbd6"
AI_PDF_HIGHLIGHT_COLOR = (0.31, 0.80, 0.84)

WORD_HIGHLIGHT_CLASSES = {
    "yellow": "doc-highlight-yellow",
    "cyan": "doc-highlight-cyan",
    "turquoise": "doc-highlight-cyan",
    "green": "doc-highlight-green",
    "brightgreen": "doc-highlight-green",
    "magenta": "doc-highlight-pink",
    "pink": "doc-highlight-pink",
    "darkmagenta": "doc-highlight-violet",
    "violet": "doc-highlight-violet",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(node: ET.Element, name: str, default: str = "") -> str:
    return str(node.get(f"{{{W}}}{name}", default))


def _word_comments(package: ZipFile) -> dict[str, dict[str, str]]:
    if "word/comments.xml" not in package.namelist():
        return {}
    root = ET.fromstring(package.read("word/comments.xml"))
    comments: dict[str, dict[str, str]] = {}
    for item in root.findall("w:comment", NS):
        comment_id = _attr(item, "id")
        comments[comment_id] = {
            "author": _attr(item, "author") or "未署名",
            "date": _attr(item, "date"),
            "text": "".join(node.text or "" for node in item.findall(".//w:t", NS)).strip(),
        }
    return comments


def _value(row: Any, name: str, default: str = "") -> str:
    if isinstance(row, dict):
        return str(row.get(name, default) or default)
    return str(getattr(row, name, default) or default)


def _link_ai_comments_to_risks(
    comments: dict[str, dict[str, str]],
    risks: Iterable[Any] | None,
) -> None:
    """Attach persisted risk ids to Word AI comment ranges.

    python-docx assigns numeric comment ids, while the review UI uses the
    persisted suggestion UUID.  The generated comment body contains the risk
    title, so title plus occurrence order provides a stable bridge without
    exposing an internal UUID in the downloaded Word comment.
    """
    available = [
        {
            "id": _value(row, "id"),
            "title": _value(row, "title"),
            "suggested_text": _value(row, "suggested_text"),
        }
        for row in (risks or [])
        if _value(row, "id")
    ]
    used: set[int] = set()
    for comment in comments.values():
        if "契析 AI审核" not in comment.get("author", ""):
            continue
        body = comment.get("text", "")
        header = body.split("\n", 1)[0]
        title = header.split("】", 1)[-1].strip() if "】" in header else ""
        match_index = next(
            (
                index
                for index, row in enumerate(available)
                if index not in used
                and row["suggested_text"]
                and row["suggested_text"][:120] in body
            ),
            None,
        )
        if match_index is None:
            match_index = next(
                (
                    index
                    for index, row in enumerate(available)
                    if index not in used and row["title"] and row["title"] == title
                ),
                None,
            )
        if match_index is None:
            match_index = next(
                (
                    index
                    for index, row in enumerate(available)
                    if index not in used and row["title"] and row["title"] in body
                ),
                None,
            )
        if match_index is not None:
            comment["risk_id"] = available[match_index]["id"]
            used.add(match_index)


def _element_text(element: ET.Element) -> str:
    return "".join(
        node.text or ""
        for node in element.iter()
        if _local_name(node.tag) in {"t", "delText", "instrText"}
    )


def _fallback_risk_links(
    body: ET.Element,
    comments: dict[str, dict[str, str]],
    risks: Iterable[Any] | None,
) -> dict[int, list[str]]:
    """Link risks without a Word comment to the best matching paragraph or row."""
    linked_ids = {
        comment.get("risk_id", "")
        for comment in comments.values()
        if comment.get("risk_id")
    }
    candidates: list[tuple[ET.Element, str]] = []
    for element in body.iter():
        if _local_name(element.tag) not in {"p", "tr"}:
            continue
        compact = re.sub(r"\s+", "", _element_text(element))
        if compact:
            candidates.append((element, compact))

    links: dict[int, list[str]] = {}
    for risk in risks or []:
        risk_id = _value(risk, "id")
        if not risk_id or risk_id in linked_ids:
            continue
        evidence = _value(risk, "anchor_text") or _value(risk, "original_text")
        raw_tokens = re.split(r"[|｜\n\r；;。]", evidence)
        tokens = list(
            dict.fromkeys(
                token
                for token in (re.sub(r"\s+", "", item) for item in raw_tokens)
                if len(token) >= 2
            )
        )
        if not tokens:
            tokens = [re.sub(r"\s+", "", evidence)]
        best: tuple[tuple[int, int, int], ET.Element] | None = None
        for element, compact in candidates:
            matched = [token for token in tokens if token and token in compact]
            if not matched:
                continue
            longest = max(len(token) for token in matched)
            if len(matched) < 2 and longest < 10:
                continue
            score = (len(matched), sum(len(token) for token in matched), -len(compact))
            if best is None or score > best[0]:
                best = (score, element)
        if best is not None:
            links.setdefault(id(best[1]), []).append(risk_id)
    return links


def _risk_html_attrs(element: ET.Element, risk_links: dict[int, list[str]]) -> str:
    risk_ids = risk_links.get(id(element), [])
    if not risk_ids:
        return ""
    escaped_ids = [escape(risk_id, quote=True) for risk_id in risk_ids]
    return (
        ' class="doc-ai-risk-fallback"'
        f' data-risk-id="{escaped_ids[0]}"'
        f' data-risk-ids="{" ".join(escaped_ids)}"'
        ' role="button" tabindex="0" title="点击定位到对应风险项"'
    )


def _run_html(run: ET.Element, active_comments: set[str], comments: dict[str, dict[str, str]], mode: str = "") -> str:
    pieces: list[str] = []
    for node in run.iter():
        name = _local_name(node.tag)
        if name in {"t", "delText", "instrText"} and node.text:
            pieces.append(escape(node.text))
        elif name == "tab":
            pieces.append("&emsp;")
        elif name in {"br", "cr"}:
            pieces.append("<br />")
    if run.find(".//w:drawing", NS) is not None or run.find(".//w:pict", NS) is not None:
        pieces.append('<span class="doc-image-placeholder">[合同内图片]</span>')
    value = "".join(pieces)
    if not value:
        return ""
    classes: list[str] = []
    highlight = run.find("./w:rPr/w:highlight", NS)
    shading = run.find("./w:rPr/w:shd", NS)
    if highlight is not None and _attr(highlight, "val", "none") not in {"none", "clear"}:
        classes.append("doc-highlight")
        color_class = WORD_HIGHLIGHT_CLASSES.get(_attr(highlight, "val").casefold())
        if color_class:
            classes.append(color_class)
    if shading is not None and _attr(shading, "fill", "auto") not in {"auto", "FFFFFF", "ffffff"}:
        classes.append("doc-highlight")
    if active_comments:
        classes.append("doc-comment-range")
        if any("契析 AI审核" in comments.get(comment_id, {}).get("author", "") for comment_id in active_comments):
            classes.append("doc-ai-highlight")
    if mode == "ins":
        classes.append("doc-track-insert")
    elif mode == "del":
        classes.append("doc-track-delete")
    class_attr = f' class="{" ".join(classes)}"' if classes else ""
    risk_ids = [comments.get(comment_id, {}).get("risk_id", "") for comment_id in active_comments]
    risk_id = next((item for item in risk_ids if item), "")
    risk_attr = (
        f' data-risk-id="{escape(risk_id, quote=True)}" role="button" tabindex="0" title="点击定位到对应风险项"'
        if risk_id
        else ""
    )
    return f"<span{class_attr}{risk_attr}>{value}</span>"


def _children_html(
    container: ET.Element,
    comments: dict[str, dict[str, str]],
    active_comments: set[str],
    mode: str = "",
) -> str:
    html: list[str] = []
    for child in list(container):
        name = _local_name(child.tag)
        if name == "commentRangeStart":
            active_comments.add(_attr(child, "id"))
            continue
        if name == "commentRangeEnd":
            comment_id = _attr(child, "id")
            comment = comments.get(comment_id, {})
            title = escape(f"{comment.get('author', '批注')}：{comment.get('text', '')}", quote=True)
            risk_id = comment.get("risk_id", "")
            risk_attr = (
                f' data-risk-id="{escape(risk_id, quote=True)}" role="button" tabindex="0"'
                if risk_id
                else ""
            )
            html.append(
                f'<span class="doc-comment-marker"{risk_attr} title="{title}">批注{escape(comment_id)}</span>'
            )
            active_comments.discard(comment_id)
            continue
        if name == "r":
            html.append(_run_html(child, active_comments, comments, mode))
            continue
        if name in {"ins", "del", "moveFrom", "moveTo"}:
            nested_mode = "del" if name in {"del", "moveFrom"} else "ins"
            html.append(_children_html(child, comments, active_comments, nested_mode))
            continue
        if name in {"hyperlink", "smartTag", "sdt", "sdtContent", "customXml"}:
            html.append(_children_html(child, comments, active_comments, mode))
    return "".join(html)


def _paragraph_html(
    paragraph: ET.Element,
    comments: dict[str, dict[str, str]],
    active_comments: set[str],
    risk_links: dict[int, list[str]],
) -> str:
    body = _children_html(paragraph, comments, active_comments)
    risk_attrs = _risk_html_attrs(paragraph, risk_links)
    if not body.strip():
        return f'<p class="doc-empty"{risk_attrs}>&nbsp;</p>'
    style = paragraph.find("./w:pPr/w:pStyle", NS)
    style_name = _attr(style, "val").casefold() if style is not None else ""
    if style_name in {"title", "标题"}:
        tag = "h1"
    elif "heading1" in style_name or "标题1" in style_name:
        tag = "h2"
    elif "heading2" in style_name or "标题2" in style_name:
        tag = "h3"
    else:
        tag = "p"
    return f"<{tag}{risk_attrs}>{body}</{tag}>"


def _cell_html(
    cell: ET.Element,
    comments: dict[str, dict[str, str]],
    active_comments: set[str],
    risk_links: dict[int, list[str]],
) -> str:
    rows: list[str] = []
    for child in list(cell):
        name = _local_name(child.tag)
        if name == "p":
            rows.append(_paragraph_html(child, comments, active_comments, risk_links))
        elif name == "tbl":
            rows.append(_table_html(child, comments, active_comments, risk_links))
    return "".join(rows)


def _table_html(
    table: ET.Element,
    comments: dict[str, dict[str, str]],
    active_comments: set[str],
    risk_links: dict[int, list[str]],
) -> str:
    rows: list[str] = []
    for row in table.findall("./w:tr", NS):
        cells = [
            f"<td>{_cell_html(cell, comments, active_comments, risk_links)}</td>"
            for cell in row.findall("./w:tc", NS)
        ]
        rows.append(f"<tr{_risk_html_attrs(row, risk_links)}>{''.join(cells)}</tr>")
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def render_docx_preview(path: Path, risks: Iterable[Any] | None = None) -> dict:
    """Return safe HTML that keeps Word highlights, comment ranges and tracked changes visible."""
    try:
        with ZipFile(path) as package:
            root = ET.fromstring(package.read("word/document.xml"))
            comments = _word_comments(package)
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError(f"无法读取 Word 预览：{exc}") from exc

    _link_ai_comments_to_risks(comments, risks)
    body = root.find("w:body", NS)
    if body is None:
        raise ValueError("Word 正文结构不存在")
    active_comments: set[str] = set()
    risk_links = _fallback_risk_links(body, comments, risks)
    blocks: list[str] = []
    for child in list(body):
        name = _local_name(child.tag)
        if name == "p":
            blocks.append(_paragraph_html(child, comments, active_comments, risk_links))
        elif name == "tbl":
            blocks.append(_table_html(child, comments, active_comments, risk_links))
    return {
        "html": f'<article class="docx-preview-page">{"".join(blocks)}</article>',
        "embedded_comment_count": len(comments),
    }


def _risk_candidates(value: str) -> list[str]:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if not compact:
        return []
    candidates: list[str] = []
    for piece in re.split(r"(?<=[。；;！？!?])", compact):
        piece = piece.strip()
        if len(re.sub(r"\s+", "", piece)) >= 8:
            candidates.append(piece[:180])
            for start in range(0, min(len(piece), 180), 45):
                part = piece[start : start + 70].strip()
                if len(re.sub(r"\s+", "", part)) >= 8:
                    candidates.append(part)
    candidates.append(compact[:180])
    return list(dict.fromkeys(candidates))[:14]


def locate_pdf_risks(path: Path, risks: Iterable[Any]) -> dict[str, list[dict[str, float | int]]]:
    """Locate review evidence in a PDF and return scale-independent hit boxes."""
    locations: dict[str, list[dict[str, float | int]]] = {}
    with fitz.open(path) as document:
        for risk in risks:
            risk_id = _value(risk, "id")
            if not risk_id:
                continue
            try:
                preferred_page = int(_value(risk, "page_no", "0") or 0)
            except ValueError:
                preferred_page = 0
            page_numbers = list(range(document.page_count))
            if 1 <= preferred_page <= document.page_count:
                page_numbers.remove(preferred_page - 1)
                page_numbers.insert(0, preferred_page - 1)
            found: list[dict[str, float | int]] = []
            evidence = _value(risk, "anchor_text") or _value(risk, "original_text")
            for page_index in page_numbers:
                page = document[page_index]
                rects: list[fitz.Rect] = []
                for candidate in _risk_candidates(evidence):
                    rects = page.search_for(candidate, quads=False)
                    if rects:
                        break
                if not rects:
                    continue
                page_rect = page.rect
                for rect in rects[:12]:
                    found.append(
                        {
                            "page_no": page_index + 1,
                            "x": round(rect.x0 / page_rect.width * 100, 4),
                            "y": round(rect.y0 / page_rect.height * 100, 4),
                            "width": round(rect.width / page_rect.width * 100, 4),
                            "height": round(rect.height / page_rect.height * 100, 4),
                        }
                    )
                break
            locations[risk_id] = found
    return locations


def prepare_pdf_preview(path: Path) -> Path:
    """Create a browser-preview copy with every AI annotation normalized to cyan-blue."""
    output = path.with_name(f"{path.stem}.web-preview-cyan-v2.pdf")
    if output.exists() and output.stat().st_mtime >= path.stat().st_mtime:
        return output
    with fitz.open(path) as document:
        for page in document:
            annotation = page.first_annot
            ai_highlight_chain = False
            while annotation:
                info = annotation.info
                title = str(info.get("title", ""))
                is_ai_start = "契析 AI审核" in title
                is_ai_continuation = (
                    ai_highlight_chain
                    and annotation.type[1] == "Highlight"
                    and not title
                    and not info.get("subject")
                    and not info.get("content")
                )
                if is_ai_start or is_ai_continuation:
                    annotation.set_colors(stroke=AI_PDF_HIGHLIGHT_COLOR)
                    annotation.update()
                ai_highlight_chain = is_ai_start or is_ai_continuation
                annotation = annotation.next
        document.save(output, garbage=4, deflate=True)
    return output
