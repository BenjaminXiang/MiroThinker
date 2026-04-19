import pytest

from src.data_agents.professor.name_selection import (
    choose_richer_name,
    is_obvious_non_person_name,
    is_same_person_name_variant,
    normalize_name_key,
    select_canonical_name,
)


@pytest.mark.parametrize(
    "title",
    [
        "首页",
        "师资",
        "师资队伍",
        "南燕新闻",
        "返回主站",
        "最新公告",
        "院长寄语",
        "优质教育",
        "“师说”教授专访",
    ],
)
def test_is_obvious_non_person_name_recognizes_known_navigation_titles(title: str):
    assert is_obvious_non_person_name(title)


def test_is_obvious_non_person_name_does_not_block_legitimate_name_with_news_substring():
    assert not is_obvious_non_person_name("李新闻")


@pytest.mark.parametrize("title", ["Teaching", "工作履历"])
def test_is_obvious_non_person_name_recognizes_direct_profile_nav_titles(title: str):
    assert is_obvious_non_person_name(title)


def test_is_obvious_non_person_name_recognizes_faculty_section_heading():
    assert is_obvious_non_person_name("专任教师")
    assert is_obvious_non_person_name("教师队伍")
    assert is_obvious_non_person_name("教授")


@pytest.mark.parametrize(
    "label",
    [
        "教学平台",
        "机构设置",
        "组织构架",
        "学术机构",
        "科学研究",
        "行业导师",
        "行政教辅",
    ],
)
def test_is_obvious_non_person_name_recognizes_zh_cms_section_labels(label: str):
    """SUSTech/SZTU nav fragments that leaked into v3 enriched output."""
    assert is_obvious_non_person_name(label)


@pytest.mark.parametrize(
    "label",
    [
        "About Us",
        "View More",
        "Home",
        "Contact",
        "Job Openings Admission Alumni",
        "English String",
        "Central Saint Martins",
    ],
)
def test_is_obvious_non_person_name_recognizes_english_nav_titles(label: str):
    assert is_obvious_non_person_name(label)


def test_is_obvious_non_person_name_does_not_block_real_english_name():
    assert not is_obvious_non_person_name("Connie Chang-Hasnain")
    assert not is_obvious_non_person_name("Jianwei Huang")
    assert not is_obvious_non_person_name("Tianshi Qin")


@pytest.mark.parametrize(
    "label",
    [
        "Energy Mater",
        "Academia Europaea",
        "Advanced Science",
        "Science Advances",
        "Optics Express",
        "Neural Networks",
        "Environmental Science",
        "Plasma Physics",
        "Intelligent Transportation Systems",
        "Operations Management",
        "Postgraduate Certificate",
        "Highly Cited Chinese Researchers",
    ],
)
def test_is_obvious_non_person_name_recognizes_journal_or_topic_labels(label: str):
    assert is_obvious_non_person_name(label)


@pytest.mark.parametrize(
    "label",
    [
        "本科生",
        "研究生",
        "团学风采",
        "学生工作",
        "本科教学",
        "行政人员",
        "学术交流",
        "人才计划",
    ],
)
def test_is_obvious_non_person_name_recognizes_student_admin_labels(label: str):
    assert is_obvious_non_person_name(label)


def test_same_person_richer_variant_selection_prefers_more_informative_name():
    assert is_same_person_name_variant("李志", "李志教授")
    assert choose_richer_name("李志教授", "李志") == "李志教授"
    assert select_canonical_name(roster_name="李志", extracted_name="李志教授") == "李志教授"


def test_normalize_name_key_removes_separators_and_spaces():
    assert normalize_name_key(" 李·志 教授 ") == "李志教授"


def test_select_canonical_name_falls_back_to_roster_name_when_extracted_is_nav_noise():
    assert select_canonical_name(roster_name="靳玉乐", extracted_name="导航") == "靳玉乐"
    assert select_canonical_name(roster_name="陈向兵", extracted_name="学部概况") == "陈向兵"
    assert select_canonical_name(roster_name="Huthanance", extracted_name="概况") == "Huthanance"


def test_select_canonical_name_normalizes_bom_prefixed_names():
    assert select_canonical_name(roster_name="\ufeff陈冠亨", extracted_name=None) == "陈冠亨"


def test_select_canonical_name_prefers_roster_when_extracted_name_is_profile_blob():
    extracted_name = (
        "Connie Chang-Hasnain Title X.Q. Deng Presidential Chair Professor "
        "Education Background Ph.D. (U.C. Berkeley) Research Micro/Nano "
        "electro mechanical systems Biography Connie Chang-Hasnain is the "
        "professor at the School of Science and Engineering Publications"
    )

    assert select_canonical_name(roster_name="常瑞华", extracted_name=extracted_name) == "常瑞华"


# Round 7.18 — patterns observed in miroflow_real that slipped past earlier guard.


@pytest.mark.parametrize(
    "label",
    [
        "师资力量",
        "综合新闻",
        "教师简介",
        "新闻动态",
        "最新动态",
        "学术动态",
        "招生简章",
        "学院动态",
    ],
)
def test_is_obvious_non_person_name_recognizes_additional_page_headings(label: str):
    """Page-section headings scrapers mistake for professor names."""
    assert is_obvious_non_person_name(label)


@pytest.mark.parametrize(
    "name",
    [
        "陈怀海 性别： 男",
        "倪江群职称：教授",
        "张某职务：院长",
        "李某 学位：博士",
        "王某 E-mail：foo@bar.edu",
        "赵某 邮箱：a@b.com",
    ],
)
def test_is_obvious_non_person_name_rejects_field_label_pollution(name: str):
    """Names with stuck-on Chinese field labels (e.g. 'Name 性别：男')."""
    assert is_obvious_non_person_name(name)


def test_is_obvious_non_person_name_rejects_long_mid_dot_suffix():
    """'Name·MCI The Entrepreneurial ...' — multi-field stuck by · separator."""
    assert is_obvious_non_person_name(
        "Prof. Dr. Anita Zehrer·MCI The Entrepreneurial ..."
    )


def test_is_obvious_non_person_name_keeps_legitimate_western_lastname_first():
    """Nobel-laureate style 'LASTNAME, Firstname' must pass (citation export format)."""
    assert not is_obvious_non_person_name("WARSHEL, Arieh")
    assert not is_obvious_non_person_name("KOBILKA, Brian")
    assert not is_obvious_non_person_name("BRESAR, Miha")


def test_is_obvious_non_person_name_keeps_short_middot_personal_names():
    """Short · names (Uyghur/Tibetan personal names) must not be rejected."""
    assert not is_obvious_non_person_name("吾买尔·阿卜杜拉")
    assert not is_obvious_non_person_name("次仁·卓玛")
