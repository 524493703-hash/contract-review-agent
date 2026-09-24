from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import LegalAuthority


@dataclass(frozen=True)
class LegalSeed:
    authority: str
    title: str
    document_no: str
    article_no: str
    content: str
    summary: str
    keywords: tuple[str, ...]
    effective_from: date
    source_url: str
    effective_to: date | None = None


# Legal materials live in a separate, versioned namespace from company clauses.
# The text below is deliberately limited to the provisions used by the lease
# playbook. Each record carries its official source and effective period.
LEGAL_SEEDS: tuple[LegalSeed, ...] = (
    LegalSeed(
        authority="全国人民代表大会",
        title="中华人民共和国民法典",
        document_no="中华人民共和国主席令第四十五号",
        article_no="第四百九十六条",
        content="采用格式条款订立合同的，提供格式条款的一方应当遵循公平原则确定当事人之间的权利和义务，并采取合理的方式提示对方注意免除或者减轻其责任等与对方有重大利害关系的条款，按照对方的要求，对该条款予以说明。提供格式条款的一方未履行提示或者说明义务，致使对方没有注意或者理解与其有重大利害关系的条款的，对方可以主张该条款不成为合同的内容。",
        summary="格式条款提供方负有公平拟定、合理提示和按要求说明义务；未履行可能导致异常条款不成为合同内容。",
        keywords=("格式条款", "提示说明义务", "重大利害关系", "条款并入", "举证责任"),
        effective_from=date(2021, 1, 1),
        source_url="https://www.cac.gov.cn/2020-06/01/c_15925617772683192.htm",
    ),
    LegalSeed(
        authority="全国人民代表大会",
        title="中华人民共和国民法典",
        document_no="中华人民共和国主席令第四十五号",
        article_no="第五百八十四条至第五百八十五条",
        content="损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益，但不得超过违约方订立合同时预见到或者应当预见到的损失。当事人可以约定违约金；约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。",
        summary="合同损失受可预见性限制；约定违约金过分高于实际损失时，当事人可以请求司法或仲裁调整。",
        keywords=("违约金调整", "违约金过高", "损失赔偿", "可预见性", "全部损失", "责任限制"),
        effective_from=date(2021, 1, 1),
        source_url="https://www.court.gov.cn/zixun/xiangqing/233181.html",
    ),
    LegalSeed(
        authority="最高人民法院",
        title="最高人民法院关于适用《中华人民共和国民法典》合同编通则若干问题的解释",
        document_no="法释〔2023〕13号",
        article_no="第六十四条至第六十五条",
        content="当事人一方通过反诉或者抗辩的方式请求调整违约金的，人民法院依法予以支持。人民法院判断约定违约金是否过分高于损失时，应以民法典第五百八十四条规定的损失为基础，兼顾合同主体、交易类型、履行情况、过错程度、履约背景等因素，遵循公平原则和诚信原则进行衡量。",
        summary="法院可依请求调整违约金，并结合实际损失、履行、过错和交易背景综合判断是否过高。",
        keywords=("违约金调整", "违约金过高", "实际损失", "公平原则", "诚信原则", "举证责任"),
        effective_from=date(2023, 12, 5),
        source_url="https://gongbao.court.gov.cn/Details/f4722cf61c92a585f04b2ecd334f5b.html",
    ),
    LegalSeed(
        authority="全国人民代表大会",
        title="中华人民共和国民法典",
        document_no="中华人民共和国主席令第四十五号",
        article_no="第四百九十七条",
        content="有下列情形之一的，该格式条款无效：（一）具有本法第一编第六章第三节和本法第五百零六条规定的无效情形；（二）提供格式条款一方不合理地免除或者减轻其责任、加重对方责任、限制对方主要权利；（三）提供格式条款一方排除对方主要权利。",
        summary="不合理免责、减责、加重对方责任、限制或排除对方主要权利的格式条款存在无效风险。",
        keywords=("格式条款效力", "免责", "减轻责任", "加重责任", "限制主要权利", "排除主要权利", "单方定价条款效力"),
        effective_from=date(2021, 1, 1),
        source_url="https://www.cac.gov.cn/2020-06/01/c_15925617772683192.htm",
    ),
    LegalSeed(
        authority="全国人民代表大会",
        title="中华人民共和国民法典",
        document_no="中华人民共和国主席令第四十五号",
        article_no="第四百九十八条",
        content="对格式条款的理解发生争议的，应当按照通常理解予以解释。对格式条款有两种以上解释的，应当作出不利于提供格式条款一方的解释。格式条款和非格式条款不一致的，应当采用非格式条款。",
        summary="格式条款按通常理解解释；有多种解释时作不利于提供方的解释，且非格式条款优先。",
        keywords=("格式条款", "合同解释", "不利解释", "非格式条款优先", "文件优先级"),
        effective_from=date(2021, 1, 1),
        source_url="https://www.cac.gov.cn/2020-06/01/c_15925617772683192.htm",
    ),
    LegalSeed(
        authority="最高人民法院",
        title="最高人民法院关于适用《中华人民共和国民法典》合同编通则若干问题的解释",
        document_no="法释〔2023〕13号",
        article_no="第十条",
        content="提供格式条款的一方在合同订立时采用通常足以引起对方注意的文字、符号、字体等明显标识，提示对方注意免除或者减轻其责任、排除或者限制对方权利等与对方有重大利害关系的异常条款的，人民法院可以认定其已经履行提示义务。提供格式条款的一方对其已经尽到提示义务或者说明义务承担举证责任。",
        summary="异常格式条款应以明显标识提示并按要求作可理解的说明，提供方对完成提示说明承担举证责任。",
        keywords=("格式条款", "提示说明义务", "异常条款", "明显标识", "举证责任", "协商留痕"),
        effective_from=date(2023, 12, 5),
        source_url="https://gongbao.court.gov.cn/Details/f4722cf61c92a585f04b2ecd334f5b.html",
    ),
    LegalSeed(
        authority="全国人民代表大会",
        title="中华人民共和国民法典",
        document_no="中华人民共和国主席令第四十五号",
        article_no="第六百二十条至第六百二十二条",
        content="当事人约定检验期限的，买受人应当在检验期限内通知数量或者质量不符合约定的情形；怠于通知的，视为符合约定。出卖人知道或者应当知道标的物不符合约定的，买受人不受通知时间限制。约定检验期限过短、按标的物性质和交易习惯难以完成全面检验的，该期限仅视为对外观瑕疵提出异议的期限。",
        summary="短期验收或默示验收通常不能当然覆盖难以及时发现的非外观瑕疵，且明知瑕疵时通知期限例外适用。",
        keywords=("默示验收", "检验期限", "质量异议", "隐蔽瑕疵", "外观瑕疵", "安全缺陷"),
        effective_from=date(2021, 1, 1),
        source_url="https://www.cac.gov.cn/2020-06/01/c_15925617772683192.htm",
    ),
    LegalSeed(
        authority="全国人民代表大会常务委员会",
        title="中华人民共和国特种设备安全法",
        document_no="中华人民共和国主席令第四号",
        article_no="第三十九条至第四十二条",
        content="特种设备使用单位应当对其使用的特种设备进行经常性维护保养和定期自行检查，并作出记录。使用单位应当在检验合格有效期届满前一个月提出定期检验要求；未经定期检验或者检验不合格的特种设备，不得继续使用。设备出现故障或者异常情况，应当全面检查并消除事故隐患后方可继续使用。",
        summary="特种设备使用单位承担经常维护、定期自行检查、定期检验申报和故障停用整改义务。",
        keywords=("特种设备", "使用单位", "维护保养", "定期检验", "安全维保", "停用", "事故隐患", "强制义务"),
        effective_from=date(2014, 1, 1),
        source_url="https://www.samr.gov.cn/tzsbj/zcfg/flfg/art/2019/art_39715c5a62f64e32aa522fcc2afd6298.html",
    ),
    LegalSeed(
        authority="国家市场监督管理总局",
        title="场（厂）内专用机动车辆安全技术规程实施意见",
        document_no="市监特设发〔2022〕87号",
        article_no="第三部分",
        content="场车使用单位应按要求办理使用登记和定期（首次）检验。自2023年12月1日起新生产出厂的叉车必须安装安全监控装置，定期（首次）检验应包含安全监控装置检查；此前制造的叉车适用相应过渡安排。",
        summary="明确场车使用登记、定期检验及叉车安全监控装置的实施和过渡要求。",
        keywords=("叉车", "场车", "使用登记", "定期检验", "安全监控装置", "TSG 81-2022", "现行安全技术规范"),
        effective_from=date(2022, 12, 1),
        source_url="https://www.samr.gov.cn/tzsbj/tzgg/bgtwh/art/2022/art_c1409d0e1bb24d0e995d1f062b5b4b71.html",
    ),
    LegalSeed(
        authority="国家市场监督管理总局",
        title="特种设备使用管理规则及实施通知",
        document_no="TSG 08—2026 / 市监特设发〔2026〕82号",
        article_no="使用登记、停用及风险管控",
        content="《特种设备使用管理规则》（TSG 08—2026）自2026年5月1日起施行。特种设备移装后应办理使用登记变更；停用超过安全检验合格有效期的，重新启用前应按要求进行定期检验；使用单位应结合实际制定安全风险管控清单和每日安全检查记录。",
        summary="现行使用管理规则强调登记变更、超期停用后的检验以及风险清单和每日检查记录。",
        keywords=("特种设备", "使用单位", "使用登记", "登记变更", "定期检验", "每日检查", "风险管控", "TSG 08-2026", "现行安全技术规范"),
        effective_from=date(2026, 5, 1),
        source_url="https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/tzsbs/art/2026/art_add0c578d19a40abb58e042b4983d59b.html",
    ),
    LegalSeed(
        authority="最高人民法院",
        title="最高人民法院关于适用《中华人民共和国民事诉讼法》的解释",
        document_no="法释〔2022〕11号",
        article_no="第二十九条至第三十一条",
        content="书面协议管辖包括书面合同中的协议管辖条款；根据管辖协议，起诉时能够确定管辖法院的，从其约定。经营者使用格式条款与消费者订立管辖协议，未采取合理方式提请消费者注意的，消费者可以主张管辖协议无效。",
        summary="协议管辖应采用书面形式并能确定法院；格式管辖条款还应满足提示要求。",
        keywords=("协议管辖有效性", "法院管辖", "书面协议", "实际联系", "格式条款", "提示义务"),
        effective_from=date(2022, 4, 10),
        source_url="https://www.court.gov.cn/zixun/xiangqing/353651.html",
    ),
)


def _hash(seed: LegalSeed) -> str:
    return hashlib.sha256(seed.content.encode("utf-8")).hexdigest()


def seed_legal_authorities(db: Session) -> dict:
    """Idempotently seed only authoritative sources used by the active playbook."""
    active_ids: list[str] = []
    for seed in LEGAL_SEEDS:
        item = db.scalar(
            select(LegalAuthority).where(
                LegalAuthority.document_no == seed.document_no,
                LegalAuthority.article_no == seed.article_no,
                LegalAuthority.effective_from == seed.effective_from,
            )
        )
        values = {
            "authority": seed.authority,
            "title": seed.title,
            "content": seed.content,
            "summary": seed.summary,
            "keywords": list(seed.keywords),
            "jurisdiction": "CN",
            "effective_to": seed.effective_to,
            "source_url": seed.source_url,
            "content_hash": _hash(seed),
            "status": "active",
        }
        if item is None:
            item = LegalAuthority(
                document_no=seed.document_no,
                article_no=seed.article_no,
                effective_from=seed.effective_from,
                **values,
            )
            db.add(item)
            db.flush()
        else:
            for key, value in values.items():
                setattr(item, key, value)
        active_ids.append(item.id)
    db.flush()
    return {"seeded": len(active_ids), "authority_ids": active_ids}


def _query_terms(query: str) -> list[str]:
    chunks = re.split(r"[\s,，、；;：:/+()（）]+", query or "")
    return list(dict.fromkeys(chunk.strip() for chunk in chunks if len(chunk.strip()) >= 2))


def retrieve_legal_authorities(
    db: Session,
    query: str,
    *,
    as_of_date: date,
    jurisdiction: str = "CN",
    limit: int = 5,
) -> list[dict]:
    """Return effective legal records with transparent lexical match scores."""
    authorities = db.scalars(
        select(LegalAuthority).where(
            LegalAuthority.jurisdiction == jurisdiction,
            LegalAuthority.status == "active",
            LegalAuthority.effective_from <= as_of_date,
            or_(LegalAuthority.effective_to.is_(None), LegalAuthority.effective_to >= as_of_date),
        )
    ).all()
    query_terms = _query_terms(query)
    ranked: list[dict] = []
    for item in authorities:
        keyword_text = " ".join(str(value) for value in (item.keywords or []))
        title_text = f"{item.title} {item.article_no} {item.summary}"
        corpus = f"{title_text} {keyword_text} {item.content}"
        matched: list[str] = []
        score = 0
        for term in query_terms:
            if term in corpus or any(keyword in term for keyword in (item.keywords or []) if len(str(keyword)) >= 2):
                matched.append(term)
                score += 18 if term in keyword_text else 10 if term in title_text else 5
        if "格式条款" in query and "格式条款" in corpus:
            score += 25
        if any(term in query for term in ("特种设备", "使用登记", "定期检验", "安全维保")) and "特种设备" in corpus:
            score += 25
        if "管辖" in query and "管辖" in corpus:
            score += 25
        if score:
            ranked.append({
                "authority": item,
                "relevance_score": min(100, score),
                "matched_terms": list(dict.fromkeys(matched)),
            })
    ranked.sort(key=lambda value: (-value["relevance_score"], -value["authority"].effective_from.toordinal(), value["authority"].article_no))
    return ranked[:limit]
