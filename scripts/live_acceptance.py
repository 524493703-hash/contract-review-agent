from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pymysql
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "e2e"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_JSON = OUTPUT_DIR / "live-acceptance.json"
REPORT_MD = OUTPUT_DIR / "template-acceptance-report.md"
DEFAULT_TEST_DATABASE = "contract_review_test"


def load_local_environment() -> None:
    for source in (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"):
        if not source.exists():
            continue
        for raw_line in source.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def prepare_database() -> str:
    source_url = make_url(os.environ["DATABASE_URL"])
    source_database = source_url.database or ""
    database_name = os.environ.get("TEST_DATABASE_NAME", DEFAULT_TEST_DATABASE).strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise RuntimeError("TEST_DATABASE_NAME may contain only letters, numbers, and underscores")
    if not database_name.endswith("_test"):
        raise RuntimeError("The acceptance database name must end with '_test'")
    if database_name == source_database:
        raise RuntimeError("The acceptance database must be different from the production database")
    connection = pymysql.connect(
        host=source_url.host,
        port=source_url.port or 3306,
        user=source_url.username,
        password=source_url.password,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=20,
    )
    try:
        with connection.cursor() as cursor:
            # The full acceptance suite always starts from a clean, fixed test
            # database. Production data remains in the DATABASE_URL database.
            cursor.execute(f"DROP DATABASE IF EXISTS `{database_name}`")
            cursor.execute(
                f"CREATE DATABASE `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()
    os.environ["DATABASE_URL"] = source_url.set(database=database_name).render_as_string(hide_password=False)
    os.environ["ENVIRONMENT"] = "e2e"
    os.environ["UPLOAD_DIR"] = str(OUTPUT_DIR / database_name / "uploads")
    os.environ["EXPORT_DIR"] = str(OUTPUT_DIR / database_name / "exports")
    return database_name


load_local_environment()
DATABASE_NAME = prepare_database()
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ContractVersion, WebsiteTermsSnapshot  # noqa: E402


TEMPLATE_DIRS = (
    WORKSPACE_ROOT / "KSOCM_合同模板",
    WORKSPACE_ROOT / "POC合同模板（租赁）",
)

EXPECTED_FILES = {
    "1.客版新客户WORD.docx": {"type": "销售", "min_chars": 7500, "keywords": ["设备采购合同", "甲方"]},
    "2.客版新客户PDF.pdf": {"type": "销售", "min_chars": 8500, "keywords": ["采购合同", "福建金石"]},
    "3.客版老客户PDF.pdf": {"type": "销售", "min_chars": 5200, "keywords": ["P60", "元翔空运"]},
    "4.PDF简单版带背面条款.pdf": {"type": "销售", "min_chars": 3500, "keywords": ["采购订单", "ZEISS"]},
    "5.PO带客户官网地址PDF1.pdf": {"type": "销售", "min_chars": 2500, "keywords": ["purchaseorder", "bosch.com"], "url": True},
    "6.PO带客户官网链接PDF.PDF": {"type": "销售", "min_chars": 500, "keywords": ["采购订单", "voss.net"], "url": True},
    "7.ABU业务WORD.doc": {"type": "销售", "min_chars": 10000, "keywords": ["移动机器人采购合同", "林德"]},
    "8.林德标版合同背面条款供参考.jpg": {"type": "销售", "min_chars": 2600, "keywords": ["设备销售", "违约责任"], "template": "标准合同"},
    "1- 关联企业已签章历史合同 脱敏.pdf": {"type": "租赁", "min_chars": 8000, "keywords": ["叉车租赁合同", "关联方"]},
    "1-客户版待偏离  脱敏.docx": {"type": "租赁", "min_chars": 28000, "keywords": ["DDBB", "叉车租赁"]},
    "1-已签章历史合同 脱敏.pdf": {"type": "租赁", "min_chars": 25000, "keywords": ["德邦", "叉车租赁"]},
    "2-客户版待偏离 脱敏.docx": {"type": "租赁", "min_chars": 8500, "keywords": ["叉车租赁框架合同", "上海"]},
    "3-一般性条款客户偏离带图片 脱敏.docx": {"type": "租赁", "min_chars": 2000, "keywords": ["出租方的权利和义务", "文档图片OCR"]},
    "4- 林德版合同特别条款 脱敏.xls": {"type": "租赁", "min_chars": 4400, "keywords": ["Terms of Payment", "承租方"], "template": "标准合同"},
    "4-CHN-林德（中国）叉车有限公司设备租赁合同的一般性条款--2025年01版.pdf": {"type": "租赁", "min_chars": 7000, "keywords": ["设备租赁合同的一般性条款", "General Terms"], "template": "标准合同"},
    "5-客户版待偏离 脱敏.pdf": {"type": "租赁", "min_chars": 6500, "keywords": ["租赁协议", "GOLDE"]},
    "5-已签章历史合同 脱敏.pdf": {"type": "租赁", "min_chars": 18000, "keywords": ["租赁协议", "林德"]},
    "6-一般性条款 - 客户批注版.pdf": {"type": "租赁", "min_chars": 8500, "keywords": ["一般性条款", "PDF批注"], "template": "标准合同（有偏离）"},
    "7-客户版待偏离 脱敏.doc": {"type": "租赁", "min_chars": 14000, "keywords": ["云牌", "租赁服务项目"]},
}


class Acceptance:
    def __init__(self) -> None:
        self.report = {
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "database": DATABASE_NAME,
            "checks": [],
            "files": [],
            "reviews": [],
            "flow": {},
            "summary": {},
        }

    def persist(self) -> None:
        REPORT_JSON.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(self, section: str, name: str, passed: bool, evidence: object = "") -> bool:
        item = {"section": section, "name": name, "passed": bool(passed), "evidence": evidence}
        self.report["checks"].append(item)
        print(f"[{'PASS' if passed else 'FAIL'}] {section} :: {name}", flush=True)
        self.persist()
        return bool(passed)

    def finish(self) -> None:
        checks = self.report["checks"]
        self.report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self.report["summary"] = {
            "total_checks": len(checks),
            "passed": sum(item["passed"] for item in checks),
            "failed": sum(not item["passed"] for item in checks),
            "files": len(self.report["files"]),
            "reviews": len(self.report["reviews"]),
        }
        self.persist()
        self.write_markdown()

    def write_markdown(self) -> None:
        summary = self.report["summary"]
        lines = [
            "# 合同审核智能体全量验收报告",
            "",
            f"- 验收时间：{self.report['started_at']} 至 {self.report.get('finished_at', '')}",
            f"- 独立 MySQL 验收库：`{DATABASE_NAME}`",
            f"- 检查项：{summary.get('total_checks', 0)}，通过 {summary.get('passed', 0)}，失败 {summary.get('failed', 0)}",
            "",
            "## 文件识别与首轮审核",
            "",
            "| 文件 | 格式 | 字符数 | 类型 | 解析 | 首轮建议 | 模板判断 | 结果 |",
            "|---|---:|---:|---|---|---:|---|---|",
        ]
        review_by_file = {item["file"]: item for item in self.report["reviews"]}
        for item in self.report["files"]:
            review = review_by_file.get(item["file"], {})
            passed = item.get("passed") and review.get("passed")
            lines.append(
                f"| {item['file']} | {item['extension']} | {item['chars']} | {item['contract_type']} | "
                f"{item['parse_status']} | {review.get('suggestions', '-')} | {review.get('template_type', '-')} | "
                f"{'通过' if passed else '失败/待核'} |"
            )
        failed = [item for item in self.report["checks"] if not item["passed"]]
        lines.extend(["", "## 未通过检查", ""])
        if failed:
            lines.extend(f"- **{item['section']} / {item['name']}**：{item['evidence']}" for item in failed)
        else:
            lines.append("- 无")
        lines.extend(["", "## 完整流程与权限", ""])
        by_section: dict[str, list[dict]] = {}
        for item in self.report["checks"]:
            if item["section"] in {"文件识别", "逐文件审核"}:
                continue
            by_section.setdefault(item["section"], []).append(item)
        for section, items in by_section.items():
            lines.append(f"### {section}")
            lines.append("")
            lines.extend(f"- {'通过' if item['passed'] else '失败'}：{item['name']}" for item in items)
            lines.append("")
        REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def auth_headers(tokens: dict[str, str], username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens[username]}"}


def get_version_text(version_id: str) -> str:
    with SessionLocal() as db:
        version = db.get(ContractVersion, version_id)
        return version.extracted_text if version else ""


def main() -> int:
    acceptance = Acceptance()
    template_paths = [path for directory in TEMPLATE_DIRS for path in sorted(directory.iterdir()) if path.is_file()]
    acceptance.check("清单", "两套目录共19个模板文件", len(template_paths) == 19, [path.name for path in template_paths])
    acceptance.check("清单", "每个模板都有预期识别基线", all(path.name in EXPECTED_FILES for path in template_paths), "")

    with TestClient(app) as client:
        users_response = client.get("/api/auth/demo-users")
        acceptance.check("账号", "演示账号接口可用", users_response.status_code == 200, users_response.status_code)
        demo_users = users_response.json()["users"]
        tokens: dict[str, str] = {}
        users = {item["username"]: item for item in demo_users}
        expected_users = {
            "contract.admin",
            "legal.reviewer",
            "sales.owner",
            "approver",
            "finance.expert",
            "system.admin",
        }
        acceptance.check("账号", "六类角色账号齐全", set(users) == expected_users, sorted(users))
        for username in sorted(expected_users):
            response = client.post("/api/auth/login", json={"username": username, "password": "Poc@2026"})
            acceptance.check("账号", f"{username} 登录", response.status_code == 200, response.status_code)
            if response.status_code == 200:
                tokens[username] = response.json()["access_token"]
                me = client.get("/api/auth/me", headers=auth_headers(tokens, username))
                acceptance.check("账号", f"{username} 身份信息一致", me.status_code == 200 and me.json()["username"] == username, me.status_code)
        unauthorized = client.get("/api/contracts")
        acceptance.check("权限", "未登录访问合同被拦截", unauthorized.status_code == 401, unauthorized.status_code)

        # Upload each source independently so a format-specific failure cannot
        # hide results already produced for other files. Batch upload is tested
        # separately below with two files in one request.
        upload_pairs: list[tuple[Path, dict]] = []
        for index, path in enumerate(template_paths, start=1):
            print(f"[INFO] 上传解析 {index}/19: {path.name}", flush=True)
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            started = time.perf_counter()
            response = client.post(
                "/api/contracts/upload",
                headers=auth_headers(tokens, "legal.reviewer"),
                data={"customer": "", "project": "模板全量识别验收", "note": "自动化全量验收"},
                files=[("files", (path.name, path.read_bytes(), mime))],
            )
            body = response.json() if response.status_code == 200 else []
            accepted = response.status_code == 200 and len(body) == 1
            acceptance.check(
                "文件上传",
                path.name,
                accepted,
                {"status": response.status_code, "seconds": round(time.perf_counter() - started, 1)},
            )
            if accepted:
                upload_pairs.append((path, body[0]))
        acceptance.check("文件识别", "19个模板均生成独立合同记录", len(upload_pairs) == 19, len(upload_pairs))
        batch_payload = "批量上传验收合同\n甲方：批量客户\n乙方：林德（中国）叉车有限公司".encode("utf-8")
        batch_response = client.post(
            "/api/contracts/upload",
            headers=auth_headers(tokens, "sales.owner"),
            data={"customer": "批量客户", "project": "批量上传验收"},
            files=[
                ("files", ("batch-a.txt", batch_payload, "text/plain")),
                ("files", ("batch-b.txt", batch_payload, "text/plain")),
            ],
        )
        acceptance.check(
            "文件上传",
            "双文件批量上传",
            batch_response.status_code == 200 and len(batch_response.json()) == 2,
            batch_response.status_code,
        )
        contract_by_file: dict[str, dict] = {}
        for path, row in upload_pairs:
            expected = EXPECTED_FILES[path.name]
            contract = row["contract"]
            text = get_version_text(row["version_id"])
            folded = text.casefold().replace(" ", "")
            keyword_hits = {
                keyword: keyword.casefold().replace(" ", "") in folded for keyword in expected["keywords"]
            }
            url_ok = not expected.get("url") or bool(contract.get("website_terms_url"))
            passed = (
                row["parse_status"] == "已解析"
                and len(text) >= expected["min_chars"]
                and contract["contract_type"] == expected["type"]
                and all(keyword_hits.values())
                and url_ok
            )
            file_result = {
                "folder": path.parent.name,
                "file": path.name,
                "extension": path.suffix.lower(),
                "parse_status": row["parse_status"],
                "parse_message": row.get("parse_message", ""),
                "chars": len(text),
                "min_chars": expected["min_chars"],
                "contract_id": contract["id"],
                "version_id": row["version_id"],
                "contract_no": contract["contract_no"],
                "name": contract["name"],
                "customer": contract["customer"],
                "contract_type": contract["contract_type"],
                "website_terms_url": contract.get("website_terms_url", ""),
                "keyword_hits": keyword_hits,
                "passed": passed,
            }
            acceptance.report["files"].append(file_result)
            acceptance.check("文件识别", path.name, passed, file_result)
            contract_by_file[path.name] = file_result

        # Every source file must enter the actual rule+knowledge+LLM review flow.
        for index, path in enumerate(template_paths, start=1):
            item = contract_by_file.get(path.name)
            if not item:
                continue
            print(f"[INFO] 首轮审核 {index}/19: {path.name}", flush=True)
            started = time.perf_counter()
            response = client.post(
                f"/api/contracts/{item['contract_id']}/review",
                headers=auth_headers(tokens, "legal.reviewer"),
            )
            elapsed = round(time.perf_counter() - started, 1)
            review_result = {
                "file": path.name,
                "status": response.status_code,
                "seconds": elapsed,
                "suggestions": 0,
                "template_type": "",
                "engine": "",
                "passed": False,
            }
            if response.status_code == 200:
                body = response.json()
                detail = client.get(
                    f"/api/contracts/{item['contract_id']}",
                    headers=auth_headers(tokens, "legal.reviewer"),
                ).json()
                run = detail["review_runs"][0]
                suggestions = run["suggestions"]
                required_fields = ("title", "risk_level", "original_text", "suggested_text", "basis", "negotiation_focus")
                structurally_complete = bool(suggestions) and all(
                    all(suggestion.get(field) for field in required_fields) for suggestion in suggestions
                )
                expected_template = EXPECTED_FILES[path.name].get("template")
                template_ok = not expected_template or body["template_type"] == expected_template
                model_completed = f"大模型（{os.environ.get('LLM_MODEL', '')}）" in run["engine"]
                review_result.update(
                    suggestions=len(suggestions),
                    template_type=body["template_type"],
                    engine=run["engine"],
                    stats=body["stats"],
                    model_completed=model_completed,
                    passed=structurally_complete and template_ok and model_completed,
                )
            acceptance.report["reviews"].append(review_result)
            acceptance.check("逐文件审核", path.name, review_result["passed"], review_result)

        # Role gate checks use a disposable text contract in the isolated DB.
        permission_text = (
            "设备销售合同\n合同编号：PERM-2026-001\n甲方：权限测试客户\n"
            "合同总金额：人民币400万元。验收后30日付款。甲方有权单方解除合同。"
        ).encode("utf-8")
        upload_statuses = {}
        permission_contract_id = ""
        for username in sorted(expected_users):
            response = client.post(
                "/api/contracts/upload",
                headers=auth_headers(tokens, username),
                data={"customer": "权限测试客户", "project": "权限矩阵"},
                files=[("files", (f"permission-{username}.txt", permission_text, "text/plain"))],
            )
            upload_statuses[username] = response.status_code
            if username == "contract.admin" and response.status_code == 200:
                permission_contract_id = response.json()[0]["contract"]["id"]
        expected_upload = {
            "contract.admin": 200,
            "legal.reviewer": 200,
            "sales.owner": 200,
            "approver": 403,
            "finance.expert": 403,
            "system.admin": 200,
        }
        acceptance.check("权限", "上传权限矩阵", upload_statuses == expected_upload, upload_statuses)

        if permission_contract_id:
            review_statuses = {
                username: client.post(
                    "/api/contracts/not-found/review",
                    headers=auth_headers(tokens, username),
                ).status_code
                for username in expected_users
            }
            expected_review = {
                "contract.admin": 404,
                "legal.reviewer": 404,
                "system.admin": 404,
                "sales.owner": 403,
                "approver": 403,
                "finance.expert": 403,
            }
            acceptance.check("权限", "AI审核角色门禁（系统管理员为超级管理员）", review_statuses == expected_review, review_statuses)
            legal_review = client.post(
                f"/api/contracts/{permission_contract_id}/review",
                headers=auth_headers(tokens, "contract.admin"),
            )
            acceptance.check("权限", "合同管理员可启动AI审核", legal_review.status_code == 200, legal_review.status_code)

            redaction_statuses = {
                username: client.get(
                    f"/api/contracts/{permission_contract_id}/redacted-preview",
                    headers=auth_headers(tokens, username),
                ).status_code
                for username in expected_users
            }
            expected_redaction = {
                "contract.admin": 200,
                "legal.reviewer": 200,
                "system.admin": 200,
                "sales.owner": 403,
                "approver": 403,
                "finance.expert": 403,
            }
            acceptance.check("权限", "敏感信息预览权限矩阵", redaction_statuses == expected_redaction, redaction_statuses)

            invalid_approval_statuses = {
                username: client.patch(
                    "/api/approvals/not-found",
                    headers=auth_headers(tokens, username),
                    json={"decision": "通过", "comment": "权限门禁"},
                ).status_code
                for username in expected_users
            }
            allowed_deciders = {"legal.reviewer", "finance.expert", "approver", "system.admin"}
            approval_gate_ok = all(
                status == (404 if username in allowed_deciders else 403)
                for username, status in invalid_approval_statuses.items()
            )
            acceptance.check("权限", "审批决策角色门禁", approval_gate_ok, invalid_approval_statuses)

        audit_statuses = {
            username: client.get("/api/audit-logs", headers=auth_headers(tokens, username)).status_code
            for username in expected_users
        }
        expected_audit = {
            "contract.admin": 200,
            "legal.reviewer": 200,
            "system.admin": 200,
            "sales.owner": 403,
            "approver": 403,
            "finance.expert": 403,
        }
        acceptance.check("权限", "审计日志权限矩阵", audit_statuses == expected_audit, audit_statuses)

        # Full five-round workflow on a representative long lease contract.
        flow_file = contract_by_file.get("1-客户版待偏离  脱敏.docx")
        if flow_file:
            flow_id = flow_file["contract_id"]
            first_version_id = flow_file["version_id"]
            assign = client.patch(
                f"/api/contracts/{flow_id}/assign",
                headers=auth_headers(tokens, "contract.admin"),
                json={"assignee_id": users["legal.reviewer"]["id"]},
            )
            acceptance.check("完整流程", "分配法务审核人", assign.status_code == 200, assign.status_code)

            detail = client.get(f"/api/contracts/{flow_id}", headers=auth_headers(tokens, "legal.reviewer")).json()
            first_suggestion = detail["review_runs"][0]["suggestions"][0]
            sales_decision = client.patch(
                f"/api/suggestions/{first_suggestion['id']}",
                headers=auth_headers(tokens, "sales.owner"),
                json={"decision": "接纳", "note": "越权测试"},
            )
            acceptance.check("权限", "销售不能处置AI建议", sales_decision.status_code == 403, sales_decision.status_code)
            legal_decision = client.patch(
                f"/api/suggestions/{first_suggestion['id']}",
                headers=auth_headers(tokens, "legal.reviewer"),
                json={"decision": "修改后接纳", "suggested_text": first_suggestion["suggested_text"] + "（验收确认）", "note": "法务验收"},
            )
            acceptance.check("完整流程", "法务修改后接纳AI建议", legal_decision.status_code == 200, legal_decision.status_code)

            consultation = client.post(
                f"/api/contracts/{flow_id}/consultations",
                headers=auth_headers(tokens, "legal.reviewer"),
                json={
                    "suggestion_id": first_suggestion["id"],
                    "assignee_id": users["finance.expert"]["id"],
                    "question": "请确认付款及租金风险是否可接受",
                    "due_hours": 24,
                },
            )
            consultation_id = consultation.json().get("id") if consultation.status_code == 200 else ""
            acceptance.check("完整流程", "法务发起跨部门询问", consultation.status_code == 200, consultation.status_code)
            wrong_answer = client.patch(
                f"/api/consultations/{consultation_id}/answer",
                headers=auth_headers(tokens, "sales.owner"),
                json={"answer": "越权答复"},
            )
            acceptance.check("权限", "非被询问人不能答复", wrong_answer.status_code == 403, wrong_answer.status_code)
            finance_answer = client.patch(
                f"/api/consultations/{consultation_id}/answer",
                headers=auth_headers(tokens, "finance.expert"),
                json={"answer": "建议将付款周期控制在45日内，并保留逾期利息。"},
            )
            acceptance.check("完整流程", "财务专家答复询问", finance_answer.status_code == 200, finance_answer.status_code)

            negotiation = client.post(
                f"/api/contracts/{flow_id}/negotiations",
                headers=auth_headers(tokens, "sales.owner"),
                json={
                    "suggestion_id": first_suggestion["id"],
                    "status": "客户二次偏离",
                    "customer_feedback": "客户接受付款修改，但不同意提前解约金调整。",
                    "internal_note": "需提交审批矩阵复核",
                },
            )
            acceptance.check("完整流程", "销售记录客户二次偏离", negotiation.status_code == 200, negotiation.status_code)

            # Round 2 uses a second real lease template; rounds 3-5 are compact
            # negotiation revisions so the five-round limit and diff engine are deterministic.
            second_path = WORKSPACE_ROOT / "POC合同模板（租赁）" / "1-已签章历史合同 脱敏.pdf"
            version_ids = [first_version_id]
            round2_upload = client.post(
                "/api/contracts/upload",
                headers=auth_headers(tokens, "legal.reviewer"),
                data={"contract_id": flow_id, "note": "第二轮谈判稿"},
                files=[("files", (second_path.name, second_path.read_bytes(), "application/pdf"))],
            )
            if round2_upload.status_code == 200:
                version_ids.append(round2_upload.json()[0]["version_id"])
            acceptance.check("完整流程", "同一合同上传第二个真实版本", round2_upload.status_code == 200, round2_upload.status_code)
            round2_review = client.post(
                f"/api/contracts/{flow_id}/review",
                headers=auth_headers(tokens, "legal.reviewer"),
            )
            round2_body = round2_review.json() if round2_review.status_code == 200 else {}
            acceptance.check(
                "完整流程",
                "第二轮审核生成版本偏离分析",
                round2_review.status_code == 200 and round2_body.get("round_no") == 2 and "首轮" not in round2_body.get("comparison_summary", ""),
                round2_body.get("comparison_summary", round2_review.status_code),
            )

            for round_no in (3, 4, 5):
                revision = (
                    f"叉车租赁框架合同 第{round_no}轮谈判稿\n"
                    "甲方：DDBB物流股份有限公司\n乙方：林德（中国）叉车有限公司\n"
                    f"第{round_no}轮客户反馈：付款周期调整为{30 + round_no * 5}日；租期届满须书面确认续租；"
                    "争议由合同履行地法院管辖。\n"
                ).encode("utf-8")
                upload = client.post(
                    "/api/contracts/upload",
                    headers=auth_headers(tokens, "legal.reviewer"),
                    data={"contract_id": flow_id, "note": f"第{round_no}轮谈判稿"},
                    files=[("files", (f"round-{round_no}.txt", revision, "text/plain"))],
                )
                if upload.status_code == 200:
                    version_ids.append(upload.json()[0]["version_id"])
                review = client.post(
                    f"/api/contracts/{flow_id}/review",
                    headers=auth_headers(tokens, "legal.reviewer"),
                )
                body = review.json() if review.status_code == 200 else {}
                acceptance.check(
                    "完整流程",
                    f"第{round_no}轮上传、审核与偏离记录",
                    upload.status_code == 200 and review.status_code == 200 and body.get("round_no") == round_no,
                    {"upload": upload.status_code, "review": review.status_code, "round": body.get("round_no")},
                )
            sixth = client.post(f"/api/contracts/{flow_id}/review", headers=auth_headers(tokens, "legal.reviewer"))
            acceptance.check("完整流程", "第六轮审核被五轮上限拦截", sixth.status_code == 400, sixth.status_code)

            compare = client.get(
                f"/api/contracts/{flow_id}/versions/compare",
                params={"left": version_ids[0], "right": version_ids[1]},
                headers=auth_headers(tokens, "legal.reviewer"),
            )
            compare_body = compare.json() if compare.status_code == 200 else {}
            acceptance.check("完整流程", "版本对比产生差异摘要", compare.status_code == 200 and bool(compare_body.get("changes")), {"status": compare.status_code, "changes": len(compare_body.get("changes", []))})

            consistency = client.get(f"/api/contracts/{flow_id}/consistency", headers=auth_headers(tokens, "legal.reviewer"))
            consistency_body = consistency.json() if consistency.status_code == 200 else {}
            acceptance.check("完整流程", "一致性校验覆盖最近版本和未处置风险", consistency.status_code == 200 and consistency_body.get("versions_checked") == 3 and bool(consistency_body.get("alerts")), consistency_body)

            redacted = client.get(f"/api/contracts/{flow_id}/redacted-preview", headers=auth_headers(tokens, "legal.reviewer"))
            acceptance.check("完整流程", "脱敏预览生成", redacted.status_code == 200 and "preview" in redacted.json(), redacted.status_code)

            notification = client.post(
                f"/api/contracts/{flow_id}/notifications",
                headers=auth_headers(tokens, "legal.reviewer"),
                json={"recipient": "poc@example.com", "subject": "验收通知", "body": "五轮审核已完成"},
            )
            acceptance.check("完整流程", "邮件通知进入待发队列", notification.status_code == 200 and notification.json().get("status") == "待发送", notification.status_code)

            change = client.post(
                "/api/change-requests",
                headers=auth_headers(tokens, "sales.owner"),
                json={"contract_id": flow_id, "request_text": "客户要求将付款周期调整为45日，并取消自动续租。"},
            )
            change_body = change.json() if change.status_code == 200 else {}
            acceptance.check("完整流程", "对话式订改申请生成补充协议", change.status_code == 200 and "补充协议" in change_body.get("generated_supplement", "") and bool(change_body.get("original_requirement")), change.status_code)

            approvals = client.post(
                f"/api/contracts/{flow_id}/approvals/prepare",
                headers=auth_headers(tokens, "legal.reviewer"),
            )
            approval_rows = approvals.json() if approvals.status_code == 200 else []
            acceptance.check("完整流程", "租赁合同按矩阵生成法务和财务审批", approvals.status_code == 200 and {row["department"] for row in approval_rows} == {"法务部", "财务部"}, approval_rows)
            approval_detail = client.get(f"/api/contracts/{flow_id}", headers=auth_headers(tokens, "legal.reviewer")).json()
            decision_statuses = []
            for task in approval_detail["approvals"]:
                username = "finance.expert" if task["department"] == "财务部" else "legal.reviewer"
                decision = client.patch(
                    f"/api/approvals/{task['id']}",
                    headers=auth_headers(tokens, username),
                    json={"decision": "通过", "comment": f"{task['department']}验收通过"},
                )
                decision_statuses.append(decision.status_code)
            final_detail = client.get(f"/api/contracts/{flow_id}", headers=auth_headers(tokens, "legal.reviewer")).json()
            acceptance.check("完整流程", "审批人逐级完成后合同状态为通过", all(status == 200 for status in decision_statuses) and final_detail["contract"]["status"] == "通过", {"statuses": decision_statuses, "contract_status": final_detail["contract"]["status"]})

            export_results = {}
            for mode in ("clean", "redline", "internal"):
                response = client.get(
                    f"/api/contracts/{flow_id}/export",
                    params={"mode": mode},
                    headers=auth_headers(tokens, "legal.reviewer"),
                )
                valid_docx = response.status_code == 200 and response.content[:2] == b"PK"
                if valid_docx:
                    with ZipFile(BytesIO(response.content)) as package:
                        document_xml = package.read("word/document.xml").decode("utf-8", errors="ignore")
                    export_results[mode] = {
                        "valid": True,
                        "has_contract_body": "第5轮客户反馈" in document_xml,
                        "has_strike": "w:strike" in document_xml,
                        "has_basis": "修改依据" in document_xml,
                        "has_internal_note": "需提交审批矩阵复核" in document_xml,
                    }
                else:
                    export_results[mode] = {"valid": False}
            export_ok = (
                all(export_results[mode].get("valid") for mode in export_results)
                and all(export_results[mode].get("has_contract_body") for mode in export_results)
                and export_results["redline"].get("has_strike")
                and export_results["internal"].get("has_basis")
                and not export_results["clean"].get("has_basis")
                and not export_results["clean"].get("has_internal_note")
                and not export_results["redline"].get("has_internal_note")
            )
            acceptance.check("完整流程", "清洁版、带痕迹版和内部版导出隔离", export_ok, export_results)
            sales_internal = client.get(
                f"/api/contracts/{flow_id}/export",
                params={"mode": "internal"},
                headers=auth_headers(tokens, "sales.owner"),
            )
            sales_clean = client.get(
                f"/api/contracts/{flow_id}/export",
                params={"mode": "clean"},
                headers=auth_headers(tokens, "sales.owner"),
            )
            acceptance.check(
                "权限",
                "销售可导出客户清洁版但不可导出内部版",
                sales_clean.status_code == 200 and sales_internal.status_code == 403,
                {"clean": sales_clean.status_code, "internal": sales_internal.status_code},
            )

            download = client.get(
                f"/api/contracts/{flow_id}/versions/{first_version_id}/download",
                headers=auth_headers(tokens, "legal.reviewer"),
            )
            acceptance.check("完整流程", "原始合同版本可下载", download.status_code == 200 and len(download.content) > 1000, {"status": download.status_code, "bytes": len(download.content)})

            search = client.get(
                "/api/contracts",
                params={"q": "DDBB"},
                headers=auth_headers(tokens, "legal.reviewer"),
            )
            acceptance.check("完整流程", "合同全文关键词检索", search.status_code == 200 and any(row["id"] == flow_id for row in search.json()), search.status_code)

        # Website-term snapshot should exist for both PO contracts even when the
        # public site rejects crawling; failures must become explicit manual tasks.
        website_contract_ids = [
            contract_by_file[name]["contract_id"]
            for name in ("5.PO带客户官网地址PDF1.pdf", "6.PO带客户官网链接PDF.PDF")
            if name in contract_by_file
        ]
        with SessionLocal() as db:
            website_snapshots = [
                {
                    "contract_id": item.contract_id,
                    "status": item.fetch_status,
                    "url": item.url,
                    "message": item.message,
                }
                for item in db.query(WebsiteTermsSnapshot).filter(WebsiteTermsSnapshot.contract_id.in_(website_contract_ids)).all()
            ]
        acceptance.check("完整流程", "官网条款抓取/失败转人工均有快照留痕", len(website_snapshots) == len(website_contract_ids), website_snapshots)

        reports = client.get("/api/reports/overview", headers=auth_headers(tokens, "system.admin"))
        report_body = reports.json() if reports.status_code == 200 else {}
        acceptance.check("报表", "风险报表汇总模板和流程数据", reports.status_code == 200 and report_body.get("kpis", {}).get("contracts", 0) >= 22 and bool(report_body.get("risk_categories")), report_body.get("kpis", reports.status_code))
        audits = client.get("/api/audit-logs?limit=500", headers=auth_headers(tokens, "system.admin"))
        actions = {row["action"] for row in audits.json()} if audits.status_code == 200 else set()
        expected_actions = {"上传合同版本", "启动AI合同审核", "记录销售谈判反馈", "按矩阵生成审批单", "生成订改申请草案"}
        acceptance.check("审计", "关键业务动作均有审计留痕", audits.status_code == 200 and expected_actions.issubset(actions), {"missing": sorted(expected_actions - actions), "count": len(actions)})

    acceptance.finish()
    engine.dispose()
    return 0 if acceptance.report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        try:
            failure = json.loads(REPORT_JSON.read_text(encoding="utf-8")) if REPORT_JSON.exists() else {}
        except Exception:
            failure = {}
        failure.update(
            finished_at=datetime.now().isoformat(timespec="seconds"),
            database=DATABASE_NAME,
            fatal_error=f"{type(exc).__name__}: {exc}",
        )
        REPORT_JSON.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
