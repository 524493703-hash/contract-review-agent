import pytest

from app.services.baseline_service import BASELINE_TEXT_PATH, baseline_findings, parse_standard_clauses
from app.services.review_engine import EVIDENCE_MAX_CHARS, EVIDENCE_MIN_CHARS, apply_accepted_suggestions, build_clause_context, bound_evidence_text, classify_template, compare_versions, default_replacement_clause, is_direct_replacement_clause, is_placeholder_revision_text, legacy_rule_candidates, preserve_asymmetric_obligation_subject, preserve_clause_format, refine_evidence, review_text, source_occurrence_fragments, source_occurrence_with_heading, validate_replacement_clause
from app.services.redaction import redact_text
from app.services.website_terms import fetch_website_terms


def test_legacy_rules_can_run_as_shadow_candidates_without_final_findings():
    source = "甲方有权随时单方解除合同。"
    candidates = legacy_rule_candidates(source)
    assert any(item["rule_code"] == "TERMINATION_ONE_SIDED" for item in candidates)

    result = review_text(source, include_legacy_rules=False)
    assert "TERMINATION_ONE_SIDED" not in {item["rule_code"] for item in result["suggestions"]}


def test_review_engine_detects_sample_contract_risks():
    text = """设备租赁合同。租期届满后继续使用且出租方无异议的，视同自动续租。
    验收并收到发票后60日内支付。甲方有权单方解除合同。
    乙方迟延交付每日支付0.5%违约金并赔偿全部损失。
    客户标准条款见 https://example.com/terms。争议由甲方所在地法院管辖。"""
    result = review_text(text)
    codes = {item["rule_code"] for item in result["suggestions"]}
    assert {"LEASE_AUTO_RENEW", "PAYMENT_LONG", "PENALTY_EXCESSIVE", "TERMINATION_ONE_SIDED", "WEBSITE_TERMS", "JURISDICTION"} <= codes
    penalty = next(item for item in result["suggestions"] if item["rule_code"] == "PENALTY_EXCESSIVE")
    assert "乙方因违约承担" in penalty["suggested_text"]
    assert "任何一方因违约承担" not in penalty["suggested_text"]
    assert result["risk_level"] == "高"
    assert result["template_type"] == "客户版本"


def test_penalty_replacement_preserves_unilateral_obligor():
    original = "如果乙方违反此保证，甲方有权解除合同，并要求乙方承担合同总额30%的违约金。"
    suggested = default_replacement_clause("PENALTY_EXCESSIVE")
    revised = preserve_asymmetric_obligation_subject(original, suggested)
    assert "乙方因违约承担" in revised
    assert "乙方仅赔偿" in revised
    assert "任何一方因违约承担" not in revised
    assert "任何一方均不对" not in revised


def test_penalty_replacement_keeps_bilateral_source_generic():
    original = "任何一方违反本合同的，违约方应承担相应责任。"
    suggested = default_replacement_clause("PENALTY_EXCESSIVE")
    assert preserve_asymmetric_obligation_subject(original, suggested) == suggested


def test_standard_classification_and_version_summary():
    standard = "林德（中国）叉车有限公司设备租赁合同的一般性条款 2025年01版 Linde (China) Forklift"
    assert classify_template(standard) == "标准合同"
    summary = compare_versions("付款期30日。", "付款期60日。增加自动续租。")
    assert "相似度" in summary
    assert "新增" in summary


def test_redaction_and_website_ssrf_guard():
    redacted, counts = redact_text("联系人13812345678，邮箱alice@example.com，身份证110101199001011234")
    assert "138****5678" in redacted
    assert "ali***@example.com" in redacted
    assert counts["手机号"] == 1
    capture = fetch_website_terms("http://127.0.0.1/private")
    assert capture.status == "抓取失败"
    assert "非公网" in capture.message


@pytest.mark.parametrize(
    ("rule_code", "clause"),
    [
        ("LEASE_AUTO_RENEW", "租期届满后自动续租。"),
        ("PAYMENT_LONG", "验收合格后60日内支付全部价款。"),
        ("PENALTY_EXCESSIVE", "乙方应赔偿甲方全部损失。"),
        ("AFFILIATE_SCOPE", "各关联方之间互不承担连带责任。"),
        ("ACCEPTANCE_SILENCE", "甲方5个工作日内未提出异议视为验收。"),
        ("TERMINATION_ONE_SIDED", "甲方有权随时单方解除合同。"),
        ("MAINTENANCE_SUSPEND", "承租方逾期超过30天，出租方可暂停维修和保养。"),
        ("JURISDICTION", "争议由甲方所在地人民法院管辖。"),
        ("ASSIGNMENT", "未经甲方书面同意，乙方不得转让本合同权利。"),
        ("WEBSITE_TERMS", "客户条款见 https://example.com/terms。"),
        ("ATTACHMENT_CONFLICT", "技术协议作为本合同附件。"),
        ("IP_UNLIMITED", "知识产权侵权导致的一切责任及全部损失由乙方承担。"),
        ("RENT_RETURN_130", "设备逾期归还期间按130%租金支付占用费。"),
    ],
)
def test_each_custom_rule_has_a_deterministic_positive_case(rule_code: str, clause: str):
    codes = {item["rule_code"] for item in review_text(clause)["suggestions"]}
    assert rule_code in codes


def test_custom_rules_do_not_flag_compliant_payment_renewal_or_jurisdiction():
    compliant = "验收合格后30日内支付。租期届满须双方书面确认后续租。争议由被告所在地法院管辖。"
    codes = {item["rule_code"] for item in review_text(compliant)["suggestions"]}
    assert {"PAYMENT_LONG", "LEASE_AUTO_RENEW", "JURISDICTION"}.isdisjoint(codes)


def test_risk_evidence_is_clause_scoped_and_length_bounded():
    unrelated = "设备应当符合技术指标并完成安装调试，双方应配合验收。" * 180
    text = f"第一条 定义。验收合格后60日内支付全部价款。{unrelated}最后一笔款项应按约支付。"
    result = review_text(text)
    payment = next(item for item in result["suggestions"] if item["rule_code"] == "PAYMENT_LONG")
    assert EVIDENCE_MIN_CHARS <= len(payment["original_text"]) <= EVIDENCE_MAX_CHARS
    assert "60日内支付" in payment["original_text"]
    assert "最后一笔款项" not in payment["original_text"]
    assert all(EVIDENCE_MIN_CHARS <= len(item["original_text"]) <= EVIDENCE_MAX_CHARS for item in result["suggestions"])


def test_short_evidence_expands_to_source_clause_and_invalid_fragment_is_rejected():
    source = "付款条件：合同签订后支付30%预付款，验收完成后支付余款。"
    expanded = refine_evidence(source, "支付余款")
    assert len(expanded) >= EVIDENCE_MIN_CHARS
    assert "验收完成后支付余款" in expanded
    assert refine_evidence(source, "余款") == ""


def test_same_risk_splits_multiple_occurrences_for_independent_decisions():
    text = "第一笔货款在验收后60日内支付。第二笔服务费在结算后90天内支付。尾款在开票后120日内支付。备用条款约定60日内支付。"
    result = review_text(text)
    payment_rows = [item for item in result["suggestions"] if item["rule_code"] == "PAYMENT_LONG"]
    assert len(payment_rows) == 4
    assert [item["occurrence_no"] for item in payment_rows] == [1, 2, 3, 4]
    assert all(item["occurrence_count"] == 4 for item in payment_rows)
    assert len({item["risk_key"] for item in payment_rows}) == 4
    assert all("【命中" not in item["original_text"] for item in payment_rows)
    assert all(item["action_type"] == "替换条款" for item in payment_rows)
    assert "第一笔货款" in payment_rows[0]["original_text"] and "第二笔服务费" not in payment_rows[0]["original_text"]
    assert "第二笔服务费" in payment_rows[1]["original_text"] and "尾款" not in payment_rows[1]["original_text"]


def test_final_evidence_guard_preserves_multi_hit_lines_and_rejects_short_text():
    grouped = "【命中1】验收后90日内支付。\n【命中2】开票后120日内支付。"
    assert bound_evidence_text(grouped) == grouped
    assert bound_evidence_text("余款") == ""
    assert len(bound_evidence_text("有效风险原文" * 1000)) == EVIDENCE_MAX_CHARS


def test_multiple_patterns_in_the_same_clause_count_as_one_occurrence():
    text = "客户官网条款详见网站公布的条款。其他约定不变。"
    website = next(item for item in review_text(text)["suggestions"] if item["rule_code"] == "WEBSITE_TERMS")
    assert "【命中2】" not in website["original_text"]
    assert "共识别到" not in website["negotiation_focus"]


def test_accepted_suggestion_changes_the_next_review_text():
    class Suggestion:
        id = "sug_payment"
        decision = "修改后接纳"
        original_text = "验收合格后60日内支付全部价款。"
        suggested_text = "验收合格并收到发票后30日内支付全部价款。"

    rendered, applied, unmatched = apply_accepted_suggestions(
        "设备租赁合同。\n验收合格后60日内支付全部价款。其他条款不变。",
        [Suggestion()],
    )
    assert applied == ["sug_payment"]
    assert unmatched == []
    assert "60日内支付" not in rendered
    assert "30日内支付" in rendered
    assert "PAYMENT_LONG" not in {item["rule_code"] for item in review_text(rendered)["suggestions"]}


def test_same_rule_occurrences_are_applied_independently():
    class FirstSuggestion:
        id = "sug_first"
        decision = "修改后接纳"
        rule_code = "PAYMENT_LONG"
        original_text = "第一笔货款在验收后60日内支付。"
        anchor_text = original_text
        suggested_text = "第一笔货款应在验收合格并收到发票后三十日内支付。"

    class SecondSuggestion:
        id = "sug_second"
        decision = "拒绝"
        rule_code = "PAYMENT_LONG"
        original_text = "第二笔服务费在结算后90天内支付。"
        anchor_text = original_text
        suggested_text = "第二笔服务费应在结算后三十日内支付。"

    source = "第一笔货款在验收后60日内支付。第二笔服务费在结算后90天内支付。"
    rendered, applied, unmatched = apply_accepted_suggestions(source, [FirstSuggestion(), SecondSuggestion()])
    assert applied == ["sug_first"]
    assert unmatched == []
    assert "第一笔货款应在验收合格" in rendered
    assert "第二笔服务费在结算后90天内支付" in rendered


def test_pdf_whitespace_does_not_block_an_unambiguous_accepted_change():
    class Suggestion:
        id = "sug_spare_parts"
        decision = "修改后接纳"
        rule_code = "LLM_DISCOVERY_8"
        original_text = "乙方所提供的设备备件，应保证质保期内和质保期满后一年内的备件的使用。无论是否在本合同有效期内，备件应与原部件完全相同。"
        suggested_text = "乙方应在质保期满后五年内继续供应备件，并提前六个月通知停产计划。"

    source = "3.乙方所提供的设备备件，应保证质保期内和质保期满后\n一年内的备件的使用。无\n论是否在本合同有效期内，备件应与原部件完全相同。4.其他约定。"
    rendered, applied, unmatched = apply_accepted_suggestions(source, [Suggestion()])
    assert applied == ["sug_spare_parts"]
    assert unmatched == []
    assert "质保期满后五年内" in rendered
    assert "3." in rendered and "4.其他约定" in rendered


def test_whitespace_insensitive_change_rejects_ambiguous_duplicate_clause():
    class Suggestion:
        id = "sug_duplicate"
        decision = "接纳"
        rule_code = "LLM_DISCOVERY_DUPLICATE"
        original_text = "乙方应在十日内交付设备。"
        suggested_text = "乙方应在十五日内交付设备。"

    source = "乙方应在十日内\n交付设备。附件再次记载：乙方应在十日内 交付设备。"
    rendered, applied, unmatched = apply_accepted_suggestions(source, [Suggestion()])
    assert rendered == source
    assert applied == []
    assert unmatched == ["sug_duplicate"]


def test_revision_placeholder_detection():
    assert is_placeholder_revision_text("应该XXX")
    assert is_placeholder_revision_text("待补充")
    assert is_placeholder_revision_text("租赁期限自【起租日期】起至【退租日期】止。")
    assert is_placeholder_revision_text("租赁期限自____年__月__日起计算。")
    assert not is_placeholder_revision_text("甲方应在十五个工作日内完成验收。")
    assert not is_direct_replacement_clause("建议将付款账期调整为30日。")
    assert is_direct_replacement_clause("甲方应在验收合格并收到发票后三十日内付款。")


def test_replacement_linkage_allows_intended_risk_field_changes():
    original = "验收合格后60日内支付全部价款。"
    revised = "付款方应在验收合格并收到合法有效发票之日起三十日内支付全部价款。"
    check = validate_replacement_clause(original, revised)
    assert check["eligible"] is True
    assert check["status"] == "需人工确认变更"
    assert "付款" in check["shared_topics"]
    assert "60日" in check["changed_anchors"]["numeric"]
    assert "三十日" in check["changed_anchors"]["numeric"]


def test_replacement_linkage_rejects_a_polished_but_unrelated_clause():
    original = "验收合格后60日内支付全部价款。"
    unrelated = "因本合同引起的争议，任何一方均可向被告所在地有管辖权的人民法院提起诉讼。"
    check = validate_replacement_clause(original, unrelated)
    assert check["eligible"] is False
    assert check["status"] == "不可直接使用"
    assert check["warnings"]


def test_replacement_linkage_does_not_accept_a_shared_party_role_as_topic_link():
    original = "甲方有权单方解除合同。"
    unrelated = "甲方应在验收合格后30日内支付全部价款。"
    check = validate_replacement_clause(original, unrelated)
    assert check["eligible"] is False
    assert check["status"] == "不可直接使用"
    assert "关联" in "".join(check["warnings"])


def test_replacement_linkage_does_not_accept_only_generic_obligation_phrase():
    original = "乙方应完成设备交付。"
    unrelated = "乙方应在验收合格后30日内支付全部价款。"
    check = validate_replacement_clause(original, unrelated)
    assert check["eligible"] is False


def test_replacement_linkage_allows_balanced_party_and_trigger_rewrite():
    original = "甲方有权单方解除合同。"
    revised = "一方仅在对方发生重大违约且收到书面催告后十五日内仍未纠正时方可解除本合同。"
    check = validate_replacement_clause(original, revised)
    assert check["eligible"] is True
    assert "解除终止" in check["shared_topics"]
    assert check["changed_anchors"]["subjects"] == []


def test_replacement_preserves_source_article_label_and_context_heading():
    assert preserve_clause_format("第七条 付款方式：验收后60日内支付。", "付款方应在验收后30日内支付。") == "第七条 付款方应在验收后30日内支付。"
    assert preserve_clause_format("7.1 验收后60日内支付。", "第八条 付款方应在30日内支付。") == "7.1 付款方应在30日内支付。"
    context = build_clause_context("第七条 付款方式\n验收后60日内支付。\n第八条 其他约定\n设备交付。", "验收后60日内支付。")
    assert context.startswith("第七条")


def test_new_clause_has_no_risk_original_and_is_inserted_after_context_anchor():
    original = "合同主体明确，双方应按约履行。"
    proposed = "第七条 付款方式\n承租方应在验收合格并收到发票后三十日内支付租金。"

    class Suggestion:
        id = "sug_new_clause"
        decision = "修改后接纳"
        action_type = "新增条款"
        original_text = ""
        anchor_text = original
        suggested_text = proposed

    check = validate_replacement_clause("", proposed, "新增条款")
    assert check["eligible"] is True
    rendered, applied, unmatched = apply_accepted_suggestions(original, [Suggestion()])
    assert applied == ["sug_new_clause"]
    assert unmatched == []
    assert original in rendered
    assert proposed in rendered


def test_source_occurrences_and_context_keep_duplicate_hits_independent():
    source = "第七条 乙方应在验收后60日内支付。第八条 乙方应在验收后60日内支付。"
    evidence = "乙方应在验收后60日内支付。"
    occurrences = source_occurrence_fragments(source, evidence)
    assert len(occurrences) == 2
    assert source_occurrence_with_heading(source, evidence, 1).startswith("第七条")
    assert source_occurrence_with_heading(source, evidence, 2).startswith("第八条")
    assert build_clause_context(source, evidence, occurrence_no=1).startswith("第七条")
    assert build_clause_context(source, evidence, occurrence_no=2).startswith("第八条")


def test_heading_anchor_prevents_duplicate_article_number_when_applying_llm_rewrite():
    source = "第七条 乙方应在验收后60日内支付。"

    class Suggestion:
        id = "sug_heading"
        decision = "接纳"
        action_type = "替换条款"
        original_text = "乙方应在验收后60日内支付。"
        anchor_text = "第七条 乙方应在验收后60日内支付。"
        suggested_text = "第七条 乙方应在验收合格后三十日内支付。"

    rendered, applied, unmatched = apply_accepted_suggestions(source, [Suggestion()])
    assert applied == ["sug_heading"]
    assert unmatched == []
    assert rendered.count("第七条") == 1
    assert rendered == "第七条 乙方应在验收合格后三十日内支付。"


def test_lease_baseline_contains_all_major_sections_and_detects_a_modified_standard_clause():
    source = BASELINE_TEXT_PATH.read_text(encoding="utf-8")
    clauses = parse_standard_clauses(source)
    assert len(clauses) >= 50
    assert {item["clause_no"].split(".", 1)[0] for item in clauses} == {str(number) for number in range(1, 19)}
    records = [{**item, "id": f"std-{item['clause_no']}"} for item in clauses]
    assert baseline_findings(source, "租赁", records) == []

    changed = source.replace("承租方逾期归还设备，应按合同约定租金标准的130%支付", "承租方逾期归还设备，应按合同约定租金标准的200%支付")
    findings = baseline_findings(changed, "租赁", records)
    deviation = next(item for item in findings if item["rule_code"] == "BASELINE_DEVIATION_14_3")
    assert "第 14.3 条" in deviation["title"]
    assert "200%" in deviation["original_text"]
    assert "130%" in deviation["suggested_text"]
