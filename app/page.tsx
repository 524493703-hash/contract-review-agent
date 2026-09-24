import type { Metadata } from "next";
import ContractReviewApp from "./ContractReviewApp";

export const metadata: Metadata = {
  title: "契析 · 合同审核管理平台",
  description: "覆盖合同提交、风险审核、五轮协同、审批、订改和审计留痕的一体化合同工作台。",
};

export default function Home() {
  return <ContractReviewApp />;
}
