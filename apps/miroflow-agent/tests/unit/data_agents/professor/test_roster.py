from src.data_agents.professor.roster import extract_roster_entries


def test_extract_roster_entries_supports_cuhk_teacher_search_cards():
    html = """
<html><body>
  <div class="list-content">
    <div class="list-text">
      <div class="list-title">
        <a href="https://myweb.cuhk.edu.cn/cuishuguang" target="_blank">崔曙光</a>
      </div>
      <div class="list-des">校长学勤讲座教授</div>
      <div class="list-area"><span>学术领域: </span>计算机工程，电子工程</div>
    </div>
  </div>
  <div class="list-content">
    <div class="list-text">
      <div class="list-title">
        <a href="https://myweb.cuhk.edu.cn/alicezhang" target="_blank">Alice Zhang</a>
      </div>
      <div class="list-des">助理教授</div>
      <div class="list-area"><span>研究领域: </span>人工智能</div>
    </div>
  </div>
  <div class="list-content">
    <div class="list-text">
      <div class="list-title">
        <a href="" target="_blank">科研团队</a>
      </div>
    </div>
  </div>
</body></html>
"""

    entries = extract_roster_entries(
        html=html,
        institution="香港中文大学（深圳）",
        department="理工学院",
        source_url="https://sse.cuhk.edu.cn/teacher-search",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("崔曙光", "https://myweb.cuhk.edu.cn/cuishuguang"),
        ("Alice Zhang", "https://myweb.cuhk.edu.cn/alicezhang"),
    ]


def test_extract_roster_entries_supports_cuhk_teacher_search_markdown_personal_homepages():
    markdown = """
    * [返回主站](https://www.cuhk.edu.cn/)
    * [院长致辞](https://sse.cuhk.edu.cn/page/42)
    * [黄建伟](https://jianwei.cuhk.edu.cn/)

    校长讲座教授

    * [崔曙光](https://myweb.cuhk.edu.cn/cuishuguang)

    校长学勤讲座教授
    """

    entries = extract_roster_entries(
        markdown,
        institution="香港中文大学（深圳）",
        department="理工学院",
        source_url="https://sse.cuhk.edu.cn/teacher-search",
    )

    assert [(entry.name, entry.profile_url) for entry in entries] == [
        ("黄建伟", "https://jianwei.cuhk.edu.cn/"),
        ("崔曙光", "https://myweb.cuhk.edu.cn/cuishuguang"),
    ]
