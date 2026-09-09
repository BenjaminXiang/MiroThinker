from __future__ import annotations

from src.data_agents.company.generic_source_judgment import (
    GenericSearchResult,
    SourceJudgment,
    run_generic_source_workflow,
)


def test_generic_workflow_rejects_competitor_snippet_without_fetch() -> None:
    fetch_calls: list[str] = []

    def judge(**_kwargs):
        return SourceJudgment(
            status="rejected",
            reason="company_identity_failed",
            evidence_span="另一家公司",
            snippet_sufficiency="irrelevant",
            confirms_identity=False,
            confirms_fact_attribution=False,
            should_fetch=False,
        )

    def fetch(url: str) -> str:
        fetch_calls.append(url)
        raise AssertionError("irrelevant snippet should not be fetched")

    result = run_generic_source_workflow(
        company_name="深圳旭宏医疗科技有限公司",
        search_results=[
            GenericSearchResult(
                title="智象机器人融资新闻",
                url="https://example.com/competitor",
                snippet="智象机器人是一家停车机器人公司。",
            )
        ],
        judge_source=judge,
        fetch_page=fetch,
    )

    assert result.accepted_sources == []
    assert result.rejected_results[0].reason == "company_identity_failed"
    assert fetch_calls == []
    assert [step.tool for step in result.steps] == ["judge_source"]


def test_generic_workflow_fetches_full_page_when_snippet_is_insufficient() -> None:
    judge_calls: list[str | None] = []
    fetch_calls: list[str] = []

    def judge(*, page_text=None, **_kwargs):
        judge_calls.append(page_text)
        if page_text is None:
            return SourceJudgment(
                status="needs_review",
                reason="snippet_insufficient",
                evidence_span="旭宏医疗",
                snippet_sufficiency="insufficient",
                confirms_identity=True,
                confirms_fact_attribution=False,
                should_fetch=True,
            )
        return SourceJudgment(
            status="accepted",
            reason="company_identity_and_fact_attribution_confirmed",
            evidence_span="深圳旭宏医疗科技有限公司发布创新心电产品",
            snippet_sufficiency="sufficient",
            confirms_identity=True,
            confirms_fact_attribution=True,
            should_fetch=False,
        )

    def fetch(url: str) -> str:
        fetch_calls.append(url)
        return "深圳旭宏医疗科技有限公司发布创新心电产品，用于基层医疗心电检测。"

    result = run_generic_source_workflow(
        company_name="深圳旭宏医疗科技有限公司",
        search_results=[
            GenericSearchResult(
                title="旭宏医疗产品动态",
                url="https://example.com/xuhong",
                snippet="旭宏医疗发布产品动态。",
            )
        ],
        judge_source=judge,
        fetch_page=fetch,
    )

    assert fetch_calls == ["https://example.com/xuhong"]
    assert judge_calls == [None, "深圳旭宏医疗科技有限公司发布创新心电产品，用于基层医疗心电检测。"]
    assert [source.url for source in result.accepted_sources] == [
        "https://example.com/xuhong"
    ]
    assert result.accepted_sources[0].trust_reason == (
        "company_identity_and_fact_attribution_confirmed"
    )
    assert [step.tool for step in result.steps] == [
        "judge_source",
        "fetch_webpage",
        "judge_source",
    ]


def test_generic_workflow_requires_identity_and_fact_attribution_for_acceptance() -> None:
    def judge(**_kwargs):
        return SourceJudgment(
            status="accepted",
            reason="missing_fact_attribution",
            evidence_span="旭宏医疗",
            snippet_sufficiency="sufficient",
            confirms_identity=True,
            confirms_fact_attribution=False,
            should_fetch=False,
        )

    result = run_generic_source_workflow(
        company_name="深圳旭宏医疗科技有限公司",
        search_results=[
            GenericSearchResult(
                title="旭宏医疗行业报道",
                url="https://example.com/report",
                snippet="报道提到旭宏医疗，但产品事实无法归属。",
            )
        ],
        judge_source=judge,
        fetch_page=lambda _url: "",
    )

    assert result.accepted_sources == []
    assert result.rejected_results[0].reason == "fact_attribution_failed"


def test_generic_workflow_rejects_near_name_legal_entity_even_if_llm_accepts() -> None:
    def judge(**_kwargs):
        return SourceJudgment(
            status="accepted",
            reason="company_identity_and_fact_attribution_confirmed",
            evidence_span="股一科技（深圳）有限责任公司成立于2022-09-27",
            snippet_sufficiency="sufficient",
            confirms_identity=True,
            confirms_fact_attribution=True,
            should_fetch=False,
        )

    result = run_generic_source_workflow(
        company_name="一股科技",
        search_results=[
            GenericSearchResult(
                title="股一科技（深圳）有限责任公司 - 企查查",
                url="https://example.com/wrong-legal-entity",
                snippet="股一科技（深圳）有限责任公司成立于2022-09-27，法定代表人为李桂民。",
            )
        ],
        judge_source=judge,
        fetch_page=lambda _url: "",
    )

    assert result.accepted_sources == []
    assert result.rejected_results[0].reason == "identity_evidence_missing"


def test_generic_workflow_rejects_short_alias_when_other_legal_entity_is_named() -> None:
    def judge(**_kwargs):
        return SourceJudgment(
            status="accepted",
            reason="company_identity_and_fact_attribution_confirmed",
            evidence_span="天津逸步科技有限公司申请计算机网络信息安全专利",
            snippet_sufficiency="sufficient",
            confirms_identity=True,
            confirms_fact_attribution=True,
            should_fetch=False,
        )

    result = run_generic_source_workflow(
        company_name="逸步科技",
        trusted_identity_terms=("深圳市逸步科技有限公司",),
        search_results=[
            GenericSearchResult(
                title="天津逸步科技申请计算机网络信息安全监护系统专利",
                url="https://example.com/wrong-city-yibu",
                snippet="天津逸步科技有限公司申请计算机网络信息安全监护系统专利。",
            )
        ],
        judge_source=judge,
        fetch_page=lambda _url: "",
    )

    assert result.accepted_sources == []
    assert result.rejected_results[0].reason == "identity_evidence_missing"


def test_generic_workflow_accepts_trusted_short_brand_without_legal_entity() -> None:
    def judge(**_kwargs):
        return SourceJudgment(
            status="accepted",
            reason="company_identity_and_fact_attribution_confirmed",
            evidence_span="孵化的企业中农美蔬第一轮融资700万元",
            snippet_sufficiency="sufficient",
            confirms_identity=True,
            confirms_fact_attribution=True,
            should_fetch=False,
        )

    result = run_generic_source_workflow(
        company_name="中农美蔬（深圳）科技有限公司",
        search_results=[
            GenericSearchResult(
                title="深圳农业基因组所助力广东农业“美味”新品种",
                url="https://example.com/zhongnongmeishu",
                snippet="孵化的企业中农美蔬第一轮融资700万元。",
            )
        ],
        judge_source=judge,
        fetch_page=lambda _url: "",
    )

    assert [source.url for source in result.accepted_sources] == [
        "https://example.com/zhongnongmeishu"
    ]
    assert result.rejected_results == []


def test_generic_workflow_excludes_recruiting_pages_before_llm_judgment() -> None:
    judge_calls = 0

    def judge(**_kwargs):
        nonlocal judge_calls
        judge_calls += 1
        raise AssertionError("recruiting page should be rejected before LLM")

    result = run_generic_source_workflow(
        company_name="深圳旭宏医疗科技有限公司",
        search_results=[
            GenericSearchResult(
                title="深圳旭宏医疗科技有限公司招聘算法工程师",
                url="https://jobs.example.com/xuhong",
                snippet="招聘岗位职责与薪资。",
            )
        ],
        judge_source=judge,
        fetch_page=lambda _url: "",
    )

    assert result.accepted_sources == []
    assert result.rejected_results[0].reason == "job_intent_excluded"
    assert judge_calls == 0
