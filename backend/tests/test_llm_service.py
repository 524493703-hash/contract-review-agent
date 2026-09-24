from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services import llm_service
from app.services.llm_service import SEVERITY_RUBRIC, SYSTEM_INSTRUCTIONS, _decode_json_object, adjudicate_focused_checks, analyze_contract, classify_llm_severity


def test_decode_json_object_accepts_gateway_wrappers():
    payload = _decode_json_object('审核结果如下：\n```json\n{"findings": []}\n```')
    assert payload == {"findings": []}


def test_decode_json_object_rejects_incomplete_output():
    with pytest.raises(ValueError):
        _decode_json_object('{"findings": [')


def test_model_prompt_bounds_original_evidence():
    assert "8至420个字符" in SYSTEM_INSTRUCTIONS
    assert "同一风险在合同中命中多个不同位置时" in SYSTEM_INSTRUCTIONS
    assert 'action_type“新增条款”' in SYSTEM_INSTRUCTIONS
    assert "同主题自检" in SYSTEM_INSTRUCTIONS


@pytest.mark.parametrize(
    ("impact", "likelihood", "remediation", "expected_level", "expected_score"),
    [
        (5, 1, 1, "高", 76),
        (4, 4, 3, "高", 78),
        (4, 1, 1, "中", 62),
        (3, 1, 1, "中", 48),
        (2, 3, 2, "低", 44),
        (1, 5, 5, "低", 44),
    ],
)
def test_llm_severity_matrix_is_deterministic(impact, likelihood, remediation, expected_level, expected_score):
    item = {"severity_factors": {"impact": impact, "likelihood": likelihood, "remediation": remediation, "reason": "基于合同条款"}}
    level, score, factors = classify_llm_severity(item)
    assert (level, score) == (expected_level, expected_score)
    assert factors["impact"] == impact


@pytest.mark.parametrize(
    "factors",
    [None, {}, {"impact": 6, "likelihood": 3, "remediation": 2, "reason": "超范围"}, {"impact": 3, "likelihood": 2, "remediation": 2, "reason": ""}],
)
def test_llm_severity_matrix_rejects_incomplete_or_invalid_factors(factors):
    assert classify_llm_severity({"severity_factors": factors}) is None


def test_model_rubric_requires_three_scored_dimensions_and_backend_recalculation():
    assert all(name in SEVERITY_RUBRIC for name in ("impact", "likelihood", "remediation"))
    assert "后端将按固定公式重新计算最终等级" in SEVERITY_RUBRIC


def test_backend_severity_ignores_the_models_free_form_level():
    item = {
        "risk_level": "高",
        "severity_factors": {"impact": 1, "likelihood": 2, "remediation": 1, "reason": "轻微文字问题"},
    }
    assert classify_llm_severity(item)[0] == "低"


def test_llm_duplicate_evidence_is_expanded_and_keeps_each_article_label(monkeypatch):
    payload = {
        "findings": [{
            "action_type": "替换条款",
            "category": "付款条件",
            "title": "付款账期过长",
            "risk_level": "中",
            "severity_factors": {"impact": 3, "likelihood": 3, "remediation": 2, "reason": "付款时间过长"},
            "original_text": "乙方应在验收后60日内支付。",
            "suggested_text": "乙方应在验收合格后三十日内支付。",
            "basis": "付款期限过长",
            "negotiation_focus": "确认账期和发票条件",
            "confidence": 88,
        }]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(llm_api_key="test-key", llm_api_url="http://llm.test", llm_model="test-model"),
    )
    findings, message = analyze_contract(
        "第七条 乙方应在验收后60日内支付。第八条 乙方应在验收后60日内支付。",
        [],
        "test-user",
    )
    assert message.startswith("大模型增强完成")
    assert len(findings) == 2
    assert findings[0]["original_text"] == findings[1]["original_text"]
    assert findings[0]["suggested_text"].startswith("第七条")
    assert findings[1]["suggested_text"].startswith("第八条")
    assert findings[0]["anchor_text"].startswith("第七条")
    assert findings[1]["anchor_text"].startswith("第八条")


def test_llm_new_clause_uses_empty_original_and_real_insertion_anchor(monkeypatch):
    payload = {
        "findings": [{
            "action_type": "新增条款",
            "category": "付款方式",
            "title": "缺少付款方式",
            "risk_level": "中",
            "severity_factors": {"impact": 3, "likelihood": 3, "remediation": 2, "reason": "基础付款条款缺失"},
            "original_text": "",
            "anchor_text": "第六条 其他约定。",
            "suggested_text": "第七条 付款方式\n承租方应在验收合格后三十日内支付租金。",
            "basis": "合同未明确付款方式",
            "negotiation_focus": "补充付款时间和条件",
            "confidence": 82,
        }]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(llm_api_key="test-key", llm_api_url="http://llm.test", llm_model="test-model"),
    )
    findings, _ = analyze_contract(
        "合同主体明确。第六条 其他约定。",
        [],
        "test-user",
    )
    assert len(findings) == 1
    assert findings[0]["action_type"] == "新增条款"
    assert findings[0]["original_text"] == ""
    assert findings[0]["anchor_text"] == "第六条 其他约定。"


def test_llm_unrelated_candidate_gets_topic_grounded_repair_before_drop(monkeypatch):
    payload = {
        "findings": [{
            "action_type": "替换条款",
            "category": "付款条件",
            "title": "付款账期过长",
            "risk_level": "中",
            "severity_factors": {"impact": 3, "likelihood": 3, "remediation": 2, "reason": "付款时间过长"},
            "original_text": "乙方应在验收后60日内支付。",
            "suggested_text": "因本合同引起的争议，任何一方均可向被告所在地法院起诉。",
            "basis": "付款期限过长",
            "negotiation_focus": "确认账期和发票条件",
            "confidence": 60,
        }]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(llm_api_key="test-key", llm_api_url="http://llm.test", llm_model="test-model"),
    )
    calls = []

    def fake_repair(**kwargs):
        calls.append(kwargs)
        assert "同一法律/业务主题" in kwargs["instruction"]
        assert "支付" in kwargs["risk_context"]
        return "付款方应在验收合格后三十日内支付。", "测试主题修复"

    monkeypatch.setattr(llm_service, "redraft_replacement_clause", fake_repair)
    findings, message = analyze_contract(
        "第七条 乙方应在验收后60日内支付。",
        [],
        "test-user",
    )
    assert len(findings) == 1
    assert findings[0]["suggested_text"].startswith("第七条")
    assert "自动重试，成功修复 1 项" in message
    assert len(calls) == 1


def test_redraft_retry_includes_validator_feedback(monkeypatch):
    responses = [
        {"replacement_clause": "因本合同引起的争议，任何一方均可向被告所在地法院起诉。"},
        {"replacement_clause": "付款方应在验收合格后三十日内支付相应款项。"},
    ]
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(self.payload, ensure_ascii=False)}}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **kwargs):
            requests.append(kwargs["json"])
            return FakeResponse(responses.pop(0))

    monkeypatch.setattr(llm_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(llm_api_key="test-key", llm_api_url="http://llm.test", llm_model="test-model"),
    )
    clause, message = llm_service.redraft_replacement_clause(
        original_text="乙方应在验收后60日内支付。",
        current_text="争议法院约定。",
        instruction="请保留付款主题并缩短账期",
        action_type="替换条款",
        title="付款账期过长",
        basis="付款规则",
        contract_context="第七条 乙方应在验收后60日内支付。",
        risk_context="第七条 乙方应在验收后60日内支付。",
    )
    assert clause.startswith("第七条 付款方应在验收合格后三十日内支付")
    assert message.startswith("大模型重新起草完成")
    assert len(requests) == 2
    retry_text = requests[1]["messages"][-1]["content"]
    assert "风险主题关联校验" in retry_text
    assert "支付" in retry_text


def test_llm_recomputes_legal_and_human_gate_after_status_change(monkeypatch):
    source = "本合同系出租方预先拟定的一般性条款。"
    model_payload = {
        "results": [{
            "check_code": "L-05",
            "status": "UNMET",
            "evidence_quotes": [source],
            "satisfied_slots": [],
            "missing_slots": ["slot_1", "slot_2"],
            "reason": "未见合理提示和协商留痕。",
            "confidence": 91,
            "need_legal_rag": False,
        }]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(model_payload, ensure_ascii=False)}}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(
            llm_api_key="test-key",
            llm_api_url="http://llm.test",
            llm_model="test-model",
            focused_check_model=None,
        ),
    )
    review = {
        "stats": {},
        "check_results": [{
            "check_code": "L-05",
            "check_name": "格式条款提示说明与协商留痕",
            "category": "格式条款",
            "status": "MET",
            "risk_level": "提示",
            "base_risk_level": "高",
            "confidence": 92,
            "satisfied_slots": ["slot_1", "slot_2"],
            "missing_slots": [],
            "contradictions": [],
            "reason": "初判满足",
            "decision_source": "deterministic_hybrid",
            "legal_rag_required": False,
            "legal_rag_triggers": ["格式条款效力", "提示说明义务"],
            "technical_status": "verified",
            "human_confirmation_required": False,
            "human_gate_policy": True,
            "evidence": [],
        }],
    }
    updated, message = adjudicate_focused_checks(source, review, "test-user")
    result = updated["check_results"][0]
    assert message.startswith("大模型四态裁决完成")
    assert result["status"] == "UNMET"
    assert result["risk_level"] == "高"
    assert result["legal_rag_required"] is True
    assert result["human_confirmation_required"] is True
    assert source[result["evidence"][0]["start_offset"]:result["evidence"][0]["end_offset"]] == source


def test_llm_keeps_deterministic_adverse_evidence(monkeypatch):
    source = "4.2 普通交付说明。\n4.3 每延迟一天支付千分之一违约金。"
    model_payload = {
        "results": [{
            "check_code": "L-29",
            "status": "UNMET",
            "evidence_quotes": ["普通交付说明"],
            "satisfied_slots": ["slot_1"],
            "missing_slots": ["slot_2"],
            "reason": "迟延交付责任偏重。",
            "confidence": 90,
            "need_legal_rag": True,
        }]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(model_payload, ensure_ascii=False)}}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(
            llm_api_key="test-key", llm_api_url="http://llm.test", llm_model="test-model", focused_check_model=None
        ),
    )
    adverse_start = source.index("4.3")
    adverse_evidence = [{
        "order_index": 1,
        "clause_no": "4.3",
        "page_no": 2,
        "source_file": "客户合同.docx",
        "page_method": "test",
        "start_offset": adverse_start,
        "end_offset": len(source),
        "quote": source[adverse_start:],
        "evidence_type": "contradict",
        "retrieval_methods": ["adverse_rule"],
        "score": 99,
    }]
    review = {
        "stats": {},
        "check_results": [{
            "check_code": "L-29",
            "check_name": "出租方迟延交付责任",
            "category": "交付",
            "status": "UNMET",
            "risk_level": "高",
            "base_risk_level": "高",
            "confidence": 96,
            "satisfied_slots": ["slot_1"],
            "missing_slots": ["slot_2"],
            "contradictions": [{"pattern": "千分之一", "quote": source[adverse_start:]}],
            "reason": "确定性不利规则",
            "decision_source": "deterministic_hybrid",
            "legal_rag_required": True,
            "legal_rag_triggers": ["违约金调整"],
            "technical_status": "verified",
            "human_confirmation_required": True,
            "human_gate_policy": True,
            "evidence": adverse_evidence,
            "retrieval_trace": {"query_pack": {}, "candidates": [
                {"clause_no": "4.2", "start_offset": 0, "end_offset": adverse_start, "quote": source[:adverse_start]},
                {"clause_no": "4.3", "start_offset": adverse_start, "end_offset": len(source), "quote": source[adverse_start:]},
            ]},
        }],
    }
    updated, _ = adjudicate_focused_checks(source, review, "test-user")
    assert updated["check_results"][0]["evidence"] == adverse_evidence
