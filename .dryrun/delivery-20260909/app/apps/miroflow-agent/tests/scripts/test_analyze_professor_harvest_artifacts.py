from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "analyze_professor_harvest_artifacts.py"
)
spec = importlib.util.spec_from_file_location("analyze_professor_harvest_artifacts", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _pad(text: str, target: int = 180) -> str:
    return text + "。" * max(0, target - len(text))


def _profile(**overrides):
    good_summary = (
        "张三现任南方科技大学计算机科学与工程系教授，长期研究大语言模型安全、"
        "大语言模型安全对齐、可信人工智能和红队评测。近年来在NeurIPS、ICML等会议发表多篇论文，"
        "围绕RLHF训练策略、风险识别、对抗样本和模型可靠性提出系统方法。"
        "其成果支撑智能系统安全部署、模型评估基准建设和高可靠应用落地，"
        "并服务于面向医疗、工业和科研场景的可控生成式智能系统。"
        "团队持续构建自动化安全评测工具链，关注数据治理、模型行为解释和复杂任务规划中的可靠性问题。"
    )
    data = {
        "name": "张三",
        "institution": "南方科技大学",
        "department": "计算机科学与工程系",
        "title": "教授",
        "research_directions": ["大语言模型安全", "大语言模型安全对齐", "RLHF训练策略"],
        "research_directions_source": "paper_driven",
        "top_papers": [
            {
                "title": "Safety Alignment for LLMs",
                "year": 2024,
                "venue": "NeurIPS",
                "citation_count": 100,
                "source": "openalex",
            }
        ],
        "paper_count": 10,
        "profile_summary": good_summary,
        "enrichment_source": "paper_enriched",
        "evidence_urls": ["https://faculty.sustech.edu.cn/zhangsan"],
        "profile_url": "https://faculty.sustech.edu.cn/zhangsan",
        "roster_source": "https://www.sustech.edu.cn/",
        "extraction_status": "structured",
    }
    data.update(overrides)
    return data


def test_analyze_harvest_flags_refusal_summary_and_paper_coverage(tmp_path: Path):
    output_dir = tmp_path / "harvest"
    output_dir.mkdir()
    refusal_profile = _profile(
        name="李四",
        department=None,
        title=None,
        research_directions=[],
        top_papers=[],
        paper_count=None,
        profile_summary=_pad(
            "由于您提供的原始信息中缺乏研究方向、职称、院系、代表论文等核心学术维度，"
            "无法构建符合学术规范且达到要求的专业简介。"
        ),
        profile_url="https://faculty.sustech.edu.cn/lisi",
    )
    (output_dir / "enriched_v3.jsonl").write_text(
        "\n".join(
            [
                json.dumps(_profile(), ensure_ascii=False),
                json.dumps(refusal_profile, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "paper_staging.jsonl").write_text(
        json.dumps(
            {
                "title": "Safety Alignment for LLMs",
                "authors": ["张三"],
                "year": 2024,
                "venue": "NeurIPS",
                "abstract": "LLM safety.",
                "doi": "10.1234/example",
                "citation_count": 100,
                "keywords": ["LLM"],
                "source_url": "https://openalex.org/W1",
                "source": "openalex",
                "link_status": "candidate",
                "anchoring_professor_id": "unused-for-this-test",
                "anchoring_professor_name": "张三",
                "anchoring_institution": "南方科技大学",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = module.analyze_harvest(output_dir)

    assert report["profiles"]["valid_profiles"] == 2
    assert report["profiles"]["quality_status"]["ready"] == 1
    assert report["profiles"]["quality_status"]["low_confidence"] == 1
    assert report["profiles"]["gap_flags"]["summary_boilerplate_or_refusal"] == 1
    assert report["paper_staging"]["valid_records"] == 1
    assert report["paper_staging"]["by_source"] == [
        {"name": "openalex", "count": 1}
    ]
    assert report["paper_staging"]["by_link_status"] == [
        {"name": "candidate", "count": 1}
    ]
