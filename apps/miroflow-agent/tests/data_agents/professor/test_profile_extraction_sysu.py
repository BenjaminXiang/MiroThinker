import pytest

from src.data_agents.professor.profile import extract_professor_profile


@pytest.mark.parametrize(
    ("case_name", "source_url", "html", "expected_name", "expected_topics"),
    [
        (
            "sece_narrative",
            "https://sece.sysu.edu.cn/szll/js/zngz/1401951.htm",
            """
            <html><body>
              <article class="teacher-detail">
                <h1>李明</h1>
                <p>职称：教授</p>
                <section>
                  <h2>个人简介</h2>
                  <p>主要从事水污染控制、环境微生物、智慧水务研究。</p>
                </section>
              </article>
            </body></html>
            """,
            "李明",
            ("水污染控制", "环境微生物", "智慧水务"),
        ),
        (
            "scst_narrative_after_research_label",
            "https://scst.sysu.edu.cn/teacher/DaiXianhua",
            """
            <html><body>
              <main class="teacher-profile">
                <h1>戴显华</h1>
                <p>研究方向</p>
                <p>主要从事人工智能、数据挖掘、生物信息学研究。</p>
              </main>
            </body></html>
            """,
            "戴显华",
            ("人工智能", "数据挖掘", "生物信息学"),
        ),
        (
            "science_semicolon_research_field",
            "https://science.sysu.edu.cn/teacher/536",
            """
            <html><body>
              <main>
                <h1>Loic Marsot</h1>
                <p>Research Areas: mathematical physics; geometric analysis; quantum field theory.</p>
                <p>Email: marsot3@mail.sysu.edu.cn</p>
              </main>
            </body></html>
            """,
            "Loic Marsot",
            ("mathematical physics", "geometric analysis", "quantum field theory"),
        ),
        (
            "sofe_drupal_field",
            "http://sofe.sysu.edu.cn/zh-hans/teacher/81",
            """
            <html><body>
              <div class="region-content">
                <h1>Wang Rui</h1>
                <div class="field-name-field-research-area">
                  <div class="field-label">Research Areas</div>
                  <div class="field-items">
                    <div class="field-item">financial econometrics; asset pricing; risk management</div>
                  </div>
                </div>
              </div>
            </body></html>
            """,
            "Wang Rui",
            ("financial econometrics", "asset pricing", "risk management"),
        ),
        (
            "ise_fragment_card",
            "http://ise.sysu.edu.cn/Faculty/Engineer#prof-target",
            """
            <html><body>
              <main class="faculty-list">
                <section id="prof-other" class="professor-card">
                  <h2>Other Professor</h2>
                  <p>研究方向：工业控制</p>
                </section>
                <section id="prof-target" class="professor-card">
                  <h2>陈俊洲</h2>
                  <p>职称：副教授</p>
                  <p>主要从事智能感知、无人系统、机器人控制研究。</p>
                </section>
              </main>
            </body></html>
            """,
            "陈俊洲",
            ("智能感知", "无人系统", "机器人控制"),
        ),
        (
            "sece_narrative_drops_etc_domain_tail",
            "https://sece.sysu.edu.cn/szll/js/zngz/1398017.htm",
            """
            <html><body>
              <article>
                <h1>张月</h1>
                <p>长期围绕宽带数字化技术、软件化多功能雷达技术，开展
                新体制雷达系统设计、高速高精度大带宽数字化、雷达信号处理、
                智能目标识别等方面研究工作，理论功底深厚、工程实践经验丰富。</p>
              </article>
            </body></html>
            """,
            "张月",
            (
                "宽带数字化技术",
                "软件化多功能雷达技术",
                "新体制雷达系统设计",
                "高速高精度大带宽数字化",
                "雷达信号处理",
                "智能目标识别",
            ),
        ),
        (
            "scst_english_interest_sentence_stops_before_bio",
            "https://scst.sysu.edu.cn/teacher/CaoXiaochun",
            """
            <html><body>
              <main>
                <h1>Cao Xiaochun</h1>
                <p>His research interests include: artificial intelligence
                especially computer vision, machine learning, multimedia analysis,
                and content analysis in cyber space. He is a Fellow of IAPR,
                China.</p>
              </main>
            </body></html>
            """,
            "Cao Xiaochun",
            (
                "artificial intelligence especially computer vision",
                "machine learning",
                "multimedia analysis",
                "content analysis in cyber space",
            ),
        ),
        (
            "scst_specific_include_prefix_is_removed",
            "https://scst.sysu.edu.cn/teacher/YueSheng",
            """
            <html><body>
              <main>
                <h1>岳晟</h1>
                <p>当前主要研究方向为决策智能与端智能，具体包括强化学习、
                大模型智能体、端智能体、分布式机器学习等。</p>
              </main>
            </body></html>
            """,
            "岳晟",
            (
                "决策智能与端智能",
                "强化学习",
                "大模型智能体",
                "端智能体",
                "分布式机器学习",
            ),
        ),
        (
            "scst_stops_before_representative_publications",
            "https://scst.sysu.edu.cn/teacher/CaoXiaochun",
            """
            <html><body>
              <main>
                <h1>Cao Xiaochun</h1>
                <p>Research Field 人工智能安全 Representative Publications
                Qianqian Xu, Yunrui Zhao. A survey on robust learning.</p>
              </main>
            </body></html>
            """,
            "Cao Xiaochun",
            ("人工智能安全",),
        ),
        (
            "sofe_stops_before_education_background",
            "http://sofe.sysu.edu.cn/zh-hans/teacher/205",
            """
            <html><body>
              <main>
                <h1>陈高洁</h1>
                <p>主要从事柔性电子智能感知通信一体化、柔性光电感知与通信、
                人工智能赋能柔性电子智能系统研究。教育背景 2002 本科毕业。</p>
              </main>
            </body></html>
            """,
            "陈高洁",
            ("柔性电子智能感知通信一体化", "柔性光电感知与通信", "人工智能赋能柔性电子智能系统"),
        ),
    ],
)
def test_sysu_profile_extracts_research_topics_from_school_fragments(
    case_name: str,
    source_url: str,
    html: str,
    expected_name: str,
    expected_topics: tuple[str, ...],
):
    profile = extract_professor_profile(
        html=html,
        source_url=source_url,
        institution="中山大学（深圳）",
        department=None,
    )

    assert profile.name == expected_name, case_name
    assert profile.research_directions == expected_topics, case_name


@pytest.mark.parametrize(
    ("case_name", "source_url", "html", "expected_title", "expected_topics"),
    [
        (
            "sece_unlabeled_intro_title",
            "https://sece.sysu.edu.cn/szll/js/zngz/1135759.htm",
            """
            <html><body>
              <article>
                <h1>陈曾平</h1>
                <p>中山大学电子与通信工程学院院长，教授，博士生导师，
                信息与通信工程学科学术带头人。主要从事空间态势感知、软件化雷达探测、
                宽带成像识别等领域的基础理论研究和工程应用关键技术攻关等方面的教学、
                科研与人才培养工作，理论功底深厚、工程实践经验丰富。</p>
              </article>
            </body></html>
            """,
            "教授，博士生导师",
            ("空间态势感知", "软件化雷达探测", "宽带成像识别"),
        ),
        (
            "sece_space_separated_title",
            "https://sece.sysu.edu.cn/szll/js/zngz/1413872.htm",
            """
            <html><body>
              <article>
                <h1>罗锴</h1>
                <p>罗锴 博士 教授 博士生导师 联系邮箱：kluo@mail.sysu.edu.cn</p>
                <p>研究领域：通信感知一体化、星间激光测距与通信、MIMO 系统等</p>
              </article>
            </body></html>
            """,
            "教授 博士生导师",
            ("通信感知一体化", "星间激光测距与通信", "MIMO 系统"),
        ),
    ],
)
def test_sysu_profile_extracts_unlabeled_sece_title_and_bounded_topics(
    case_name: str,
    source_url: str,
    html: str,
    expected_title: str,
    expected_topics: tuple[str, ...],
):
    profile = extract_professor_profile(
        html=html,
        source_url=source_url,
        institution="中山大学（深圳）",
        department="电子与通信工程学院",
    )

    assert profile.title == expected_title, case_name
    assert profile.research_directions == expected_topics, case_name
