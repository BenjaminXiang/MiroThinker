#!/usr/bin/env python3
"""G2 shared helpers: read-only lookup.sqlite3 loaders + identity-key normalizers.

Used by g2_identity_audit.py and g2_cross_release.py. Read-only by design:
every connection is opened with mode=ro&immutable=1.
"""
import json
import re
import sqlite3
from collections import Counter, defaultdict

RUN14_DB = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
S12F_DB = "/var/tmp/mirothinker-canonical-v2-s12f/serving-pack/lookup.sqlite3"

DOMAINS = ("company", "professor", "paper", "patent")


def connect(db_path):
    return sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)


def load_lookup(db_path):
    """Return [{domain, cid, release, content(dict)}] for every lookup document."""
    con = connect(db_path)
    rows = []
    for cid, pid, rid, dj in con.execute(
        "SELECT canonical_object_id, projection_id, release_id, document_json "
        "FROM lookup_document"
    ):
        d = json.loads(dj)
        lc = d.get("lookup_content")
        if isinstance(lc, str):
            lc = json.loads(lc)
        if not isinstance(lc, dict):
            lc = {}
        dom = d.get("domain") or pid.rsplit(":", 1)[-1]
        rows.append({"domain": dom, "cid": cid, "release": rid, "content": lc})
    con.close()
    return rows


def release_ids(db_path):
    con = connect(db_path)
    out = {k: v for k, v in con.execute("SELECT key, value FROM build_metadata")}
    con.close()
    return out


# ---------------------------------------------------------------- company names

_WS = re.compile(r"\s+")
_PAREN = re.compile(r"[（(][^）)]*[）)]")
_LEGAL = [
    "集团股份有限公司",
    "股份有限公司",
    "有限责任公司",
    "有限公司",
    "有限合伙企业",
    "集团有限公司",
    "集团",
    "公司",
]
# trailing industry/business words for the brand-stem tier
_INDUSTRY_TAIL = [
    "机器人",
    "生物医药",
    "人工智能",
    "电子科技",
    "智能科技",
    "科技实业",
    "半导体",
    "新能源",
    "供应链",
    "大数据",
    "物联网",
    "云计算",
    "环保科技",
    "医疗器械",
    "生物科技",
    "信息技术",
    "网络科技",
    "智能",
    "科技",
    "技术",
    "电子",
    "实业",
    "信息",
    "网络",
    "生物",
    "医疗",
    "材料",
    "光电",
    "通信",
    "软件",
    "数据",
    "自动化",
    "装备",
    "机械",
    "环保",
    "芯片",
    "微电子",
    "仪器",
    "检测",
    "能源",
    "电力",
    "汽车",
    "物流",
    "控股",
    "投资",
    "医药",
    "健康",
    "传媒",
    "文化",
    "教育",
]
# region prefixes worth stripping for the approximate tiers
_REGIONS = [
    "内蒙古自治区",
    "广西壮族自治区",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
    "西藏自治区",
    "香港特别行政区",
    "澳门特别行政区",
    "黑龙江省",
    "河北省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "山西省",
    "陕西省",
    "四川省",
    "贵州省",
    "云南省",
    "辽宁省",
    "吉林省",
    "甘肃省",
    "青海省",
    "海南省",
    "石家庄市",
    "深圳市",
    "东莞市",
    "广州市",
    "惠州市",
    "珠海市",
    "佛山市",
    "中山市",
    "北京市",
    "上海市",
    "成都市",
    "重庆市",
    "天津市",
    "杭州市",
    "南京市",
    "苏州市",
    "武汉市",
    "长沙市",
    "西安市",
    "合肥市",
    "青岛市",
    "无锡市",
    "宁波市",
    "厦门市",
    "福州市",
    "济南市",
    "郑州市",
    "常州市",
    "绵阳市",
    "粤港澳大湾区",
    "深圳",
    "东莞",
    "广州",
    "惠州",
    "珠海",
    "佛山",
    "中山",
    "北京",
    "上海",
    "成都",
    "重庆",
    "天津",
    "杭州",
    "南京",
    "苏州",
    "武汉",
    "长沙",
    "西安",
    "合肥",
    "青岛",
    "无锡",
    "宁波",
    "厦门",
    "福州",
    "济南",
    "郑州",
    "常州",
    "绵阳",
    "东莞市",
]
_REGIONS = sorted(_REGIONS, key=len, reverse=True)


def _strip_region(s):
    # Whitelist-only: a fuzzy ^X市 regex misfires on brand words like
    # 普智城市/图灵集市 (strips "普智城"+市), so only known region names count.
    changed = True
    while changed:
        changed = False
        for r in _REGIONS:
            if len(s) - len(r) >= 2 and s.startswith(r):
                s = s[len(r):]
                changed = True
                break
    return s


def _strip_legal(s):
    changed = True
    while changed:
        changed = False
        for suf in _LEGAL:
            if len(s) - len(suf) >= 2 and s.endswith(suf):
                s = s[: -len(suf)]
                changed = True
                break
    return s


def _strip_industry(s, rounds=2):
    for _ in range(rounds):
        for w in _INDUSTRY_TAIL:
            if len(s) - len(w) >= 2 and s.endswith(w):
                s = s[: -len(w)]
                break
        else:
            break
    return s


def company_name_key(name, tier):
    """tier1 = exact (whitespace-normalized); tier2 = brand+industry core;
    tier3 = brand stem (industry tail stripped)."""
    if not isinstance(name, str):
        return ""
    s = _WS.sub("", name)
    if tier == 1:
        return s
    s = _PAREN.sub("", s)
    s = _strip_region(s)
    s = _strip_legal(s)
    if tier == 2:
        return s
    return _strip_industry(s)


def paper_title_key(title, strict=True):
    if not isinstance(title, str):
        return ""
    t = title.strip().lower()
    if strict:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", t)
    return t


def patent_number_key(number):
    if not isinstance(number, str):
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", number).upper()


def professor_name_key(name):
    return _WS.sub("", name) if isinstance(name, str) else ""


def name_of(value):
    """Field values in lookup_content are often {reference_id, name} dicts or
    lists of such dicts. Return a comparable string."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return _WS.sub(" ", str(value.get("name") or ""))
    if isinstance(value, list):
        return "|".join(name_of(v) for v in value if name_of(v))
    return _WS.sub(" ", str(value))


def group_stats(rows, keyfn):
    """rows -> (groups dict, fragmented dict size>=2, size histogram)."""
    groups = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k:
            groups[k].append(r)
    frag = {k: v for k, v in groups.items() if len(v) >= 2}
    hist = Counter(len(v) for v in frag.values())
    return dict(groups), frag, hist


PLACEHOLDER_MARKERS = (
    "not supplied",
    "no dedicated summary",
    "not provided",
    "尚未",
    "暂无",
    "暂缺",
    "待补充",
    "n/a",
)


def is_placeholder(text):
    if not isinstance(text, str):
        return False
    low = text.strip().lower()
    return any(m in low for m in PLACEHOLDER_MARKERS)


def assertion_family(content):
    """Provenance family from the first evidence assertion id."""
    ev = content.get("evidence")
    if isinstance(ev, list) and ev and isinstance(ev[0], dict):
        aid = str(ev[0].get("assertion_id") or "")
        parts = aid.split(":")
        if len(parts) >= 2:
            return parts[1]
    return "unknown"
