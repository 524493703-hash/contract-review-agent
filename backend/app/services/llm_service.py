from __future__ import annotations

import json
import re

import httpx

from ..config import get_settings
from .review_engine import (
    EVIDENCE_MAX_CHARS,
    EVIDENCE_MIN_CHARS,
    build_clause_context,
    preserve_clause_format,
    preserve_asymmetric_obligation_subject,
    refine_evidence,
    source_occurrence_fragments,
    source_occurrence_with_heading,
    validate_replacement_clause,
)
from .source_trace import clause_label_at, locate_source_span


SYSTEM_INSTRUCTIONS = """你是企业采购与设备租赁合同审核专家。你的任务是补充规则引擎可能遗漏的风险，不重复已有发现。
仅依据给定合同文本与规则摘要判断；不得编造法律条文、历史案例或合同事实。每项发现必须引用合同原文片段。
original_text 必须是能直接证明风险的连续原文，优先引用完整的一至两个条款或句子，长度控制在8至420个字符；不得复制整章或大段无关上下文。若 action_type 为“新增条款”，合同中不存在可替换的风险原文，此时 original_text 必须为空，并用 anchor_text 提供实际存在的插入位置上下文。
suggested_text 必须是完整、自洽、可直接替换 original_text 的正式合同条款，不得写成“建议删除、建议修改、调整为、补充约定、请确认”等修改方向，不得包含占位符。替换稿可以有意调整风险相关的金额、比例、期限、主体、权利义务或触发条件，但必须保留原文的风险主题和关键语义关联，不能凭空返回另一类条款。如果 original_text 带有“第七条”“7.1”等条款编号或层级前缀，suggested_text 必须保留同一前缀，不得另起编号。
提交每条 finding 前必须做一次“同主题自检”：先从 original_text 中识别主要风险主题、义务对象和触发条件，再检查 suggested_text 是否仍在同一主题内，并至少保留一个主题锚点（如付款/验收/租赁期限/解除/违约/维保等）及对应对象；只改数字、主体或触发条件时也不得改成另一类法律条款。若原文明确由甲方、乙方、出租方、承租方等单一主体承担义务，替换稿不得无理由改成“双方”“任何一方”或泛称“违约方”；只有原文明确约定双边责任时才使用双边主体。若无法生成与原文同主题的完整替换稿，应删除该 finding 或使用 action_type“新增条款”，不得用无关通用模板凑数。
同一风险在合同中命中多个不同位置时，必须每个位置单独输出一条 finding，original_text 只能引用该位置，不能用“命中1/命中2”合并；每条 finding 都要生成针对该位置的可替换条款。新增条款必须使用 action_type“新增条款”，不伪造风险原文，但必须提供能在合同中定位的 anchor_text。
优先关注：主体与关联方、价税与付款、交付验收、租赁期限与自动续租、维保、安全责任、违约责任上限、解除、知识产权、保密与数据、附件冲突、争议解决。
内部推理必须简短，不得逐条复述合同，必须在输出预算内完成最终 JSON。
输出必须是一个JSON对象，格式：{"findings":[{"action_type":"替换条款|新增条款","category":"","title":"","risk_level":"高|中|低","severity_factors":{"impact":1-5,"likelihood":1-5,"remediation":1-5,"reason":""},"original_text":"","anchor_text":"","suggested_text":"","basis":"","negotiation_focus":"","confidence":0-100}]}。
最多返回8项；若无新增风险，返回{"findings":[]}。不要输出Markdown代码围栏或JSON以外的文字。"""

REDRAFT_INSTRUCTIONS = """你是企业合同条款起草专家。请根据风险原文、当前替换稿和用户的自然语言修改要求，重新起草一条正式合同条款。
输出必须是 JSON 对象：{"replacement_clause":""}。
replacement_clause 必须满足：
1. 是完整、自洽、可直接放进合同的条款文本；
2. 能直接替换风险原文；如 action_type 为“新增条款”，则必须是可直接插入合同的完整条款；
3. 严格落实用户本次修改要求，同时保留用户未要求改变的关键主体、条件、数字和责任边界；原文若明确由单一主体承担义务，不得无理由改成“双方”“任何一方”或泛称“违约方”，除非用户明确要求改为双边责任；用户明确要求修改的风险字段可以变化，但必须仍然围绕风险原文；如果风险原文或上下文带有“第七条”“7.1”等编号，必须保留同一编号/层级前缀，不得另起编号；
4. 不得出现“建议、请、需要、应考虑、删除、修改、调整为、补充约定”等面向审核人的修改指令；
5. 不得使用 XXX、待补充、待确认等占位符，不得解释起草过程。
只返回 JSON，不要返回 Markdown 或其他文字。"""

SEVERITY_RUBRIC = """
风险等级必须使用以下量化矩阵，不得仅凭措辞强烈程度判断。每项 finding 额外输出 severity_factors：
1. impact（影响程度，1-5）：1=文字或轻微流程问题；2=有限操作成本或局部义务；3=实质影响付款、验收、服务或一般合同权利；4=重大财务损失、诉讼、解除、数据或知识产权责任；5=无限责任、重大合规/人身安全风险、合同效力风险或可能造成灾难性损失。
2. likelihood（触发可能性，1-5）：1=极少且需多个特殊条件；2=较低；3=存在现实可能；4=较可能；5=条款自动生效、当前事实已满足或高度可能发生。不得因为条款存在就一律评5分。
3. remediation（整改难度，1-5）：1=文字修改即可；2=标准补充条款可解决；3=需要实质谈判；4=涉及核心商务条件；5=受外部制度约束或极难通过谈判控制。
severity_factors 格式必须为：{"impact":1-5,"likelihood":1-5,"remediation":1-5,"reason":"一句话说明评分事实依据"}。
后端将按固定公式重新计算最终等级，因此 risk_level 仅为模型参考值。缺少评分维度、超出1-5范围或理由为空的发现将被丢弃。
"""


def classify_llm_severity(item: dict) -> tuple[str, int, dict] | None:
    """Turn model-provided factors into an authoritative, reproducible level."""
    factors = item.get("severity_factors")
    if not isinstance(factors, dict) or not str(factors.get("reason", "")).strip():
        return None
    values: dict[str, int] = {}
    for key in ("impact", "likelihood", "remediation"):
        raw_value = factors.get(key)
        if isinstance(raw_value, bool):
            return None
        try:
            numeric = int(raw_value)
        except (TypeError, ValueError):
            return None
        if str(raw_value).strip() not in {str(numeric), f"{numeric}.0"} or not 1 <= numeric <= 5:
            return None
        values[key] = numeric

    score = values["impact"] * 14 + values["likelihood"] * 4 + values["remediation"] * 2
    if values["impact"] == 5 or (values["impact"] >= 4 and score >= 75):
        level = "高"
    elif values["impact"] >= 3 or score >= 45:
        level = "中"
    else:
        level = "低"
    normalized = {**values, "reason": str(factors["reason"]).strip()[:300]}
    return level, score, normalized


def _extract_output_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return str(content)


def _decode_json_object(output_text: str) -> dict:
    cleaned = output_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    # Some compatible gateways prepend a short explanation despite the JSON
    # instruction. Decode the first complete JSON object without accepting
    # arbitrary non-JSON output.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise json.JSONDecodeError("No complete JSON object in model output", cleaned, 0)


def redraft_replacement_clause(
    *,
    original_text: str,
    current_text: str,
    instruction: str,
    action_type: str,
    title: str,
    basis: str,
    contract_context: str,
    risk_context: str = "",
    history: list[dict] | None = None,
) -> tuple[str, str]:
    """Generate another independently reviewable replacement draft."""
    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_api_url:
        return "", "未配置大模型，无法根据自然语言重新起草合同条款"
    prompt = {
        "risk_title": title,
        "action_type": action_type,
        "risk_original": original_text,
        "current_replacement": current_text,
        "user_instruction": instruction,
        "review_basis": basis,
        "previous_drafts": (history or [])[-6:],
        "contract_context": contract_context[:12000],
        "risk_context": risk_context[:1800],
        "format_requirement": "沿用风险原文/上下文中的条款编号、层级和标点格式；替换条款不得另起编号。",
    }
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": REDRAFT_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "stream": False,
        "temperature": 0.15,
        "max_tokens": 3000,
        "user": "contract-review-agent-redraft",
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
    }
    last_error: Exception | None = None
    last_quality: dict[str, object] | None = None
    for attempt in range(2):
        request_body = dict(body)
        if attempt:
            quality = last_quality or {}
            warnings = "；".join(str(item) for item in quality.get("warnings", [])) or "未保留原文的风险主题或关键语义"
            shared_topics = "、".join(str(item) for item in quality.get("shared_topics", [])) or "无"
            shared_terms = "、".join(str(item) for item in quality.get("shared_terms", [])) or "无"
            request_body["messages"] = [
                *body["messages"],
                {
                    "role": "user",
                    "content": (
                        "上一稿未通过后端的风险主题关联校验，请不要换成通用模板。"
                        f"校验提示：{warnings}；识别到的共同主题：{shared_topics}；共同语义词：{shared_terms}。"
                        f"风险原文：{original_text[:600]}；风险上下文：{risk_context[:900]}。"
                        "请回到同一风险原文，保留其义务对象、风险主题和触发条件，只修改用户明确要求的字段；"
                        "替换稿必须是完整合同条款，并沿用原文条款编号/层级。仅返回完整 JSON："
                        '{"replacement_clause":"..."}'
                    ),
                },
            ]
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    settings.llm_api_url.rstrip("/") + "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
                    json=request_body,
                )
                response.raise_for_status()
            data = _decode_json_object(_extract_output_text(response.json()))
            clause = str(data.get("replacement_clause") or "").strip()[:6000]
            if action_type != "新增条款":
                clause = preserve_asymmetric_obligation_subject(
                    original_text,
                    preserve_clause_format(original_text, clause, risk_context),
                )
            quality = validate_replacement_clause(original_text, clause, action_type)
            if quality["eligible"]:
                return clause, f"大模型重新起草完成（{settings.llm_model}）"
            last_quality = quality
            last_error = ValueError("模型返回的条款与风险原文关联不足或不是可直接使用的完整条款")
        except Exception as exc:
            last_error = exc
    return "", f"条款重新起草失败：{type(last_error).__name__ if last_error else '未知错误'}"


def analyze_contract(
    text: str,
    existing_titles: list[str],
    safety_identifier: str,
    our_role: str = "",
    candidate_hints: list[dict] | None = None,
) -> tuple[list[dict], str]:
    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_api_url:
        return [], "未配置大模型"
    shadow_hints = [
        {
            "rule_code": str(item.get("rule_code") or ""),
            "title": str(item.get("title") or ""),
            "risk_level": str(item.get("risk_level") or ""),
            "original_text": str(item.get("original_text") or "")[:500],
        }
        for item in (candidate_hints or [])[:24]
    ]
    hint_prompt = ""
    if shadow_hints:
        hint_prompt = (
            "\n旧正则影子召回候选（仅是定位线索，不是审核结论；必须根据合同原文独立采纳或拒绝，"
            "不得照抄其风险分类）：\n"
            + json.dumps(shadow_hints, ensure_ascii=False)
            + "\n"
        )
    prompt = (
        f"我方在本合同中的角色：{our_role or '未识别，禁止自行假定'}。判断风险方向时必须以该角色为准。\n"
        "已有规则发现标题（不要重复）：\n- "
        + "\n- ".join(existing_titles)
        + hint_prompt
        + "\n\n合同文本：\n"
        + text[:70000]
    )
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS + "\n\n" + SEVERITY_RUBRIC},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 12000,
        "user": "contract-review-agent",
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
    }
    # Keep a stable application identifier for OpenAI-compatible gateways.
    # Per-user accountability remains in our own audit log.
    _ = safety_identifier
    last_error: Exception | None = None
    data: dict | None = None
    for attempt in range(2):
        request_body = dict(body)
        if attempt:
            request_body["max_tokens"] = 16000
            request_body["messages"] = [
                *body["messages"],
                {"role": "user", "content": "上一次输出无法解析。请只返回一个完整的 JSON 对象，不要附加其他文字。"},
            ]
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    settings.llm_api_url.rstrip("/") + "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
                    json=request_body,
                )
                response.raise_for_status()
            data = _decode_json_object(_extract_output_text(response.json()))
            break
        except Exception as exc:
            last_error = exc
    if data is None:
        return [], f"大模型增强失败：{type(last_error).__name__ if last_error else '未知错误'}"
    findings = []
    repair_attempts = 0
    repair_successes = 0
    for index, item in enumerate(data.get("findings", [])[:8], start=1):
        if not all(item.get(key) for key in ("title", "suggested_text", "basis", "negotiation_focus")):
            continue
        action_type = str(item.get("action_type") or "替换条款")
        raw_suggested = str(item.get("suggested_text") or "").strip()
        severity = classify_llm_severity(item)
        if severity is None:
            continue
        risk_level, severity_score, severity_factors = severity
        severity_reason = severity_factors["reason"].rstrip("。；;,.， ")
        model_basis = str(item["basis"]).lstrip()
        try:
            confidence = max(0, min(100, int(item.get("confidence", 75))))
        except (TypeError, ValueError):
            confidence = 75

        source_rows: list[tuple[str, str]] = []
        if action_type == "新增条款":
            # A new clause has no risk original. It must instead identify a
            # real source anchor so the insertion can be previewed and applied
            # without replacing an unrelated paragraph.
            raw_context = str(item.get("anchor_text") or item.get("context_text") or "")
            contexts = source_occurrence_fragments(text, raw_context)
            if not contexts:
                continue
            anchor_text = refine_evidence(text, contexts[0])
            if not anchor_text:
                continue
            if not validate_replacement_clause("", raw_suggested, "新增条款")["eligible"]:
                continue
            source_rows = [("", anchor_text)]
        else:
            raw_evidence = str(item.get("original_text") or "")
            occurrences = source_occurrence_fragments(text, raw_evidence)
            if not occurrences:
                continue
            # If the model cited a phrase that appears more than once, expand
            # it into independent findings. Each row then has its own anchor,
            # risk key and decision instead of sharing one broad replacement.
            source_rows = [
                (
                    refine_evidence(text, occurrence),
                    source_occurrence_with_heading(text, raw_evidence, occurrence_no),
                )
                for occurrence_no, occurrence in enumerate(occurrences, start=1)
            ]

            # Give the model one targeted repair opportunity before dropping a
            # candidate. The repair prompt contains the actual validator
            # feedback and the same source context, so it is much less likely
            # to drift into unrelated boilerplate than a generic retry.
            if source_rows:
                first_original, first_anchor = source_rows[0]
                first_context = build_clause_context(text, first_anchor, occurrence_no=1)
                first_suggested = preserve_asymmetric_obligation_subject(
                    first_original,
                    preserve_clause_format(first_original, raw_suggested, first_context),
                )
                first_quality = validate_replacement_clause(first_original, first_suggested, action_type)
                if not first_quality["eligible"]:
                    repair_attempts += 1
                    repaired, _ = redraft_replacement_clause(
                        original_text=first_original,
                        current_text=first_suggested,
                        instruction=(
                            "请仅围绕风险原文的同一法律/业务主题重新起草可替换条款；"
                            "保留义务对象、风险主题和必要触发条件，只修正原文中的风险字段，"
                            "不得改成无关的付款、争议、解除或其他通用条款。"
                        ),
                        action_type=action_type,
                        title=str(item["title"]),
                        basis=model_basis,
                        contract_context=text,
                        risk_context=first_context,
                        history=[],
                    )
                    if repaired:
                        raw_suggested = repaired
                        repair_successes += 1

        for occurrence_no, (original_text, occurrence) in enumerate(source_rows, start=1):
            if action_type == "新增条款":
                suggested_text = raw_suggested[:3000]
            else:
                context = build_clause_context(text, occurrence, occurrence_no=occurrence_no)
                suggested_text = preserve_asymmetric_obligation_subject(
                    original_text,
                    preserve_clause_format(original_text, raw_suggested, context),
                )[:3000]
                if not original_text or not validate_replacement_clause(original_text, suggested_text, action_type)["eligible"]:
                    continue
            findings.append(
                {
                    "rule_code": f"LLM_DISCOVERY_{index}",
                    "category": str(item.get("category") or "新增条款"),
                    "title": str(item["title"])[:255],
                    "risk_level": risk_level,
                    "original_text": original_text,
                    "suggested_text": suggested_text,
                    "action_type": action_type,
                    "anchor_text": occurrence,
                    "basis": (
                        f"模型统一分级 {severity_score}/100：影响{severity_factors['impact']}/5、"
                        f"触发可能性{severity_factors['likelihood']}/5、整改难度{severity_factors['remediation']}/5；"
                        f"{severity_reason}。{model_basis}"
                    )[:2000],
                    "negotiation_focus": str(item["negotiation_focus"])[:2000],
                    "source": f"大模型增强（{settings.llm_model}）",
                    "confidence": confidence,
                    "historical_release": False,
                }
            )
    repair_note = f"；已对 {repair_attempts} 项关联不足候选自动重试，成功修复 {repair_successes} 项" if repair_attempts else ""
    return findings, f"大模型增强完成，新增 {len(findings)} 项{repair_note}"


FOCUSED_CHECK_INSTRUCTIONS = """你是公司设备租赁合同的受约束审核裁决器，我方角色为出租方。
你会收到一个固定版本 Playbook 的全部 Focused Checks、确定性初判和每项 Check 的候选证据。
逐项判断 MET、UNMET、PARTIAL 或 NOT_MENTIONED，不得遗漏任何 check_code，不得创造新的 Check。
MET 表示全部强制槽位满足；UNMET 表示存在明确相反约定或数值越线；PARTIAL 表示只有部分内容、存在歧义或冲突；NOT_MENTIONED 表示合同没有相关约定。
不得跨多个无关条款拼凑槽位。每条 evidence_quotes 必须从该 Check 的 candidate_quotes 中逐字截取真实、连续的原文，不得改写、拼接或概括。MET、UNMET、PARTIAL 至少需要一条证据；NOT_MENTIONED 的 evidence_quotes 必须为空。
不得把公司基准条款当作法律，不得编造法律依据。法律效力或强制性问题只设置 need_legal_rag=true。
只返回 JSON：{"results":[{"check_code":"L-01","status":"MET|UNMET|PARTIAL|NOT_MENTIONED","evidence_quotes":[],"satisfied_slots":[],"missing_slots":[],"reason":"","confidence":0-100,"need_legal_rag":false}]}。"""


def _locate_model_quote(source: str, quote: str) -> tuple[int, int, str] | None:
    value = str(quote or "").strip()
    if len(value) < 6:
        return None
    direct = source.find(value)
    if direct >= 0:
        return direct, direct + len(value), value
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
    return start, end, source[start:end]


def adjudicate_focused_checks(
    contract_text: str,
    focused_review: dict,
    safety_identifier: str,
    *,
    source_map: list[dict] | None = None,
    source_file: str = "",
) -> tuple[dict, str]:
    """Let the configured LLM adjudicate the fixed Focused Checks.

    Deterministic adverse matches remain authoritative. Every model quote is
    rebound to source offsets before it can replace the initial decision.
    """
    settings = get_settings()
    model_name = settings.focused_check_model or settings.llm_model
    if not settings.llm_api_key or not settings.llm_api_url:
        return focused_review, "未配置大模型裁决服务，保留确定性四态结果"
    check_rows = []
    for item in focused_review.get("check_results", []):
        check_rows.append({
            "check_code": item["check_code"],
            "name": item["check_name"],
            "category": item["category"],
            "initial_status": item["status"],
            "required_slots": [*item.get("satisfied_slots", []), *item.get("missing_slots", [])],
            "initial_satisfied_slots": item.get("satisfied_slots", []),
            "initial_missing_slots": item.get("missing_slots", []),
            "deterministic_contradictions": item.get("contradictions", []),
            "candidate_quotes": [
                candidate.get("quote", "")
                for candidate in item.get("retrieval_trace", {}).get("candidates", [])[:8]
                if candidate.get("quote")
            ],
            "query_pack": item.get("retrieval_trace", {}).get("query_pack", {}),
            "legal_rag_triggers": item.get("legal_rag_triggers", []),
        })
    prompt = {
        "contract_text": contract_text[:70000],
        "checks": check_rows,
        "required_result_count": len(check_rows),
    }
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": FOCUSED_CHECK_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "stream": False,
        "temperature": 0.05,
        "max_tokens": 16000,
        "user": "contract-focused-check-adjudication",
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
    }
    _ = safety_identifier
    last_error: Exception | None = None
    data: dict | None = None
    for attempt in range(2):
        request_body = dict(body)
        if attempt:
            request_body["messages"] = [
                *body["messages"],
                {"role": "user", "content": f"上次输出无效。必须返回全部 {len(check_rows)} 个 check_code，且只返回完整 JSON。"},
            ]
        try:
            with httpx.Client(timeout=180) as client:
                response = client.post(
                    settings.llm_api_url.rstrip("/") + "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
                    json=request_body,
                )
                response.raise_for_status()
            data = _decode_json_object(_extract_output_text(response.json()))
            if isinstance(data.get("results"), list):
                break
            data = None
        except Exception as exc:
            last_error = exc
    if data is None:
        return focused_review, f"大模型四态裁决失败，保留确定性结果：{type(last_error).__name__ if last_error else '无有效JSON'}"

    by_code = {item["check_code"]: item for item in focused_review.get("check_results", [])}
    accepted = 0
    rejected = 0
    seen: set[str] = set()
    for model_item in data.get("results", []):
        code = str(model_item.get("check_code") or "")
        target = by_code.get(code)
        if not target or code in seen:
            rejected += 1
            continue
        seen.add(code)
        status = str(model_item.get("status") or "")
        if status not in {"MET", "UNMET", "PARTIAL", "NOT_MENTIONED"}:
            rejected += 1
            continue
        located = []
        candidate_rows = target.get("retrieval_trace", {}).get("candidates", [])
        for quote in model_item.get("evidence_quotes") or []:
            selected = None
            for candidate in candidate_rows:
                left = int(candidate.get("start_offset") or 0)
                right = int(candidate.get("end_offset") or left)
                local = _locate_model_quote(contract_text[left:right], str(quote))
                if local:
                    local_start, local_end, exact_quote = local
                    selected = (candidate, left + local_start, left + local_end, exact_quote)
                    break
            if not candidate_rows:
                global_match = _locate_model_quote(contract_text, str(quote))
                if global_match:
                    start, end, exact_quote = global_match
                    selected = ({}, start, end, exact_quote)
            if not selected:
                continue
            candidate, start, end, exact_quote = selected
            locator = locate_source_span(source_map, start, end, source_file=source_file)
            located.append({
                "order_index": len(located) + 1,
                "clause_no": str(candidate.get("clause_no") or clause_label_at(contract_text, start)),
                "page_no": candidate.get("page_no") or locator["page_no"],
                "source_file": str(candidate.get("source_file") or locator["source_file"]),
                "page_method": locator["page_method"],
                "start_offset": start,
                "end_offset": end,
                "quote": exact_quote[:1200],
                "evidence_type": "contradict" if status == "UNMET" else "support",
                "retrieval_methods": ["llm_semantic"],
                "score": None,
            })
        if status == "NOT_MENTIONED" and located:
            rejected += 1
            continue
        if status != "NOT_MENTIONED" and not located:
            rejected += 1
            continue
        # A deterministic adverse-pattern match cannot be silently waived by
        # a model. It remains UNMET until a human reviewer changes it.
        if target.get("contradictions") and status != "UNMET":
            rejected += 1
            continue
        if target.get("contradictions"):
            # The deterministic engine owns both the status and the exact
            # adverse evidence. A model may explain it, but may not replace it
            # with a benign sentence from the same candidate clause.
            located = target.get("evidence", [])
        valid_slots = set(target.get("satisfied_slots", [])) | set(target.get("missing_slots", []))
        satisfied = [slot for slot in model_item.get("satisfied_slots", []) if slot in valid_slots]
        missing = [slot for slot in model_item.get("missing_slots", []) if slot in valid_slots and slot not in satisfied]
        if status == "MET" and (missing or valid_slots - set(satisfied)):
            rejected += 1
            continue
        try:
            confidence = max(0, min(100, int(model_item.get("confidence", 75))))
        except (TypeError, ValueError):
            confidence = 75
        model_legal_request = bool(model_item.get("need_legal_rag"))
        legal_needed = model_legal_request or (
            status != "MET" and bool(target.get("legal_rag_triggers"))
        )
        risk_level = "提示" if status == "MET" else str(target.get("base_risk_level") or target.get("risk_level") or "中")
        human_needed = legal_needed or (
            status != "MET" and (bool(target.get("human_gate_policy")) or risk_level == "高")
        )
        target.update({
            "status": status,
            "risk_level": risk_level,
            "confidence": confidence,
            "satisfied_slots": satisfied,
            "missing_slots": missing or ([slot for slot in valid_slots if slot not in satisfied] if status != "MET" else []),
            "reason": str(model_item.get("reason") or target["reason"])[:1200],
            "decision_source": f"llm_adjudicated:{model_name}",
            "legal_rag_required": legal_needed,
            "human_confirmation_required": human_needed,
            "evidence": located,
        })
        accepted += 1

    statuses = {"MET", "UNMET", "PARTIAL", "NOT_MENTIONED"}
    focused_review["stats"].update({status: sum(item["status"] == status for item in by_code.values()) for status in statuses})
    focused_review["stats"]["HUMAN_CONFIRMATION"] = sum(item["human_confirmation_required"] for item in by_code.values())
    focused_review["stats"]["LEGAL_RAG_REQUIRED"] = sum(item["legal_rag_required"] for item in by_code.values())
    return focused_review, f"大模型四态裁决完成（{model_name}）：采纳 {accepted} 项，拒绝无效输出 {rejected} 项，缺失输出沿用确定性结果 {len(by_code) - len(seen)} 项"
