#!/usr/bin/env python3
"""G3 step 2: deterministic category-term extraction (two traffic scopes).

Input : g3-category-queries.json (output of g3_classify_queries.py)
        /var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3 (all turns)
Output: g3-terms.json

Two scopes are extracted with the *same* machinery so that the vocabulary can be
ranked by real traffic and cross-checked:
  scope "category" : the classified category/recommendation turns only
                     (the task's 类目问句 corpus)
  scope "full"     : every turn in the access log (context / cross-check lens;
                     used to rank the gap list, never as the primary vocabulary)

Method (deterministic; no LLM, no hand-authored term list):
 1. Scope filter (category scope only) — drop anaphoric / entity-scoped
    enumerations (它…/他…/该公司…/上述企业…, 优必选…, or enumeration of a
    non-category object: 论文/专利/布局/进展/方式/路线/几种) and safety turns.
 2. Scaffold stripping — a fixed regex list removes question scaffolds
    (有哪些/推荐/介绍/比较/知名…), geo & org names (深圳/大湾区/中国/南山/
    清华/深圳大学…), enumeration head-nouns (公司/企业/厂商/供应商/教授/论文/
    专利…) and single-char particles. NOTE 能/下/上/里/中 are deliberately kept
    so 智能/储能/水下机器人/阿里/中心 survive.
 3. Candidate generation — every contiguous substring of length 2..12 of each
    residual run (so a run `酒店送餐机器人` yields `机器人` and `送餐机器人` too).
 4. Counting — per candidate: turns, distinct queries, sessions; per scope.
    `whole_run_turns` counts only turns where the candidate is exactly a
    residual run (the structural evidence that it is a standalone term and not
    a fragment of a longer string).
 5. No keep/reject filter is applied here (the pack-attestation filter lives in
    g3_finalize.py so that zero-signal terms stay visible in the data).
"""
import json
import re
import sqlite3
from collections import Counter, defaultdict

BASE = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series"
IN = f"{BASE}/g3-category-queries.json"
OUT = f"{BASE}/g3-terms.json"
ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"

# --- scope filter for the category corpus ----------------------------------
ANAPHORIC = re.compile(
    r"^(它|他|她|该|上述)|"
    r"(它|他|她)(有哪些|的)|"
    r"该(公司|企业|中心|教授)|"
    r"上述(企业|公司)|"
    r"^(是否|能否)"
)
NON_CATEGORY_OBJECT = re.compile(
    r"(论文|专利|布局|进展|方式|方法|路线|几种|步骤|措施|政策|链接|详细信息|评价|信息)"
    r"\s*(有哪些|是什么|如何|怎么样|多少)?"
)
ENTITY_POSSESSIVE = re.compile(r"(优必选|普渡|星桥|岚湾|云迹|华力创|国际先进技术)")
SAFETY = re.compile(r"黄赌毒")

# --- scaffolding ------------------------------------------------------------
GEO = [
    "国际先进技术应用推进中心", "国际先进技术应用推广中心", "国际先进技术应用", "国际先进技术",
    "应用推进中心", "应用推广中心", "技术应用推进", "技术应用推广", "先进技术应用",
    "深圳市", "深圳", "广东省", "广东", "大湾区", "粤港澳", "珠三角", "中国", "全国",
    "南山", "福田", "宝安", "龙岗", "龙华", "坪山", "光明", "盐田", "罗湖", "大鹏",
    "深圳大学", "清华", "北京大学", "哈尔滨工业大学", "早稻田", "香港", "澳门",
    "广州", "东莞", "惠州", "珠海", "佛山", "本市", "我市", "本地",
]
SCAFFOLD = [
    "有哪些", "哪几家", "哪几个", "哪些", "哪家", "几家", "几种", "代表",
    "推荐", "帮我", "给我", "请", "介绍", "一下", "想找", "我想", "想", "找", "列举",
    "值得关注", "值得", "关注", "知名", "头部", "龙头", "成熟", "相关", "类似", "其他",
    "别的", "还有", "以及", "目前", "现在", "具体", "分别", "什么", "怎么", "如何",
    "可以", "能够", "实现", "情况", "信息", "方面", "层面", "状态", "大牛",
    "比较", "非常", "并且", "而且", "同时",
    # enumeration head nouns
    "公司", "企业", "企业家", "厂商", "供应商", "制造商", "生产商", "服务商",
    "代理商", "分销商", "集成商", "厂家", "团队", "教授", "老师", "学者",
    "大学", "学院", "研究院", "研究所", "机构", "中心", "平台", "协会", "联盟",
    "论文", "专利", "布局", "进展", "产品", "技术", "领域", "行业", "方向",
    "数据", "方式", "方法", "路线", "方案", "能力", "场景", "应用",
    # org suffixes
    "科技", "有限公司", "有限", "股份", "集团", "责任",
    # particles / fillers (NOTE 能/下/上/里/中 deliberately absent)
    "的", "是", "有", "在", "和", "与", "及", "或", "为", "了", "吗", "呢",
    "都", "要", "做", "从事", "聚焦", "专注", "专门", "研究", "关注", "提供",
    "谁", "这", "那", "个", "家", "种", "些", "般",
]
PUNCT = "，。？！、；：（）()《》〈〉“”\"'·—－-…~ \t\n\r,.;:?!/\\|[]{}<>*#@$%^&+=_`"

CAND_MIN, CAND_MAX = 2, 12
STRIP_RE = re.compile("|".join(re.escape(t) for t in sorted(set(GEO + SCAFFOLD), key=len, reverse=True)))


def residual_runs(query):
    q = query
    for ch in PUNCT:
        q = q.replace(ch, "\x00")
    q = STRIP_RE.sub("\x00", q)
    return [p.strip() for p in q.split("\x00") if p.strip()]


def valid_candidate(s):
    if len(s) < CAND_MIN or len(s) > CAND_MAX:
        return False
    if re.fullmatch(r"[\d\W_]+", s):
        return False
    if re.fullmatch(r"[A-Za-z0-9+/#.\-]+", s):
        return bool(re.search(r"[A-Za-z]", s)) and len(s) >= 2
    return True


def extract(queries, q_sessions=None):
    """queries: list of (query, turns) sorted by turns desc. Returns candidate stats."""
    turns = Counter()
    whole_run = Counter()
    nq = Counter()
    sess = defaultdict(set)
    ex = defaultdict(list)
    for q, n in queries:
        rs = residual_runs(q)
        runs = set(rs)
        seen = set()
        for run in rs:
            L = len(run)
            # a run made only of ASCII letters/digits is one opaque token
            # (paper titles, patent numbers): take the whole token, no substrings
            if re.fullmatch(r"[A-Za-z0-9+/#.\-]+", run):
                spans = [(0, L)]
            else:
                spans = [(i, j) for i in range(L) for j in range(i + CAND_MIN, min(L, i + CAND_MAX) + 1)]
            for i, j in spans:
                s = run[i:j]
                if not valid_candidate(s) or s in seen:
                    continue
                seen.add(s)
                turns[s] += n
                nq[s] += 1
                if s in runs:
                    whole_run[s] += n
                if q_sessions is not None:
                    sess[s] |= q_sessions.get(q, set())
                if len(ex[s]) < 3:
                    ex[s].append(q)
    return turns, whole_run, nq, ex, sess


def main():
    with open(IN, encoding="utf-8") as fh:
        cat = json.load(fh)

    kept, dropped_ana, dropped_safe = [], [], []
    for r in cat["rows"]:
        q = r["query"]
        if SAFETY.search(q):
            dropped_safe.append(q)
            continue
        if ANAPHORIC.search(q) or ENTITY_POSSESSIVE.search(q):
            dropped_ana.append(r)
            continue
        if NON_CATEGORY_OBJECT.search(q) and "具身智能" not in q and "机器人" not in q:
            dropped_ana.append(r)
            continue
        kept.append(r)

    cat_turns = Counter(r["query"] for r in kept)
    cat_sess = defaultdict(set)
    for r in kept:
        cat_sess[r["query"]].add(r["session_id"])

    con = sqlite3.connect(f"file:{ACCESS}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT query FROM turns")
    full_turns = Counter((q or "").strip() for q, in cur.fetchall())
    con.close()

    c_turns, c_run, c_nq, c_ex, c_sess = extract(
        sorted(cat_turns.items(), key=lambda kv: -kv[1]), cat_sess
    )
    f_turns, f_run, f_nq, f_ex, f_sess = extract(
        sorted(full_turns.items(), key=lambda kv: -kv[1])
    )

    terms = sorted(set(c_turns) | set(f_turns))
    payload = {
        "source_access_log": ACCESS,
        "source_category_file": IN,
        "scope_category": {
            "classified_turns": cat["category_turns"],
            "kept_turns": sum(cat_turns.values()),
            "kept_distinct_queries": len(cat_turns),
            "kept_sessions": len({r["session_id"] for r in kept}),
            "dropped_anaphoric_turns": len(dropped_ana),
            "dropped_safety_turns": len(dropped_safe),
        },
        "scope_full": {
            "turns": sum(full_turns.values()),
            "distinct_queries": len(full_turns),
        },
        "kept_category_queries": [
            {
                "query": q,
                "turns": n,
                "sessions": len(cat_sess[q]),
                "residual_runs": residual_runs(q),
            }
            for q, n in sorted(cat_turns.items(), key=lambda kv: -kv[1])
        ],
        "dropped_anaphoric_distinct": sorted({r["query"] for r in dropped_ana}),
        "dropped_safety_distinct": sorted(set(dropped_safe)),
        "terms": [
            {
                "term": t,
                "cat_turns": c_turns.get(t, 0),
                "cat_whole_run_turns": c_run.get(t, 0),
                "cat_distinct_queries": c_nq.get(t, 0),
                "cat_sessions": len(c_sess.get(t, ())),
                "cat_examples": c_ex.get(t, []),
                "full_turns": f_turns.get(t, 0),
                "full_whole_run_turns": f_run.get(t, 0),
                "full_distinct_queries": f_nq.get(t, 0),
                "full_sessions": len(f_sess.get(t, ())),
                "full_examples": f_ex.get(t, []),
            }
            for t in sorted(terms, key=lambda t: (-c_turns.get(t, 0), -f_turns.get(t, 0), -len(t), t))
        ],
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(json.dumps({k: payload[k] for k in ("scope_category", "scope_full")}, ensure_ascii=False, indent=1))
    print()
    print(f"terms={len(terms)}  (category-corpus candidates: {len(c_turns)})")
    print()
    print("--- category scope: candidates with whole-run support ---")
    for t in sorted(c_run, key=lambda t: (-c_run[t], -c_turns[t], t)):
        print(f"  {c_run[t]:4d}w {c_turns[t]:4d}t {c_nq[t]:2d}q  {t:20s} {c_ex[t][0][:60]}")
    print()
    print("--- full scope: top 45 by turns (whole-run flagged) ---")
    for t in sorted(f_turns, key=lambda t: (-f_turns[t], t))[:45]:
        print(f"  {f_turns[t]:4d}t {f_run.get(t,0):4d}w  {t:22s} {f_ex[t][0][:55]}")


if __name__ == "__main__":
    main()
