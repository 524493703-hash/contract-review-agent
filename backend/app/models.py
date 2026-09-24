from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_department_created", "department", "created_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("usr"))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(160), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(40), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"
    __table_args__ = (Index("ix_contracts_updated_at", "updated_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("ctr"))
    contract_no: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    customer: Mapped[str] = mapped_column(String(255), index=True)
    customer_group: Mapped[str] = mapped_column(String(255), default="")
    contract_type: Mapped[str] = mapped_column(String(40), index=True)
    our_role: Mapped[str] = mapped_column(String(40), default="", index=True)
    transaction_scenario: Mapped[str] = mapped_column(String(80), default="")
    document_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    legal_as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    template_type: Mapped[str] = mapped_column(String(40), default="待判断")
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    project: Mapped[str] = mapped_column(String(255), default="", index=True)
    status: Mapped[str] = mapped_column(String(40), default="已提交", index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="待评估", index=True)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    website_terms_url: Mapped[str] = mapped_column(String(500), default="")
    key_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    parent_contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    versions: Mapped[list["ContractVersion"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    review_runs: Mapped[list["ReviewRun"]] = relationship(back_populates="contract", cascade="all, delete-orphan")


class ContractVersion(Base, TimestampMixin):
    __tablename__ = "contract_versions"
    __table_args__ = (
        UniqueConstraint("contract_id", "version_no", name="uq_contract_version"),
        UniqueConstraint("contract_id", "review_round_no", name="uq_contract_review_round_version"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("ver"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    review_round_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(120), default="客户版本")
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    extracted_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), default="")
    source_map: Mapped[list] = mapped_column(JSON, default=list)
    parse_status: Mapped[str] = mapped_column(String(40), default="已解析")
    parse_message: Mapped[str] = mapped_column(String(500), default="")
    document_source: Mapped[str] = mapped_column(String(40), default="客户")
    source_department: Mapped[str] = mapped_column(String(120), default="")
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    contract: Mapped[Contract] = relationship(back_populates="versions")


class ReviewRun(Base, TimestampMixin):
    __tablename__ = "review_runs"
    __table_args__ = (UniqueConstraint("contract_id", "round_no", name="uq_contract_round"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("run"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("contract_versions.id"))
    round_no: Mapped[int] = mapped_column(Integer)
    # The engine label is assembled from every enabled review stage and the
    # configured model name. It can legitimately exceed the original
    # VARCHAR(80) limit as stages are added, so keep it as text rather than
    # letting a completed review fail during the final database flush.
    engine: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), default="规则引擎")
    status: Mapped[str] = mapped_column(String(40), default="已完成")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    comparison_summary: Mapped[str] = mapped_column(Text, default="")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    annotated_file_path: Mapped[str] = mapped_column(String(500), default="")
    annotated_file_name: Mapped[str] = mapped_column(String(255), default="")
    annotation_status: Mapped[str] = mapped_column(String(255), default="")
    playbook_version: Mapped[str] = mapped_column(String(80), default="")
    coverage_status: Mapped[str] = mapped_column(String(40), default="")
    check_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    started_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    contract: Mapped[Contract] = relationship(back_populates="review_runs")
    suggestions: Mapped[list["ReviewSuggestion"]] = relationship(back_populates="review_run", cascade="all, delete-orphan")
    check_results: Mapped[list["CheckResult"]] = relationship(back_populates="review_run", cascade="all, delete-orphan")


class ReviewSuggestion(Base, TimestampMixin):
    __tablename__ = "review_suggestions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("sug"))
    review_run_id: Mapped[str] = mapped_column(ForeignKey("review_runs.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(255))
    risk_level: Mapped[str] = mapped_column(String(20), index=True)
    original_text: Mapped[str] = mapped_column(Text)
    suggested_text: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(Text)
    negotiation_focus: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120), default="规则库")
    confidence: Mapped[int] = mapped_column(Integer, default=80)
    historical_release: Mapped[bool] = mapped_column(Boolean, default=False)
    baseline_clause_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    risk_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    action_type: Mapped[str] = mapped_column(String(30), default="替换条款")
    occurrence_no: Mapped[int] = mapped_column(Integer, default=1)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    latest_instruction: Mapped[str] = mapped_column(Text, default="")
    revision_history: Mapped[list] = mapped_column(JSON, default=list)
    decision: Mapped[str] = mapped_column(String(30), default="待处理", index=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    check_status: Mapped[str] = mapped_column(String(30), default="")
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    risk_reason: Mapped[str] = mapped_column(Text, default="")
    deviation_type: Mapped[str] = mapped_column(String(40), default="")
    human_confirmation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_run: Mapped[ReviewRun] = relationship(back_populates="suggestions")


class Consultation(Base, TimestampMixin):
    __tablename__ = "consultations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("ask"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    suggestion_id: Mapped[str | None] = mapped_column(ForeignKey("review_suggestions.id"), nullable=True)
    requester_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_department: Mapped[str] = mapped_column(String(120), default="")
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    review_decision: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(30), default="待答复", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NegotiationRecord(Base, TimestampMixin):
    __tablename__ = "negotiation_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("neg"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    suggestion_id: Mapped[str | None] = mapped_column(ForeignKey("review_suggestions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    customer_feedback: Mapped[str] = mapped_column(Text)
    internal_note: Mapped[str] = mapped_column(Text, default="")
    recorded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ApprovalTask(Base, TimestampMixin):
    __tablename__ = "approval_tasks"
    __table_args__ = (Index("ix_approval_contract_department", "contract_id", "department"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("apr"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    department: Mapped[str] = mapped_column(String(80))
    approver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="待复核", index=True)
    decision: Mapped[str] = mapped_column(String(40), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    external_flow_id: Mapped[str] = mapped_column(String(120), default="")


class ChangeRequest(Base, TimestampMixin):
    __tablename__ = "change_requests"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("chg"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    request_text: Mapped[str] = mapped_column(Text)
    original_requirement: Mapped[str] = mapped_column(Text, default="")
    new_requirement: Mapped[str] = mapped_column(Text, default="")
    generated_supplement: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="草稿", index=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class KnowledgeEntry(Base, TimestampMixin):
    __tablename__ = "knowledge_entries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("knw"))
    entry_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(255), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String(20), default="提示")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StandardClause(Base, TimestampMixin):
    __tablename__ = "standard_clauses"
    __table_args__ = (
        UniqueConstraint("contract_type", "baseline_version", "clause_no", name="uq_standard_clause_version"),
        Index("ix_standard_clause_type_active", "contract_type", "is_active"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("std"))
    contract_type: Mapped[str] = mapped_column(String(40), index=True)
    baseline_name: Mapped[str] = mapped_column(String(255))
    baseline_version: Mapped[str] = mapped_column(String(40), index=True)
    clause_no: Mapped[str] = mapped_column(String(30), index=True)
    heading: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    source_file: Mapped[str] = mapped_column(String(500))
    source_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="提示")
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("namespace", "document_key", "version", name="uq_knowledge_document_version"),
        Index("ix_knowledge_document_scope", "namespace", "contract_type", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("kdoc"))
    namespace: Mapped[str] = mapped_column(String(40), index=True)
    document_key: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255))
    contract_type: Mapped[str] = mapped_column(String(40), default="", index=True)
    version: Mapped[str] = mapped_column(String(40), index=True)
    source_file: Mapped[str] = mapped_column(String(500), default="")
    source_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    text_hash: Mapped[str] = mapped_column(String(64), default="")
    authority_level: Mapped[str] = mapped_column(String(40), default="canonical")
    jurisdiction: Mapped[str] = mapped_column(String(40), default="CN")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class LegalAuthority(Base, TimestampMixin):
    __tablename__ = "legal_authorities"
    __table_args__ = (
        UniqueConstraint("document_no", "article_no", "effective_from", name="uq_legal_authority_version"),
        Index("ix_legal_authority_scope", "jurisdiction", "status", "effective_from"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("law"))
    authority: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    document_no: Mapped[str] = mapped_column(String(120), default="", index=True)
    article_no: Mapped[str] = mapped_column(String(80), default="", index=True)
    content: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    summary: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    jurisdiction: Mapped[str] = mapped_column(String(40), default="CN", index=True)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class ClauseNode(Base, TimestampMixin):
    __tablename__ = "clause_nodes"
    __table_args__ = (
        UniqueConstraint("document_id", "clause_no", name="uq_clause_node_document_no"),
        Index("ix_clause_node_document_order", "document_id", "order_index"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("cln"))
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("clause_nodes.id"), nullable=True, index=True)
    clause_no: Mapped[str] = mapped_column(String(40), index=True)
    heading: Mapped[str] = mapped_column(String(160), default="")
    heading_path: Mapped[list] = mapped_column(JSON, default=list)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    node_type: Mapped[str] = mapped_column(String(30), default="clause")
    raw_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    normalized_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    summary: Mapped[str] = mapped_column(Text, default="")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requirement_level: Mapped[str] = mapped_column(String(30), default="preferred", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ClauseAtom(Base, TimestampMixin):
    __tablename__ = "clause_atoms"
    __table_args__ = (
        UniqueConstraint("clause_node_id", "atom_no", name="uq_clause_atom_node_no"),
        Index("ix_clause_atom_action_role", "action", "subject_role", "is_active"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("atm"))
    clause_node_id: Mapped[str] = mapped_column(ForeignKey("clause_nodes.id"), index=True)
    atom_no: Mapped[str] = mapped_column(String(30))
    atom_type: Mapped[str] = mapped_column(String(50), default="obligation", index=True)
    subject_role: Mapped[str] = mapped_column(String(40), default="")
    modality: Mapped[str] = mapped_column(String(40), default="")
    action: Mapped[str] = mapped_column(String(80), default="", index=True)
    object_text: Mapped[str] = mapped_column(String(255), default="")
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    exceptions: Mapped[list] = mapped_column(JSON, default=list)
    consequence: Mapped[str] = mapped_column(Text, default="")
    atom_text: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    retrieval_terms: Mapped[list] = mapped_column(JSON, default=list)
    facts: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ClauseLink(Base, TimestampMixin):
    __tablename__ = "clause_links"
    __table_args__ = (UniqueConstraint("source_node_id", "target_node_id", "link_type", name="uq_clause_link"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("lnk"))
    source_node_id: Mapped[str] = mapped_column(ForeignKey("clause_nodes.id"), index=True)
    target_node_id: Mapped[str] = mapped_column(ForeignKey("clause_nodes.id"), index=True)
    link_type: Mapped[str] = mapped_column(String(40), index=True)
    source_text: Mapped[str] = mapped_column(String(255), default="")


class Playbook(Base, TimestampMixin):
    __tablename__ = "playbooks"
    __table_args__ = (UniqueConstraint("playbook_key", "version", name="uq_playbook_version"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("pb"))
    playbook_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(40), index=True)
    contract_type: Mapped[str] = mapped_column(String(40), index=True)
    our_role: Mapped[str] = mapped_column(String(40), index=True)
    scenario: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class FocusedCheck(Base, TimestampMixin):
    __tablename__ = "focused_checks"
    __table_args__ = (
        UniqueConstraint("playbook_id", "check_code", name="uq_focused_check_playbook_code"),
        Index("ix_focused_check_playbook_order", "playbook_id", "order_index"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("chk"))
    playbook_id: Mapped[str] = mapped_column(ForeignKey("playbooks.id"), index=True)
    check_code: Mapped[str] = mapped_column(String(40), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80), index=True)
    applies_when: Mapped[dict] = mapped_column(JSON, default=dict)
    query_pack: Mapped[dict] = mapped_column(JSON, default=dict)
    required_slots: Mapped[list] = mapped_column(JSON, default=list)
    deterministic_rules: Mapped[list] = mapped_column(JSON, default=list)
    legal_rag_triggers: Mapped[list] = mapped_column(JSON, default=list)
    requirement_level: Mapped[str] = mapped_column(String(30), default="preferred")
    base_risk_level: Mapped[str] = mapped_column(String(20), default="中")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    redline_strategy: Mapped[str] = mapped_column(String(80), default="")
    expected_absence_check: Mapped[bool] = mapped_column(Boolean, default=False)
    human_confirmation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class CheckBaselineMap(Base):
    __tablename__ = "check_baseline_maps"
    __table_args__ = (UniqueConstraint("check_id", "clause_node_id", "atom_id", name="uq_check_baseline_map"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("cbm"))
    check_id: Mapped[str] = mapped_column(ForeignKey("focused_checks.id"), index=True)
    clause_node_id: Mapped[str] = mapped_column(ForeignKey("clause_nodes.id"), index=True)
    atom_id: Mapped[str | None] = mapped_column(ForeignKey("clause_atoms.id"), nullable=True, index=True)
    map_type: Mapped[str] = mapped_column(String(30), default="supports")


class CheckResult(Base, TimestampMixin):
    __tablename__ = "check_results"
    __table_args__ = (
        UniqueConstraint("review_run_id", "check_code", name="uq_check_result_run_code"),
        Index("ix_check_result_status_risk", "status", "risk_level"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("res"))
    review_run_id: Mapped[str] = mapped_column(ForeignKey("review_runs.id"), index=True)
    check_id: Mapped[str | None] = mapped_column(ForeignKey("focused_checks.id"), nullable=True, index=True)
    check_code: Mapped[str] = mapped_column(String(40), index=True)
    check_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80), default="", index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="提示", index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    satisfied_slots: Mapped[list] = mapped_column(JSON, default=list)
    missing_slots: Mapped[list] = mapped_column(JSON, default=list)
    contradictions: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, default="")
    decision_source: Mapped[str] = mapped_column(String(60), default="deterministic")
    legal_rag_required: Mapped[bool] = mapped_column(Boolean, default=False)
    technical_status: Mapped[str] = mapped_column(String(40), default="verified")
    human_confirmation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    review_run: Mapped[ReviewRun] = relationship(back_populates="check_results")


class EvidenceSpan(Base, TimestampMixin):
    __tablename__ = "evidence_spans"
    __table_args__ = (Index("ix_evidence_result_order", "check_result_id", "order_index"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("evd"))
    check_result_id: Mapped[str] = mapped_column(ForeignKey("check_results.id"), index=True)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("contract_versions.id"), nullable=True, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    clause_no: Mapped[str] = mapped_column(String(40), default="")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_method: Mapped[str] = mapped_column(String(40), default="")
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    evidence_type: Mapped[str] = mapped_column(String(30), default="support")
    retrieval_methods: Mapped[list] = mapped_column(JSON, default=list)


class RetrievalTrace(Base, TimestampMixin):
    __tablename__ = "retrieval_traces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("trc"))
    check_result_id: Mapped[str] = mapped_column(ForeignKey("check_results.id"), unique=True, index=True)
    query_pack: Mapped[dict] = mapped_column(JSON, default=dict)
    searched_clause_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    returned_count: Mapped[int] = mapped_column(Integer, default=0)
    methods_executed: Mapped[list] = mapped_column(JSON, default=list)
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)


class LegalCitation(Base, TimestampMixin):
    __tablename__ = "legal_citations"
    __table_args__ = (UniqueConstraint("check_result_id", "legal_authority_id", name="uq_check_legal_citation"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("lct"))
    check_result_id: Mapped[str] = mapped_column(ForeignKey("check_results.id"), index=True)
    legal_authority_id: Mapped[str] = mapped_column(ForeignKey("legal_authorities.id"), index=True)
    relevance_score: Mapped[int] = mapped_column(Integer, default=0)
    matched_terms: Mapped[list] = mapped_column(JSON, default=list)
    as_of_date: Mapped[date] = mapped_column(Date)


class RedlineProposal(Base, TimestampMixin):
    __tablename__ = "redline_proposals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("rdl"))
    check_result_id: Mapped[str] = mapped_column(ForeignKey("check_results.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(30), default="人工起草")
    source_clause_no: Mapped[str] = mapped_column(String(40), default="")
    original_text: Mapped[str] = mapped_column(Text, default="")
    proposed_text: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[str] = mapped_column(String(80), default="")
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="草案", index=True)


class HumanConfirmation(Base, TimestampMixin):
    __tablename__ = "human_confirmations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("hcf"))
    check_result_id: Mapped[str] = mapped_column(ForeignKey("check_results.id"), index=True)
    required_role: Mapped[str] = mapped_column(String(40), default="法务审核")
    status: Mapped[str] = mapped_column(String(30), default="待确认", index=True)
    decision: Mapped[str] = mapped_column(String(40), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    confirmed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ReviewerIdentity(Base, TimestampMixin):
    __tablename__ = "reviewer_identities"
    alias: Mapped[str] = mapped_column(String(160), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    source_kind: Mapped[str] = mapped_column(String(40), default="同事")
    department: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DocumentComment(Base, TimestampMixin):
    __tablename__ = "document_comments"
    __table_args__ = (Index("ix_document_comment_version_source", "version_id", "source_kind"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("cmt"))
    version_id: Mapped[str] = mapped_column(ForeignKey("contract_versions.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(160), default="")
    annotation_type: Mapped[str] = mapped_column(String(60), default="批注")
    author_name: Mapped[str] = mapped_column(String(160), default="")
    source_kind: Mapped[str] = mapped_column(String(40), default="未识别", index=True)
    source_department: Mapped[str] = mapped_column(String(120), default="")
    source_confidence: Mapped[int] = mapped_column(Integer, default=0)
    source_basis: Mapped[str] = mapped_column(String(255), default="")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    comment_text: Mapped[str] = mapped_column(Text, default="")
    comment_date: Mapped[str] = mapped_column(String(80), default="")
    location: Mapped[dict] = mapped_column(JSON, default=dict)


class WebsiteTermsSnapshot(Base):
    __tablename__ = "website_terms_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("web"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    final_url: Mapped[str] = mapped_column(String(1000), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    extracted_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), default="")
    fetch_status: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False, index=True)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("msg"))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30), default="email")
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="待发送", index=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uid("aud"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String(120), default="系统")
    action: Mapped[str] = mapped_column(String(120), index=True)
    object_type: Mapped[str] = mapped_column(String(80), default="")
    object_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False, index=True)
