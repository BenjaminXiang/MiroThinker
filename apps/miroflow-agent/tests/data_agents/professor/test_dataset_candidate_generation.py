from __future__ import annotations

from src.data_agents.professor.core_profile_paper_quality_audit import (
    DatasetClosureBucketRow,
    DatasetClosureBuckets,
)
from src.data_agents.professor.dataset_candidate_generation import (
    CandidateProviderFailure,
    CandidateRejection,
    DuplicatePaperRecord,
    DuplicatePaperMergeCandidate,
    ProfessorPaperSummaryCandidate,
    ProfileSummaryFact,
    ProfileSummaryCandidate,
    build_profile_summary_input,
    ResearchOverviewCandidate,
    build_candidate_generation_report,
    generate_professor_paper_summary_candidate,
    generate_profile_summary_candidate,
    generate_research_overview_candidate,
    plan_duplicate_paper_merge_candidate,
    validate_duplicate_merge_candidate,
    validate_paper_summary_candidate,
    validate_profile_summary_candidate,
    validate_research_overview_candidate,
)
from src.data_agents.professor.output_summaries import PaperSummaryInput


def test_candidate_generation_report_counts_candidates_failures_and_skips() -> None:
    report = build_candidate_generation_report(
        _candidate_buckets(),
        candidates=(
            _valid_profile_candidate("PROF-PROFILE-1"),
            ProfileSummaryCandidate(
                professor_id="PROF-PROFILE-2",
                candidate_profile_summary="内容过短。",
                source_ids=("PAGE-2",),
                source_text_hashes=("b" * 64,),
                generation_method="llm_synthesis",
                input_facts=("research_topic: medical image analysis",),
            ),
            _valid_paper_summary_candidate("PROF-PAPER-1"),
            _valid_duplicate_merge_candidate(),
        ),
        provider_failures=(
            CandidateProviderFailure(
                lane="research_overview_backfill",
                professor_id="PROF-OVERVIEW-1",
                provider="fake-llm",
                stage="llm_translation",
                error_class="TimeoutError",
                retryable=True,
                next_action="retry_with_same_source_hash",
            ),
        ),
        rejections=(
            CandidateRejection(
                lane="duplicate_paper_merge",
                professor_id="PROF-DUP-2",
                duplicate_group_id="PROF-DUP-2:2024:title",
                reason="ambiguous_fuzzy_match",
                next_action="manual_duplicate_paper_review",
            ),
        ),
    )

    assert report.mode == "candidate_dry_run"
    assert report.dry_run is True
    assert report.write_allowed is False
    assert report.selection_hash
    assert report.closure_selection_hash
    assert report.closure_selection_hash != report.selection_hash

    by_lane = {lane.lane: lane for lane in report.lanes}
    profile = by_lane["profile_summary_repair"]
    assert profile.dataset_input_count == 2
    assert profile.input_count == 2
    assert profile.candidate_count == 2
    assert profile.validation_failure_count == 0
    assert profile.provider_failure_count == 0
    assert profile.skipped_count == 0
    assert profile.affected_professor_ids == ("PROF-PROFILE-1", "PROF-PROFILE-2")
    assert profile.validation_failures == ()
    assert profile.samples[0]["write_evidence"]["candidate_profile_summary"]
    weak_profile = next(
        sample
        for sample in profile.samples
        if sample["professor_id"] == "PROF-PROFILE-2"
    )
    weak_gate = weak_profile["write_evidence"]["candidate_generation"]
    assert weak_gate["candidate_status"] == "needs_review"
    assert weak_gate["write_recommendation"] == "review_before_write"
    assert weak_gate["source_confidence"] == "strong"
    assert "profile_summary_length_out_of_range" in weak_gate["quality_flags"]
    assert weak_gate["llm_self_check"]["hard_rejection"] is False

    research = by_lane["research_overview_backfill"]
    assert research.candidate_count == 0
    assert research.provider_failure_count == 1
    assert research.provider_failures[0]["provider"] == "fake-llm"
    assert research.provider_failures[0]["retryable"] is True

    duplicate = by_lane["duplicate_paper_merge"]
    assert duplicate.candidate_count == 1
    assert duplicate.skipped_count == 1
    assert duplicate.affected_professor_ids == ("PROF-DUP-1",)
    assert duplicate.affected_paper_ids == ("PAPER-CANON", "PAPER-OLD")
    assert duplicate.rejections[0]["reason"] == "ambiguous_fuzzy_match"


def test_profile_summary_input_assembly_collects_grounded_sources() -> None:
    profile_input = build_profile_summary_input(
        professor_id="PROF-PROFILE-1",
        canonical_name="Ahmed Elazab",
        institution="清华大学",
        department="深圳国际研究生院",
        title="助理教授、博士生导师",
        source_page_id="PAGE-1",
        source_url="https://example.edu/prof/ahmed",
        profile_raw_text=(
            "研究领域介绍 My research focuses on developing trustworthy artificial "
            "intelligence for medical image analysis, with a special emphasis on "
            "brain disease diagnosis and prognosis."
        ),
        facts=(
            ProfileSummaryFact(
                fact_type="research_topic",
                value="可信人工智能、医学影像分析、脑疾病诊断预后",
                evidence_span="research_topic evidence",
                source_page_id="PAGE-1",
            ),
        ),
        paper_summary=(
            "论文围绕多模态神经影像融合、稀疏特征选择和阿尔茨海默病诊断展开。"
        ),
        linked_output_titles=(
            "Improved Alzheimer's disease diagnosis using multimodal sparse similarity feature selection and auxiliary data",
        ),
    )

    assert profile_input.professor_id == "PROF-PROFILE-1"
    assert profile_input.identity_line == (
        "Ahmed Elazab现任清华大学深圳国际研究生院助理教授、博士生导师"
    )
    assert profile_input.source_text_hash == "d" * 64 or len(
        profile_input.source_text_hash
    ) == 64
    assert profile_input.source_ids == ("PAGE-1",)
    assert profile_input.input_facts == (
        "research_topic:可信人工智能、医学影像分析、脑疾病诊断预后",
    )
    assert profile_input.linked_output_titles[0].startswith("Improved Alzheimer's")


def test_generate_profile_summary_candidate_uses_provider_and_ignores_hidden_company_gap() -> None:
    profile_input = build_profile_summary_input(
        professor_id="PROF-PROFILE-1",
        canonical_name="Ahmed Elazab",
        institution="清华大学",
        department="深圳国际研究生院",
        title="助理教授、博士生导师",
        source_page_id="PAGE-1",
        source_url="https://example.edu/prof/ahmed",
        profile_raw_text="研究方向包括可信人工智能、医学影像分析和脑疾病诊断预后。",
        facts=(
            ProfileSummaryFact(
                fact_type="research_topic",
                value="可信人工智能、医学影像分析、脑疾病诊断预后",
                evidence_span="研究方向包括可信人工智能、医学影像分析和脑疾病诊断预后。",
                source_page_id="PAGE-1",
            ),
        ),
        paper_summary=(
            "论文围绕多模态神经影像融合、稀疏特征选择和阿尔茨海默病诊断展开。"
        ),
        linked_output_titles=("Improved Alzheimer's disease diagnosis",),
    )

    result = generate_profile_summary_candidate(
        profile_input,
        provider=lambda _: _valid_profile_candidate("PROF-PROFILE-1").candidate_profile_summary,
        provider_name="fake-llm",
    )

    assert isinstance(result, ProfileSummaryCandidate)
    assert result.professor_id == "PROF-PROFILE-1"
    assert result.generation_method == "llm_synthesis"
    assert result.source_ids == ("PAGE-1",)
    assert result.source_text_hashes == (profile_input.source_text_hash,)
    assert validate_profile_summary_candidate(result).valid is True


def test_generate_profile_summary_candidate_rejects_unsupported_and_provider_failure() -> None:
    unsupported_input = build_profile_summary_input(
        professor_id="PROF-EMPTY",
        canonical_name="空数据",
        institution="清华大学",
        department=None,
        title=None,
        source_page_id=None,
        source_url=None,
        profile_raw_text=None,
        facts=(),
        paper_summary=None,
        linked_output_titles=(),
    )

    unsupported = generate_profile_summary_candidate(unsupported_input)

    assert isinstance(unsupported, CandidateRejection)
    assert unsupported.reason == "missing_grounded_profile_inputs"
    assert unsupported.next_action == "recrawl_official_profile_or_add_grounded_facts"

    def failing_provider(_profile_input):
        raise TimeoutError("provider timed out")

    provider_failure = generate_profile_summary_candidate(
        build_profile_summary_input(
            professor_id="PROF-PROVIDER",
            canonical_name="Provider Case",
            institution="清华大学",
            department="深圳国际研究生院",
            title="助理教授",
            source_page_id="PAGE-2",
            source_url="https://example.edu/prof/provider",
            profile_raw_text="研究方向包括人工智能和医学影像。",
            facts=(
                ProfileSummaryFact(
                    fact_type="research_topic",
                    value="人工智能、医学影像",
                    evidence_span="研究方向包括人工智能和医学影像。",
                    source_page_id="PAGE-2",
                ),
            ),
            paper_summary="论文围绕人工智能和医学影像展开。",
            linked_output_titles=("A grounded paper title",),
        ),
        provider=failing_provider,
        provider_name="fake-llm",
    )

    assert isinstance(provider_failure, CandidateProviderFailure)
    assert provider_failure.provider == "fake-llm"
    assert provider_failure.stage == "profile_summary_generation"
    assert provider_failure.error_class == "TimeoutError"


def test_generate_research_overview_candidate_extracts_chinese_source() -> None:
    result = generate_research_overview_candidate(
        professor_id="PROF-OVERVIEW-ZH",
        profile_raw_text=(
            "个人简介 Ahmed Elazab。研究领域介绍 研究方向包括可信人工智能、"
            "医学影像分析、多模态神经影像融合和脑疾病辅助诊断。教育经历 清华大学。"
        ),
        source_page_id="PAGE-ZH",
        source_url="https://example.edu/prof/overview-zh",
    )

    assert isinstance(result, ResearchOverviewCandidate)
    assert result.professor_id == "PROF-OVERVIEW-ZH"
    assert result.source_language == "zh"
    assert result.generation_method == "official_extract"
    assert result.research_overview_content.startswith("研究方向包括")
    assert len(result.source_text_hash) == 64
    assert result.to_write_evidence()["source_span"].startswith("研究方向包括")


def test_generate_research_overview_candidate_translates_english_source() -> None:
    calls: list[str] = []

    def translator(source_text: str) -> str:
        calls.append(source_text)
        return (
            "研究方向包括可信人工智能、医学影像分析、多模态神经影像融合、"
            "脑疾病诊断预后和可解释临床决策支持。"
        )

    result = generate_research_overview_candidate(
        professor_id="PROF-OVERVIEW-EN",
        profile_raw_text=(
            "Biography Ahmed Elazab. Research Overview My research focuses on "
            "developing trustworthy artificial intelligence for medical image "
            "analysis, with a special emphasis on brain disease diagnosis and "
            "prognosis. Education Tsinghua University."
        ),
        source_page_id="PAGE-EN",
        source_url="https://example.edu/prof/overview-en",
        translator=translator,
        provider_name="fake-llm",
    )

    assert isinstance(result, ResearchOverviewCandidate)
    assert calls and calls[0].startswith("My research focuses")
    assert result.source_language == "en"
    assert result.generation_method == "llm_translation"
    assert result.provider_metadata == {"provider": "fake-llm"}
    assert len(result.source_text_hash) == 64


def test_generate_research_overview_candidate_rejects_missing_source_and_provider_failure() -> None:
    missing = generate_research_overview_candidate(
        professor_id="PROF-MISSING",
        profile_raw_text="个人简介 缺少研究概况。",
        source_page_id=None,
        source_url=None,
    )

    assert isinstance(missing, CandidateRejection)
    assert missing.reason == "source_missing"
    assert missing.next_action == "recrawl_official_profile_research_overview"

    def failing_translator(_source_text: str) -> str:
        raise RuntimeError("translator unavailable")

    failure = generate_research_overview_candidate(
        professor_id="PROF-FAIL",
        profile_raw_text=(
            "Research Overview My research focuses on trustworthy artificial "
            "intelligence for medical image analysis."
        ),
        source_page_id="PAGE-FAIL",
        source_url="https://example.edu/prof/fail",
        translator=failing_translator,
        provider_name="fake-llm",
    )

    assert isinstance(failure, CandidateProviderFailure)
    assert failure.lane == "research_overview_backfill"
    assert failure.stage == "llm_translation"
    assert failure.error_class == "RuntimeError"


def test_generate_professor_paper_summary_candidate_uses_verified_deduplicated_links() -> None:
    result = generate_professor_paper_summary_candidate(
        professor_id="PROF-PAPER-1",
        professor_name="Ahmed Elazab",
        paper_inputs=(
            _paper_input(
                paper_id="PAPER-1",
                title="Improved Alzheimer's disease diagnosis using multimodal sparse similarity feature selection and auxiliary data",
                canonical_source="prof_page_official",
                summary_zh="论文提出多模态稀疏相似性特征选择方法，用于提升阿尔茨海默病诊断。",
            ),
            _paper_input(
                paper_id="PAPER-2",
                title="Explainable medical image analysis for brain disease prognosis",
                canonical_source="crossref_enriched",
                summary_zh="论文关注脑疾病预后中的可解释医学影像分析。",
            ),
        ),
        source_page_ids=("PAGE-PAPER-1",),
        provider=lambda _generation_input: _valid_paper_summary_candidate(
            "PROF-PAPER-1"
        ).candidate_paper_summary,
        provider_name="fake-llm",
    )

    assert isinstance(result, ProfessorPaperSummaryCandidate)
    assert result.professor_id == "PROF-PAPER-1"
    assert result.verified_paper_ids == ("PAPER-1", "PAPER-2")
    assert result.excluded_paper_ids == ()
    assert result.duplicate_status == "deduplicated"
    assert result.source_page_ids == ("PAGE-PAPER-1",)
    assert validate_paper_summary_candidate(result).valid is True


def test_generate_professor_paper_summary_candidate_rejects_provider_only_and_flags_duplicates() -> None:
    provider_only = generate_professor_paper_summary_candidate(
        professor_id="PROF-PAPER-2",
        professor_name="Provider Only",
        paper_inputs=(
            _paper_input(
                paper_id="PAPER-PROVIDER",
                title="Provider-only paper",
                canonical_source="provider_only_author_search",
                match_reason="Candidate OpenAlex paper link from exact-name author search",
            ),
        ),
        source_page_ids=(),
    )

    assert isinstance(provider_only, CandidateRejection)
    assert provider_only.reason == "provider_only_author_search"
    assert provider_only.next_action == "verify_papers_from_official_professor_page"

    duplicate_blocked = generate_professor_paper_summary_candidate(
        professor_id="PROF-PAPER-3",
        professor_name="Duplicate Blocked",
        paper_inputs=(
            _paper_input(
                paper_id="PAPER-OK",
                title="Verified paper",
                canonical_source="prof_page_official",
            ),
        ),
        source_page_ids=("PAGE-PAPER-3",),
        duplicate_status="unresolved_duplicate",
    )

    assert isinstance(duplicate_blocked, ProfessorPaperSummaryCandidate)
    assert duplicate_blocked.duplicate_status == "unresolved_duplicate"
    duplicate_gate = duplicate_blocked.to_write_evidence()["candidate_generation"]
    assert duplicate_gate["candidate_status"] == "needs_review"
    assert "unresolved_duplicate_status" in duplicate_gate["quality_flags"]
    assert duplicate_gate["write_recommendation"] == "review_before_write"


def test_plan_duplicate_paper_merge_candidate_prefers_identifier_and_richer_row() -> None:
    result = plan_duplicate_paper_merge_candidate(
        professor_id="PROF-DUP-DOI",
        duplicate_group_id="PROF-DUP-DOI:2024:title",
        papers=(
            DuplicatePaperRecord(
                paper_id="PAPER-PAGE",
                title="Same Paper",
                year=2024,
                doi="10.1000/same",
                arxiv_id=None,
                authors_display="Ahmed Elazab; Co Author",
                venue="Test Venue",
                canonical_source="prof_page_only",
                source_page_ids=("PAGE-DUP",),
            ),
            DuplicatePaperRecord(
                paper_id="PAPER-RICH",
                title="Same Paper",
                year=2024,
                doi="10.1000/same",
                arxiv_id=None,
                authors_display="Ahmed Elazab; Co Author",
                venue="Test Venue",
                canonical_source="crossref_enriched",
                source_page_ids=("PAGE-DUP",),
                abstract_clean="Abstract is available.",
                summary_zh="已有中文摘要。",
                citation_count=20,
            ),
        ),
    )

    assert isinstance(result, DuplicatePaperMergeCandidate)
    assert result.canonical_paper_id == "PAPER-RICH"
    assert result.old_paper_ids == ("PAPER-PAGE",)
    assert result.evidence_type == "doi_match"
    assert result.confidence == 0.99
    assert "PAGE-DUP" in result.source_page_ids


def test_plan_duplicate_paper_merge_candidate_accepts_arxiv_and_flags_ambiguous() -> None:
    arxiv = plan_duplicate_paper_merge_candidate(
        professor_id="PROF-DUP-ARXIV",
        duplicate_group_id="PROF-DUP-ARXIV:2024:title",
        papers=(
            DuplicatePaperRecord(
                paper_id="PAPER-A",
                title="Arxiv Paper",
                year=2024,
                doi=None,
                arxiv_id="2401.12345",
                authors_display="Ahmed Elazab",
                venue="arXiv",
                canonical_source="prof_page_only",
                source_page_ids=("PAGE-ARXIV",),
            ),
            DuplicatePaperRecord(
                paper_id="PAPER-B",
                title="Arxiv Paper",
                year=2024,
                doi=None,
                arxiv_id="arXiv:2401.12345",
                authors_display="Ahmed Elazab",
                venue="arXiv",
                canonical_source="openalex_enriched",
                source_page_ids=("PAGE-ARXIV",),
            ),
        ),
    )

    assert isinstance(arxiv, DuplicatePaperMergeCandidate)
    assert arxiv.evidence_type == "arxiv_match"
    assert arxiv.canonical_paper_id == "PAPER-B"

    ambiguous = plan_duplicate_paper_merge_candidate(
        professor_id="PROF-DUP-FUZZY",
        duplicate_group_id="PROF-DUP-FUZZY:2024:title",
        papers=(
            DuplicatePaperRecord(
                paper_id="PAPER-X",
                title="Common Title",
                year=2024,
                doi=None,
                arxiv_id=None,
                authors_display="Alice Wang",
                venue="Venue A",
                canonical_source="prof_page_only",
                source_page_ids=("PAGE-FUZZY",),
            ),
            DuplicatePaperRecord(
                paper_id="PAPER-Y",
                title="Common Title",
                year=2024,
                doi=None,
                arxiv_id=None,
                authors_display="Bob Li",
                venue="Venue B",
                canonical_source="crossref_enriched",
                source_page_ids=("PAGE-FUZZY",),
            ),
        ),
    )

    assert isinstance(ambiguous, DuplicatePaperMergeCandidate)
    assert ambiguous.evidence_type == "title_year_only"
    assert ambiguous.confidence == 0.60
    ambiguous_gate = ambiguous.to_write_evidence()["candidate_generation"]
    assert ambiguous_gate["candidate_status"] == "needs_review"
    assert ambiguous_gate["write_recommendation"] == "review_before_write"
    assert "unsafe_duplicate_merge_evidence" in ambiguous_gate["quality_flags"]


def test_plan_duplicate_paper_merge_candidate_accepts_source_supported_match() -> None:
    result = plan_duplicate_paper_merge_candidate(
        professor_id="PROF-DUP-SOURCE",
        duplicate_group_id="PROF-DUP-SOURCE:2024:title",
        papers=(
            DuplicatePaperRecord(
                paper_id="PAPER-SOURCE-A",
                title="Source Supported Paper",
                year=2024,
                doi=None,
                arxiv_id=None,
                authors_display="Ahmed Elazab; Co Author",
                venue="Medical Image Analysis",
                canonical_source="prof_page_only",
                source_page_ids=("PAGE-SOURCE",),
            ),
            DuplicatePaperRecord(
                paper_id="PAPER-SOURCE-B",
                title="Source Supported Paper",
                year=2024,
                doi=None,
                arxiv_id=None,
                authors_display="Ahmed Elazab; Co Author",
                venue="Medical Image Analysis",
                canonical_source="crossref_enriched",
                source_page_ids=("PAGE-SOURCE",),
                abstract_clean="Abstract is available.",
            ),
        ),
    )

    assert isinstance(result, DuplicatePaperMergeCandidate)
    assert result.evidence_type == "source_supported_title_year_author_venue_match"
    assert result.confidence == 0.93
    assert result.canonical_paper_id == "PAPER-SOURCE-B"


def test_profile_and_research_candidates_validate_source_grounding() -> None:
    profile = _valid_profile_candidate("PROF-PROFILE-1")
    profile_result = validate_profile_summary_candidate(profile)

    assert profile_result.valid is True
    assert profile.to_write_evidence()["candidate_profile_summary"] == (
        profile.candidate_profile_summary
    )

    invalid_profile = ProfileSummaryCandidate(
        professor_id="PROF-PROFILE-2",
        candidate_profile_summary="内容过短。",
        source_ids=("PAGE-2",),
        source_text_hashes=("b" * 64,),
        generation_method="llm_synthesis",
        input_facts=("research_topic: AI",),
    )
    invalid_profile_result = validate_profile_summary_candidate(invalid_profile)
    assert invalid_profile_result.valid is True
    assert "profile_summary_length_out_of_range" in invalid_profile_result.errors

    research = ResearchOverviewCandidate(
        professor_id="PROF-OVERVIEW-1",
        research_overview_content=(
            "研究方向包括可信人工智能、医学影像分析、多模态神经影像融合、"
            "脑疾病诊断预后和可解释临床决策支持。"
        ),
        source_language="en",
        source_text_hash="c" * 64,
        source_span=(
            "My research focuses on trustworthy artificial intelligence for "
            "medical image analysis."
        ),
        generation_method="llm_translation",
        provider_metadata={"provider": "fake-llm", "model": "unit-test"},
    )
    research_result = validate_research_overview_candidate(research)

    assert research_result.valid is True
    research_evidence = research.to_write_evidence()
    assert research_evidence["research_overview_content"].startswith("研究方向包括")
    assert research_evidence["source_text_hash"] == "c" * 64
    assert research_evidence["generation_method"] == "llm_translation"
    assert research_evidence["candidate_generation"]["candidate_status"] == "ready"

    invalid_research = ResearchOverviewCandidate(
        professor_id="PROF-OVERVIEW-2",
        research_overview_content="Research focuses on medical imaging.",
        source_language="en",
        source_text_hash="",
        source_span="Research focuses on medical imaging.",
        generation_method="official_extract",
    )
    invalid_research_result = validate_research_overview_candidate(invalid_research)
    assert invalid_research_result.valid is False
    assert "missing_chinese_research_overview" in invalid_research_result.errors
    assert "missing_source_text_hash" in invalid_research_result.errors
    assert "invalid_generation_method_for_language" in invalid_research_result.errors

    weak_hash_research = ResearchOverviewCandidate(
        professor_id="PROF-OVERVIEW-3",
        research_overview_content=(
            "研究方向包括可信人工智能、医学影像分析和脑疾病诊断预后。"
        ),
        source_language="en",
        source_text_hash="",
        source_span="My research focuses on trustworthy artificial intelligence.",
        generation_method="llm_translation",
    )
    weak_hash_result = validate_research_overview_candidate(weak_hash_research)
    assert weak_hash_result.valid is True
    assert "missing_source_text_hash" in weak_hash_result.errors
    weak_hash_evidence = weak_hash_research.to_write_evidence()["candidate_generation"]
    assert weak_hash_evidence["candidate_status"] == "needs_review"
    assert weak_hash_evidence["source_confidence"] == "weak"
    assert "missing_source_text_hash" in weak_hash_evidence["quality_flags"]


def test_paper_summary_candidate_requires_verified_deduplicated_inputs() -> None:
    candidate = _valid_paper_summary_candidate("PROF-PAPER-1")
    result = validate_paper_summary_candidate(candidate)

    assert result.valid is True
    write_evidence = candidate.to_write_evidence()
    assert write_evidence["candidate_paper_summary"].startswith("该教师论文围绕")
    assert write_evidence["paper_ids"] == ["PAPER-1", "PAPER-2"]
    assert write_evidence["source_page_provenance"] == ["PAGE-PAPER-1"]
    assert write_evidence["excluded_paper_ids"] == ["PAPER-3"]
    assert write_evidence["exclusion_reasons"]["PAPER-3"] == (
        "provider_only_author_search"
    )

    invalid = ProfessorPaperSummaryCandidate(
        professor_id="PROF-PAPER-2",
        candidate_paper_summary="该教师论文涉及人工智能。",
        verified_paper_ids=(),
        excluded_paper_ids=("PAPER-X",),
        exclusion_reasons={"PAPER-X": "provider_only_author_search"},
        duplicate_status="unresolved_duplicate",
        source_page_ids=(),
        generation_method="llm_synthesis",
    )
    invalid_result = validate_paper_summary_candidate(invalid)

    assert invalid_result.valid is False
    assert "missing_verified_paper_ids" in invalid_result.errors
    assert "missing_source_page_provenance" in invalid_result.errors
    assert "unresolved_duplicate_status" in invalid_result.errors

    unresolved_duplicate = ProfessorPaperSummaryCandidate(
        professor_id="PROF-PAPER-3",
        candidate_paper_summary="该教师论文涉及人工智能和医学影像分析，已验证论文可支撑后续产出摘要。",
        verified_paper_ids=("PAPER-OK",),
        excluded_paper_ids=(),
        exclusion_reasons={},
        duplicate_status="unresolved_duplicate",
        source_page_ids=("PAGE-PAPER-3",),
        generation_method="llm_synthesis",
    )
    unresolved_result = validate_paper_summary_candidate(unresolved_duplicate)
    assert unresolved_result.valid is True
    assert "unresolved_duplicate_status" in unresolved_result.errors
    unresolved_gate = unresolved_duplicate.to_write_evidence()["candidate_generation"]
    assert unresolved_gate["candidate_status"] == "needs_review"
    assert unresolved_gate["write_recommendation"] == "review_before_write"


def test_duplicate_merge_candidate_accepts_identifier_match_and_rejects_unsafe() -> None:
    candidate = _valid_duplicate_merge_candidate()
    result = validate_duplicate_merge_candidate(candidate)

    assert result.valid is True
    write_evidence = candidate.to_write_evidence()
    assert write_evidence["canonical_paper_id"] == "PAPER-CANON"
    assert write_evidence["old_paper_ids"] == ["PAPER-OLD"]
    assert write_evidence["paper_ids"] == ["PAPER-CANON", "PAPER-OLD"]
    assert write_evidence["merge_reason"] == "dataset_candidate_generation:doi_match"

    unsafe = DuplicatePaperMergeCandidate(
        professor_id="PROF-DUP-3",
        duplicate_group_id="PROF-DUP-3:2024:title",
        canonical_paper_id="PAPER-A",
        old_paper_ids=("PAPER-B",),
        paper_ids=("PAPER-A", "PAPER-B"),
        evidence_type="title_year_only",
        confidence=0.60,
        merge_reason="dataset_candidate_generation:title_year_only",
        source_page_ids=("PAGE-DUP-3",),
    )
    unsafe_result = validate_duplicate_merge_candidate(unsafe)

    assert unsafe_result.valid is True
    assert "unsafe_duplicate_merge_evidence" in unsafe_result.errors
    unsafe_gate = unsafe.to_write_evidence()["candidate_generation"]
    assert unsafe_gate["candidate_status"] == "needs_review"
    assert unsafe_gate["source_confidence"] == "weak"


def _candidate_buckets() -> DatasetClosureBuckets:
    return DatasetClosureBuckets(
        bucket_limit=2,
        summary={
            "ready_summary_lt_200": {
                "total": 2,
                "sampled": 2,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            },
            "missing_research_overview_zh": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "research_overview_backfill",
            },
            "missing_professor_paper_summary": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "professor_paper_summary_generation",
            },
            "duplicate_verified_paper_title_year_groups": {
                "total": 2,
                "sampled": 2,
                "truncated": False,
                "remediation_lane": "duplicate_paper_merge",
            },
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-PROFILE-1",
                automatic_eligibility=True,
            ),
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-PROFILE-2",
                automatic_eligibility=True,
            ),
            DatasetClosureBucketRow(
                blocker_type="missing_research_overview_zh",
                entity_type="professor",
                remediation_lane="research_overview_backfill",
                professor_id="PROF-OVERVIEW-1",
                automatic_eligibility=True,
            ),
            DatasetClosureBucketRow(
                blocker_type="missing_professor_paper_summary",
                entity_type="professor",
                remediation_lane="professor_paper_summary_generation",
                professor_id="PROF-PAPER-1",
                automatic_eligibility=True,
            ),
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id="PROF-DUP-1",
                duplicate_group_id="PROF-DUP-1:2024:title",
                automatic_eligibility=True,
            ),
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id="PROF-DUP-2",
                duplicate_group_id="PROF-DUP-2:2024:title",
                automatic_eligibility=False,
                skip_reason="ambiguous_fuzzy_match",
            ),
        ],
    )


def _valid_profile_candidate(professor_id: str) -> ProfileSummaryCandidate:
    summary = (
        "Ahmed Elazab现任清华大学深圳国际研究生院助理教授、博士生导师，研究聚焦可信人工智能、"
        "医学影像分析和脑疾病诊断预后。他结合机器学习、深度学习与多模态神经影像融合，构建稳健的"
        "计算机辅助检测与诊断系统，并通过模式识别和神经信息学发现疾病特异性生物标志物。其工作强调"
        "可解释人工智能和临床可解释性，目标是形成可融入医疗流程的可靠决策支持工具。相关成果可支撑"
        "教师画像中的研究领域、论文摘要和后续可追溯检索。"
    )
    assert 200 <= len(summary) <= 300
    return ProfileSummaryCandidate(
        professor_id=professor_id,
        candidate_profile_summary=summary,
        source_ids=("PAGE-1",),
        source_text_hashes=("a" * 64,),
        generation_method="llm_synthesis",
        input_facts=("research_topic: trustworthy artificial intelligence",),
    )


def _valid_paper_summary_candidate(professor_id: str) -> ProfessorPaperSummaryCandidate:
    return ProfessorPaperSummaryCandidate(
        professor_id=professor_id,
        candidate_paper_summary=(
            "该教师论文围绕可信人工智能、医学影像分析和脑疾病诊断展开，重点覆盖多模态神经影像融合、"
            "稀疏特征选择、疾病预后建模和可解释辅助诊断。已验证论文显示其研究持续连接机器学习方法"
            "与临床影像场景，能够为阿尔茨海默病等脑疾病识别提供模型、特征和证据链支撑。"
        ),
        verified_paper_ids=("PAPER-1", "PAPER-2"),
        excluded_paper_ids=("PAPER-3",),
        exclusion_reasons={"PAPER-3": "provider_only_author_search"},
        duplicate_status="deduplicated",
        source_page_ids=("PAGE-PAPER-1",),
        generation_method="llm_synthesis",
    )


def _valid_duplicate_merge_candidate() -> DuplicatePaperMergeCandidate:
    return DuplicatePaperMergeCandidate(
        professor_id="PROF-DUP-1",
        duplicate_group_id="PROF-DUP-1:2024:title",
        canonical_paper_id="PAPER-CANON",
        old_paper_ids=("PAPER-OLD",),
        paper_ids=("PAPER-CANON", "PAPER-OLD"),
        evidence_type="doi_match",
        confidence=0.99,
        merge_reason="dataset_candidate_generation:doi_match",
        source_page_ids=("PAGE-DUP-1",),
    )


def _paper_input(
    *,
    paper_id: str,
    title: str,
    canonical_source: str,
    summary_zh: str | None = None,
    match_reason: str = "verified from official professor page",
) -> PaperSummaryInput:
    return PaperSummaryInput(
        paper_id=paper_id,
        title=title,
        year=2024,
        venue="Test Venue",
        abstract_clean="This paper studies trustworthy AI for medical image analysis.",
        summary_zh=summary_zh,
        authors_display="Ahmed Elazab; Co Author",
        citation_count=12,
        canonical_source=canonical_source,
        link_status="verified",
        match_reason=match_reason,
    )
