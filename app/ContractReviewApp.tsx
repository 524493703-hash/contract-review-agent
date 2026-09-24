"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

type User = {
  id: string;
  username: string;
  name: string;
  email: string;
  department: string;
  role: string;
};
type BaselineCitation = {
  document_id?: string;
  document_title: string;
  document_key?: string;
  document_version: string;
  source_file: string;
  source_hash: string;
  clause_node_id?: string;
  clause_no: string;
  heading: string;
  page_no?: number | null;
  clause_text: string;
};
type Contract = {
  id: string;
  contract_no: string;
  name: string;
  customer: string;
  customer_group: string;
  contract_type: string;
  our_role: string;
  transaction_scenario: string;
  document_complete: boolean;
  legal_as_of_date?: string | null;
  template_type: string;
  amount: number;
  currency: string;
  project: string;
  status: string;
  risk_level: string;
  current_round: number;
  website_terms_url: string;
  key_fields: Record<string, unknown>;
  summary: string;
  version_count: number;
  suggestion_count: number;
  assigned_to_id?: string;
  created_at: string;
  updated_at: string;
};
type Suggestion = {
  id: string;
  rule_code: string;
  risk_key: string;
  action_type: string;
  occurrence_no: number;
  occurrence_count: number;
  category: string;
  title: string;
  risk_level: string;
  original_text: string;
  suggested_text: string;
  basis: string;
  negotiation_focus: string;
  source: string;
  confidence: number;
  historical_release: boolean;
  page_no?: number;
  anchor_text: string;
  latest_instruction: string;
  revision_history: {
    version: number;
    instruction: string;
    suggested_text: string;
    generator: string;
    created_at: string;
    created_by: string;
  }[];
  decision: string;
  decision_note: string;
  baseline_citation?: BaselineCitation | null;
  replacement_check?: {
    status: string;
    eligible: boolean;
    relation_score: number;
    shared_topics: string[];
    shared_terms: string[];
    changed_anchors: {
      subjects: string[];
      numeric: string[];
      triggers: string[];
    };
    warnings: string[];
  };
};
type Version = {
  id: string;
  version_no: number;
  review_round_no: number;
  label: string;
  file_name: string;
  file_size: number;
  parse_status: string;
  parse_message: string;
  document_source: string;
  source_department: string;
  comment_count: number;
  created_at: string;
};
type ReviewRun = {
  id: string;
  version_id: string;
  round_no: number;
  engine: string;
  status: string;
  risk_score: number;
  summary: string;
  comparison_summary: string;
  stats: Record<string, number>;
  playbook_version: string;
  coverage_status: string;
  check_stats: Record<string, number>;
  focused_checks_available: boolean;
  annotated_file_name: string;
  annotation_status: string;
  annotated_available: boolean;
  created_at: string;
  suggestions: Suggestion[];
};
type FocusedEvidence = {
  id: string;
  clause_no: string;
  page_no?: number | null;
  page_method?: string;
  source_file?: string;
  start_offset?: number;
  end_offset?: number;
  quote: string;
  evidence_type: string;
  retrieval_methods: string[];
};
type LegalCitation = {
  authority_id: string;
  authority: string;
  title: string;
  document_no: string;
  article_no: string;
  summary: string;
  effective_from: string;
  effective_to?: string | null;
  source_url: string;
  relevance_score: number;
  matched_terms: string[];
  as_of_date: string;
};
type FocusedCheckResult = {
  id: string;
  check_code: string;
  check_name: string;
  category: string;
  status: "MET" | "UNMET" | "PARTIAL" | "NOT_MENTIONED";
  risk_level: string;
  confidence: number;
  satisfied_slots: string[];
  missing_slots: string[];
  contradictions: { pattern: string; quote: string }[];
  reason: string;
  decision_source: string;
  legal_rag_required: boolean;
  legal_citations: LegalCitation[];
  baseline_citations: BaselineCitation[];
  technical_status: string;
  human_confirmation_required: boolean;
  evidence: FocusedEvidence[];
  retrieval_trace: {
    searched_clause_count?: number;
    candidate_count?: number;
    returned_count?: number;
    methods_executed?: string[];
    truncated?: boolean;
  };
  redline?: {
    action_type: string;
    proposed_text: string;
    strategy: string;
    status: string;
  } | null;
  negotiation_focus: string;
  human_confirmation?: {
    id: string;
    status: string;
    decision: string;
    comment: string;
  } | null;
};
type FocusedReview = {
  review_run_id: string;
  playbook_version: string;
  coverage_status: string;
  stats: Record<string, number>;
  results: FocusedCheckResult[];
};
type DocumentComment = {
  id: string;
  version_id: string;
  annotation_type: string;
  author_name: string;
  source_kind: string;
  source_department: string;
  source_confidence: number;
  source_basis: string;
  page_no?: number;
  anchor_text: string;
  comment_text: string;
  comment_date: string;
  created_at: string;
};
type PreviewAnnotation = {
  id: string;
  kind: string;
  author_name: string;
  source_kind: string;
  source_department: string;
  risk_level: string;
  title: string;
  page_no?: number;
  anchor_text: string;
  comment_text: string;
  suggested_text: string;
  basis: string;
  negotiation_focus: string;
  round_no: number;
  highlight_color: string;
  locations?: PreviewLocation[];
};
type PreviewLocation = {
  page_no: number;
  x: number;
  y: number;
  width: number;
  height: number;
};
type PreviewData = {
  contract_id: string;
  version_id: string;
  round_no: number;
  round_color: string;
  file_name: string;
  format: "pdf" | "docx";
  is_annotated: boolean;
  annotation_status: string;
  html: string;
  embedded_comment_count: number;
  annotations: PreviewAnnotation[];
  file_endpoint: string;
};
type Consultation = {
  id: string;
  suggestion_id: string | null;
  requester_id: string;
  assignee_id: string;
  target_department: string;
  question: string;
  answer: string;
  review_decision: string;
  status: string;
  due_at: string;
  created_at: string;
};
type Negotiation = {
  id: string;
  suggestion_id: string | null;
  status: string;
  customer_feedback: string;
  internal_note: string;
  created_at: string;
};
type Approval = {
  id: string;
  contract_id?: string;
  contract_no?: string;
  contract_name?: string;
  customer?: string;
  level: number;
  department: string;
  approver?: string;
  approver_id?: string;
  status: string;
  decision: string;
  comment: string;
  external_flow_id: string;
};
type ContractDetail = {
  contract: Contract;
  versions: Version[];
  review_runs: ReviewRun[];
  document_comments: DocumentComment[];
  cumulative_review: {
    rounds_completed: number;
    total_opinions: number;
    pending: number;
    accepted: number;
    released: number;
  };
  negotiations: Negotiation[];
  consultations: Consultation[];
  approvals: Approval[];
  focused_review: FocusedReview | null;
};
type Dashboard = {
  greeting: string;
  totals: {
    contracts: number;
    pending: number;
    consultations: number;
    high_risk: number;
  };
  by_status: { label: string; value: number }[];
  by_risk: { label: string; value: number }[];
  recent_contracts: Contract[];
  referral_tasks: {
    id: string;
    contract_id: string;
    suggestion_id: string;
    target_department: string;
    question: string;
    due_at: string;
    contract_no: string;
    contract_name: string;
    suggestion_title: string;
    risk_level: string;
  }[];
};
type Bootstrap = {
  profile: User;
  dashboard: Dashboard;
  contracts: Contract[];
  users: User[];
};
type Report = {
  kpis: {
    contracts: number;
    amount: number;
    high_risk: number;
    resolved_suggestions: number;
  };
  risk_categories: { label: string; value: number }[];
  customer_warnings: { customer: string; count: number; level: string }[];
  ledger: Record<string, unknown>[];
};
type Knowledge = {
  id: string;
  entry_type: string;
  title: string;
  category: string;
  content: string;
  source: string;
  tags: string[];
  risk_level: string;
  is_standard_clause?: boolean;
  contract_type?: string;
  clause_no?: string;
  baseline_name?: string;
  baseline_version?: string;
  source_file?: string;
  is_required?: boolean;
};
type ChangeRequest = {
  id: string;
  contract_id: string;
  contract_no: string;
  contract_name: string;
  request_text: string;
  original_requirement: string;
  new_requirement: string;
  generated_supplement: string;
  status: string;
  created_at: string;
};
type Audit = {
  id: string;
  actor_name: string;
  action: string;
  object_type: string;
  object_id: string;
  detail: Record<string, unknown>;
  ip_address: string;
  created_at: string;
};
type View =
  | "dashboard"
  | "contracts"
  | "review"
  | "approvals"
  | "changes"
  | "knowledge"
  | "reports"
  | "audit";
type LongTask = {
  kind:
    | "upload"
    | "review"
    | "preview"
    | "compare"
    | "download"
    | "change"
    | "approval"
    | "redraft";
  title: string;
  detail: string;
  steps: string[];
  startedAt: number;
};

const NAV: { id: View; label: string; hint: string }[] = [
  { id: "dashboard", label: "工作台", hint: "业务总览" },
  { id: "contracts", label: "合同台账", hint: "上传与检索" },
  { id: "review", label: "合同审核", hint: "五轮审核" },
  { id: "approvals", label: "审批中心", hint: "审批矩阵" },
  { id: "changes", label: "订改申请", hint: "补充协议" },
  { id: "knowledge", label: "知识库", hint: "规则与案例" },
  { id: "reports", label: "风险报告", hint: "统计分析" },
  { id: "audit", label: "审计日志", hint: "操作记录" },
];

function apiRoot() {
  if (process.env.NEXT_PUBLIC_API_BASE)
    return process.env.NEXT_PUBLIC_API_BASE.replace(/\/$/, "");
  return "/api";
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token = "",
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiRoot()}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail || message;
    } catch {
      /* empty */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function fmtMoney(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function fmtDate(value?: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function riskClass(value: string) {
  return value === "高"
    ? "danger"
    : value === "中"
      ? "warning"
      : value === "低"
        ? "success"
        : "neutral";
}

function isActionableFocusedRisk(item: FocusedCheckResult) {
  return (
    item.technical_status === "verified" &&
    ["UNMET", "PARTIAL", "NOT_MENTIONED"].includes(item.status)
  );
}

function StatusPill({
  value,
  risk = false,
}: {
  value: string;
  risk?: boolean;
}) {
  const cls = risk
    ? riskClass(value)
    : value.includes("完成") || value === "通过" || value === "已答复"
      ? "success"
      : value.includes("待") || value.includes("中")
        ? "warning"
        : "neutral";
  return (
    <span className={`pill ${cls}`}>
      <i />
      {value || "—"}
    </span>
  );
}

function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-mark">暂无数据</div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}

function Spinner() {
  return (
    <div className="spinner-wrap">
      <span className="spinner" />
      正在加载业务数据…
    </div>
  );
}

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function LongTaskStatus({
  task,
  elapsed,
  serviceOnline,
}: {
  task: LongTask;
  elapsed: number;
  serviceOnline: boolean;
}) {
  return (
    <aside
      className={`long-task-status ${task.kind}`}
      role="status"
      aria-live="polite"
      aria-label="后台任务处理状态"
    >
      <header>
        <span className="task-spinner" aria-hidden="true">
          <i />
        </span>
        <div>
          <small>任务处理中</small>
          <strong>{task.title}</strong>
        </div>
        <time>已等待 {formatElapsed(elapsed)}</time>
      </header>
      <p>{task.detail}</p>
      <div className="task-service">
        <span className={serviceOnline ? "online" : "waiting"}>
          <i />
          {serviceOnline ? "审核服务在线" : "服务暂时未响应，继续等待中"}
        </span>
        <b>页面可保持打开</b>
      </div>
      <div className="task-progress-track" aria-label="处理中">
        <i />
      </div>
      <div className="task-steps">
        <span>预计处理流程</span>
        <ol>
          {task.steps.map((step, index) => (
            <li key={step}>
              <b>{index + 1}</b>
              {step}
            </li>
          ))}
        </ol>
      </div>
      <footer>
        {elapsed >= 60
          ? "复杂合同可能需要数分钟，当前任务仍在继续。"
          : "请勿重复提交；完成后页面会自动刷新。"}
      </footer>
    </aside>
  );
}

export default function ContractReviewApp() {
  const [token, setToken] = useState("");
  const [me, setMe] = useState<User | null>(null);
  const [demoUsers, setDemoUsers] = useState<User[]>([]);
  const [demoPassword, setDemoPassword] = useState("");
  const [view, setView] = useState<View>("dashboard");
  const [mobileNav, setMobileNav] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<{
    text: string;
    kind: "ok" | "error";
  } | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<ContractDetail | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [approvalRows, setApprovalRows] = useState<Approval[]>([]);
  const [changes, setChanges] = useState<ChangeRequest[]>([]);
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [loadedViews, setLoadedViews] = useState<
    Partial<Record<View, boolean>>
  >({});
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadCustomer, setUploadCustomer] = useState("");
  const [uploadProject, setUploadProject] = useState("");
  const [uploadContractId, setUploadContractId] = useState("");
  const [uploadRoundNo, setUploadRoundNo] = useState(1);
  const [uploadContractType, setUploadContractType] = useState<"采购" | "租赁">(
    "采购",
  );
  const [uploadOurRole, setUploadOurRole] = useState<"采购方" | "供应方" | "出租方" | "承租方">("采购方");
  const [uploadDocumentComplete, setUploadDocumentComplete] = useState(true);
  const [uploadLegalAsOfDate, setUploadLegalAsOfDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [uploadSource, setUploadSource] = useState("客户");
  const [uploadDepartment, setUploadDepartment] = useState("");
  const [workTab, setWorkTab] = useState<
    "checks" | "risks" | "versions" | "collaboration" | "approval"
  >("risks");
  const [changeText, setChangeText] = useState("");
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [compareResult, setCompareResult] = useState<{
    summary: string;
    changes: { type: string; text: string }[];
  } | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [previewFileUrl, setPreviewFileUrl] = useState("");
  const [longTask, setLongTask] = useState<LongTask | null>(null);
  const [taskElapsed, setTaskElapsed] = useState(0);
  const [serviceOnline, setServiceOnline] = useState(true);
  const taskActiveRef = useRef(false);
  const taskStartedAtRef = useRef(0);
  const taskFinishTimerRef = useRef<number | null>(null);

  const toast = useCallback((text: string, kind: "ok" | "error" = "ok") => {
    setNotice({ text, kind });
    window.setTimeout(() => setNotice(null), 3600);
  }, []);

  const applyBootstrap = useCallback((data: Bootstrap) => {
    setMe(data.profile);
    setDashboard(data.dashboard);
    setContracts(data.contracts);
    setUsers(data.users);
    setLoadedViews((current) => ({
      ...current,
      dashboard: true,
      contracts: true,
    }));
    setSelectedId((current) => current || data.contracts[0]?.id || "");
  }, []);

  const loadCore = useCallback(
    async (authToken: string) => {
      setLoading(true);
      try {
        applyBootstrap(await request<Bootstrap>("/bootstrap", {}, authToken));
      } catch (error) {
        localStorage.removeItem("contract-token");
        setToken("");
        setMe(null);
        toast(
          error instanceof Error ? error.message : "登录状态已失效",
          "error",
        );
      } finally {
        setLoading(false);
      }
    },
    [applyBootstrap, toast],
  );

  useEffect(() => {
    request<{ users: User[]; password?: string }>("/auth/demo-users")
      .then((data) => {
        setDemoUsers(data.users);
        setDemoPassword(data.password || "");
      })
      .catch(() => {
        setDemoUsers([]);
        setDemoPassword("");
      });
    const saved = localStorage.getItem("contract-token") || "";
    if (saved)
      queueMicrotask(() => {
        setToken(saved);
        void loadCore(saved);
      });
  }, [loadCore]);

  useEffect(
    () => () => {
      if (previewFileUrl) URL.revokeObjectURL(previewFileUrl);
    },
    [previewFileUrl],
  );
  useEffect(
    () => () => {
      if (taskFinishTimerRef.current)
        window.clearTimeout(taskFinishTimerRef.current);
    },
    [],
  );

  useEffect(() => {
    if (!longTask) return;
    const updateElapsed = () =>
      setTaskElapsed(
        Math.max(0, Math.floor((Date.now() - longTask.startedAt) / 1000)),
      );
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [longTask]);

  useEffect(() => {
    if (!longTask) return;
    let cancelled = false;
    let controller: AbortController | null = null;
    const pollHealth = async () => {
      controller?.abort();
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller?.abort(), 4000);
      try {
        const response = await fetch(`${apiRoot()}/health`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!cancelled) setServiceOnline(response.ok);
      } catch {
        if (!cancelled) setServiceOnline(false);
      } finally {
        window.clearTimeout(timeout);
      }
    };
    void pollHealth();
    const timer = window.setInterval(() => void pollHealth(), 8000);
    return () => {
      cancelled = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, [longTask]);

  function beginLongTask(task: Omit<LongTask, "startedAt">) {
    if (taskActiveRef.current) {
      toast("已有任务正在处理，请等待完成后再操作", "error");
      return false;
    }
    taskActiveRef.current = true;
    taskStartedAtRef.current = Date.now();
    setTaskElapsed(0);
    setServiceOnline(true);
    setLongTask({ ...task, startedAt: taskStartedAtRef.current });
    return true;
  }

  function finishLongTask() {
    const finish = () => {
      taskFinishTimerRef.current = null;
      taskActiveRef.current = false;
      setLongTask(null);
      setTaskElapsed(0);
    };
    const remaining = Math.max(
      0,
      1200 - (Date.now() - taskStartedAtRef.current),
    );
    if (remaining)
      taskFinishTimerRef.current = window.setTimeout(finish, remaining);
    else finish();
  }

  const loadDetail = useCallback(
    async (id: string) => {
      if (!id || !token) return;
      try {
        setDetail(await request<ContractDetail>(`/contracts/${id}`, {}, token));
      } catch (error) {
        toast(error instanceof Error ? error.message : "合同加载失败", "error");
      }
    },
    [token, toast],
  );

  useEffect(() => {
    if (!selectedId || !token) return;
    const timer = window.setTimeout(() => void loadDetail(selectedId), 0);
    return () => window.clearTimeout(timer);
  }, [selectedId, token, loadDetail]);

  const navigate = async (next: View) => {
    setView(next);
    setMobileNav(false);
    if (!token || loadedViews[next] || next === "review") return;
    try {
      if (next === "dashboard")
        setDashboard(await request<Dashboard>("/dashboard", {}, token));
      if (next === "contracts")
        setContracts(await request<Contract[]>("/contracts", {}, token));
      if (next === "approvals")
        setApprovalRows(await request<Approval[]>("/approvals", {}, token));
      if (next === "changes")
        setChanges(
          await request<ChangeRequest[]>("/change-requests", {}, token),
        );
      if (next === "knowledge")
        setKnowledge(await request<Knowledge[]>("/knowledge", {}, token));
      if (next === "reports")
        setReport(await request<Report>("/reports/overview", {}, token));
      if (next === "audit")
        setAudits(await request<Audit[]>("/audit-logs", {}, token));
      setLoadedViews((current) => ({ ...current, [next]: true }));
    } catch (error) {
      toast(error instanceof Error ? error.message : "模块加载失败", "error");
    }
  };

  async function login(username: string, password: string) {
    setLoading(true);
    try {
      const data = await request<{
        access_token: string;
        user: User;
        bootstrap: Bootstrap;
      }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      localStorage.setItem("contract-token", data.access_token);
      setToken(data.access_token);
      applyBootstrap(data.bootstrap);
    } catch (error) {
      toast(error instanceof Error ? error.message : "登录失败", "error");
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("contract-token");
    setToken("");
    setMe(null);
    setDetail(null);
    setLoadedViews({});
    setView("dashboard");
  }

  function openUpload(contractId = "") {
    if (taskActiveRef.current)
      return toast("当前任务仍在处理，请稍后再上传", "error");
    const target = contracts.find((item) => item.id === contractId);
    const currentContract =
      detail?.contract.id === contractId ? detail.contract : target;
    setUploadContractId(contractId);
    setUploadRoundNo(
      contractId ? Math.min(5, (currentContract?.current_round || 0) + 1) : 1,
    );
    setUploadContractType(target?.contract_type === "租赁" ? "租赁" : "采购");
    setUploadOurRole(
      (target?.our_role as "采购方" | "供应方" | "出租方" | "承租方") ||
        (target?.contract_type === "租赁" ? "出租方" : "采购方"),
    );
    setUploadDocumentComplete(target?.document_complete ?? true);
    setUploadLegalAsOfDate(
      target?.legal_as_of_date || new Date().toISOString().slice(0, 10),
    );
    setUploadCustomer(target?.customer || "");
    setUploadProject(target?.project || "");
    setUploadFiles([]);
    setUploadOpen(true);
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!uploadFiles.length) return toast("请先选择合同文件", "error");
    if (
      !beginLongTask({
        kind: "upload",
        title: uploadContractId
          ? `正在上传并解析第 ${uploadRoundNo} 轮合同`
          : "正在导入合同文件",
        detail:
          "系统正在保存文件、解析正文，并识别原文件中的批注作者与修订来源。",
        steps: [
          "上传文件并校验",
          "解析正文与表格",
          "识别批注和修订",
          "更新合同台账",
        ],
      })
    )
      return;
    const form = new FormData();
    uploadFiles.forEach((file) => form.append("files", file));
    form.append("customer", uploadCustomer);
    form.append("project", uploadProject);
    form.append("contract_type", uploadContractType);
    form.append("our_role", uploadOurRole);
    form.append("document_complete", String(uploadDocumentComplete));
    form.append("legal_as_of_date", uploadLegalAsOfDate);
    form.append("document_source", uploadSource);
    form.append("source_department", uploadDepartment);
    if (uploadContractId) {
      form.append("contract_id", uploadContractId);
      form.append("review_round", String(uploadRoundNo));
    }
    setLoading(true);
    try {
      const result = await request<{ contract: Contract }[]>(
        "/contracts/upload",
        { method: "POST", body: form },
        token,
      );
      setContracts((current) => {
        const uploaded = result.map((item) => item.contract);
        const ids = new Set(uploaded.map((item) => item.id));
        return [...uploaded, ...current.filter((item) => !ids.has(item.id))];
      });
      setLoadedViews((current) => ({
        ...current,
        reports: false,
        audit: false,
      }));
      setUploadOpen(false);
      setUploadFiles([]);
      setUploadContractId("");
      setUploadRoundNo(1);
      setSelectedId(result[0].contract.id);
      setView("review");
      await loadDetail(result[0].contract.id);
      toast(
        uploadContractId
          ? `第 ${(result[0] as { review_round_no?: number }).review_round_no || "下一"} 轮合同已上传，可启动审核`
          : `已创建 ${result.length} 份${uploadContractType}合同`,
      );
    } catch (error) {
      toast(error instanceof Error ? error.message : "上传失败", "error");
    } finally {
      setLoading(false);
      finishLongTask();
    }
  }

  async function runReview() {
    if (!selectedId) return;
    const roundNo = Math.min(5, (detail?.contract.current_round || 0) + 1);
    if (
      !beginLongTask({
        kind: "review",
        title: `正在执行第 ${roundNo} 轮合同审核`,
        detail:
          "规则库、知识库和大模型将依次检查，并在原文件中回写青蓝色高亮与审核批注。",
        steps: [
          "读取本轮合同",
          "规则库与知识库检查",
          "大模型补充分析",
          "生成高亮批注版",
          "刷新审核结果",
        ],
      })
    )
      return;
    setLoading(true);
    try {
      const data = await request<{
        round_no: number;
        summary: string;
        generated_version_no?: number;
        applied_suggestions?: number;
      }>(`/contracts/${selectedId}/review`, { method: "POST" }, token);
      await loadDetail(selectedId);
      setLoadedViews((current) => ({
        ...current,
        dashboard: false,
        contracts: false,
        reports: false,
        audit: false,
      }));
      toast(`第 ${data.round_no} 轮审核完成：${data.summary}`);
    } catch (error) {
      toast(error instanceof Error ? error.message : "审核启动失败", "error");
    } finally {
      setLoading(false);
      finishLongTask();
    }
  }

  async function decideSuggestion(
    item: Suggestion,
    decision: string,
    note = "",
  ) {
    try {
      const updated = await request<
        Pick<
          Suggestion,
          | "id"
          | "decision"
          | "decision_note"
          | "suggested_text"
          | "latest_instruction"
          | "revision_history"
        >
      >(
        `/suggestions/${item.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            decision,
            suggested_text: item.suggested_text,
            note,
          }),
        },
        token,
      );
      setDetail((current) =>
        current
          ? {
              ...current,
              review_runs: current.review_runs.map((run) => ({
                ...run,
                suggestions: run.suggestions.map((suggestion) =>
                  suggestion.id === updated.id
                    ? { ...suggestion, ...updated }
                    : suggestion,
                ),
              })),
            }
          : current,
      );
      setLoadedViews((current) => ({
        ...current,
        reports: false,
        audit: false,
      }));
      toast(
        decision === "拒绝"
          ? "已拒绝该审核建议；下一轮将继承人工放行结论"
          : `已${decision}该审核建议；下一轮将按修改后文本审核`,
      );
      return true;
    } catch (error) {
      toast(error instanceof Error ? error.message : "处理失败", "error");
      return false;
    }
  }

  async function redraftSuggestion(item: Suggestion, instruction: string) {
    if (!instruction.trim()) {
      toast("请输入本次希望调整的方向", "error");
      return false;
    }
    if (
      !beginLongTask({
        kind: "redraft",
        title: `正在生成第 ${(item.revision_history?.length || 1) + 1} 稿替换条款`,
        detail:
          "大模型正在结合风险原文、当前稿和你的自然语言要求，重新起草可直接写入合同的完整条款。",
        steps: [
          "理解本次修改要求",
          "保留未要求改变的条件",
          "生成完整合同条款",
          "保存改稿历史",
        ],
      })
    )
      return false;
    try {
      const updated = await request<
        Pick<
          Suggestion,
          "id" | "suggested_text" | "latest_instruction" | "revision_history"
        > & { draft_version: number }
      >(
        `/suggestions/${item.id}/redraft`,
        {
          method: "POST",
          body: JSON.stringify({ instruction: instruction.trim() }),
        },
        token,
      );
      setDetail((current) =>
        current
          ? {
              ...current,
              review_runs: current.review_runs.map((run) => ({
                ...run,
                suggestions: run.suggestions.map((suggestion) =>
                  suggestion.id === updated.id
                    ? { ...suggestion, ...updated }
                    : suggestion,
                ),
              })),
            }
          : current,
      );
      setLoadedViews((current) => ({ ...current, audit: false }));
      toast(
        `第 ${updated.draft_version} 稿完整替换条款已生成，可继续提意见或接纳当前稿`,
      );
      return true;
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "条款重新生成失败",
        "error",
      );
      return false;
    } finally {
      finishLongTask();
    }
  }

  async function prepareApprovals() {
    if (!selectedId) return;
    if (
      !beginLongTask({
        kind: "approval",
        title: "正在生成审批矩阵",
        detail:
          "系统正在汇总未解决风险，并按金额、业务线和角色配置生成审批节点。",
        steps: ["汇总审核结论", "匹配审批规则", "生成审批任务"],
      })
    )
      return;
    try {
      const approvals = await request<Approval[]>(
        `/contracts/${selectedId}/approvals/prepare`,
        { method: "POST" },
        token,
      );
      setDetail((current) => (current ? { ...current, approvals } : current));
      setLoadedViews((current) => ({
        ...current,
        approvals: false,
        audit: false,
      }));
      toast("已按金额/合同类型生成审批矩阵，并形成 K2 草稿号");
    } catch (error) {
      toast(error instanceof Error ? error.message : "审批单生成失败", "error");
    } finally {
      finishLongTask();
    }
  }

  async function compareVersions() {
    if (!detail || detail.versions.length < 2)
      return toast("至少需要两个版本才能比对", "error");
    const [left, right] = detail.versions.slice(-2);
    if (
      !beginLongTask({
        kind: "compare",
        title: "正在比对最近两个合同版本",
        detail: "系统正在解析两个独立文件并定位新增、删除及修改的条款。",
        steps: ["读取两个版本", "对齐条款结构", "生成差异摘要"],
      })
    )
      return;
    try {
      setCompareResult(
        await request(
          `/contracts/${selectedId}/versions/compare?left=${left.id}&right=${right.id}`,
          {},
          token,
        ),
      );
    } catch (error) {
      toast(error instanceof Error ? error.message : "版本比对失败", "error");
    } finally {
      finishLongTask();
    }
  }

  async function download(path: string, fileName: string) {
    if (
      !beginLongTask({
        kind: "download",
        title: "正在准备合同文件",
        detail: "系统正在生成或读取目标文件，浏览器会在完成后自动开始下载。",
        steps: ["读取合同版本", "整理批注与格式", "准备浏览器下载"],
      })
    )
      return;
    try {
      const response = await fetch(`${apiRoot()}${path}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("文件生成或下载失败");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = fileName;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast(error instanceof Error ? error.message : "下载失败", "error");
    } finally {
      finishLongTask();
    }
  }

  async function openPreview(version: Version) {
    if (
      !beginLongTask({
        kind: "preview",
        title: `正在准备第 ${version.review_round_no} 轮合同预览`,
        detail:
          "系统正在读取原文件与本轮审核批注；PDF 会保持为可缩放的原生文档预览。",
        steps: ["读取合同文件", "合并原批注与 AI 意见", "打开在线预览"],
      })
    )
      return;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewData(null);
    setPreviewFileUrl("");
    try {
      const data = await request<PreviewData>(
        `/contracts/${selectedId}/versions/${version.id}/preview`,
        {},
        token,
      );
      let fileUrl = "";
      if (data.format === "pdf") {
        const response = await fetch(`${apiRoot()}${data.file_endpoint}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("无法读取 PDF 预览文件");
        fileUrl = URL.createObjectURL(await response.blob());
      }
      setPreviewData(data);
      setPreviewFileUrl(fileUrl);
    } catch (error) {
      setPreviewOpen(false);
      toast(error instanceof Error ? error.message : "合同预览失败", "error");
    } finally {
      setPreviewLoading(false);
      finishLongTask();
    }
  }

  function closePreview() {
    setPreviewOpen(false);
    setPreviewData(null);
    setPreviewFileUrl("");
  }

  async function createChange(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !changeText.trim())
      return toast("请选择合同并输入客户新要求", "error");
    if (
      !beginLongTask({
        kind: "change",
        title: "正在生成订改申请",
        detail:
          "系统正在理解客户新要求、定位原合同约定并生成可编辑的补充协议草案。",
        steps: ["解析客户新要求", "定位原合同条款", "生成补充协议草案"],
      })
    )
      return;
    try {
      const created = await request<ChangeRequest>(
        "/change-requests",
        {
          method: "POST",
          body: JSON.stringify({
            contract_id: selectedId,
            request_text: changeText,
          }),
        },
        token,
      );
      setChangeText("");
      setChanges((current) => [created, ...current]);
      setLoadedViews((current) => ({
        ...current,
        changes: true,
        audit: false,
      }));
      toast("已抽取新旧需求并生成补充协议草案");
    } catch (error) {
      toast(error instanceof Error ? error.message : "生成失败", "error");
    } finally {
      finishLongTask();
    }
  }

  const filteredContracts = useMemo(
    () =>
      contracts.filter((item) =>
        `${item.contract_no}${item.name}${item.customer}${item.project}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [contracts, search],
  );
  const activeTitle = NAV.find((item) => item.id === view)?.label || "工作台";

  if (!me)
    return (
      <LoginScreen
        users={demoUsers}
        demoPassword={demoPassword}
        loading={loading}
        onLogin={login}
      />
    );

  return (
    <div className="app-shell">
      {notice && (
        <div className={`toast ${notice.kind}`}>
          {notice.kind === "ok" ? "✓" : "!"}
          <span>{notice.text}</span>
        </div>
      )}
      {longTask && (
        <LongTaskStatus
          task={longTask}
          elapsed={taskElapsed}
          serviceOnline={serviceOnline}
        />
      )}
      <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">契</div>
          <div>
            <strong>契析</strong>
            <span>合同审核管理平台</span>
          </div>
        </div>
        <div className="sidebar-section">业务导航</div>
        <nav>
          {NAV.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "active" : ""}
              onClick={() => void navigate(item.id)}
            >
              <b aria-hidden="true" />
              <span>
                {item.label}
                <small>{item.hint}</small>
              </span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="gateway">
            <i />
            <span>
              <strong>审核服务</strong>
              <small>运行正常</small>
            </span>
          </div>
          <div className="user-mini">
            <span className="avatar">{me.name.slice(0, 1)}</span>
            <div>
              <strong>{me.name}</strong>
              <small>
                {me.department} · {me.role}
              </small>
            </div>
            <button onClick={logout} title="退出登录">
              退出
            </button>
          </div>
        </div>
      </aside>
      {mobileNav && (
        <button
          className="scrim"
          onClick={() => setMobileNav(false)}
          aria-label="关闭菜单"
        />
      )}
      <main className="main">
        <header className="topbar">
          <button className="menu" onClick={() => setMobileNav(true)}>
            菜单
          </button>
          <div>
            <span>合同管理 /</span>
            <strong>{activeTitle}</strong>
          </div>
          <div className="top-actions">
            <button
              className="top-link"
              onClick={() => void navigate("contracts")}
            >
              合同检索
            </button>
            <button
              className="top-link notification"
              onClick={() => void navigate("approvals")}
            >
              待办事项
              <i />
            </button>
            <span className="top-avatar">{me.name.slice(0, 1)}</span>
          </div>
        </header>
        <div className="content">
          {loading && <div className="loading-line" />}
          {view === "dashboard" && (
            <DashboardView
              data={dashboard}
              onOpen={(id) => {
                setSelectedId(id);
                setView("review");
              }}
              onUpload={() => openUpload()}
              onNavigate={navigate}
            />
          )}
          {view === "contracts" && (
            <ContractsView
              contracts={filteredContracts}
              search={search}
              setSearch={setSearch}
              onUpload={() => openUpload()}
              onOpen={(id) => {
                setSelectedId(id);
                setView("review");
              }}
            />
          )}
          {view === "review" && (
            <ReviewView
              detail={detail}
              contracts={contracts}
              selectedId={selectedId}
              setSelectedId={setSelectedId}
              setDetail={setDetail}
              tab={workTab}
              setTab={setWorkTab}
              users={users}
              me={me}
              busy={Boolean(longTask)}
              onUploadNext={() => openUpload(selectedId)}
              onReview={runReview}
              onDecision={decideSuggestion}
              onRedraft={redraftSuggestion}
              onCompare={compareVersions}
              onDownload={download}
              onPreview={openPreview}
              onPrepare={prepareApprovals}
              token={token}
              toast={toast}
              invalidate={(...views) =>
                setLoadedViews((current) => ({
                  ...current,
                  ...Object.fromEntries(views.map((item) => [item, false])),
                }))
              }
            />
          )}
          {view === "approvals" && (
            <ApprovalsView
              rows={approvalRows}
              setRows={setApprovalRows}
              token={token}
              me={me}
              toast={toast}
              invalidate={() =>
                setLoadedViews((current) => ({
                  ...current,
                  dashboard: false,
                  contracts: false,
                  audit: false,
                }))
              }
              onOpen={(id) => {
                setSelectedId(id);
                setView("review");
                setWorkTab("approval");
              }}
            />
          )}
          {view === "changes" && (
            <ChangesView
              rows={changes}
              contracts={contracts}
              selectedId={selectedId}
              setSelectedId={setSelectedId}
              text={changeText}
              setText={setChangeText}
              busy={Boolean(longTask)}
              onSubmit={createChange}
            />
          )}
          {view === "knowledge" && (
            <KnowledgeView
              rows={knowledge}
              query={knowledgeQuery}
              setQuery={setKnowledgeQuery}
              onSearch={async () => {
                try {
                  setKnowledge(
                    await request<Knowledge[]>(
                      `/knowledge?q=${encodeURIComponent(knowledgeQuery)}`,
                      {},
                      token,
                    ),
                  );
                } catch (error) {
                  toast(
                    error instanceof Error ? error.message : "检索失败",
                    "error",
                  );
                }
              }}
            />
          )}
          {view === "reports" && <ReportsView data={report} />}
          {view === "audit" && <AuditView rows={audits} />}
        </div>
      </main>
      {uploadOpen && (
        <UploadModal
          files={uploadFiles}
          setFiles={setUploadFiles}
          customer={uploadCustomer}
          setCustomer={setUploadCustomer}
          project={uploadProject}
          setProject={setUploadProject}
          contractId={uploadContractId}
          contractType={uploadContractType}
          setContractType={setUploadContractType}
          ourRole={uploadOurRole}
          setOurRole={setUploadOurRole}
          documentComplete={uploadDocumentComplete}
          setDocumentComplete={setUploadDocumentComplete}
          legalAsOfDate={uploadLegalAsOfDate}
          setLegalAsOfDate={setUploadLegalAsOfDate}
          documentSource={uploadSource}
          setDocumentSource={setUploadSource}
          sourceDepartment={uploadDepartment}
          setSourceDepartment={setUploadDepartment}
          roundNo={uploadRoundNo}
          busy={Boolean(longTask)}
          onClose={() => setUploadOpen(false)}
          onSubmit={upload}
        />
      )}
      {compareResult && (
        <CompareModal
          data={compareResult}
          onClose={() => setCompareResult(null)}
        />
      )}
      {previewOpen && (
        <ContractPreviewModal
          data={previewData}
          fileUrl={previewFileUrl}
          loading={previewLoading}
          onClose={closePreview}
        />
      )}
    </div>
  );
}

function LoginScreen({
  users,
  demoPassword,
  loading,
  onLogin,
}: {
  users: User[];
  demoPassword: string;
  loading: boolean;
  onLogin: (username: string, password: string) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (username.trim() && password) onLogin(username.trim(), password);
  }

  return (
    <main className="login-page">
      <section className="login-story">
        <div className="login-brand">
          <span>契</span>
          <div>
            <strong>契析</strong>
            <small>合同审核管理平台</small>
          </div>
        </div>
        <div className="story-copy">
          <p className="eyebrow light">合同审核管理</p>
          <h1>统一管理合同审核与审批</h1>
          <p>集中处理合同台账、风险审核、版本协同、审批流转和归档记录。</p>
        </div>
        <div className="story-stats">
          <div>
            <strong>统一台账</strong>
            <span>合同与版本集中管理</span>
          </div>
          <div>
            <strong>过程可查</strong>
            <span>五轮审核与处置留痕</span>
          </div>
          <div>
            <strong>审批衔接</strong>
            <span>按角色生成审批任务</span>
          </div>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-box">
          <p className="eyebrow">合同审核管理平台</p>
          <h2>账号登录</h2>
          <p className="muted">请使用管理员分配的账号和密码登录。</p>
          <form className="login-form" onSubmit={submit}>
            <label>
              用户名
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="请输入用户名"
                required
              />
            </label>
            <label>
              密码
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="请输入密码"
                required
              />
            </label>
            <button className="primary" type="submit" disabled={loading}>
              {loading ? "正在登录…" : "登录"}
            </button>
          </form>
          {demoPassword && users.length > 0 && (
            <>
              <div className="login-divider"><span>演示角色快捷登录</span></div>
              <div className="role-grid">
                {users.map((user) => (
                  <button
                    key={user.id}
                    onClick={() => onLogin(user.username, demoPassword)}
                    disabled={loading}
                  >
                    <span className="role-avatar">{user.name.slice(0, 1)}</span>
                    <span>
                      <strong>{user.role}</strong>
                      <small>{user.name} · {user.department}</small>
                    </span>
                    <b>进入</b>
                  </button>
                ))}
              </div>
            </>
          )}
          {!users.length && (
            <div className="login-wait">
              {loading
                ? "正在连接合同审核服务…"
                : "后端暂未连接，请先启动 API 服务。"}
            </div>
          )}
          <div className="login-security">
            登录和业务操作将写入审计日志
          </div>
        </div>
      </section>
    </main>
  );
}

function PageHead({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow: string;
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
      {action}
    </div>
  );
}

function DashboardView({
  data,
  onOpen,
  onUpload,
  onNavigate,
}: {
  data: Dashboard | null;
  onOpen: (id: string) => void;
  onUpload: () => void;
  onNavigate: (view: View) => void;
}) {
  if (!data) return <Spinner />;
  const cards = [
    {
      label: "合同总数",
      value: data.totals.contracts,
      sub: "已纳入统一台账",
      icon: "合同",
      tone: "blue",
    },
    {
      label: "高风险合同",
      value: data.totals.high_risk,
      sub: "需优先完成处置",
      icon: "风险",
      tone: "red",
    },
    {
      label: "待审批任务",
      value: data.totals.pending,
      sub: "来自审批矩阵",
      icon: "审批",
      tone: "amber",
    },
    {
      label: "我的待审核",
      value: data.totals.consultations,
      sub: "条款转批与询问",
      icon: "协同",
      tone: "green",
    },
  ];
  const max = Math.max(...data.by_status.map((i) => i.value), 1);
  return (
    <>
      <PageHead
        eyebrow="工作台"
        title="合同审核工作台"
        text="查看合同风险、协同事项与审批进度。"
        action={
          <button className="primary" onClick={onUpload}>
            上传合同
          </button>
        }
      />
      <div className="kpi-grid">
        {cards.map((card) => (
          <article className="kpi" key={card.label}>
            <div className={`kpi-icon ${card.tone}`}>{card.icon}</div>
            <div>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <small>{card.sub}</small>
            </div>
          </article>
        ))}
      </div>
      {!!data.referral_tasks?.length && (
        <section className="panel referral-inbox">
          <div className="panel-head">
            <div>
              <h2>转批给我的风险建议</h2>
              <p>打开合同后，可直接在对应风险卡片中提交审核结论</p>
            </div>
            <strong>{data.referral_tasks.length} 项待审核</strong>
          </div>
          <div>
            {data.referral_tasks.map((task) => (
              <button key={task.id} onClick={() => onOpen(task.contract_id)}>
                <StatusPill value={task.risk_level} risk />
                <span>
                  <strong>{task.suggestion_title}</strong>
                  <small>
                    {task.contract_no} · {task.contract_name}
                  </small>
                </span>
                <time>截止 {fmtDate(task.due_at)}</time>
                <b>进入审核 ›</b>
              </button>
            ))}
          </div>
        </section>
      )}
      <div className="dashboard-grid">
        <section className="panel recent-panel">
          <div className="panel-head">
            <div>
              <h2>最近处理的合同</h2>
              <p>按最后更新时间排序</p>
            </div>
            <button
              className="text-btn"
              onClick={() => void onNavigate("contracts")}
            >
              查看全部 →
            </button>
          </div>
          <div className="contract-list">
            {data.recent_contracts.map((item) => (
              <button key={item.id} onClick={() => onOpen(item.id)}>
                <span className="doc-symbol">
                  {item.contract_type.slice(0, 1)}
                </span>
                <span className="contract-main">
                  <strong>{item.name}</strong>
                  <small>
                    {item.contract_no} · {item.customer}
                  </small>
                </span>
                <StatusPill value={item.risk_level} risk />
                <span className="round">R{item.current_round}</span>
                <time>{fmtDate(item.updated_at)}</time>
                <b>›</b>
              </button>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>流程状态分布</h2>
              <p>当前合同处理进度</p>
            </div>
          </div>
          <div className="status-bars">
            {data.by_status.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <div>
                  <i
                    style={{
                      width: `${Math.max(8, (item.value / max) * 100)}%`,
                    }}
                  />
                </div>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
          <button
            className="wide-secondary"
            onClick={() => void onNavigate("reports")}
          >
            打开完整风险报告
          </button>
        </section>
      </div>
      <section className="quick-row">
        <button onClick={() => void onNavigate("review")}>
          <span>01</span>
          <div>
            <strong>继续合同审核</strong>
            <small>处理风险建议与版本偏离</small>
          </div>
          <b>进入</b>
        </button>
        <button onClick={() => void onNavigate("approvals")}>
          <span>02</span>
          <div>
            <strong>审批与复核</strong>
            <small>查看矩阵任务及未解决风险</small>
          </div>
          <b>进入</b>
        </button>
        <button onClick={() => void onNavigate("changes")}>
          <span>03</span>
          <div>
            <strong>生成订改申请</strong>
            <small>根据业务要求生成补充协议草案</small>
          </div>
          <b>进入</b>
        </button>
      </section>
    </>
  );
}

function ContractsView({
  contracts,
  search,
  setSearch,
  onUpload,
  onOpen,
}: {
  contracts: Contract[];
  search: string;
  setSearch: (v: string) => void;
  onUpload: () => void;
  onOpen: (id: string) => void;
}) {
  return (
    <>
      <PageHead
        eyebrow="合同管理"
        title="采购 / 租赁合同台账"
        text="采购合同与租赁合同分轨管理，分别跟踪五轮版本、风险和批注来源。"
        action={
          <button className="primary" onClick={onUpload}>
            新建并上传
          </button>
        }
      />
      <section className="panel table-panel">
        <div className="toolbar">
          <label className="search">
            <span className="search-label">检索</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="合同编号、客户或项目"
            />
          </label>
          <div className="toolbar-meta">
            共 <strong>{contracts.length}</strong> 份合同 · 支持 DOCX / DOC /
            PDF / XLS(X) / 图片
          </div>
        </div>
        {contracts.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>合同信息</th>
                  <th>客户 / 项目</th>
                  <th>业务线</th>
                  <th>金额</th>
                  <th>风险</th>
                  <th>进度</th>
                  <th>轮次</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {contracts.map((item) => (
                  <tr key={item.id} onClick={() => onOpen(item.id)}>
                    <td>
                      <strong>{item.name}</strong>
                      <small>{item.contract_no}</small>
                    </td>
                    <td>
                      <strong>{item.customer}</strong>
                      <small>{item.project || "未关联项目"}</small>
                    </td>
                    <td>
                      <span className="type-tag">{item.contract_type}合同</span>
                    </td>
                    <td className="money">{fmtMoney(item.amount)}</td>
                    <td>
                      <StatusPill value={item.risk_level} risk />
                    </td>
                    <td>
                      <StatusPill value={item.status} />
                    </td>
                    <td>
                      R{item.current_round}/5 · {item.version_count} 版
                    </td>
                    <td>
                      <button className="row-open">查看</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="没有匹配的合同"
            text="调整搜索词，或上传一份新合同开始审核。"
            action={
              <button className="secondary" onClick={onUpload}>
                上传合同
              </button>
            }
          />
        )}
      </section>
    </>
  );
}

function ReviewView({
  detail,
  contracts,
  selectedId,
  setSelectedId,
  setDetail,
  tab,
  setTab,
  users,
  me,
  busy,
  onUploadNext,
  onReview,
  onDecision,
  onRedraft,
  onCompare,
  onDownload,
  onPreview,
  onPrepare,
  token,
  toast,
  invalidate,
}: {
  detail: ContractDetail | null;
  contracts: Contract[];
  selectedId: string;
  setSelectedId: (v: string) => void;
  setDetail: (
    updater: (current: ContractDetail | null) => ContractDetail | null,
  ) => void;
  tab: "checks" | "risks" | "versions" | "collaboration" | "approval";
  setTab: (v: "checks" | "risks" | "versions" | "collaboration" | "approval") => void;
  users: User[];
  me: User;
  busy: boolean;
  onUploadNext: () => void;
  onReview: () => void;
  onDecision: (
    item: Suggestion,
    decision: string,
    note?: string,
  ) => Promise<boolean>;
  onRedraft: (item: Suggestion, instruction: string) => Promise<boolean>;
  onCompare: () => void;
  onDownload: (path: string, name: string) => void;
  onPreview: (version: Version) => void;
  onPrepare: () => void;
  token: string;
  toast: (text: string, kind?: "ok" | "error") => void;
  invalidate: (...views: View[]) => void;
}) {
  const [consultUser, setConsultUser] = useState("");
  const [question, setQuestion] = useState("");
  const [feedback, setFeedback] = useState("");
  const [internalNote, setInternalNote] = useState("");
  const [utility, setUtility] = useState<{
    title: string;
    meta: string;
    content: string;
    alerts?: { level: string; title: string; detail: string }[];
  } | null>(null);
  if (!contracts.length)
    return <Empty title="尚无可审核合同" text="请先前往合同台账上传文件。" />;
  if (!detail) return <Spinner />;
  const contractNo = detail.contract.contract_no;
  const run = detail.review_runs[0];
  const focusedRisks =
    detail.focused_review?.results.filter(isActionableFocusedRisk) || [];
  const unresolved =
    (run?.suggestions.filter((i) => i.decision === "待处理").length || 0) +
    focusedRisks.filter(
      (item) => item.human_confirmation?.status !== "已确认",
    ).length;
  const nextRound = Math.min(5, detail.contract.current_round + 1);
  const pendingVersion = detail.versions.find(
    (item) => item.review_round_no === nextRound,
  );
  async function createConsultation(event: FormEvent) {
    event.preventDefault();
    if (!consultUser || !question) return;
    try {
      const created = await request<Consultation>(
        `/contracts/${selectedId}/consultations`,
        {
          method: "POST",
          body: JSON.stringify({
            assignee_id: consultUser,
            question,
            due_hours: 24,
          }),
        },
        token,
      );
      setQuestion("");
      setDetail((current) =>
        current
          ? { ...current, consultations: [created, ...current.consultations] }
          : current,
      );
      invalidate("dashboard", "audit");
      toast("已发起跨部门询问");
    } catch (error) {
      toast(error instanceof Error ? error.message : "发起失败", "error");
    }
  }
  async function addNegotiation(event: FormEvent) {
    event.preventDefault();
    if (!feedback) return;
    try {
      const created = await request<Negotiation>(
        `/contracts/${selectedId}/negotiations`,
        {
          method: "POST",
          body: JSON.stringify({
            status: "客户二次偏离",
            customer_feedback: feedback,
            internal_note: internalNote,
          }),
        },
        token,
      );
      setFeedback("");
      setInternalNote("");
      setDetail((current) =>
        current
          ? {
              ...current,
              negotiations: [created, ...current.negotiations],
              contract: { ...current.contract, status: "待修改" },
            }
          : current,
      );
      invalidate("dashboard", "contracts", "audit");
      toast("销售反馈已记录；内部备注不会进入客户版导出");
    } catch (error) {
      toast(error instanceof Error ? error.message : "记录失败", "error");
    }
  }
  async function assignReviewer(assigneeId: string) {
    if (!assigneeId) return;
    try {
      const updated = await request<{ assigned_to_id: string }>(
        `/contracts/${selectedId}/assign`,
        { method: "PATCH", body: JSON.stringify({ assignee_id: assigneeId }) },
        token,
      );
      setDetail((current) =>
        current
          ? {
              ...current,
              contract: {
                ...current.contract,
                assigned_to_id: updated.assigned_to_id,
              },
            }
          : current,
      );
      invalidate("contracts", "audit");
      toast("审核人分配已更新");
    } catch (error) {
      toast(error instanceof Error ? error.message : "分配失败", "error");
    }
  }
  async function checkConsistency() {
    try {
      const data = await request<{
        score: number;
        versions_checked: number;
        supplements_checked: number;
        alerts: { level: string; title: string; detail: string }[];
      }>(`/contracts/${selectedId}/consistency`, {}, token);
      setUtility({
        title: "签署 / 归档一致性检查",
        meta: `一致性 ${data.score} 分 · 核对 ${data.versions_checked} 个版本、${data.supplements_checked} 份补充协议`,
        content: data.alerts.length
          ? "发现以下待核对事项"
          : "未发现阻断签署或归档的一致性问题。",
        alerts: data.alerts,
      });
    } catch (error) {
      toast(error instanceof Error ? error.message : "一致性检查失败", "error");
    }
  }
  async function previewRedaction() {
    try {
      const data = await request<{
        counts: Record<string, number>;
        preview: string;
        truncated: boolean;
      }>(`/contracts/${selectedId}/redacted-preview`, {}, token);
      const total = Object.values(data.counts).reduce(
        (sum, count) => sum + count,
        0,
      );
      setUtility({
        title: "敏感信息脱敏预览",
        meta: `共处理 ${total} 处 · ${Object.entries(data.counts)
          .map(([key, value]) => `${key} ${value}`)
          .join(" / ")}`,
        content: data.preview + (data.truncated ? "\n\n……预览已截断" : ""),
      });
    } catch (error) {
      toast(error instanceof Error ? error.message : "脱敏预览失败", "error");
    }
  }
  async function queueEmail() {
    const recipient = window.prompt(
      "请输入审核结果收件邮箱",
      "legal@example.com",
    );
    if (!recipient) return;
    try {
      await request(
        `/contracts/${selectedId}/notifications`,
        {
          method: "POST",
          body: JSON.stringify({
            recipient,
            subject: `${contractNo} 合同审核结果`,
          }),
        },
        token,
      );
      toast("审核结果已加入邮件待发队列");
    } catch (error) {
      toast(error instanceof Error ? error.message : "通知创建失败", "error");
    }
  }
  async function correctCommentSource(item: DocumentComment) {
    const sourceKind =
      window.prompt(
        "确认来源类型：客户 / 同事 / 部门 / 未识别",
        item.source_kind,
      ) || "";
    if (!["客户", "同事", "部门", "未识别"].includes(sourceKind))
      return toast("来源类型不合法", "error");
    const sourceDepartment =
      sourceKind === "客户"
        ? "客户"
        : window.prompt("确认部门（可留空）", item.source_department || "") ||
          "";
    try {
      const updated = await request<Partial<DocumentComment> & { id: string }>(
        `/document-comments/${item.id}/source`,
        {
          method: "PATCH",
          body: JSON.stringify({
            source_kind: sourceKind,
            source_department: sourceDepartment,
            author_name: item.author_name,
          }),
        },
        token,
      );
      setDetail((current) =>
        current
          ? {
              ...current,
              document_comments: current.document_comments.map((row) =>
                row.id === item.id ? { ...row, ...updated } : row,
              ),
            }
          : current,
      );
      toast("批注来源已确认，并用于后续自动识别");
    } catch (error) {
      toast(error instanceof Error ? error.message : "来源确认失败", "error");
    }
  }
  async function refreshFocusedReview() {
    if (!run?.id) return;
    const refreshed = await request<FocusedReview>(
      `/review-runs/${run.id}/focused-checks`,
      {},
      token,
    );
    setDetail((current) =>
      current ? { ...current, focused_review: refreshed } : current,
    );
  }
  async function confirmFocusedCheck(item: FocusedCheckResult) {
    const comment = window.prompt(
      `确认 ${item.check_code} · ${item.check_name}\n请输入法务复核意见`,
      "已核对合同原文、证据和修改方案，同意按当前风险结论处理。",
    );
    if (!comment) return;
    try {
      await request(
        `/focused-check-results/${item.id}/confirm`,
        {
          method: "PATCH",
          body: JSON.stringify({ decision: "确认风险", comment }),
        },
        token,
      );
      await refreshFocusedReview();
      toast(`${item.check_code} 已完成人工确认`);
    } catch (error) {
      toast(error instanceof Error ? error.message : "人工确认失败", "error");
    }
  }
  async function confirmAllFocusedChecks() {
    if (!run?.id) return;
    const comment = window.prompt(
      "批量确认本轮全部待确认高风险 Check\n该操作会写入审计日志，请填写复核依据",
      "已逐项核对本轮高风险检查、原文证据和拟修改方案。",
    );
    if (!comment) return;
    try {
      const response = await request<{ confirmed_count: number }>(
        `/review-runs/${run.id}/confirm-high-risk`,
        {
          method: "POST",
          body: JSON.stringify({ decision: "确认风险", comment }),
        },
        token,
      );
      await refreshFocusedReview();
      toast(`已确认 ${response.confirmed_count} 项高风险 Check`);
    } catch (error) {
      toast(error instanceof Error ? error.message : "批量确认失败", "error");
    }
  }
  return (
    <>
      <div className="review-selector" aria-busy={busy}>
        <div className="selector-fields">
          <label>
            当前审核合同
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              disabled={busy}
            >
              {contracts.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.contract_no} · {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
              合同负责人 / 分配审核人
            <select
              value={detail.contract.assigned_to_id || ""}
              onChange={(e) => void assignReviewer(e.target.value)}
              disabled={busy}
            >
              <option value="">待分配</option>
              {users
                .filter((user) =>
                  ["法务审核", "合同管理员"].includes(user.role),
                )
                .map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.name} · {user.department}
                  </option>
                ))}
            </select>
          </label>
        </div>
        <div>
          {run?.annotated_available && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                onDownload(
                  `/contracts/${selectedId}/review-runs/${run.id}/annotated`,
                  run.annotated_file_name,
                )
              }
            >
              下载本轮原文件批注版
            </button>
          )}
          {detail.contract.current_round < 5 &&
            (!pendingVersion ? (
              <button
                className="primary"
                disabled={busy}
                onClick={onUploadNext}
              >
                {busy ? "处理中…" : `上传第 ${nextRound} 轮合同`}
              </button>
            ) : (
              <button className="primary" disabled={busy} onClick={onReview}>
                {busy
                  ? "处理中…"
                  : `审核第 ${nextRound} 轮 · ${pendingVersion.document_source}`}
              </button>
            ))}
        </div>
      </div>
      <section className="contract-hero">
        <div>
          <div className="hero-meta">
            <StatusPill value={detail.contract.risk_level} risk />
            <span>{detail.contract.contract_type}合同</span>
            <span>我方：{detail.contract.our_role}</span>
            <span>{detail.contract.template_type}</span>
            <span>第 {detail.contract.current_round}/5 轮</span>
          </div>
          <h1>{detail.contract.name}</h1>
          <p>
            {detail.contract.contract_no} · {detail.contract.customer} ·{" "}
            {detail.contract.project}
          </p>
        </div>
        <div
          className="score-ring"
          style={
            { "--score": `${run?.risk_score || 0}%` } as React.CSSProperties
          }
        >
          <div>
            <strong>{run?.risk_score || 0}</strong>
            <span>风险分</span>
          </div>
        </div>
        <div className="hero-facts">
          <div>
            <span>合同金额</span>
            <strong>{fmtMoney(detail.contract.amount)}</strong>
          </div>
          <div>
            <span>五轮累计意见</span>
            <strong>{detail.cumulative_review.total_opinions} 项</strong>
          </div>
          <div>
            <span>本轮待处置</span>
            <strong>{unresolved} 项</strong>
          </div>
        </div>
      </section>
      <div className="workspace-tabs">
        <button
          className={tab === "checks" ? "active" : ""}
          onClick={() => setTab("checks")}
        >
          全部专项检查 <i>{detail.focused_review?.results.length || 0}</i>
        </button>
        <button
          className={tab === "risks" ? "active" : ""}
          onClick={() => setTab("risks")}
        >
          风险审核 <i>{(run?.suggestions.length || 0) + focusedRisks.length}</i>
        </button>
        <button
          className={tab === "versions" ? "active" : ""}
          onClick={() => setTab("versions")}
        >
          版本对比 <i>{detail.versions.length}</i>
        </button>
        <button
          className={tab === "collaboration" ? "active" : ""}
          onClick={() => setTab("collaboration")}
        >
          协同谈判{" "}
          <i>{detail.consultations.length + detail.negotiations.length}</i>
        </button>
        <button
          className={tab === "approval" ? "active" : ""}
          onClick={() => setTab("approval")}
        >
          审批流 <i>{detail.approvals.length}</i>
        </button>
      </div>
      {tab === "checks" && (
        <FocusedChecksWorkspace
          data={detail.focused_review}
          busy={busy}
          onConfirm={confirmFocusedCheck}
          onConfirmAll={confirmAllFocusedChecks}
        />
      )}
      {tab === "risks" && (
        <RiskWorkspace
          run={run}
          focusedReview={detail.focused_review}
          contractId={selectedId}
          consultations={detail.consultations}
          users={users}
          me={me}
          token={token}
          busy={busy}
          onDecision={onDecision}
          onRedraft={onRedraft}
          onConfirmFocused={confirmFocusedCheck}
          onConsultationsChange={(updater) =>
            setDetail((current) =>
              current
                ? { ...current, consultations: updater(current.consultations) }
                : current,
            )
          }
          toast={toast}
          invalidate={invalidate}
        />
      )}
      {tab === "versions" && (
        <VersionsWorkspace
          detail={detail}
          selectedId={selectedId}
          onCompare={onCompare}
          onDownload={onDownload}
          onPreview={onPreview}
          onCorrectComment={correctCommentSource}
          onConsistency={checkConsistency}
          onRedaction={previewRedaction}
          onNotify={queueEmail}
          utility={utility}
          onCloseUtility={() => setUtility(null)}
        />
      )}
      {tab === "collaboration" && (
        <section className="two-col">
          <div className="panel padded">
            <div className="panel-head">
              <div>
                <h2>跨部门询问</h2>
                <p>向财务、业务或审批人咨询条款问题</p>
              </div>
            </div>
            <form className="stack-form" onSubmit={createConsultation}>
              <select
                value={consultUser}
                onChange={(e) => setConsultUser(e.target.value)}
                required
              >
                <option value="">选择被询问人</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name} · {user.department}
                  </option>
                ))}
              </select>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="例如：客户坚持 60 天账期，是否可结合授信额度放行？"
                required
              />
              <button className="primary">发起询问</button>
            </form>
            <div className="timeline">
              {detail.consultations.map((item) => (
                <div key={item.id}>
                  <i />
                  <div>
                    <strong>{item.question}</strong>
                    <p>{item.answer || "等待答复…"}</p>
                    <small>
                      <StatusPill value={item.status} /> · 截止{" "}
                      {fmtDate(item.due_at)}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="panel padded">
            <div className="panel-head">
              <div>
                <h2>销售谈判反馈</h2>
                <p>外部反馈与内部备注严格分层</p>
              </div>
            </div>
            <form className="stack-form" onSubmit={addNegotiation}>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="客户对修改建议的反馈（可进入对客文档）"
                required
              />
              <textarea
                className="internal-input"
                value={internalNote}
                onChange={(e) => setInternalNote(e.target.value)}
                placeholder="内部备注（不会进入对客输出）"
              />
              <button className="primary">记录本轮反馈</button>
            </form>
            <div className="timeline">
              {detail.negotiations.map((item) => (
                <div key={item.id}>
                  <i />
                  <div>
                    <strong>{item.status}</strong>
                    <p>{item.customer_feedback}</p>
                    {item.internal_note && (
                      <p className="internal-note">
                        内部：{item.internal_note}
                      </p>
                    )}
                    <small>{fmtDate(item.created_at)}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
      {tab === "approval" && (
        <section className="panel padded">
          <div className="panel-head">
            <div>
              <h2>审批矩阵与 K2 推送准备</h2>
              <p>按合同类型与金额自动匹配法务、财务和管理层</p>
            </div>
            <button className="primary" onClick={onPrepare}>
              生成 / 刷新审批单
            </button>
          </div>
          <div className="approval-flow">
            {detail.approvals.map((item, index) => (
              <div key={item.id}>
                <span>{index + 1}</span>
                <div>
                  <strong>{item.department}</strong>
                  <small>{item.external_flow_id || "尚未生成外部流程号"}</small>
                </div>
                <StatusPill value={item.status} />
                {index < detail.approvals.length - 1 && <b>→</b>}
              </div>
            ))}
          </div>
          {!detail.approvals.length && (
            <Empty
              title="尚未生成审批矩阵"
              text="完成风险建议处置后，可按合同金额和类型自动生成审批层级。"
            />
          )}
        </section>
      )}
    </>
  );
}

function FocusedChecksWorkspace({
  data,
  busy,
  onConfirm,
  onConfirmAll,
}: {
  data: FocusedReview | null;
  busy: boolean;
  onConfirm: (item: FocusedCheckResult) => void;
  onConfirmAll: () => void;
}) {
  const [statusFilter, setStatusFilter] = useState("全部");
  if (!data)
    return (
      <Empty
        title="本轮尚未生成 Focused Checks"
        text="启动审核后，系统会按合同类型和我方角色执行固定版本 Playbook。"
      />
    );
  const rows = data.results.filter(
    (item) => statusFilter === "全部" || item.status === statusFilter,
  );
  const pendingConfirmations = data.results.filter(
    (item) =>
      item.human_confirmation_required &&
      item.human_confirmation?.status !== "已确认",
  ).length;
  return (
    <section className="panel padded">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Playbook {data.playbook_version}</p>
          <h2>49 项完整专项检查矩阵</h2>
          <p>
            覆盖状态：{data.coverage_status} · MET {data.stats.MET || 0} · UNMET{" "}
            {data.stats.UNMET || 0} · PARTIAL {data.stats.PARTIAL || 0} · 未提及{" "}
            {data.stats.NOT_MENTIONED || 0}
          </p>
        </div>
        <button
          className="primary"
          disabled={busy || pendingConfirmations === 0}
          onClick={onConfirmAll}
        >
          {pendingConfirmations ? `确认 ${pendingConfirmations} 项高风险` : "高风险已确认"}
        </button>
      </div>
      <div className="filter-row">
        <div>
          {["全部", "MET", "UNMET", "PARTIAL", "NOT_MENTIONED"].map((item) => (
            <button
              key={item}
              className={statusFilter === item ? "active" : ""}
              onClick={() => setStatusFilter(item)}
            >
              {item}
            </button>
          ))}
        </div>
        <span>显示 {rows.length} 项 · 每项均保存检索轨迹</span>
      </div>
      <div className="review-risk-list">
        {rows.map((item) => (
          <article className={`risk-card ${riskClass(item.risk_level)}`} key={item.id}>
            <header>
              <div>
                <span className="risk-index">{item.check_code}</span>
                <StatusPill value={item.status} />
                <span className="category">{item.category}</span>
                {item.legal_rag_required && <span className="history-badge">需法律 RAG</span>}
              </div>
              <StatusPill value={item.risk_level} risk />
            </header>
            <h3>{item.check_name}</h3>
            <p>{item.reason}</p>
            <small>
              已满足 {item.satisfied_slots.length} 个槽位 · 缺失 {item.missing_slots.length} 个 ·
              置信度 {item.confidence}% · {item.decision_source}
            </small>
            {item.technical_status !== "verified" && (
              <p className="internal-note">
                技术状态：{item.technical_status}。不得据此认定条款未提及。
              </p>
            )}
            <details>
              <summary>查看 Evidence 与检索轨迹</summary>
              {item.evidence.length ? (
                item.evidence.map((evidence) => (
                  <div className="quote" key={evidence.id}>
                    <span>
                      {evidence.source_file || "当前合同"}
                      {evidence.page_no ? ` · 第 ${evidence.page_no} 页` : ""}
                      {evidence.clause_no
                        ? ` · ${/^\d+(?:\.\d+)*$/.test(evidence.clause_no) ? `第 ${evidence.clause_no} 条` : evidence.clause_no}`
                        : ""}
                      {evidence.page_method
                        ? ` · ${evidence.page_method === "rendered_pdf" || evidence.page_method === "pdf_text_layer"
                          ? "渲染页码"
                          : evidence.page_method === "word_rendered_break"
                            ? "Word分页标记"
                            : evidence.page_method === "ocr_page_marker"
                              ? "OCR页码"
                              : evidence.page_method}`
                        : ""}
                      {` · ${evidence.evidence_type} · ${evidence.retrieval_methods.join(" + ")}`}
                    </span>
                    <p>{evidence.quote}</p>
                  </div>
                ))
              ) : (
                <p>没有合同原文证据；空结果由完整检索轨迹支撑。</p>
              )}
              <p>
                搜索条款 {item.retrieval_trace.searched_clause_count || 0} 个，候选{" "}
                {item.retrieval_trace.candidate_count || 0} 个，送审{" "}
                {item.retrieval_trace.returned_count || 0} 个
                {item.retrieval_trace.truncated ? "（候选已按每项上限截取）" : ""}。
              </p>
            </details>
            {item.baseline_citations?.length > 0 && (
              <details>
                <summary>查看公司基准条款依据（{item.baseline_citations.length}）</summary>
                {item.baseline_citations.map((citation) => (
                  <div
                    className="quote"
                    key={citation.clause_node_id || `${citation.source_file}-${citation.clause_no}`}
                  >
                    <span>
                      《{citation.document_title}》· {citation.document_version} · {citation.source_file} ·
                      第 {citation.clause_no} 条
                      {citation.page_no ? ` · 第 ${citation.page_no} 页` : ""}
                    </span>
                    <p>{citation.clause_text}</p>
                  </div>
                ))}
              </details>
            )}
            {item.legal_citations?.length > 0 && (
              <details>
                <summary>查看法律 RAG 依据（{item.legal_citations.length}）</summary>
                {item.legal_citations.map((citation) => (
                  <div className="quote" key={citation.authority_id}>
                    <span>
                      {citation.authority} · {citation.document_no} · {citation.article_no} ·
                      相关度 {citation.relevance_score}% · 截止 {citation.as_of_date}
                    </span>
                    <p>{citation.summary}</p>
                    <a href={citation.source_url} target="_blank" rel="noreferrer">
                      查看官方来源（生效：{citation.effective_from}）
                    </a>
                  </div>
                ))}
              </details>
            )}
            {item.redline?.proposed_text && (
              <details>
                <summary>查看 Redline 草案</summary>
                <div className="suggestion-copy replacement-clause">
                  <span>{item.redline.action_type} · {item.redline.strategy}</span>
                  <p>{item.redline.proposed_text}</p>
                </div>
              </details>
            )}
            <footer>
              <span>
                {item.human_confirmation?.status === "已确认"
                  ? `已人工确认：${item.human_confirmation.comment}`
                  : item.human_confirmation_required
                    ? "高风险：导出对外版本前必须人工确认"
                    : "无需高风险人工门禁"}
              </span>
              {item.human_confirmation_required &&
                item.human_confirmation?.status !== "已确认" && (
                  <button className="accept" disabled={busy} onClick={() => onConfirm(item)}>
                    人工确认
                  </button>
                )}
            </footer>
          </article>
        ))}
      </div>
    </section>
  );
}

function SuggestionReferral({
  item,
  contractId,
  consultations,
  users,
  me,
  token,
  busy,
  onChange,
  toast,
  invalidate,
}: {
  item: Suggestion;
  contractId: string;
  consultations: Consultation[];
  users: User[];
  me: User;
  token: string;
  busy: boolean;
  onChange: (updater: (rows: Consultation[]) => Consultation[]) => void;
  toast: (text: string, kind?: "ok" | "error") => void;
  invalidate: (...views: View[]) => void;
}) {
  const referrals = consultations.filter(
    (row) => row.suggestion_id === item.id,
  );
  const active = referrals.find((row) =>
    ["待审核", "待答复"].includes(row.status),
  );
  const latestCompleted = referrals.find((row) => row.status === "已审核");
  const [open, setOpen] = useState(false);
  const [department, setDepartment] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [question, setQuestion] = useState(
    `请审核“${item.title}”这一风险及系统生成的替换条款，确认是否适合接纳，并说明需要调整的边界。`,
  );
  const [reviewDecision, setReviewDecision] = useState("同意系统建议");
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const departments = Array.from(
    new Set(
      users
        .filter((user) => user.id !== me.id && user.department)
        .map((user) => user.department),
    ),
  ).sort((left, right) => left.localeCompare(right, "zh-CN"));
  const departmentUsers = users.filter(
    (user) => user.id !== me.id && user.department === department,
  );
  const userName = (id: string) =>
    users.find((user) => user.id === id)?.name || "未知同事";

  function openReferral() {
    const recommended =
      item.category.includes("付款") ||
      item.category.includes("金额") ||
      item.category.includes("税")
        ? "财务部"
        : item.category.includes("技术") || item.category.includes("设备")
          ? "服务部"
          : "法务部";
    const nextDepartment = departments.includes(recommended)
      ? recommended
      : departments.includes("合同管理部")
        ? "合同管理部"
        : departments[0] || "";
    setDepartment(nextDepartment);
    setAssigneeId(
      users.find(
        (user) => user.id !== me.id && user.department === nextDepartment,
      )?.id || "",
    );
    setOpen(true);
  }

  async function submitReferral(event: FormEvent) {
    event.preventDefault();
    if (!department || !assigneeId || !question.trim()) return;
    setSubmitting(true);
    try {
      const created = await request<Consultation>(
        `/contracts/${contractId}/consultations`,
        {
          method: "POST",
          body: JSON.stringify({
            suggestion_id: item.id,
            assignee_id: assigneeId,
            question: question.trim(),
            due_hours: 24,
          }),
        },
        token,
      );
      onChange((rows) => [created, ...rows]);
      setOpen(false);
      invalidate("dashboard", "audit");
      toast(
        `已转批给${created.target_department} · ${userName(created.assignee_id)}`,
      );
    } catch (error) {
      toast(error instanceof Error ? error.message : "转批失败", "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitReview(event: FormEvent) {
    event.preventDefault();
    if (!active || !answer.trim()) return;
    setSubmitting(true);
    try {
      const updated = await request<
        Pick<Consultation, "id" | "status" | "answer" | "review_decision">
      >(
        `/consultations/${active.id}/answer`,
        {
          method: "PATCH",
          body: JSON.stringify({
            answer: answer.trim(),
            review_decision: reviewDecision,
          }),
        },
        token,
      );
      onChange((rows) =>
        rows.map((row) =>
          row.id === updated.id ? { ...row, ...updated } : row,
        ),
      );
      setAnswer("");
      invalidate("dashboard", "audit");
      toast("该风险建议的转批审核已完成");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "提交审核意见失败",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelReferral() {
    if (!active) return;
    setSubmitting(true);
    try {
      const updated = await request<Pick<Consultation, "id" | "status">>(
        `/consultations/${active.id}/cancel`,
        { method: "PATCH" },
        token,
      );
      onChange((rows) =>
        rows.map((row) =>
          row.id === updated.id ? { ...row, ...updated } : row,
        ),
      );
      invalidate("dashboard", "audit");
      toast("已撤回本条建议的转批");
    } catch (error) {
      toast(error instanceof Error ? error.message : "撤回失败", "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="suggestion-referral">
      {active && (
        <section className="referral-card pending">
          <header>
            <div>
              <strong>转批审核中</strong>
              <span>
                {active.target_department} · {userName(active.assignee_id)}
              </span>
            </div>
            <StatusPill value={active.status} />
          </header>
          <p>{active.question}</p>
          <small>
            由 {userName(active.requester_id)} 发起 · 截止{" "}
            {fmtDate(active.due_at)}
          </small>
          {active.assignee_id === me.id && (
            <form className="referral-review-form" onSubmit={submitReview}>
              <label>
                审核结论
                <select
                  value={reviewDecision}
                  onChange={(event) => setReviewDecision(event.target.value)}
                  disabled={submitting || busy}
                >
                  <option>同意系统建议</option>
                  <option>建议修改</option>
                  <option>不建议采纳</option>
                </select>
              </label>
              <textarea
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="填写对该风险原文和替换条款的专业审核意见"
                disabled={submitting || busy}
                required
              />
              <button
                className="primary"
                disabled={submitting || busy || !answer.trim()}
              >
                提交审核意见
              </button>
            </form>
          )}
          {active.requester_id === me.id && (
            <button
              className="referral-cancel"
              onClick={() => void cancelReferral()}
              disabled={submitting || busy}
            >
              撤回转批
            </button>
          )}
        </section>
      )}
      {!active && latestCompleted && (
        <section className="referral-card completed">
          <header>
            <div>
              <strong>转批审核意见</strong>
              <span>
                {latestCompleted.target_department} ·{" "}
                {userName(latestCompleted.assignee_id)}
              </span>
            </div>
            <StatusPill
              value={latestCompleted.review_decision || latestCompleted.status}
            />
          </header>
          <p>{latestCompleted.answer}</p>
          <small>该意见供原审核人最终接纳、改写或拒绝本条建议时参考。</small>
        </section>
      )}
      {!active && item.decision === "待处理" && (
        <div className="referral-action">
          <button onClick={openReferral} disabled={busy}>
            转批
          </button>
          <span>没有把握时，按部门快速选择同事复核这一条建议</span>
        </div>
      )}
      {open && !active && (
        <form className="referral-form" onSubmit={submitReferral}>
          <header>
            <div>
              <strong>转批这一条风险建议</strong>
              <span>只转交当前建议，不影响本轮其他风险</span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={submitting}
            >
              ×
            </button>
          </header>
          <div className="referral-selects">
            <label>
              目标部门
              <select
                value={department}
                onChange={(event) => {
                  const value = event.target.value;
                  setDepartment(value);
                  setAssigneeId(
                    users.find(
                      (user) => user.id !== me.id && user.department === value,
                    )?.id || "",
                  );
                }}
                disabled={submitting}
                required
              >
                <option value="">选择部门</option>
                {departments.map((value) => (
                  <option value={value} key={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              审核同事
              <select
                value={assigneeId}
                onChange={(event) => setAssigneeId(event.target.value)}
                disabled={submitting || !department}
                required
              >
                <option value="">选择同事</option>
                {departmentUsers.map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.name} · {user.role}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            需要同事确认的问题
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={submitting}
              required
            />
          </label>
          <footer>
            <small>接收人答复前，本条建议暂不能接纳、改写或拒绝。</small>
            <button
              className="primary"
              disabled={submitting || !assigneeId || !question.trim()}
            >
              {submitting ? "正在转批…" : "确认转批"}
            </button>
          </footer>
        </form>
      )}
    </div>
  );
}

function FocusedRiskReviewCard({
  item,
  selected,
  busy,
  onSelect,
  onConfirm,
}: {
  item: FocusedCheckResult;
  selected: boolean;
  busy: boolean;
  onSelect: () => void;
  onConfirm: () => void;
}) {
  const evidence = item.evidence[0];
  const isMissing = item.status === "NOT_MENTIONED";
  const redlineLabel =
    item.redline?.action_type === "新增条款" || isMissing
      ? "可直接插入的完整条款"
      : item.redline?.action_type === "人工起草"
        ? "公司标准参考稿（需人工确认）"
        : "可直接替换风险原文的完整条款";
  return (
    <div
      className={`risk-card focused-risk-card ${riskClass(item.risk_level)} ${selected ? "selected" : ""}`}
      data-risk-card-id={item.id}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <header>
        <div>
          <span className="risk-index">{item.check_code}</span>
          <StatusPill value={item.risk_level} risk />
          <span className="category">专项风险 · {item.category}</span>
          <StatusPill value={item.status} />
        </div>
        {item.legal_rag_required && <span className="history-badge">法律 RAG</span>}
      </header>
      <h3>{item.check_name}</h3>
      <div className="quote evidence-source">
        <span>{isMissing ? "合同缺失条款" : "风险原文"}</span>
        {evidence ? (
          <>
            <small>
              {evidence.source_file || "当前合同"}
              {evidence.page_no ? ` · 第 ${evidence.page_no} 页` : ""}
              {evidence.clause_no ? ` · ${evidence.clause_no}` : ""}
            </small>
            <p>{evidence.quote}</p>
          </>
        ) : (
          <p>待审合同未约定“{item.check_name}”相关内容，完整检索后没有可定位的风险原文。</p>
        )}
      </div>
      <div className="suggestion-copy replacement-clause">
        <span>
          {redlineLabel}
          <b>{item.redline?.status || "待人工起草"}</b>
        </span>
        <p>
          {item.redline?.proposed_text ||
            "尚无可直接使用的完整条款，请依据公司标准条款人工起草后再接纳。"}
        </p>
      </div>
      <details>
        <summary>查看审核依据与谈判重点</summary>
        <div className="basis-grid">
          <div>
            <strong>审核依据</strong>
            <p>{item.check_code} · {item.status} · {item.reason}</p>
            {item.evidence.slice(1).map((row) => (
              <div className="quote evidence-source" key={row.id}>
                <span>其他风险原文 · {row.source_file} · {row.clause_no || "原文"}</span>
                <p>{row.quote}</p>
              </div>
            ))}
            {item.baseline_citations.map((row) => (
              <div className="quote baseline-source" key={row.clause_node_id || `${row.source_file}-${row.clause_no}`}>
                <span>
                  公司标准依据 · 《{row.document_title}》· {row.document_version} ·
                  第 {row.clause_no} 条
                  {row.page_no ? ` · 第 ${row.page_no} 页` : ""}
                </span>
                <p>{row.clause_text}</p>
              </div>
            ))}
            {item.legal_citations.map((row) => (
              <div className="quote legal-source" key={row.authority_id}>
                <span>
                  法律法规依据 · {row.title} · {row.article_no} · 相关度 {row.relevance_score}%
                </span>
                <p>{row.summary}</p>
                <a href={row.source_url} target="_blank" rel="noreferrer">
                  查看官方来源
                </a>
              </div>
            ))}
          </div>
          <div>
            <strong>谈判重点</strong>
            <p>{item.negotiation_focus}</p>
          </div>
        </div>
      </details>
      <footer>
        <span>
          置信度 {item.confidence}% · {item.decision_source}
          {item.human_confirmation?.status === "已确认"
            ? ` · 已确认：${item.human_confirmation.comment}`
            : item.human_confirmation_required
              ? " · 需要人工确认"
              : " · 无需人工门禁"}
        </span>
        {item.human_confirmation_required &&
          item.human_confirmation?.status !== "已确认" && (
            <button className="accept" disabled={busy} onClick={onConfirm}>
              人工确认
            </button>
          )}
      </footer>
    </div>
  );
}

function RiskWorkspace({
  run,
  focusedReview,
  contractId,
  consultations,
  users,
  me,
  token,
  busy,
  onDecision,
  onRedraft,
  onConfirmFocused,
  onConsultationsChange,
  toast,
  invalidate,
}: {
  run?: ReviewRun;
  focusedReview: FocusedReview | null;
  contractId: string;
  consultations: Consultation[];
  users: User[];
  me: User;
  token: string;
  busy: boolean;
  onDecision: (
    item: Suggestion,
    decision: string,
    note?: string,
  ) => Promise<boolean>;
  onRedraft: (item: Suggestion, instruction: string) => Promise<boolean>;
  onConfirmFocused: (item: FocusedCheckResult) => Promise<void>;
  onConsultationsChange: (
    updater: (rows: Consultation[]) => Consultation[],
  ) => void;
  toast: (text: string, kind?: "ok" | "error") => void;
  invalidate: (...views: View[]) => void;
}) {
  const focusedRisks = useMemo(
    () => focusedReview?.results.filter(isActionableFocusedRisk) || [],
    [focusedReview],
  );
  const [filter, setFilter] = useState("全部");
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [previewFileUrl, setPreviewFileUrl] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [selectedRiskId, setSelectedRiskId] = useState("");
  const [expandedEvidence, setExpandedEvidence] = useState<Set<string>>(
    new Set(),
  );
  const [editor, setEditor] = useState<{
    id: string;
    mode: "redraft" | "reject";
  } | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [submittingId, setSubmittingId] = useState("");
  const documentPreviewRef = useRef<HTMLDivElement>(null);
  const riskListRef = useRef<HTMLDivElement>(null);
  const selectionOriginRef = useRef<"document" | "risk" | "">("");
  const previewVersionId = run?.version_id || "";
  const firstRiskId = focusedRisks[0]?.id || run?.suggestions[0]?.id || "";
  const selectRiskFromCard = useCallback((riskId: string) => {
    selectionOriginRef.current = "risk";
    setSelectedRiskId(riskId);
  }, []);
  const selectRiskFromDocument = useCallback(
    (riskId: string) => {
      selectionOriginRef.current = "document";
      const risk = run?.suggestions.find((item) => item.id === riskId);
      const focusedRisk = focusedRisks.find((item) => item.id === riskId);
      const visible =
        (!risk && !focusedRisk) ||
        filter === "全部" ||
        risk?.risk_level === filter ||
        focusedRisk?.risk_level === filter ||
        (filter === "待处理" &&
          (risk?.decision === "待处理" ||
            (focusedRisk &&
              focusedRisk.human_confirmation?.status !== "已确认"))) ||
        (filter === "转批给我" &&
          Boolean(risk) &&
          consultations.some(
            (row) =>
              row.suggestion_id === risk?.id &&
              row.assignee_id === me.id &&
              ["待审核", "待答复"].includes(row.status),
          ));
      if (!visible) setFilter("全部");
      setSelectedRiskId(riskId);
    },
    [consultations, filter, focusedRisks, me.id, run],
  );

  useEffect(() => {
    if (!previewVersionId) {
      const resetTimer = window.setTimeout(() => {
        setPreviewData(null);
        setPreviewFileUrl("");
      }, 0);
      return () => window.clearTimeout(resetTimer);
    }
    let cancelled = false;
    let objectUrl = "";
    const controller = new AbortController();
    const initializeTimer = window.setTimeout(() => {
      setPreviewLoading(true);
      setPreviewError("");
      setPreviewData(null);
      setPreviewFileUrl("");
      selectionOriginRef.current = "risk";
      setSelectedRiskId(firstRiskId);
    }, 0);
    void request<PreviewData>(
      `/contracts/${contractId}/versions/${previewVersionId}/preview`,
      { signal: controller.signal },
      token,
    )
      .then(async (data) => {
        if (data.format === "pdf") {
          const response = await fetch(`${apiRoot()}${data.file_endpoint}`, {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
          });
          if (!response.ok) throw new Error("无法读取批注版 PDF");
          objectUrl = URL.createObjectURL(await response.blob());
        }
        if (!cancelled) {
          setPreviewData(data);
          setPreviewFileUrl(objectUrl);
        }
      })
      .catch((reason) => {
        if (!cancelled && !(reason instanceof DOMException && reason.name === "AbortError"))
          setPreviewError(reason instanceof Error ? reason.message : "在线预览加载失败");
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
      window.clearTimeout(initializeTimer);
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [contractId, firstRiskId, previewVersionId, token]);

  useEffect(() => {
    if (!selectedRiskId) return;
    const frame = window.requestAnimationFrame(() => {
      const markers = Array.from(
        documentPreviewRef.current?.querySelectorAll<HTMLElement>(
          "[data-risk-id], [data-risk-ids]",
        ) || [],
      );
      markers.forEach((marker) => {
        const riskIds = (
          marker.dataset.riskIds || marker.dataset.riskId || ""
        ).split(/\s+/);
        const selected = riskIds.includes(selectedRiskId);
        marker.classList.toggle("risk-source-selected", selected);
        marker.setAttribute("aria-current", selected ? "true" : "false");
      });
      const source = markers.find(
        (marker) =>
          (marker.dataset.riskIds || marker.dataset.riskId || "")
            .split(/\s+/)
            .includes(selectedRiskId),
      );
      const cards = Array.from(
        riskListRef.current?.querySelectorAll<HTMLElement>("[data-risk-card-id]") || [],
      );
      const card = cards.find(
        (item) => item.dataset.riskCardId === selectedRiskId,
      );
      if (selectionOriginRef.current === "risk" && source) {
        source.scrollIntoView({ behavior: "smooth", block: "center" });
        selectionOriginRef.current = "";
      } else if (selectionOriginRef.current === "document" && card) {
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.focus({ preventScroll: true });
        selectionOriginRef.current = "";
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [filter, previewData, selectedRiskId]);

  useEffect(() => {
    const root = documentPreviewRef.current;
    if (!root || previewData?.format !== "docx") return;
    const activate = (event: Event) => {
      if (
        event instanceof KeyboardEvent &&
        !["Enter", " "].includes(event.key)
      )
        return;
      const marker = (event.target as HTMLElement | null)?.closest<HTMLElement>(
        "[data-risk-id], [data-risk-ids]",
      );
      const riskIds = (
        marker?.dataset.riskIds || marker?.dataset.riskId || ""
      ).split(/\s+/).filter(Boolean);
      const riskId = riskIds.includes(selectedRiskId)
        ? selectedRiskId
        : riskIds[0];
      if (!riskId) return;
      if (event instanceof KeyboardEvent) event.preventDefault();
      selectRiskFromDocument(riskId);
    };
    root.addEventListener("click", activate);
    root.addEventListener("keydown", activate);
    return () => {
      root.removeEventListener("click", activate);
      root.removeEventListener("keydown", activate);
    };
  }, [previewData, selectRiskFromDocument, selectedRiskId]);

  if (!run)
    return (
      <Empty
        title="尚未执行智能审核"
        text="点击“启动第 1 轮审核”，系统会结合规则库、历史经验和大模型分析当前版本。"
      />
    );
  const suggestionRows = run.suggestions.filter(
    (item) =>
      filter === "全部" ||
      item.risk_level === filter ||
      (filter === "待处理" && item.decision === "待处理") ||
      (filter === "转批给我" &&
        consultations.some(
          (row) =>
            row.suggestion_id === item.id &&
            row.assignee_id === me.id &&
            ["待审核", "待答复"].includes(row.status),
        )),
  );
  const focusedRows = focusedRisks.filter(
    (item) =>
      filter === "全部" ||
      item.risk_level === filter ||
      (filter === "待处理" &&
        item.human_confirmation?.status !== "已确认"),
  );
  const selectedRisk = run.suggestions.find((item) => item.id === selectedRiskId);
  const selectedFocusedRisk = focusedRisks.find(
    (item) => item.id === selectedRiskId,
  );
  const selectedAnnotation = previewData?.annotations.find(
    (item) => item.id === selectedRiskId,
  );
  const focusPage =
    selectedRisk?.page_no ||
    selectedFocusedRisk?.evidence?.[0]?.page_no ||
    selectedAnnotation?.page_no ||
    selectedAnnotation?.locations?.[0]?.page_no;
  const unifiedRisks = [...focusedRisks, ...run.suggestions];
  const unifiedRiskCounts = {
    high: unifiedRisks.filter((item) => item.risk_level === "高").length,
    medium: unifiedRisks.filter((item) => item.risk_level === "中").length,
    low: unifiedRisks.filter((item) => item.risk_level === "低").length,
  };

  async function generateAnotherDraft(item: Suggestion) {
    const instruction = (inputs[item.id] || "").trim();
    if (!instruction) return;
    setSubmittingId(item.id);
    const completed = await onRedraft(item, instruction);
    setSubmittingId("");
    if (completed) setInputs((current) => ({ ...current, [item.id]: "" }));
  }

  async function decide(item: Suggestion, decision: string, note = "") {
    setSubmittingId(item.id);
    const completed = await onDecision(item, decision, note);
    setSubmittingId("");
    if (completed) setEditor(null);
  }

  return (
    <div className="risk-layout review-split-layout">
      <section className="review-document-pane panel" aria-label="带批注合同在线预览">
        <header className="review-document-head">
          <div>
            <p className="eyebrow">带批注合同</p>
            <strong>{previewData?.file_name || `第 ${run.round_no} 轮审核文件`}</strong>
            <span>
              {previewData?.annotation_status || "正在读取本轮批注版文件"}
              {focusedRisks.some((item) => item.evidence.length)
                ? ` · 网页预览另联动 ${focusedRisks.filter((item) => item.evidence.length).length} 项专项风险`
                : ""}
            </span>
          </div>
          <div className="document-status">
            <span className="annotation-dot" />
            {previewData?.is_annotated ? "批注已回写" : "上传原件"}
          </div>
        </header>
        <div className="review-document-canvas" ref={documentPreviewRef}>
          {previewLoading ? (
            <div className="preview-loading">
              <span className="spinner" />
              正在加载批注版合同…
            </div>
          ) : previewError ? (
            <div className="preview-loading error">{previewError}</div>
          ) : previewData?.format === "pdf" ? (
            <PdfDocumentViewer
              fileUrl={previewFileUrl}
              focusPage={focusPage}
              focusRiskId={selectedRiskId}
              riskAnnotations={previewData.annotations}
              onRiskClick={selectRiskFromDocument}
            />
          ) : previewData?.format === "docx" ? (
            <div
              className="docx-web-preview"
              dangerouslySetInnerHTML={{ __html: previewData.html }}
            />
          ) : (
            <div className="preview-loading">暂时无法显示本轮文件</div>
          )}
        </div>
      </section>
      <section className="risk-feed review-risk-pane">
        <aside className="risk-summary panel review-risk-summary">
        <p className="eyebrow">第 {run.round_no} 轮审核</p>
        <h2>风险条款</h2>
        <div className="risk-score-big">
          <strong>{run.risk_score}</strong>
          <span>/ 100</span>
        </div>
        <p>{run.summary}</p>
        <div className="risk-counts">
          <button onClick={() => setFilter("高")}>
            <i className="dot red" />
            <span>高风险</span>
            <strong>{unifiedRiskCounts.high}</strong>
          </button>
          <button onClick={() => setFilter("中")}>
            <i className="dot amber" />
            <span>中风险</span>
            <strong>{unifiedRiskCounts.medium}</strong>
          </button>
          <button onClick={() => setFilter("低")}>
            <i className="dot green" />
            <span>低风险</span>
            <strong>{unifiedRiskCounts.low}</strong>
          </button>
        </div>
        <div className="comparison">
          <span>版本偏离分析</span>
          <p>{run.comparison_summary}</p>
        </div>
        <small className="engine">分析引擎：{run.engine}</small>
        </aside>
        <div className="filter-row">
          <div>
            {["全部", "高", "中", "低", "待处理", "转批给我"].map((item) => (
              <button
                key={item}
                className={filter === item ? "active" : ""}
                onClick={() => setFilter(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <span>
            显示 {focusedRows.length + suggestionRows.length} 项 · 专项风险 {focusedRisks.length} · 文档风险 {run.suggestions.length}
          </span>
        </div>
        <div className="review-risk-list" ref={riskListRef}>
        {focusedRows.map((item) => (
          <FocusedRiskReviewCard
            item={item}
            selected={selectedRiskId === item.id}
            busy={busy}
            onSelect={() => selectRiskFromCard(item.id)}
            onConfirm={() => void onConfirmFocused(item)}
            key={item.id}
          />
        ))}
        {suggestionRows.map((item, index) => {
          const expanded = expandedEvidence.has(item.id);
          const foldable = item.original_text.length > 220;
          const draftCount = Math.max(1, item.revision_history?.length || 0);
          const editing = editor?.id === item.id ? editor.mode : null;
          const activeReferral = consultations.find(
            (row) =>
              row.suggestion_id === item.id &&
              ["待审核", "待答复"].includes(row.status),
          );
          return (
            <div
              className={`risk-card ${riskClass(item.risk_level)} ${selectedRiskId === item.id ? "selected" : ""}`}
              key={item.id}
              data-risk-card-id={item.id}
              role="button"
              tabIndex={0}
              onClick={() => selectRiskFromCard(item.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  selectRiskFromCard(item.id);
                }
              }}
            >
              <header>
                <div>
                  <span className="risk-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <StatusPill value={item.risk_level} risk />
                  <span className="category">{item.category}</span>
                  {item.occurrence_count > 1 && (
                    <span className="occurrence-badge">
                      同类风险 {item.occurrence_no}/{item.occurrence_count} ·
                      独立处置
                    </span>
                  )}
                  {item.historical_release && (
                    <span className="history-badge">历史曾放行</span>
                  )}
                </div>
                <StatusPill value={item.decision} />
              </header>
              <h3>{item.title}</h3>
              <div className="quote">
                <span>
                  {item.action_type === "新增条款"
                    ? "建议插入位置上下文"
                    : "风险原文"}
                </span>
                <p
                  className={
                    item.action_type !== "新增条款" && foldable && !expanded
                      ? "collapsed-evidence"
                      : ""
                  }
                >
                  {item.action_type === "新增条款"
                    ? item.anchor_text || "未指定插入位置，将在接纳后追加到合同末尾。"
                    : item.original_text}
                </p>
                {item.action_type !== "新增条款" && foldable && (
                  <button
                    className="evidence-toggle"
                    onClick={() =>
                      setExpandedEvidence((current) => {
                        const next = new Set(current);
                        if (expanded) next.delete(item.id);
                        else next.add(item.id);
                        return next;
                      })
                    }
                  >
                    {expanded
                      ? "收起原文"
                      : `展开原文（${item.original_text.length}字）`}
                  </button>
                )}
              </div>
              <div className="suggestion-copy replacement-clause">
                <span>
                  {item.action_type === "新增条款"
                    ? "可直接插入的完整条款"
                    : item.action_type === "人工起草"
                      ? "需人工起草的关联替换条款"
                    : "可直接替换风险原文的完整条款"}
                  <b className={item.replacement_check ? "replacement-quality" : undefined}>
                    {item.replacement_check
                      ? item.replacement_check.status +
                        " · 关联度 " +
                        item.replacement_check.relation_score +
                        "%"
                      : "第 " + draftCount + " 稿"}
                  </b>
                </span>
                <p>
                  {item.suggested_text ||
                    "系统未生成可直接使用的关联替换条款，请结合风险原文人工起草。"}
                </p>
                {item.replacement_check?.warnings.length ? (
                  <small className="replacement-quality-note">
                    {item.replacement_check.warnings.join(" ")}
                  </small>
                ) : null}
              </div>
              {draftCount > 1 && (
                <details className="draft-history">
                  <summary>查看全部生成历史（{draftCount} 稿）</summary>
                  {item.revision_history.map((draft) => (
                    <article key={draft.version}>
                      <header>
                        <strong>第 {draft.version} 稿</strong>
                        <small>
                          {draft.created_by} · {fmtDate(draft.created_at)}
                        </small>
                      </header>
                      <p>{draft.suggested_text}</p>
                      <footer>修改要求：{draft.instruction}</footer>
                    </article>
                  ))}
                </details>
              )}
              <details>
                <summary>查看审核依据与谈判重点</summary>
                <div className="basis-grid">
                  <div>
                    <strong>审核依据</strong>
                    <p>{item.basis}</p>
                    {item.baseline_citation && (
                      <div className="quote">
                        <span>
                          《{item.baseline_citation.document_title}》· {item.baseline_citation.document_version} ·
                          {item.baseline_citation.source_file} · 第 {item.baseline_citation.clause_no} 条
                          {item.baseline_citation.page_no ? ` · 第 ${item.baseline_citation.page_no} 页` : ""}
                        </span>
                        <p>{item.baseline_citation.clause_text}</p>
                      </div>
                    )}
                  </div>
                  <div>
                    <strong>谈判重点</strong>
                    <p>{item.negotiation_focus}</p>
                  </div>
                </div>
              </details>
              {editing === "redraft" && (
                <div className="clause-redraft">
                  <header>
                    <div>
                      <strong>用自然语言继续修改</strong>
                      <span>
                        不必自己写法律条款；系统会生成可直接替换原文的第{" "}
                        {draftCount + 1} 稿
                      </span>
                    </div>
                    <button onClick={() => setEditor(null)} disabled={busy}>
                      ×
                    </button>
                  </header>
                  <textarea
                    value={inputs[item.id] || ""}
                    onChange={(event) =>
                      setInputs((current) => ({
                        ...current,
                        [item.id]: event.target.value,
                      }))
                    }
                    placeholder="例如：付款期限改为45日，但保留验收合格和收到发票两个前提；逾期利息按一年期LPR计算。"
                    disabled={busy}
                  />
                  <div>
                    <small>
                      如果新稿仍不满意，可以继续输入下一次修改意见，生成第三稿、第四稿。
                    </small>
                    <button
                      onClick={() => void generateAnotherDraft(item)}
                      disabled={
                        busy ||
                        submittingId === item.id ||
                        !(inputs[item.id] || "").trim()
                      }
                    >
                      重新生成第 {draftCount + 1} 稿
                    </button>
                    <button
                      className="accept"
                      onClick={() =>
                        void decide(
                          item,
                          draftCount > 1 ? "修改后接纳" : "接纳",
                          item.latest_instruction || "接纳当前完整条款",
                        )
                      }
                      disabled={busy || submittingId === item.id}
                    >
                      接纳当前稿
                    </button>
                  </div>
                </div>
              )}
              {editing === "reject" && (
                <div className="clause-redraft reject-editor">
                  <header>
                    <div>
                      <strong>拒绝本处建议</strong>
                      <span>
                        仅放行这一处风险，不影响同类风险原文的其他处置
                      </span>
                    </div>
                    <button onClick={() => setEditor(null)} disabled={busy}>
                      ×
                    </button>
                  </header>
                  <textarea
                    value={inputs[item.id] || ""}
                    onChange={(event) =>
                      setInputs((current) => ({
                        ...current,
                        [item.id]: event.target.value,
                      }))
                    }
                    placeholder="请输入业务放行理由，将写入审计日志"
                    disabled={busy}
                  />
                  <div>
                    <small>拒绝后，下一轮仅对同一处风险继承放行结论。</small>
                    <button
                      className="danger-action"
                      onClick={() =>
                        void decide(
                          item,
                          "拒绝",
                          (inputs[item.id] || "").trim() ||
                            "人工确认放行本处风险",
                        )
                      }
                      disabled={busy || submittingId === item.id}
                    >
                      确认拒绝本处建议
                    </button>
                  </div>
                </div>
              )}
              <SuggestionReferral
                item={item}
                contractId={contractId}
                consultations={consultations}
                users={users}
                me={me}
                token={token}
                busy={busy}
                onChange={onConsultationsChange}
                toast={toast}
                invalidate={invalidate}
              />
              <footer>
                <span>
                  置信度 {item.confidence}% · {item.source}
                </span>
                <div>
                  {item.decision === "待处理" && activeReferral ? (
                    <span className="referral-wait">
                      等待 {activeReferral.target_department} 审核后再处置
                    </span>
                  ) : item.decision === "待处理" ? (
                    <>
                      <button
                        disabled={busy}
                        onClick={() =>
                          setEditor({ id: item.id, mode: "reject" })
                        }
                      >
                        拒绝
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          setEditor({ id: item.id, mode: "redraft" })
                        }
                      >
                        修改
                      </button>
                      <button
                        className="accept"
                        disabled={busy}
                        onClick={() =>
                          void decide(item, "接纳", "接纳系统生成的完整条款")
                        }
                      >
                        批准
                      </button>
                    </>
                  ) : (
                    <span className="decided">
                      已完成处置 · {item.decision}
                      {item.decision_note ? ` · ${item.decision_note}` : ""}
                    </span>
                  )}
                </div>
              </footer>
            </div>
          );
        })}
        </div>
      </section>
    </div>
  );
}

function VersionsWorkspace({
  detail,
  selectedId,
  onCompare,
  onDownload,
  onPreview,
  onCorrectComment,
  onConsistency,
  onRedaction,
  onNotify,
  utility,
  onCloseUtility,
}: {
  detail: ContractDetail;
  selectedId: string;
  onCompare: () => void;
  onDownload: (path: string, name: string) => void;
  onPreview: (version: Version) => void;
  onCorrectComment: (item: DocumentComment) => void;
  onConsistency: () => void;
  onRedaction: () => void;
  onNotify: () => void;
  utility: {
    title: string;
    meta: string;
    content: string;
    alerts?: { level: string; title: string; detail: string }[];
  } | null;
  onCloseUtility: () => void;
}) {
  return (
    <section className="panel padded">
      <div className="panel-head">
        <div>
          <h2>五轮版本与批注来源</h2>
          <p>
            每轮绑定一份用户上传的主合同，每份都可在网页中预览原批注与 AI 高亮
          </p>
        </div>
        <div className="version-actions">
          <button className="secondary" onClick={onConsistency}>
            一致性检查
          </button>
          <button className="secondary" onClick={onRedaction}>
            脱敏预览
          </button>
          <button className="secondary" onClick={onNotify}>
            邮件通知
          </button>
          <button className="secondary" onClick={onCompare}>
            对比最近两轮
          </button>
          <button
            className="primary"
            onClick={() =>
              onDownload(
                `/contracts/${selectedId}/export?mode=clean`,
                `${detail.contract.contract_no}-无痕清洁版.docx`,
              )
            }
          >
            下载无痕清洁版
          </button>
        </div>
      </div>
      {utility && (
        <div className="utility-result">
          <header>
            <div>
              <strong>{utility.title}</strong>
              <span>{utility.meta}</span>
            </div>
            <button onClick={onCloseUtility}>×</button>
          </header>
          {utility.alerts?.map((item) => (
            <div
              className={`utility-alert ${riskClass(item.level)}`}
              key={`${item.level}-${item.title}`}
            >
              <StatusPill value={item.level} risk />
              <div>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </div>
            </div>
          ))}
          {!utility.alerts?.length && <pre>{utility.content}</pre>}
          {utility.alerts?.length ? (
            <p className="utility-note">{utility.content}</p>
          ) : null}
        </div>
      )}
      <div className="version-grid">
        {detail.versions.map((item) => (
          <article key={item.id}>
            <div className="version-head">
              <span>
                R{item.review_round_no} / V{item.version_no}
              </span>
              <StatusPill value={item.parse_status} />
            </div>
            <h3>{item.label}</h3>
            <p>{item.file_name}</p>
            <small>
              {item.document_source}
              {item.source_department ? ` · ${item.source_department}` : ""} ·
              批注/修订 {item.comment_count} 条
            </small>
            <small>
              {(item.file_size / 1024).toFixed(1)} KB ·{" "}
              {fmtDate(item.created_at)}
            </small>
            <div>
              <button className="preview-link" onClick={() => onPreview(item)}>
                在线预览
              </button>
              <button
                onClick={() =>
                  onDownload(
                    `/contracts/${selectedId}/versions/${item.id}/download`,
                    item.file_name,
                  )
                }
              >
                下载上传原件
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="round-strip">
        {Array.from({ length: 5 }, (_, index) => {
          const roundNo = index + 1;
          const round = detail.review_runs.find(
            (item) => item.round_no === roundNo,
          );
          const version = detail.versions.find(
            (item) => item.review_round_no === roundNo,
          );
          return (
            <div
              className={round ? "done" : version ? "uploaded" : ""}
              key={index}
            >
              <span>{round ? "✓" : roundNo}</span>
              <strong>第 {roundNo} 轮</strong>
              <small>
                {round
                  ? `${round.risk_score} 分 · 已回写`
                  : version
                    ? "已上传，待审核"
                    : "尚未上传"}
              </small>
              {version && (
                <button onClick={() => onPreview(version)}>在线预览</button>
              )}
              {round?.annotated_available && (
                <button
                  onClick={() =>
                    onDownload(
                      `/contracts/${selectedId}/review-runs/${round.id}/annotated`,
                      round.annotated_file_name,
                    )
                  }
                >
                  下载批注版
                </button>
              )}
            </div>
          );
        })}
      </div>
      <div className="comment-source-section">
        <div className="panel-head">
          <div>
            <h2>原文件批注来源识别</h2>
            <p>
              优先匹配员工身份；未匹配时结合文件来源、作者名和部门关键词判断，可人工确认并沉淀映射
            </p>
          </div>
          <strong>{detail.document_comments.length} 条</strong>
        </div>
        {detail.document_comments.length ? (
          <div className="comment-list">
            {detail.document_comments.map((item) => (
              <article key={item.id}>
                <header>
                  <div>
                    <strong>{item.author_name}</strong>
                    <span>
                      {item.annotation_type}
                      {item.page_no ? ` · 第${item.page_no}页` : ""}
                    </span>
                  </div>
                  <StatusPill value={item.source_kind} />
                </header>
                <p>
                  {item.comment_text ||
                    item.anchor_text ||
                    "仅高亮，未填写批注文字"}
                </p>
                <footer>
                  <span>
                    {item.source_department || "未确认部门"} · 置信度{" "}
                    {item.source_confidence}% · {item.source_basis}
                  </span>
                  <button onClick={() => onCorrectComment(item)}>
                    确认来源
                  </button>
                </footer>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="本轮文件未检测到可读取的批注或修订"
            text="系统仍会保留上传原件；如批注已被扁平化为图片，可通过OCR作为合同图片内容处理。"
          />
        )}
      </div>
    </section>
  );
}

function ApprovalsView({
  rows,
  setRows,
  token,
  me,
  toast,
  invalidate,
  onOpen,
}: {
  rows: Approval[];
  setRows: (updater: (current: Approval[]) => Approval[]) => void;
  token: string;
  me: User;
  toast: (text: string, kind?: "ok" | "error") => void;
  invalidate: () => void;
  onOpen: (id: string) => void;
}) {
  async function decide(item: Approval, decision: string) {
    const comment =
      window.prompt(
        `${decision}意见`,
        decision === "通过"
          ? "风险已审阅，同意进入下一节点。"
          : "请修改未解决风险后重新提交。",
      ) || "";
    try {
      const updated = await request<
        Pick<Approval, "id" | "status" | "decision" | "comment">
      >(
        `/approvals/${item.id}`,
        { method: "PATCH", body: JSON.stringify({ decision, comment }) },
        token,
      );
      setRows((current) =>
        current.map((row) =>
          row.id === updated.id ? { ...row, ...updated } : row,
        ),
      );
      invalidate();
      toast(`审批任务已${decision}`);
    } catch (error) {
      toast(error instanceof Error ? error.message : "审批失败", "error");
    }
  }
  return (
    <>
      <PageHead
        eyebrow="审批管理"
        title="审批中心"
        text="汇总审核结论、人工复核和外部流程号，未解决风险将随审批单提交。"
      />
      <section className="panel table-panel">
        {rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>合同</th>
                  <th>审批部门</th>
                  <th>审批人</th>
                  <th>K2 / OA 草稿号</th>
                  <th>状态</th>
                  <th>意见</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <button
                        className="table-link"
                        onClick={() => onOpen(item.contract_id || "")}
                      >
                        <strong>{item.contract_name}</strong>
                        <small>
                          {item.contract_no} · {item.customer}
                        </small>
                      </button>
                    </td>
                    <td>
                      第 {item.level} 级 · {item.department}
                    </td>
                    <td>{item.approver}</td>
                    <td>
                      <code>{item.external_flow_id || "—"}</code>
                    </td>
                    <td>
                      <StatusPill value={item.status} />
                    </td>
                    <td>{item.comment || "—"}</td>
                    <td>
                      {item.status !== "已完成" &&
                      (item.approver === me.name ||
                        [
                          "法务审核",
                          "财务专家",
                          "审批人",
                          "系统管理员",
                        ].includes(me.role)) ? (
                        <div className="row-actions">
                          <button onClick={() => void decide(item, "驳回")}>
                            驳回
                          </button>
                          <button
                            className="approve"
                            onClick={() => void decide(item, "通过")}
                          >
                            通过
                          </button>
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="暂无审批任务" text="请在合同审核工作台生成审批矩阵。" />
        )}
      </section>
    </>
  );
}

function ChangesView({
  rows,
  contracts,
  selectedId,
  setSelectedId,
  text,
  setText,
  busy,
  onSubmit,
}: {
  rows: ChangeRequest[];
  contracts: Contract[];
  selectedId: string;
  setSelectedId: (v: string) => void;
  text: string;
  setText: (v: string) => void;
  busy: boolean;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <>
      <PageHead
        eyebrow="合同变更"
        title="订改申请与补充协议"
        text="描述客户新要求，系统将定位原合同约定并生成可编辑草案。"
      />
      <section className="change-composer">
        <div>
          <span className="change-index">订改</span>
          <div>
            <h2>填写客户变更要求</h2>
            <p>示例：客户希望把付款账期从 30 天改成 60 天，并增加季度结算。</p>
          </div>
        </div>
        <form onSubmit={onSubmit} aria-busy={busy}>
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            disabled={busy}
            required
          >
            {contracts.map((item) => (
              <option value={item.id} key={item.id}>
                {item.contract_no} · {item.name}
              </option>
            ))}
          </select>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="输入客户新要求或业务变更…"
            disabled={busy}
            required
          />
          <button className="primary" disabled={busy}>
            {busy ? "正在生成…" : "生成订改申请"}
          </button>
        </form>
      </section>
      <div className="change-list">
        {rows.map((item) => (
          <article className="panel padded" key={item.id}>
            <header>
              <div>
                <StatusPill value={item.status} />
                <span>{item.contract_no}</span>
              </div>
              <time>{fmtDate(item.created_at)}</time>
            </header>
            <h2>{item.contract_name}</h2>
            <div className="change-compare">
              <div>
                <span>原合同要求</span>
                <p>{item.original_requirement}</p>
              </div>
              <b>至</b>
              <div>
                <span>客户新要求</span>
                <p>{item.new_requirement}</p>
              </div>
            </div>
            <details>
              <summary>查看生成的补充协议草案</summary>
              <pre>{item.generated_supplement}</pre>
            </details>
          </article>
        ))}
        {!rows.length && (
          <Empty title="暂无订改申请" text="在上方选择合同并输入客户新要求。" />
        )}
      </div>
    </>
  );
}

function KnowledgeView({
  rows,
  query,
  setQuery,
  onSearch,
}: {
  rows: Knowledge[];
  query: string;
  setQuery: (v: string) => void;
  onSearch: () => void;
}) {
  const [section, setSection] = useState<"all" | "knowledge" | "clauses" | "租赁" | "采购">("all");
  const standardClauses = rows.filter((item) => item.is_standard_clause);
  const knowledgeEntries = rows.filter((item) => !item.is_standard_clause);
  const leaseClauses = standardClauses.filter((item) => item.contract_type === "租赁");
  const procurementClauses = standardClauses.filter((item) => item.contract_type === "采购");
  const visibleRows = rows.filter((item) => {
    if (section === "knowledge") return !item.is_standard_clause;
    if (section === "clauses") return Boolean(item.is_standard_clause);
    if (section === "租赁" || section === "采购") return item.is_standard_clause && item.contract_type === section;
    return true;
  });

  return (
    <>
      <PageHead
        eyebrow="审核依据"
        title="合同审核知识库"
        text="沉淀风险规则、标准条款、历史案例与可复用谈判口径。"
      />
      <div className="knowledge-search">
        <span className="search-label">检索</span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSearch();
          }}
          placeholder="付款、违约责任、自动续租、关联方"
        />
        <button onClick={onSearch}>搜索知识库</button>
      </div>
      <div className="knowledge-library-summary">
        <article className="panel">
          <span>租赁标准条款</span>
          <strong>{leaseClauses.length}</strong>
          <small>{leaseClauses[0]?.baseline_version || "尚未导入版本"}</small>
        </article>
        <article className="panel">
          <span>采购标准条款</span>
          <strong>{procurementClauses.length}</strong>
          <small>{procurementClauses.length ? "已结构化" : "待从采购模板建立"}</small>
        </article>
        <article className="panel">
          <span>规则 / 案例 / 模板</span>
          <strong>{knowledgeEntries.length}</strong>
          <small>可检索知识条目</small>
        </article>
      </div>
      <div className="knowledge-tabs" role="tablist" aria-label="知识库分类">
        {([
          ["all", `全部 (${rows.length})`],
          ["clauses", `标准条款 (${standardClauses.length})`],
          ["租赁", `租赁条款 (${leaseClauses.length})`],
          ["采购", `采购条款 (${procurementClauses.length})`],
          ["knowledge", `知识条目 (${knowledgeEntries.length})`],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            className={section === value ? "active" : ""}
            onClick={() => setSection(value)}
            role="tab"
            aria-selected={section === value}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="knowledge-grid">
        {visibleRows.map((item) => (
          <article className={`panel knowledge-card ${item.is_standard_clause ? "clause-card" : ""}`} key={item.id}>
            <header>
              <div className="knowledge-card-label">
                <span className="type-tag">{item.is_standard_clause ? "标准条款" : item.entry_type}</span>
                {item.is_standard_clause && <b>第 {item.clause_no} 条</b>}
              </div>
              <StatusPill value={item.risk_level} risk />
            </header>
            <h2>{item.is_standard_clause ? item.category : item.title}</h2>
            <p className={item.is_standard_clause ? "clause-content" : ""}>{item.content}</p>
            <footer>
              <span>
                {item.is_standard_clause
                  ? `${item.contract_type} · 基准版 ${item.baseline_version}`
                  : item.category}
              </span>
              <small>{item.is_standard_clause ? item.source_file || item.source : item.source}</small>
            </footer>
            <div>
              {item.tags.map((tag) => (
                <i key={tag}>#{tag}</i>
              ))}
            </div>
          </article>
        ))}
      </div>
      {!visibleRows.length && (
        <Empty
          title={section === "采购" ? "采购标准条款库尚未建立" : "暂无匹配内容"}
          text={section === "采购" ? "可以从 KSOCM 采购合同模板导入并结构化生成采购条款库。" : "请调整分类或搜索关键词。"}
        />
      )}
    </>
  );
}

function ReportsView({ data }: { data: Report | null }) {
  if (!data) return <Spinner />;
  const max = Math.max(...data.risk_categories.map((item) => item.value), 1);
  return (
    <>
      <PageHead
        eyebrow="数据分析"
        title="历史风险报告"
        text="从合同、客户和风险类别三个维度，复盘问题分布与建议处置。"
      />
      <div className="kpi-grid report-kpis">
        <article className="kpi">
          <div>
            <span>纳管合同</span>
            <strong>{data.kpis.contracts}</strong>
            <small>份</small>
          </div>
        </article>
        <article className="kpi">
          <div>
            <span>合同总金额</span>
            <strong>{fmtMoney(data.kpis.amount)}</strong>
            <small>累计业务规模</small>
          </div>
        </article>
        <article className="kpi">
          <div>
            <span>高风险合同</span>
            <strong>{data.kpis.high_risk}</strong>
            <small>需重点跟进</small>
          </div>
        </article>
        <article className="kpi">
          <div>
            <span>已处置建议</span>
            <strong>{data.kpis.resolved_suggestions}</strong>
            <small>接纳 / 修改 / 拒绝</small>
          </div>
        </article>
      </div>
      <div className="two-col report-grid">
        <section className="panel padded">
          <div className="panel-head">
            <div>
              <h2>风险类别排行</h2>
              <p>知识库命中频次</p>
            </div>
          </div>
          <div className="category-chart">
            {data.risk_categories.map((item, index) => (
              <div key={item.label}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{item.label}</strong>
                <div>
                  <i style={{ width: `${(item.value / max) * 100}%` }} />
                </div>
                <b>{item.value}</b>
              </div>
            ))}
          </div>
        </section>
        <section className="panel padded">
          <div className="panel-head">
            <div>
              <h2>客户风险预警</h2>
              <p>按历史高风险合同聚合</p>
            </div>
          </div>
          {data.customer_warnings.length ? (
            <div className="warning-list">
              {data.customer_warnings.map((item) => (
                <div key={item.customer}>
                  <span>{item.customer.slice(0, 1)}</span>
                  <div>
                    <strong>{item.customer}</strong>
                    <small>历史高风险合同 {item.count} 份</small>
                  </div>
                  <StatusPill value={item.level} risk />
                </div>
              ))}
            </div>
          ) : (
            <Empty title="暂无客户预警" text="当前客户未形成重复高风险记录。" />
          )}
        </section>
      </div>
    </>
  );
}

function AuditView({ rows }: { rows: Audit[] }) {
  return (
    <>
      <PageHead
        eyebrow="系统记录"
        title="审计日志"
        text="记录登录、上传、审核决策、协同、审批与导出动作，满足追溯要求。"
      />
      <section className="panel table-panel">
        {rows.length ? (
          <div className="audit-list">
            {rows.map((item) => (
              <article key={item.id}>
                <span className="audit-avatar">
                  {item.actor_name.slice(0, 1)}
                </span>
                <div>
                  <strong>
                    {item.actor_name} · {item.action}
                  </strong>
                  <p>
                    {item.object_type}
                    {item.object_id ? ` / ${item.object_id.slice(0, 16)}` : ""}
                  </p>
                </div>
                <code>
                  {Object.keys(item.detail || {}).length
                    ? JSON.stringify(item.detail)
                    : "—"}
                </code>
                <small>
                  {fmtDate(item.created_at)}
                  <br />
                  {item.ip_address}
                </small>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="没有可显示的审计日志"
            text="当前角色可能没有审计权限，或系统尚未产生操作记录。"
          />
        )}
      </section>
    </>
  );
}

function UploadModal({
  files,
  setFiles,
  customer,
  setCustomer,
  project,
  setProject,
  contractId,
  contractType,
  setContractType,
  ourRole,
  setOurRole,
  documentComplete,
  setDocumentComplete,
  legalAsOfDate,
  setLegalAsOfDate,
  documentSource,
  setDocumentSource,
  sourceDepartment,
  setSourceDepartment,
  roundNo,
  busy,
  onClose,
  onSubmit,
}: {
  files: File[];
  setFiles: (files: File[]) => void;
  customer: string;
  setCustomer: (v: string) => void;
  project: string;
  setProject: (v: string) => void;
  contractId: string;
  contractType: "采购" | "租赁";
  setContractType: (v: "采购" | "租赁") => void;
  ourRole: "采购方" | "供应方" | "出租方" | "承租方";
  setOurRole: (v: "采购方" | "供应方" | "出租方" | "承租方") => void;
  documentComplete: boolean;
  setDocumentComplete: (v: boolean) => void;
  legalAsOfDate: string;
  setLegalAsOfDate: (v: string) => void;
  documentSource: string;
  setDocumentSource: (v: string) => void;
  sourceDepartment: string;
  setSourceDepartment: (v: string) => void;
  roundNo: number;
  busy: boolean;
  onClose: () => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const internalSource = documentSource !== "客户" && documentSource !== "未知";
  return (
    <div className="modal-wrap">
      <button
        className="modal-scrim"
        onClick={onClose}
        disabled={busy}
        aria-label="关闭"
      />
      <section className="modal">
        <header>
          <div>
            <p className="eyebrow">
              {contractId ? `第 ${roundNo} 轮合同` : "新合同导入"}
            </p>
            <h2>{contractId ? "上传本轮谈判版本" : "新建采购 / 租赁合同"}</h2>
          </div>
          <button onClick={onClose} disabled={busy}>
            ×
          </button>
        </header>
        <form onSubmit={onSubmit} aria-busy={busy}>
          <fieldset disabled={busy}>
            <label className="drop-zone">
              <input
                type="file"
                multiple={!contractId}
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
                accept=".doc,.docx,.pdf,.xls,.xlsx,.txt,.png,.jpg,.jpeg"
              />
              <span>选择文件</span>
              <strong>
                {contractId ? "选择本轮唯一主合同" : "拖入文件或点击此处选择"}
              </strong>
              <small>
                {contractId
                  ? "每轮上传一份可能带客户/同事批注的 Word 或 PDF"
                  : "新合同可批量导入；单个不超过 80MB"}
              </small>
            </label>
            {files.length > 0 && (
              <div className="file-chips">
                {files.map((file) => (
                  <span key={`${file.name}-${file.size}`}>
                    {file.name}
                    <small>{(file.size / 1024).toFixed(0)} KB</small>
                  </span>
                ))}
              </div>
            )}
            <div className="form-row">
              <label>
                合同业务线
                <select
                  value={contractType}
                  onChange={(e) => {
                    const nextType = e.target.value as "采购" | "租赁";
                    setContractType(nextType);
                    setOurRole(nextType === "租赁" ? "出租方" : "采购方");
                  }}
                  disabled={Boolean(contractId) || busy}
                >
                  <option value="采购">采购合同</option>
                  <option value="租赁">租赁合同</option>
                </select>
              </label>
              <label>
                我方立场
                <select
                  value={ourRole}
                  onChange={(e) =>
                    setOurRole(
                      e.target.value as "采购方" | "供应方" | "出租方" | "承租方",
                    )
                  }
                  disabled={Boolean(contractId) || busy}
                >
                  {contractType === "租赁" ? (
                    <>
                      <option value="出租方">出租方</option>
                      <option value="承租方">承租方</option>
                    </>
                  ) : (
                    <>
                      <option value="采购方">采购方</option>
                      <option value="供应方">供应方</option>
                    </>
                  )}
                </select>
              </label>
              <label>
                文件来源
                <select
                  value={documentSource}
                  onChange={(e) => {
                    setDocumentSource(e.target.value);
                    if (e.target.value.endsWith("部"))
                      setSourceDepartment(e.target.value);
                  }}
                >
                  <option value="客户">客户</option>
                  <option value="法务部">内部 · 法务部</option>
                  <option value="财务部">内部 · 财务部</option>
                  <option value="销售部">内部 · 销售部</option>
                  <option value="合同管理部">内部 · 合同管理部</option>
                  <option value="ABU">内部 · ABU</option>
                  <option value="其他内部">其他内部来源</option>
                  <option value="未知">暂不确定</option>
                </select>
              </label>
              <label>
                客户名称
                <input
                  value={customer}
                  onChange={(e) => setCustomer(e.target.value)}
                  placeholder="可留空，系统自动抽取"
                  disabled={Boolean(contractId) || busy}
                />
              </label>
              <label>
                关联项目
                <input
                  value={project}
                  onChange={(e) => setProject(e.target.value)}
                  placeholder="例如：华南数据中心扩容"
                  disabled={Boolean(contractId) || busy}
                />
              </label>
              <label>
                法律适用日期
                <input
                  type="date"
                  value={legalAsOfDate}
                  onChange={(e) => setLegalAsOfDate(e.target.value)}
                  required
                />
              </label>
              {internalSource && (
                <label>
                  来源部门
                  <input
                    value={sourceDepartment}
                    onChange={(e) => setSourceDepartment(e.target.value)}
                    placeholder="用于识别未映射的批注作者"
                  />
                </label>
              )}
            </div>
            <div className="source-hint">
              系统会优先读取 Word/PDF
              批注作者；员工账号映射为同事，部门关键词映射为内部部门，其余结合本轮文件来源判断并显示置信度。
            </div>
            <label className="source-hint">
              <input
                type="checkbox"
                checked={documentComplete}
                onChange={(event) => setDocumentComplete(event.target.checked)}
              />{" "}
              已确认主合同、一般性条款、报价单及关键附件齐全。未勾选时，系统不会把检索空结果认定为真实缺失。
            </label>
          </fieldset>
          <div className="modal-actions">
            <button
              type="button"
              className="secondary"
              onClick={onClose}
              disabled={busy}
            >
              取消
            </button>
            <button className="primary" disabled={!files.length || busy}>
              {busy
                ? "正在上传并解析…"
                : `上传并解析 ${files.length ? `(${files.length})` : ""}`}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function CompareModal({
  data,
  onClose,
}: {
  data: { summary: string; changes: { type: string; text: string }[] };
  onClose: () => void;
}) {
  return (
    <div className="modal-wrap">
      <button className="modal-scrim" onClick={onClose} aria-label="关闭" />
      <section className="modal compare-modal">
        <header>
          <div>
            <p className="eyebrow">版本对比</p>
            <h2>最近两版差异</h2>
          </div>
          <button onClick={onClose}>×</button>
        </header>
        <div className="compare-summary">{data.summary}</div>
        <div className="diff-list">
          {data.changes.map((item, index) => (
            <p className={item.type} key={index}>
              <span>{item.type === "add" ? "+" : "−"}</span>
              {item.text}
            </p>
          ))}
        </div>
        <div className="modal-actions">
          <button className="primary" onClick={onClose}>
            完成核对
          </button>
        </div>
      </section>
    </div>
  );
}

function ContractPreviewModal({
  data,
  fileUrl,
  loading,
  onClose,
}: {
  data: PreviewData | null;
  fileUrl: string;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <div className="modal-wrap preview-modal-wrap">
      <button
        className="modal-scrim"
        onClick={onClose}
        aria-label="关闭合同预览"
      />
      <section className="modal contract-preview-modal">
        <header>
          <div>
            <p className="eyebrow">
              {data ? `R${data.round_no} 独立版本` : "合同预览"}
            </p>
            <h2>
              {data ? `第 ${data.round_no} 轮合同与批注` : "正在读取文件"}
            </h2>
            {data && (
              <p className="preview-file-meta">
                {data.file_name} ·{" "}
                {data.is_annotated
                  ? "已展示 AI 回写批注版"
                  : "本轮尚未审核，展示上传原件"}
              </p>
            )}
          </div>
          <button onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>
        {loading || !data ? (
          <div className="preview-loading">
            <span className="spinner" />
            正在生成网页预览…
          </div>
        ) : (
          <>
            <div className="preview-legend">
              <span>
                <i className="legend-original" />
                原文件高亮（保留原样式）
              </span>
              <span>
                <i className="legend-ai" />
                系统 AI 问题（统一青蓝色）
              </span>
              <b>{data.annotation_status}</b>
            </div>
            <div className="preview-layout">
              <section className="preview-document" aria-label="合同正文预览">
                {data.format === "pdf" ? (
                  <PdfDocumentViewer fileUrl={fileUrl} />
                ) : (
                  <div
                    className="docx-web-preview"
                    dangerouslySetInnerHTML={{ __html: data.html }}
                  />
                )}
              </section>
              <aside className="preview-comments">
                <header>
                  <div>
                    <strong>批注与审核意见</strong>
                    <span>
                      本轮 {data.annotations.length} 条 · 原文件内嵌{" "}
                      {data.embedded_comment_count} 条
                    </span>
                  </div>
                  <span className="round-badge">R{data.round_no}</span>
                </header>
                {data.annotations.length ? (
                  <div className="preview-comment-list">
                    {data.annotations.map((item, index) => (
                      <article
                        key={`${item.kind}-${item.id}-${index}`}
                        style={{
                          borderLeftColor:
                            item.kind === "AI审核" || item.kind === "专项检查"
                              ? data.round_color
                              : "#e3bd3e",
                        }}
                      >
                        <div className="preview-comment-head">
                          <span
                            className={
                              item.kind === "AI审核" || item.kind === "专项检查"
                                ? "comment-kind ai"
                                : "comment-kind original"
                            }
                          >
                            {item.kind}
                          </span>
                          {item.risk_level && (
                            <StatusPill value={item.risk_level} risk />
                          )}
                        </div>
                        <h3>{item.title || item.comment_text || "批注"}</h3>
                        <p className="comment-author">
                          {item.author_name || "未署名"}
                          {item.source_department
                            ? ` · ${item.source_department}`
                            : ""}
                          {item.page_no ? ` · 第 ${item.page_no} 页` : ""}
                        </p>
                        {item.anchor_text && (
                          <blockquote>{item.anchor_text}</blockquote>
                        )}
                        {item.kind !== "AI审核" && item.kind !== "专项检查" && item.comment_text && (
                          <p>{item.comment_text}</p>
                        )}
                        {item.suggested_text && (
                          <div className="preview-suggestion">
                            <strong>建议修改</strong>
                            <p>{item.suggested_text}</p>
                          </div>
                        )}
                        {item.basis && (
                          <details>
                            <summary>查看依据与谈判重点</summary>
                            <p>{item.basis}</p>
                            {item.negotiation_focus && (
                              <p>{item.negotiation_focus}</p>
                            )}
                          </details>
                        )}
                      </article>
                    ))}
                  </div>
                ) : (
                  <Empty title="本轮暂无批注" text="可直接核对左侧合同正文。" />
                )}
              </aside>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function PdfDocumentViewer({
  fileUrl,
  focusPage,
  focusRiskId,
  riskAnnotations = [],
  onRiskClick,
}: {
  fileUrl: string;
  focusPage?: number;
  focusRiskId?: string;
  riskAnnotations?: PreviewAnnotation[];
  onRiskClick?: (riskId: string) => void;
}) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [zoom, setZoom] = useState(1.15);
  const [error, setError] = useState("");
  const [renderedPages, setRenderedPages] = useState<Set<number>>(
    () => new Set(),
  );
  const viewerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!fileUrl) return;
    let cancelled = false;
    let loadingTask: ReturnType<
      (typeof import("pdfjs-dist"))["getDocument"]
    > | null = null;
    void import("pdfjs-dist")
      .then((pdfjs) => {
        pdfjs.GlobalWorkerOptions.workerSrc = `${window.location.origin}/pdf.worker.min.mjs`;
        loadingTask = pdfjs.getDocument({ url: fileUrl });
        return loadingTask.promise;
      })
      .then((pdf) => {
        if (!cancelled) {
          setRenderedPages(new Set());
          setDocument(pdf);
        }
      })
      .catch((reason) => {
        if (!cancelled)
          setError(reason instanceof Error ? reason.message : "PDF 解析失败");
      });
    return () => {
      cancelled = true;
      if (loadingTask) void loadingTask.destroy();
    };
  }, [fileUrl]);
  useEffect(() => {
    if (!focusPage || !document) return;
    const riskTargets = Array.from(
      viewerRef.current?.querySelectorAll<HTMLElement>("[data-pdf-risk-id]") || [],
    );
    const riskTarget = riskTargets.find(
      (item) => item.dataset.pdfRiskId === focusRiskId,
    );
    const target =
      riskTarget ||
      viewerRef.current?.querySelector<HTMLElement>(
        `[data-pdf-page="${focusPage}"]`,
      );
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [document, focusPage, focusRiskId, riskAnnotations]);
  const markRendered = useCallback(
    (pageNo: number) =>
      setRenderedPages((current) =>
        current.has(pageNo) ? current : new Set(current).add(pageNo),
      ),
    [],
  );
  if (error)
    return <div className="preview-loading error">PDF 预览失败：{error}</div>;
  if (!document)
    return (
      <div className="preview-loading">
        <span className="spinner" />
        PDF.js 正在读取文件…
      </div>
    );
  const progress = Math.round((renderedPages.size / document.numPages) * 100);
  return (
    <div className="pdf-js-viewer" ref={viewerRef}>
      <header className="pdf-toolbar">
        <span>
          PDF · {document.numPages} 页{" "}
          <i>
            已渲染 {renderedPages.size}/{document.numPages} 页
          </i>
        </span>
        <div>
          <button
            onClick={() => {
              setRenderedPages(new Set());
              setZoom((value) => Math.max(0.65, value - 0.15));
            }}
            aria-label="缩小 PDF"
          >
            −
          </button>
          <b>{Math.round(zoom * 100)}%</b>
          <button
            onClick={() => {
              setRenderedPages(new Set());
              setZoom((value) => Math.min(2.2, value + 0.15));
            }}
            aria-label="放大 PDF"
          >
            +
          </button>
        </div>
      </header>
      <div
        className="pdf-render-progress"
        aria-label={`PDF 已渲染 ${progress}%`}
      >
        <i style={{ width: `${progress}%` }} />
      </div>
      <div className="pdf-canvas-pages">
        {Array.from({ length: document.numPages }, (_, index) => (
          <PdfCanvasPage
            document={document}
            pageNo={index + 1}
            zoom={zoom}
            onRendered={markRendered}
            riskAnnotations={riskAnnotations}
            selectedRiskId={focusRiskId}
            onRiskClick={onRiskClick}
            key={index}
          />
        ))}
      </div>
    </div>
  );
}

function PdfCanvasPage({
  document,
  pageNo,
  zoom,
  onRendered,
  riskAnnotations,
  selectedRiskId,
  onRiskClick,
}: {
  document: PDFDocumentProxy;
  pageNo: number;
  zoom: number;
  onRendered: (pageNo: number) => void;
  riskAnnotations: PreviewAnnotation[];
  selectedRiskId?: string;
  onRiskClick?: (riskId: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    void document
      .getPage(pageNo)
      .then((page) => {
        if (cancelled || !canvasRef.current) return;
        const canvas = canvasRef.current;
        const viewport = page.getViewport({ scale: zoom });
        const outputScale = Math.min(window.devicePixelRatio || 1, 1.6);
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        renderTask = page.render({
          canvas,
          viewport,
          transform:
            outputScale === 1
              ? undefined
              : [outputScale, 0, 0, outputScale, 0, 0],
        });
        return renderTask.promise;
      })
      .then(() => {
        if (!cancelled) onRendered(pageNo);
      })
      .catch((reason) => {
        if (
          !cancelled &&
          !(
            reason instanceof Error &&
            reason.name === "RenderingCancelledException"
          )
        )
          console.error(reason);
      });
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [document, pageNo, zoom, onRendered]);
  const pageRisks = riskAnnotations.flatMap((annotation) =>
    (annotation.locations || [])
      .filter((location) => location.page_no === pageNo)
      .map((location, index) => ({ annotation, location, index })),
  );
  return (
    <figure className="pdf-canvas-page" data-pdf-page={pageNo}>
      <canvas ref={canvasRef} aria-label={`PDF 第 ${pageNo} 页`} />
      {pageRisks.length > 0 && (
        <div className="pdf-risk-layer" aria-label={`第 ${pageNo} 页风险原文`}>
          {pageRisks.map(({ annotation, location, index }) => (
            <button
              type="button"
              className={`pdf-risk-source ${selectedRiskId === annotation.id ? "selected" : ""}`}
              data-pdf-risk-id={annotation.id}
              aria-label={`定位到风险项：${annotation.title}`}
              title={`${annotation.title}（点击定位到右侧风险项）`}
              style={{
                left: `${location.x}%`,
                top: `${location.y}%`,
                width: `${location.width}%`,
                height: `${location.height}%`,
              }}
              onClick={() => onRiskClick?.(annotation.id)}
              key={`${annotation.id}-${index}`}
            />
          ))}
        </div>
      )}
      <figcaption>
        {pageNo} / {document.numPages}
      </figcaption>
    </figure>
  );
}
