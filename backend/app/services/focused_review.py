from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CheckBaselineMap,
    ClauseAtom,
    ClauseLink,
    ClauseNode,
    FocusedCheck,
    KnowledgeDocument,
    Playbook,
)
from .baseline_service import (
    BASELINE_NAME,
    BASELINE_SOURCE_FILE,
    BASELINE_TEXT_PATH,
    BASELINE_VERSION,
    parse_standard_clauses,
)
from .source_trace import CHINESE_ARTICLE, NUMERIC_CLAUSE, SECTION_HEADING, clause_label_at, locate_source_span


PLAYBOOK_KEY = "LEASE_BASE_CN+OUR_ROLE_LESSOR+FORKLIFT+LINDE_2025_01"
PLAYBOOK_VERSION = "1.0.0"
PLAYBOOK_NAME = "中国设备租赁（我方出租方）审核 Playbook"
BUSINESS_STATUSES = {"MET", "UNMET", "PARTIAL", "NOT_MENTIONED"}


@dataclass(frozen=True)
class CheckSpec:
    code: str
    name: str
    category: str
    clause_refs: tuple[str, ...]
    exact_terms: tuple[str, ...]
    synonyms: tuple[str, ...]
    required_groups: tuple[tuple[str, ...], ...]
    adverse_patterns: tuple[str, ...] = ()
    base_risk_level: str = "中"
    requirement_level: str = "preferred"
    recommendation: str = "恢复公司标准保护；如无法恢复，应记录商业原因、替代控制和有权审批人的放行结论。"
    redline_strategy: str = "RESTORE_BASELINE"
    legal_rag_triggers: tuple[str, ...] = ()
    human_confirmation_required: bool = False
    expected_absence_check: bool = False


def _c(
    code: str,
    name: str,
    category: str,
    refs: str,
    terms: str,
    groups: tuple[tuple[str, ...], ...],
    *,
    synonyms: str = "",
    adverse: tuple[str, ...] = (),
    risk: str = "中",
    level: str = "preferred",
    legal: tuple[str, ...] = (),
    human: bool = False,
    strategy: str = "RESTORE_BASELINE",
) -> CheckSpec:
    return CheckSpec(
        code=code,
        name=name,
        category=category,
        clause_refs=tuple(refs.split()),
        exact_terms=tuple(terms.split()),
        synonyms=tuple(synonyms.split()),
        required_groups=groups,
        adverse_patterns=adverse,
        base_risk_level=risk,
        requirement_level=level,
        legal_rag_triggers=legal,
        human_confirmation_required=human,
        redline_strategy=strategy,
    )


CHECK_SPECS: tuple[CheckSpec, ...] = (
    _c("L-01", "一般性条款并入与版本唯一", "文件效力", "1.1 1.2", "一般性条款 租赁合同 条款条件", (("一般性条款", "通用条款"), ("租赁合同", "本合同")), risk="高", human=True),
    _c("L-02", "合同文件优先级与冲突", "文件效力", "1.4", "主合同 一般性条款 特别条款 报价单 技术附件 优先", (("主合同", "本合同"), ("一般性条款", "通用条款", "附件"), ("优先", "不一致", "冲突")), synonyms="补充协议 技术协议", risk="高", human=True, strategy="ADD_PRECEDENCE"),
    _c("L-03", "合同修改的书面签署要求", "文件效力", "1.4", "增加 删改 变更 盖章 签字", (("增加", "删改", "变更", "修改"), ("盖章", "签字", "书面确认")), risk="中"),
    _c("L-04", "条款可分割性", "文件效力", "1.3", "无效条款 其余部分 仍然有效", (("无效",), ("其余", "其他条款"), ("有效",)), risk="低"),
    _c("L-05", "格式条款提示说明与协商留痕", "格式条款", "1.5", "格式条款 协商一致 提示 说明", (("格式条款",), ("协商一致", "提示", "说明")), adverse=(r"不构成.{0,20}格式条款", r"不得以格式条款"), risk="高", legal=("格式条款效力", "提示说明义务", "举证责任"), human=True, strategy="ADD_NOTICE_EVIDENCE"),
    _c("L-06", "设备及附件清单唯一识别", "租赁标的", "2.1", "设备 叉车 牵引车 电池 托盘 属具 随车工具 设备编号 车架号 序列号 资产编号", (("设备", "租赁物"), ("型号", "叉车", "牵引车", "电池", "托盘", "属具"), ("设备编号", "车架号", "序列号", "资产编号", "逐台清单")), risk="高"),
    _c("L-07", "交付签收上牌与起租日一致", "租赁期限", "2.3 2.4 9.1", "设备交付 签收 上牌 租赁起始日", (("交付", "签收"), ("租赁起始日", "起租日", "租期开始")), synonyms="登记 使用登记", risk="高", human=True),
    _c("L-08", "付款周期与租金定义一致", "租金", "2.2 2.5 2.6 2.7", "付款周期 租赁年 租赁季 租赁月 月租金 每期租金", (("付款周期", "支付周期"), ("月租金", "租金"), ("每期租金", "当期租金", "应付租金")), risk="中"),
    _c("L-09", "工时及超时租金口径", "租金", "2.8 2.9 2.10", "设备工作小时 正常工作小时 实际工作小时 年工作小时 工时表 超时租金", (("设备工作小时", "正常工作小时", "实际工作小时", "年工作小时", "工时表", "小时表"), ("超时租金", "超时费")), risk="高"),
    _c("L-10", "工况变化通知与调租", "租金", "3.1", "工况 加重 年工作小时 承重限制 班制 通知 重新确定租金", (("工况",), ("通知",), ("租金", "调租")), risk="高"),
    _c("L-11", "调租决定权及合理性", "租金", "3.1", "协商不成 公平合理 确定租金 调整租金", (("确定租金", "调整租金", "租金标准", "调租"), ("协商不成",), ("公平合理", "合理原则")), adverse=(r"承租方单方.{0,20}(?:确定|调整).{0,10}租金",), risk="高", legal=("单方定价条款效力",), human=True),
    _c("L-12", "年度工时确认与超时租金付款", "租金", "3.2", "每满一年 小时表 共同确定 超时租金 三十个工作日", (("小时表", "工时表"), ("共同确定", "双方确认"), ("超时租金", "超时费")), risk="中"),
    _c("L-13", "小时表损坏替代计算", "租金", "3.3", "小时表损坏 更换 六个月 月平均数 顺延", (("小时表损坏", "工时表损坏"), ("月平均数", "平均工时", "替代计算"), ("顺延", "延期")), risk="中"),
    _c("L-14", "年内变更的比例结算", "租金", "3.4", "合同变更 实际使用期限 按比例 正常工作小时 超时租金", (("按比例", "比例确定", "实际使用期限"), ("合同变更", "租赁变更"), ("超时租金", "超时费")), risk="中"),
    _c("L-15", "押金金额及计算基数", "押金", "4.1", "押金 一个季度 租金", (("押金", "保证金"), ("一个季度", "三个月租金", "季度租金")), adverse=(r"押金.{0,20}(?:低于|不超过).{0,10}(?:一个月|月租金)",), risk="中"),
    _c("L-16", "押金扣款与不足补足", "押金", "4.2", "押金 不可充抵 扣除 租金 维修费 违约金 不足 补足", (("押金", "保证金"), ("扣除", "扣抵"), ("不足", "补足")), risk="中"),
    _c("L-17", "押金返还条件期限及利息", "押金", "4.3", "押金返还 十个工作日 不计利息 履行义务", (("返还", "退还"), ("工作日", "日内"), ("不计利息", "无息")), risk="中"),
    _c("L-18", "往返运费与途中保险", "运输", "5.1 5.2", "运费 仓库 工厂 运回 运输费用 途中保险 出租方安排 承租方负担", (("运费", "运输费"), ("运回", "返程", "往返"), ("保险", "途中保险"), ("负担", "承担")), risk="中"),
    _c("L-19", "首期及后续租金预付", "付款", "6.1", "第一租赁期 租金 押金 运费 五个工作日 第一日前", (("第一期", "第一租赁期", "首期"), ("租金",), ("第一日前", "预付", "提前支付")), risk="高"),
    _c("L-20", "付款方式及到账时点", "付款", "6.4", "电汇 汇入账户 视为支付", (("电汇", "银行转账", "汇款"), ("汇入", "到账"), ("视为支付", "完成支付")), risk="中"),
    _c("L-21", "逾期停服权与条款一致性", "付款与维保", "6.2 11.8", "逾期超过30天 中止保养 维修 暂停", (("逾期",), ("30天", "三十天", "一个月"), ("暂停", "中止"), ("维修", "保养", "维保")), risk="高"),
    _c("L-22", "安全或强制维保能否暂停", "安全合规", "6.2 11.8", "暂停维修 暂停保养 中止维保 设备安全 人身安全 法定义务", (("暂停维修", "暂停保养", "中止维修", "中止保养", "中止维保"), ("设备安全", "人身安全", "法定义务", "强制维保")), adverse=(r"(?:随时|有权).{0,15}(?:暂停|中止).{0,20}(?:全部|任何)?(?:维修|保养).{0,30}无需承担",), risk="高", legal=("特种设备安全维保强制义务", "停服责任边界"), human=True, strategy="CARVE_OUT_SAFETY_SERVICE"),
    _c("L-23", "逾期付款违约金", "付款", "6.3", "逾期支付 每逾期一日 0.05% 违约金", (("逾期支付", "逾期付款"), ("每日", "每逾期一日"), ("违约金",)), adverse=(r"(?:0\.[1-9]\d*%|[一二三四五六七八九十]+%).{0,20}(?:每日|每逾期一日)",), risk="高", legal=("违约金调整", "损失赔偿"), human=True),
    _c("L-24", "开票时间暂停及租金权利", "发票", "7.1", "付款日前 十个工作日 发票 收据 暂停开具 租金", (("发票", "收据"), ("付款日", "支付日"), ("暂停开具", "停止开票", "继续开票")), risk="中"),
    _c("L-25", "电子发票交付和异议", "发票", "7.2", "电子发票 电子邮件 微信 钉钉 三天 异议 视为收到", (("电子发票",), ("电子邮件", "微信", "钉钉", "数据传输"), ("异议",), ("视为", "推定")), risk="中"),
    _c("L-26", "设备使用地点及变更同意", "使用地点", "8", "设备使用地点 场所 地址 更换 书面同意", (("使用地点", "使用场所"), ("地址", "场所"), ("书面同意", "事先同意")), risk="高"),
    _c("L-27", "擅自变更地点的保险和服务后果", "使用地点", "8", "擅自变更地点 更换使用地点 保险公司拒赔 保养 维修 损失责任", (("擅自变更地点", "擅自更换地点", "变更使用地点", "更换使用地点"), ("保险", "拒赔"), ("维修", "保养", "服务"), ("损失", "责任")), risk="高"),
    _c("L-28", "交付前提时间及顺延", "交付", "9.1 9.2", "交付前提 收到第一期租金 收到押金 收到运费 租用期开始前 交付顺延", (("交付前提", "交付条件", "交付前置条件", "租用期开始前"), ("收到第一期租金", "收到押金", "收到运费"), ("交付顺延", "交货顺延", "租期顺延")), risk="高"),
    _c("L-29", "出租方迟延交付责任", "交付", "9.3", "延误 迟交设备价值 万分之三 三个月 解除 10%", (("延误", "迟延交付"), ("万分之三", "违约金"), ("三个月",), ("解除",)), adverse=(r"(?:每日|每延误一日|每延迟一天).{0,30}(?:0\.0[5-9]%|0\.[1-9]\d*%|千分之)", r"迟延交付.{0,50}(?:全部损失|一切损失)"), risk="高", legal=("违约金调整", "损失赔偿", "可预见性"), human=True),
    _c("L-30", "承租方迟延接收及设备处置", "交付", "9.4", "延迟接收 拒绝签收 万分之三 三个月 解除 先行处理 重新确定交货时间", (("延迟接收", "迟延接收", "拒绝签收"), ("赔偿", "违约金"), ("解除",), ("先行处理", "另行处置", "重新确定交货")), risk="高"),
    _c("L-31", "数量型号质量异议与默示验收", "验收", "10", "数量 型号 质量 异议 当天 五个工作日 视为符合", (("数量",), ("型号",), ("质量",), ("异议",), ("视为", "默认")), risk="高"),
    _c("L-32", "默示验收与隐蔽安全缺陷", "验收", "10", "默示验收 视为验收 隐蔽瑕疵 安全缺陷 法定责任", (("视为", "默示"), ("验收", "符合")), adverse=(r"(?:未|逾期未).{0,30}(?:提出|书面).{0,12}异议.{0,30}视为.{0,20}(?:验收|质量|符合)", r"(?:期限|日内).{0,30}未.{0,20}异议.{0,30}视为.{0,20}(?:验收|符合)", r"未在.{0,20}(?:日内|期限内).{0,20}(?:完成)?验收.{0,20}视为.{0,20}验收合格"), risk="高", legal=("默示验收对隐蔽瑕疵和安全缺陷的效力",), human=True, strategy="ADD_LATENT_DEFECT_CARVEOUT"),
    _c("L-33", "全面保养和正常磨损范围", "维修保养", "11.1", "全面保养 定期保养 正常磨损 维修 零配件 人工 轮胎 每租赁年度", (("保养",), ("正常磨损",), ("维修",), ("零配件", "配件"), ("人工",)), risk="高"),
    _c("L-34", "维保排除事项", "维修保养", "11.2", "事故 误操作 超载 滥用 燃料 工作条件 日常检查 维修更换", (("事故", "误操作", "超载", "滥用"), ("不包括", "排除"), ("维修", "更换")), risk="中"),
    _c("L-35", "日常检查故障停用及免费维修", "维修保养", "11.3", "换班前检查 日常检查 每日检查 日常点检 每月 自行检查 故障 通知 停止使用 免费维修", (("日常检查", "换班前检查", "每日检查", "日常点检"), ("故障",), ("通知",), ("停止使用", "停用"), ("免费维修",)), risk="高", human=True),
    _c("L-36", "1000小时保养与原装配件", "维修保养", "11.4", "1000小时 通知保养 决定如何维修 原装零配件 擅自保养 赔偿", (("1000小时", "一千小时"), ("通知",), ("原装", "原厂"), ("赔偿", "负责")), risk="中"),
    _c("L-37", "维修场地培训持证与违规责任", "维修保养", "11.5 11.6 11.7", "工作场地 作业场地 维修场地 通风 照明 温度 培训 叉车操作证 操作手册 超出工况 赔偿", (("工作场地", "作业场地", "维修场地"), ("培训", "安全教育"), ("操作证", "持证", "作业证"), ("操作手册", "使用说明")), risk="高"),
    _c("L-38", "设备所有权及禁止处分", "所有权", "12.1", "所有权 出租方 转让 出借 出租 抵押 质押 投资 非法活动", (("所有权",), ("出租方", "我方"), ("不得", "禁止"), ("转让", "出借", "抵押", "质押")), risk="高", human=True),
    _c("L-39", "特种设备使用登记定检及责任", "安全合规", "12.2", "特种设备 使用单位 使用登记 定期检验 年检 技术监督 安全义务 民事行政刑事责任", (("特种设备",), ("使用单位",), ("使用登记", "登记"), ("定期检验", "年检")), risk="高", legal=("特种设备使用单位认定", "使用登记", "定期检验", "现行安全技术规范"), human=True, strategy="ALIGN_CURRENT_SAFETY_RULES"),
    _c("L-40", "损坏灭失人身财产损害与修复", "风险责任", "12.3 12.4", "设备损坏 灭失 财产损失 人身伤害 修复费用 恢复原状 更换部件", (("损坏", "损毁"), ("灭失", "丢失"), ("修复", "恢复原状"), ("损失", "赔偿")), risk="高", human=True),
    _c("L-41", "事故通知现场保留及鉴定", "安全合规", "12.6", "设备事故 立即通知 维持事故现场 鉴定责任", (("事故",), ("通知",), ("现场",), ("鉴定", "责任认定")), risk="高", human=True),
    _c("L-42", "承租方转让限制与出租方融资", "权利转让", "12.5 12.7", "不得转让 书面同意 融资需求 抵押 出售 银行 融资租赁公司 回租 不影响占有使用", (("转让",), ("书面同意",), ("融资", "抵押", "出售", "回租"), ("不影响", "继续使用")), adverse=(r"未经承租方.{0,10}同意.{0,30}出租方不得.{0,20}(?:抵押|出售|转让)",), risk="高", human=True),
    _c("L-43", "自动或默示续租", "续租", "13.1", "继续租赁 书面请求 出租方同意 继续使用 无异议 视同自动续租", (("续租", "继续租赁"), ("同意", "无异议"), ("继续使用", "期限届满")), adverse=(r"承租方有权单方.{0,20}续租", r"按原租金.{0,30}无限期.{0,10}续租"), risk="高", human=True),
    _c("L-44", "承租方提前终止与损失补偿", "解除终止", "13.2 15.2", "提前终止 提前30个工作日 协商 书面同意 交还设备 租金损失 剩余租赁期限 30%", (("提前终止", "提前解除", "提前退租"), ("提前", "工作日", "天"), ("书面同意", "协商", "通知"), ("租金损失", "损失补偿", "剩余租期", "违约责任")), adverse=(r"(?:承租方|甲方)有权.{0,35}(?:随时|无理由|经营需要|提前.{0,10}通知).{0,25}(?:解除|终止|退租).{0,35}(?:不承担|无需承担|免于).{0,20}(?:赔偿|补偿|违约责任)",), risk="高", human=True),
    _c("L-45", "终止后设备交还程序", "设备交还", "14.1 14.2", "终止后交还 解除后返还 归还设备 返还设备 24小时 清洁 整理 良好状态 书面通知 验收 装运 逾期归还 正常损耗", (("终止后交还", "解除后返还", "归还设备", "返还设备", "设备交还"), ("终止", "解除"), ("清洁", "整理", "良好状态"), ("验收", "接收")), risk="高"),
    _c("L-46", "逾期交还占用费", "设备交还", "14.3", "逾期归还 130% 租金 占用费 使用费", (("逾期归还", "逾期返还", "逾期交还"), ("占用", "使用费"), ("130%", "百分之一百三十")), adverse=(r"逾期.{0,15}(?:归还|返还).{0,30}(?:低于|不超过)100%",), risk="高"),
    _c("L-47", "严重违约解除收回及损失责任", "违约责任", "15.1 15.2 15.3 15.4 15.5", "严重违约 终止合同 收回设备 剩余租赁期限 30% 三个月租金 法律救济 间接损失 利润损失", (("严重违约",), ("终止合同", "解除合同"), ("收回",), ("损失", "违约金", "赔偿"), ("间接损失", "利润损失", "责任限制")), adverse=(r"出租方.{0,30}(?:承担|赔偿).{0,20}(?:全部|一切|无限).{0,20}损失",), risk="高", legal=("违约金调整", "损失赔偿", "可预见性", "责任限制"), human=True),
    _c("L-48", "不可抗力及后续处理", "不可抗力", "16", "不可预见 不可避免 不可克服 不可抗力 通知 证明文件 协商 新协议", (("不可抗力", "不可预见", "不能预见"), ("不可避免", "不能避免"), ("不可克服", "不能克服"), ("通知",), ("证明", "证据")), risk="中"),
    _c("L-49", "管辖、实现债权费用与送达", "争议解决", "17.1 17.2 18", "出租方所在地 法院管辖 案件受理费 保全费 律师费 送达地址 地址变更 拒收 退件 视为送达", (("管辖", "法院"), ("出租方所在地", "我方所在地"), ("律师费", "保全费", "实现债权费用"), ("送达地址", "通知地址"), ("视为送达", "有效送达")), adverse=(r"(?:承租方|客户|甲方)所在地.{0,30}(?:有管辖权的)?(?:人民)?法院", r"向(?:承租方|客户|甲方).{0,8}所在地.{0,30}(?:人民)?法院"), risk="高", legal=("协议管辖有效性", "诉讼费用承担", "约定送达效力"), human=True),
)


@dataclass(frozen=True)
class TextSegment:
    index: int
    clause_no: str
    text: str
    start: int
    end: int
    page_no: int | None = None
    source_file: str = ""
    page_method: str = ""


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value or "").replace("％", "%")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_contract_segments(
    text: str,
    *,
    source_map: list[dict] | None = None,
    source_file: str = "",
) -> list[TextSegment]:
    """Preserve source offsets while producing clause-sized retrieval units."""
    source = text or ""
    # Clause numbers are structural only at a line boundary. Treating any
    # number followed by Chinese text as a heading would incorrectly split
    # values such as "30天" and "1000小时" into fake clauses.
    matches = [(item.start(), item.end(), item.group(1)) for item in NUMERIC_CLAUSE.finditer(source)]
    matches.extend(
        (item.start(), item.end(), f"第{item.group(1)}条")
        for item in CHINESE_ARTICLE.finditer(source)
    )
    matches.extend(
        (item.start(), item.end(), item.group(1).strip()[:40])
        for item in SECTION_HEADING.finditer(source)
    )
    matches.sort(key=lambda item: item[0])
    segments: list[TextSegment] = []
    if matches:
        for index, match in enumerate(matches):
            start = match[0]
            end = matches[index + 1][0] if index + 1 < len(matches) else len(source)
            value = re.sub(r"\s+", " ", source[start:end]).strip()
            if len(value) >= 6:
                locator = locate_source_span(source_map, start, end, source_file=source_file)
                segments.append(TextSegment(
                    len(segments), match[2], value, start, end,
                    locator["page_no"], locator["source_file"], locator["page_method"],
                ))
    if segments:
        return segments
    sentence_pattern = re.compile(r"[^。；！？\n]+[。；！？]?", re.MULTILINE)
    for match in sentence_pattern.finditer(source):
        value = re.sub(r"\s+", " ", match.group(0)).strip()
        if len(value) >= 6:
            locator = locate_source_span(source_map, match.start(), match.end(), source_file=source_file)
            segments.append(TextSegment(
                len(segments), clause_label_at(source, match.start()), value, match.start(), match.end(),
                locator["page_no"], locator["source_file"], locator["page_method"],
            ))
    if not segments and source.strip():
        value = re.sub(r"\s+", " ", source).strip()
        locator = locate_source_span(source_map, 0, len(source), source_file=source_file)
        segments.append(TextSegment(0, "", value, 0, len(source), locator["page_no"], locator["source_file"], locator["page_method"]))
    return segments


def _term_hits(text: str, terms: Iterable[str]) -> list[str]:
    compact = _normalized(text)
    return [term for term in terms if _normalized(term) in compact]


def retrieve_check_evidence(spec: CheckSpec, segments: list[TextSegment], max_candidates: int = 8) -> dict:
    """Hybrid deterministic/BM25/concept retrieval with a complete trace."""
    query_terms = tuple(dict.fromkeys((*spec.exact_terms, *spec.synonyms)))
    document_frequency = {
        term: sum(bool(_term_hits(segment.text, (term,))) for segment in segments)
        for term in query_terms
    }
    ranked: list[dict] = []
    for segment in segments:
        exact_hits = _term_hits(segment.text, spec.exact_terms)
        concept_hits = _term_hits(segment.text, spec.synonyms)
        # Baseline clause numbers are not customer-contract clause numbers.
        # Using them as a retrieval signal caused e.g. customer clause 7.9
        # (subcontracting) to be selected for a baseline assignment check.
        number_hit = False
        adverse_hits = [pattern for pattern in spec.adverse_patterns if re.search(pattern, segment.text)]
        slot_hits = [
            f"slot_{index}"
            for index, group in enumerate(spec.required_groups, start=1)
            if _term_hits(segment.text, group)
        ]
        bm25_score = 0.0
        length_norm = max(0.5, min(2.0, len(segment.text) / 160))
        for term in (*exact_hits, *concept_hits):
            df = document_frequency.get(term, 0)
            idf = math.log(1 + (len(segments) - df + 0.5) / (df + 0.5)) if segments else 0
            tf = max(1, _normalized(segment.text).count(_normalized(term)))
            bm25_score += idf * (tf * 2.2 / (tf + 1.2 * length_norm))
        # The first required group is the check's topic anchor. Generic terms
        # such as "更换", "通知" or "电子邮件" cannot make an unrelated clause
        # admissible evidence by themselves.
        topical = bool(adverse_hits) or "slot_1" in slot_hits
        score = len(exact_hits) * 4.0 + len(concept_hits) * 2.0 + len(slot_hits) * 3.0 + bm25_score + len(adverse_hits) * 8.0
        if score <= 0 or not topical:
            continue
        methods = []
        if number_hit:
            methods.append("number")
        if exact_hits:
            methods.append("exact")
        if bm25_score:
            methods.append("bm25")
        if concept_hits:
            methods.append("concept")
        if adverse_hits:
            methods.append("adverse_rule")
        ranked.append({
            "segment": segment,
            "score": round(score, 6),
            "methods": methods,
            "exact_hits": exact_hits,
            "concept_hits": concept_hits,
            "adverse_hits": adverse_hits,
            "slot_hits": slot_hits,
        })
    ranked.sort(key=lambda item: (-item["score"], item["segment"].index))
    returned = ranked[:max_candidates]
    return {
        "searched_clause_count": len(segments),
        "candidate_count": len(ranked),
        "returned_count": len(returned),
        "truncated": len(ranked) > len(returned),
        "methods_executed": ["number", "exact", "bm25", "concept", "adverse_rule"],
        "candidates": returned,
    }


def _evaluate_one(spec: CheckSpec, trace: dict, *, parse_verified: bool, document_complete: bool) -> dict:
    candidates = trace["candidates"]
    # Slots must be satisfied by one coherent clause, not by stitching terms
    # from unrelated top-k candidates. This is the main false-MET guard.
    best_candidate = max(candidates, key=lambda item: (len(item["slot_hits"]), item["score"]), default=None)
    satisfied_slots = list(best_candidate["slot_hits"]) if best_candidate else []
    all_slots = [f"slot_{index}" for index in range(1, len(spec.required_groups) + 1)]
    missing_slots = [slot for slot in all_slots if slot not in satisfied_slots]
    contradictions = [
        {"pattern": pattern, "quote": item["segment"].text[:600]}
        for item in candidates
        for pattern in item["adverse_hits"]
    ]
    if not parse_verified or not document_complete:
        status = "NOT_MENTIONED"
        technical_status = "UNVERIFIABLE"
        reason = "合同包不完整或文档解析未通过，业务四态仅为占位，禁止据此认定条款缺失。"
        confidence = 0
    elif contradictions:
        status = "UNMET"
        technical_status = "verified"
        reason = "检出与我方出租方 Playbook 底线相反的明确约定。"
        confidence = 96
    elif not candidates:
        status = "NOT_MENTIONED"
        technical_status = "verified"
        reason = "已执行编号、精确、BM25、概念扩展和不利模式检索，未找到相关约定。"
        confidence = 88
    elif not missing_slots:
        status = "MET"
        technical_status = "verified"
        reason = "候选条款覆盖本 Check 的全部确定性必需槽位，仍保留模型语义复核入口。"
        confidence = 92
    else:
        status = "PARTIAL"
        technical_status = "verified"
        reason = f"已找到相关约定，但仍缺少 {len(missing_slots)} 个必需槽位或需语义确认。"
        confidence = 72
    risk_level = "提示" if status == "MET" else spec.base_risk_level
    # A verified absence can be legally material as well (for example, missing
    # forklift registration/inspection allocation), so NOT_MENTIONED must also
    # enter the legal-RAG branch. UNVERIFIABLE remains a technical issue only.
    legal_required = bool(spec.legal_rag_triggers and technical_status == "verified" and status != "MET")
    human_required = status != "MET" and (spec.human_confirmation_required or risk_level == "高" or legal_required)
    evidence = []
    if contradictions:
        evidence_candidates = sorted(
            (item for item in candidates if item["adverse_hits"]),
            key=lambda item: (-len(item["slot_hits"]), -item["score"]),
        )[:2]
    else:
        evidence_candidates = [best_candidate] if best_candidate else []
    for index, item in enumerate(evidence_candidates, start=1):
        segment = item["segment"]
        evidence.append({
            "order_index": index,
            "clause_no": segment.clause_no,
            "page_no": segment.page_no,
            "source_file": segment.source_file,
            "page_method": segment.page_method,
            "start_offset": segment.start,
            "end_offset": segment.end,
            "quote": segment.text[:1200],
            "evidence_type": "contradict" if item["adverse_hits"] else "support",
            "retrieval_methods": item["methods"],
            "score": item["score"],
        })
    return {
        "check_code": spec.code,
        "check_name": spec.name,
        "category": spec.category,
        "status": status,
        "risk_level": risk_level,
        "base_risk_level": spec.base_risk_level,
        "confidence": confidence,
        "satisfied_slots": satisfied_slots,
        "missing_slots": missing_slots,
        "contradictions": contradictions,
        "reason": reason,
        "decision_source": "deterministic_hybrid",
        "legal_rag_required": legal_required,
        "legal_rag_triggers": list(spec.legal_rag_triggers),
        "technical_status": technical_status,
        "human_confirmation_required": human_required,
        "human_gate_policy": spec.human_confirmation_required,
        "evidence": evidence,
        "retrieval_trace": {
            "query_pack": {
                "exact_terms": list(spec.exact_terms),
                "synonyms": list(spec.synonyms),
                "clause_no_hints": list(spec.clause_refs),
                "adverse_patterns": list(spec.adverse_patterns),
            },
            "searched_clause_count": trace["searched_clause_count"],
            "candidate_count": trace["candidate_count"],
            "returned_count": trace["returned_count"],
            "methods_executed": trace["methods_executed"],
            "candidates": [
                {
                    "clause_no": item["segment"].clause_no,
                    "score": item["score"],
                    "methods": item["methods"],
                    "exact_hits": item["exact_hits"],
                    "concept_hits": item["concept_hits"],
                    "adverse_hits": item["adverse_hits"],
                    "slot_hits": item["slot_hits"],
                    "source_file": item["segment"].source_file,
                    "page_no": item["segment"].page_no,
                    "start_offset": item["segment"].start,
                    "end_offset": item["segment"].end,
                    "quote": item["segment"].text[:1200],
                }
                for item in trace["candidates"]
            ],
            "truncated": trace["truncated"],
        },
    }


def evaluate_focused_checks(
    text: str,
    *,
    contract_type: str,
    our_role: str,
    parse_status: str = "已解析",
    document_complete: bool = True,
    source_map: list[dict] | None = None,
    source_file: str = "",
) -> dict:
    if contract_type != "租赁" or our_role != "出租方":
        return {
            "playbook_key": "",
            "playbook_version": "",
            "coverage_status": "NOT_APPLICABLE",
            "check_results": [],
            "stats": {},
        }
    segments = split_contract_segments(text, source_map=source_map, source_file=source_file)
    parse_verified = parse_status == "已解析" and bool(text.strip())
    results = [
        _evaluate_one(
            spec,
            retrieve_check_evidence(spec, segments),
            parse_verified=parse_verified,
            document_complete=document_complete,
        )
        for spec in CHECK_SPECS
    ]
    status_counts = {status: sum(item["status"] == status for item in results) for status in BUSINESS_STATUSES}
    technical_failures = sum(item["technical_status"] != "verified" for item in results)
    coverage_status = "UNVERIFIABLE" if technical_failures else "COMPLETE" if len(results) == len(CHECK_SPECS) else "INCOMPLETE"
    return {
        "playbook_key": PLAYBOOK_KEY,
        "playbook_version": PLAYBOOK_VERSION,
        "coverage_status": coverage_status,
        "check_results": results,
        "stats": {
            **status_counts,
            "TOTAL": len(results),
            "HUMAN_CONFIRMATION": sum(item["human_confirmation_required"] for item in results),
            "LEGAL_RAG_REQUIRED": sum(item["legal_rag_required"] for item in results),
            "TECHNICAL_FAILURES": technical_failures,
        },
    }


def _atom_parts(clause_no: str, content: str) -> list[str]:
    value = re.sub(r"\s+", " ", content).strip()
    if clause_no == "15.1":
        parts = [item.strip() for item in re.split(r"(?=\d{1,2}）)", value) if item.strip()]
        expanded: list[str] = []
        for part in parts:
            expanded.extend(item.strip() for item in re.split(r"(?<=[。；])", part) if item.strip())
        return expanded
    parts = [item.strip() for item in re.split(r"(?<=[。；])", value) if item.strip()]
    if clause_no in {"1.4", "1.5", "3.1", "4.2", "6.2", "7.1", "8", "9.3", "9.4", "10", "11.1", "11.3", "11.4", "12.2", "12.7", "14.1", "15.2", "16", "18"}:
        refined: list[str] = []
        for part in parts:
            if len(part) > 90:
                refined.extend(item.strip() for item in re.split(r"(?<=[，,])(?=(?:但|如|若|且|并|否则|双方|承租方|出租方|一方|未按|因))", part) if item.strip())
            else:
                refined.append(part)
        parts = refined
    return parts or [value]


def _atom_semantics(text: str) -> tuple[str, str, str]:
    subject = "BOTH" if "双方" in text else "LESSEE" if "承租方" in text else "LESSOR" if "出租方" in text else ""
    modality = "PROHIBITION" if "不得" in text or "严禁" in text else "RIGHT" if "有权" in text else "DEEMED" if "视为" in text or "视同" in text else "OBLIGATION" if "应" in text or "必须" in text else "DEFINITION"
    action_map = (
        ("pay", ("支付", "付款", "租金")),
        ("deliver", ("交付", "签收")),
        ("maintain", ("维修", "保养", "维护")),
        ("return", ("交还", "归还", "返还")),
        ("terminate", ("解除", "终止")),
        ("renew", ("续租", "延长")),
        ("register_inspect", ("登记", "检验", "年检")),
        ("notify", ("通知", "送达")),
        ("compensate", ("赔偿", "违约金", "损失")),
        ("use", ("使用", "操作")),
    )
    action = next((name for name, terms in action_map if any(term in text for term in terms)), "define")
    return subject, modality, action


def _numeric_facts(text: str) -> list[dict]:
    facts = []
    pattern = re.compile(r"(?P<value>\d+(?:\.\d+)?|[一二三四五六七八九十百]+)\s*(?P<unit>%|％|天|日|个工作日|个月|月|小时|年|次)")
    for match in pattern.finditer(text):
        facts.append({"raw_value": match.group(0), "value": match.group("value"), "unit": match.group("unit").replace("％", "%"), "start": match.start(), "end": match.end()})
    if "万分之三" in text:
        facts.append({"raw_value": "万分之三", "value": 0.03, "unit": "%", "normalized": 0.0003})
    return facts


def _terms_for_clause(clause_no: str) -> list[str]:
    terms = []
    for spec in CHECK_SPECS:
        if clause_no in spec.clause_refs:
            terms.extend((*spec.exact_terms, *spec.synonyms))
    return list(dict.fromkeys(terms))


def seed_structured_knowledge(db: Session) -> dict:
    """Idempotently seed canonical clauses, atomic units, links and the role-aware playbook."""
    source_text = BASELINE_TEXT_PATH.read_text(encoding="utf-8")
    text_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    workspace_pdf = Path(__file__).resolve().parents[4] / "POC合同模板（租赁）" / BASELINE_SOURCE_FILE
    source_hash = _file_sha256(workspace_pdf) if workspace_pdf.exists() else text_hash
    document = db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.namespace == "company_baseline",
        KnowledgeDocument.document_key == "LINDE-LEASE-GT",
        KnowledgeDocument.version == BASELINE_VERSION,
    ))
    if not document:
        document = KnowledgeDocument(
            namespace="company_baseline",
            document_key="LINDE-LEASE-GT",
            title=BASELINE_NAME,
            contract_type="租赁",
            version=BASELINE_VERSION,
            source_file=BASELINE_SOURCE_FILE,
            source_hash=source_hash,
            text_hash=text_hash,
            authority_level="canonical",
            jurisdiction="CN",
            effective_from=date(2025, 1, 1),
            status="active",
            metadata_json={"page_count": 1, "layout": "three-column", "authoritative_node_count": 66},
        )
        db.add(document)
        db.flush()
    else:
        document.source_hash = source_hash
        document.text_hash = text_hash
        document.effective_from = date(2025, 1, 1)
        document.metadata_json = {"page_count": 1, "layout": "three-column", "authoritative_node_count": 66}

    parsed = parse_standard_clauses(source_text)
    existing_nodes = {item.clause_no: item for item in db.scalars(select(ClauseNode).where(ClauseNode.document_id == document.id)).all()}
    touched_nodes = 0
    touched_atoms = 0
    for order_index, payload in enumerate(parsed, start=1):
        clause_no = payload["clause_no"]
        raw_text = payload["content"]
        node = existing_nodes.get(clause_no)
        requirement_level = "informational" if clause_no == "2" or clause_no.startswith("2.") else "mandatory" if clause_no.split(".", 1)[0] in {"3", "6", "9", "10", "12", "13", "14", "15", "17"} else "preferred"
        if not node:
            node = ClauseNode(
                document_id=document.id,
                clause_no=clause_no,
                heading=payload["heading"],
                heading_path=[f"{clause_no.split('.', 1)[0]} {payload['heading']}"],
                order_index=order_index,
                node_type="clause",
                raw_text=raw_text,
                normalized_text=_normalized(raw_text),
                summary=raw_text[:160],
                page_no=1,
                requirement_level=requirement_level,
                is_active=True,
            )
            db.add(node)
            db.flush()
            touched_nodes += 1
        else:
            if node.raw_text != raw_text or node.normalized_text != _normalized(raw_text):
                touched_nodes += 1
            node.heading = payload["heading"]
            node.heading_path = [f"{clause_no.split('.', 1)[0]} {payload['heading']}"]
            node.order_index = order_index
            node.raw_text = raw_text
            node.normalized_text = _normalized(raw_text)
            node.summary = raw_text[:160]
            node.page_no = 1
            node.requirement_level = requirement_level
            node.is_active = True

        existing_atoms = {item.atom_no: item for item in db.scalars(select(ClauseAtom).where(ClauseAtom.clause_node_id == node.id)).all()}
        active_atom_nos: set[str] = set()
        for atom_index, atom_text in enumerate(_atom_parts(clause_no, raw_text), start=1):
            atom_no = f"A{atom_index:02d}"
            active_atom_nos.add(atom_no)
            subject, modality, action = _atom_semantics(atom_text)
            atom = existing_atoms.get(atom_no)
            payload_values = {
                "atom_type": "definition" if modality == "DEFINITION" else "proposition",
                "subject_role": subject,
                "modality": modality,
                "action": action,
                "object_text": atom_text[:255],
                "conditions": [part for part in re.findall(r"(?:如|若|如果|除非|当)[^，。；]{2,80}", atom_text)],
                "exceptions": [part for part in re.findall(r"(?:但|除外|否则)[^，。；]{2,80}", atom_text)],
                "consequence": atom_text,
                "atom_text": atom_text,
                "summary": atom_text[:180],
                "retrieval_terms": _terms_for_clause(clause_no),
                "facts": _numeric_facts(atom_text),
                "is_active": True,
            }
            if not atom:
                db.add(ClauseAtom(clause_node_id=node.id, atom_no=atom_no, **payload_values))
                touched_atoms += 1
            else:
                for key, value in payload_values.items():
                    setattr(atom, key, value)
                touched_atoms += int(atom.atom_text != atom_text)
        for atom_no, atom in existing_atoms.items():
            if atom_no not in active_atom_nos:
                atom.is_active = False

    db.flush()
    nodes_by_no = {item.clause_no: item for item in db.scalars(select(ClauseNode).where(ClauseNode.document_id == document.id, ClauseNode.is_active.is_(True))).all()}
    for source_no, target_no in (("4.2", "4.3"), ("13.2", "15.2")):
        source_node, target_node = nodes_by_no.get(source_no), nodes_by_no.get(target_no)
        if source_node and target_node and not db.scalar(select(ClauseLink.id).where(ClauseLink.source_node_id == source_node.id, ClauseLink.target_node_id == target_node.id, ClauseLink.link_type == "explicit_reference")):
            db.add(ClauseLink(source_node_id=source_node.id, target_node_id=target_node.id, link_type="explicit_reference", source_text=f"按照{target_no}条"))

    playbook = db.scalar(select(Playbook).where(Playbook.playbook_key == PLAYBOOK_KEY, Playbook.version == PLAYBOOK_VERSION))
    if not playbook:
        playbook = Playbook(
            playbook_key=PLAYBOOK_KEY,
            name=PLAYBOOK_NAME,
            version=PLAYBOOK_VERSION,
            contract_type="租赁",
            our_role="出租方",
            scenario="叉车/特种设备",
            description="基础租赁 + 我方出租方 + 叉车特种设备 + 林德2025.01基准的组合式 Playbook",
            is_active=True,
        )
        db.add(playbook)
        db.flush()
    existing_checks = {item.check_code: item for item in db.scalars(select(FocusedCheck).where(FocusedCheck.playbook_id == playbook.id)).all()}
    for order_index, spec in enumerate(CHECK_SPECS, start=1):
        check = existing_checks.get(spec.code)
        values = {
            "order_index": order_index,
            "name": spec.name,
            "category": spec.category,
            "applies_when": {"contract_type": ["租赁"], "our_role": ["出租方"]},
            "query_pack": {
                "exact_terms": list(spec.exact_terms),
                "synonyms": list(spec.synonyms),
                "clause_no_hints": list(spec.clause_refs),
                "adverse_patterns": list(spec.adverse_patterns),
            },
            "required_slots": [f"slot_{index}" for index in range(1, len(spec.required_groups) + 1)],
            "deterministic_rules": ["全部必需槽位命中为MET", "不利模式命中为UNMET", "部分槽位命中为PARTIAL", "完整检索后无候选为NOT_MENTIONED"],
            "legal_rag_triggers": list(spec.legal_rag_triggers),
            "requirement_level": spec.requirement_level,
            "base_risk_level": spec.base_risk_level,
            "recommendation": spec.recommendation,
            "redline_strategy": spec.redline_strategy,
            "expected_absence_check": spec.expected_absence_check,
            "human_confirmation_required": spec.human_confirmation_required,
            "is_active": True,
        }
        if not check:
            check = FocusedCheck(playbook_id=playbook.id, check_code=spec.code, **values)
            db.add(check)
            db.flush()
        else:
            for key, value in values.items():
                setattr(check, key, value)
        mapped_node_ids = set(db.scalars(select(CheckBaselineMap.clause_node_id).where(CheckBaselineMap.check_id == check.id)).all())
        for clause_no in spec.clause_refs:
            node = nodes_by_no.get(clause_no)
            if node and node.id not in mapped_node_ids:
                db.add(CheckBaselineMap(check_id=check.id, clause_node_id=node.id, map_type="supports"))
                mapped_node_ids.add(node.id)
    db.flush()
    mapped_nodes = set(db.scalars(
        select(CheckBaselineMap.clause_node_id)
        .join(FocusedCheck, FocusedCheck.id == CheckBaselineMap.check_id)
        .where(FocusedCheck.playbook_id == playbook.id, FocusedCheck.is_active.is_(True))
    ).all())
    governed_nodes = [node for node in nodes_by_no.values() if node.requirement_level != "informational"]
    active_nodes = {node.id for node in governed_nodes}
    return {
        "document_id": document.id,
        "playbook_id": playbook.id,
        "authoritative_nodes": len(nodes_by_no),
        "active_checks": len(CHECK_SPECS),
        "unmapped_nodes": sorted(node.clause_no for node in governed_nodes if node.id not in mapped_nodes),
        "touched_nodes": touched_nodes,
        "touched_atoms": touched_atoms,
    }


def active_focused_checks(db: Session) -> list[FocusedCheck]:
    playbook = db.scalar(select(Playbook).where(Playbook.playbook_key == PLAYBOOK_KEY, Playbook.version == PLAYBOOK_VERSION, Playbook.is_active.is_(True)))
    if not playbook:
        return []
    return db.scalars(select(FocusedCheck).where(FocusedCheck.playbook_id == playbook.id, FocusedCheck.is_active.is_(True)).order_by(FocusedCheck.order_index)).all()


def playbook_coverage(db: Session) -> dict:
    checks = active_focused_checks(db)
    if not checks:
        return {"status": "MISSING", "active_checks": 0, "unmapped_checks": [], "unmapped_nodes": []}
    check_ids = [item.id for item in checks]
    maps = db.scalars(select(CheckBaselineMap).where(CheckBaselineMap.check_id.in_(check_ids))).all()
    mapped_check_ids = {item.check_id for item in maps}
    mapped_node_ids = {item.clause_node_id for item in maps}
    document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.namespace == "company_baseline", KnowledgeDocument.document_key == "LINDE-LEASE-GT", KnowledgeDocument.version == BASELINE_VERSION))
    nodes = db.scalars(select(ClauseNode).where(ClauseNode.document_id == document.id, ClauseNode.is_active.is_(True))).all() if document else []
    unmapped_checks = [item.check_code for item in checks if item.id not in mapped_check_ids and not item.expected_absence_check]
    unmapped_nodes = [item.clause_no for item in nodes if item.requirement_level != "informational" and item.id not in mapped_node_ids]
    return {
        "status": "COMPLETE" if not unmapped_checks and not unmapped_nodes and len(checks) == len(CHECK_SPECS) else "INCOMPLETE",
        "active_checks": len(checks),
        "authoritative_nodes": len(nodes),
        "unmapped_checks": unmapped_checks,
        "unmapped_nodes": unmapped_nodes,
    }


def check_specs_as_dicts() -> list[dict]:
    return [asdict(item) for item in CHECK_SPECS]
