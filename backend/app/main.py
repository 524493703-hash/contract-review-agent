from __future__ import annotations

import difflib
import json
import re
import shutil
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, inspect, literal, or_, select, text, union_all
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .database import Base, SessionLocal, engine, get_db, get_read_db, read_engine
from .models import (
    ApprovalTask,
    AuditLog,
    ChangeRequest,
    CheckResult,
    CheckBaselineMap,
    ClauseAtom,
    ClauseLink,
    ClauseNode,
    Consultation,
    Contract,
    ContractVersion,
    DocumentComment,
    EvidenceSpan,
    FocusedCheck,
    HumanConfirmation,
    KnowledgeDocument,
    KnowledgeEntry,
    LegalAuthority,
    LegalCitation,
    NegotiationRecord,
    NotificationOutbox,
    Playbook,
    RedlineProposal,
    RetrievalTrace,
    ReviewRun,
    ReviewSuggestion,
    ReviewerIdentity,
    StandardClause,
    User,
    WebsiteTermsSnapshot,
)
from .security import cache_authenticated_user, create_access_token, get_current_user, require_roles, verify_password
from .seed import seed_database
from .services.annotation_service import DetectedAnnotation, annotate_source_document, resolve_annotation_source
from .services.baseline_service import active_standard_clauses
from .services.contract_integrity import audit_contract_integrity
from .services.document_parser import parse_document, sha256_file
from .services.exporter import build_review_docx
from .services.focused_review import CHECK_SPECS, PLAYBOOK_VERSION, active_focused_checks, evaluate_focused_checks, playbook_coverage
from .services.llm_service import adjudicate_focused_checks, analyze_contract, redraft_replacement_clause
from .services.legal_rag import retrieve_legal_authorities
from .services.preview_service import AI_HIGHLIGHT_HEX, locate_pdf_risks, prepare_pdf_preview, render_docx_preview
from .services.redaction import redact_text
from .services.review_engine import apply_accepted_suggestions, bound_evidence_text, build_clause_context, compare_versions, default_replacement_clause, finalize_suggestion_metadata, is_direct_replacement_clause, legacy_rule_candidates, preserve_asymmetric_obligation_subject, preserve_clause_format, review_text, suggestion_risk_key, validate_replacement_clause
from .services.source_trace import clause_label_at, find_text_span, locate_source_span
from .services.website_terms import fetch_website_terms


settings = get_settings()


def ensure_runtime_schema() -> None:
    """Add POC columns to existing SQLite/MySQL databases without data loss."""
    inspector = inspect(engine)
    migrations = {
        "contract_versions": {
            "review_round_no": "INTEGER NULL",
            "document_source": "VARCHAR(40) NULL",
            "source_department": "VARCHAR(120) NULL",
            "comment_count": "INTEGER NULL",
            "source_map": "JSON NULL",
        },
        "contracts": {
            "our_role": "VARCHAR(40) NULL",
            "transaction_scenario": "VARCHAR(80) NULL",
            "document_complete": "BOOLEAN NULL",
            "legal_as_of_date": "DATE NULL",
        },
        "review_runs": {
            "annotated_file_path": "VARCHAR(500) NULL",
            "annotated_file_name": "VARCHAR(255) NULL",
            "annotation_status": "VARCHAR(255) NULL",
            "playbook_version": "VARCHAR(80) NULL",
            "coverage_status": "VARCHAR(40) NULL",
            "check_stats": "JSON NULL",
        },
        "review_suggestions": {
            "baseline_clause_id": "VARCHAR(64) NULL",
            "risk_key": "VARCHAR(160) NULL",
            "action_type": "VARCHAR(30) NULL",
            "occurrence_no": "INTEGER NULL",
            "occurrence_count": "INTEGER NULL",
            "page_no": "INTEGER NULL",
            "anchor_text": "TEXT NULL",
            "latest_instruction": "TEXT NULL",
            "revision_history": "JSON NULL",
            "check_status": "VARCHAR(30) NULL",
            "evidence_json": "JSON NULL",
            "risk_reason": "TEXT NULL",
            "deviation_type": "VARCHAR(40) NULL",
            "human_confirmation_required": "BOOLEAN NULL",
        },
        "evidence_spans": {
            "page_method": "VARCHAR(40) NULL",
        },
        "consultations": {
            "target_department": "VARCHAR(120) NULL",
            "review_decision": "VARCHAR(40) NULL",
        },
    }
    with engine.begin() as connection:
        for table_name, columns in migrations.items():
            existing = {item["name"] for item in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    quoted_table = f"`{table_name}`" if engine.dialect.name == "mysql" else f'"{table_name}"'
                    quoted_column = f"`{column_name}`" if engine.dialect.name == "mysql" else f'"{column_name}"'
                    connection.exec_driver_sql(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {definition}")
        connection.exec_driver_sql(
            "UPDATE contract_versions SET review_round_no = version_no "
            "WHERE review_round_no IS NULL AND version_no BETWEEN 1 AND 5"
        )
        connection.exec_driver_sql("UPDATE contracts SET our_role = CASE WHEN contract_type = '租赁' THEN '出租方' ELSE '采购方' END WHERE our_role IS NULL OR our_role = ''")
        connection.exec_driver_sql("UPDATE contracts SET transaction_scenario = '' WHERE transaction_scenario IS NULL")
        connection.exec_driver_sql("UPDATE contracts SET document_complete = 1 WHERE document_complete IS NULL")
        connection.exec_driver_sql(
            "UPDATE contract_versions SET document_source = '客户' "
            "WHERE document_source IS NULL OR document_source = ''"
        )
        connection.exec_driver_sql(
            "UPDATE contract_versions SET source_department = '' WHERE source_department IS NULL"
        )
        connection.exec_driver_sql(
            "UPDATE contract_versions SET comment_count = 0 WHERE comment_count IS NULL"
        )
        connection.execute(
            text(
                "UPDATE contracts SET contract_type = CASE "
                "WHEN contract_type LIKE :lease_pattern THEN :lease_type ELSE :procurement_type END "
                "WHERE contract_type NOT IN (:procurement_type, :lease_type)"
            ),
            {"lease_pattern": "%租赁%", "lease_type": "租赁", "procurement_type": "采购"},
        )
        connection.exec_driver_sql("UPDATE review_suggestions SET risk_key = '' WHERE risk_key IS NULL")
        connection.exec_driver_sql("UPDATE review_suggestions SET action_type = '替换条款' WHERE action_type IS NULL OR action_type = ''")
        connection.exec_driver_sql("UPDATE review_suggestions SET occurrence_no = 1 WHERE occurrence_no IS NULL")
        connection.exec_driver_sql("UPDATE review_suggestions SET occurrence_count = 1 WHERE occurrence_count IS NULL")
        connection.exec_driver_sql("UPDATE review_suggestions SET latest_instruction = '' WHERE latest_instruction IS NULL")
        connection.exec_driver_sql("UPDATE review_suggestions SET check_status = '' WHERE check_status IS NULL")
        connection.exec_driver_sql("UPDATE review_suggestions SET risk_reason = '' WHERE risk_reason IS NULL")
        connection.exec_driver_sql("UPDATE review_suggestions SET deviation_type = '' WHERE deviation_type IS NULL")
        connection.exec_driver_sql("UPDATE review_suggestions SET human_confirmation_required = 0 WHERE human_confirmation_required IS NULL")
        connection.exec_driver_sql("UPDATE review_runs SET playbook_version = '' WHERE playbook_version IS NULL")
        connection.exec_driver_sql("UPDATE review_runs SET coverage_status = '' WHERE coverage_status IS NULL")
        connection.exec_driver_sql("UPDATE consultations SET target_department = '' WHERE target_department IS NULL")
        connection.exec_driver_sql("UPDATE consultations SET review_decision = '' WHERE review_decision IS NULL")


def scalar(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def public_user(user: User) -> dict:
    return {"id": user.id, "username": user.username, "name": user.name, "email": user.email, "department": user.department, "role": user.role}


def audit(db: Session, request: Request, user: User | None, action: str, object_type: str = "", object_id: str = "", detail: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, actor_name=user.name if user else "系统", action=action, object_type=object_type, object_id=object_id, detail=detail or {}, ip_address=request.client.host if request.client else ""))


def contract_summary(contract: Contract, version_count: int = 0, suggestion_count: int = 0) -> dict:
    return {
        "id": contract.id,
        "contract_no": contract.contract_no,
        "name": contract.name,
        "customer": contract.customer,
        "customer_group": contract.customer_group,
        "contract_type": contract.contract_type,
        "our_role": contract.our_role or ("出租方" if contract.contract_type == "租赁" else "采购方"),
        "transaction_scenario": contract.transaction_scenario or "",
        "document_complete": bool(contract.document_complete),
        "legal_as_of_date": contract.legal_as_of_date.isoformat() if contract.legal_as_of_date else None,
        "template_type": contract.template_type,
        "amount": scalar(contract.amount),
        "currency": contract.currency,
        "project": contract.project,
        "status": contract.status,
        "risk_level": contract.risk_level,
        "current_round": contract.current_round,
        "website_terms_url": contract.website_terms_url,
        "key_fields": contract.key_fields or {},
        "summary": contract.summary,
        "assigned_to_id": contract.assigned_to_id,
        "version_count": version_count,
        "suggestion_count": suggestion_count,
        "created_at": scalar(contract.created_at),
        "updated_at": scalar(contract.updated_at),
    }


def contract_list_payload(
    db: Session,
    q: str = "",
    status_filter: str = "",
    risk: str = "",
    contract_type: str = "",
) -> list[dict]:
    version_counts = (
        select(ContractVersion.contract_id.label("contract_id"), func.count(ContractVersion.id).label("version_count"))
        .group_by(ContractVersion.contract_id)
        .subquery()
    )
    suggestion_counts = (
        select(ReviewRun.contract_id.label("contract_id"), func.count(ReviewSuggestion.id).label("suggestion_count"))
        .join(ReviewSuggestion, ReviewSuggestion.review_run_id == ReviewRun.id)
        .group_by(ReviewRun.contract_id)
        .subquery()
    )
    statement = (
        select(
            Contract,
            func.coalesce(version_counts.c.version_count, 0),
            func.coalesce(suggestion_counts.c.suggestion_count, 0),
        )
        .outerjoin(version_counts, version_counts.c.contract_id == Contract.id)
        .outerjoin(suggestion_counts, suggestion_counts.c.contract_id == Contract.id)
    )
    if q:
        like = f"%{q}%"
        text_contracts = select(ContractVersion.contract_id).where(ContractVersion.extracted_text.like(like))
        statement = statement.where(or_(Contract.contract_no.like(like), Contract.name.like(like), Contract.customer.like(like), Contract.project.like(like), Contract.id.in_(text_contracts)))
    if status_filter:
        statement = statement.where(Contract.status == status_filter)
    if risk:
        statement = statement.where(Contract.risk_level == risk)
    if contract_type:
        statement = statement.where(Contract.contract_type.like(f"%{contract_type}%"))
    rows = db.execute(statement.order_by(desc(Contract.updated_at))).all()
    return [contract_summary(contract, int(version_count), int(suggestion_count)) for contract, version_count, suggestion_count in rows]


def dashboard_payload(db: Session, user: User) -> dict:
    pending_consultations = select(func.count()).select_from(Consultation).where(
        Consultation.assignee_id == user.id,
        Consultation.status.in_(["待审核", "待答复"]),
    ).scalar_subquery()
    metric_rows = db.execute(
        union_all(
            select(literal("status"), Contract.status, func.count()).group_by(Contract.status),
            select(literal("risk"), Contract.risk_level, func.count()).group_by(Contract.risk_level),
            select(literal("pending"), literal(""), select(func.count()).select_from(ApprovalTask).where(ApprovalTask.status.in_(["待复核", "审核中"])).scalar_subquery()),
            select(literal("consultations"), literal(""), pending_consultations),
        )
    ).all()
    status_rows = [(label, count) for kind, label, count in metric_rows if kind == "status"]
    risk_rows = [(label, count) for kind, label, count in metric_rows if kind == "risk"]
    recent = db.scalars(select(Contract).order_by(desc(Contract.updated_at)).limit(6)).all()
    referral_rows = db.execute(
        select(
            Consultation.id,
            Consultation.contract_id,
            Consultation.suggestion_id,
            Consultation.target_department,
            Consultation.question,
            Consultation.due_at,
            Contract.contract_no,
            Contract.name,
            ReviewSuggestion.title,
            ReviewSuggestion.risk_level,
        )
        .join(Contract, Contract.id == Consultation.contract_id)
        .join(ReviewSuggestion, ReviewSuggestion.id == Consultation.suggestion_id)
        .where(Consultation.assignee_id == user.id, Consultation.status == "待审核")
        .order_by(Consultation.due_at, Consultation.created_at)
        .limit(6)
    ).all()
    pending_approvals = next((count for kind, _, count in metric_rows if kind == "pending"), 0) or 0
    consultations = next((count for kind, _, count in metric_rows if kind == "consultations"), 0) or 0
    return {
        "greeting": f"{user.name}，今天有 {pending_approvals + consultations} 项协同事项待处理",
        "totals": {"contracts": sum(count for _, count in status_rows), "pending": pending_approvals, "consultations": consultations, "high_risk": next((count for level, count in risk_rows if level == "高"), 0)},
        "by_status": [{"label": label, "value": count} for label, count in status_rows],
        "by_risk": [{"label": label, "value": count} for label, count in risk_rows],
        "recent_contracts": [contract_summary(contract) for contract in recent],
        "referral_tasks": [{"id": item_id, "contract_id": contract_id, "suggestion_id": suggestion_id, "target_department": department, "question": question, "due_at": scalar(due_at), "contract_no": contract_no, "contract_name": contract_name, "suggestion_title": suggestion_title, "risk_level": risk_level} for item_id, contract_id, suggestion_id, department, question, due_at, contract_no, contract_name, suggestion_title, risk_level in referral_rows],
    }


def active_users_payload(db: Session) -> list[dict]:
    return [public_user(user) for user in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.department, User.name)).all()]


def approval_detail(item: ApprovalTask) -> dict:
    return {"id": item.id, "level": item.level, "department": item.department, "approver_id": item.approver_id, "status": item.status, "decision": item.decision, "comment": item.comment, "external_flow_id": item.external_flow_id}


def contract_activity_payload(db: Session, contract_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    empty = literal(None)
    rows = db.execute(
        union_all(
            select(
                literal("negotiation"), NegotiationRecord.id, NegotiationRecord.suggestion_id,
                empty, empty, empty, empty,
                NegotiationRecord.status, NegotiationRecord.customer_feedback, NegotiationRecord.internal_note,
                empty, empty, empty, empty, empty, empty, empty, NegotiationRecord.created_at,
            ).where(NegotiationRecord.contract_id == contract_id),
            select(
                literal("consultation"), Consultation.id, Consultation.suggestion_id, Consultation.assignee_id,
                Consultation.requester_id, Consultation.target_department, Consultation.review_decision,
                Consultation.status, Consultation.question, Consultation.answer, Consultation.due_at,
                empty, empty, empty, empty, empty, empty, Consultation.created_at,
            ).where(Consultation.contract_id == contract_id),
            select(
                literal("approval"), ApprovalTask.id, empty, empty, empty, empty, empty,
                ApprovalTask.status, empty, empty, empty,
                ApprovalTask.level, ApprovalTask.department, ApprovalTask.approver_id, ApprovalTask.decision,
                ApprovalTask.comment, ApprovalTask.external_flow_id, ApprovalTask.created_at,
            ).where(ApprovalTask.contract_id == contract_id),
        )
    ).all()
    negotiations: list[dict] = []
    consultations: list[dict] = []
    approvals: list[dict] = []
    for kind, item_id, suggestion_id, assignee_id, requester_id, target_department, review_decision, status_value, text_one, text_two, due_at, level, department, approver_id, decision, comment, external_flow_id, created_at in rows:
        if kind == "negotiation":
            negotiations.append({"id": item_id, "suggestion_id": suggestion_id, "status": status_value, "customer_feedback": text_one, "internal_note": text_two, "created_at": scalar(created_at)})
        elif kind == "consultation":
            consultations.append({"id": item_id, "suggestion_id": suggestion_id, "requester_id": requester_id, "assignee_id": assignee_id, "target_department": target_department or "", "question": text_one, "answer": text_two, "review_decision": review_decision or "", "status": status_value, "due_at": scalar(due_at), "created_at": scalar(created_at)})
        else:
            approvals.append({"id": item_id, "level": level, "department": department, "approver_id": approver_id, "status": status_value, "decision": decision, "comment": comment, "external_flow_id": external_flow_id, "created_at": scalar(created_at)})
    negotiations.sort(key=lambda item: item["created_at"] or "", reverse=True)
    consultations.sort(key=lambda item: item["created_at"] or "", reverse=True)
    approvals.sort(key=lambda item: (item["level"] or 0, item["created_at"] or ""))
    for item in approvals:
        item.pop("created_at", None)
    return negotiations, consultations, approvals


def recalculate_review_result(result: dict, suffixes: list[str] | None = None) -> None:
    weights = {"高": 18, "中": 10, "低": 4}
    suggestions = []
    for item in result["suggestions"]:
        action_type = str(item.get("action_type") or "替换条款")
        if action_type == "新增条款":
            if not is_direct_replacement_clause(item.get("suggested_text", "")):
                continue
            item["original_text"] = ""
            item["anchor_text"] = bound_evidence_text(item.get("anchor_text", ""))
        else:
            evidence = bound_evidence_text(item.get("original_text", ""))
            if not evidence:
                continue
            item["original_text"] = evidence
        suggestions.append(item)
    result["suggestions"] = suggestions
    result["stats"] = {
        "high": sum(item["risk_level"] == "高" for item in suggestions),
        "medium": sum(item["risk_level"] == "中" for item in suggestions),
        "low": sum(item["risk_level"] == "低" for item in suggestions),
        "total": len(suggestions),
    }
    result["risk_score"] = min(100, sum(weights.get(item["risk_level"], 2) for item in suggestions))
    result["risk_level"] = "高" if result["risk_score"] >= 55 or result["stats"]["high"] >= 3 else "中" if result["risk_score"] >= 20 else "低"
    result["summary"] = f"识别为{result['template_type']}，发现 {result['stats']['total']} 项建议，其中高风险 {result['stats']['high']} 项、中风险 {result['stats']['medium']} 项。"
    if suffixes:
        result["summary"] += " " + " ".join(suffixes)


def migrate_legacy_suggestion_drafts(db: Session) -> None:
    """Bring existing POC findings into the per-clause drafting workflow."""
    grouped_pattern = re.compile(r"【命中\d+】(.*?)(?=\n【命中\d+】|\n【另有\d+处同类命中】|$)", re.DOTALL)
    rows = db.scalars(select(ReviewSuggestion).order_by(ReviewSuggestion.created_at)).all()
    now = datetime.now().isoformat(timespec="seconds")
    for item in rows:
        if not item.action_type:
            item.action_type = "新增条款" if "TOPIC_MISSING" in item.rule_code else "替换条款"
        if item.action_type == "新增条款" and item.original_text:
            # Legacy rows used the first 160 characters as faux evidence for
            # missing-section findings. Preserve it only as an insertion
            # anchor; a new clause has no risk original to replace.
            item.anchor_text = item.anchor_text or item.original_text
            item.original_text = ""
        replacement = item.suggested_text
        if item.decision == "待处理" and not is_direct_replacement_clause(replacement):
            replacement = default_replacement_clause(item.rule_code)
            if not replacement and item.baseline_clause_id:
                baseline = db.get(StandardClause, item.baseline_clause_id)
                replacement = baseline.content if baseline else ""
            if item.action_type != "新增条款":
                replacement = preserve_clause_format(item.original_text, replacement)
            quality = validate_replacement_clause(item.original_text, replacement, item.action_type)
            if quality["eligible"]:
                item.suggested_text = replacement
            else:
                # Never backfill an unrelated generic paragraph into a live
                # finding. Keep the risk visible, but require a human drafter.
                item.action_type = "人工起草"
                item.suggested_text = ""
        fragments = [re.sub(r"\s+", " ", value).strip("… ") for value in grouped_pattern.findall(item.original_text or "")]
        fragments = [value for value in fragments if value]
        if item.decision == "待处理" and len(fragments) > 1:
            original_values = fragments
            item.original_text = original_values[0]
            item.anchor_text = original_values[0]
            item.occurrence_no = 1
            item.occurrence_count = len(original_values)
            item.risk_key = suggestion_risk_key(item.rule_code, original_values[0], 1)
            for occurrence_no, original in enumerate(original_values[1:], start=2):
                db.add(ReviewSuggestion(
                    review_run_id=item.review_run_id,
                    rule_code=item.rule_code,
                    risk_key=suggestion_risk_key(item.rule_code, original, occurrence_no),
                    action_type=item.action_type,
                    occurrence_no=occurrence_no,
                    occurrence_count=len(original_values),
                    category=item.category,
                    title=item.title,
                    risk_level=item.risk_level,
                    original_text=original,
                    suggested_text=item.suggested_text,
                    basis=item.basis,
                    negotiation_focus=item.negotiation_focus,
                    source=item.source,
                    confidence=item.confidence,
                    historical_release=item.historical_release,
                    baseline_clause_id=item.baseline_clause_id,
                    page_no=item.page_no,
                    anchor_text=original,
                    revision_history=[{"version": 1, "instruction": "系统首次生成", "suggested_text": item.suggested_text, "generator": item.source, "created_at": now, "created_by": "系统"}],
                ))
        else:
            item.occurrence_no = item.occurrence_no or 1
            item.occurrence_count = item.occurrence_count or 1
            item.risk_key = item.risk_key or suggestion_risk_key(item.rule_code, item.original_text, item.occurrence_no)
        if not item.revision_history:
            item.revision_history = [{"version": 1, "instruction": "系统首次生成", "suggested_text": item.suggested_text, "generator": item.source, "created_at": scalar(item.created_at) or now, "created_by": "系统"}]
    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    if engine.dialect.name == "mysql":
        inspector = inspect(engine)
        longtext_targets = (
            ("contract_versions", "extracted_text"),
            ("website_terms_snapshots", "extracted_text"),
            ("review_runs", "engine"),
        )
        with engine.begin() as connection:
            for table_name, column_name in longtext_targets:
                column = next(
                    item for item in inspector.get_columns(table_name) if item["name"] == column_name
                )
                if column["type"].__class__.__name__.upper() != "LONGTEXT":
                    connection.exec_driver_sql(
                        f"ALTER TABLE `{table_name}` MODIFY COLUMN `{column_name}` LONGTEXT NOT NULL"
                    )
            performance_indexes = {
                "contracts": ("ix_contracts_updated_at", "`updated_at`"),
                "users": ("ix_users_department_created", "`department`, `created_at`"),
                "approval_tasks": ("ix_approval_contract_department", "`contract_id`, `department`"),
            }
            for table_name, (index_name, columns) in performance_indexes.items():
                existing_indexes = {item["name"] for item in inspector.get_indexes(table_name)}
                if index_name not in existing_indexes:
                    connection.exec_driver_sql(f"CREATE INDEX `{index_name}` ON `{table_name}` ({columns})")
    with SessionLocal() as db:
        seed_database(db)
        migrate_legacy_suggestion_drafts(db)
    if read_engine is not engine:
        with read_engine.connect() as connection:
            connection.execute(select(1))
    yield


app = FastAPI(title=settings.app_name, version="1.0.0-poc", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/guide", include_in_schema=False)
def contract_review_guide():
    guide = settings.export_dir.parent.parent / "public" / "contract-review-guide.html"
    if not guide.exists():
        raise HTTPException(status_code=404, detail="说明页面不存在")
    return FileResponse(guide, media_type="text/html; charset=utf-8")


class LoginInput(BaseModel):
    username: str
    password: str


class SuggestionDecisionInput(BaseModel):
    decision: str = Field(pattern="^(接纳|修改后接纳|拒绝|待处理)$")
    suggested_text: str | None = None
    note: str = ""


class SuggestionRedraftInput(BaseModel):
    instruction: str = Field(min_length=2, max_length=2000)


class ConsultationInput(BaseModel):
    suggestion_id: str | None = None
    assignee_id: str
    question: str = Field(min_length=2, max_length=2000)
    due_hours: int = Field(default=24, ge=1, le=168)


class ConsultationAnswerInput(BaseModel):
    answer: str = Field(min_length=2, max_length=4000)
    review_decision: str = Field(default="", pattern="^(|同意系统建议|建议修改|不建议采纳)$")


class NegotiationInput(BaseModel):
    suggestion_id: str | None = None
    status: str
    customer_feedback: str
    internal_note: str = ""


class ApprovalInput(BaseModel):
    decision: str
    comment: str = ""


class ChangeRequestInput(BaseModel):
    contract_id: str
    request_text: str


class AssignmentInput(BaseModel):
    assignee_id: str


class NotificationInput(BaseModel):
    recipient: str
    subject: str = "合同审核结果通知"
    body: str = ""


class CommentSourceInput(BaseModel):
    source_kind: str = Field(pattern="^(客户|同事|部门|未识别)$")
    source_department: str = ""
    author_name: str | None = None


class FocusedCheckConfirmationInput(BaseModel):
    decision: str = Field(pattern="^(确认风险|接受偏离|退回修改)$")
    comment: str = Field(min_length=2, max_length=4000)


@app.get("/api/health")
def health():
    """Cheap liveness probe; database readiness is exposed separately."""
    return {"status": "ok", "service": settings.app_name, "database": "mysql" if settings.database_url.startswith("mysql") else "sqlite", "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/ready")
def ready(db: Session = Depends(get_read_db)):
    db.execute(select(1))
    return {"status": "ok", "service": settings.app_name, "database": "mysql" if settings.database_url.startswith("mysql") else "sqlite", "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/auth/demo-users")
def demo_users(db: Session = Depends(get_read_db)):
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.role)).all()
    payload = {"users": [public_user(user) for user in users]}
    if settings.demo_mode:
        payload["password"] = settings.initial_password
    return payload


@app.post("/api/auth/login")
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    audit(db, request, user, "登录系统", "用户", user.id)
    db.commit()
    cache_authenticated_user(user)
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": public_user(user),
        "bootstrap": {
            "profile": public_user(user),
            "dashboard": dashboard_payload(db, user),
            "contracts": contract_list_payload(db),
            "users": active_users_payload(db),
        },
    }


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return public_user(user)


@app.get("/api/users")
def users(_: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    return active_users_payload(db)


@app.get("/api/bootstrap")
def bootstrap(user: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    return {
        "profile": public_user(user),
        "dashboard": dashboard_payload(db, user),
        "contracts": contract_list_payload(db),
        "users": active_users_payload(db),
    }


@app.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    return dashboard_payload(db, user)


@app.get("/api/contracts")
def list_contracts(
    q: str = "",
    status_filter: str = Query("", alias="status"),
    risk: str = "",
    contract_type: str = Query("", alias="type"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_read_db),
):
    return contract_list_payload(db, q, status_filter, risk, contract_type)


@app.post("/api/contracts/upload")
def upload_contracts(
    request: Request,
    files: list[UploadFile] = File(...),
    customer: str = Form(""),
    project: str = Form(""),
    contract_id: str = Form(""),
    contract_type: str = Form(""),
    our_role: str = Form(""),
    transaction_scenario: str = Form(""),
    document_complete: bool = Form(True),
    legal_as_of_date: str = Form(""),
    review_round: int = Form(0),
    document_source: str = Form("客户"),
    source_department: str = Form(""),
    note: str = Form(""),
    user: User = Depends(require_roles("合同管理员", "法务审核", "销售")),
    db: Session = Depends(get_db),
):
    if len(files) > 30:
        raise HTTPException(status_code=400, detail="单批最多上传30个文件")
    if contract_id and len(files) != 1:
        raise HTTPException(status_code=400, detail="同一合同的每一审核轮次只能上传一份主合同文件")
    if contract_type and contract_type not in {"采购", "租赁"}:
        raise HTTPException(status_code=400, detail="合同类型只能选择采购合同或租赁合同")
    if our_role and our_role not in {"出租方", "承租方", "采购方", "供应方"}:
        raise HTTPException(status_code=400, detail="我方角色不在允许范围内")
    try:
        selected_legal_date = date.fromisoformat(legal_as_of_date) if legal_as_of_date else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="法律适用日期必须为 YYYY-MM-DD") from exc
    allowed_sources = {"客户", "法务部", "财务部", "销售部", "合同管理部", "ABU", "服务部", "其他内部", "未知"}
    if document_source not in allowed_sources:
        raise HTTPException(status_code=400, detail="文件来源不在允许范围内")
    # Authentication has already queried MySQL through this request-scoped
    # session. Release that connection before CPU-heavy OCR so a long scanned
    # document cannot outlive the server's idle-connection timeout.
    db.close()
    results = []
    for upload in files:
        suffix = Path(upload.filename or "contract.bin").suffix.lower()
        storage_name = f"{uuid4().hex}{suffix}"
        destination = settings.upload_dir / storage_name
        size = 0
        with destination.open("wb") as handle:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > 80 * 1024 * 1024:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"{upload.filename} 超过80MB限制")
                handle.write(chunk)
        parsed = parse_document(destination, upload.filename or storage_name)
        fields = parsed.fields
        contract = db.get(Contract, contract_id) if contract_id else None
        if contract_id and not contract:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail="要追加轮次的合同不存在")
        target_round = review_round
        if contract:
            if our_role:
                allowed_roles = {"租赁": {"出租方", "承租方"}, "采购": {"采购方", "供应方"}}
                if our_role not in allowed_roles[contract.contract_type]:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail=f"{contract.contract_type}合同不能使用我方角色“{our_role}”")
                contract.our_role = our_role
            if transaction_scenario:
                contract.transaction_scenario = transaction_scenario
            contract.document_complete = document_complete
            if selected_legal_date:
                contract.legal_as_of_date = selected_legal_date
            expected_round = contract.current_round + 1
            target_round = target_round or expected_round
            if target_round != expected_round:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=409, detail=f"当前应上传第 {expected_round} 轮合同，不能跳轮或覆盖已审核轮次")
            if target_round > 5:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="合同审核最多五轮")
            if db.scalar(select(ContractVersion.id).where(ContractVersion.contract_id == contract.id, ContractVersion.review_round_no == target_round)):
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=409, detail=f"第 {target_round} 轮合同已上传，请直接启动审核")
        if not contract:
            base_no = fields.get("contract_no") or f"POC-{datetime.now():%Y%m%d}-{uuid4().hex[:6].upper()}"
            existing = db.scalar(select(Contract).where(Contract.contract_no == base_no))
            contract_no = f"{base_no}-{uuid4().hex[:4].upper()}" if existing else str(base_no)
            selected_type = contract_type or str(fields.get("contract_type") or "采购")
            selected_type = selected_type if selected_type in {"采购", "租赁"} else "采购"
            selected_role = our_role or ("出租方" if selected_type == "租赁" else "采购方")
            allowed_roles = {"租赁": {"出租方", "承租方"}, "采购": {"采购方", "供应方"}}
            if selected_role not in allowed_roles[selected_type]:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail=f"{selected_type}合同不能使用我方角色“{selected_role}”")
            target_round = target_round or 1
            if target_round != 1:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="新合同必须从第 1 轮开始")
            contract = Contract(
                contract_no=contract_no,
                name=str(fields.get("name") or Path(upload.filename or storage_name).stem),
                customer=customer or str(fields.get("customer") or "待补充客户"),
                customer_group=customer or str(fields.get("customer") or ""),
                contract_type=selected_type,
                our_role=selected_role,
                transaction_scenario=transaction_scenario,
                document_complete=document_complete,
                legal_as_of_date=selected_legal_date or date.today(),
                amount=float(fields.get("amount") or 0),
                project=project,
                status="已提交",
                risk_level="待评估",
                website_terms_url=str(fields.get("website_terms_url") or ""),
                key_fields=fields,
                summary=note or "待启动AI审核",
                created_by_id=user.id,
            )
            db.add(contract)
            db.flush()
        version_no = (db.scalar(select(func.max(ContractVersion.version_no)).where(ContractVersion.contract_id == contract.id)) or 0) + 1
        version = ContractVersion(
            contract_id=contract.id,
            version_no=version_no,
            review_round_no=target_round,
            label=f"第{target_round}轮 · {document_source}版本",
            file_name=upload.filename or storage_name,
            file_path=str(destination),
            mime_type=upload.content_type or "application/octet-stream",
            file_size=size,
            file_hash=sha256_file(destination),
            extracted_text=parsed.text,
            source_map=parsed.source_map,
            parse_status=parsed.status,
            parse_message=parsed.message,
            document_source=document_source,
            source_department=("客户" if document_source == "客户" else source_department or (document_source if document_source.endswith("部") or document_source in {"ABU", "服务部"} else "")),
            comment_count=len(parsed.annotations),
            uploaded_by_id=user.id,
        )
        db.add(version)
        db.flush()
        active_users = db.scalars(select(User).where(User.is_active.is_(True))).all()
        identities = db.scalars(select(ReviewerIdentity).where(ReviewerIdentity.is_active.is_(True))).all()
        for annotation_payload in parsed.annotations:
            annotation = DetectedAnnotation(**annotation_payload)
            resolved = resolve_annotation_source(annotation, document_source, version.source_department, active_users, identities)
            db.add(DocumentComment(
                version_id=version.id,
                external_id=annotation.external_id,
                annotation_type=annotation.annotation_type,
                author_name=resolved["author_name"],
                source_kind=resolved["source_kind"],
                source_department=resolved["source_department"],
                source_confidence=resolved["source_confidence"],
                source_basis=resolved["source_basis"],
                page_no=annotation.page_no,
                anchor_text=annotation.anchor_text,
                comment_text=annotation.comment_text,
                comment_date=annotation.comment_date,
                location=annotation.location,
            ))
        contract.status = "待审核" if parsed.text else "已提交"
        contract.key_fields = {**(contract.key_fields or {}), **fields}
        audit(db, request, user, "上传合同轮次版本", "合同", contract.id, {"file": upload.filename, "version": version_no, "round": target_round, "document_source": document_source, "comment_count": len(parsed.annotations), "parse_status": parsed.status})
        db.commit()
        results.append({"contract": contract_summary(contract, version_no), "version_id": version.id, "review_round_no": target_round, "comment_count": len(parsed.annotations), "parse_status": parsed.status, "parse_message": parsed.message})
    return results


@app.get("/api/contracts/{contract_id}")
def contract_detail(contract_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    contract = db.scalars(select(Contract).options(joinedload(Contract.versions)).where(Contract.id == contract_id)).unique().first()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    versions = sorted(contract.versions, key=lambda item: item.version_no)
    runs = db.scalars(select(ReviewRun).options(joinedload(ReviewRun.suggestions)).where(ReviewRun.contract_id == contract_id).order_by(desc(ReviewRun.round_no))).unique().all()
    version_ids = [item.id for item in versions]
    comments = db.scalars(
        select(DocumentComment)
        .where(DocumentComment.version_id.in_(version_ids))
        .order_by(DocumentComment.version_id, DocumentComment.created_at)
    ).all() if version_ids else []
    negotiations, consultations, approvals = contract_activity_payload(db, contract_id)
    all_suggestions = [item for run in runs for item in run.suggestions]
    baseline_ids = [item.baseline_clause_id for item in all_suggestions if item.baseline_clause_id]
    baseline_clause_rows = db.scalars(select(StandardClause).where(StandardClause.id.in_(baseline_ids))).all() if baseline_ids else []
    baseline_citation_by_id = {
        item.id: {
            "document_title": item.baseline_name,
            "document_version": item.baseline_version,
            "source_file": item.source_file,
            "source_hash": item.source_hash,
            "clause_no": item.clause_no,
            "heading": item.heading,
            "page_no": 1,
            "clause_text": item.content,
        }
        for item in baseline_clause_rows
    }
    def suggestion_dict(item: ReviewSuggestion):
        payload = {key: scalar(getattr(item, key)) for key in ("id", "rule_code", "risk_key", "action_type", "occurrence_no", "occurrence_count", "category", "title", "risk_level", "original_text", "suggested_text", "basis", "negotiation_focus", "source", "confidence", "historical_release", "baseline_clause_id", "page_no", "anchor_text", "latest_instruction", "revision_history", "check_status", "evidence_json", "risk_reason", "deviation_type", "human_confirmation_required", "decision", "decision_note", "updated_at")}
        payload["revision_history"] = payload["revision_history"] or []
        payload["baseline_citation"] = baseline_citation_by_id.get(item.baseline_clause_id)
        payload["replacement_check"] = validate_replacement_clause(item.original_text, item.suggested_text, item.action_type or "替换条款")
        return payload
    return {
        "contract": contract_summary(contract, len(versions)),
        "versions": [{"id": item.id, "version_no": item.version_no, "review_round_no": item.review_round_no, "label": item.label, "file_name": item.file_name, "file_size": item.file_size, "parse_status": item.parse_status, "parse_message": item.parse_message, "document_source": item.document_source or "客户", "source_department": item.source_department or "", "comment_count": item.comment_count or 0, "created_at": scalar(item.created_at)} for item in versions],
        "review_runs": [{"id": run.id, "version_id": run.version_id, "round_no": run.round_no, "engine": run.engine, "status": run.status, "risk_score": run.risk_score, "summary": run.summary, "comparison_summary": run.comparison_summary, "stats": run.stats, "playbook_version": run.playbook_version or "", "coverage_status": run.coverage_status or "", "check_stats": run.check_stats or {}, "focused_checks_available": bool(run.playbook_version), "annotated_file_name": run.annotated_file_name or "", "annotation_status": run.annotation_status or "", "annotated_available": bool(run.annotated_file_path and Path(run.annotated_file_path).exists()), "created_at": scalar(run.created_at), "suggestions": [suggestion_dict(item) for item in run.suggestions]} for run in runs],
        "document_comments": [{"id": item.id, "version_id": item.version_id, "external_id": item.external_id, "annotation_type": item.annotation_type, "author_name": item.author_name, "source_kind": item.source_kind, "source_department": item.source_department, "source_confidence": item.source_confidence, "source_basis": item.source_basis, "page_no": item.page_no, "anchor_text": item.anchor_text, "comment_text": item.comment_text, "comment_date": item.comment_date, "created_at": scalar(item.created_at)} for item in comments],
        "cumulative_review": {
            "rounds_completed": len(runs),
            "total_opinions": len(all_suggestions),
            "pending": sum(item.decision == "待处理" for item in all_suggestions),
            "accepted": sum(item.decision in {"接纳", "修改后接纳"} for item in all_suggestions),
            "released": sum(item.decision == "拒绝" for item in all_suggestions),
        },
        "negotiations": negotiations,
        "consultations": consultations,
        "approvals": approvals,
        "focused_review": focused_review_payload(db, runs[0].id) if runs and runs[0].playbook_version else None,
    }


@app.post("/api/contracts/{contract_id}/review")
def run_review(contract_id: str, request: Request, version_id: str = "", user: User = Depends(require_roles("法务审核", "合同管理员")), db: Session = Depends(get_db)):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    next_round = contract.current_round + 1
    if next_round > 5:
        raise HTTPException(status_code=400, detail="POC最多支持五轮审核，请归档当前合同")
    version = db.get(ContractVersion, version_id) if version_id else db.scalar(
        select(ContractVersion)
        .where(ContractVersion.contract_id == contract_id, ContractVersion.review_round_no == next_round)
        .order_by(desc(ContractVersion.version_no))
    )
    if not version:
        raise HTTPException(status_code=409, detail=f"请先上传第 {next_round} 轮合同文件，再启动本轮审核")
    if version.contract_id != contract_id or version.review_round_no != next_round:
        raise HTTPException(status_code=409, detail=f"所选文件不属于当前待审核的第 {next_round} 轮")
    if not version or not version.extracted_text:
        raise HTTPException(status_code=400, detail="当前版本尚未解析出可审核文本")
    if db.scalar(select(ReviewRun.id).where(ReviewRun.contract_id == contract_id, ReviewRun.round_no == next_round)):
        raise HTTPException(status_code=409, detail=f"第 {next_round} 轮已经完成审核")

    prior_suggestions = db.scalars(
        select(ReviewSuggestion)
        .join(ReviewRun)
        .where(
            ReviewRun.contract_id == contract_id,
            ReviewRun.round_no < next_round,
        )
        .order_by(ReviewRun.round_no, ReviewSuggestion.created_at)
    ).all()
    accepted = [item for item in prior_suggestions if item.decision in {"接纳", "修改后接纳"}]
    rejected = [item for item in prior_suggestions if item.decision == "拒绝"]
    rejected_keys = {
        item.risk_key or suggestion_risk_key(item.rule_code, item.original_text, item.occurrence_no or 1)
        for item in rejected
    }
    previous = db.scalar(
        select(ContractVersion)
        .where(ContractVersion.contract_id == contract_id, ContractVersion.review_round_no < next_round)
        .order_by(desc(ContractVersion.review_round_no), desc(ContractVersion.version_no))
    )
    historical_contract = db.scalar(
        select(Contract)
        .where(
            Contract.customer_group == contract.customer_group,
            Contract.contract_type == contract.contract_type,
            Contract.id != contract.id,
        )
        .order_by(desc(Contract.updated_at))
    )
    historical_version = db.scalar(select(ContractVersion).where(ContractVersion.contract_id == historical_contract.id).order_by(desc(ContractVersion.version_no))) if historical_contract else None
    contract_website_url = contract.website_terms_url
    source_version_id = version.id
    current_text = version.extracted_text
    previous_text = previous.extracted_text if previous else ""
    historical_text = historical_version.extracted_text if historical_version else ""
    legacy_rule_mode = str(settings.legacy_rule_mode or "shadow").strip().lower()
    if legacy_rule_mode not in {"active", "shadow", "disabled"}:
        legacy_rule_mode = "shadow"
    legacy_shadow_candidates = (
        legacy_rule_candidates(current_text, historical_text)
        if legacy_rule_mode == "shadow"
        else []
    )
    result = review_text(
        current_text,
        previous_text,
        historical_text,
        contract_type=contract.contract_type,
        standard_clauses=active_standard_clauses(db, contract.contract_type),
        has_annotations=bool(version.comment_count),
        include_legacy_rules=legacy_rule_mode == "active",
    )
    integrity_findings = audit_contract_integrity(
        current_text,
        source_map=version.source_map or [],
        source_file=version.file_name,
        as_of_date=contract.legal_as_of_date or date.today(),
    )
    if integrity_findings:
        result["suggestions"].extend(integrity_findings)
    focused_review = evaluate_focused_checks(
        current_text,
        contract_type=contract.contract_type,
        our_role=contract.our_role or ("出租方" if contract.contract_type == "租赁" else "采购方"),
        parse_status=version.parse_status,
        document_complete=bool(contract.document_complete),
        source_map=version.source_map or [],
        source_file=version.file_name,
    )
    enhancement_messages: list[str] = []
    if integrity_findings:
        enhancement_messages.append(f"合同完整性检查识别 {len(integrity_findings)} 项金额、期限、参数或跨条款异常。")
    if focused_review["check_results"]:
        enhancement_messages.append(
            f"角色化 Playbook 已执行 {focused_review['stats']['TOTAL']} 项 Focused Checks，覆盖状态 {focused_review['coverage_status']}。"
        )
    if legacy_rule_mode == "shadow":
        enhancement_messages.append(
            f"旧正则已作为影子召回执行，提供 {len(legacy_shadow_candidates)} 条候选线索，不再独立生成审核结论。"
        )
    elif legacy_rule_mode == "disabled":
        enhancement_messages.append("旧正则风险规则已禁用，审核结论仅来自知识库、Playbook、确定性检查和大模型。")
    if legacy_rule_mode == "active" and contract.contract_type == "租赁" and (contract.our_role or "出租方") == "出租方":
        # These legacy rules were authored from a lessee/customer perspective
        # and directly conflict with the approved lessor baseline. The role-aware
        # Playbook now owns these topics.
        incompatible_legacy_codes = {"LEASE_AUTO_RENEW", "ACCEPTANCE_SILENCE", "MAINTENANCE_SUSPEND", "RENT_RETURN_130"}
        before_role_filter = len(result["suggestions"])
        result["suggestions"] = [item for item in result["suggestions"] if item["rule_code"] not in incompatible_legacy_codes]
        removed_for_role = before_role_filter - len(result["suggestions"])
        if removed_for_role:
            enhancement_messages.append(f"已按我方出租方角色移除 {removed_for_role} 项方向冲突的旧规则结果。")
    accepted_keys = {
        item.risk_key or suggestion_risk_key(item.rule_code, item.original_text, item.occurrence_no or 1)
        for item in accepted
    }
    inherited_open = 0
    for item in result["suggestions"]:
        if item.get("risk_key") in accepted_keys:
            item["negotiation_focus"] += " 上一轮已接纳该修改，但本轮上传文本仍命中，请核对是否落实或被客户再次偏离。"
            item["source"] += " + 前轮人工审核"
            inherited_open += 1
    if accepted:
        enhancement_messages.append(f"已叠加前 {next_round - 1} 轮 {len(accepted)} 项人工接纳意见；其中 {inherited_open} 项在本轮仍需核对。")
    if historical_version:
        enhancement_messages.append("已综合比照同客户组历史合同。")
    website_url = contract_website_url
    if not website_url:
        match = re.search(r"https?://[^\s<>\"'，。；）)]+", current_text)
        website_url = match.group(0) if match else ""
    previous_snapshot_hash = ""
    if website_url:
        previous_snapshot = db.scalar(select(WebsiteTermsSnapshot).where(WebsiteTermsSnapshot.contract_id == contract.id, WebsiteTermsSnapshot.url == website_url, WebsiteTermsSnapshot.fetch_status == "已抓取").order_by(desc(WebsiteTermsSnapshot.created_at)))
        previous_snapshot_hash = previous_snapshot.content_hash if previous_snapshot else ""

    # Website capture and the model gateway can each take tens of seconds.
    # Keep only plain values, then release MySQL until the external work is done.
    db.close()
    website_capture = None
    if website_url:
        capture = fetch_website_terms(website_url)
        website_capture = capture
        if capture.status == "已抓取":
            website_review = review_text(
                capture.text,
                contract_type=contract.contract_type,
                include_legacy_rules=legacy_rule_mode == "active",
                add_general_fallback=False,
            )
            existing_codes = {item["rule_code"] for item in result["suggestions"]}
            appended = 0
            if previous_snapshot_hash and previous_snapshot_hash != capture.content_hash:
                result["suggestions"].append({"rule_code": "WEBSITE_TERMS_CHANGED", "category": "外部条款", "title": "客户官网条款自上次审核后发生变化", "risk_level": "高", "original_text": website_url, "suggested_text": "双方确认，仅以本合同签署时抓取并作为附件固定的网页条款版本为准，该附件应载明网址、抓取日期及文件哈希；任何后续网页更新未经双方书面确认均不生效。", "basis": f"上次哈希 {previous_snapshot_hash[:12]}，本次哈希 {capture.content_hash[:12]}。", "negotiation_focus": "确认适用网页版本、抓取日期和文件优先级。", "source": "官网条款版本监测", "confidence": 98, "historical_release": False})
                appended += 1
            for item in website_review["suggestions"]:
                if item["rule_code"] in existing_codes or appended >= 5:
                    continue
                website_item = {**item, "rule_code": f"WEB_{item['rule_code']}", "source": f"客户官网条款固化：{capture.final_url}"}
                result["suggestions"].append(website_item)
                existing_codes.add(item["rule_code"])
                appended += 1
            enhancement_messages.append(f"官网条款已固化并补充 {appended} 项风险。")
        else:
            result["suggestions"].append({"rule_code": "WEBSITE_TERMS_FETCH_FAILED", "category": "外部条款", "title": "客户官网条款未能固化", "risk_level": "中", "original_text": website_url, "suggested_text": "本合同不直接适用任何可动态更新的网页条款；相关网页条款仅在双方将其下载为载明版本及日期的静态附件并书面签署后，方构成本合同的组成部分。", "basis": capture.message or "外部条款抓取失败。", "negotiation_focus": "不得接受可由客户单方动态更新的网页条款。", "source": "官网条款抓取器", "confidence": 95, "historical_release": False})
            enhancement_messages.append("官网条款抓取失败，已转人工固化任务。")
    llm_findings, llm_message = analyze_contract(
        current_text,
        [item["title"] for item in result["suggestions"]],
        user.id,
        our_role=contract.our_role or "",
        candidate_hints=legacy_shadow_candidates,
    )
    if llm_findings:
        result["suggestions"].extend(llm_findings)
        enhancement_messages.append(f"大模型补充发现 {len(llm_findings)} 项。")
    focused_review, focused_llm_message = adjudicate_focused_checks(
        current_text,
        focused_review,
        user.id,
        source_map=version.source_map or [],
        source_file=version.file_name,
    )
    if focused_review["check_results"]:
        enhancement_messages.append(focused_llm_message)
    # Every visible finding must identify the exact input file and, whenever
    # available, its page and clause. This runs for deterministic, knowledge,
    # website and LLM findings alike.
    for item in result["suggestions"]:
        if item.get("evidence_json"):
            continue
        located = find_text_span(current_text, str(item.get("original_text") or ""))
        if not located:
            continue
        start, end = located
        locator = locate_source_span(version.source_map or [], start, end, source_file=version.file_name)
        clause_no = clause_label_at(current_text, start)
        item["page_no"] = locator["page_no"]
        item["evidence_json"] = [{
            "source_file": locator["source_file"] or version.file_name,
            "page_no": locator["page_no"],
            "page_method": locator["page_method"],
            "clause_no": clause_no,
            "start_offset": start,
            "end_offset": end,
            "quote": current_text[start:end],
        }]
        source_label = locator["source_file"] or version.file_name
        if clause_no:
            source_label += f" 第{clause_no}条" if re.fullmatch(r"\d+(?:\.\d+)*", clause_no) else f" {clause_no}"
        if locator["page_no"]:
            source_label += f" 第{locator['page_no']}页"
        if source_label and source_label not in str(item.get("basis") or ""):
            item["basis"] = f"依据：{source_label}。{item.get('basis') or ''}".strip()
    ungrounded_replacements = 0
    for item in result["suggestions"]:
        action_type = str(item.get("action_type") or "替换条款")
        original_text = str(item.get("original_text") or "")
        suggested_text = str(item.get("suggested_text") or "")
        if action_type != "新增条款":
            suggested_text = preserve_asymmetric_obligation_subject(
                original_text,
                preserve_clause_format(
                    original_text,
                    suggested_text,
                    build_clause_context(
                        current_text,
                        original_text,
                        occurrence_no=int(item.get("occurrence_no") or 1),
                    ),
                ),
            )
            item["suggested_text"] = suggested_text
        quality = validate_replacement_clause(original_text, suggested_text, action_type)
        if not quality["eligible"]:
            item["action_type"] = "人工起草"
            item["suggested_text"] = ""
            ungrounded_replacements += 1
    if ungrounded_replacements:
        enhancement_messages.append(f"有 {ungrounded_replacements} 项替换稿与风险原文关联不足，已转为人工起草，不能直接接纳。")
    finalize_suggestion_metadata(result["suggestions"])
    before_rejection_filter = len(result["suggestions"])
    result["suggestions"] = [
        item
        for item in result["suggestions"]
        if item["risk_key"] not in rejected_keys
    ]
    suppressed_rejections = before_rejection_filter - len(result["suggestions"])
    if suppressed_rejections:
        enhancement_messages.append(f"继承人工放行结论，未重复提示 {suppressed_rejections} 项已拒绝建议。")
    recalculate_review_result(result, enhancement_messages)
    result["legacy_shadow"] = {
        "mode": legacy_rule_mode,
        "candidate_count": len(legacy_shadow_candidates),
        "rule_codes": sorted({item["rule_code"] for item in legacy_shadow_candidates}),
    }
    llm_completed = llm_message.startswith("大模型增强完成")
    legacy_engine_label = " + 旧正则影子召回" if legacy_rule_mode == "shadow" else " + 旧正则规则" if legacy_rule_mode == "active" else ""
    engine_name = "确定性检查 + 结构化知识库" + legacy_engine_label + (f" + 角色化Playbook {PLAYBOOK_VERSION}" if focused_review["check_results"] else "") + (" + 租赁基准条款2025.01" if contract.contract_type == "租赁" else " + 采购规则库") + (f" + 大模型（{settings.llm_model}）" if llm_completed else "")
    contract = db.get(Contract, contract_id)
    version = db.get(ContractVersion, source_version_id)
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    if not version or version.contract_id != contract_id or version.review_round_no != next_round:
        raise HTTPException(status_code=409, detail="审核期间合同轮次版本已更新，请重新启动审核")
    if contract.current_round + 1 != next_round or db.scalar(select(ReviewRun.id).where(ReviewRun.contract_id == contract_id, ReviewRun.round_no == next_round)):
        raise HTTPException(status_code=409, detail="审核期间轮次状态已变化，请刷新页面")
    if website_capture is not None:
        db.add(WebsiteTermsSnapshot(contract_id=contract.id, url=website_url, final_url=website_capture.final_url, content_hash=website_capture.content_hash, extracted_text=website_capture.text, fetch_status=website_capture.status, message=website_capture.message))
    run = ReviewRun(
        contract_id=contract.id,
        version_id=version.id,
        round_no=next_round,
        engine=engine_name,
        risk_score=result["risk_score"],
        summary=result["summary"],
        comparison_summary=result["comparison_summary"],
        stats=result["stats"],
        playbook_version=focused_review["playbook_version"],
        coverage_status=focused_review["coverage_status"],
        check_stats=focused_review["stats"],
        started_by_id=user.id,
    )
    db.add(run)
    db.flush()
    persisted_suggestions: list[ReviewSuggestion] = []
    for suggestion in result["suggestions"]:
        suggestion.setdefault("latest_instruction", "")
        suggestion.setdefault("revision_history", [{
            "version": 1,
            "instruction": "系统首次生成",
            "suggested_text": suggestion["suggested_text"],
            "generator": suggestion.get("source", "审核引擎"),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "created_by": "系统",
        }])
        item = ReviewSuggestion(review_run_id=run.id, **suggestion)
        db.add(item)
        persisted_suggestions.append(item)
    db.flush()
    check_models = {item.check_code: item for item in active_focused_checks(db)}
    baseline_citations_by_check = _baseline_citations_by_check_id(
        db,
        [item.id for item in check_models.values()],
    )
    baseline_by_no = {item.clause_no: item for item in active_standard_clauses(db, "租赁")}
    spec_by_code = {item.code: item for item in CHECK_SPECS}
    legal_citation_count = 0
    legal_as_of_date = contract.legal_as_of_date or date.today()
    for check_payload in focused_review["check_results"]:
        check_model = check_models.get(check_payload["check_code"])
        check_payload["baseline_citations"] = baseline_citations_by_check.get(check_model.id, []) if check_model else []
        check_result = CheckResult(
            review_run_id=run.id,
            check_id=check_model.id if check_model else None,
            check_code=check_payload["check_code"],
            check_name=check_payload["check_name"],
            category=check_payload["category"],
            status=check_payload["status"],
            risk_level=check_payload["risk_level"],
            confidence=check_payload["confidence"],
            satisfied_slots=check_payload["satisfied_slots"],
            missing_slots=check_payload["missing_slots"],
            contradictions=check_payload["contradictions"],
            reason=check_payload["reason"],
            decision_source=check_payload["decision_source"],
            legal_rag_required=check_payload["legal_rag_required"],
            technical_status=check_payload["technical_status"],
            human_confirmation_required=check_payload["human_confirmation_required"],
        )
        db.add(check_result)
        db.flush()
        for evidence in check_payload["evidence"]:
            db.add(EvidenceSpan(
                check_result_id=check_result.id,
                version_id=version.id,
                order_index=evidence["order_index"],
                clause_no=evidence["clause_no"],
                page_no=evidence["page_no"],
                page_method=evidence.get("page_method", ""),
                start_offset=evidence["start_offset"],
                end_offset=evidence["end_offset"],
                quote=evidence["quote"],
                evidence_type=evidence["evidence_type"],
                retrieval_methods=evidence["retrieval_methods"],
            ))
        trace = check_payload["retrieval_trace"]
        db.add(RetrievalTrace(
            check_result_id=check_result.id,
            query_pack=trace["query_pack"],
            searched_clause_count=trace["searched_clause_count"],
            candidate_count=trace["candidate_count"],
            returned_count=trace["returned_count"],
            methods_executed=trace["methods_executed"],
            candidates=trace["candidates"],
            truncated=trace["truncated"],
        ))
        check_payload["legal_citations"] = []
        if check_payload["legal_rag_required"]:
            legal_query = " ".join((
                check_payload["check_name"],
                check_payload["category"],
                *check_payload.get("legal_rag_triggers", []),
            ))
            for citation in retrieve_legal_authorities(db, legal_query, as_of_date=legal_as_of_date):
                authority = citation["authority"]
                db.add(LegalCitation(
                    check_result_id=check_result.id,
                    legal_authority_id=authority.id,
                    relevance_score=citation["relevance_score"],
                    matched_terms=citation["matched_terms"],
                    as_of_date=legal_as_of_date,
                ))
                check_payload["legal_citations"].append({
                    "authority_id": authority.id,
                    "authority": authority.authority,
                    "title": authority.title,
                    "document_no": authority.document_no,
                    "article_no": authority.article_no,
                    "summary": authority.summary,
                    "effective_from": authority.effective_from.isoformat(),
                    "effective_to": authority.effective_to.isoformat() if authority.effective_to else None,
                    "source_url": authority.source_url,
                    "relevance_score": citation["relevance_score"],
                    "matched_terms": citation["matched_terms"],
                    "as_of_date": legal_as_of_date.isoformat(),
                })
                legal_citation_count += 1
        if check_payload["status"] != "MET":
            spec = spec_by_code.get(check_payload["check_code"])
            baseline_parts = [
                f"{clause_no} {baseline_by_no[clause_no].content}"
                for clause_no in (spec.clause_refs if spec else ())
                if clause_no in baseline_by_no
            ]
            proposed_text = "\n".join(baseline_parts)[:6000]
            original_text = check_payload["evidence"][0]["quote"] if check_payload["evidence"] else ""
            action_type = "新增条款" if check_payload["status"] == "NOT_MENTIONED" else "替换条款"
            validation = validate_replacement_clause(original_text, proposed_text, action_type) if proposed_text else {"eligible": False, "status": "需人工起草", "warnings": ["没有可用的基准文本"]}
            db.add(RedlineProposal(
                check_result_id=check_result.id,
                action_type=action_type if validation.get("eligible") else "人工起草",
                source_clause_no=check_payload["evidence"][0]["clause_no"] if check_payload["evidence"] else "",
                original_text=original_text,
                # 即使与客户原文的直接关联度不足，也保留公司标准条款作为
                # 人工确认稿，供法务继续修改，而不是只展示风险结论。
                proposed_text=proposed_text,
                strategy=spec.redline_strategy if spec else "HUMAN_DRAFT",
                validation=validation,
                status="待人工确认" if check_payload["human_confirmation_required"] else "草案",
            ))
        if check_payload["human_confirmation_required"]:
            db.add(HumanConfirmation(check_result_id=check_result.id, required_role="法务审核", status="待确认"))
    db.flush()
    if legal_citation_count:
        enhancement_messages.append(f"法律 RAG 已为需复核的检查项绑定 {legal_citation_count} 条现行有效依据。")
    source_path = Path(version.file_path)
    if source_path.suffix.lower() in {".pdf", ".docx"}:
        safe_no = re.sub(r'[<>:"/\\|?*]+', "-", contract.contract_no).strip(" .") or "contract"
        suffix = source_path.suffix.lower()
        output = settings.export_dir / f"{safe_no}-R{next_round}-AI批注{suffix}"
        try:
            annotation_result = annotate_source_document(source_path, persisted_suggestions, output, round_no=next_round)
            run.annotated_file_path = str(output)
            run.annotated_file_name = output.name
            run.annotation_status = f"已在原文件定位 {annotation_result['anchored']} 项；另有 {annotation_result['fallback']} 项以页边批注提示"
        except Exception as exc:
            run.annotation_status = f"原文件批注生成失败：{type(exc).__name__}: {exc}"
    else:
        run.annotation_status = f"{source_path.suffix or '未知'} 格式暂不支持原位回写，请使用内部审核版查看意见"
    contract.template_type = result["template_type"]
    contract.risk_level = result["risk_level"]
    contract.status = "审核中"
    contract.current_round = next_round
    contract.summary = result["summary"]
    audit(db, request, user, "完成合同轮次审核并回写原文件", "合同", contract.id, {"round": next_round, "version_id": version.id, "engine": engine_name, "stats": result["stats"], "focused_checks": focused_review["stats"], "coverage_status": focused_review["coverage_status"], "annotation_status": run.annotation_status, "llm": llm_message, "focused_llm": focused_llm_message})
    db.commit()
    return {
        "review_run_id": run.id,
        "round_no": next_round,
        "version_id": version.id,
        "inherited_accepted_opinions": len(accepted),
        "annotation_status": run.annotation_status,
        "annotated_available": bool(run.annotated_file_path),
        "focused_review": focused_review,
        **result,
    }


@app.patch("/api/contracts/{contract_id}/assign")
def assign_reviewer(contract_id: str, payload: AssignmentInput, request: Request, user: User = Depends(require_roles("合同管理员", "法务审核")), db: Session = Depends(get_db)):
    row = db.execute(select(Contract, User).where(Contract.id == contract_id, User.id == payload.assignee_id)).first()
    contract, assignee = row if row else (None, None)
    if not contract or not assignee:
        raise HTTPException(status_code=404, detail="合同或审核人不存在")
    contract.assigned_to_id = assignee.id
    audit(db, request, user, "分配合同审核人", "合同", contract.id, {"assignee": assignee.name, "role": assignee.role})
    db.commit()
    return {"contract_id": contract.id, "assigned_to_id": assignee.id, "assignee": public_user(assignee)}


@app.get("/api/contracts/{contract_id}/consistency")
def check_consistency(contract_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    versions = db.scalars(select(ContractVersion).where(ContractVersion.contract_id == contract_id).order_by(desc(ContractVersion.version_no)).limit(5)).all()
    alerts: list[dict] = []
    if not versions:
        alerts.append({"level": "高", "title": "缺少合同文件", "detail": "台账没有可核对的合同版本。"})
    latest_text = versions[0].extracted_text if versions else ""
    if contract.contract_no and contract.contract_no not in latest_text:
        alerts.append({"level": "中", "title": "合同编号一致性待确认", "detail": f"最新文件未检出台账编号 {contract.contract_no}。"})
    if len(versions) >= 2:
        alerts.append({"level": "提示", "title": "最近版本差异", "detail": compare_versions(versions[1].extracted_text, versions[0].extracted_text)})
    supplements = db.scalars(select(ChangeRequest).where(ChangeRequest.contract_id == contract_id)).all()
    unresolved = db.scalar(select(func.count()).select_from(ReviewSuggestion).join(ReviewRun).where(ReviewRun.contract_id == contract_id, ReviewSuggestion.decision == "待处理")) or 0
    if unresolved:
        alerts.append({"level": "高", "title": "仍有未处置风险", "detail": f"签署/归档前仍有 {unresolved} 项审核建议待处理。"})
    score = max(0, 100 - sum(25 if item["level"] == "高" else 10 if item["level"] == "中" else 0 for item in alerts))
    return {"contract_id": contract.id, "score": score, "versions_checked": len(versions), "supplements_checked": len(supplements), "alerts": alerts}


@app.get("/api/contracts/{contract_id}/redacted-preview")
def redacted_preview(contract_id: str, _: User = Depends(require_roles("合同管理员", "法务审核", "系统管理员")), db: Session = Depends(get_read_db)):
    version = db.scalar(select(ContractVersion).where(ContractVersion.contract_id == contract_id).order_by(desc(ContractVersion.version_no)))
    if not version:
        raise HTTPException(status_code=404, detail="合同版本不存在")
    redacted, counts = redact_text(version.extracted_text)
    return {"contract_id": contract_id, "version_id": version.id, "counts": counts, "preview": redacted[:12000], "truncated": len(redacted) > 12000}


@app.post("/api/contracts/{contract_id}/notifications")
def queue_notification(contract_id: str, payload: NotificationInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    body = payload.body or f"合同《{contract.name}》（{contract.contract_no}）当前状态：{contract.status}，风险等级：{contract.risk_level}。请登录契析合同审核平台查看详情。"
    item = NotificationOutbox(contract_id=contract.id, recipient=payload.recipient, subject=payload.subject, body=body, created_by_id=user.id)
    db.add(item)
    audit(db, request, user, "加入邮件待发队列", "合同", contract.id, {"recipient": payload.recipient})
    db.commit()
    return {"id": item.id, "status": item.status, "recipient": item.recipient}


@app.patch("/api/suggestions/{suggestion_id}")
def decide_suggestion(suggestion_id: str, payload: SuggestionDecisionInput, request: Request, user: User = Depends(require_roles("法务审核", "合同管理员")), db: Session = Depends(get_db)):
    suggestion = db.get(ReviewSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="审核建议不存在")
    pending_referral = db.scalar(
        select(Consultation.id).where(
            Consultation.suggestion_id == suggestion_id,
            Consultation.status.in_(["待审核", "待答复"]),
        ).limit(1)
    )
    if pending_referral and payload.decision != "待处理":
        raise HTTPException(status_code=409, detail="该建议正在转批审核，请等待答复或先撤回转批")
    effective_text = payload.suggested_text or suggestion.suggested_text
    if payload.decision in {"接纳", "修改后接纳"} and not is_direct_replacement_clause(effective_text):
        raise HTTPException(status_code=400, detail="接纳前必须先生成可直接替换风险原文的完整合同条款，不能提交修改方向或占位文本")
    if payload.decision in {"接纳", "修改后接纳"}:
        quality = validate_replacement_clause(suggestion.original_text, effective_text, suggestion.action_type or "替换条款")
        if not quality["eligible"]:
            warnings = "；".join(str(item) for item in quality.get("warnings", []))
            raise HTTPException(status_code=400, detail=f"接纳前必须确认替换条款与风险原文具有关联：{warnings}")
    suggestion.decision = payload.decision
    suggestion.decision_note = payload.note
    suggestion.decided_by_id = user.id
    if payload.suggested_text:
        suggestion.suggested_text = payload.suggested_text
    audit(db, request, user, f"{payload.decision}AI建议", "审核建议", suggestion.id, {"note": payload.note})
    db.commit()
    return {"id": suggestion.id, "decision": suggestion.decision, "decision_note": suggestion.decision_note, "suggested_text": suggestion.suggested_text, "latest_instruction": suggestion.latest_instruction, "revision_history": suggestion.revision_history or []}


@app.post("/api/suggestions/{suggestion_id}/redraft")
def redraft_suggestion(suggestion_id: str, payload: SuggestionRedraftInput, request: Request, user: User = Depends(require_roles("法务审核", "合同管理员")), db: Session = Depends(get_db)):
    suggestion = db.get(ReviewSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="审核建议不存在")
    if suggestion.decision != "待处理":
        raise HTTPException(status_code=409, detail="该风险已经完成处置；如需改稿，请先恢复为待处理")
    pending_referral = db.scalar(
        select(Consultation.id).where(
            Consultation.suggestion_id == suggestion_id,
            Consultation.status.in_(["待审核", "待答复"]),
        ).limit(1)
    )
    if pending_referral:
        raise HTTPException(status_code=409, detail="该建议正在转批审核，请等待答复或先撤回转批")
    run = db.get(ReviewRun, suggestion.review_run_id)
    version = db.get(ContractVersion, run.version_id) if run else None
    history = list(suggestion.revision_history or [])
    if not history:
        history.append({
            "version": 1,
            "instruction": "系统首次生成",
            "suggested_text": suggestion.suggested_text,
            "generator": suggestion.source,
            "created_at": scalar(suggestion.created_at),
            "created_by": "系统",
        })
    source_values = {
        "original_text": suggestion.original_text,
        "current_text": suggestion.suggested_text,
        "action_type": suggestion.action_type or "替换条款",
        "title": suggestion.title,
        "basis": suggestion.basis,
        "contract_context": version.extracted_text if version else "",
        "risk_context": build_clause_context(
            version.extracted_text if version else "",
            suggestion.original_text or suggestion.anchor_text,
            occurrence_no=int(suggestion.occurrence_no or 1),
        ),
    }
    db.close()
    replacement, generator_message = redraft_replacement_clause(
        **source_values,
        instruction=payload.instruction.strip(),
        history=history,
    )
    if not replacement:
        raise HTTPException(status_code=502, detail=generator_message)
    suggestion = db.get(ReviewSuggestion, suggestion_id)
    if not suggestion or suggestion.decision != "待处理":
        raise HTTPException(status_code=409, detail="生成期间该风险的处置状态已变化，请刷新页面")
    next_version = max((int(item.get("version", 0)) for item in history if isinstance(item, dict)), default=0) + 1
    history.append({
        "version": next_version,
        "instruction": payload.instruction.strip(),
        "suggested_text": replacement,
        "generator": generator_message,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "created_by": user.name,
    })
    suggestion.suggested_text = replacement
    suggestion.latest_instruction = payload.instruction.strip()
    suggestion.revision_history = history
    audit(db, request, user, "根据自然语言重新起草替换条款", "审核建议", suggestion.id, {"draft_version": next_version, "instruction": payload.instruction.strip(), "generator": generator_message})
    db.commit()
    return {
        "id": suggestion.id,
        "suggested_text": suggestion.suggested_text,
        "replacement_check": validate_replacement_clause(suggestion.original_text, suggestion.suggested_text, suggestion.action_type or "替换条款"),
        "latest_instruction": suggestion.latest_instruction,
        "revision_history": suggestion.revision_history,
        "draft_version": next_version,
        "generator": generator_message,
    }


@app.patch("/api/document-comments/{comment_id}/source")
def correct_comment_source(comment_id: str, payload: CommentSourceInput, request: Request, user: User = Depends(require_roles("法务审核", "合同管理员")), db: Session = Depends(get_db)):
    comment = db.get(DocumentComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="批注不存在")
    comment.source_kind = payload.source_kind
    comment.source_department = payload.source_department
    comment.source_confidence = 100
    comment.source_basis = f"由{user.name}人工确认"
    if payload.author_name:
        comment.author_name = payload.author_name
    if comment.author_name and payload.source_kind != "未识别":
        identity = db.get(ReviewerIdentity, comment.author_name)
        if not identity:
            identity = ReviewerIdentity(alias=comment.author_name)
            db.add(identity)
        identity.display_name = comment.author_name
        identity.source_kind = payload.source_kind
        identity.department = payload.source_department
        identity.is_active = True
    audit(db, request, user, "确认批注来源", "文档批注", comment.id, {"source_kind": payload.source_kind, "department": payload.source_department})
    db.commit()
    return {"id": comment.id, "author_name": comment.author_name, "source_kind": comment.source_kind, "source_department": comment.source_department, "source_confidence": comment.source_confidence, "source_basis": comment.source_basis}


@app.post("/api/contracts/{contract_id}/consultations")
def create_consultation(contract_id: str, payload: ConsultationInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = db.get(Contract, contract_id)
    assignee = db.scalar(select(User).where(User.id == payload.assignee_id, User.is_active.is_(True)))
    if not contract or not assignee:
        raise HTTPException(status_code=404, detail="合同或询问对象不存在")
    if assignee.id == user.id:
        raise HTTPException(status_code=400, detail="转批对象不能是当前用户本人")
    if payload.suggestion_id:
        suggestion_contract_id = db.scalar(
            select(ReviewRun.contract_id)
            .join(ReviewSuggestion, ReviewSuggestion.review_run_id == ReviewRun.id)
            .where(ReviewSuggestion.id == payload.suggestion_id)
        )
        if suggestion_contract_id != contract_id:
            raise HTTPException(status_code=404, detail="该风险建议不属于当前合同")
        existing = db.scalar(
            select(Consultation.id).where(
                Consultation.suggestion_id == payload.suggestion_id,
                Consultation.status.in_(["待审核", "待答复"]),
            ).limit(1)
        )
        if existing:
            raise HTTPException(status_code=409, detail="该风险建议已有待处理转批，请等待答复或先撤回")
    status = "待审核" if payload.suggestion_id else "待答复"
    item = Consultation(
        contract_id=contract_id,
        suggestion_id=payload.suggestion_id,
        requester_id=user.id,
        assignee_id=assignee.id,
        target_department=assignee.department,
        question=payload.question.strip(),
        status=status,
        due_at=datetime.now() + timedelta(hours=payload.due_hours),
    )
    db.add(item)
    action = "转批风险建议" if payload.suggestion_id else "发起条款询问"
    audit(db, request, user, action, "审核建议" if payload.suggestion_id else "合同", payload.suggestion_id or contract_id, {"assignee_id": assignee.id, "assignee": assignee.name, "department": assignee.department})
    db.commit()
    return {"id": item.id, "suggestion_id": item.suggestion_id, "requester_id": item.requester_id, "assignee_id": item.assignee_id, "target_department": item.target_department, "question": item.question, "answer": item.answer, "review_decision": item.review_decision, "status": item.status, "due_at": scalar(item.due_at), "created_at": scalar(item.created_at)}


@app.patch("/api/consultations/{consultation_id}/answer")
def answer_consultation(consultation_id: str, payload: ConsultationAnswerInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(Consultation, consultation_id)
    if not item:
        raise HTTPException(status_code=404, detail="询问不存在")
    if item.assignee_id != user.id and user.role != "系统管理员":
        raise HTTPException(status_code=403, detail="仅被询问人可答复")
    if item.status not in {"待审核", "待答复"}:
        raise HTTPException(status_code=409, detail="该转批或询问已经结束")
    if item.suggestion_id and not payload.review_decision:
        raise HTTPException(status_code=400, detail="审核风险建议时必须选择审核结论")
    item.answer = payload.answer.strip()
    item.review_decision = payload.review_decision
    item.status = "已审核" if item.suggestion_id else "已答复"
    action = "完成风险建议转批审核" if item.suggestion_id else "答复条款询问"
    audit(db, request, user, action, "审核建议" if item.suggestion_id else "询问", item.suggestion_id or item.id, {"review_decision": item.review_decision, "consultation_id": item.id})
    db.commit()
    return {"id": item.id, "status": item.status, "answer": item.answer, "review_decision": item.review_decision}


@app.patch("/api/consultations/{consultation_id}/cancel")
def cancel_consultation(consultation_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(Consultation, consultation_id)
    if not item:
        raise HTTPException(status_code=404, detail="转批或询问不存在")
    if item.requester_id != user.id and user.role != "系统管理员":
        raise HTTPException(status_code=403, detail="仅发起人可撤回转批")
    if item.status not in {"待审核", "待答复"}:
        raise HTTPException(status_code=409, detail="该转批或询问已经结束")
    item.status = "已撤回"
    audit(db, request, user, "撤回风险建议转批" if item.suggestion_id else "撤回条款询问", "审核建议" if item.suggestion_id else "询问", item.suggestion_id or item.id, {"consultation_id": item.id})
    db.commit()
    return {"id": item.id, "status": item.status}


@app.post("/api/contracts/{contract_id}/negotiations")
def add_negotiation(contract_id: str, payload: NegotiationInput, request: Request, user: User = Depends(require_roles("销售", "法务审核", "合同管理员")), db: Session = Depends(get_db)):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    record = NegotiationRecord(contract_id=contract_id, suggestion_id=payload.suggestion_id, status=payload.status, customer_feedback=payload.customer_feedback, internal_note=payload.internal_note, recorded_by_id=user.id)
    db.add(record)
    contract.status = "待修改" if payload.status in {"客户二次偏离", "客户不接受"} else contract.status
    audit(db, request, user, "记录销售谈判反馈", "合同", contract_id, {"status": payload.status})
    db.commit()
    return {"id": record.id, "suggestion_id": record.suggestion_id, "status": record.status, "customer_feedback": record.customer_feedback, "internal_note": record.internal_note, "created_at": scalar(record.created_at)}


@app.get("/api/approvals")
def approvals(_: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    rows = db.execute(select(ApprovalTask, Contract, User).join(Contract, ApprovalTask.contract_id == Contract.id).outerjoin(User, ApprovalTask.approver_id == User.id).order_by(desc(ApprovalTask.created_at))).all()
    return [{"id": task.id, "contract_id": contract.id, "contract_no": contract.contract_no, "contract_name": contract.name, "customer": contract.customer, "level": task.level, "department": task.department, "approver": approver.name if approver else "待分配", "status": task.status, "decision": task.decision, "comment": task.comment, "external_flow_id": task.external_flow_id} for task, contract, approver in rows]


@app.post("/api/contracts/{contract_id}/approvals/prepare")
def prepare_approvals(contract_id: str, request: Request, user: User = Depends(require_roles("法务审核", "合同管理员", "审批人")), db: Session = Depends(get_db)):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    departments = ["法务部"]
    if float(contract.amount or 0) >= 500000 or contract.contract_type == "租赁":
        departments.append("财务部")
    if float(contract.amount or 0) >= 3000000:
        departments.append("管理层")
    existing_by_department = {
        item.department: item
        for item in db.scalars(select(ApprovalTask).where(ApprovalTask.contract_id == contract_id, ApprovalTask.department.in_(departments))).all()
    }
    approver_by_department = {
        item.department: item
        for item in db.scalars(select(User).where(User.department.in_(departments), User.is_active.is_(True)).order_by(User.created_at)).all()
    }
    created = []
    for level, department in enumerate(departments, start=1):
        existing = existing_by_department.get(department)
        if existing:
            created.append(existing)
            continue
        approver = approver_by_department.get(department)
        item = ApprovalTask(contract_id=contract_id, level=level, department=department, approver_id=approver.id if approver else None, status="待复核", external_flow_id=f"K2-DRAFT-{uuid4().hex[:8].upper()}")
        db.add(item)
        created.append(item)
    contract.status = "审批中"
    audit(db, request, user, "按矩阵生成审批单", "合同", contract_id, {"departments": departments})
    db.commit()
    return [approval_detail(item) for item in created]


@app.patch("/api/approvals/{approval_id}")
def decide_approval(approval_id: str, payload: ApprovalInput, request: Request, user: User = Depends(require_roles("审批人", "法务审核", "财务专家")), db: Session = Depends(get_db)):
    row = db.execute(
        select(ApprovalTask, Contract).join(Contract, ApprovalTask.contract_id == Contract.id).where(ApprovalTask.id == approval_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="审批任务不存在")
    item, contract = row
    if item.approver_id and item.approver_id != user.id and user.role != "系统管理员":
        raise HTTPException(status_code=403, detail="该任务未分配给当前用户")
    item.decision = payload.decision
    item.comment = payload.comment
    item.status = "已完成"
    if payload.decision == "驳回":
        contract.status = "待修改"
    elif not db.scalar(select(func.count()).select_from(ApprovalTask).where(ApprovalTask.contract_id == item.contract_id, ApprovalTask.id != item.id, ApprovalTask.status != "已完成")):
        contract.status = "通过"
    audit(db, request, user, f"审批{payload.decision}", "审批任务", item.id, {"comment": payload.comment})
    db.commit()
    return {"id": item.id, "status": item.status, "decision": item.decision, "comment": item.comment, "contract_status": contract.status}


@app.get("/api/change-requests")
def list_change_requests(_: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    rows = db.execute(select(ChangeRequest, Contract).join(Contract).order_by(desc(ChangeRequest.created_at))).all()
    return [{"id": item.id, "contract_id": contract.id, "contract_no": contract.contract_no, "contract_name": contract.name, "request_text": item.request_text, "original_requirement": item.original_requirement, "new_requirement": item.new_requirement, "generated_supplement": item.generated_supplement, "status": item.status, "created_at": scalar(item.created_at)} for item, contract in rows]


@app.post("/api/change-requests")
def create_change_request(payload: ChangeRequestInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = db.get(Contract, payload.contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    version = db.scalar(select(ContractVersion).where(ContractVersion.contract_id == contract.id).order_by(desc(ContractVersion.version_no)))
    sentences = re.split(r"(?<=[。；！？])", version.extracted_text if version else "")
    keywords = [word for word in re.findall(r"[\u4e00-\u9fff]{2,6}", payload.request_text) if word not in {"客户要求", "希望", "需要"}]
    related = [sentence.strip() for sentence in sentences if any(word in sentence for word in keywords[:8])]
    original = "\n".join(related[:3]) or "未在原合同中找到直接对应条款，请人工确认是否属于新增要求。"
    supplement = f"补充协议（草案）\n一、双方确认主合同编号为{contract.contract_no}。\n二、客户新要求：{payload.request_text}\n三、原合同相关约定：{original}\n四、本补充协议与主合同不一致的，以本补充协议为准；未变更事项继续按主合同执行。"
    item = ChangeRequest(contract_id=contract.id, request_text=payload.request_text, original_requirement=original, new_requirement=payload.request_text, generated_supplement=supplement, created_by_id=user.id)
    db.add(item)
    audit(db, request, user, "生成订改申请草案", "合同", contract.id)
    db.commit()
    return {"id": item.id, "contract_id": contract.id, "contract_no": contract.contract_no, "contract_name": contract.name, "request_text": item.request_text, "original_requirement": original, "new_requirement": payload.request_text, "generated_supplement": supplement, "status": item.status, "created_at": scalar(item.created_at)}


def _baseline_citations_by_check_id(db: Session, check_ids: list[str]) -> dict[str, list[dict]]:
    """Resolve each frozen Playbook check to its exact company-source clauses."""
    if not check_ids:
        return {}
    rows = db.execute(
        select(CheckBaselineMap.check_id, ClauseNode, KnowledgeDocument)
        .join(ClauseNode, ClauseNode.id == CheckBaselineMap.clause_node_id)
        .join(KnowledgeDocument, KnowledgeDocument.id == ClauseNode.document_id)
        .where(
            CheckBaselineMap.check_id.in_(check_ids),
            ClauseNode.is_active.is_(True),
            KnowledgeDocument.status == "active",
        )
        .order_by(CheckBaselineMap.check_id, ClauseNode.order_index)
    ).all()
    grouped: dict[str, list[dict]] = {}
    for check_id, clause, document in rows:
        grouped.setdefault(check_id, []).append({
            "document_id": document.id,
            "document_title": document.title,
            "document_key": document.document_key,
            "document_version": document.version,
            "source_file": document.source_file,
            "source_hash": document.source_hash,
            "clause_node_id": clause.id,
            "clause_no": clause.clause_no,
            "heading": clause.heading,
            "page_no": clause.page_no,
            "clause_text": clause.raw_text,
        })
    return grouped


def focused_review_payload(db: Session, run_id: str) -> dict:
    run = db.get(ReviewRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="审核轮次不存在")
    version = db.get(ContractVersion, run.version_id)
    results = db.scalars(select(CheckResult).where(CheckResult.review_run_id == run_id).order_by(CheckResult.check_code)).all()
    result_ids = [item.id for item in results]
    focused_checks = db.scalars(
        select(FocusedCheck).where(
            FocusedCheck.id.in_([item.check_id for item in results if item.check_id])
        )
    ).all() if results else []
    focused_check_by_id = {item.id: item for item in focused_checks}
    baseline_by_check = _baseline_citations_by_check_id(db, [item.check_id for item in results if item.check_id])
    evidence = db.scalars(select(EvidenceSpan).where(EvidenceSpan.check_result_id.in_(result_ids)).order_by(EvidenceSpan.check_result_id, EvidenceSpan.order_index)).all() if result_ids else []
    traces = db.scalars(select(RetrievalTrace).where(RetrievalTrace.check_result_id.in_(result_ids))).all() if result_ids else []
    redlines = db.scalars(select(RedlineProposal).where(RedlineProposal.check_result_id.in_(result_ids))).all() if result_ids else []
    confirmations = db.scalars(select(HumanConfirmation).where(HumanConfirmation.check_result_id.in_(result_ids))).all() if result_ids else []
    legal_rows = db.execute(
        select(LegalCitation, LegalAuthority)
        .join(LegalAuthority, LegalAuthority.id == LegalCitation.legal_authority_id)
        .where(LegalCitation.check_result_id.in_(result_ids))
        .order_by(LegalCitation.check_result_id, desc(LegalCitation.relevance_score))
    ).all() if result_ids else []
    evidence_by_result: dict[str, list] = {}
    for item in evidence:
        evidence_by_result.setdefault(item.check_result_id, []).append({
            "id": item.id,
            "order_index": item.order_index,
            "clause_no": item.clause_no,
            "page_no": item.page_no,
            "page_method": item.page_method,
            "source_file": version.file_name if version else "",
            "start_offset": item.start_offset,
            "end_offset": item.end_offset,
            "quote": item.quote,
            "evidence_type": item.evidence_type,
            "retrieval_methods": item.retrieval_methods or [],
        })
    trace_by_result = {item.check_result_id: {
        "query_pack": item.query_pack or {},
        "searched_clause_count": item.searched_clause_count,
        "candidate_count": item.candidate_count,
        "returned_count": item.returned_count,
        "methods_executed": item.methods_executed or [],
        "candidates": item.candidates or [],
        "truncated": item.truncated,
    } for item in traces}
    redline_by_result = {item.check_result_id: {
        "id": item.id,
        "action_type": item.action_type,
        "source_clause_no": item.source_clause_no,
        "original_text": item.original_text,
        "proposed_text": item.proposed_text,
        "strategy": item.strategy,
        "validation": item.validation or {},
        "status": item.status,
    } for item in redlines}
    confirmation_by_result = {item.check_result_id: {
        "id": item.id,
        "required_role": item.required_role,
        "status": item.status,
        "decision": item.decision,
        "comment": item.comment,
        "confirmed_by_id": item.confirmed_by_id,
        "updated_at": scalar(item.updated_at),
    } for item in confirmations}
    legal_by_result: dict[str, list] = {}
    for citation, authority in legal_rows:
        legal_by_result.setdefault(citation.check_result_id, []).append({
            "authority_id": authority.id,
            "authority": authority.authority,
            "title": authority.title,
            "document_no": authority.document_no,
            "article_no": authority.article_no,
            "summary": authority.summary,
            "effective_from": authority.effective_from.isoformat(),
            "effective_to": authority.effective_to.isoformat() if authority.effective_to else None,
            "source_url": authority.source_url,
            "relevance_score": citation.relevance_score,
            "matched_terms": citation.matched_terms or [],
            "as_of_date": citation.as_of_date.isoformat(),
        })
    payload_results = []
    for item in results:
        baseline_citations = baseline_by_check.get(item.check_id, [])
        redline = redline_by_result.get(item.id)
        if redline and not redline["proposed_text"] and baseline_citations:
            # 兼容修复前已生成的轮次：从绑定的公司标准条款恢复人工确认稿。
            redline = {
                **redline,
                "proposed_text": "\n".join(
                    f"{citation['clause_no']} {citation['clause_text']}"
                    for citation in baseline_citations
                )[:6000],
                "status": "待人工确认",
            }
        focused_check = focused_check_by_id.get(item.check_id)
        if item.status == "UNMET":
            negotiation_focus = "要求删除或修正与我方标准相反的约定，并恢复公司标准保护；如对方不接受，应明确替代控制、商业原因和放行权限。"
        elif item.status == "PARTIAL":
            negotiation_focus = "按公司标准补齐当前条款遗漏的条件、期限、责任边界和执行口径，避免仅保留原则性或歧义表述。"
        elif item.status == "NOT_MENTIONED":
            negotiation_focus = "要求将所引公司标准条款完整补入合同；如决定不补充，应记录缺失影响、替代控制和有权审批人的放行结论。"
        else:
            negotiation_focus = focused_check.recommendation if focused_check else "维持当前符合公司标准的表述。"
        payload_results.append({
            "id": item.id,
            "check_code": item.check_code,
            "check_name": item.check_name,
            "category": item.category,
            "status": item.status,
            "risk_level": item.risk_level,
            "confidence": item.confidence,
            "satisfied_slots": item.satisfied_slots or [],
            "missing_slots": item.missing_slots or [],
            "contradictions": item.contradictions or [],
            "reason": item.reason,
            "decision_source": item.decision_source,
            "legal_rag_required": item.legal_rag_required,
            "legal_citations": legal_by_result.get(item.id, []),
            "technical_status": item.technical_status,
            "human_confirmation_required": item.human_confirmation_required,
            "baseline_citations": baseline_citations,
            "evidence": evidence_by_result.get(item.id, []),
            "retrieval_trace": trace_by_result.get(item.id, {}),
            "redline": redline,
            "negotiation_focus": negotiation_focus,
            "human_confirmation": confirmation_by_result.get(item.id),
        })
    return {
        "review_run_id": run.id,
        "contract_id": run.contract_id,
        "round_no": run.round_no,
        "playbook_version": run.playbook_version or "",
        "coverage_status": run.coverage_status or "",
        "stats": run.check_stats or {},
        "results": payload_results,
    }


@app.get("/api/legal-authorities")
def legal_authorities(
    q: str = "",
    as_of: str = "",
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_read_db),
):
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="as_of 必须为 YYYY-MM-DD") from exc
    statement = select(LegalAuthority).where(
        LegalAuthority.status == "active",
        LegalAuthority.effective_from <= as_of_date,
        or_(LegalAuthority.effective_to.is_(None), LegalAuthority.effective_to >= as_of_date),
    )
    if q:
        like = f"%{q}%"
        statement = statement.where(or_(
            LegalAuthority.title.like(like),
            LegalAuthority.article_no.like(like),
            LegalAuthority.summary.like(like),
            LegalAuthority.content.like(like),
        ))
    items = db.scalars(statement.order_by(desc(LegalAuthority.effective_from), LegalAuthority.title).limit(limit)).all()
    return {
        "as_of_date": as_of_date.isoformat(),
        "items": [{
            "id": item.id,
            "authority": item.authority,
            "title": item.title,
            "document_no": item.document_no,
            "article_no": item.article_no,
            "summary": item.summary,
            "keywords": item.keywords or [],
            "effective_from": item.effective_from.isoformat(),
            "effective_to": item.effective_to.isoformat() if item.effective_to else None,
            "source_url": item.source_url,
            "content_hash": item.content_hash,
        } for item in items],
    }


@app.get("/api/playbooks/active")
def active_playbook(_: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    checks = active_focused_checks(db)
    return {
        "playbook_key": "LEASE_BASE_CN+OUR_ROLE_LESSOR+FORKLIFT+LINDE_2025_01",
        "version": PLAYBOOK_VERSION,
        "coverage": playbook_coverage(db),
        "checks": [{
            "id": item.id,
            "check_code": item.check_code,
            "order_index": item.order_index,
            "name": item.name,
            "category": item.category,
            "applies_when": item.applies_when or {},
            "query_pack": item.query_pack or {},
            "required_slots": item.required_slots or [],
            "deterministic_rules": item.deterministic_rules or [],
            "legal_rag_triggers": item.legal_rag_triggers or [],
            "requirement_level": item.requirement_level,
            "base_risk_level": item.base_risk_level,
            "recommendation": item.recommendation,
            "redline_strategy": item.redline_strategy,
            "human_confirmation_required": item.human_confirmation_required,
        } for item in checks],
    }


@app.get("/api/knowledge/structured")
def structured_knowledge(
    q: str = "",
    clause_no: str = "",
    limit: int = Query(200, ge=1, le=500),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_read_db),
):
    documents = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.status == "active").order_by(KnowledgeDocument.namespace, KnowledgeDocument.title)).all()
    document_ids = [item.id for item in documents]
    statement = select(ClauseNode).where(ClauseNode.document_id.in_(document_ids), ClauseNode.is_active.is_(True))
    if q:
        like = f"%{q}%"
        atom_node_ids = select(ClauseAtom.clause_node_id).where(
            ClauseAtom.is_active.is_(True),
            or_(
                ClauseAtom.atom_text.like(like),
                ClauseAtom.summary.like(like),
                ClauseAtom.action.like(like),
                ClauseAtom.object_text.like(like),
            ),
        )
        statement = statement.where(or_(
            ClauseNode.heading.like(like),
            ClauseNode.raw_text.like(like),
            ClauseNode.summary.like(like),
            ClauseNode.id.in_(atom_node_ids),
        ))
    if clause_no:
        statement = statement.where(ClauseNode.clause_no == clause_no)
    nodes = db.scalars(statement.order_by(ClauseNode.document_id, ClauseNode.order_index).limit(limit)).all()
    node_ids = [item.id for item in nodes]
    atoms = db.scalars(select(ClauseAtom).where(ClauseAtom.clause_node_id.in_(node_ids), ClauseAtom.is_active.is_(True)).order_by(ClauseAtom.clause_node_id, ClauseAtom.atom_no)).all() if node_ids else []
    links = db.scalars(select(ClauseLink).where(or_(ClauseLink.source_node_id.in_(node_ids), ClauseLink.target_node_id.in_(node_ids)))).all() if node_ids else []
    map_rows = db.execute(
        select(CheckBaselineMap, FocusedCheck)
        .join(FocusedCheck, FocusedCheck.id == CheckBaselineMap.check_id)
        .where(CheckBaselineMap.clause_node_id.in_(node_ids), FocusedCheck.is_active.is_(True))
        .order_by(CheckBaselineMap.clause_node_id, FocusedCheck.order_index)
    ).all() if node_ids else []
    atoms_by_node: dict[str, list] = {}
    for item in atoms:
        atoms_by_node.setdefault(item.clause_node_id, []).append({
            "id": item.id,
            "atom_no": item.atom_no,
            "atom_type": item.atom_type,
            "subject_role": item.subject_role,
            "modality": item.modality,
            "action": item.action,
            "atom_text": item.atom_text,
            "conditions": item.conditions or [],
            "exceptions": item.exceptions or [],
            "retrieval_terms": item.retrieval_terms or [],
            "facts": item.facts or [],
        })
    checks_by_node: dict[str, list] = {}
    for mapping, check in map_rows:
        checks_by_node.setdefault(mapping.clause_node_id, []).append({
            "check_code": check.check_code,
            "check_name": check.name,
            "map_type": mapping.map_type,
        })
    return {
        "coverage": playbook_coverage(db),
        "documents": [{
            "id": item.id,
            "namespace": item.namespace,
            "document_key": item.document_key,
            "title": item.title,
            "contract_type": item.contract_type,
            "version": item.version,
            "source_file": item.source_file,
            "source_hash": item.source_hash,
            "text_hash": item.text_hash,
            "authority_level": item.authority_level,
            "jurisdiction": item.jurisdiction,
            "effective_from": item.effective_from.isoformat() if item.effective_from else None,
            "effective_to": item.effective_to.isoformat() if item.effective_to else None,
            "status": item.status,
            "metadata": item.metadata_json or {},
        } for item in documents],
        "clauses": [{
            "id": item.id,
            "document_id": item.document_id,
            "clause_no": item.clause_no,
            "heading": item.heading,
            "heading_path": item.heading_path or [],
            "order_index": item.order_index,
            "node_type": item.node_type,
            "raw_text": item.raw_text,
            "normalized_text": item.normalized_text,
            "summary": item.summary,
            "page_no": item.page_no,
            "requirement_level": item.requirement_level,
            "atoms": atoms_by_node.get(item.id, []),
            "focused_checks": checks_by_node.get(item.id, []),
        } for item in nodes],
        "links": [{
            "id": item.id,
            "source_node_id": item.source_node_id,
            "target_node_id": item.target_node_id,
            "link_type": item.link_type,
            "source_text": item.source_text,
        } for item in links],
    }


@app.get("/api/review-runs/{run_id}/focused-checks")
def review_run_focused_checks(run_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    return focused_review_payload(db, run_id)


@app.patch("/api/focused-check-results/{result_id}/confirm")
def confirm_focused_check(
    result_id: str,
    payload: FocusedCheckConfirmationInput,
    request: Request,
    user: User = Depends(require_roles("法务审核", "合同管理员", "系统管理员")),
    db: Session = Depends(get_db),
):
    result = db.get(CheckResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Focused Check 结果不存在")
    confirmation = db.scalar(select(HumanConfirmation).where(HumanConfirmation.check_result_id == result_id))
    if not confirmation:
        confirmation = HumanConfirmation(check_result_id=result_id, required_role="法务审核")
        db.add(confirmation)
    confirmation.status = "已确认" if payload.decision in {"确认风险", "接受偏离"} else "退回修改"
    confirmation.decision = payload.decision
    confirmation.comment = payload.comment
    confirmation.confirmed_by_id = user.id
    run = db.get(ReviewRun, result.review_run_id)
    audit(db, request, user, "人工确认Focused Check", "审核结果", result.id, {"check_code": result.check_code, "decision": payload.decision, "comment": payload.comment})
    db.commit()
    return {"id": confirmation.id, "review_run_id": run.id if run else "", "check_result_id": result.id, "status": confirmation.status, "decision": confirmation.decision, "comment": confirmation.comment}


@app.post("/api/review-runs/{run_id}/confirm-high-risk")
def confirm_review_run_high_risk(
    run_id: str,
    payload: FocusedCheckConfirmationInput,
    request: Request,
    user: User = Depends(require_roles("法务审核", "合同管理员", "系统管理员")),
    db: Session = Depends(get_db),
):
    run = db.get(ReviewRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="审核轮次不存在")
    confirmations = db.scalars(
        select(HumanConfirmation)
        .join(CheckResult, CheckResult.id == HumanConfirmation.check_result_id)
        .where(CheckResult.review_run_id == run_id, HumanConfirmation.status != "已确认")
    ).all()
    for confirmation in confirmations:
        confirmation.status = "已确认" if payload.decision in {"确认风险", "接受偏离"} else "退回修改"
        confirmation.decision = payload.decision
        confirmation.comment = payload.comment
        confirmation.confirmed_by_id = user.id
    audit(db, request, user, "批量人工确认高风险Focused Checks", "审核轮次", run.id, {"count": len(confirmations), "decision": payload.decision, "comment": payload.comment})
    db.commit()
    return {"review_run_id": run.id, "confirmed_count": len(confirmations), "decision": payload.decision}


@app.get("/api/knowledge")
def knowledge(q: str = "", category: str = "", _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    statement = select(KnowledgeEntry).where(KnowledgeEntry.is_active.is_(True))
    if q:
        like = f"%{q}%"
        statement = statement.where(or_(KnowledgeEntry.title.like(like), KnowledgeEntry.content.like(like)))
    if category:
        statement = statement.where(KnowledgeEntry.category == category)
    entries = db.scalars(statement.order_by(KnowledgeEntry.entry_type, KnowledgeEntry.title)).all()
    standard_statement = select(StandardClause).where(StandardClause.is_active.is_(True))
    if q:
        like = f"%{q}%"
        standard_statement = standard_statement.where(or_(StandardClause.heading.like(like), StandardClause.content.like(like), StandardClause.clause_no.like(like)))
    if category:
        standard_statement = standard_statement.where(StandardClause.heading == category)
    standard = db.scalars(standard_statement).all()
    payload = [{"id": item.id, "entry_type": item.entry_type, "title": item.title, "category": item.category, "content": item.content, "source": item.source, "tags": item.tags, "risk_level": item.risk_level, "is_standard_clause": False} for item in entries]
    payload.extend({"id": item.id, "entry_type": "标准条款", "title": f"第 {item.clause_no} 条 · {item.heading}", "category": item.heading, "content": item.content, "source": f"{item.baseline_name} {item.baseline_version} / {item.source_file}", "tags": [item.contract_type, item.baseline_version, "常规基本条款"], "risk_level": item.risk_level, "is_standard_clause": True, "contract_type": item.contract_type, "clause_no": item.clause_no, "baseline_name": item.baseline_name, "baseline_version": item.baseline_version, "source_file": item.source_file, "is_required": item.is_required} for item in standard)
    return payload


@app.get("/api/standard-clauses")
def standard_clauses(contract_type: str = Query("租赁", pattern="^(采购|租赁)$"), _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    clauses = active_standard_clauses(db, contract_type)
    clauses.sort(key=lambda item: tuple(int(part) for part in item.clause_no.split(".")))
    return [{"id": item.id, "contract_type": item.contract_type, "baseline_name": item.baseline_name, "baseline_version": item.baseline_version, "clause_no": item.clause_no, "heading": item.heading, "content": item.content, "source_file": item.source_file, "source_hash": item.source_hash, "risk_level": item.risk_level, "is_required": item.is_required} for item in clauses]


@app.get("/api/reports/overview")
def reports(_: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    contracts = db.scalars(select(Contract)).all()
    customer_counts: dict[str, int] = {}
    for contract in contracts:
        customer_counts[contract.customer_group or contract.customer] = customer_counts.get(contract.customer_group or contract.customer, 0) + (1 if contract.risk_level == "高" else 0)
    suggestion_rows = db.execute(
        select(
            ReviewSuggestion.category,
            func.count(ReviewSuggestion.id),
            func.sum(case((ReviewSuggestion.decision.in_(["接纳", "修改后接纳", "拒绝"]), 1), else_=0)),
        ).group_by(ReviewSuggestion.category)
    ).all()
    resolved_suggestions = sum(int(row[2] or 0) for row in suggestion_rows)
    return {
        "kpis": {"contracts": len(contracts), "amount": sum(float(item.amount or 0) for item in contracts), "high_risk": sum(item.risk_level == "高" for item in contracts), "resolved_suggestions": resolved_suggestions},
        "risk_categories": [{"label": category, "value": count} for category, count, _ in sorted(suggestion_rows, key=lambda row: row[1], reverse=True)],
        "customer_warnings": [{"customer": key, "count": value, "level": "高" if value >= 2 else "关注"} for key, value in customer_counts.items() if value],
        "ledger": [{"contract_no": item.contract_no, "customer": item.customer, "type": item.contract_type, "amount": scalar(item.amount), "risk": item.risk_level, **(item.key_fields or {})} for item in contracts],
    }


@app.get("/api/audit-logs")
def audit_logs(limit: int = Query(100, le=500), _: User = Depends(require_roles("系统管理员", "合同管理员", "法务审核")), db: Session = Depends(get_read_db)):
    logs = db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)).all()
    return [{"id": item.id, "actor_name": item.actor_name, "action": item.action, "object_type": item.object_type, "object_id": item.object_id, "detail": item.detail, "ip_address": item.ip_address, "created_at": scalar(item.created_at)} for item in logs]


@app.get("/api/contracts/{contract_id}/versions/{version_id}/download")
def download_version(contract_id: str, version_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    version = db.get(ContractVersion, version_id)
    if not version or version.contract_id != contract_id or not Path(version.file_path).exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(version.file_path, filename=version.file_name, media_type=version.mime_type)


def _preview_source(db: Session, contract_id: str, version_id: str):
    version = db.get(ContractVersion, version_id)
    if not version or version.contract_id != contract_id:
        raise HTTPException(status_code=404, detail="版本不存在")
    run = db.scalars(
        select(ReviewRun)
        .options(joinedload(ReviewRun.suggestions))
        .where(ReviewRun.contract_id == contract_id, ReviewRun.version_id == version_id)
    ).unique().first()
    annotated_path = Path(run.annotated_file_path) if run and run.annotated_file_path else None
    source_path = annotated_path if annotated_path and annotated_path.exists() else Path(version.file_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="预览文件不存在")
    return version, run, source_path, bool(annotated_path and annotated_path.exists())


@app.get("/api/contracts/{contract_id}/versions/{version_id}/preview")
def preview_version(contract_id: str, version_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    version, run, source_path, is_annotated = _preview_source(db, contract_id, version_id)
    suffix = source_path.suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=422, detail="当前仅支持在线预览 PDF 和 DOCX")
    original_comments = db.scalars(
        select(DocumentComment)
        .where(DocumentComment.version_id == version.id)
        .order_by(DocumentComment.created_at)
    ).all()
    focused_results = db.scalars(
        select(CheckResult)
        .where(
            CheckResult.review_run_id == run.id,
            CheckResult.status.in_(("UNMET", "PARTIAL", "NOT_MENTIONED")),
            CheckResult.technical_status == "verified",
        )
        .order_by(CheckResult.check_code)
    ).all() if run else []
    focused_result_ids = [item.id for item in focused_results]
    focused_evidence_rows = db.scalars(
        select(EvidenceSpan)
        .where(EvidenceSpan.check_result_id.in_(focused_result_ids))
        .order_by(EvidenceSpan.check_result_id, EvidenceSpan.order_index)
    ).all() if focused_result_ids else []
    focused_redline_rows = db.scalars(
        select(RedlineProposal).where(RedlineProposal.check_result_id.in_(focused_result_ids))
    ).all() if focused_result_ids else []
    focused_evidence_by_result: dict[str, EvidenceSpan] = {}
    for evidence in focused_evidence_rows:
        focused_evidence_by_result.setdefault(evidence.check_result_id, evidence)
    focused_redline_by_result = {item.check_result_id: item for item in focused_redline_rows}
    focused_preview_risks = []
    for item in focused_results:
        evidence = focused_evidence_by_result.get(item.id)
        redline = focused_redline_by_result.get(item.id)
        focused_preview_risks.append({
            "id": item.id,
            "title": f"{item.check_code} {item.check_name}",
            "risk_level": item.risk_level,
            "anchor_text": evidence.quote if evidence else "",
            "original_text": evidence.quote if evidence else "",
            "suggested_text": redline.proposed_text if redline else "",
            "page_no": evidence.page_no if evidence else None,
            "reason": item.reason,
            "status": item.status,
            "negotiation_focus": (
                "要求删除或修正与我方标准相反的约定，并恢复公司标准保护。"
                if item.status == "UNMET"
                else "按公司标准补齐当前条款遗漏的条件、期限、责任边界和执行口径。"
                if item.status == "PARTIAL"
                else "要求将所引公司标准条款完整补入合同，并确认缺失条款的替代控制。"
            ),
        })
    preview_risks = [*(run.suggestions if run else []), *focused_preview_risks]
    pdf_locations = (
        locate_pdf_risks(source_path, preview_risks)
        if run and suffix == ".pdf"
        else {}
    )
    annotations = [
        {
            "id": item.id,
            "kind": "原文件批注",
            "author_name": item.author_name,
            "source_kind": item.source_kind,
            "source_department": item.source_department,
            "risk_level": "",
            "title": item.annotation_type,
            "page_no": item.page_no,
            "anchor_text": item.anchor_text,
            "comment_text": item.comment_text or "仅高亮，未填写批注文字",
            "suggested_text": "",
            "basis": item.source_basis,
            "negotiation_focus": "",
            "round_no": version.review_round_no,
            "highlight_color": "#f3c94f",
            "locations": [],
        }
        for item in original_comments
    ]
    if run:
        annotations.extend(
            {
                "id": item.id,
                "kind": "AI审核",
                "author_name": "契析 AI审核",
                "source_kind": "AI审核",
                "source_department": "合同审核系统",
                "risk_level": item.risk_level,
                "title": item.title,
                "page_no": item.page_no,
                "anchor_text": item.anchor_text or item.original_text,
                "comment_text": item.original_text,
                "suggested_text": item.suggested_text,
                "basis": item.basis,
                "negotiation_focus": item.negotiation_focus,
                "round_no": run.round_no,
                "highlight_color": AI_HIGHLIGHT_HEX,
                "locations": pdf_locations.get(item.id, []),
            }
            for item in run.suggestions
        )
        annotations.extend(
            {
                "id": item["id"],
                "kind": "专项检查",
                "author_name": "契析 专项审核",
                "source_kind": "角色化 Playbook",
                "source_department": "合同审核系统",
                "risk_level": item["risk_level"],
                "title": item["title"],
                "page_no": item["page_no"],
                "anchor_text": item["anchor_text"],
                "comment_text": item["reason"],
                "suggested_text": item["suggested_text"],
                "basis": f"{item['status']} · 角色化 Playbook 专项检查",
                "negotiation_focus": item["negotiation_focus"],
                "round_no": run.round_no,
                "highlight_color": AI_HIGHLIGHT_HEX,
                "locations": pdf_locations.get(item["id"], []),
            }
            for item in focused_preview_risks
        )
    html = ""
    embedded_comment_count = 0
    if suffix == ".docx":
        try:
            rendered = render_docx_preview(source_path, preview_risks)
            html = rendered["html"]
            embedded_comment_count = rendered["embedded_comment_count"]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "contract_id": contract_id,
        "version_id": version.id,
        "round_no": version.review_round_no,
        "round_color": AI_HIGHLIGHT_HEX,
        "file_name": source_path.name if is_annotated else version.file_name,
        "format": suffix.lstrip("."),
        "is_annotated": is_annotated,
        "annotation_status": run.annotation_status if run else "本轮尚未执行AI审核，显示上传原件批注",
        "html": html,
        "embedded_comment_count": embedded_comment_count,
        "annotations": annotations,
        "file_endpoint": f"/contracts/{contract_id}/versions/{version.id}/preview/file",
    }


@app.get("/api/contracts/{contract_id}/versions/{version_id}/preview/file")
def preview_version_file(contract_id: str, version_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    version, _, source_path, is_annotated = _preview_source(db, contract_id, version_id)
    suffix = source_path.suffix.lower()
    media_type = "application/pdf" if suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    preview_path = prepare_pdf_preview(source_path) if suffix == ".pdf" and is_annotated else source_path
    return FileResponse(
        preview_path,
        filename=source_path.name if is_annotated else version.file_name,
        media_type=media_type,
        content_disposition_type="inline",
    )


@app.get("/api/contracts/{contract_id}/review-runs/{run_id}/annotated")
def download_annotated_review(contract_id: str, run_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    run = db.get(ReviewRun, run_id)
    path = Path(run.annotated_file_path) if run and run.annotated_file_path else None
    if not run or run.contract_id != contract_id or not path or not path.exists():
        raise HTTPException(status_code=404, detail="本轮原文件批注版不存在")
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, filename=run.annotated_file_name or path.name, media_type=media_type)


@app.get("/api/contracts/{contract_id}/versions/compare")
def compare_contract_versions(contract_id: str, left: str, right: str, _: User = Depends(get_current_user), db: Session = Depends(get_read_db)):
    left_version, right_version = db.get(ContractVersion, left), db.get(ContractVersion, right)
    if not left_version or not right_version or left_version.contract_id != contract_id or right_version.contract_id != contract_id:
        raise HTTPException(status_code=404, detail="版本不存在")
    diff = list(difflib.ndiff(left_version.extracted_text.splitlines(), right_version.extracted_text.splitlines()))
    changes = [{"type": "add" if line.startswith("+") else "remove", "text": line[2:]} for line in diff if line.startswith(("+ ", "- "))][:200]
    return {"summary": compare_versions(left_version.extracted_text, right_version.extracted_text), "changes": changes}


@app.get("/api/contracts/{contract_id}/export")
def export_review(contract_id: str, mode: str = Query("redline", pattern="^(clean|redline|internal)$"), request: Request = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = db.get(Contract, contract_id)
    run = db.scalars(select(ReviewRun).options(joinedload(ReviewRun.suggestions)).where(ReviewRun.contract_id == contract_id).order_by(desc(ReviewRun.round_no))).unique().first()
    if not contract or not run:
        raise HTTPException(status_code=404, detail="合同或审核结果不存在")
    if mode == "internal" and user.role not in {"法务审核", "合同管理员", "系统管理员"}:
        raise HTTPException(status_code=403, detail="无权导出内部审核版")
    unresolved_high_risk_checks = db.scalar(
        select(func.count())
        .select_from(HumanConfirmation)
        .join(CheckResult, CheckResult.id == HumanConfirmation.check_result_id)
        .where(CheckResult.review_run_id == run.id, HumanConfirmation.status != "已确认")
    ) or 0
    if mode != "internal" and unresolved_high_risk_checks:
        raise HTTPException(status_code=409, detail=f"仍有 {unresolved_high_risk_checks} 项高风险 Focused Check 未完成人工确认，只允许先导出内部审核版")
    if mode == "redline" and run.annotated_file_path and Path(run.annotated_file_path).exists():
        path = Path(run.annotated_file_path)
        if request:
            audit(db, request, user, "下载原文件AI批注版", "合同", contract.id, {"round": run.round_no})
            db.commit()
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(path, filename=run.annotated_file_name or path.name, media_type=media_type)
    latest_version = db.scalar(select(ContractVersion).where(ContractVersion.contract_id == contract_id).order_by(desc(ContractVersion.version_no)))
    suggestion_statement = (
        select(ReviewSuggestion)
        .join(ReviewRun)
        .where(ReviewRun.contract_id == contract_id)
        .order_by(ReviewRun.round_no, ReviewSuggestion.created_at)
    )
    if mode == "clean" and latest_version:
        # Earlier accepted changes are already embedded in a generated working
        # version. Only decisions made against the latest version remain to be
        # applied to a clean export.
        suggestion_statement = suggestion_statement.where(ReviewRun.version_id == latest_version.id)
    suggestions = db.scalars(suggestion_statement).all()
    negotiations = db.scalars(select(NegotiationRecord).where(NegotiationRecord.contract_id == contract_id).order_by(NegotiationRecord.created_at)).all()
    internal_notes = [item.internal_note for item in negotiations if item.internal_note]
    focused_findings = focused_review_payload(db, run.id)["results"] if mode == "internal" and run.playbook_version else []
    output = settings.export_dir / f"{contract.contract_no}-{mode}-{datetime.now():%Y%m%d%H%M%S}.docx"
    build_review_docx(
        contract.name,
        latest_version.extracted_text if latest_version else "",
        suggestions,
        mode,
        output,
        internal_notes,
        focused_findings,
    )
    if request:
        audit(db, request, user, "导出审核文档", "合同", contract.id, {"mode": mode})
        db.commit()
    return FileResponse(output, filename=output.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
