from src.data_agents.professor.discovery import discover_professor_seeds
from src.data_agents.professor.models import ProfessorRosterSeed


def test_discover_professor_seeds_uses_cuhk_teacher_search_pagination():
    seed = ProfessorRosterSeed(
        institution="香港中文大学（深圳）",
        department="理工学院",
        roster_url="https://sse.cuhk.edu.cn/teacher-search",
    )
    pages = {
        "https://sse.cuhk.edu.cn/teacher-search": """
<html><body>
  <div class="list-content">
    <div class="list-text">
      <div class="list-title">
        <a href="https://myweb.cuhk.edu.cn/cuishuguang" target="_blank">崔曙光</a>
      </div>
    </div>
  </div>
  <div class="list-content">
    <div class="list-text">
      <div class="list-title">
        <a href="https://myweb.cuhk.edu.cn/alicezhang" target="_blank">Alice Zhang</a>
      </div>
    </div>
  </div>
</body></html>
""",
        "https://sse.cuhk.edu.cn/teacher-search?page=1": """
<html><body>
  <div class="list-content">
    <div class="list-text">
      <div class="list-title">
        <a href="https://myweb.cuhk.edu.cn/bobli" target="_blank">Bob Li</a>
      </div>
    </div>
  </div>
</body></html>
""",
        "https://sse.cuhk.edu.cn/teacher-search?page=2": "<html><body></body></html>",
    }
    calls: list[str] = []

    def fake_fetch_html(url: str) -> str:
        calls.append(url)
        return pages[url]

    result = discover_professor_seeds(
        seeds=[seed],
        fetch_html=fake_fetch_html,
    )

    assert calls == [
        "https://sse.cuhk.edu.cn/teacher-search",
        "https://sse.cuhk.edu.cn/teacher-search?page=1",
        "https://sse.cuhk.edu.cn/teacher-search?page=2",
    ]
    assert [(item.name, item.department, item.profile_url) for item in result.professors] == [
        ("崔曙光", "理工学院", "https://myweb.cuhk.edu.cn/cuishuguang"),
        ("Alice Zhang", "理工学院", "https://myweb.cuhk.edu.cn/alicezhang"),
        ("Bob Li", "理工学院", "https://myweb.cuhk.edu.cn/bobli"),
    ]
    assert result.source_statuses[0].status == "resolved"
    assert result.source_statuses[0].visited_urls == calls


def test_discover_professor_seeds_fetches_labeled_direct_profile_seed_before_resolving():
    seed = ProfessorRosterSeed(
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        roster_url="https://sai.cuhk.edu.cn/teacher/104",
        label="NAKAMURA, Satoshi",
    )
    calls: list[str] = []

    def fake_fetch_html(url: str) -> str:
        calls.append(url)
        return "<html><head><title>NAKAMURA, Satoshi | 人工智能学院</title></head><body></body></html>"

    result = discover_professor_seeds(
        seeds=[seed],
        fetch_html=fake_fetch_html,
    )

    assert calls == ["https://sai.cuhk.edu.cn/teacher/104"]
    assert [(item.name, item.profile_url) for item in result.professors] == [
        ("NAKAMURA, Satoshi", "https://sai.cuhk.edu.cn/teacher/104"),
    ]
    assert result.source_statuses[0].reason != "direct_profile_seed_label"
