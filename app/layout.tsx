import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "契析 · 合同审核管理平台", template: "%s · 契析" },
  description: "企业销售、租赁与服务合同的审核管理平台。",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "契析 · 合同审核管理平台",
    description: "合同提交、风险审核、五轮协同、审批与全程审计的一体化工作台。",
    type: "website",
    images: [{ url: "/og-contract-review.png", width: 1672, height: 941, alt: "合同风险审核工作台" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
