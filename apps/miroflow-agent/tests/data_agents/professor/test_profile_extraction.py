from src.data_agents.professor.profile import extract_professor_profile


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

    assert profile.name == "李立浧院士"
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

    assert profile.name == "李立浧院士"
    assert profile.research_directions == ()


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
