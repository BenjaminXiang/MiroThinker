# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.paper.cv_pdf import discover_professor_paper_candidates_from_cv_pdf


def test_discover_professor_paper_candidates_from_cv_pdf_extracts_counts_titles_and_metrics():
    sample_text = """
CURRICULUM VITAE
Jianwei Huang
• Research Outputs
– 8 books, 14 book chapters, 172 journal/magazine papers, 226 conference papers
– Google Scholar citations: 20207, H-Index: 71

• Publications
(J1) J. Cheng, N. Ding, J. Lui, and J. Huang, “Trading Continuous Queries,” IEEE/ACM Transactions on Networking, accepted in September 2025
(J2) J. He, Q. Ma, M. Zhang, and J. Huang, “Optimizing Fresh Data Sampling and Trading,” IEEE/ACM Transactions on Networking, accepted in March 2025
[C1] J. Cheng, X. Dai, N. Ding, J. Lui, and J. Huang, “Trading Vector Data in Vector Databases,” IEEE International Conference on Computer Communications (INFOCOM), 2025
[C2] Y. Liu, Y. Xiao, M. Tang, L. Gao, and J. Huang, “Spectral Co-Clustering Based Wireless Network Decomposition for Resource Scheduling,” IEEE WiOpt, 2025
"""

    result = discover_professor_paper_candidates_from_cv_pdf(
        professor_id="PROF-001",
        professor_name="黄建伟",
        institution="香港中文大学（深圳）",
        cv_url="https://jianwei.cuhk.edu.cn/Files/CV.pdf",
        request_bytes=lambda _url: b"%PDF-sample",
        extract_text=lambda _pdf_bytes: sample_text,
        max_papers=3,
    )

    assert result.source == "official_linked_cv"
    assert result.author_id == "https://jianwei.cuhk.edu.cn/Files/CV.pdf"
    assert result.paper_count == 398
    assert result.citation_count == 20207
    assert result.h_index == 71
    assert [paper.title for paper in result.papers] == [
        "Trading Continuous Queries",
        "Optimizing Fresh Data Sampling and Trading",
        "Trading Vector Data in Vector Databases",
    ]
    assert result.papers[0].venue == "IEEE/ACM Transactions on Networking"
    assert result.papers[1].venue == "IEEE/ACM Transactions on Networking"
    assert result.papers[2].venue == "IEEE International Conference on Computer Communications (INFOCOM)"
    assert all(paper.source_url == "https://jianwei.cuhk.edu.cn/Files/CV.pdf" for paper in result.papers)


def test_discover_professor_paper_candidates_from_cv_pdf_rejects_non_pdf_url():
    result = discover_professor_paper_candidates_from_cv_pdf(
        professor_id="PROF-001",
        professor_name="黄建伟",
        institution="香港中文大学（深圳）",
        cv_url="https://jianwei.cuhk.edu.cn/profile",
        request_bytes=lambda _url: (_ for _ in ()).throw(AssertionError("should not fetch")),
    )

    assert result.source == "official_linked_cv"
    assert result.author_id is None
    assert result.paper_count is None
    assert result.papers == []
