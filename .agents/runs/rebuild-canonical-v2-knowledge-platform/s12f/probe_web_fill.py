"""Probe: can web search + fetch fill the 4 known workbook gaps?

For each failing turn we run targeted serper queries and check whether the
missing KEY terms appear in titles/snippets; for promising URLs we fetch the
page and check full-page text.  The script reuses the project's own
WebSearchProvider (key file fallback), never prints the key, and only reports
term hits and result metadata.

Usage (from the worktree root):
  python3 .agents/runs/rebuild-canonical-v2-knowledge-platform/s12f/probe_web_fill.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import requests  # noqa: E402  (must precede src/ sys.path insertion)

sys.path.insert(0, "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/apps/miroflow-agent")

from src.data_agents.providers.web_search import WebSearchProvider  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\\1>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\\s+", " ", text)


def main() -> None:
    provider = WebSearchProvider(timeout=30.0)
    assert provider.api_key, "no serper key available"
    probes = [
        ("T3-开普勒", ["上海开普勒机器人有限公司 酒店送餐机器人",
                        "开普勒机器人 送餐机器人 产品",
                        "Kepler Robotics hotel delivery robot",
                        "上海开普勒机器人 业务 服务机器人 送餐"]),
        ("T19-真实采集", ["具身智能 数据采集 遥操作 动捕 真机",
                           "具身智能 动捕数据 采集方式",
                           "人形机器人 真机数据采集 动作捕捉 遥操作",
                           "具身智能 数据采集 全模态"]),
        ("T22-合成数据", ["具身智能 合成数据 物理仿真引擎 生成方法",
                           "具身智能 合成数据 基于规则生成",
                           "具身智能 合成数据 生成式模型 规则 仿真",
                           "合成数据 具身智能 实现方法 厂商"]),
        ("T23-运动操作", ["具身智能 数据需求 运动 操作 环境感知 多模态交互",
                           "具身智能 全模态真机采集",
                           "具身智能 本体感知 环境感知 多模态交互 数据采集",
                           "人形机器人 运动数据 操作数据 采集方式 差异"]),
    ]
    key_terms = {
        "T3-开普勒": ["酒店送餐", "送餐机器人", "酒店机器人", "服务机器人"],
        "T19-真实采集": ["动捕", "动作捕捉", "遥操作", "真机"],
        "T22-合成数据": ["物理仿真", "仿真引擎", "基于规则", "规则生成", "生成式"],
        "T23-运动操作": ["环境感知", "多模态交互", "本体感知", "全模态", "真机采集"],
    }
    fetch_terms = {
        "T3-开普勒": ["酒店", "送餐", "配送"],
        "T19-真实采集": ["动捕", "动作捕捉"],
        "T22-合成数据": ["物理仿真", "规则"],
        "T23-运动操作": ["环境感知", "多模态", "全模态"],
    }
    for group, queries in probes:
        print(f"\n########## {group} ##########")
        fetch_candidates: dict[str, tuple[str, list[str]]] = {}
        for qi, query in enumerate(queries, 1):
            try:
                resp = provider.search(query)
            except Exception as exc:  # noqa: BLE001
                print(f"  [q{qi}] {query!r} -> SEARCH ERROR {exc!r}")
                continue
            results = resp.get("organic", []) if isinstance(resp, dict) else []
            print(f"  [q{qi}] {query!r} -> {len(results)} organic results")
            terms = key_terms[group]
            for ri, item in enumerate(results[:6], 1):
                title = item.get("title", "")
                url = item.get("link", "")
                snippet = item.get("snippet", "")
                hit = [t for t in terms if t in title or t in snippet]
                print(f"    {ri}. {title[:70]}")
                print(f"       {url[:110]}")
                if snippet:
                    print(f"       {snippet[:130]}")
                if hit:
                    print(f"       HIT terms: {hit}")
                    fetch_candidates.setdefault(url, (title, hit))
        # fetch the top candidate pages (max 3 per group) and check full text
        print(f"  -- fetching {min(3, len(fetch_candidates))} candidate pages --")
        for url, (title, hit) in list(fetch_candidates.items())[:3]:
            try:
                resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
                text = strip_html(resp.text)
                terms = fetch_terms[group]
                found = [t for t in terms if t in text]
                print(f"    fetch {resp.status_code} {len(text)} chars {url[:100]}")
                print(f"       page HIT: {found if found else 'NONE'}")
            except Exception as exc:  # noqa: BLE001
                print(f"    fetch FAILED {url[:100]}: {exc!r}")


if __name__ == "__main__":
    main()
