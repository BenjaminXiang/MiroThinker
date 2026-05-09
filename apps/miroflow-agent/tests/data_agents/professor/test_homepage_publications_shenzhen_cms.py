from __future__ import annotations

from pathlib import Path

from src.data_agents.professor.homepage_publications import (
    extract_publications_from_html,
)


_RUN_FIXTURE_DIR = (
    Path(__file__).resolve().parents[5]
    / "logs"
    / "data_agents"
    / "paper"
    / "homepage_ingest_runs"
    / "2026-05-09"
)


def _paper_paragraphs() -> str:
    return """
    <p>1. Adaptive action chunking at inference time for vision language action
    models. IEEE Conference on Computer Vision and Pattern Recognition, 2026.</p>
    <p>2. Reliable vector guided softmax loss for robust face recognition
    systems. IEEE Transactions on Image Processing, 2024.</p>
    <p>3. Teacher guided neural architecture search for face recognition
    models. AAAI Conference on Artificial Intelligence, 2021.</p>
    <p>4. Exclusivity consistency regularized knowledge distillation for face
    recognition. European Conference on Computer Vision, 2020.</p>
    <p>5. Loss function search for face recognition with noisy web labels.
    International Conference on Machine Learning, 2020.</p>
    """


def _br_separated_papers() -> str:
    return """
    1. Adaptive action chunking at inference time for vision language action
    models. IEEE Conference on Computer Vision and Pattern Recognition, 2026.<br/>
    2. Reliable vector guided softmax loss for robust face recognition
    systems. IEEE Transactions on Image Processing, 2024.<br/>
    3. Teacher guided neural architecture search for face recognition
    models. AAAI Conference on Artificial Intelligence, 2021.<br/>
    4. Exclusivity consistency regularized knowledge distillation for face
    recognition. European Conference on Computer Vision, 2020.<br/>
    5. Loss function search for face recognition with noisy web labels.
    International Conference on Machine Learning, 2020.
    """


V1_ACADEMIC_RESULTS_HTML = f"""
<html><body>
  <div class="item">
    <h3 class="tit">学术成果</h3>
    <div class="desc">
      <p>近年发表的主要学术论文 (Selected Journal Papers)：</p>
      {_paper_paragraphs()}
    </div>
  </div>
</body></html>
"""


V2_STRONG_PARAGRAPH_HTML = f"""
<html><body>
  <div class="WordSection1">
    <p><strong><span>代表性论文：</span></strong></p>
    <p>{_br_separated_papers()}</p>
  </div>
</body></html>
"""


V3_CMS_TITLE_HTML = f"""
<html><body>
  <div class="body">
    <div class="tit">代表性文章</div>
    <div class="text">
      {_paper_paragraphs()}
    </div>
  </div>
</body></html>
"""


V4_STANDALONE_HEADING_HTML = f"""
<html><body>
  <div class="szdw_bd">
    <p>代表文章：</p>
    {_paper_paragraphs()}
  </div>
</body></html>
"""


def _extract(html: str):
    return extract_publications_from_html(html, page_url="https://example.edu/prof")


def test_v1_academic_results_heading_uses_new_vocab_word():
    publications = _extract(V1_ACADEMIC_RESULTS_HTML)

    assert len(publications) >= 5


def test_v2_strong_paragraph_heading_accepts_trailing_punctuation():
    publications = _extract(V2_STRONG_PARAGRAPH_HTML)

    assert len(publications) >= 5


def test_v3_cms_title_class_heading_is_detected():
    publications = _extract(V3_CMS_TITLE_HTML)

    assert len(publications) >= 5


def test_v4_short_standalone_exact_vocab_heading_is_detected():
    publications = _extract(V4_STANDALONE_HEADING_HTML)

    assert len(publications) >= 5


def test_embedded_vocab_in_body_copy_is_not_a_heading():
    html = """
    <html><body>
      <div>
        <p>本团队近年发表论文50余篇，主持多个科研项目，研究成果服务产业。</p>
        <p>联系方式：teacher@example.edu</p>
      </div>
    </body></html>
    """

    assert _extract(html) == []


def test_swyxgcxy_prefetched_sample_still_extracts_papers():
    html = (_RUN_FIXTURE_DIR / "PROF-2E2F7D86A756.html").read_text(encoding="utf-8")

    publications = extract_publications_from_html(
        html,
        page_url="file://PROF-2E2F7D86A756.html",
    )

    assert len(publications) >= 5
