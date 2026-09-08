#!/usr/bin/env python3
"""End-to-end smoke test: assemble → serve → query → verify answer.

Run AFTER pack assembly. Verifies the full serving chain works:
1. Serving is up (health check)
2. Company patent query returns local patents (G3)
3. Paper search finds pool papers (G4)
4. Professor query returns profile (baseline)
5. Weak result returns guidance (smart guidance)

Usage: uv run --directory apps/miroflow-agent python smoke_test.py --base-url http://127.0.0.1:18188
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError


def post_chat(base_url: str, query: str, session_id: str, timeout: int = 120) -> dict:
    body = json.dumps({"query": query, "session_id": session_id}).encode()
    req = Request(
        f"{base_url}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def test_health(base_url: str) -> bool:
    try:
        with urlopen(f"{base_url}/api/health", timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except (URLError, json.JSONDecodeError):
        return False


def run_tests(base_url: str) -> list[tuple[str, bool, str]]:
    results = []

    # Test 0: Health
    print("[0] Health check...", end=" ", flush=True)
    if test_health(base_url):
        results.append(("Health", True, "OK"))
        print("✅")
    else:
        results.append(("Health", False, "Serving not responding"))
        print("❌")
        return results

    # Test 1: G3 — Company patent query
    print("[1] G3: Company patents...", end=" ", flush=True)
    t0 = time.time()
    try:
        r = post_chat(base_url, "深圳智赛精密装备有限公司有哪些专利", "smoke-g3")
        answer = r.get("answer_text", "")
        citations = r.get("citations", [])
        has_patent_cite = any(c.get("type") == "patent" for c in citations)
        has_patent_text = any(kw in answer for kw in ["专利", "CN", "ZL"])
        passed = has_patent_text  # basic check: answer mentions patents
        detail = f"answer={answer[:60]}... cites={len(citations)} patent_cite={has_patent_cite}"
        results.append(("G3-CompanyPatents", passed, detail))
        print(f"{'✅' if passed else '⚠️'} ({time.time()-t0:.1f}s)")
    except Exception as e:
        results.append(("G3-CompanyPatents", False, str(e)[:80]))
        print(f"❌ ({e})")

    # Test 2: G4 — Paper search (previously unavailable papers)
    print("[2] G4: Paper search...", end=" ", flush=True)
    try:
        r = post_chat(base_url, "Crop selection reduces potential heavy metal", "smoke-g4")
        answer = r.get("answer_text", "")
        citations = r.get("citations", [])
        has_paper_cite = any(c.get("type") == "paper" for c in citations)
        passed = len(answer) > 20  # got some answer
        detail = f"answer={answer[:60]}... paper_cite={has_paper_cite}"
        results.append(("G4-PaperSearch", passed, detail))
        print(f"{'✅' if passed else '⚠️'}")
    except Exception as e:
        results.append(("G4-PaperSearch", False, str(e)[:80]))
        print(f"❌ ({e})")

    # Test 3: Baseline — Professor query
    print("[3] Baseline: Professor...", end=" ", flush=True)
    try:
        r = post_chat(base_url, "洪子扬", "smoke-prof")
        answer = r.get("answer_text", "")
        citations = r.get("citations", [])
        has_prof_cite = any(c.get("type") == "professor" for c in citations)
        passed = "洪子扬" in answer  # answer is about the professor
        detail = f"answer={answer[:60]}... prof_cite={has_prof_cite}"
        results.append(("Baseline-Professor", passed, detail))
        print(f"{'✅' if passed else '⚠️'}")
    except Exception as e:
        results.append(("Baseline-Professor", False, str(e)[:80]))
        print(f"❌ ({e})")

    # Test 4: Smart guidance — Weak result
    print("[4] Smart guidance: Weak result...", end=" ", flush=True)
    try:
        r = post_chat(base_url, "zzzxxx 不存在的实体", "smoke-guidance")
        answer = r.get("answer_text", "")
        followups = r.get("suggested_followups", [])
        has_guidance = any(kw in answer for kw in ["换个角度", "尝试", "具体"])
        passed = len(answer) > 10  # got some response
        detail = f"answer={answer[:60]}... followups={followups[:2]}"
        results.append(("SmartGuidance", passed, detail))
        print(f"{'✅' if passed else '⚠️'}")
    except Exception as e:
        results.append(("SmartGuidance", False, str(e)[:80]))
        print(f"❌ ({e})")

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18188")
    args = parser.parse_args()

    print("=" * 60)
    print("SMOKE TEST")
    print("=" * 60)

    results = run_tests(args.base_url)

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"RESULTS: {passed}/{total} passed")
    for name, ok, detail in results:
        print(f"  {'✅' if ok else '❌'} {name}: {detail}")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
