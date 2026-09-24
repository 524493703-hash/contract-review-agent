import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: handler } = await import(workerUrl.href);
  const request = new Request("http://localhost/", { headers: { accept: "text/html" } });
  if (typeof handler === "function") return handler(request);
  return handler.fetch(
    request,
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server renders the contract review product shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<html lang="zh-CN"/i);
  assert.match(html, /契析/);
  assert.match(html, /合同审核管理平台/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|SkeletonPreview/i);
});

test("project contains the real application and social preview", async () => {
  const [page, app, css, layout] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/ContractReviewApp.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(page, /ContractReviewApp/);
  assert.match(app, /智能审核/);
  assert.match(app, /采购合同/);
  assert.match(app, /租赁合同/);
  assert.match(app, /上传第 \$\{nextRound\} 轮合同/);
  assert.match(app, /form\.append\("review_round", String\(uploadRoundNo\)\)/);
  assert.doesNotMatch(app, /form\.append\("review_round"[^\n]+target\?\.current_round/);
  assert.match(app, /批注来源识别/);
  assert.match(app, /下载本轮原文件批注版/);
  assert.match(app, /在线预览/);
  assert.match(app, /ContractPreviewModal/);
  assert.match(app, /系统 AI 问题（统一青蓝色）/);
  assert.match(app, /可直接替换风险原文的完整条款/);
  assert.match(app, /用自然语言继续修改/);
  assert.match(app, /重新生成第 \{draftCount \+ 1\} 稿/);
  assert.match(app, /查看全部生成历史/);
  assert.match(app, /同类风险\s+\{item\.occurrence_no\}\/\{item\.occurrence_count\}\s+·\s+独立处置/);
  assert.match(app, /\/suggestions\/\$\{item\.id\}\/redraft/);
  assert.match(app, /转批这一条风险建议/);
  assert.match(app, /目标部门/);
  assert.match(app, /审核同事/);
  assert.match(app, /\/consultations\/\$\{active\.id\}\/answer/);
  assert.match(app, /同意系统建议/);
  assert.match(css, /\.suggestion-referral/);
  assert.match(css, /\.referral-review-form/);
  assert.match(css, /\.clause-redraft/);
  assert.match(css, /\.doc-ai-highlight/);
  assert.match(app, /PdfDocumentViewer/);
  assert.match(css, /\.pdf-js-viewer/);
  assert.match(app, /LongTaskStatus/);
  assert.match(app, /审核服务在线/);
  assert.match(app, /请勿重复提交；完成后页面会自动刷新/);
  assert.match(app, /setInterval\(\(\) => void pollHealth\(\), 8000\)/);
  assert.match(css, /\.task-progress-track/);
  assert.match(app, /已渲染 \{renderedPages\.size\}\/\{document\.numPages\} 页/);
  assert.match(css, /\.pdf-render-progress/);
  assert.match(app, /data-risk-card-id/);
  assert.match(app, /data-pdf-risk-id/);
  assert.match(app, /selectRiskFromDocument/);
  assert.match(app, /专项风险/);
  assert.match(app, /合同缺失条款/);
  assert.match(app, /公司标准依据/);
  assert.match(app, /法律法规依据/);
  assert.match(app, /focusedReview\?\.results\.filter\(isActionableFocusedRisk\)/);
  assert.match(app, /可直接替换风险原文的完整条款/);
  assert.match(app, /查看审核依据与谈判重点/);
  assert.match(css, /\.risk-source-selected/);
  assert.match(css, /\.focused-source-grid/);
  assert.match(css, /\.pdf-risk-source/);
  assert.match(app, /订改申请/);
  assert.match(app, /审计日志/);
  assert.match(css, /\.risk-card/);
  assert.match(layout, /og-contract-review\.png/);
  await access(new URL("../public/og-contract-review.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview/SkeletonPreview.tsx", import.meta.url)));
});

test("contract review guide documents permissions and full workflow", async () => {
  const guide = await readFile(new URL("../public/contract-review-guide.html", import.meta.url), "utf8");
  for (const text of ["六类账户权限矩阵", "合同审核端到端流程", "POC规则如何判断风险", "大模型如何统一评定风险等级", "审批矩阵与状态流转", "一个正式库中的主要数据表"]) {
    assert.match(guide, new RegExp(text));
  }
  assert.match(guide, /高风险数 × 18/);
  assert.match(guide, /impact|影响程度/);
});
