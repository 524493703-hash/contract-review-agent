from datetime import date

from app.services.contract_integrity import audit_contract_integrity


def test_integrity_checks_detect_arithmetic_units_expiry_and_trace():
    text = """合同有效期：2024年5月1日到2026年4月30日。
报价均包含运费和税率（税点13%）。物料 | 未税 | 含税
纯租赁叉车 | 2654.87 | 30000
8.转弯半径不超过30000mm；
"""
    source_map = [{
        "start_offset": 0,
        "end_offset": len(text),
        "page_no": 7,
        "page_method": "test",
        "block_type": "page",
        "source_file": "客户合同.docx",
    }]
    findings = audit_contract_integrity(
        text,
        source_map=source_map,
        source_file="客户合同.docx",
        as_of_date=date(2026, 9, 11),
    )
    by_code = {item["rule_code"]: item for item in findings}
    assert {"DOC_PRICE_TAX_ARITHMETIC", "DOC_TECHNICAL_UNIT_OUTLIER", "DOC_CONTRACT_EXPIRED"} <= set(by_code)
    assert all(item["page_no"] == 7 for item in by_code.values())
    assert all(item["evidence_json"][0]["source_file"] == "客户合同.docx" for item in by_code.values())


def test_integrity_checks_detect_cross_clause_conflicts():
    text = """4.8 长租、短租均含运费。
附件二：短租租期不超过6个月，甲方承担运费。
5.1 至少1名专人驻场服务。
附件要求：租赁<50台，不提供驻场服务。
"""
    findings = audit_contract_integrity(text, source_file="客户合同.docx")
    codes = {item["rule_code"] for item in findings}
    assert "DOC_CONFLICT_FREIGHT" in codes
    assert "DOC_CONFLICT_RESIDENT_SERVICE" in codes
