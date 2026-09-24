from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    ApprovalTask,
    AuditLog,
    Contract,
    ContractVersion,
    KnowledgeEntry,
    NegotiationRecord,
    ReviewRun,
    ReviewSuggestion,
    ReviewerIdentity,
    User,
)
from .security import hash_password
from .services.review_engine import review_text
from .services.baseline_service import active_standard_clauses, seed_standard_clauses
from .services.focused_review import seed_structured_knowledge
from .services.legal_rag import seed_legal_authorities


def seed_database(db: Session) -> None:
    seed_standard_clauses(db)
    db.flush()
    seed_structured_knowledge(db)
    db.flush()
    seed_legal_authorities(db)
    db.flush()
    legacy_renewal = db.scalar(select(KnowledgeEntry).where(KnowledgeEntry.title == "租赁合同禁止默示自动续租"))
    if legacy_renewal:
        legacy_renewal.title = "出租方租赁合同续租立场"
        legacy_renewal.category = "租赁期限"
        legacy_renewal.content = "我方为出租方时，2025.01基准条款允许承租方继续使用且出租方无异议时视同续租；审核必须先绑定我方角色，不得套用承租方立场下的‘禁止默示续租’规则。"
        legacy_renewal.source = "林德租赁一般性条款2025.01/角色化Playbook"
        legacy_renewal.tags = ["租赁", "出租方", "自动续租", "角色化"]
    if db.scalar(select(func.count()).select_from(User)):
        db.commit()
        return
    settings = get_settings()
    initial_password = settings.initial_password
    users = [
        User(username="contract.admin", password_hash=hash_password(initial_password), name="张伟", email="zhang.wei@example.com", department="合同管理部", role="合同管理员"),
        User(username="legal.reviewer", password_hash=hash_password(initial_password), name="李思", email="li.si@example.com", department="法务部", role="法务审核"),
        User(username="finance.expert", password_hash=hash_password(initial_password), name="王芳", email="wang.fang@example.com", department="财务部", role="财务专家"),
        User(username="sales.owner", password_hash=hash_password(initial_password), name="陈晨", email="chen.chen@example.com", department="销售部", role="销售"),
        User(username="approver", password_hash=hash_password(initial_password), name="刘建平", email="liu.jp@example.com", department="管理层", role="审批人"),
        User(username="system.admin", password_hash=hash_password(initial_password), name="系统管理员", email="admin@example.com", department="信息技术部", role="系统管理员"),
    ]
    db.add_all(users)
    db.flush()
    db.add_all(
        ReviewerIdentity(alias=alias, display_name=user.name, source_kind="同事", department=user.department)
        for user in users
        for alias in (user.username, user.name, user.email.split("@", 1)[0])
    )
    by_role = {user.role: user for user in users}
    entries = [
        KnowledgeEntry(entry_type="规则", title="出租方租赁合同续租立场", category="租赁期限", content="我方为出租方时，2025.01基准条款允许承租方继续使用且出租方无异议时视同续租；审核必须先绑定我方角色，不得套用承租方立场下的‘禁止默示续租’规则。", source="林德租赁一般性条款2025.01/角色化Playbook", tags=["租赁", "出租方", "自动续租", "角色化"], risk_level="高"),
        KnowledgeEntry(entry_type="规则", title="违约责任累计上限", category="违约责任", content="违约金累计原则上不超过合同金额20%，责任应相互对等，仅覆盖可预见直接损失。", source="采购合同管理规则", tags=["违约金", "责任上限"], risk_level="高"),
        KnowledgeEntry(entry_type="历史案例", title="物流集团框架租赁关联方放行案例", category="主体与关联方", content="曾接受关联企业下单，但要求订单主体独立付款、母公司提供保证，并附关联方白名单。", source="历史合同脱敏案例", tags=["关联方", "历史放行"], risk_level="中"),
        KnowledgeEntry(entry_type="谈判策略", title="客户要求60天账期的替代方案", category="付款条件", content="可用分阶段付款、银行保函或信用保险作为交换，将无担保账期控制在45天内。", source="法务与财务复盘", tags=["付款", "账期", "谈判"], risk_level="中"),
        KnowledgeEntry(entry_type="模板", title="设备租赁补充协议模板", category="订改申请", content="用于变更租期、租金、设备数量、使用地点及维保范围，并明确与主合同的优先顺序。", source="合同模板库", tags=["补充协议", "租赁"], risk_level="提示"),
    ]
    db.add_all(entries)
    demo_contracts = [
        {
            "contract_no": "HT-2026-0128",
            "name": "华南数据中心叉车租赁合同",
            "customer": "A集团股份有限公司",
            "customer_group": "A集团",
            "contract_type": "租赁",
            "amount": 2680000,
            "project": "华南数据中心扩容项目",
            "status": "审核中",
            "website_terms_url": "https://example.com/legal/standard-terms",
            "text": """设备租赁合同\n甲方：A集团股份有限公司\n乙方：林德（中国）叉车有限公司\n合同总价：2,680,000元。验收合格并收到发票后60日内支付。租赁期36个月，租期届满后继续使用且出租方无异议的，视同自动续租。乙方迟延交付每日支付0.5%违约金，并赔偿甲方全部损失。甲方有权因经营需要单方解除合同，设备必须保留在甲方场地至替代供应商设备到位。技术协议及补充协议与正文不一致时，以对甲方最有利的解释为准。客户标准条款见 https://example.com/legal/standard-terms 。争议由甲方所在地法院管辖。""",
        },
        {
            "contract_no": "ZL-2026-0096",
            "name": "华东物流园叉车租赁框架合同",
            "customer": "某物流股份有限公司",
            "customer_group": "物流集团",
            "contract_type": "租赁",
            "amount": 1260000,
            "project": "华东快递转运场",
            "status": "待修改",
            "website_terms_url": "",
            "text": """叉车租赁框架合同\n甲方及甲方认为与甲方相关联的公司统称为甲方关联方，由内部各公司分别履行，互不承担连带责任。月租金按季度预付。承租方逾期支付租金超过30天，出租方有权暂停维修和保养。租赁期届满后承租方继续使用设备而出租方无异议的，视同自动续租。承租方逾期归还设备，应按租金标准130%支付占用费。补充协议与本合同冲突时以补充协议为准。""",
        },
        {
            "contract_no": "FW-2026-0042",
            "name": "新能源工厂设备维保服务合同",
            "customer": "某新能源科技有限公司",
            "customer_group": "新能源集团",
            "contract_type": "采购",
            "amount": 480000,
            "project": "年度维保服务",
            "status": "已完成",
            "website_terms_url": "",
            "text": """设备维保服务合同\n甲方：某新能源科技有限公司。年度服务费480000元，开票后30日支付。乙方提供季度保养及紧急维修，重大故障4小时响应。任何一方违约的累计责任不超过合同总额20%。争议由被告所在地法院管辖。""",
        },
    ]
    for index, payload in enumerate(demo_contracts, start=1):
        contract = Contract(
            **{key: value for key, value in payload.items() if key != "text"},
            template_type="待判断",
            created_by_id=by_role["合同管理员"].id,
            assigned_to_id=by_role["法务审核"].id,
            key_fields={},
            summary="由POC样例初始化的演示合同",
        )
        db.add(contract)
        db.flush()
        file_path = settings.upload_dir / f"seed-{index}.txt"
        file_path.write_text(payload["text"], encoding="utf-8")
        version = ContractVersion(
            contract_id=contract.id,
            version_no=1,
            review_round_no=1,
            label="客户初稿" if index < 3 else "已审核版本",
            file_name=f"{payload['contract_no']}.txt",
            file_path=str(file_path),
            mime_type="text/plain",
            file_size=file_path.stat().st_size,
            file_hash=f"seed-{index}",
            extracted_text=payload["text"],
            parse_status="已解析",
            document_source="客户",
            source_department="",
            comment_count=0,
            uploaded_by_id=by_role["合同管理员"].id,
        )
        db.add(version)
        db.flush()
        result = review_text(
            payload["text"],
            contract_type=contract.contract_type,
            standard_clauses=active_standard_clauses(db, contract.contract_type),
        )
        contract.template_type = result["template_type"]
        contract.risk_level = result["risk_level"]
        contract.current_round = 1
        run = ReviewRun(
            contract_id=contract.id,
            version_id=version.id,
            round_no=1,
            risk_score=result["risk_score"],
            summary=result["summary"],
            comparison_summary=result["comparison_summary"],
            stats=result["stats"],
            started_by_id=by_role["法务审核"].id,
        )
        db.add(run)
        db.flush()
        for suggestion in result["suggestions"]:
            db.add(ReviewSuggestion(review_run_id=run.id, **suggestion))
        if index == 1:
            db.add(ApprovalTask(contract_id=contract.id, level=1, department="法务部", approver_id=by_role["法务审核"].id, status="审核中"))
            db.add(ApprovalTask(contract_id=contract.id, level=1, department="财务部", approver_id=by_role["财务专家"].id, status="待复核"))
        if index == 2:
            db.add(NegotiationRecord(contract_id=contract.id, status="客户二次偏离", customer_feedback="客户坚持自动续租，但可接受提前60日通知退出。", internal_note="继续争取书面续租确认。", recorded_by_id=by_role["销售"].id))
    db.add(AuditLog(user_id=by_role["系统管理员"].id, actor_name="系统管理员", action="初始化POC数据", object_type="系统", detail={"source": "POC需求与脱敏合同样例"}, ip_address="127.0.0.1"))
    db.commit()
