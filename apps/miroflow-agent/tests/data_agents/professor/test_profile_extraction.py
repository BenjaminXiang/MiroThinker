from pathlib import Path

from src.data_agents.professor.profile import extract_professor_profile

_SYSU_FIXTURE_DIR = Path(__file__).with_name("fixtures") / "sysu"


def _load_sysu_fixture(name: str) -> str:
    return (_SYSU_FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_extract_professor_profile_from_sustech_message_layout():
    html = """
    <html>
      <head><title>杨阳 - 师资概况 - 南方科技大学</title></head>
      <body>
        <div class="message-left">
          <span class="font fl">杨阳</span>
          <span class="font fl">助理教授</span>
          <span class="font fl">yangyang3@sustech.edu.cn</span>
        </div>
        <div class="message-right fr">
          <p><strong>个人简介：</strong></p>
          <p>杨阳博士，南方科技大学医学院助理教授，博士生导师。</p>
          <p><strong>研究领域：</strong></p>
          <p>心肌细胞横管（T-tubules）作为一种特殊的质膜内陷结构</p>
          <p><strong>教育背景：</strong></p>
          <p>2012-2018 新加坡国立大学 力学生物学研究所 博士</p>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sustech.edu.cn/zh/faculties/yangyang-2.html",
        institution="南方科技大学",
        department=None,
    )

    assert profile.name == "杨阳"
    assert profile.department == "医学院"
    assert profile.title == "助理教授"
    assert profile.email == "yangyang3@sustech.edu.cn"
    assert profile.research_directions == (
        "心肌细胞横管（T-tubules）作为一种特殊的质膜内陷结构",
    )
    assert profile.profile_raw_text is not None
    assert "个人简介" in profile.profile_raw_text
    assert "教育背景" in profile.profile_raw_text


def test_extract_professor_profile_from_szu_cpoe_detail_body():
    html = """
    <html>
      <body>
        <nav><a href="xyzj/jbjs.htm">校友之家</a></nav>
        <div class="teac-det">
          <span class="name">白志勇</span>
          <span class="zw">副教授</span>
          <ul>
            <li>baizhiyong@szu.edu.cn</li>
          </ul>
          <div class="v_news_content">
            <h2>研究方向</h2>
            <p>光纤微结构器件、光纤涡旋光场调控技术、高分辨率光纤传感技术。</p>
            <p>近五年部分论文如下：</p>
            <p>Zhiyong Bai, Ultrafast laser fabrication of fiber devices, Optics Express, 2024.</p>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url=(
            "https://cpoe.szu.edu.cn/szxq.jsp?urltype=tp.TpTeacherDetail"
            "&wbtreeid=1111&id=1779754310756143105&dm=baizhiyong_1en&language="
        ),
        institution="深圳大学",
        department="物理与光电工程学院",
    )

    assert profile.name == "白志勇"
    assert profile.title == "副教授"
    assert profile.email == "baizhiyong@szu.edu.cn"
    assert profile.profile_raw_text is not None
    assert "近五年部分论文如下" in profile.profile_raw_text
    assert "校友之家" not in profile.profile_raw_text


def test_extract_professor_profile_rejects_breadcrumb_heading_as_name():
    html = """
    <html>
      <body>
        <h2>面包屑</h2>
        <main>
          <p>赵展展（双聘：人文社科学院&amp;人工智能学院） 助理教授</p>
          <p>邮箱 zhanzhanzhao@cuhk.edu.cn</p>
          <p>研究领域 算法治理、算法公平、人工智能赋能社会</p>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sai.cuhk.edu.cn/teacher/154",
        institution="香港中文大学（深圳）",
        department="人工智能学院",
    )

    assert profile.name == "赵展展"
    assert profile.title == "助理教授"
    assert profile.email == "zhanzhanzhao@cuhk.edu.cn"
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("赵展展")
    assert "算法治理" in profile.profile_raw_text
    assert "面包屑" not in profile.profile_raw_text


def test_extract_professor_profile_uses_body_name_when_page_title_is_breadcrumb():
    html = """
    <html>
      <head><title>面包屑 - 香港中文大学（深圳）</title></head>
      <body>
        <main>
          <h1>面包屑</h1>
          <p>赵展展 助理教授</p>
          <p>邮箱 zhanzhanzhao@cuhk.edu.cn</p>
          <p>研究方向：算法治理、算法公平</p>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sai.cuhk.edu.cn/teacher/154",
        institution="香港中文大学（深圳）",
        department="人工智能学院",
    )

    assert profile.name == "赵展展"
    assert profile.title == "助理教授"


def test_extract_professor_profile_uses_body_name_when_page_title_is_navigation():
    html = """
    <html>
      <head><title>友情链接 - 中山大学理学院</title></head>
      <body>
        <main>
          <h2>友情链接</h2>
          <p>Loïc MARSOT 助理教授 电子邮箱：marsot3@mail.sysu.edu.cn</p>
          <p>研究领域：mathematical and fundamental physics</p>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://science.sysu.edu.cn/teacher/Lo%C3%AFc%20MARSOT",
        institution="中山大学（深圳）",
        department="理学院",
    )

    assert profile.name == "Loïc MARSOT"
    assert profile.email == "marsot3@mail.sysu.edu.cn"


def test_extract_professor_profile_rejects_login_heading_as_name():
    html = """
    <html>
      <head><title>登录 - CUHK(SZ)</title></head>
      <body>
        <main>
          <h1>登录</h1>
          <form action="/cas/login">
            <input name="username" />
            <input name="password" type="password" />
          </form>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://myweb.cuhk.edu.cn/jwhuang/",
        institution="香港中文大学（深圳）",
        department="理工学院",
    )

    assert profile.name is None
    assert profile.profile_raw_text is None


def test_extract_professor_profile_scopes_sztu_design_fragment_profile():
    html = """
    <html>
      <body>
        <nav>首页 学院概况 科学研究 党的建设</nav>
        <div class="team-part active">
          <div class="team-item">
            <h3 class="team-item__name">杜鹤民</h3>
            <div class="team-item__title">副教授</div>
            <p>电子邮箱：duhemin@sztu.edu.cn</p>
            <p>研究方向：服务设计、交互设计、可持续设计</p>
          </div>
          <div class="team-item">
            <h3 class="team-item__name">李立全</h3>
            <div class="team-item__title">教授</div>
            <p>研究方向：工业设计</p>
          </div>
        </div>
        <footer>书记｜院长信箱 网站地图</footer>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%9C%E9%B9%A4%E6%B0%91",
        institution="深圳技术大学",
        department="创意设计学院",
    )

    assert profile.name == "杜鹤民"
    assert profile.title == "副教授"
    assert profile.email == "duhemin@sztu.edu.cn"
    assert profile.research_directions == ("服务设计", "交互设计", "可持续设计")
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("杜鹤民")
    assert "李立全" not in profile.profile_raw_text
    assert "学院概况" not in profile.profile_raw_text


def test_extract_professor_profile_scopes_sztu_design_fragment_fields_to_matching_card():
    html = """
    <html>
      <body>
        <nav>首页 学院概况 科学研究 党的建设</nav>
        <div class="team-part active">
          <div class="team-item">
            <h3 class="team-item__name">杜鹤民</h3>
            <div class="team-item__title">副教授</div>
            <p>电子邮箱：duhemin@sztu.edu.cn</p>
            <p>研究方向：服务设计、交互设计、可持续设计</p>
          </div>
          <div class="team-item">
            <h3 class="team-item__name">李立全</h3>
            <div class="team-item__title">教授</div>
            <p>电子邮箱：liliquan@sztu.edu.cn</p>
            <p>研究方向：工业设计、产品创新</p>
          </div>
        </div>
        <footer>书记｜院长信箱 网站地图</footer>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%8E%E7%AB%8B%E5%85%A8",
        institution="深圳技术大学",
        department="创意设计学院",
    )

    assert profile.name == "李立全"
    assert profile.title == "教授"
    assert profile.email == "liliquan@sztu.edu.cn"
    assert profile.research_directions == ("工业设计", "产品创新")
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("李立全")
    assert "杜鹤民" not in profile.profile_raw_text
    assert "学院概况" not in profile.profile_raw_text


def test_extract_professor_profile_extracts_sztu_table_research_topics():
    html = """
    <html>
      <body>
        <div class="teacher-details">
          <h1 class="name">梁永生</h1>
          <table>
            <tr><th>职称</th><td>教授</td></tr>
            <tr><th>邮箱</th><td>liangys@sztu.edu.cn</td></tr>
            <tr><th>研究方向</th><td>智能机器人、机器视觉、工业人工智能</td></tr>
          </table>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://ai.sztu.edu.cn/info/1332/6055.htm",
        institution="深圳技术大学",
        department="人工智能学院",
    )

    assert profile.name == "梁永生"
    assert profile.title == "教授"
    assert profile.email == "liangys@sztu.edu.cn"
    assert profile.research_directions == ("智能机器人", "机器视觉", "工业人工智能")


def test_extract_professor_profile_from_sztu_icoc_prefers_page_title_over_section_heading():
    html = """
    <html>
      <head><title>宁存政-深圳技术大学集成电路与光电芯片学院</title></head>
      <body>
        <div class="content">
          <div id="vsb_content"><div class="v_news_content">
            <h1>教育及工作经历</h1>
            <p>2022年至今：深圳技术大学讲席教授，集成电路与光电芯片学院院长。</p>
            <h1>研究领域</h1>
            <p>半导体光电子材料、光电子集成、纳米激光器</p>
            <h1>代表性文章</h1>
            <p>Representative paper title, Advanced Materials, 2024.</p>
            <p>电子邮箱：ningcunzheng@sztu.edu.cn</p>
          </div></div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://icoc.sztu.edu.cn/info/1012/1160.htm",
        institution="深圳技术大学",
        department="集成电路与光电芯片学院",
    )

    assert profile.name == "宁存政"
    assert profile.title == "讲席教授"
    assert profile.email == "ningcunzheng@sztu.edu.cn"
    assert profile.research_directions == ("半导体光电子材料", "光电子集成", "纳米激光器")


def test_extract_professor_profile_scopes_sztu_design_fragment_bare_email_to_matching_card():
    html = """
    <html>
      <body>
        <div class="team-part active">
          <div class="team-item">
            <h3 class="team-item__name">杜鹤民</h3>
            <div class="team-item__title">教授</div>
            <p>主要研究方向：产品创新设计、人机工效。</p>
            <p>duhemin@sztu.edu.cn</p>
          </div>
          <div class="team-item">
            <h3 class="team-item__name">李立全</h3>
            <div class="team-item__title">副教授</div>
            <p>主要研究方向为工业设计、产品创新等。</p>
            <p>liliquan@sztu.edu.cn</p>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%8E%E7%AB%8B%E5%85%A8",
        institution="深圳技术大学",
        department="创意设计学院",
    )

    assert profile.name == "李立全"
    assert profile.email == "liliquan@sztu.edu.cn"
    assert profile.research_directions == ("工业设计", "产品创新")
    assert profile.profile_raw_text is not None
    assert "杜鹤民" not in profile.profile_raw_text


def test_extract_professor_profile_keeps_sztu_cep_name_separate_from_role_suffix():
    html = """
    <html>
      <head><title>吴思忠 书记-深圳技术大学工程物理学院</title></head>
      <body>
        <div class="v_news_content">
          <div class="position">当前位置：首页 &gt; 师资队伍 &gt; 吴思忠 书记</div>
          <h1>吴思忠 书记</h1>
          <p>吴思忠，教授，主要从事工程物理研究。</p>
          <p>邮箱：wusizhong@sztu.edu.cn</p>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cep.sztu.edu.cn/info/1053/1049.htm",
        institution="深圳技术大学",
        department="工程物理学院",
    )

    assert profile.name == "吴思忠"
    assert profile.title == "教授"
    assert profile.email == "wusizhong@sztu.edu.cn"


def test_extract_professor_profile_strips_sztu_cep_support_role_suffix_from_name():
    html = """
    <html>
      <body>
        <div class="v_news_content">
          <h1>刘小梅 校企合作专员（副院长）</h1>
          <p>刘小梅，副教授，主要从事智能制造工程研究。</p>
          <p>邮箱：liuxiaomei@sztu.edu.cn</p>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cep.sztu.edu.cn/info/1053/4301.htm",
        institution="深圳技术大学",
        department="工程物理学院",
    )

    assert profile.name == "刘小梅"
    assert profile.title == "副教授"
    assert profile.email == "liuxiaomei@sztu.edu.cn"


def test_extract_professor_profile_scopes_cuhk_myweb_profile_content():
    html = """
    <html>
      <body>
        <div class="content">
          <nav>Home Lab News People Publications</nav>
          <div class="lab-news">Deep Bit Lab Highlighted News Lab Introduction</div>
          <article class="profile">
            <h1>Jianwei Huang</h1>
            <p>Position: Presidential Chair Professor</p>
            <p>Email: jianweihuang@cuhk.edu.cn</p>
            <p>Research Interests: network economics, game theory, AI systems</p>
          </article>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://myweb.cuhk.edu.cn/jwhuang/",
        institution="香港中文大学（深圳）",
        department="理工学院",
    )

    assert profile.name == "Jianwei Huang"
    assert profile.title == "Presidential Chair Professor"
    assert profile.email == "jianweihuang@cuhk.edu.cn"
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("Jianwei Huang")
    assert "network economics" in profile.profile_raw_text
    assert "Deep Bit Lab" not in profile.profile_raw_text
    assert "Highlighted News" not in profile.profile_raw_text


def test_extract_professor_profile_prefers_cuhk_sse_heading_title_over_patent_title():
    html = """
    <html><body>
      <main>
        <h1>陈刚</h1>
        <p>客座副教授 校长青年学者</p>
        <p>教育背景 博士 （美国罗切斯特大学化学系）</p>
        <p>研究领域 生物物理化学、化学生物学、RNA折叠和分子识别</p>
        <p>电子邮件 chengang@cuhk.edu.cn</p>
        <h2>学术著作</h2>
        <p>Patents Filed</p>
        <p>
          1. Singapore Provisional patent: 10201906239R.
          Title: Compositions and Methods For Inhibition of RNA Editing For
          Treatment of Cancer. Inventors: 1) Leilei CHEN; 2) Gang CHEN
        </p>
        <p>
          2. PAT/179/14/15/PCT, Title: Modified Peptide Nucleic Acids And
          Their Use. Inventors: 1) Gitali DEVI; 10) CHEN Gang.
        </p>
      </main>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sse.cuhk.edu.cn/faculty/chengang",
        institution="香港中文大学（深圳）",
        department="理工学院",
    )

    assert profile.name == "陈刚"
    assert profile.title == "客座副教授"
    assert profile.email == "chengang@cuhk.edu.cn"


def test_extract_professor_profile_supports_accented_latin_name_before_title():
    html = """
    <html>
      <body>
        <h2>友情链接</h2>
        <main>
          <p>Loïc MARSOT 助理教授 电子邮箱：marsot3@mail.sysu.edu.cn</p>
          <p>研究领域：mathematical and fundamental physics</p>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://science.sysu.edu.cn/teacher/Lo%C3%AFc%20MARSOT",
        institution="中山大学（深圳）",
        department="理学院",
    )

    assert profile.name == "Loïc MARSOT"
    assert profile.email == "marsot3@mail.sysu.edu.cn"


def test_extract_professor_profile_rejects_generic_sysu_homepage_link():
    html = """
    <html>
      <body>
        <h1>王五</h1>
        <p>个人简介：王五主要从事智能工程研究。</p>
        <a href="https://www.sysu.edu.cn/">主页</a>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://ise.sysu.edu.cn/teacher/123",
        institution="中山大学（深圳）",
        department="智能工程学院",
    )

    assert profile.name == "王五"
    assert profile.homepage_url == "https://ise.sysu.edu.cn/teacher/123"


def test_extract_professor_profile_normalizes_sysu_am_academic_homepage_url_boundaries():
    html = """
    <html>
      <body>
        <main>
          <h1>张浩祺</h1>
          <p>电子邮箱：zhanghq76@mail.sysu.edu.cn</p>
          <p>学术主页：
            <a href="https://www.https://www.researchgate.net/profile/Haoqi-Zhang-2">
              https://www.https://www.researchgate.net/profile/Haoqi-Zhang-2
            </a>（ResearchGate）
          </p>
          <p>
            <a href="https://scholar.google.co.uk/citations?user=3KlzaUAAAAAJ&amp;hl=en&amp;oi=sra">
              https://scholar.google.co.uk/citations?user=3KlzaUAAAAAJ&amp;hl=en&amp;oi=sra
            </a>（Google Scholar）
          </p>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://am.sysu.edu.cn/szdw/fjs/1416305.htm",
        institution="中山大学（深圳）",
        department="先进制造学院",
    )

    assert profile.name == "张浩祺"
    assert profile.homepage_url == (
        "https://www.researchgate.net/profile/Haoqi-Zhang-2"
    )
    assert "ResearchGate" not in profile.homepage_url
    assert "Google Scholar" not in profile.homepage_url
    assert "www.https" not in profile.homepage_url


def test_extract_professor_profile_scopes_sysu_ise_fragment_to_target_card():
    html = """
    <html>
      <body>
        <main class="faculty-list">
          <section id="prof-other" class="professor-card">
            <h2>Other Professor</h2>
            <p>职称：教授</p>
            <p>电子邮箱：other@mail.sysu.edu.cn</p>
            <p>研究方向：工业控制</p>
          </section>
          <section id="prof-target" class="professor-card">
            <h2>Target Professor</h2>
            <p>职称：副教授</p>
            <p>电子邮箱：target@mail.sysu.edu.cn</p>
            <p>研究方向：智能系统、边缘计算</p>
          </section>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="http://ise.sysu.edu.cn/Faculty/Engineer#prof-target",
        institution="中山大学",
        department="智能工程学院",
    )

    assert profile.name == "Target Professor"
    assert profile.email == "target@mail.sysu.edu.cn"
    assert profile.research_directions == ("智能系统", "边缘计算")
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("Target Professor")
    assert "Other Professor" not in profile.profile_raw_text
    assert "other@mail.sysu.edu.cn" not in profile.profile_raw_text


def test_extract_professor_profile_from_uestc_yjsjy_detail_page():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">张小松</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">教授</span></td></tr>
              <tr><td>头衔</td><td><span id="Labeltc">博士生导师</span></td></tr>
              <tr><td>邮箱</td><td><span id="Labelemail">johnsonzxs @ uestc.edu.cn</span></td></tr>
              <tr><td>学术经历</td><td>长期从事计算机系统与智能计算研究。</td></tr>
              <tr><td>个人简介</td><td>张小松教授在电子科技大学（深圳）高等研究院指导研究生。</td></tr>
              <tr><td>科研项目</td><td>主持多项国家和省部级科研项目。</td></tr>
              <tr><td>研究成果</td><td>发表多篇高水平论文。</td></tr>
              <tr><td>专业研究方向</td><td>人工智能与机器学习</td></tr>
              <tr><td>专业研究方向</td><td>云计算与大数据</td></tr>
            </table>
          </div>
        </div>
        <div class="side">学院列表 计算机科学与工程学院 软件学院</div>
        <div class="footer">研招办邮箱：yzb@uestc.edu.cn</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10364?yxsh=28",
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
    )

    assert profile.name == "张小松"
    assert profile.title == "教授"
    assert profile.email == "johnsonzxs@uestc.edu.cn"
    assert profile.research_directions == ("人工智能与机器学习", "云计算与大数据")
    assert profile.profile_raw_text is not None
    assert "学术经历" in profile.profile_raw_text
    assert "个人简介" in profile.profile_raw_text
    assert "科研项目" in profile.profile_raw_text
    assert "研究成果" in profile.profile_raw_text
    assert "专业研究方向" in profile.profile_raw_text
    assert "学院列表" not in profile.profile_raw_text
    assert "yzb@uestc.edu.cn" not in profile.profile_raw_text
    assert profile.homepage_url is None


def test_extract_professor_profile_from_uestc_yjsjy_detail_keeps_personal_homepage():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">黄野</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">教授</span></td></tr>
              <tr><td>我的个人主页</td><td><a href="https://edwardyehuang.com/">https://edwardyehuang.com/</a></td></tr>
              <tr><td>个人简介</td><td>黄野教授在电子科技大学（深圳）高等研究院指导研究生。</td></tr>
              <tr><td>专业研究方向</td><td>网络空间安全</td></tr>
            </table>
          </div>
        </div>
      </body>
    </html>
    """
    source_url = "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/12345?yxsh=28"

    profile = extract_professor_profile(
        html=html,
        source_url=source_url,
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
    )

    assert profile.profile_url == source_url
    assert profile.homepage_url == "https://edwardyehuang.com/"


def test_extract_professor_profile_from_uestc_yjsjy_detail_keeps_secondary_academic_urls():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">黄野</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">教授</span></td></tr>
              <tr><td>Google Scholar</td><td><a href="https://scholar.google.com/citations?user=abc123">Scholar</a></td></tr>
              <tr><td>DBLP</td><td><a href="https://dblp.org/pid/12/3456.html">DBLP profile</a></td></tr>
              <tr><td>教师主页</td><td><a href="https://faculty.uestc.edu.cn/huangye/zh_CN/index.htm">学院教师主页</a></td></tr>
              <tr><td>个人简介</td><td>更多成果见 https://staff.uestc.edu.cn/huangye 。代表性成果 DOI: https://doi.org/10.1145/1234567.7654321</td></tr>
            </table>
          </div>
        </div>
      </body>
    </html>
    """
    source_url = "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/12345?yxsh=28"

    profile = extract_professor_profile(
        html=html,
        source_url=source_url,
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
    )

    assert profile.source_urls == (
        source_url,
        "https://scholar.google.com/citations?user=abc123",
        "https://dblp.org/pid/12/3456.html",
        "https://faculty.uestc.edu.cn/huangye/zh_CN/index.htm",
        "https://staff.uestc.edu.cn/huangye",
        "https://doi.org/10.1145/1234567.7654321",
    )
    assert profile.profile_raw_text is not None
    assert "Google Scholar" in profile.profile_raw_text
    assert "更多成果见 https://staff.uestc.edu.cn/huangye" in profile.profile_raw_text


def test_extract_professor_profile_from_uestc_yjsjy_detail_reads_narrative_research_direction():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">李四</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">教授</span></td></tr>
              <tr><td>个人简介</td><td><span id="Labelgrjj">主要研究方向为智能感知、可信人工智能和具身智能。曾主持多项科研项目。</span></td></tr>
            </table>
          </div>
        </div>
        <div class="footer">研招办 研究方向：招生咨询、报考流程</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/54321?yxsh=28",
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
    )

    assert profile.research_directions == ("智能感知", "可信人工智能", "具身智能")


def test_extract_professor_profile_from_uestc_yjsjy_detail_reconstructs_split_email():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">王明</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">副教授</span></td></tr>
              <tr><td>邮箱</td><td><span id="Labelemail">wangming</span>@ uestc.edu.cn</td></tr>
              <tr><td>个人简介</td><td><span id="Labelgrjj">电子科技大学教师。</span></td></tr>
            </table>
          </div>
        </div>
        <div class="footer">研招办邮箱：yzb@uestc.edu.cn</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10368?yxsh=28",
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
    )

    assert profile.email == "wangming@uestc.edu.cn"


def test_extract_professor_profile_from_uestc_yjsjy_detail_reads_mainly_engaged_topic():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">赵强</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">教授</span></td></tr>
              <tr><td>个人简介</td><td><span id="Labelgrjj">主要从事工业软件与智能制造研究，主持多项科研项目。</span></td></tr>
              <tr><td>科研项目</td><td><span id="lblKyxm">主持国家自然科学基金项目。</span></td></tr>
            </table>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/20492?yxsh=28",
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
    )

    assert profile.research_directions == ("工业软件与智能制造",)


def test_extract_professor_profile_from_uestc_yjsjy_detail_reads_long_term_engaged_topic():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">李轩</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">研究员</span></td></tr>
              <tr><td>个人简介</td><td><span id="Labelgrjj">李轩，电子科技大学，特聘研究员，博导。研究方向：长期从事宽禁带碳化硅基功率器件、封装及应用研究。成果形成了具有里程碑性质的零开关损耗系列成果。</span></td></tr>
            </table>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/20350?yxsh=28",
        institution="电子科技大学（深圳）高等研究院",
        department="电子信息",
    )

    assert profile.research_directions == ("宽禁带碳化硅基功率器件", "封装及应用研究")


def test_extract_professor_profile_from_uestc_yjsjy_detail_reads_spacer_cell_topic():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">李轩</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">研究员</span></td></tr>
              <tr>
                <td>个人简介：</td>
                <td></td>
                <td>李轩，电子科技大学，特聘研究员，博导。研究方向：长期从事宽禁带碳化硅基功率器件、封装及应用研究。</td>
              </tr>
              <tr><td colspan="3">专业研究方向：</td></tr>
            </table>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/20350?yxsh=28",
        institution="电子科技大学（深圳）高等研究院",
        department="电子信息",
    )

    assert profile.research_directions == ("宽禁带碳化硅基功率器件", "封装及应用研究")


def test_extract_professor_profile_from_uestc_yjsjy_blank_detail_email_ignores_footer():
    html = """
    <html>
      <body>
        <div id="mcontent">
          <div class="news_list">
            <table class="box">
              <tr><td>姓名</td><td><span id="Labeldsxm">张小松</span></td></tr>
              <tr><td>职称</td><td><span id="Labelzc">教授</span></td></tr>
              <tr><td>邮箱</td><td><span id="Labelemail"></span></td></tr>
              <tr><td>个人简介</td><td>个人简介内容。</td></tr>
              <tr><td>专业研究方向</td><td>人工智能与机器学习</td></tr>
            </table>
          </div>
        </div>
        <div class="footer">研招办邮箱：yzb@uestc.edu.cn</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10364?yxsh=28",
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
    )

    assert profile.name == "张小松"
    assert profile.email is None


def test_extract_professor_profile_from_generic_text_block():
    html = """
    <html><body>
      <div>王五</div>
      <div>职称：教授 / 邮箱：wangwu_AT_szu.edu.cn / 研究方向：多模态学习、强化学习</div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cs.szu.edu.cn/faculty/wangwu.htm",
        institution="深圳大学",
        department="计算机与软件学院",
    )

    assert profile.title == "教授"
    assert profile.email == "wangwu@szu.edu.cn"
    assert profile.research_directions == ("多模态学习", "强化学习")
    assert profile.profile_url == "https://cs.szu.edu.cn/faculty/wangwu.htm"
    assert profile.source_urls == ("https://cs.szu.edu.cn/faculty/wangwu.htm",)


def test_extract_professor_profile_from_szu_bigdata_detail_page():
    html = """
    <html>
      <head><title>PHILIPPE FOURNIER-VIGER - 深圳大数据技术与应用研究所</title></head>
      <body>
        <div class="nav">首页 科研团队 论文发表 人才培养</div>
        <div class="abm2">
          <div class="teamm1">PHILIPPE FOURNIER-VIGER</div>
          <div class="teamm2">
            <h3>个人简介</h3>
            <div class="teamm2_1">
              I got my Ph.D from the U. of Quebec in Montreal (2010).
              Research interests：Data Mining, Big Data, Artificial Intelligence,
              Pattern Mining, Itemset Mining, Graph Mining, Sequence Prediction.
            </div>
            <h3 class="teamh3">研究方向</h3>
            <div class="teamm2_2">
              Data Mining, Big Data, Artificial Intelligence, Pattern Mining
            </div>
          </div>
        </div>
        <div class="related">黄哲学 发表学术论文250多篇。</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://bigdata.szu.edu.cn/info/1008/1183.htm",
        institution="深圳大学",
        department="计算机与软件学院",
    )

    assert profile.name == "PHILIPPE FOURNIER-VIGER"
    assert profile.title == "教授"
    assert profile.research_directions[:3] == (
        "Data Mining",
        "Big Data",
        "Artificial Intelligence",
    )
    assert profile.profile_raw_text is not None
    assert "I got my Ph.D" in profile.profile_raw_text
    assert "黄哲学" not in profile.profile_raw_text


def test_extract_professor_profile_from_szu_bigdata_detail_keeps_cjk_name_with_subject_word():
    html = """
    <html>
      <head><title>黄哲学 - 深圳大数据技术与应用研究所</title></head>
      <body>
        <div class="abm2">
          <div class="teamm1"><p class="mingzi">黄哲学</p></div>
          <div class="teamm2">
            <h3>个人简介</h3>
            <div class="teamm2_1">
              瑞典皇家理工学院博士，深圳大学特聘教授，发表学术论文250多篇。
            </div>
            <h3 class="teamh3">研究方向</h3>
            <div class="teamm2_2">
              大数据近似计算
              大数据多样本分析理论与方法
              RSP大数据分析平台软件
            </div>
            <h3 class="teamh3">其他</h3>
            <div class="teamm2_2">国际学术兼职。</div>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://bigdata.szu.edu.cn/info/1008/1185.htm",
        institution="深圳大学",
        department="计算机与软件学院",
    )

    assert profile.name == "黄哲学"
    assert profile.title == "教授"
    assert profile.research_directions == (
        "大数据近似计算",
        "大数据多样本分析理论与方法",
        "RSP大数据分析平台软件",
    )


def test_extract_professor_profile_bounds_szu_math_title_before_phone_label():
    html = """
    <html><body>
      <div class="teacherDetail">
        <h1>陈波</h1>
        <p>职称：副教授 电话：26534582</p>
        <p>邮箱：chenbo@szu.edu.cn</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://math.szu.edu.cn/info/1103/chenbo.htm",
        institution="深圳大学",
        department="数学科学学院",
    )

    assert profile.title == "副教授"
    assert profile.email == "chenbo@szu.edu.cn"


def test_extract_professor_profile_keeps_szu_math_official_profile_url_without_homepage_link():
    html = """
    <html><body>
      <div class="nav"><a href="https://www.szu.edu.cn/index.htm">深圳大学主页</a></div>
      <div class="teacherDetail">
        <h1>陈波</h1>
        <p>职称：副教授 电话：26534582</p>
        <p>邮箱：chenbo@szu.edu.cn</p>
      </div>
    </body></html>
    """
    source_url = "https://math.szu.edu.cn/info/1103/chenbo.htm"

    profile = extract_professor_profile(
        html=html,
        source_url=source_url,
        institution="深圳大学",
        department="数学科学学院",
    )

    assert profile.profile_url == source_url
    assert profile.homepage_url == source_url


def test_extract_professor_profile_bounds_szu_chemistry_title_and_email():
    html = """
    <html><body>
      <div class="content">
        <h1>周学昌</h1>
        <p>职称：特聘教授 个人课题组：https://chem.szu.edu.cn/zhou</p>
        <p>电子邮箱：zhouxc@szu.edu.cn https://chem.szu.edu.cn/zhou</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://chem.szu.edu.cn/info/1047/zhouxc.htm",
        institution="深圳大学",
        department="化学与环境工程学院",
    )

    assert profile.title == "特聘教授"
    assert profile.email == "zhouxc@szu.edu.cn"


def test_extract_professor_profile_strips_szu_homepage_trailing_chinese_prose():
    html = """
    <html><body>
      <div class="content">
        <h1>胡小银</h1>
        <p>职称：教授</p>
        <p>个人主页：https://huxiaoyin708.github.io 主要介绍课题组研究方向和论文成果</p>
        <p>电子邮箱：huxiaoyin@szu.edu.cn</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://chem.szu.edu.cn/info/1047/huxiaoyin.htm",
        institution="深圳大学",
        department="化学与环境工程学院",
    )

    assert profile.homepage_url == "https://huxiaoyin708.github.io"


def test_extract_professor_profile_bounds_szu_cmse_title_before_office_phone():
    html = """
    <html><body>
      <div class="main_cont">
        <h1>刘光良</h1>
        <p>职称：教授 办公电话</p>
        <p>EMAIL：liugl@szu.edu.cn</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/lgli.htm",
        institution="深圳大学",
        department="材料学院",
    )

    assert profile.title == "教授"
    assert profile.email == "liugl@szu.edu.cn"


def test_extract_professor_profile_extracts_szu_cmse_chair_professor_title():
    html = """
    <html><body>
      <div class="main_cont">
        <h1>刁东风</h1>
        <p>讲席教授</p>
        <p>EMAIL：dfdiao@szu.edu.cn</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/dfdiao.htm",
        institution="深圳大学",
        department="材料学院",
    )

    assert profile.title == "讲席教授"
    assert profile.email == "dfdiao@szu.edu.cn"


def test_extract_professor_profile_extracts_szu_swift_labeled_compound_title():
    html = """
    <html><body>
      <dl class="teacherDetail">
        <dt>姓名：</dt><dd>陈海强</dd>
        <dt>职称：</dt><dd>教授、博士生导师</dd>
        <dt>邮箱：</dt><dd>haiqiang.chen@szu.edu.cn</dd>
      </dl>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://swift.szu.edu.cn/info/1032/chenhq.htm",
        institution="深圳大学",
        department="微众银行金融科技学院",
    )

    assert profile.title == "教授、博士生导师"
    assert profile.email == "haiqiang.chen@szu.edu.cn"


def test_extract_professor_profile_raw_text_from_szu_ceie_arc_con():
    html = """
    <html><body>
      <div class="nav">学院概况 师资队伍 招生就业</div>
      <div class="arc-con">
        <h1>王敏</h1>
        <p>职称：副教授</p>
        <p>邮箱：wangmin@szu.edu.cn</p>
        <p>研究方向：电磁场与微波技术、无线通信系统、智能感知。</p>
        <p>个人简介：长期围绕电子信息工程中的电磁建模、射频前端和无线感知开展研究，服务深圳通信产业应用。</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://ceie.szu.edu.cn/info/1011/wangmin.htm",
        institution="深圳大学",
        department="电子与信息工程学院",
    )

    assert profile.profile_raw_text is not None
    assert "无线通信系统" in profile.profile_raw_text
    assert "学院概况" not in profile.profile_raw_text


def test_extract_professor_profile_prefers_szu_bio_profile_body_over_publication_block():
    html = """
    <html><body>
      <div class="v_news_content">
        <h2>代表性论文</h2>
        <p>Publication A. Publication B. Publication C.</p>
      </div>
      <div class="wp_articlecontent">
        <h1>李明</h1>
        <p>职称：教授</p>
        <p>邮箱：liming@szu.edu.cn</p>
        <p>研究方向：细胞生物学、合成生物学、肿瘤免疫。</p>
        <p>个人简介：围绕生命科学前沿问题开展长期研究，建设跨学科实验平台并指导研究生培养。</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://bio.szu.edu.cn/info/1042/liming.htm",
        institution="深圳大学",
        department="生命与海洋科学学院",
    )

    assert profile.profile_raw_text is not None
    assert "细胞生物学" in profile.profile_raw_text
    assert "代表性论文" not in profile.profile_raw_text


def test_extract_professor_profile_uses_szu_cmse_bio_body_not_publication_block():
    html = """
    <html><body>
      <div class="v_news_content">
        <h2>代表性论文</h2>
        <p>Li Y. Publication A. Publication B. Publication C.</p>
      </div>
      <div class="main_cont">
        <h1>李亚运</h1>
        <p>职称：副教授</p>
        <p>电子邮箱：liyy@szu.edu.cn</p>
        <p>研究方向：高分子材料、功能复合材料、能源材料。</p>
        <p>个人简介：围绕材料科学与工程中的功能高分子和复合材料开展研究，建设面向新能源应用的材料制备与表征平台。</p>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/lyy.htm",
        institution="深圳大学",
        department="材料学院",
    )

    assert profile.profile_raw_text is not None
    assert "高分子材料" in profile.profile_raw_text
    assert "个人简介" in profile.profile_raw_text
    assert "代表性论文" not in profile.profile_raw_text


def test_extract_professor_profile_raw_text_from_suat_v_news_content():
    html = """
    <html>
      <head><title>陈晓明-深圳理工大学生命健康学院</title></head>
      <body>
        <div class="top-nav">首页 学院概况 科学研究 人才招聘</div>
        <div class="main_cont">
          <div class="v_news_content">
            <p>姓名：陈晓明</p>
            <p>职称：副教授</p>
            <p>邮箱：xiaoming.chen@suat-sz.edu.cn</p>
            <p>研究方向：生物医学工程、智能传感、精准医学</p>
            <p>个人简介：陈晓明博士长期围绕生物医学工程中的智能感知与临床转化开展研究，关注柔性传感器、微纳制造、生命体征连续监测和多源医学数据融合。</p>
            <p>教育经历：博士毕业于相关交叉学科，接受过材料、电子信息和医学工程训练，具备从器件设计、系统集成到实验验证的完整研究经验。</p>
            <p>科研成果：近年主持和参与多项省部级科研项目，推动智能传感技术在健康监测、康复评估和精准医疗场景中的应用，并与医院及产业团队保持长期合作。</p>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.suat-sz.edu.cn/info/1024/1234.htm",
        institution="深圳理工大学",
        department="生命健康学院",
    )

    assert profile.name == "陈晓明"
    assert profile.title == "副教授"
    assert profile.email == "xiaoming.chen@suat-sz.edu.cn"
    assert profile.research_directions == ("生物医学工程", "智能传感", "精准医学")
    assert profile.profile_raw_text is not None
    assert len(profile.profile_raw_text) >= 200
    assert "个人简介" in profile.profile_raw_text
    assert "科研成果" in profile.profile_raw_text


def test_extract_professor_profile_raw_text_from_sztu_content_detail_block():
    html = """
    <html>
      <head><title>刘洋-深圳技术大学大数据与互联网学院</title></head>
      <body>
        <div class="header">深圳技术大学 教师队伍 通知公告</div>
        <div class="content">
          <div class="detail">
            <h1>刘洋</h1>
            <p>职称：教授</p>
            <p>电子邮箱：liuyang@sztu.edu.cn</p>
            <p>研究方向：机器视觉、智能机器人、工业互联网；</p>
            <p>个人简介：刘洋教授主要从事机器视觉、智能机器人和工业互联网方向研究，面向高端装备制造、智能检测和复杂生产系统优化等应用场景开展算法与系统研发。</p>
            <p>工作经历：曾在高校和科研机构承担多项科研任务，具有跨学科团队管理、工程样机开发和产学研协同经验，持续服务深圳先进制造产业需求。</p>
            <p>代表成果：发表多篇学术论文，参与制定智能制造相关技术方案，推动视觉感知、边缘计算和机器人控制技术在真实生产线中的落地验证。</p>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://bigdata.sztu.edu.cn/info/1074/2451.htm",
        institution="深圳技术大学",
        department="大数据与互联网学院",
    )

    assert profile.name == "刘洋"
    assert profile.title == "教授"
    assert profile.email == "liuyang@sztu.edu.cn"
    assert profile.research_directions == ("机器视觉", "智能机器人", "工业互联网")
    assert profile.profile_raw_text is not None
    assert len(profile.profile_raw_text) >= 200
    assert "个人简介" in profile.profile_raw_text
    assert "代表成果" in profile.profile_raw_text


def test_extract_professor_profile_from_sgim_sztu_standalone_role_node():
    html = """
    <html>
      <head><title>王红志-中德智能制造学院</title></head>
      <body>
        <div class="content">
          <div class="title">王红志</div>
          <div class="content-body" id="vsb_content">
            <div class="v_news_content">
              <p class="ldxm">王红志</p>
              <p class="ldzw">教授.</p>
              <div class="ldjs">
                <p><strong>研究方向：</strong>机电装备开发</p>
                <p><strong>教育及工作经历：</strong></p>
                <p>2017年就职于深圳技术大学，中德智能制造学院，担任教授、副院长。</p>
                <p><strong>电子邮箱：</strong>wanghongzhi@sztu.edu.cn</p>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sgim.sztu.edu.cn/info/1273/4113.htm",
        institution="深圳技术大学",
        department="中德智能制造学院",
    )

    assert profile.name == "王红志"
    assert profile.title == "教授"
    assert profile.email == "wanghongzhi@sztu.edu.cn"
    assert profile.research_directions == ("机电装备开发",)
    assert profile.profile_raw_text is not None
    assert "机电装备开发" in profile.profile_raw_text


def test_extract_professor_profile_from_sgim_sztu_keeps_title_name_over_leader_role():
    html = """
    <html>
      <head><title>杨灿-中德智能制造学院</title></head>
      <body>
        <div class="content">
          <div class="title">杨灿</div>
          <div class="content-body" id="vsb_content">
            <div class="v_news_content">
              <p class="ldxm">副院长（外事专员）</p>
              <p class="ldxm">副教授，硕士生导师</p>
              <p>分管工作：分管国际交流合作、研究生工作。</p>
              <p><strong>研究方向：</strong>增材制造；精密/微纳加工；轻量化材料与构件</p>
              <p><strong>电子邮箱：</strong>yangcan@sztu.edu.cn</p>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sgim.sztu.edu.cn/info/1273/4133.htm",
        institution="深圳技术大学",
        department="中德智能制造学院",
    )

    assert profile.name == "杨灿"
    assert profile.title == "副教授"
    assert profile.email == "yangcan@sztu.edu.cn"
    assert profile.profile_raw_text is not None
    assert "轻量化材料与构件" in profile.profile_raw_text


def test_extract_professor_profile_from_cep_sztu_name_title_header():
    html = """
    <html>
      <head><title>姚建铨-深圳技术大学工程物理学院</title></head>
      <body>
        <div class="content">
          <div id="vsb_content"><div class="v_news_content">
            <div class="szdw_txt">
              <p class="title">姚建铨&nbsp;&nbsp; 特聘教授/博导</p>
              <p class="gzdw">工作单位：工程物理学院</p>
              <p class="mailbox">邮箱：</p>
            </div>
            <div class="szdw_bd">
              <div class="jssx"><strong>个人简介</strong></div>
              <p>姚建铨激光与光电子科学家，现任深圳技术大学工程物理学院特聘教授。</p>
              <p>目前正在开展太赫兹调控技术、超材料及超表面光电子学及智慧海洋等领域的研究。</p>
            </div>
          </div></div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cep.sztu.edu.cn/info/1052/2201.htm",
        institution="深圳技术大学",
        department="工程物理学院",
    )

    assert profile.name == "姚建铨"
    assert profile.title == "特聘教授/博导"
    assert profile.profile_raw_text is not None
    assert "太赫兹调控技术" in profile.profile_raw_text


def test_extract_professor_profile_from_cep_sztu_body_title_without_title_header():
    html = """
    <html>
      <head><title>万亮亮-深圳技术大学工程物理学院</title></head>
      <body>
        <div class="content">
          <div id="vsb_content"><div class="v_news_content">
            <p>万亮亮，博士，深圳技术大学工程物理学院教授。</p>
            <p>主要从事腔光力学、拓扑分类、非厄米物理等方向的研究。</p>
          </div></div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cep.sztu.edu.cn/info/1055/2739.htm",
        institution="深圳技术大学",
        department="工程物理学院",
    )

    assert profile.name == "万亮亮"
    assert profile.title == "教授"
    assert profile.profile_raw_text is not None
    assert "腔光力学" in profile.profile_raw_text


def test_extract_professor_profile_ignores_sztu_school_root_homepage_link():
    source_url = "https://cep.sztu.edu.cn/info/1055/2739.htm"
    html = """
    <html>
      <head><title>万亮亮-深圳技术大学工程物理学院</title></head>
      <body>
        <a href="https://www.sztu.edu.cn/">学校主页</a>
        <div id="vsb_content"><div class="v_news_content">
          <p>万亮亮，博士，深圳技术大学工程物理学院教授。</p>
          <p>主要从事腔光力学、拓扑分类、非厄米物理等方向的研究。</p>
        </div></div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url=source_url,
        institution="深圳技术大学",
        department="工程物理学院",
    )

    assert profile.homepage_url is None


def test_extract_professor_profile_from_sziit_detail_does_not_mark_profile_as_homepage():
    source_url = "https://zd.suit-sz.edu.cn/info/1013/2674.htm"
    html = """
    <html>
      <head><title>夏林中-中德机器人学院</title></head>
      <body>
        <nav>学院概况 师资队伍 招生就业 联系我们</nav>
        <div class="detailtitle11"><h4>夏林中</h4></div>
        <div class="detailtext11" id="vsb_content">
          <div class="v_news_content">
            <p><strong>夏林中</strong>，男，毕业于华中科技大学，博士，教授。</p>
            <p>本人长期从教于ICT领域，主要教学方向包括通信技术、机器学习、自然语言处理等方面。</p>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url=source_url,
        institution="深圳信息职业技术大学",
        department="中德机器人学院",
    )

    assert profile.name == "夏林中"
    assert profile.title == "教授"
    assert profile.homepage_url is None
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("夏林中")
    assert "学院概况" not in profile.profile_raw_text


def test_extract_professor_profile_from_csce_suat_title_duty_card():
    html = """
    <html>
      <head><title>张立朝-计算机科学与人工智能学院</title></head>
      <body>
        <div class="m-details2">
          <div class="top">
            <h3 class="name">张立朝</h3>
            <div class="info">
              <div class="i-t"><span class="t1">职称职务：</span><div class="t-c">特聘副教授</div></div>
              <div class="i-t"><span class="t1">所在学院：</span><div class="t-c">人工智能研究院</div></div>
              <div class="i-t"><span class="t1">邮箱：</span><div class="t-c">zhanglichao@suat-sz.edu.cn</div></div>
            </div>
          </div>
          <div id="vsb_content">
            <div class="item">
              <h3 class="tit">个人简历</h3>
              <div class="desc">
                <p>研究领域</p>
                <p>研究聚焦机器学习与多模态大模型理论研究及其应用方向。</p>
                <p>个人简介</p>
                <p>张立朝博士长期致力于多模态目标跟踪和视觉内容生成的研究。</p>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://csce.suat-sz.edu.cn/info/1012/1400.htm",
        institution="深圳理工大学",
        department="计算机科学与人工智能学院",
    )

    assert profile.name == "张立朝"
    assert profile.title == "特聘副教授"
    assert profile.email == "zhanglichao@suat-sz.edu.cn"
    assert profile.profile_raw_text is not None
    assert "多模态目标跟踪" in profile.profile_raw_text


def test_extract_professor_profile_from_cme_suat_numbered_research_section():
    html = """
    <html>
      <head><title>李慧敏-算力微电子学院</title></head>
      <body>
        <nav>学校主页 首页 学院概况 师资队伍 导师介绍</nav>
        <div class="v_news_content">
          <h1>李慧敏</h1>
          <p>李慧敏 教研助理教授</p>
          <p>简介 中文简介 （ Chinese Biography ） 李慧敏，算力微电子学院教研助理教授、博士生导师。</p>
          <p>简历投递与联系邮箱： lihuimin@suat-sz.edu.cn English Biography Efficient and Secure Computing System Design for the AI Era</p>
          <p>二、研究方向 其研究围绕算法—架构—芯片—系统—智能应用贯通的高效安全计算体系展开，主要包括以下四个方向。</p>
          <p>1. 硬件加速与芯片实现：面向 AI 算法、大模型推理、密码算法和隐私计算算法等高计算复杂度任务。</p>
          <p>2. 软硬件协同设计与计算机体系结构：面向高效计算需求。</p>
          <p>3. 芯片安全与 AI 算力平台安全：面向处理器、SoC、FPGA 和 AI 加速器。</p>
          <p>4. AI/LLM/Agent 安全与可信部署：面向大模型与智能体系统。</p>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cme.suat-sz.edu.cn/info/1012/1463.htm",
        institution="深圳理工大学",
        department="算力微电子学院",
    )

    assert profile.name == "李慧敏"
    assert profile.title == "教研助理教授"
    assert profile.email == "lihuimin@suat-sz.edu.cn"
    assert profile.research_directions == (
        "硬件加速与芯片实现",
        "软硬件协同设计与计算机体系结构",
        "芯片安全与 AI 算力平台安全",
        "AI/LLM/Agent 安全与可信部署",
    )


def test_extract_professor_profile_from_synbio_suat_teacher_details_card():
    html = """
    <html>
      <head><title>张先恩-合成生物学院</title></head>
      <body>
        <div class="teacher-details">
          <div class="info-con">
            <div class="text-con">
              <div class="name">张先恩</div>
              <div class="text">院长、讲席教授</div>
              <div class="des"><p>电子邮件：zhangxianen@suat-sz.edu.cn</p></div>
            </div>
          </div>
          <div class="body">
            <div class="tit">个人简介</div>
            <div class="text"><p>合成生物学与生物技术专家，从事合成生物学、生物传感、纳米生物学和分析微生物学交叉创新研究。</p></div>
            <div class="tit">研究方向</div>
            <div class="text"><p>AI与机器学习的运用、基因编码/合成生物传感器、病毒宿主互作示踪。</p></div>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://synbio.suat-sz.edu.cn/info/1151/2122.htm",
        institution="深圳理工大学",
        department="合成生物学院",
    )

    assert profile.name == "张先恩"
    assert profile.title == "讲席教授"
    assert profile.email == "zhangxianen@suat-sz.edu.cn"
    assert profile.profile_raw_text is not None
    assert "基因编码/合成生物传感器" in profile.profile_raw_text


def test_extract_professor_profile_prefers_suat_detail_email_over_footer_contact():
    html = """
    <html>
      <body>
        <footer>
          <p>邮箱：synbiofaculty@suat-sz.edu.cn</p>
        </footer>
        <div class="teacher-details">
          <div class="info-con">
            <div class="text-con">
              <div class="name">康 乐</div>
              <div class="text">讲席教授</div>
              <div class="des">
                <p>电子邮件：lkang@ioz.ac.cn;lkang@suat-sz.edu.cn</p>
                <p>个人简介 康乐，中国科学院院士，深圳理工大学合成生物学院讲席教授。</p>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://synbio.suat-sz.edu.cn/info/1151/2121.htm",
        institution="深圳理工大学",
        department="合成生物学院",
    )

    assert profile.name == "康 乐"
    assert profile.title == "讲席教授"
    assert profile.email == "lkang@ioz.ac.cn"


def test_extract_professor_profile_raw_text_from_sysu_sece_mainright_cont():
    html = """
    <html>
      <head><title>罗锴 - 中山大学电子与通信工程学院</title></head>
      <body>
        <div class="nav">首页 学院概况 师资力量 科学研究 人才引进</div>
        <div class="mainright">
          <div class="loca">首页 » 师资力量 » 专任教师 » 智能感知 » 罗锴 教授</div>
          <div class="cont">
            <h1>罗锴 博士 教授 博士生导师</h1>
            <p>联系邮箱：kluo@mail.sysu.edu.cn</p>
            <p>通讯地址：广东省深圳市光明区公常路66号中山大学深圳校区电子与通信工程学院。</p>
            <p>研究领域：通信感知一体化、星间激光测距与通信、MIMO 系统等。</p>
            <p>教育背景：2006.06，华中科技大学，通信工程，工学学士学位；2013.01，英国帝国理工学院，电子工程，博士学位。</p>
            <p>个人简介：长期从事无线通信、智能感知、空间通信和阵列信号处理方向研究，主持多项国家级和省部级科研项目，围绕空天地一体化网络与通信感知融合开展理论和系统研究。</p>
            <p>科研成果：在通信和信号处理领域发表多篇论文，承担研究生培养、课程教学和国际合作任务，并服务学院相关科研平台建设。</p>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sece.sysu.edu.cn/szll/js/zngz/1413872.htm",
        institution="中山大学（深圳）",
        department="电子与通信工程学院",
    )

    assert profile.email == "kluo@mail.sysu.edu.cn"
    assert profile.profile_raw_text is not None
    assert len(profile.profile_raw_text) >= 200
    assert "通信感知一体化" in profile.profile_raw_text
    assert "科研成果" in profile.profile_raw_text


def test_extract_professor_profile_does_not_treat_sysu_sece_roster_list_as_raw_text():
    html = """
    <html>
      <head><title>专任教师 - 中山大学电子与通信工程学院</title></head>
      <body>
        <div class="mainright">
          <div class="cont">
            <h3>教授</h3>
            <ul class="listteacher">
              <li><a href="1413872.htm">罗锴 教授</a></li>
              <li><a href="1361653.htm">王涛 副教授</a></li>
              <li><a href="1135749.htm">徐世友 教授</a></li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sece.sysu.edu.cn/szll/js/zngz/index.htm",
        institution="中山大学（深圳）",
        department="电子与通信工程学院",
    )

    assert profile.profile_raw_text is None


def test_extract_professor_profile_raw_text_from_sysu_sic_member_body():
    html = """
    <html>
      <head><title>王美琪 - 中山大学集成电路学院</title></head>
      <body>
        <nav class="navbar">首页 学院概况 师资队伍 科学研究 人才招聘</nav>
        <main id="main-content">
          <aside class="sidebar">国家高层次人才 教授 双聘教授 副教授 助理教授</aside>
          <div class="region-content">
            <div class="field-name-body">
              <h3>王美琪</h3>
              <p>一、个人简介</p>
              <p>王美琪（Meiqi Wang），博士、“百人计划”助理教授、硕士生导师。主要研究方向为面向人工智能的集成电路与智能系统设计，侧重软硬协同设计，VLSI优化，存算一体等研究思路。</p>
              <p>二、研究领域</p>
              <p>本人的主要研究领域为面向多样化人工智能应用需求的集成电路和智能系统设计，推动AI算法在自动驾驶，机器人，AI内容生成和数字孪生等领域中的落地应用。</p>
              <footer class="footer">联系我们 地址：深圳市光明区公常路66号 邮箱：jcdlxy@mail.sysu.edu.cn 友情链接 COPYRIGHT</footer>
            </div>
          </div>
        </main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sic.sysu.edu.cn/members/t02/1409794.htm",
        institution="中山大学（深圳）",
        department="集成电路学院",
    )

    assert profile.profile_raw_text is not None
    assert "面向人工智能的集成电路与智能系统设计" in profile.profile_raw_text
    assert "数字孪生" in profile.profile_raw_text
    assert "师资队伍" not in profile.profile_raw_text
    assert "jcdlxy@mail.sysu.edu.cn" not in profile.profile_raw_text
    assert "COPYRIGHT" not in profile.profile_raw_text


def test_extract_professor_profile_sysu_sic_col_md_9_raw_text_ignores_footer_email():
    profile = extract_professor_profile(
        html=_load_sysu_fixture("sic_profile_col_md_9.html"),
        source_url="https://sic.sysu.edu.cn/members/t01/1409794.htm",
        institution="中山大学（深圳）",
        department="集成电路学院",
    )

    assert profile.name == "王美琪"
    assert profile.email is None
    assert profile.profile_raw_text is not None
    assert "面向人工智能的集成电路与智能系统设计" in profile.profile_raw_text
    assert "数字孪生系统" in profile.profile_raw_text
    assert "jcdlxy@mail.sysu.edu.cn" not in profile.profile_raw_text
    assert "友情链接" not in profile.profile_raw_text


def test_extract_professor_profile_raw_text_from_sysu_am_vsb_content():
    html = """
    <html>
      <head><title>丁北辰 - 中山大学先进制造学院</title></head>
      <body>
        <div class="header-nav">首页 学院概况 师资队伍 科学研究 人才招聘</div>
        <div class="breadcrumb">首页 &gt; 师资队伍 &gt; 副教授 &gt; 丁北辰</div>
        <div class="teacher-detail">
          <div id="vsb_content_2">
            <h1>丁北辰</h1>
            <p>副教授</p>
            <p>电子邮箱: dingbch@mail.sysu.edu.cn</p>
            <p>基本情况</p>
            <p>丁北辰，中山大学先进制造学院副教授，博士生导师，中山大学“百人计划”引进人才，逸仙学者。</p>
            <p>主要研究方向：电液伺服控制系统、机器人精密驱动及运动控制技术、智能装备设计集成。</p>
            <p>教育背景</p>
            <p>2014.10--2019.07，英国巴斯大学，机械工程，博士。</p>
            <div class="footer">联系地址：深圳市光明区公常路66号 联系邮箱：wangrq55@mail.sysu.edu.cn</div>
          </div>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://am.sysu.edu.cn/szdw/fjs/1416781.htm",
        institution="中山大学（深圳）",
        department="先进制造学院",
    )

    assert profile.profile_raw_text is not None
    assert "电液伺服控制系统" in profile.profile_raw_text
    assert "英国巴斯大学" in profile.profile_raw_text
    assert "学院概况" not in profile.profile_raw_text
    assert "wangrq55@mail.sysu.edu.cn" not in profile.profile_raw_text


def test_extract_professor_profile_sysu_am_col_md_9_normalizes_researchgate_and_email():
    profile = extract_professor_profile(
        html=_load_sysu_fixture("am_profile_col_md_9.html"),
        source_url="https://am.sysu.edu.cn/teacher/DingBeichen",
        institution="中山大学（深圳）",
        department="先进制造学院",
    )

    assert profile.name == "丁北辰"
    assert profile.email == "dingbch@mail.sysu.edu.cn"
    assert profile.homepage_url == "https://www.researchgate.net/profile/Beichen-Ding"
    assert profile.profile_raw_text is not None
    assert "电液伺服控制系统" in profile.profile_raw_text
    assert "wangrq55@mail.sysu.edu.cn" not in profile.profile_raw_text


def test_extract_professor_profile_strips_sysu_am_homepage_trailing_chinese_prose():
    html = """
    <html><body>
      <main>
        <h1>郭川</h1>
        <p>电子邮箱：guoch37@mail.sysu.edu.cn</p>
        <p>学术主页：https://www.researchgate.net/profile/Chuan-Guo-4/research5.通讯地址：广东省深圳市光明区公常路66号中山大学深圳校区</p>
      </main>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://am.sysu.edu.cn/teacher/GuoChuan",
        institution="中山大学（深圳）",
        department="先进制造学院",
    )

    assert profile.homepage_url == "https://www.researchgate.net/profile/Chuan-Guo-4/research"


def test_extract_professor_profile_bounds_cuhk_sds_reader_markdown_title():
    html = """
    Title: BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    URL Source: https://sds.cuhk.edu.cn/teacher/2238
    Published Time: Fri, 03 Apr 2026 16:55:19 GMT
    Markdown Content:
    # BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    搜索 返回主站 English
    ## 面包屑
    * 首页
    ## BRESAR, Miha 助理教授
    教育背景
    博士，统计学，华威大学（2020-2023）
    学术领域
    计算机科学, 机器学习与人工智能
    个人简介
    Miha Brešar博士是香港中文大学（深圳）的助理教授。
    学术著作
    1. Brownian motion with asymptotically normal reflection
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sds.cuhk.edu.cn/teacher/2238",
        institution="香港中文大学（深圳）",
        department="数据科学学院",
    )

    assert profile.title == "助理教授"
    assert profile.title is not None
    assert "URL Source" not in profile.title
    assert "Markdown Content" not in profile.title
    assert "教育背景" not in profile.title


def test_extract_professor_profile_scopes_cuhk_sds_reader_markdown_body_and_contact_fields():
    html = """
    Title: BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    URL Source: https://sds.cuhk.edu.cn/teacher/2238
    Published Time: Fri, 03 Apr 2026 16:55:19 GMT
    Markdown Content:
    # BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    搜索 返回主站 English
    ## 面包屑
    * 首页
    ## BRESAR, Miha 助理教授
    教育背景
    博士，统计学，华威大学（2020-2023）
    学术领域
    计算机科学, 机器学习与人工智能
    个人简介
    Miha Brešar博士是香港中文大学（深圳）的助理教授。
    联系方式
    电子邮箱：mihabresar@cuhk.edu.cn
    个人网站：https://sites.google.com/view/mihabresar
    ## Footer
    版权所有 © 香港中文大学（深圳）数据科学学院
    sds@cuhk.edu.cn
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sds.cuhk.edu.cn/teacher/2238",
        institution="香港中文大学（深圳）",
        department="数据科学学院",
    )

    assert profile.title == "助理教授"
    assert profile.email == "mihabresar@cuhk.edu.cn"
    assert profile.homepage_url == "https://sites.google.com/view/mihabresar"
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("BRESAR, Miha 助理教授")
    assert "Miha Brešar博士是香港中文大学（深圳）的助理教授。" in profile.profile_raw_text
    assert "sds@cuhk.edu.cn" not in profile.profile_raw_text


def test_extract_professor_profile_rejects_reader_metadata_title_without_clean_role():
    html = """
    Title: Teacher Search | 香港中文大学（深圳）理工学院
    URL Source: https://sse.cuhk.edu.cn/teacher-search
    Markdown Content:
    [学院概况](https://sse.cuhk.edu.cn/node/411)
    教育背景 学术科研 人才招聘
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sse.cuhk.edu.cn/teacher-search",
        institution="香港中文大学（深圳）",
        department="理工学院",
    )

    assert profile.title is None


def test_extract_professor_profile_finds_cuhk_sds_title_when_reader_title_label_was_stripped():
    html = """
    BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    URL Source: https://sds.cuhk.edu.cn/teacher/2238
    Markdown Content:
    # BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    搜索 返回主站 English
    ## BRESAR, Miha 助理教授
    教育背景
    博士，统计学，华威大学（2020-2023）
    个人简介
    Miha Brešar博士是香港中文大学（深圳）的助理教授。
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sds.cuhk.edu.cn/teacher/2238",
        institution="香港中文大学（深圳）",
        department="数据科学学院",
    )

    assert profile.title == "助理教授"


def test_extract_professor_profile_ignores_nav_professor_word_before_cuhk_sds_heading():
    html = """
    BRESAR, Miha | 香港中文大学（深圳）数据科学学院 URL Source: https://sds.cuhk.edu.cn/teacher/2238
    Markdown Content:
    # BRESAR, Miha | 香港中文大学（深圳）数据科学学院 搜索 师资力量 教职人员 荣休教授 兼职人员 新闻与公示
    ## 面包屑 * 首页
    ## BRESAR, Miha 助理教授 教育背景 博士，统计学，华威大学（2020-2023） 个人简介 Miha Brešar博士是香港中文大学（深圳）的助理教授。
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sds.cuhk.edu.cn/teacher/2238",
        institution="香港中文大学（深圳）",
        department="数据科学学院",
    )

    assert profile.title == "助理教授"


def test_extract_professor_profile_scopes_cuhk_sds_reader_markdown_when_title_is_next_line():
    html = """
    Title: BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    URL Source: https://sds.cuhk.edu.cn/teacher/2238
    Markdown Content:
    # BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    搜索 返回主站 English
    ## 面包屑
    * 首页
    ## BRESAR, Miha
    助理教授
    教育背景
    博士，统计学，华威大学（2020-2023）
    个人简介
    Miha Brešar博士是香港中文大学（深圳）的助理教授。
    联系方式
    电子邮箱：mihabresar@cuhk.edu.cn
    ## Footer
    版权所有 © 香港中文大学（深圳）数据科学学院
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://sds.cuhk.edu.cn/teacher/2238",
        institution="香港中文大学（深圳）",
        department="数据科学学院",
    )

    assert profile.name == "BRESAR, Miha"
    assert profile.title == "助理教授"
    assert profile.profile_raw_text is not None
    assert profile.profile_raw_text.startswith("BRESAR, Miha 助理教授")
    assert "面包屑" not in profile.profile_raw_text
    assert "版权所有" not in profile.profile_raw_text


def test_extract_professor_profile_keeps_bounded_compound_title_candidate():
    html = """
    <html><body>
      <div>姓名：陈道毅</div>
      <div>职称：教授，博士生导师 / 邮箱：chen.daoyi@example.edu.cn</div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://example.edu.cn/prof/chen",
        institution="示例大学",
        department="示例学院",
    )

    assert profile.title == "教授，博士生导师"


def test_extract_professor_profile_from_sustech_like_labeled_html():
    html = """
    <html><body>
      <h3 class="t-name">白雨卉</h3>
      <p><span>职位</span>讲师 </p>
      <p><span>邮箱</span>baiyh_AT_sustech.edu.cn </p>
      <p><span>办公地点</span>工学院南114室 </p>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cse.sustech.edu.cn/faculty/baiyuhui/",
        institution="南方科技大学",
        department="计算机科学与工程系",
    )

    assert profile.name == "白雨卉"
    assert profile.title == "讲师"
    assert profile.email == "baiyh@sustech.edu.cn"
    assert profile.office == "工学院南114室"
    assert profile.profile_url == "https://cse.sustech.edu.cn/faculty/baiyuhui/"
    assert profile.source_urls == ("https://cse.sustech.edu.cn/faculty/baiyuhui/",)


def test_extract_professor_profile_prefers_visible_heading_and_ignores_script_noise():
    html = """
    <html>
      <head>
        <script>
          var fixedNavTexts = ['首页', '概况'];
          var NameLink = $('.col_path a').filter(function() {
            return !fixedNavTexts.includes($(this).text().trim());
          });
        </script>
      </head>
      <body>
        <div class="banner">
          <h1>李立浧院士</h1>
        </div>
        <div class="content">
          <p>职位：教授</p>
        </div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="http://www.sigs.tsinghua.edu.cn/llyys/main.htm",
        institution="清华大学深圳国际研究生院",
        department="某研究中心",
    )

    assert profile.name == "李立浧"
    assert profile.title == "教授"


def test_extract_professor_profile_prefers_labeled_name_over_generic_heading():
    html = """
    <html><body>
      <h1>师资队伍</h1>
      <div>姓名：张三</div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://example.edu.cn/faculty/zhangsan.html",
        institution="某大学",
        department="某学院",
    )

    assert profile.name == "张三"


def test_extract_professor_profile_ignores_sigs_tab_menu_noise_for_research_directions():
    html = """
    <html><body>
      <div class="banner"><h1>李立浧院士</h1></div>
      <div class="tab-menu">概况 研究领域 研究成果 奖励荣誉</div>
      <p>李立浧院士1967年毕业于清华大学。</p>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="http://www.sigs.tsinghua.edu.cn/llyys/main.htm",
        institution="清华大学深圳国际研究生院",
        department="某研究中心",
    )

    assert profile.name == "李立浧"
    assert profile.research_directions == ()


def test_extract_professor_profile_from_sigs_teacher_layout():
    html = """
    <html><body>
      <div class="col_news_con">
        <div class="teacher_right">
          陈道毅 教授 ， 博士生导师
          电话：0755-26036290
          邮箱：Chen.daoyi@sz.tsinghua.edu.cn
          地址：
          <div class="sudy-tab">
            个人简历 教学 研究领域 研究成果 奖励荣誉
            概况 教育经历 1978.2-1982.1 重庆建筑工程学院给排水工程专业 工学学士
            工作经历 1984.6-1984.12 清华大学水利系 助教
          </div>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="http://www.sigs.tsinghua.edu.cn/cdy/main.htm",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.title == "教授，博士生导师"
    assert profile.email == "chen.daoyi@sz.tsinghua.edu.cn"
    assert profile.profile_raw_text is not None
    assert "个人简历" in profile.profile_raw_text
    assert "教育经历" in profile.profile_raw_text


def test_extract_professor_profile_uses_sigs_top_name_before_tab_section_heading():
    html = """
    <html><body>
      <div class="teacher_right">
        Xiaodong CHEN（陈晓东） 教授 ， 博士生导师
        电话：
        邮箱：xdchen@sz.tsinghua.edu.cn
        地址：1440
        <div class="sudy-tab">
          <ul class="tab-menu"><li><span>个人简历</span></li></ul>
          <ul class="tab-list"><li>
            <div class="post"><h3 class="tit"><span class="title">教育经历</span></h3>
              <div class="con"><p>1988-1992, Zhejiang University, Chemical Engineering, PhD</p></div>
            </div>
          </li></ul>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sigs.tsinghua.edu.cn/Xiaodong%20CHEN%EF%BC%88cxd%EF%BC%89/main.htm",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.name == "Xiaodong CHEN"
    assert profile.title == "教授，博士生导师"
    assert profile.email == "xdchen@sz.tsinghua.edu.cn"


def test_extract_professor_profile_reads_sigs_tab_research_paragraph():
    html = """
    <html><body>
      <div class="teacher_right">
        <h1 class="news_title">Ahmed Elazab</h1>
        <div class="carrer">
          <span class="f5">助理教授</span><span class="dh">，</span><span class="f37">博士生导师</span>
        </div>
        <p class="news_text"><span>邮箱：</span><span class="email">ahmedelazab@sz.tsinghua.edu.cn</span></p>
        <div class="sudy-tab">
          <ul class="tab-menu">
            <li><span>个人简历</span></li>
            <li><span>教学</span></li>
            <li><span>研究领域</span></li>
            <li><span>研究成果</span></li>
            <li><span>奖励荣誉</span></li>
          </ul>
          <ul class="tab-list">
            <li>
              <div class="post"><h3 class="tit"><span class="title">教育经历</span></h3>
                <div class="con"><p>09/2012-01/2017, University of Chinese Academy of Sciences, Pattern Recognition &amp; Intelligent Systems, PhD</p></div>
              </div>
            </li>
            <li></li>
            <li>
              <div class="post"><h3 class="tit"><span class="title">研究领域</span></h3>
                <div class="con"><p>My research focuses on developing trustworthy artificial intelligence for medical image analysis, with a special emphasis on brain disease diagnosis and prognosis. I integrate advanced machine and deep learning techniques with multi-modal neuroimaging data fusion to build robust computer-aided detection and diagnosis systems. A core aspect of my work involves applying pattern recognition and neural informatics to uncover disease-specific biomarkers, while simultaneously prioritizing explainable AI to ensure clinical interpretability and trust.</p></div>
              </div>
            </li>
            <li></li>
            <li></li>
          </ul>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.name == "Ahmed Elazab"
    assert profile.title == "助理教授，博士生导师"
    assert profile.email == "ahmedelazab@sz.tsinghua.edu.cn"
    assert "trustworthy artificial intelligence" in profile.research_directions
    assert "medical image analysis" in profile.research_directions
    assert all("个人简历" not in item for item in profile.research_directions)


def test_extract_professor_profile_prefers_sigs_title_over_publication_title_label():
    html = """
    <html><body>
      <div class="teacher_right">
        Vijay Kumar Pandey 助理教授 ， 博士生导师
        邮箱：vijay.pandey@sz.tsinghua.edu.cn
        <div class="sudy-tab">
          <ul class="tab-menu"><li><span>研究成果</span></li></ul>
          <ul class="tab-list"><li>
            <div class="post"><h3 class="tit"><span class="title">主要专利成果</span></h3>
              <div class="con"><p>Title: Compounds as modulator of JAK-STAT pathway</p></div>
            </div>
          </li></ul>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sigs.tsinghua.edu.cn/Vijay/main.htm",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.title == "助理教授，博士生导师"


def test_extract_professor_profile_sigs_english_research_keeps_atomic_topics():
    html = """
    <html><body>
      <div class="teacher_right">
        付红岩 副教授 ， 博士生导师
        <div class="sudy-tab">
          <ul class="tab-menu"><li><span>研究领域</span></li></ul>
          <ul class="tab-list"><li>
            <div class="post"><h3 class="tit"><span class="title">研究领域</span></h3>
              <div class="con"><p>Integrated Photonics and Their Applications for Communications and Sensing, including Optical Wireless Communications, LiDAR, Silicon Photonics.</p></div>
            </div>
          </li></ul>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sigs.tsinghua.edu.cn/fhy/main.htm",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.research_directions == (
        "Integrated Photonics",
        "Optical Wireless Communications",
        "LiDAR",
        "Silicon Photonics",
    )


def test_extract_professor_profile_sigs_chinese_research_field_variants():
    html = """
    <html><body>
      <div class="teacher_right">
        <h1 class="news_title">许银亮</h1>
        <div class="sudy-tab">
          <ul class="tab-menu"><li><span>研究领域</span></li></ul>
          <ul class="tab-list"><li>
            <div class="post"><h3 class="tit"><span class="title">研究领域</span></h3>
              <div class="con"><p>主要研究领域包括智能电网先进控制，分布式控制与优化算法，低碳能源系统优化等，组织实施和参与了多个网、省、地综合能量管理系统。IEEE 协会高级会员，在国内外重要学术期刊和国际会议上发表论文及报告 130 余篇。</p></div>
            </div>
          </li></ul>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sigs.tsinghua.edu.cn/xyl/main.htm",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.research_directions == (
        "智能电网先进控制",
        "分布式控制与优化算法",
        "低碳能源系统优化",
    )


def test_extract_professor_profile_sigs_chinese_keyword_research_topic():
    html = """
    <html><body>
      <div class="teacher_right">
        <h1 class="news_title">杨云锋</h1>
        <div class="sudy-tab">
          <ul class="tab-menu"><li><span>研究领域</span></li></ul>
          <ul class="tab-list"><li>
            <div class="post"><h3 class="tit"><span class="title">研究领域</span></h3>
              <div class="con"><p>研究的关键词为“功能菌群”。主要致力于协同减污、降碳的功能微生物研究。通过优化宏基因组学、分子生态网络、基因功能鉴定和土壤碳库模型等实验和数据分析工具。</p></div>
            </div>
          </li></ul>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sigs.tsinghua.edu.cn/yyf/main.htm",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.research_directions == ("功能菌群",)


def test_extract_professor_profile_sigs_chinese_research_stops_before_metrics():
    html = """
    <html><body>
      <div class="teacher_right">
        <h1 class="news_title">董宇涵</h1>
        <div class="sudy-tab">
          <ul class="tab-menu"><li><span>研究领域</span></li></ul>
          <ul class="tab-list"><li>
            <div class="post"><h3 class="tit"><span class="title">研究领域</span></h3>
              <div class="con"><p>研究方向包括无线通信与网络、机器学习与优化、智能传感器网络及应用、人工智能与医疗、智能交通车路协同。作为项目（技术）负责人承担国家自然科学基金、国家重点研发计划子课题、省部级项目、企业委托项目 30 余项。累计发表论文 170 余篇，申请专利 60 余项，授权专利 30 余项。</p></div>
            </div>
          </li></ul>
        </div>
      </div>
    </body></html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://www.sigs.tsinghua.edu.cn/dyh/main.htm",
        institution="清华大学深圳国际研究生院",
        department=None,
    )

    assert profile.research_directions == (
        "无线通信与网络",
        "机器学习与优化",
        "智能传感器网络及应用",
        "人工智能与医疗",
        "智能交通车路协同",
    )


def test_extract_professor_profile_prefers_title_person_name_over_generic_nav_heading():
    html = """
    <html>
      <head><title>李亚运-深圳大学材料学院欢迎您</title></head>
      <body>
        <h1>学院概况</h1>
        <div>职称：教授</div>
        <div>EMAIL：kittyli@szu.edu.cn</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://cmse.szu.edu.cn/szdw1/jsml/clkxygcx/fzr/lyy.htm",
        institution="深圳大学",
        department="材料学院",
    )

    assert profile.name == "李亚运"
    assert profile.title == "教授"
    assert profile.email == "kittyli@szu.edu.cn"


def test_extract_professor_profile_ignores_subject_heading_when_title_contains_name():
    html = """
    <html>
      <head><title>牛鹏涛-深圳大学人文学院</title></head>
      <body>
        <h1>汉语言文字学</h1>
        <div>牛鹏涛，现任深圳大学人文学院特聘研究员。</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://wxy.szu.edu.cn/info/1027/1094.htm",
        institution="深圳大学",
        department="人文学院",
    )

    assert profile.name == "牛鹏涛"


def test_extract_professor_profile_extracts_structured_research_directions_from_table_cells():
    html = """
    <html>
      <body>
        <h3 class="t-name">靳玉乐</h3>
        <table>
          <tr>
            <th>研究方向</th>
            <td>课程思政、 高等教育治理</td>
          </tr>
          <tr>
            <th>邮箱</th>
            <td>jinyule_AT_example.edu.cn</td>
          </tr>
        </table>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://example.edu.cn/faculty/jinyule.html",
        institution="深圳大学",
        department="教育学部",
    )

    assert profile.name == "靳玉乐"
    assert profile.research_directions == ("课程思政", "高等教育治理")


def test_extract_professor_profile_rejects_section_heading_as_name_on_detail_page():
    html = """
    <html>
      <head><title>工作履历-中山大学（深圳）材料学院</title></head>
      <body>
        <h1>工作履历</h1>
        <div>中山大学（深圳）材料学院教授，长期从事材料科学研究。</div>
        <div>邮箱：example@sysu.edu.cn</div>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="http://materials.sysu.edu.cn/teacher/162",
        institution="中山大学（深圳）",
        department="材料学院",
    )

    assert profile.name is None


def test_extract_professor_profile_uses_person_name_from_page_title_with_at_separator():
    html = """
    <html>
      <head><title>Jianwei Huang @ CUHK</title></head>
      <body>
        <a href="Files/CV.pdf">CV</a>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://jianwei.cuhk.edu.cn/",
        institution="香港中文大学（深圳）",
        department=None,
    )

    assert profile.name == "Jianwei Huang"


def test_extract_professor_profile_rejects_not_open_placeholder_as_name():
    html = """
    <html>
      <head><title>未开通</title></head>
      <body>
        <h1>未开通</h1>
        <main><p>未开通</p></main>
      </body>
    </html>
    """

    profile = extract_professor_profile(
        html=html,
        source_url="https://faculty.example.edu/not-open",
        institution="哈尔滨工业大学（深圳）",
        department="计算机科学与技术学院",
    )

    assert profile.name is None
