"""Run the real user test set against 18188 and record pass/fail per key point."""
import json
import re
import subprocess
import time
from pathlib import Path

BASE = "http://127.0.0.1:18188/api/chat/stream"
TIMEOUT = 120

# (question, key_points_to_check, depends_on_prev)
TESTS = [
    ("介绍清华的丁文伯", ["丁文伯", "清华", "副教授|助理教授|教授", "机器人|信号处理|人机交互"], None),
    ("他是否有参与哪些企业的创立", ["无界智航", "联合创始人|首席科学家"], "介绍清华的丁文伯"),
    ("中国有哪些成熟的酒店送餐机器人供应商", ["普渡", "开普勒|云迹|擎朗|九号"], None),
    ("上述企业里总部在深圳的企业有哪些", ["普渡|安赛步|深圳"], "中国有哪些成熟的酒店送餐机器人供应商"),
    ("酒店电梯需要送餐机器人能够使用机械臂自主按电梯，上述企业的产品有哪些可以实现", ["普渡"], "中国有哪些成熟的酒店送餐机器人供应商"),
    ("在深圳旅游旅游有哪些涉及黄赌毒的地方是不能去的", ["NOT_ANSWER|不能|无法|违法|零容忍|文明"], None),
    ("请介绍无界智航的相关信息", ["无界智航", "具身智能|机器人|穆世龙"], None),
    ("我想找PCB打板，有哪些推荐", ["嘉立创|一博|深南"], None),
    ("毕业于早稻田，且在深圳专注在机器人行业的企业家有谁", ["早稻田|许晋诚|帕西尼"], None),
    ("华力创科学这家公司相关信息，这家公司的产量特点是什么，市场竞争力怎么样", ["华力创", "力传感|传感器"], None),
    ("光基多维力传感原理具体展开说", ["光学|光基|多维|力|传感"], None),
    ("清华的王学谦的评价如何，他是否是属于大牛", ["王学谦", "清华|教授|领军|人才"], None),
    ("具身智能厂商在数据方面目前存在几种技术路线", ["真实数据|合成数据|仿真"], None),
    ("在真实数据采集路线中，有哪些具体方式", ["遥操作|动捕|真机"], "具身智能厂商在数据方面目前存在几种技术路线"),
    ("优必选有哪些专利", ["优必选", "专利|CN\\d+"], None),
    ("专利 CN117873146A 的详细信息是什么", ["CN117873146A"], None),
]


def ask(query: str) -> dict:
    started = time.time()
    try:
        r = subprocess.run(
            ["curl", "-s", "-N", "-m", str(TIMEOUT), "-X", "POST", BASE,
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"query": query})],
            capture_output=True, text=True, timeout=TIMEOUT + 10,
        )
        answer = ""
        first_chunk = None
        for line in r.stdout.splitlines():
            if line.strip().startswith("data:"):
                try:
                    d = json.loads(line[5:].strip())
                    if d.get("text") and not first_chunk:
                        first_chunk = round(time.time() - started, 1)
                    if "answer_text" in d and d["answer_text"]:
                        answer = d["answer_text"]
                except Exception:
                    pass
        return {
            "query": query,
            "answer": answer,
            "ttft": first_chunk,
            "total": round(time.time() - started, 1),
            "status": "OK" if answer else "EMPTY",
        }
    except Exception as e:
        return {"query": query, "answer": "", "ttft": None,
                "total": round(time.time() - started, 1),
                "status": f"FAIL:{e}"}


def check_keypoints(answer: str, keypoints: list) -> dict:
    results = {}
    for kp in keypoints:
        if kp.startswith("NOT_ANSWER"):
            # 期望答案不出现具体内容
            patterns = kp.replace("NOT_ANSWER|", "").split("|")
            found = any(p in answer for p in patterns if p)
            results[kp] = "PASS" if found else "FAIL"
        else:
            patterns = kp.split("|")
            found = any(p in answer for p in patterns if p)
            results[kp] = "PASS" if found else "FAIL"
    return results


def main():
    results = []
    context = {}  # Store answers for follow-up reference

    for query, keypoints, depends in TESTS:
        print(f"\n[{len(results)+1}/{len(TESTS)}] {query[:50]}...", flush=True)
        result = ask(query)
        context[query] = result["answer"]

        if result["status"] == "OK" and keypoints:
            kp_results = check_keypoints(result["answer"], keypoints)
            result["keypoints"] = kp_results
            passed = sum(1 for v in kp_results.values() if v == "PASS")
            total = len(kp_results)
            result["kp_score"] = f"{passed}/{total}"
            print(f"  TTFT: {result['ttft']}s | 关键点: {passed}/{total}", flush=True)
            for kp, verdict in kp_results.items():
                print(f"    {'✅' if verdict == 'PASS' else '❌'} {kp[:40]}", flush=True)
        else:
            result["kp_score"] = "N/A"
            print(f"  ⚠️ {result['status']}", flush=True)

        # 检查自白
        self_narration = any(
            phrase in result["answer"]
            for phrase in ["本地库暂未", "数据库未建立", "数据覆盖缺口"]
        )
        result["self_narration"] = self_narration
        if self_narration:
            print(f"  ❌ 含自白！", flush=True)

        results.append(result)

    # 汇总
    ok = sum(1 for r in results if r["status"] == "OK")
    kp_scores = [r.get("kp_score", "N/A") for r in results]
    narration_count = sum(1 for r in results if r.get("self_narration"))

    print(f"\n{'='*60}")
    print(f"总问题: {len(results)} | 有答案: {ok} | 含自白: {narration_count}")
    print(f"\n关键点详情:")
    for r, query in zip(results, [t[0] for t in TESTS]):
        print(f"  {r.get('kp_score', 'N/A'):>5} | {'⚠️' if r.get('self_narration') else '  '} | {query[:50]}")

    out = Path("/tmp/testset-results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\n详细结果: {out}")


if __name__ == "__main__":
    main()
