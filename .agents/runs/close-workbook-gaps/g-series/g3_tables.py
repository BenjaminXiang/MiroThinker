#!/usr/bin/env python3
"""Emit the report tables (markdown) from g3-vocabulary.json.

Usage: python3 g3_tables.py            # writes g3-appendix-tables.md and prints it
"""
import json
import sys

BASE = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series"
V = f"{BASE}/g3-vocabulary.json"
OUT = f"{BASE}/g3-appendix-tables.md"


def co(r, f):
    return r["hits"].get(f, 0)


def main():
    with open(V, encoding="utf-8") as fh:
        d = json.load(fh)

    vocab = d["vocabulary"]
    corpus = d["corpus_vocabulary"]
    ext = [r for r in d["extension_vocabulary"] if r["lens"] == "pack_taxonomy"]
    top30 = corpus + ext[:21]
    for i, r in enumerate(top30, 1):
        r["top_rank"] = i

    print("### T1 corpus lens (9)")
    print("| # | term | catT | distinctQ | sessions | wholeRun | tier | 代表问句 |")
    print("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(corpus, 1):
        print(f"| {i} | {r['term']} | {r['cat_turns']} | {r['cat_distinct_queries']} | "
              f"{r['cat_sessions']} | {r['cat_whole_run_turns']} | {r['tier']} | {r['example_query']} |")

    print()
    print("### T2 extension lens (top 21 by pack reach)")
    print("| # | term | reach | phrases | tier | cCov | compInd | compItag | compTech | prodDesc | profSum | patents t/a/s | papers t/a/s | profRD |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in ext[:21]:
        print(f"| {r['top_rank'] if 'top_rank' in r else ''} | {r['term']} | {r['pack_tail_reach']} | "
              f"{r['pack_tail_phrases']} | {r['tier']} | {r['company_structured_coverage']*100:.1f}% | "
              f"{co(r,'company.industry')} | {co(r,'company.industry_tags')} | {co(r,'company.tech_tags')} | "
              f"{co(r,'company.product_description')} | {co(r,'company.profile_summary')} | "
              f"{co(r,'patent.title')}/{co(r,'patent.abstract')}/{co(r,'patent.summary_text')} | "
              f"{co(r,'paper.title')}/{co(r,'paper.abstract')}/{co(r,'paper.summary_text')} | "
              f"{co(r,'professor.research_directions')} |")

    print()
    print("### T3 anchoring matrix for the top 30 (all fields)")
    cols = [
        ("company.industry", "ind"), ("company.industry_tags", "itag"), ("company.tech_tags", "tech"),
        ("company.product_description", "prod"), ("company.profile_summary", "prof"),
        ("patent.title", "pt"), ("patent.abstract", "pa"), ("patent.summary_text", "ps"),
        ("paper.title", "yt"), ("paper.abstract", "ya"), ("paper.summary_text", "ys"),
        ("professor.research_directions", "prd"), ("professor.profile_summary", "pprof"),
    ]
    print("| # | term | tier | cCov | " + " | ".join(c[1] for c in cols) + " | totalDocs |")
    print("|---" * (5 + len(cols)) + "|")
    for r in top30:
        print(f"| {r['top_rank']} | {r['term']} | {r['tier']} | {r['company_structured_coverage']*100:.1f}% | "
              + " | ".join(str(co(r, c[0])) for c in cols)
              + f" | {r['total_hit_docs']} |")

    print()
    print("### T4 offline verification table (top 15): anchored vs text-only")
    print("| # | term | anchored | textOnly | both | 结构化信号覆盖率 | totalDocs | examples(structured) | examples(text-only) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in d["verification_table"]:
        c = r["company_doc_classes"]
        ex_s = "、".join(e["name"] for e in r["examples_structured"][:3])
        ex_t = "、".join(e["name"] for e in r["examples_text_only"][:3])
        print(f"| {r.get('rank','')} | {r['term']} | {c['anchored']} | {c['text_only']} | {c['both']} | "
              f"{r['company_structured_coverage']*100:.1f}% | {r['total_hit_docs']} | {ex_s} | {ex_t} |")

    print()
    print("### T5 gap list (tier T/N, by traffic)")
    print("| term | tier | catT | fullT | totalDocs | companyStructuredDocs | cCov | 原因 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in d["gap_list"]:
        reason = "无任何字段信号" if r["tier"] == "N" else "仅文本字段（摘要/全文）有信号"
        print(f"| {r['term']} | {r['tier']} | {r['cat_turns']} | {r['full_turns']} | {r['total_hit_docs']} | "
              f"{r['company_structured_docs']} | {r['company_structured_coverage']*100:.1f}% | {reason} |")

    print()
    print("### T6 probe terms (hand-picked boundary cases, NOT part of the vocabulary export)")
    print("| term | in vocab | tier | totalDocs | compTech | prod | prof | patents s | papers s | profRD | cCov |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in d["probe_table"]:
        print(f"| {r['term']} | {'yes' if r['admitted_by'] and 'category_traffic' in r['admitted_by'] else ('via taxonomy' if r['lens']=='probe_in_vocabulary' else 'no')} | "
              f"{r['tier']} | {r['total_hit_docs']} | {co(r,'company.tech_tags')} | "
              f"{co(r,'company.product_description')} | {co(r,'company.profile_summary')} | "
              f"{co(r,'patent.summary_text')} | {co(r,'paper.summary_text')} | "
              f"{co(r,'professor.research_directions')} | {r['company_structured_coverage']*100:.1f}% |")

    print()
    print("### T7 industry labels (41, pack's coarse taxonomy)")
    print("| label | companies | share |")
    print("|---|---|---|")
    for r in d["industry_labels"]:
        print(f"| {r['term']} | {r['companies']} | {r['share']*100:.1f}% |")

    print()
    print("### T8 rejected appendix (top 40)")
    print("| term | reason | catT | fullT |")
    print("|---|---|---|---|")
    for r in d["rejected"][:40]:
        print(f"| {r['term']} | {r['reason']} | {r['cat_turns']} | {r['full_turns']} |")


if __name__ == "__main__":
    import io

    buf = io.StringIO()
    real = sys.stdout

    class Tee:
        def write(self, s):
            buf.write(s)
            real.write(s)

        def flush(self):
            real.flush()

    sys.stdout = Tee()
    main()
    sys.stdout = real
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("# G3 附录表（由 g3_tables.py 从 g3-vocabulary.json 机器生成）\n\n")
        fh.write(buf.getvalue())
    print(f"wrote {OUT}")
