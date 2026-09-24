from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import asdict, dataclass

from .baseline_service import baseline_findings, outside_baseline_findings


@dataclass(frozen=True)
class Rule:
    code: str
    category: str
    title: str
    risk_level: str
    patterns: tuple[str, ...]
    suggestion: str
    basis: str
    negotiation_focus: str
    negative_patterns: tuple[str, ...] = ()


RULES: tuple[Rule, ...] = (
    Rule("LEASE_AUTO_RENEW", "租赁期限", "自动续租或默示续租", "高", (r"自动续租", r"视同[^。；！？\n]{0,100}?续租", r"无异议[^。；！？\n]{0,100}?续租"), "租赁期限届满时本合同自动终止；任何续租均须由双方在期限届满前另行签署书面协议，并明确续租期限、租金及服务条件，任何一方的沉默或继续使用均不构成自动续租。", "公司租赁标准条款：续租须经双方书面确认，避免因沉默形成长期义务。", "至少争取书面续租和明确退出窗口；确认设备返还、租金截止与残值处理。"),
    Rule("PAYMENT_LONG", "付款条件", "付款账期或付款前提偏离", "中", (r"(?:60|90|120)\s*(?:日|天)[^。；！？\n]{0,100}?支付", r"背靠背付款", r"以[^。；！？\n]{0,100}?收到[^。；！？\n]{0,80}?款[^。；！？\n]{0,80}?为[^。；！？\n]{0,80}?付款"), "付款方应在标的物验收合格并收到合法有效发票之日起三十日内支付相应款项，最迟不得超过四十五日；付款义务不以任何第三方向付款方支付款项为前提。", "采购合同管理规则：付款账期原则上不超过45日，付款义务不应取决于无关第三方。", "可用分期、信用证或保证金交换账期；保留逾期利息和暂停履约权。"),
    Rule("PENALTY_EXCESSIVE", "违约责任", "违约金过高或责任单边", "高", (r"(?:30|40|50|100)\s*%[^。]{0,30}(?:违约|赔偿)", r"每日[^。]{0,20}(?:0\.5%|5‰|千分之五)", r"一切损失", r"全部损失"), "任何一方因违约承担的累计违约金不超过合同总金额的百分之二十；违约方仅赔偿其在订立合同时可合理预见且由该违约直接造成的实际损失，任何一方均不对间接损失、利润损失或商誉损失承担责任。", "公司标准条款：违约金上限20%，排除间接、后续、商誉和利润损失。", "优先锁定累计上限；区分迟延、质量与根本违约；争取相互对等。"),
    Rule("AFFILIATE_SCOPE", "主体与关联方", "客户关联方范围过宽且责任割裂", "高", (r"甲方认为[^。；！？\n]{0,140}?关联", r"关联方[^。；！？\n]{0,140}?互不承担连带责任", r"内部负责[^。；！？\n]{0,140}?分别履行"), "本合同项下关联方仅指受同一主体控制且实际下单或使用设备、并经双方书面确认列入关联方清单的主体；各关联方应对其订单承担付款责任，甲方对该等关联方在本合同项下的付款及履约义务承担连带责任。", "合同相对性与信用风险控制要求：权利主体、付款主体和责任主体应一致且可识别。", "要求关联方清单、订单主体确认和信用额度；不能连带时至少要求母公司保证。"),
    Rule("ACCEPTANCE_SILENCE", "验收", "短期未异议视为验收或单方验收", "中", (r"(?:3|5|7)个?工作日内[^。；！？\n]{0,140}?异议[^。；！？\n]{0,100}?视为", r"逾期[^。；！？\n]{0,120}?视为[^。；！？\n]{0,80}?验收", r"单方[^。；！？\n]{0,120}?检验结果[^。；！？\n]{0,80}?有效"), "到货签收仅证明货物数量及外包装状态，不视为最终验收；最终验收应在完整资料、安装调试及约定试运行条件均已具备后由双方共同进行，且任何默示验收均不影响对隐蔽瑕疵及质保期内缺陷主张权利。", "样例合同显示签收不应等同最终验收，技术协议与附件应共同作为验收依据。", "明确验收资料、试运行期限、默认验收条件与隐蔽缺陷例外。"),
    Rule("TERMINATION_ONE_SIDED", "解除与终止", "客户单方解除或延迟交接", "高", (r"甲方有权[^。；！？\n]{0,160}?单方(?:解除|终止)", r"解除合同[^。；！？\n]{0,160}?设备必须保留", r"找到[^。；！？\n]{0,120}?供应商[^。；！？\n]{0,120}?交接"), "一方仅在对方发生重大违约且收到书面催告后十五日内仍未纠正时方可解除本合同；合同解除或终止后，继续占用或使用设备的一方应按原租金标准支付占用费，并承担保管、保险及设备毁损灭失责任。", "租赁设备所有权与持续占用风险要求：合同终止后的占用必须有期限和对价。", "锁定催告期、最长占用期、占用费、设备取回权和损坏赔偿。"),
    Rule("MAINTENANCE_SUSPEND", "维保服务", "欠款触发全面停保", "中", (r"逾期超过30天[^。；！？\n]{0,140}?暂停[^。；！？\n]{0,100}?(?:维修|保养)", r"维修和保养[^。；！？\n]{0,140}?支付[^。；！？\n]{0,100}?为前提"), "仅在无争议应付款逾期且经书面催告后仍未支付时，服务方方可暂停非紧急服务；涉及设备安全、人身安全或法定义务的维修保养不得中止，争议解决或欠款清偿后应立即恢复服务。", "安全生产与设备服务连续性要求；付款争议不应扩大为全面停保。", "划分紧急/非紧急服务；约定争议款托管和恢复服务时限。"),
    Rule("JURISDICTION", "争议解决", "争议管辖地不利", "中", (r"甲方所在地[^。；！？\n]{0,80}?法院", r"承租方所在地[^。；！？\n]{0,80}?法院", r"客户所在地[^。；！？\n]{0,80}?法院"), "因本合同引起或与本合同有关的任何争议，双方应首先协商解决；协商不成的，任何一方均可向被告所在地有管辖权的人民法院提起诉讼。", "公司争议解决标准条款：优先选择我方所在地法院，降低异地诉讼成本。", "可接受被告所在地作为折中；避免仅写“当地仲裁”而机构不明。"),
    Rule("ASSIGNMENT", "权利转让", "转让限制不对等", "中", (r"未经甲方[^。；！？\n]{0,120}?不得[^。；！？\n]{0,100}?转让", r"出租方有权[^。；！？\n]{0,120}?(?:抵押|出售)[^。；！？\n]{0,100}?设备"), "未经另一方事先书面同意，任何一方不得将本合同项下主要权利义务转让给第三方；但一方向其关联公司、融资机构转让应收账款或为融资目的作出的转让，在不实质减损另一方权利的前提下，仅需提前书面通知另一方。", "融资与集团内部重组需要保留合理转让空间，同时不实质降低对方权利。", "争取关联方转让、融资安排和提前通知例外。"),
    Rule("WEBSITE_TERMS", "外部条款", "合同引用客户官网或动态外部条款", "高", (r"https?://[^\s，。；）)]{1,300}", r"官网[^。；！？\n]{0,100}?条款", r"网站[^。；！？\n]{0,100}?公布"), "双方确认，仅以签署本合同时下载并作为本合同附件的网页条款版本为准，该附件应载明网址、抓取日期、版本号及文件哈希；网站后续任何更新未经双方书面确认均不构成本合同内容。", "POC要求：合同含官网链接时抓取并比对，防止动态网页单方变更合同内容。", "固定URL、抓取时间和文件哈希；排除单方在线更新。"),
    Rule("ATTACHMENT_CONFLICT", "文件效力", "正文、技术协议与附件优先级不清", "高", (r"技术协议[^。；！？\n]{0,160}?附件", r"附件[^。；！？\n]{0,140}?合同[^。；！？\n]{0,120}?不一致", r"补充协议"), "本合同文件发生冲突时，双方签署日期较后的补充协议或特别条款优先于合同正文，合同正文优先于一般性条款；技术协议仅就技术事项优先，任何未能依前述顺序解决的冲突均须由双方书面确认。", "长文档跨条款关联要求：技术协议、补充协议与合同正文冲突必须提示。", "先确定商业条款和技术条款各自优先级；避免“最有利于客户”的单方解释。"),
    Rule("IP_UNLIMITED", "知识产权", "知识产权保证或赔偿责任无上限", "高", (r"知识产权[^。；！？\n]{0,100}?(?:一切|全部)[^。；！？\n]{0,100}?损失", r"侵权[^。；！？\n]{0,100}?无条件", r"永久[^。；！？\n]{0,100}?使用权"), "知识产权保证仅适用于提供方自行提供且未经接收方或第三方修改、组合使用的产品；发生第三方侵权主张时，提供方可选择取得许可、替换或修改产品，无法实现时退还相应价款，且相关赔偿受本合同约定的责任总额上限约束。", "通用知识产权风险规则：赔偿范围应与可控行为、过错及合同价值相匹配。", "排除客户图纸、组合使用和擅自修改；控制第三方索赔程序。"),
    Rule("RENT_RETURN_130", "设备返还", "逾期返还占用费偏高", "中", (r"130%[^。；！？\n]{0,100}?(?:租金|占用)", r"逾期归还[^。；！？\n]{0,120}?1[23]0%"), "承租方逾期返还设备的，应按逾期期间对应日租金的百分之一百一十支付占用费；出租方应在收到返还通知后五个工作日内安排验收和提货，因出租方迟延接收产生的期间不计收占用费。", "占用费应补偿实际损失，不应因出租方迟延接收而持续累积。", "明确具备交还条件、通知方式、提货时限和正常损耗标准。"),
)


def default_replacement_clause(rule_code: str) -> str:
    base_code = str(rule_code or "").removeprefix("WEB_")
    rule = next((item for item in RULES if item.code == base_code), None)
    return rule.suggestion if rule else ""


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


ACCEPTED_DECISIONS = {"接纳", "修改后接纳"}
_GROUPED_EVIDENCE = re.compile(r"【命中\d+】(.*?)(?=\n【命中\d+】|\n【另有\d+处同类命中】|$)", re.DOTALL)
_REVISION_PLACEHOLDER = re.compile(
    r"(?:x{2,}|ｘ{2,}|todo|tbd|待补充|待确认|待完善|占位|【[^】]{0,40}】|\[[^\]]{0,40}\]|_{2,})",
    re.IGNORECASE,
)
_DIRECTIONAL_DRAFT = re.compile(r"^(?:建议|请|需要|需|应当?考虑|删除|修改|调整|补充|改为|将.+?(?:改为|调整为|修改为))")
_CLAUSE_LABEL = re.compile(
    r"^\s*(?P<label>(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*(?:条|款|章|节)|\d+(?:\.\d+)+(?:[、.．])?|\d+[、.．]|[零一二三四五六七八九十百千万]+[、.．]))"
)

# These topic groups are deliberately narrower than generic contract words.
# A replacement may change the risky number, party or trigger, but it must stay
# in the same legal/business topic as the source clause. This prevents a model
# from returning a polished but unrelated boilerplate paragraph.
_RELATION_TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "付款": ("付款", "支付", "账期", "价款", "款项", "租金", "费用", "发票", "结算"),
    "交付验收": ("交付", "交货", "到货", "验收", "签收", "试运行", "瑕疵", "质保"),
    "租赁期限": ("租赁", "租期", "续租", "返还", "占用", "提货"),
    "解除终止": ("解除", "终止", "催告", "交接"),
    "违约责任": ("违约", "赔偿", "损失", "违约金", "责任上限", "间接损失"),
    "合同主体": ("甲方", "乙方", "出租方", "承租方", "供应方", "采购方", "提供方", "服务方"),
    "维保服务": ("维修", "保养", "维保", "驻场", "备用车", "服务"),
    "争议解决": ("争议", "法院", "管辖", "仲裁", "诉讼"),
    "转让转包": ("转让", "转包", "关联公司", "融资"),
    "关联方": ("关联方", "关联企业", "同一控制", "连带"),
    "外部条款": ("网站", "网页", "官网", "网址", "抓取", "哈希", "版本", "条款"),
    "附件效力": ("附件", "技术协议", "补充协议", "正文", "优先"),
    "知识产权": ("知识产权", "侵权", "许可", "第三方"),
    "保密数据": ("保密", "披露", "秘密", "数据"),
    "安全保险": ("人身安全", "安全责任", "保险", "事故"),
    "单方解释": ("解释权", "单方解释", "判断标准", "无条件承担", "一切责任"),
}
# Party role words (甲方、乙方、出租方等) occur in almost every contract
# clause.  They help explain a change, but are not by themselves evidence that
# a replacement remains about the same risk.  A payment clause and a
# termination clause that both mention “甲方” must still be rejected as
# unrelated.
_GENERIC_RELATION_TOPICS = {"合同主体"}
_RELATION_STOPWORDS = {
    "合同", "本合同", "双方", "任何一方", "一方", "对方", "相关", "约定", "事项", "应当", "可以", "不得", "应", "并", "及", "的",
}
_GENERIC_RELATION_FRAGMENTS = (
    "甲方", "乙方", "出租方", "承租方", "供应方", "采购方", "提供方", "服务方", "双方", "任何一方", "一方", "对方", "本合同", "合同",
    "应当", "可以", "不得", "应", "并", "及", "的",
)
_NUMERIC_ANCHOR = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:%|％|‰|天|日|个月|年|小时|万元|元|台)|\d+(?:\.\d+)?|百分之[一二三四五六七八九十百千万]+|[一二三四五六七八九十百千万]+个?工作日|[一二三四五六七八九十百千万]+(?:日|天|个月|年|小时|万元|元|台))",
    re.IGNORECASE,
)
_TRIGGER_TERMS = ("如果", "若", "如", "当", "发生", "逾期", "未", "经", "收到", "届满", "符合")
_PARTY_ROLE_PATTERN = re.compile(r"甲方|乙方|出租方|承租方|供应方|采购方|提供方|服务方|买方|卖方")
_BILATERAL_PARTY_PATTERN = re.compile(r"双方|任何一方|各方|甲乙双方|甲方和乙方|甲方及乙方")
_OBLIGATION_AFTER_ROLE = re.compile(r"(?:违反|违约|迟延|逾期|应当?|须|负责|承担|支付|赔偿|履行|补足|更换|交付|返还|不得|有义务)")


def _accepted_evidence_fragments(original_text: str) -> list[str]:
    """Return source-like evidence fragments from a single or grouped finding."""
    grouped = _GROUPED_EVIDENCE.findall(str(original_text or ""))
    candidates = grouped or [str(original_text or "")]
    fragments = []
    for candidate in candidates:
        fragment = normalize(candidate).strip("… ")
        if fragment:
            fragments.append(fragment)
    return fragments


def _rule_clause_fragments(source_text: str, rule_code: str) -> list[str]:
    """Locate only the clauses matched by a deterministic rule."""
    rule = next((item for item in RULES if item.code == rule_code), None)
    if not rule:
        return []
    ranges = []
    for pattern in rule.patterns:
        for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
            left = max((source_text.rfind(mark, 0, match.start()) for mark in _CLAUSE_BOUNDARIES), default=-1) + 1
            right_candidates = [position for mark in _CLAUSE_BOUNDARIES if (position := source_text.find(mark, match.end())) >= 0]
            right = min(right_candidates) + 1 if right_candidates else len(source_text)
            ranges.append((left, right))
    merged: list[tuple[int, int]] = []
    for left, right in sorted(ranges):
        if merged and left < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return [source_text[left:right] for left, right in merged]


def is_placeholder_revision_text(text: str) -> bool:
    """Reject obvious drafting placeholders before they become contract text."""
    value = normalize(str(text or ""))
    return not value or bool(_REVISION_PLACEHOLDER.search(value))


def is_direct_replacement_clause(text: str) -> bool:
    """A replacement must read as contract language, not drafting advice."""
    value = normalize(str(text or ""))
    return len(value) >= EVIDENCE_MIN_CHARS and not is_placeholder_revision_text(value) and not bool(_DIRECTIONAL_DRAFT.search(value))


def extract_clause_label(text: str) -> str:
    """Extract a leading article/section label without consuming its body."""
    match = _CLAUSE_LABEL.match(str(text or ""))
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group("label")).strip()


def preserve_clause_format(original_text: str, suggested_text: str, context_text: str = "") -> str:
    """Keep a source article/section prefix on a replacement clause.

    The source label is authoritative. If a model omits it, prefix it; if a
    model invents a different label, replace only that label and keep the
    generated clause body. New clauses are intentionally handled separately.
    """
    proposed = normalize(str(suggested_text or ""))
    if not proposed:
        return ""
    source_label = extract_clause_label(original_text) or extract_clause_label(context_text)
    if not source_label:
        return proposed
    proposed_match = _CLAUSE_LABEL.match(proposed)
    body = proposed[proposed_match.end() :].lstrip() if proposed_match else proposed
    return f"{source_label} {body}".strip()


def _source_occurrence_spans(source_text: str, evidence: str) -> list[tuple[int, int]]:
    """Return raw source spans for every whitespace-insensitive evidence hit."""
    source = str(source_text or "")
    needle = re.sub(r"\s+", "", str(evidence or ""))
    if not source or len(needle) < 4 or "…" in needle:
        return []
    compact_chars: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(source):
        if char.isspace():
            continue
        compact_chars.append(char)
        offsets.append(index)
    compact_source = "".join(compact_chars)
    spans: list[tuple[int, int]] = []
    start = compact_source.find(needle)
    while start >= 0:
        end = start + len(needle) - 1
        if end >= len(offsets):
            break
        spans.append((offsets[start], offsets[end] + 1))
        start = compact_source.find(needle, end + 1)
    return spans


def source_occurrence_fragments(source_text: str, evidence: str) -> list[str]:
    """Return every source occurrence of an evidence phrase, ignoring whitespace."""
    source = str(source_text or "")
    return [source[start:end].strip() for start, end in _source_occurrence_spans(source, evidence)]


def source_occurrence_with_heading(source_text: str, evidence: str, occurrence_no: int = 1) -> str:
    """Expand a source hit to its nearest article/section label when safe.

    LLM evidence is often the risky sentence without its ``第七条`` prefix.
    Replacing only that sentence while prefixing the generated draft with the
    label would duplicate the label in the effective contract.  This helper
    therefore keeps the narrow evidence for display, but expands the internal
    replacement anchor to include the immediately preceding heading.
    """
    source = str(source_text or "")
    spans = _source_occurrence_spans(source, evidence)
    if not spans:
        return ""
    index = max(0, min(len(spans) - 1, int(occurrence_no or 1) - 1))
    start, end = spans[index]
    fragment = source[start:end].strip()
    if not fragment or extract_clause_label(fragment):
        return fragment
    boundaries = _CLAUSE_BOUNDARIES
    left_boundary = max((source.rfind(mark, 0, start) for mark in boundaries), default=-1) + 1
    heading_matches = list(
        re.finditer(
            r"(?m)(?:^|[。；！？;\n\r])\s*(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*(?:条|款|章|节)|(?:\d+(?:\.\d+)+|\d+)[、.．])",
            source[:start],
        )
    )
    if heading_matches:
        heading = heading_matches[-1]
        heading_start = heading.start()
        while heading_start < heading.end() and source[heading_start] in boundaries + " \t\r\n":
            heading_start += 1
        between = source[heading.end() : start]
        # A heading is part of this clause only when no sentence boundary
        # intervenes.  Keep the bound conservative to avoid swallowing a
        # previous paragraph into the replacement target.
        if heading_start >= left_boundary and len(between) <= 160 and not any(mark in between for mark in "。；！？"):
            return source[heading_start : end].strip()
    return fragment


def build_clause_context(source_text: str, evidence: str, max_chars: int = 1400, occurrence_no: int = 1) -> str:
    """Return a bounded source window including the nearest heading/paragraph."""
    source = str(source_text or "")
    fragments = source_occurrence_fragments(source, evidence)
    if not fragments:
        return ""
    fragment = fragments[max(0, min(len(fragments) - 1, int(occurrence_no or 1) - 1))]
    compact_source = re.sub(r"\s+", "", source)
    compact_fragment = re.sub(r"\s+", "", fragment)
    compact_start = -1
    search_from = 0
    for _ in range(max(1, int(occurrence_no or 1))):
        compact_start = compact_source.find(compact_fragment, search_from)
        if compact_start < 0:
            break
        search_from = compact_start + len(compact_fragment)
    if compact_start < 0:
        return fragment[:max_chars]
    # Map the compact offset back to the source string while retaining line
    # breaks and article numbering for the model's formatting decision.
    offsets = [index for index, char in enumerate(source) if not char.isspace()]
    start = offsets[compact_start]
    end = offsets[min(len(offsets) - 1, compact_start + len(compact_fragment) - 1)] + 1
    left_boundary = max((source.rfind(mark, 0, start) for mark in _CLAUSE_BOUNDARIES), default=-1) + 1
    heading_matches = list(re.finditer(r"(?m)^\s*(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*(?:条|款|章|节)|(?:\d+(?:\.\d+)+|\d+)[、.．])", source[:start]))
    if heading_matches:
        nearest_heading = heading_matches[-1]
        between_heading_and_hit = source[nearest_heading.end() : start]
        if nearest_heading.start() >= left_boundary or (
            "\n" in between_heading_and_hit
            and not any(mark in between_heading_and_hit for mark in "。；！？")
        ):
            left_boundary = nearest_heading.start()
    left = max(0, left_boundary)
    right = min(len(source), max(end, start + 1) + max_chars // 2)
    value = source[left:right].strip()
    if len(value) > max_chars:
        left = max(0, end - max_chars // 2)
        right = min(len(source), left + max_chars)
        value = source[left:right].strip()
        if len(value) > max_chars:
            value = value[: max_chars - 1].rstrip() + "…"
    return value


def _relation_topic_hits(text: str) -> dict[str, set[str]]:
    compact = normalize(str(text or ""))
    return {
        topic: {term for term in terms if term in compact}
        for topic, terms in _RELATION_TOPIC_TERMS.items()
        if any(term in compact for term in terms)
    }


def _relation_ngrams(text: str) -> set[str]:
    """Return short Chinese phrases useful for source-to-draft linkage."""
    values: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", normalize(str(text or ""))):
        for size in (2, 3, 4):
            values.update(run[index : index + size] for index in range(max(0, len(run) - size + 1)))
    return {value for value in values if value not in _RELATION_STOPWORDS and len(value) >= 2}


def _meaningful_relation_phrase(value: str) -> bool:
    """Avoid treating boilerplate such as “甲方应” as source linkage."""
    remainder = value
    for fragment in _GENERIC_RELATION_FRAGMENTS:
        remainder = remainder.replace(fragment, "")
    remainder = re.sub(r"[，。；！？：、\s]", "", remainder)
    return len(remainder) >= 2


def _relation_anchors(text: str) -> dict[str, list[str]]:
    value = normalize(str(text or ""))
    subjects = [term for term in _RELATION_TOPIC_TERMS["合同主体"] if term in value]
    numeric = list(dict.fromkeys(_NUMERIC_ANCHOR.findall(value)))
    triggers = [term for term in _TRIGGER_TERMS if term in value]
    return {"subjects": subjects, "numeric": numeric, "triggers": triggers}


def preserve_asymmetric_obligation_subject(original_text: str, suggested_text: str) -> str:
    """Keep an explicitly unilateral obligation tied to the same party.

    Generic risk rules often use ``任何一方``/``违约方`` so they can be reused
    across contracts. When the source clause clearly places the obligation on
    one named role (for example, ``乙方违反……``), blindly keeping that generic
    wording silently changes a unilateral obligation into a bilateral one. We
    only narrow the penalty-style boilerplate when the source is asymmetric;
    clauses that expressly use bilateral language remain untouched.
    """
    source = normalize(str(original_text or ""))
    proposed = normalize(str(suggested_text or ""))
    if not source or not proposed:
        return proposed
    topic_text = f"{source} {proposed}"
    if not any(term in topic_text for term in ("违约", "违约金", "赔偿", "损失", "责任上限")):
        return proposed
    if _BILATERAL_PARTY_PATTERN.search(source):
        return proposed
    role = ""
    for match in _PARTY_ROLE_PATTERN.finditer(source):
        tail = source[match.end() : match.end() + 18]
        if _OBLIGATION_AFTER_ROLE.search(tail):
            role = match.group(0)
            break
    if not role:
        return proposed
    # Replace only penalty-liability subjects. Other generic references (for
    # example, a bilateral dispute clause) must not be rewritten.
    replacements = (
        (r"任何一方\s*因违约承担", f"{role}因违约承担"),
        (r"任何一方\s*因违约", f"{role}因违约"),
        (r"任何一方\s*均?不对", f"{role}不对"),
        (r"违约方", role),
    )
    for pattern, replacement in replacements:
        proposed = re.sub(pattern, replacement, proposed)
    return proposed


def validate_replacement_clause(
    original_text: str,
    suggested_text: str,
    action_type: str = "替换条款",
) -> dict[str, object]:
    """Check that a proposed clause is usable and grounded in the source.

    Numeric values, parties and trigger conditions are allowed to change because
    those are often exactly what the review is correcting. The validator only
    rejects a draft when it is not contract language or has no meaningful topic
    and phrase linkage to the source clause.
    """
    source = normalize(str(original_text or ""))
    proposed = normalize(str(suggested_text or ""))
    result: dict[str, object] = {
        "status": "不可直接使用",
        "eligible": False,
        "relation_score": 0,
        "shared_topics": [],
        "shared_terms": [],
        "changed_anchors": {"subjects": [], "numeric": [], "triggers": []},
        "warnings": [],
    }
    if not is_direct_replacement_clause(proposed):
        result["warnings"] = ["替换稿不是完整合同条款，或仍包含修改指令/占位符。"]
        return result
    # A missing-section finding is intentionally an insertion, not a rewrite of
    # the context excerpt, so it only needs to pass the direct-clause guard.
    if str(action_type or "") == "新增条款":
        result.update({"status": "可直接插入", "eligible": True, "relation_score": 100})
        return result
    source_topics = _relation_topic_hits(source)
    proposed_topics = _relation_topic_hits(proposed)
    shared_topics = sorted(set(source_topics) & set(proposed_topics))
    meaningful_shared_topics = [topic for topic in shared_topics if topic not in _GENERIC_RELATION_TOPICS]
    source_terms = set().union(*(source_topics.get(topic, set()) for topic in meaningful_shared_topics)) if meaningful_shared_topics else set()
    proposed_terms = set().union(*(proposed_topics.get(topic, set()) for topic in meaningful_shared_topics)) if meaningful_shared_topics else set()
    shared_terms = sorted(source_terms & proposed_terms, key=lambda value: (-len(value), value))
    shared_phrases = {
        phrase
        for phrase in (_relation_ngrams(source) & _relation_ngrams(proposed))
        if _meaningful_relation_phrase(phrase)
    }
    long_phrase = max((len(value) for value in shared_phrases), default=0)
    score = min(100, len(shared_topics) * 28 + min(len(shared_terms), 5) * 9 + (18 if long_phrase >= 3 else 0))
    result["relation_score"] = score
    result["shared_topics"] = shared_topics
    result["shared_terms"] = shared_terms[:12]
    # A shared party role is too weak to ground a rewrite.  Require either a
    # non-generic legal/business topic or a concrete phrase carried over from
    # the source (useful for short clauses whose topic dictionary is sparse).
    if not meaningful_shared_topics or (not shared_terms and long_phrase < 3):
        result["warnings"] = ["替换稿与风险原文没有足够的风险主题或关键语义词关联，不能直接使用。"]
        return result

    source_anchors = _relation_anchors(source)
    proposed_anchors = _relation_anchors(proposed)
    changed: dict[str, list[str]] = {"subjects": [], "numeric": [], "triggers": []}
    warnings: list[str] = []
    if source_anchors["subjects"] and not proposed_anchors["subjects"] and not any(term in proposed for term in ("双方", "任何一方", "一方", "对方")):
        changed["subjects"] = source_anchors["subjects"]
        warnings.append("原文主体角色未在替换稿中明确保留。")
    if source_anchors["numeric"] and not proposed_anchors["numeric"]:
        changed["numeric"] = source_anchors["numeric"]
        warnings.append("原文含金额、比例或期限，但替换稿没有给出新的明确数值；请确认是否有意删除。")
    elif source_anchors["numeric"] and set(source_anchors["numeric"]) != set(proposed_anchors["numeric"]):
        changed["numeric"] = sorted(set(source_anchors["numeric"]) | set(proposed_anchors["numeric"]))
        warnings.append("金额、比例或期限发生变化；这是允许的风险修订项，但使用前请确认新数值。")
    if source_anchors["triggers"] and not proposed_anchors["triggers"]:
        changed["triggers"] = source_anchors["triggers"]
        warnings.append("原文触发条件未在替换稿中明显保留，请确认义务何时生效。")
    result["changed_anchors"] = changed
    result["warnings"] = warnings
    result["eligible"] = True
    result["status"] = "需人工确认变更" if warnings else "可直接使用"
    return result


def suggestion_risk_key(rule_code: str, original_text: str, occurrence_no: int = 1) -> str:
    compact = re.sub(r"\s+", "", str(original_text or "")).casefold()
    digest = hashlib.sha1(compact.encode("utf-8")).hexdigest()[:14]
    return f"{rule_code}:{digest}:{occurrence_no}"


def finalize_suggestion_metadata(findings: list[dict]) -> list[dict]:
    """Give every independently actionable source clause a stable identity."""
    totals: dict[str, int] = {}
    seen: dict[str, int] = {}
    for item in findings:
        code = str(item.get("rule_code") or "GENERAL_REVIEW")
        totals[code] = totals.get(code, 0) + 1
    for item in findings:
        code = str(item.get("rule_code") or "GENERAL_REVIEW")
        seen[code] = seen.get(code, 0) + 1
        number = int(item.get("occurrence_no") or seen[code])
        count = max(int(item.get("occurrence_count") or totals[code]), totals[code])
        item["occurrence_no"] = number
        item["occurrence_count"] = count
        item.setdefault("action_type", "替换条款")
        item["risk_key"] = str(item.get("risk_key") or suggestion_risk_key(code, str(item.get("original_text") or ""), number))
    return findings


def _replace_unique_ignoring_whitespace(source: str, fragment: str, replacement: str) -> tuple[str, bool]:
    """Replace one unambiguous fragment while preserving offsets in PDF text."""
    compact_fragment = re.sub(r"\s+", "", fragment)
    if len(compact_fragment) < EVIDENCE_MIN_CHARS:
        return source, False
    compact_chars: list[str] = []
    source_offsets: list[int] = []
    for index, char in enumerate(source):
        if char.isspace():
            continue
        compact_chars.append(char)
        source_offsets.append(index)
    compact_source = "".join(compact_chars)
    start = compact_source.find(compact_fragment)
    if start < 0 or compact_source.find(compact_fragment, start + 1) >= 0:
        return source, False
    end = start + len(compact_fragment) - 1
    source_start = source_offsets[start]
    source_end = source_offsets[end] + 1
    return source[:source_start] + replacement + source[source_end:], True


def _insert_after_unique_ignoring_whitespace(source: str, fragment: str, insertion: str) -> tuple[str, bool]:
    """Insert after one unambiguous source anchor while preserving source text."""
    compact_fragment = re.sub(r"\s+", "", fragment)
    if len(compact_fragment) < EVIDENCE_MIN_CHARS:
        return source, False
    compact_chars: list[str] = []
    source_offsets: list[int] = []
    for index, char in enumerate(source):
        if char.isspace():
            continue
        compact_chars.append(char)
        source_offsets.append(index)
    compact_source = "".join(compact_chars)
    start = compact_source.find(compact_fragment)
    if start < 0 or compact_source.find(compact_fragment, start + 1) >= 0:
        return source, False
    end = start + len(compact_fragment) - 1
    source_end = source_offsets[end] + 1
    return source[:source_end] + "\n" + insertion + source[source_end:], True


def apply_accepted_suggestions(source_text: str, suggestions: list) -> tuple[str, list[str], list[str]]:
    """Apply accepted decisions to the effective text used by later reviews."""
    rendered = source_text
    applied: list[str] = []
    unmatched: list[str] = []
    for suggestion in suggestions:
        if getattr(suggestion, "decision", "") not in ACCEPTED_DECISIONS:
            continue
        suggestion_id = str(getattr(suggestion, "id", ""))
        raw_proposed = str(getattr(suggestion, "suggested_text", "") or "").strip()
        proposed = normalize(raw_proposed)
        action_type = str(getattr(suggestion, "action_type", "替换条款") or "替换条款")
        if action_type == "新增条款":
            # New clauses are inserted, not replaced. Keep their line breaks
            # and numbering so the effective document retains the source
            # formatting style.
            proposed = raw_proposed
            if not proposed or not is_direct_replacement_clause(proposed):
                unmatched.append(suggestion_id)
                continue
            anchors = _accepted_evidence_fragments(getattr(suggestion, "anchor_text", ""))
            inserted = False
            for anchor in anchors[:1]:
                if anchor in rendered:
                    position = rendered.find(anchor) + len(anchor)
                    rendered = rendered[:position] + "\n" + proposed + rendered[position:]
                    inserted = True
                    break
                flexible = re.compile(re.escape(anchor).replace(r"\ ", r"\s+"))
                match = flexible.search(rendered)
                if match:
                    rendered = rendered[:match.end()] + "\n" + proposed + rendered[match.end():]
                    inserted = True
                    break
                rendered, inserted = _insert_after_unique_ignoring_whitespace(rendered, anchor, proposed)
                if inserted:
                    break
            # A missing-section recommendation has no risk anchor. Appending
            # it keeps the accepted clause in the effective contract instead
            # of incorrectly replacing an unrelated paragraph.
            if not inserted and not anchors:
                rendered = rendered.rstrip() + "\n" + proposed
                inserted = True
            if inserted:
                applied.append(suggestion_id)
            else:
                unmatched.append(suggestion_id)
            continue
        # New findings are one risk clause per row, so the anchored original is
        # authoritative. The broad rule lookup remains only as a legacy fallback.
        fragments = _accepted_evidence_fragments(getattr(suggestion, "anchor_text", "") or getattr(suggestion, "original_text", ""))
        if not fragments:
            fragments = _rule_clause_fragments(rendered, str(getattr(suggestion, "rule_code", "")))
        if not proposed or not fragments:
            unmatched.append(suggestion_id)
            continue
        changed = False
        for fragment in fragments:
            if fragment in rendered:
                rendered = rendered.replace(fragment, proposed, 1)
                changed = True
                continue
            flexible = re.compile(re.escape(fragment).replace(r"\ ", r"\s+"))
            if flexible.search(rendered):
                rendered = flexible.sub(lambda _: proposed, rendered, count=1)
                changed = True
                continue
            rendered, whitespace_matched = _replace_unique_ignoring_whitespace(rendered, fragment, proposed)
            changed = changed or whitespace_matched
        if changed:
            applied.append(suggestion_id)
        else:
            unmatched.append(suggestion_id)
    return rendered, applied, unmatched


EVIDENCE_MIN_CHARS = 8
EVIDENCE_MAX_CHARS = 2000
_CLAUSE_BOUNDARIES = "。；！？;\n\r"


def bound_evidence_text(
    evidence: str,
    min_chars: int = EVIDENCE_MIN_CHARS,
    max_chars: int = EVIDENCE_MAX_CHARS,
) -> str:
    """Apply the final evidence-size guard while preserving multi-hit line breaks."""
    lines = [normalize(line) for line in str(evidence or "").replace("\r\n", "\n").split("\n")]
    value = "\n".join(line for line in lines if line).strip()
    if len(value) < min_chars:
        return ""
    if len(value) > max_chars:
        value = value[: max_chars - 1].rstrip() + "…"
    return value


def excerpt(text: str, start: int, end: int, max_chars: int = EVIDENCE_MAX_CHARS) -> str:
    """Return the hit clause plus limited context, never a cross-document span."""
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    search_left = max(0, start - 140)
    boundary_left = max((text.rfind(mark, search_left, start) for mark in _CLAUSE_BOUNDARIES), default=-1)
    left = boundary_left + 1 if boundary_left >= search_left else search_left
    search_right = min(len(text), max(end, start + 1) + 220)
    boundary_rights = [position for mark in _CLAUSE_BOUNDARIES if (position := text.find(mark, end, search_right)) >= 0]
    right = min(boundary_rights) + 1 if boundary_rights else search_right
    if right - left > max_chars:
        left = max(left, start - 100)
        right = min(len(text), max(end, start + 1) + max_chars - (start - left))
        if right - left > max_chars:
            right = left + max_chars
    prefix = "…" if left else ""
    suffix = "…" if right < len(text) else ""
    value = normalize(text[left:right])
    value_budget = max(1, max_chars - len(prefix) - len(suffix))
    if len(value) > value_budget:
        value = value[: value_budget - 1].rstrip() + "…"
        suffix = ""
    return prefix + value + suffix


def refine_evidence(source_text: str, evidence: str, min_chars: int = EVIDENCE_MIN_CHARS, max_chars: int = EVIDENCE_MAX_CHARS) -> str:
    """Validate model/rule evidence and expand or cap it against the source."""
    source = normalize(source_text)
    value = normalize(evidence)
    if not value:
        return ""
    if len(value.strip("…，。；！？;:： ")) < 4:
        return ""
    position = source.casefold().find(value.casefold())
    if position >= 0 and (len(value) < min_chars or len(value) > max_chars):
        value = excerpt(source, position, position + len(value), max_chars=max_chars)
    elif len(value) > max_chars:
        value = value[: max_chars - 1].rstrip() + "…"
    return bound_evidence_text(value, min_chars=min_chars, max_chars=max_chars)


def classify_template(text: str) -> str:
    compact = re.sub(r"\s+", "", text).lower()
    plain = text.lower()
    standard = any(
        marker in compact
        for marker in (
            "林德（中国）叉车有限公司设备租赁合同的一般性条款",
            "林德(中国)叉车有限公司设备租赁合同的一般性条款",
            "林德（中国）叉车有限公司设备销售、交货和保修一般性条款和条件",
            "林德(中国)叉车有限公司设备销售、交货和保修一般性条款和条件",
        )
    ) or (
        "terms of payment" in plain
        and "linde" in plain
        and ("lessor" in plain or "出租方" in plain)
    )
    if standard:
        if any(marker in text for marker in ("[Word批注", "[PDF批注", "[修订插入", "[修订删除", "[文档图片OCR")):
            return "标准合同（有偏离）"
        return "标准合同"
    return "客户版本"


def compare_versions(previous: str, current: str) -> str:
    if not previous.strip():
        return "首轮审核，无上一版本。"
    previous_lines = [normalize(line) for line in previous.splitlines() if len(normalize(line)) >= 8]
    current_lines = [normalize(line) for line in current.splitlines() if len(normalize(line)) >= 8]
    diff = list(difflib.unified_diff(previous_lines, current_lines, lineterm="", n=0))
    additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    ratio = difflib.SequenceMatcher(None, normalize(previous), normalize(current)).ratio()
    return f"与上一版文本相似度 {ratio:.0%}；新增/改写约 {additions} 段，删除约 {deletions} 段。"


def rule_evidence_occurrences(text: str, rule: Rule) -> list[str]:
    """Return one bounded source clause per distinct risk occurrence."""
    raw_matches = sorted(
        (match.start(), match.end())
        for pattern in rule.patterns
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    )
    matches: list[tuple[int, int]] = []
    for start, end in raw_matches:
        boundary_left = max((text.rfind(mark, 0, start) for mark in _CLAUSE_BOUNDARIES), default=-1)
        boundary_rights = [position for mark in _CLAUSE_BOUNDARIES if (position := text.find(mark, end)) >= 0]
        clause_end = min(boundary_rights) + 1 if boundary_rights else len(text)
        matches.append((boundary_left + 1, clause_end))
    matches.sort()
    distinct: list[tuple[int, int]] = []
    for start, end in matches:
        if distinct and start < distinct[-1][1]:
            previous_start, previous_end = distinct[-1]
            distinct[-1] = (previous_start, max(previous_end, end))
        else:
            distinct.append((start, end))
    return [bound_evidence_text(text[start:end]) for start, end in distinct]


def rule_evidence(text: str, rule: Rule, max_occurrences: int = 3) -> tuple[str, list[str], int]:
    """Legacy grouped representation retained for old exports and callers."""
    occurrences = rule_evidence_occurrences(text, rule)
    visible = occurrences[:max_occurrences]
    remaining = len(occurrences) - len(visible)
    if not visible:
        return "", [], 0
    combined = visible[0] if len(visible) == 1 and not remaining else "\n".join(
        f"【命中{index}】{value}" for index, value in enumerate(visible, start=1)
    ) + (f"\n【另有{remaining}处同类命中】" if remaining else "")
    return bound_evidence_text(combined), visible, len(occurrences)


def _legacy_rule_findings(content: str, historical_text: str = "") -> list[dict]:
    """Return the legacy regex findings without mixing in knowledge-base output.

    Production can run these rules in shadow mode as recall hints.  Keeping the
    result separate prevents hard-coded legacy policy from competing with the
    versioned Playbook and knowledge base for the final decision.
    """
    findings: list[dict] = []
    for rule in RULES:
        occurrences = rule_evidence_occurrences(content, rule)
        occurrence_count = len(occurrences)
        for occurrence_no, original in enumerate(occurrences, start=1):
            if not original or len(original.strip("…，。；！？;:： \n")) < EVIDENCE_MIN_CHARS:
                continue
            tokens = re.findall(r"[\u4e00-\u9fff]{4,}", original)[:2]
            historical_release = bool(historical_text and any(token in historical_text for token in tokens))
            findings.append(
                {
                    "rule_code": rule.code,
                    "risk_key": suggestion_risk_key(rule.code, original, occurrence_no),
                    "action_type": "替换条款",
                    "occurrence_no": occurrence_no,
                    "occurrence_count": occurrence_count,
                    "category": rule.category,
                    "title": rule.title,
                    "risk_level": rule.risk_level,
                    "original_text": original,
                    "suggested_text": preserve_asymmetric_obligation_subject(
                        original,
                        preserve_clause_format(original, rule.suggestion),
                    ),
                    "basis": rule.basis,
                    "negotiation_focus": rule.negotiation_focus + (f" 本合同共识别到 {occurrence_count} 处同类表述，本项为第 {occurrence_no} 处，应单独处置。" if occurrence_count > 1 else ""),
                    "source": "旧正则风险规则",
                    "confidence": 91 if rule.risk_level == "高" else 84,
                    "historical_release": historical_release,
                    "anchor_text": original,
                }
            )
    return findings


def legacy_rule_candidates(text: str, historical_text: str = "") -> list[dict]:
    """Expose legacy matches as non-authoritative retrieval hints only."""
    content = normalize(text)
    return [
        {
            "rule_code": item["rule_code"],
            "category": item["category"],
            "title": item["title"],
            "risk_level": item["risk_level"],
            "original_text": item["original_text"],
            "occurrence_no": item["occurrence_no"],
            "occurrence_count": item["occurrence_count"],
        }
        for item in _legacy_rule_findings(content, historical_text)
    ]


def review_text(
    text: str,
    previous_text: str = "",
    historical_text: str = "",
    contract_type: str = "",
    standard_clauses: list | None = None,
    has_annotations: bool = False,
    include_legacy_rules: bool = True,
    add_general_fallback: bool = True,
) -> dict:
    content = normalize(text)
    findings = _legacy_rule_findings(content, historical_text) if include_legacy_rules else []
    findings.extend(baseline_findings(content, contract_type, standard_clauses or []))
    findings.extend(outside_baseline_findings(content, [item["original_text"] for item in findings], contract_type))
    if add_general_fallback and not findings and content:
        findings.append(
            {
                "rule_code": "GENERAL_REVIEW",
                "category": "整体审阅",
                "title": "未命中明确红线，仍需人工复核关键商务条款",
                "risk_level": "低",
                "original_text": content[:360],
                "suggested_text": "双方确认，本合同正文及附件已完整约定合同主体、标的、金额、交付、验收、付款、质保、责任限制、解除及争议解决事项；正文与附件不一致的，以双方最后签署的书面文件为准。",
                "action_type": "替换条款",
                "basis": "通用合同完整性检查清单。",
                "negotiation_focus": "确认附件齐全、签署主体一致、关键空白项已填写。",
                "source": "通用检查清单",
                "confidence": 70,
                "historical_release": False,
                "anchor_text": content[:360],
            }
        )
    finalize_suggestion_metadata(findings)
    weights = {"高": 18, "中": 10, "低": 4}
    score = min(100, sum(weights.get(item["risk_level"], 2) for item in findings))
    risk_level = "高" if score >= 55 or sum(item["risk_level"] == "高" for item in findings) >= 3 else "中" if score >= 20 else "低"
    stats = {
        "high": sum(item["risk_level"] == "高" for item in findings),
        "medium": sum(item["risk_level"] == "中" for item in findings),
        "low": sum(item["risk_level"] == "低" for item in findings),
        "total": len(findings),
    }
    template_type = classify_template(content)
    if has_annotations and template_type == "标准合同":
        template_type = "标准合同（有偏离）"
    summary = f"识别为{template_type}，发现 {stats['total']} 项建议，其中高风险 {stats['high']} 项、中风险 {stats['medium']} 项。"
    return {
        "template_type": template_type,
        "risk_score": score,
        "risk_level": risk_level,
        "summary": summary,
        "comparison_summary": compare_versions(previous_text, content),
        "stats": stats,
        "suggestions": findings,
    }
