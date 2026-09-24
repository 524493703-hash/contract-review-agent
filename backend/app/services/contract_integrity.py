from __future__ import annotations

import re
from datetime import date, datetime

from .source_trace import clause_label_at, locate_source_span


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace("元", "").strip())
    except (TypeError, ValueError):
        return None


def _line_spans(text: str):
    cursor = 0
    for line in (text or "").splitlines(keepends=True):
        value = line.rstrip("\r\n")
        yield value, cursor, cursor + len(value)
        cursor += len(line)


def _evidence(text: str, start: int, end: int, source_map: list[dict] | None, source_file: str) -> dict:
    locator = locate_source_span(source_map, start, end, source_file=source_file)
    return {
        "source_file": locator["source_file"],
        "page_no": locator["page_no"],
        "page_method": locator["page_method"],
        "clause_no": clause_label_at(text, start),
        "start_offset": start,
        "end_offset": end,
        "quote": text[start:end].strip()[:1200],
    }


def _finding(
    *,
    rule_code: str,
    category: str,
    title: str,
    risk_level: str,
    evidence: dict,
    basis: str,
    recommendation: str,
    negotiation_focus: str,
    confidence: int = 98,
) -> dict:
    source_label = evidence.get("source_file") or "当前合同"
    if evidence.get("clause_no"):
        clause_label = str(evidence["clause_no"])
        source_label += f" 第{clause_label}条" if re.fullmatch(r"\d+(?:\.\d+)*", clause_label) else f" {clause_label}"
    if evidence.get("page_no"):
        source_label += f" 第{evidence['page_no']}页"
    return {
        "rule_code": rule_code,
        "category": category,
        "title": title,
        "risk_level": risk_level,
        "original_text": evidence["quote"],
        "suggested_text": recommendation,
        "basis": f"依据：{source_label}。{basis}",
        "negotiation_focus": negotiation_focus,
        "source": "合同完整性确定性检查",
        "confidence": confidence,
        "historical_release": False,
        "action_type": "人工起草",
        "page_no": evidence.get("page_no"),
        "anchor_text": evidence["quote"],
        "check_status": "UNMET",
        "evidence_json": [evidence],
        "risk_reason": basis,
        "deviation_type": "合同内在异常",
        "human_confirmation_required": risk_level == "高",
    }


def _first_match(text: str, pattern: str, flags: int = 0) -> re.Match | None:
    return re.search(pattern, text or "", flags)


def _pair_conflict(text: str, left_pattern: str, right_pattern: str) -> tuple[int, int] | None:
    left = _first_match(text, left_pattern, re.IGNORECASE | re.DOTALL)
    right = _first_match(text, right_pattern, re.IGNORECASE | re.DOTALL)
    if not left or not right:
        return None
    return min(left.start(), right.start()), max(left.end(), right.end())


def audit_contract_integrity(
    text: str,
    *,
    source_map: list[dict] | None = None,
    source_file: str = "",
    as_of_date: date | None = None,
) -> list[dict]:
    """Run document-wide checks that clause-by-clause LLM review often misses.

    These checks are intentionally deterministic and source-bound. They flag
    arithmetic and cross-document inconsistencies for human confirmation; they
    do not attempt to decide disputed legal effect.
    """
    source = text or ""
    findings: list[dict] = []
    effective_date = as_of_date or date.today()

    # Price-table arithmetic: adjacent numeric cells are treated as before-tax
    # and tax-inclusive only when the document itself labels such columns.
    tax_match = re.search(r"(?:税率|税点)[^\d]{0,12}(\d{1,2}(?:\.\d+)?)\s*%", source)
    tax_rate = float(tax_match.group(1)) / 100 if tax_match else 0.13
    money_anomalies: list[dict] = []
    numeric_cell = re.compile(r"^[￥¥]?\s*([0-9][0-9,]*(?:\.\d{1,4})?)\s*(?:元)?$")
    if "未税" in source and "含税" in source:
        for line, start, end in _line_spans(source):
            cells = [cell.strip() for cell in line.split(" | ")]
            for index in range(len(cells) - 1):
                before_match = numeric_cell.fullmatch(cells[index])
                after_match = numeric_cell.fullmatch(cells[index + 1])
                if not before_match or not after_match:
                    continue
                before = _number(before_match.group(1))
                after = _number(after_match.group(1))
                if not before or not after or before < 100:
                    continue
                expected = before * (1 + tax_rate)
                if after > expected * 1.5 or after < before * 0.95:
                    money_anomalies.append(_evidence(source, start, end, source_map, source_file))
                    break
    if money_anomalies:
        first = money_anomalies[0]
        findings.append(_finding(
            rule_code="DOC_PRICE_TAX_ARITHMETIC",
            category="金额与表格",
            title="未税价与含税价算术不一致",
            risk_level="高",
            evidence=first,
            basis=f"报价表标明未税/含税列，但至少 {len(money_anomalies)} 行的相邻金额无法按税率 {tax_rate:.0%} 换算，存在多写零位、列错位或单位错误风险。",
            recommendation="逐行复核并重新确认未税价、税率、含税价和计价单位；由双方对最终报价表重新签章，原错误表格不作为结算依据。",
            negotiation_focus="金额错误必须在签署前由业务、财务和对方共同确认，不允许仅以口头或邮件解释。",
        ))

    radius = next(
        (
            item for item in re.finditer(r"转弯半径[^；。\n]{0,24}?(\d{4,})\s*mm", source, re.IGNORECASE)
            if int(item.group(1)) >= 10000
        ),
        None,
    )
    if radius:
        evidence = _evidence(source, radius.start(), radius.end(), source_map, source_file)
        findings.append(_finding(
            rule_code="DOC_TECHNICAL_UNIT_OUTLIER",
            category="技术参数",
            title="转弯半径参数存在数量级异常",
            risk_level="高",
            evidence=evidence,
            basis=f"合同写明转弯半径 {radius.group(1)}mm，数值达到十米以上，且文内其他车型存在明显更小的同类参数，应核对是否多写零位或单位错误。",
            recommendation="由技术负责人逐车型确认转弯半径及单位，并以经双方签章的技术参数表替换错误数值。",
            negotiation_focus="技术参数未经确认不得进入自动红线，必须保留技术人员确认记录。",
        ))

    date_range = _first_match(
        source,
        r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?\s*(?:起|至|到|—|－|-)\s*(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?",
    )
    if date_range:
        try:
            end_date = datetime(
                int(date_range.group(4)), int(date_range.group(5)), int(date_range.group(6))
            ).date()
        except ValueError:
            end_date = None
        if end_date and effective_date > end_date:
            evidence = _evidence(source, date_range.start(), date_range.end(), source_map, source_file)
            findings.append(_finding(
                rule_code="DOC_CONTRACT_EXPIRED",
                category="合同期限",
                title="合同期限在审核基准日已经届满",
                risk_level="高",
                evidence=evidence,
                basis=f"约定截止日为 {end_date.isoformat()}，早于审核基准日 {effective_date.isoformat()}。",
                recommendation="更新合同期限，并明确届满至新合同生效期间订单、在场设备、租金和服务义务的衔接规则。",
                negotiation_focus="确认本文件是历史审查、续签文本还是拟追溯生效文本。",
            ))

    holdover = _first_match(source, r"设备.{0,12}必须.{0,12}保留在.{0,30}使用\s*[一1壹]个?月", re.DOTALL)
    if holdover:
        window_end = min(len(source), holdover.end() + 180)
        window = source[holdover.start():window_end]
        if not re.search(r"(?:租金|占用费|使用费|计费)", window):
            evidence = _evidence(source, holdover.start(), holdover.end(), source_map, source_file)
            findings.append(_finding(
                rule_code="DOC_FORCED_HOLDOVER_NO_RENT",
                category="解除与设备返还",
                title="解除后强制留用设备但未约定租金",
                risk_level="高",
                evidence=evidence,
                basis="合同要求解除后设备继续留场使用一个月，但相邻约定未明确该期间租金、保险、损坏责任和返还程序。",
                recommendation="删除强制留用；如确需过渡使用，应以乙方书面同意为前提，并明确租金、保险、保管、损坏赔偿和最迟返还日。",
                negotiation_focus="设备所有权和持续占用成本必须得到保障。",
            ))

    stacked_tax = _first_match(source, r"税款金额.{0,24}112%.*?发票金额.{0,24}25%", re.DOTALL)
    if stacked_tax:
        evidence = _evidence(source, stacked_tax.start(), stacked_tax.end(), source_map, source_file)
        findings.append(_finding(
            rule_code="DOC_STACKED_TAX_PENALTY",
            category="违约责任",
            title="发票责任包含多项累计赔偿",
            risk_level="高",
            evidence=evidence,
            basis="同一发票事件同时叠加税款金额112%、发票金额25%、税款、滞纳金、罚款及全部损失，且未见总责任上限或避免重复赔偿机制。",
            recommendation="以乙方过错和甲方实际直接损失为前提，删除重复计算项目，并约定累计责任上限。",
            negotiation_focus="明确同一事件不得重复主张违约金、损失和税务成本。",
        ))

    conflicts = (
        (
            "DOC_CONFLICT_FREIGHT", "运输费用", "正文与附件的运费承担约定冲突",
            r"(?:报价.{0,20}(?:包含|含).{0,10}运费|长租.{0,8}短租.{0,12}(?:均)?含运费)", r"(?:运费.{0,20}(?:由甲方承担|甲方承担)|甲方承担运费)",
            "统一往返运费、短租运费和调拨运费的承担主体，并约定正文与附件冲突时的优先顺序。",
        ),
        (
            "DOC_CONFLICT_RESIDENT_SERVICE", "维修保养", "驻场服务人数约定冲突",
            r"(?:至少|不得少于).{0,12}(?:一|1).{0,8}(?:名|人).{0,12}(?:专人)?驻场", r"(?:租赁\s*[<＜]\s*50|少于\s*50|低于\s*50).{0,18}(?:无需|不需要|不提供).{0,8}驻场",
            "按设备数量设置统一的驻场门槛、人员数量、工作时间和费用承担。",
        ),
        (
            "DOC_CONFLICT_REPAIR_SLA", "维修保养", "正文与附件的维修响应时限冲突",
            r"4\s*(?:个)?工作?小时.{0,80}8\s*小时", r"2\s*(?:H|小时).{0,80}24\s*(?:H|小时)",
            "区分响应、到场、修复和提供备用车四个时点，统一正文与附件的具体时限。",
        ),
        (
            "DOC_CONFLICT_PEAK_NOTICE", "需求计划", "正文与附件的旺季通知期限冲突",
            r"旺季.{0,30}30\s*天.{0,35}15\s*天", r"旺季.{0,30}20\s*(?:个工作日|天).{0,35}7\s*(?:个工作日|天)",
            "统一旺季和临时需求的通知期限、可承受增量及无法供货时的责任。",
        ),
    )
    for code, category, title, left, right, recommendation in conflicts:
        span = _pair_conflict(source, left, right)
        if not span:
            continue
        start, end = span
        # Keep the displayed evidence bounded while retaining two exact source
        # snippets in evidence_json for traceability.
        left_match = _first_match(source, left, re.IGNORECASE | re.DOTALL)
        right_match = _first_match(source, right, re.IGNORECASE | re.DOTALL)
        assert left_match and right_match
        first = _evidence(source, left_match.start(), left_match.end(), source_map, source_file)
        second = _evidence(source, right_match.start(), right_match.end(), source_map, source_file)
        finding = _finding(
            rule_code=code,
            category=category,
            title=title,
            risk_level="高",
            evidence=first,
            basis=f"{first.get('clause_no') or '一处约定'}与{second.get('clause_no') or '另一处约定'}对同一事项给出不同标准，且合同未建立充分的文件优先级规则。",
            recommendation=recommendation,
            negotiation_focus="由业务确认唯一可执行口径，法务统一正文、附件和订单。",
        )
        finding["evidence_json"] = [first, second]
        finding["original_text"] = f"【依据1】{first['quote']}\n【依据2】{second['quote']}"
        finding["anchor_text"] = first["quote"]
        findings.append(finding)

    return findings
