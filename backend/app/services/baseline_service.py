from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import StandardClause


BASELINE_NAME = "林德（中国）叉车有限公司设备租赁合同的一般性条款"
BASELINE_VERSION = "2025.01"
BASELINE_SOURCE_FILE = "4-CHN-林德（中国）叉车有限公司设备租赁合同的一般性条款--2025年01版.pdf"
BASELINE_TEXT_PATH = Path(__file__).resolve().parents[1] / "data" / "lease_general_terms_2025_01.txt"

SECTION_HEADINGS = {
    "1": "总则", "2": "定义", "3": "租金", "4": "押金", "5": "运费", "6": "付款方式",
    "7": "发票的交付", "8": "设备使用地点", "9": "交付", "10": "验收及异议", "11": "维修与保养",
    "12": "所有权及风险责任", "13": "合同的延长和提前终止", "14": "设备交还", "15": "违约责任",
    "16": "不可抗力", "17": "争议的解决", "18": "通知",
}
SECTION_RISK = {
    "1": "中", "2": "提示", "3": "高", "4": "中", "5": "低", "6": "高", "7": "中", "8": "中",
    "9": "高", "10": "高", "11": "中", "12": "高", "13": "高", "14": "中", "15": "高", "16": "中",
    "17": "中", "18": "低",
}

TOPIC_CHECKS = (
    ("3", ("租金", "超时租金")),
    ("4", ("押金", "保证金")),
    ("6", ("付款", "支付", "账期")),
    ("9", ("交付", "交货")),
    ("10", ("验收", "异议")),
    ("11", ("维修", "保养", "维保")),
    ("12", ("所有权", "风险责任", "设备损坏")),
    ("13", ("续租", "提前终止", "提前解除")),
    ("14", ("返还", "交还", "归还")),
    ("15", ("违约", "赔偿", "责任限制")),
    ("16", ("不可抗力",)),
    ("17", ("争议", "管辖", "仲裁")),
    ("18", ("通知", "送达")),
)


def _chinese_number(value: str) -> str:
    """Render the small section numbers used by contract headings."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    digits = "零一二三四五六七八九"
    if number < 10:
        return digits[number]
    if number < 20:
        return "十" + (digits[number - 10] if number > 10 else "")
    if number < 100:
        return digits[number // 10] + "十" + (digits[number % 10] if number % 10 else "")
    return str(number)


def _insertion_context(text: str, max_chars: int = 360) -> str:
    """Choose a real source fragment as the anchor for a new clause."""
    candidates = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"(?<=[。；！？])", text or "")]
    candidates = [item for item in candidates if len(item) >= 8]
    if not candidates:
        candidates = [re.sub(r"\s+", " ", item).strip() for item in (text or "").splitlines() if item.strip()]
    return (candidates[-1] if candidates else "")[-max_chars:]


def _format_missing_clause(clause_no: str, heading: str, content: str, source_text: str) -> str:
    """Add a section label only when the source document has that numbering style."""
    value = re.sub(r"\s+", " ", str(content or "")).strip()
    if not value:
        return ""
    section = str(clause_no).split(".", 1)[0]
    if re.search(r"第\s*[0-9零一二三四五六七八九十百千万]+\s*(?:条|款|章|节)", source_text or ""):
        return f"第{_chinese_number(section)}条 {heading}\n{value}".strip()
    if re.search(r"(?m)^\s*\d+(?:\.\d+)?[、.．]", source_text or ""):
        return f"{section}. {heading}\n{value}".strip()
    return value


def _normal(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def parse_standard_clauses(text: str) -> list[dict]:
    """Split the source terms into auditable section/sub-clause records."""
    clauses: list[dict] = []
    current_no = ""
    current_lines: list[str] = []
    current_section = ""
    section_intro: dict[str, list[str]] = {}

    def flush() -> None:
        nonlocal current_no, current_lines
        content = re.sub(r"\s+", " ", " ".join(current_lines)).strip()
        if current_no and content:
            section = current_no.split(".", 1)[0]
            clauses.append({
                "clause_no": current_no,
                "heading": SECTION_HEADINGS.get(section, ""),
                "content": content,
                "risk_level": SECTION_RISK.get(section, "提示"),
            })
        current_no, current_lines = "", []

    for raw in text.replace("\r\n", "\n").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line.startswith("General Terms") or "2025年01版" in line or "林 德" in line:
            continue
        heading = re.match(r"^(\d{1,2})\.\s*([\u4e00-\u9fff ]{1,18})$", line)
        if heading:
            flush()
            current_section = heading.group(1)
            section_intro.setdefault(current_section, [])
            continue
        sub_clause = re.match(r"^(\d{1,2}\.\d+)\s*(.*)$", line)
        if sub_clause:
            flush()
            current_no = sub_clause.group(1)
            current_section = current_no.split(".", 1)[0]
            current_lines = [sub_clause.group(2)] if sub_clause.group(2) else []
            continue
        if current_no:
            current_lines.append(line)
        elif current_section:
            section_intro.setdefault(current_section, []).append(line)
    flush()
    sections_with_subclauses = {item["clause_no"].split(".", 1)[0] for item in clauses}
    for section, lines in section_intro.items():
        content = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if content and (section not in sections_with_subclauses or section in {"2"}):
            clauses.append({
                "clause_no": section,
                "heading": SECTION_HEADINGS.get(section, ""),
                "content": content,
                "risk_level": SECTION_RISK.get(section, "提示"),
            })
    return sorted(clauses, key=lambda item: tuple(int(part) for part in item["clause_no"].split(".")))


def seed_standard_clauses(db: Session) -> int:
    source_text = BASELINE_TEXT_PATH.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    existing = {
        item.clause_no: item
        for item in db.scalars(
            select(StandardClause).where(
                StandardClause.contract_type == "租赁",
                StandardClause.baseline_version == BASELINE_VERSION,
            )
        ).all()
    }
    touched = 0
    for payload in parse_standard_clauses(source_text):
        item = existing.get(payload["clause_no"])
        if not item:
            item = StandardClause(
                contract_type="租赁",
                baseline_name=BASELINE_NAME,
                baseline_version=BASELINE_VERSION,
                clause_no=payload["clause_no"],
                heading=payload["heading"],
                content=payload["content"],
                source_file=BASELINE_SOURCE_FILE,
                source_hash=source_hash,
                risk_level=payload["risk_level"],
                is_required=True,
                is_active=True,
            )
            db.add(item)
            touched += 1
        elif item.source_hash != source_hash or item.content != payload["content"]:
            item.heading = payload["heading"]
            item.content = payload["content"]
            item.source_file = BASELINE_SOURCE_FILE
            item.source_hash = source_hash
            item.risk_level = payload["risk_level"]
            item.is_active = True
            touched += 1
    return touched


def active_standard_clauses(db: Session, contract_type: str) -> list[StandardClause]:
    return db.scalars(
        select(StandardClause)
        .where(StandardClause.contract_type == contract_type, StandardClause.is_active.is_(True))
        .order_by(StandardClause.clause_no)
    ).all()


def _clause_value(clause, key: str, default=""):
    return clause.get(key, default) if isinstance(clause, dict) else getattr(clause, key, default)


def baseline_findings(text: str, contract_type: str, clauses: list) -> list[dict]:
    if contract_type != "租赁" or not clauses:
        return []
    compact = _normal(text)
    is_standard = "林德(中国)叉车有限公司设备租赁合同的一般性条款" in compact.replace("（", "(").replace("）", ")")
    findings: list[dict] = []
    if is_standard:
        current = {item["clause_no"]: item for item in parse_standard_clauses(text)}
        candidates: list[tuple[int, float, object, str]] = []
        risk_rank = {"高": 0, "中": 1, "低": 2, "提示": 3}
        for clause in clauses:
            clause_no = str(_clause_value(clause, "clause_no"))
            baseline_content = str(_clause_value(clause, "content"))
            current_content = current.get(clause_no, {}).get("content", "")
            similarity = SequenceMatcher(None, _normal(baseline_content), _normal(current_content)).ratio() if current_content else 0.0
            # 标准版本逐条采用精确归一化比对；金额、比例或期限只改一个字符也必须进入人工复核。
            if current_content and _normal(baseline_content) == _normal(current_content):
                continue
            candidates.append((risk_rank.get(str(_clause_value(clause, "risk_level", "提示")), 3), similarity, clause, current_content))
        # Template-integrity review is exhaustive. Never cap deviations: a
        # 13th deletion is still a deletion and must remain auditable.
        for _, similarity, clause, current_content in sorted(candidates, key=lambda item: (item[0], item[1])):
            clause_no = str(_clause_value(clause, "clause_no"))
            heading = str(_clause_value(clause, "heading"))
            baseline_content = str(_clause_value(clause, "content"))
            baseline_numbers = re.findall(r"\d+(?:\.\d+)?\s*(?:%|％|天|日|个工作日|个月|月|小时|年|次)?", baseline_content)
            current_numbers = re.findall(r"\d+(?:\.\d+)?\s*(?:%|％|天|日|个工作日|个月|月|小时|年|次)?", current_content)
            deviation_type = "删除" if not current_content else "数值偏离" if baseline_numbers != current_numbers else "实质性修改" if similarity < 0.98 else "编辑性修改"
            findings.append({
                "rule_code": f"BASELINE_DEVIATION_{clause_no.replace('.', '_')}",
                "category": heading or "标准条款偏离",
                "title": f"标准条款第 {clause_no} 条被调整或删除",
                "risk_level": str(_clause_value(clause, "risk_level", "中")),
                "original_text": current_content or "",
                "suggested_text": baseline_content if current_content else _format_missing_clause(clause_no, heading, baseline_content, text),
                "action_type": "替换条款" if current_content else "新增条款",
                "basis": f"依据文件《{BASELINE_NAME}》（{BASELINE_VERSION}，{BASELINE_SOURCE_FILE}）第 {clause_no} 条；当前文本相似度 {similarity:.0%}。基准原文：{baseline_content}",
                "negotiation_focus": "确认修改主体、商业原因和可接受底线；如不恢复标准文本，应记录人工放行结论。",
                "source": f"租赁基准条款库（{BASELINE_VERSION}）",
                "confidence": 96 if current_content else 91,
                "historical_release": False,
                "baseline_clause_id": str(_clause_value(clause, "id")) or None,
                "anchor_text": current_content or _insertion_context(text),
                "check_status": "UNMET",
                "evidence_json": ([{"clause_no": clause_no, "quote": current_content, "evidence_type": "contradict"}] if current_content else []),
                "risk_reason": f"公司标准模板第 {clause_no} 条发生{deviation_type}，需独立判断商业及法律影响。",
                "deviation_type": deviation_type,
                "human_confirmation_required": str(_clause_value(clause, "risk_level", "中")) == "高" or deviation_type in {"删除", "数值偏离"},
            })
        return findings

    # Customer-authored contracts are no longer judged by the presence of one
    # chapter keyword. The role-aware Focused Check pipeline evaluates all 49
    # checks and can distinguish MET/PARTIAL/UNMET/NOT_MENTIONED.
    return []


def outside_baseline_findings(text: str, existing_evidence: list[str], contract_type: str) -> list[dict]:
    if contract_type not in {"采购", "租赁"}:
        return []
    covered = _normal(" ".join(existing_evidence))
    suspicious = re.compile(r"(?:最终解释权|永久(?:且不可撤销)?使用权|无条件承担|承担一切责任|以对甲方最有利|唯一判断标准|不得以任何理由拒绝)")
    rows: list[dict] = []
    for sentence in re.split(r"(?<=[。；！？])", text):
        value = re.sub(r"\s+", " ", sentence).strip()
        match = suspicious.search(value)
        if not match or len(value) < 8 or _normal(match.group(0)) in covered:
            continue
        rows.append({
            "rule_code": f"OUTSIDE_BASELINE_{len(rows) + 1}",
            "category": "新增条款",
            "title": "发现超出标准条款覆盖范围的单边义务",
            "risk_level": "高",
            "original_text": value[:420],
            "suggested_text": "双方在本合同项下的权利义务均以合同明确约定、可客观验证且相互对等为原则；任何一方均无权单方解释、单方认定或要求另一方无条件承担未明确约定的责任。",
            "action_type": "替换条款",
            "basis": "该表述未由常规标准条款覆盖，触发新增条款主动风险识别，应结合业务事实和法律意见单独审核。",
            "negotiation_focus": "要求客户说明使用场景、触发条件和责任边界；必要时转批对应业务部门或法务负责人。",
            "source": "新增条款主动识别",
            "confidence": 86,
            "historical_release": False,
            "anchor_text": value[:420],
        })
        if len(rows) >= 3:
            break
    return rows
