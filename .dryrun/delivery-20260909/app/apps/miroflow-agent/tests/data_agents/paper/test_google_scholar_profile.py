# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.paper.google_scholar_profile import (
    discover_professor_paper_candidates_from_google_scholar_profile,
)


def test_discover_professor_paper_candidates_from_google_scholar_profile_extracts_metrics_and_papers():
    sample_html = """
<html>
  <body>
    <div id="gsc_prf_in">Jianwei Huang 黄建伟</div>
    <table id="gsc_rsb_st">
      <tr>
        <td class="gsc_rsb_sth">Citations</td>
        <td class="gsc_rsb_std">20,820</td>
        <td class="gsc_rsb_std">12,345</td>
      </tr>
      <tr>
        <td class="gsc_rsb_sth">h-index</td>
        <td class="gsc_rsb_std">71</td>
        <td class="gsc_rsb_std">44</td>
      </tr>
    </table>
    <tbody id="gsc_a_b">
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a class="gsc_a_at">Auction-based spectrum sharing</a>
          <div class="gs_gray">J Huang, RA Berry, ML Honig</div>
          <div class="gs_gray">Mobile Networks and Applications 11 (3), 405-418</div>
        </td>
        <td class="gsc_a_c"><a class="gsc_a_ac gs_ibl">817</a></td>
        <td class="gsc_a_y"><span class="gsc_a_h">2006</span></td>
      </tr>
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a class="gsc_a_at">Vehicle-to-aggregator interaction game</a>
          <div class="gs_gray">C Wu, H Mohsenian-Rad, J Huang</div>
          <div class="gs_gray">IEEE Transactions on Smart Grid 3 (1), 434-442</div>
        </td>
        <td class="gsc_a_c"><a class="gsc_a_ac gs_ibl">474</a></td>
        <td class="gsc_a_y"><span class="gsc_a_h">2012</span></td>
      </tr>
    </tbody>
  </body>
</html>
"""

    result = discover_professor_paper_candidates_from_google_scholar_profile(
        professor_id="PROF-001",
        professor_name="黄建伟",
        institution="香港中文大学（深圳）",
        profile_url="https://scholar.google.com/citations?user=QQq52JcAAAAJ",
        request_text=lambda _url: sample_html,
        max_papers=5,
    )

    assert result.source == "official_linked_google_scholar"
    assert result.author_id == "https://scholar.google.com/citations?user=QQq52JcAAAAJ"
    assert result.citation_count == 20820
    assert result.h_index == 71
    assert result.paper_count == 2
    assert [paper.title for paper in result.papers] == [
        "Auction-based spectrum sharing",
        "Vehicle-to-aggregator interaction game",
    ]
    assert result.papers[0].venue == "Mobile Networks and Applications 11 (3), 405-418"
    assert result.papers[0].citation_count == 817
    assert result.papers[1].year == 2012


def test_discover_professor_paper_candidates_from_google_scholar_profile_rejects_non_scholar_url():
    result = discover_professor_paper_candidates_from_google_scholar_profile(
        professor_id="PROF-001",
        professor_name="黄建伟",
        institution="香港中文大学（深圳）",
        profile_url="https://example.com/profile",
        request_text=lambda _url: (_ for _ in ()).throw(AssertionError("should not fetch")),
    )

    assert result.source == "official_linked_google_scholar"
    assert result.author_id is None
    assert result.paper_count is None
    assert result.papers == []
