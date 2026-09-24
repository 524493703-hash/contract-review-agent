from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import ClauseAtom, ClauseNode, FocusedCheck, KnowledgeDocument, LegalAuthority
from app.services.baseline_service import BASELINE_SOURCE_FILE, BASELINE_TEXT_PATH, baseline_findings, parse_standard_clauses
from app.services.focused_review import (
    CHECK_SPECS,
    evaluate_focused_checks,
    playbook_coverage,
    seed_structured_knowledge,
)
from app.services.legal_rag import retrieve_legal_authorities, seed_legal_authorities


def memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_structured_knowledge_seed_is_complete_and_idempotent():
    db = memory_session()
    first = seed_structured_knowledge(db)
    db.commit()
    second = seed_structured_knowledge(db)
    db.commit()

    assert first["authoritative_nodes"] == 66
    assert first["active_checks"] == 49
    assert first["unmapped_nodes"] == []
    assert second["unmapped_nodes"] == []
    assert playbook_coverage(db)["status"] == "COMPLETE"
    assert db.scalar(select(func.count()).select_from(KnowledgeDocument)) == 1
    assert db.scalar(select(func.count()).select_from(ClauseNode)) == 66
    assert db.scalar(select(func.count()).select_from(FocusedCheck)) == 49
    assert db.scalar(select(func.count()).select_from(ClauseAtom)) >= 120

    clause_15_1 = db.scalar(select(ClauseNode).where(ClauseNode.clause_no == "15.1"))
    atoms_15_1 = db.scalar(select(func.count()).select_from(ClauseAtom).where(ClauseAtom.clause_node_id == clause_15_1.id))
    assert atoms_15_1 >= 12


def test_all_49_checks_run_and_evidence_offsets_bind_to_source():
    text = "设备租赁合同。设备所有权属于出租方，承租方不得抵押设备。租期届满后继续使用且出租方无异议的，视同自动续租。争议由出租方所在地法院管辖。"
    result = evaluate_focused_checks(text, contract_type="租赁", our_role="出租方")

    assert len(CHECK_SPECS) == 49
    assert len({item.code for item in CHECK_SPECS}) == 49
    assert result["coverage_status"] == "COMPLETE"
    assert result["stats"]["TOTAL"] == 49
    renewal = next(item for item in result["check_results"] if item["check_code"] == "L-43")
    assert renewal["status"] == "MET"
    assert renewal["evidence"]
    evidence = renewal["evidence"][0]
    assert text[evidence["start_offset"]:evidence["end_offset"]].replace("\n", " ").strip() == evidence["quote"]


def test_not_mentioned_is_not_claimed_when_parse_or_document_is_unverified():
    result = evaluate_focused_checks(
        "设备租赁合同。",
        contract_type="租赁",
        our_role="出租方",
        parse_status="OCR失败",
        document_complete=False,
    )
    assert result["coverage_status"] == "UNVERIFIABLE"
    assert result["stats"]["TECHNICAL_FAILURES"] == 49
    assert all(item["technical_status"] == "UNVERIFIABLE" for item in result["check_results"])


def test_playbook_is_role_specific():
    result = evaluate_focused_checks("设备租赁合同。", contract_type="租赁", our_role="承租方")
    assert result["coverage_status"] == "NOT_APPLICABLE"
    assert result["check_results"] == []


def test_template_integrity_never_caps_deviations_at_twelve():
    source = BASELINE_TEXT_PATH.read_text(encoding="utf-8")
    clauses = parse_standard_clauses(source)
    records = [{**item, "id": f"std-{item['clause_no']}"} for item in clauses]
    changed = source.replace("出租方", "出租人")
    findings = baseline_findings(changed, "租赁", records)
    assert len(findings) > 12
    assert all(item["check_status"] == "UNMET" for item in findings)
    assert all(item["deviation_type"] for item in findings)
    assert all(BASELINE_SOURCE_FILE in item["basis"] for item in findings)
    assert all("基准原文：" in item["basis"] for item in findings)


def test_legal_rag_is_versioned_effective_and_idempotent():
    db = memory_session()
    first = seed_legal_authorities(db)
    db.commit()
    second = seed_legal_authorities(db)
    db.commit()

    assert first["seeded"] == 11
    assert second["seeded"] == 11
    assert db.scalar(select(func.count()).select_from(LegalAuthority)) == 11

    before_new_rule = retrieve_legal_authorities(
        db,
        "特种设备 使用登记 定期检验 现行安全技术规范",
        as_of_date=date(2025, 1, 1),
    )
    assert before_new_rule
    assert all(item["authority"].effective_from <= date(2025, 1, 1) for item in before_new_rule)
    assert all("TSG 08—2026" not in item["authority"].document_no for item in before_new_rule)

    current = retrieve_legal_authorities(
        db,
        "特种设备 使用登记 定期检验 现行安全技术规范",
        as_of_date=date(2026, 9, 10),
    )
    assert any("TSG 08—2026" in item["authority"].document_no for item in current)
    assert all(item["authority"].source_url.startswith("https://") for item in current)

    penalty = retrieve_legal_authorities(
        db,
        "违约金调整 损失赔偿 可预见性",
        as_of_date=date(2026, 9, 10),
    )
    assert any(item["authority"].article_no == "第五百八十四条至第五百八十五条" for item in penalty)
    assert any(item["authority"].document_no == "法释〔2023〕13号" for item in penalty)


def test_unrelated_candidates_cannot_be_stitched_into_a_false_met():
    text = "举报材料可以发送至电子邮件。对质量有异议应书面提出。双方视为已收到通知。"
    result = evaluate_focused_checks(text, contract_type="租赁", our_role="出租方")
    electronic_invoice = next(item for item in result["check_results"] if item["check_code"] == "L-25")
    assert electronic_invoice["status"] == "NOT_MENTIONED"
    assert electronic_invoice["evidence"] == []


def test_deemed_acceptance_without_latent_defect_carveout_is_unmet():
    text = "4.5 甲方未在7个工作日内完成验收的，视为甲方验收合格。"
    result = evaluate_focused_checks(text, contract_type="租赁", our_role="出租方")
    acceptance = next(item for item in result["check_results"] if item["check_code"] == "L-32")
    assert acceptance["status"] == "UNMET"
    assert acceptance["evidence"][0]["clause_no"] == "4.5"
