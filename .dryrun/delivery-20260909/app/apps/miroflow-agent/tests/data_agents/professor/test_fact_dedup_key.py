"""Unit tests for the format-normalizing professor_fact dedup key."""

from __future__ import annotations

from src.data_agents.professor.fact_dedup_key import (
    completeness_score,
    extract_components,
    facts_are_duplicates,
    legacy_literal_key,
    llm_merge_is_safe,
)


class TestCollapseCases:
    """Pairs that MUST be detected as duplicates."""

    def test_pipe_matches_json_same_degree(self):
        assert facts_are_duplicates(
            "education",
            "Tsinghua University | Ph.D. | Computer Science | 2010-2015",
            '{"school": "Tsinghua University", "degree": "Ph.D.", "field": "Computer Science"}',
        )

    def test_json_bilingual_flip_collapses(self):
        assert facts_are_duplicates(
            "education",
            '{"school": "Tsinghua University (清华大学)", "degree": "Ph.D. (博士)"}',
            '{"school": "清华大学 (Tsinghua University)", "degree": "博士 (Ph.D.)"}',
        )

    def test_gloss_prefix_collapses(self):
        assert facts_are_duplicates(
            "education",
            "2012 年，清华大学，建筑学专业，学士",
            "2012 年，清华大学，建筑学专业，学士 (2012, Tsinghua University, Bachelor)",
        )

    def test_degree_synonyms_collapse(self):
        assert facts_are_duplicates(
            "education",
            "Tsinghua University | Doctor of Engineering | Environmental Engineering | 2008-2012",
            "Tsinghua University | Ph.D. in Engineering | Environmental Engineering | 2008-2012",
        )

    def test_degree_level_normalizes_synonyms(self):
        a = extract_components("education", "Tsinghua | Doctor of Engineering | CS")
        b = extract_components("education", "Tsinghua | Ph.D. in Engineering | CS")
        c = extract_components("education", "Tsinghua | 博士 | CS")
        assert a and b and c
        assert a.degree_level == b.degree_level == c.degree_level == "phd"

    def test_year_bearing_pipe_matches_yearless_json(self):
        assert facts_are_duplicates(
            "education",
            "Peking University | Ph.D. | Chemistry | 2016-2020",
            '{"school": "Peking University", "degree": "Ph.D.", "field": "Chemistry"}',
        )

    def test_exact_text_collapses(self):
        assert facts_are_duplicates("award", "Best Paper Award 2023", "Best Paper Award 2023")

    def test_freeform_bilingual_flip_collapses(self):
        assert facts_are_duplicates(
            "award",
            "2013 国家奖学金，河南师范大学 (2013 National Scholarship, Henan Normal University)",
            "2013 National Scholarship, Henan Normal University (2013 国家奖学金，河南师范大学)",
        )

    def test_work_pipe_matches_json(self):
        assert facts_are_duplicates(
            "work_experience",
            "Tsinghua | Postdoc | 2017-2020",
            '{"organization": "Tsinghua", "role": "Postdoc"}',
        )

    def test_pipe_ascii_matches_json_with_cjk_gloss(self):
        # Tsinghua University (pipe, ascii) == Tsinghua University (清华大学) (JSON)
        assert facts_are_duplicates(
            "education",
            "Tsinghua University | Ph.D. | Computer Science | 2010-2015",
            '{"school": "Tsinghua University (清华大学)", "degree": "Ph.D. (博士)", "field": "Computer Science"}',
        )


class TestFalsePositiveGuards:
    """Pairs that MUST stay distinct."""

    def test_distinct_periods_same_school_field(self):
        # Master 2013-2016 vs PhD 2016-2020, same school+field
        assert not facts_are_duplicates(
            "education",
            "Peking University | Master | Chemistry | 2013-2016",
            "Peking University | Ph.D. | Chemistry | 2016-2020",
        )

    def test_distinct_periods_same_degree(self):
        # two postdoc stints at the same org, different periods
        assert not facts_are_duplicates(
            "work_experience",
            "Tsinghua | Research Assistant | 2018-2019",
            "Tsinghua | Research Assistant | 2019-2020",
        )

    def test_distinct_fields_same_school(self):
        assert not facts_are_duplicates(
            "education",
            "Tsinghua University | Bachelor | Economics | 2008-2012",
            "Tsinghua University | Bachelor | Environmental Engineering | 2008-2012",
        )

    def test_distinct_cjk_schools_not_collapsed(self):
        # both CJK-only org strings must NOT collapse just because ascii is empty
        assert not facts_are_duplicates(
            "education",
            "清华大学 | 博士 | 计算机 | 2010-2015",
            "北京大学 | 博士 | 计算机 | 2010-2015",
        )

    def test_distinct_cjk_roles_not_collapsed(self):
        # 教授 vs 副教授 at the same org+period must stay distinct
        assert not facts_are_duplicates(
            "work_experience",
            "清华大学 | 教授 | 2020-present",
            "清华大学 | 副教授 | 2020-present",
        )

    def test_distinct_english_ranks_not_collapsed(self):
        assert not facts_are_duplicates(
            "work_experience",
            "Tsinghua | Assistant Professor | 2020-present",
            "Tsinghua | Associate Professor | 2020-present",
        )

    def test_distinct_roles_same_venue(self):
        assert not facts_are_duplicates(
            "academic_position",
            "2020.2- 至今 Energy Storage Materials 科学执行编辑 ( 影响因子 17.789)",
            "2022.1- 至今 Energy Storage Materials 副编辑 ( 影响因子 17.789)",
        )

    def test_distinct_awards_not_collapsed(self):
        assert not facts_are_duplicates(
            "award",
            "2018 Best Paper Award, ICCV",
            "2019 Outstanding Student Award, ICCV",
        )

    def test_empty_values_not_duplicates(self):
        assert not facts_are_duplicates("education", "", "")
        assert not facts_are_duplicates("education", None, "   ")

    def test_structured_vs_prose_does_not_false_collapse(self):
        # a pipe fact and an unrelated prose fact must not match
        assert not facts_are_duplicates(
            "education",
            "Tsinghua University | Ph.D. | CS | 2010-2015",
            "2010 年于清华大学获得博士学位，研究方向为计算机视觉",
        )


class TestCompleteness:
    def test_pipe_with_years_richer_than_yearless_json(self):
        pipe_score = completeness_score("Tsinghua | Ph.D. | CS | 2010-2015")
        json_score = completeness_score('{"school": "Tsinghua", "degree": "Ph.D.", "field": "CS"}')
        assert pipe_score > json_score

    def test_structured_outranks_prose(self):
        assert completeness_score("Tsinghua | Ph.D. | CS")[0] > completeness_score(
            "Tsinghua University PhD in CS"
        )[0]


class TestComponentsAndFallback:
    def test_extract_returns_none_for_empty(self):
        assert extract_components("education", "") is None
        assert extract_components("education", None, "  ") is None

    def test_legacy_key_casefold(self):
        assert legacy_literal_key("  Hello  World ") == "hello world"

    def test_json_array_not_structured(self):
        # a JSON list is not a fact dict -> freeform
        comp = extract_components("education", '["a", "b"]')
        assert comp is not None
        assert comp.is_structured is False


class TestLlmMergeSafe:
    """Safety filter for LLM-proposed merges — rejects false positives, accepts
    the genuine prose<->structured / bilingual-flip merges the LLM finds."""

    def test_accepts_prose_phd_vs_yearless_pipe(self):
        # pipe omits the degree; prose has PhD; same school+period -> safe
        assert llm_merge_is_safe(
            "education",
            "University of California | Computer Science Division | 2005-2013",
            "PhD in Computer Science, University of California",
        )

    def test_accepts_json_bilingual_flip(self):
        assert llm_merge_is_safe(
            "education",
            '{"school": "Tsinghua University (清华大学)", "degree": "Ph.D."}',
            '{"school": "清华大学 (Tsinghua University)", "degree": "博士"}',
        )

    def test_rejects_phd_vs_master_same_school(self):
        # the classic LLM false positive
        assert not llm_merge_is_safe(
            "education",
            "2002-至今 香港理工大学 电子计算学系 博士",
            "1998-至今 香港理工大学 电子计算学系 硕士",
        )

    def test_rejects_same_degree_different_period(self):
        assert not llm_merge_is_safe(
            "education",
            "2009-至今 Harbin Institute Ph.D.",
            "2017-至今 Harbin Institute Ph.D.",
        )

    def test_rejects_different_schools(self):
        # different school AND different field -> no shared distinctive token
        assert not llm_merge_is_safe(
            "education",
            "Tsinghua University | Ph.D. | Economics | 2010-2015",
            "Peking University | Ph.D. | Physics | 2010-2015",
        )

    def test_empty_value_rejected(self):
        assert not llm_merge_is_safe("education", "", "Tsinghua PhD")

