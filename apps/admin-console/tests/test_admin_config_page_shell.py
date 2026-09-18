"""R6/R7 — the rebuilt admin page: shell, assets and the save/restart banner.

Fixture source: the real FastAPI route graph (page + static mount) and the
shipped static files. The page is a shell — every field, role block and probe
button is built by `admin.js` from the `/config`, `/secrets` and
`/connections/presets` payloads — so these marker tests lock the *shape*; the
scratch-port smoke locks the behaviour a marker cannot express.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from tests.conftest import authorized_client

_CARD_IDS = ("card-collection", "card-serving", "card-paths", "card-models")
_ROLE_IDS = ("chat", "collection", "embedding", "rerank", "web")
_API_CALLS = (
    "api/canonical-v2/admin/system-status",
    "api/canonical-v2/admin/config",
    "api/canonical-v2/admin/secrets",
    "api/canonical-v2/admin/connections/test",
    "api/canonical-v2/admin/connections/presets",
    "api/canonical-v2/admin/connections/",
)
# The four defects the rebuild removes: the client whitelist, the dump-all patch,
# the provider table, and the global health button (its API stays, unused here).
_REMOVED_MARKERS = (
    "FIELD_SPECS",
    "collectPatch",
    "providerTable",
    "healthCheck",
    "立即检查",
    "statusTiles",
    "configForm",
    "secretsTable",
)


def _client() -> TestClient:
    return authorized_client(raise_server_exceptions=False)


def _page() -> str:
    response = _client().get("/admin")

    assert response.status_code == 200
    return response.text


def _script() -> str:
    response = _client().get("/static/admin.js")

    assert response.status_code == 200
    return response.text


def test_shell_loads_its_own_assets() -> None:
    page = _page()

    assert '<link rel="stylesheet" href="/static/admin.css"' in page
    assert '<script src="/static/admin.js"' in page
    assert '<script src="/static/nav_auth.js"' in page


def test_shell_keeps_the_four_cards_and_the_snapshot() -> None:
    page = _page()

    for card in _CARD_IDS:
        assert f'id="{card}"' in page, card
    assert 'id="snapshot"' in page
    assert "只读快照" in page
    for container in (
        "collectionFields",
        "servingFields",
        "pathsFields",
        "roleBlocks",
    ):
        assert f'id="{container}"' in page, container
    assert "各域新鲜度" in page
    assert 'id="storageRows"' in page
    assert 'id="retentionPreview"' in page


def test_shell_carries_the_save_banner_and_per_card_saves() -> None:
    page = _page()

    assert 'id="banner"' in page
    assert 'id="bannerText"' in page
    assert 'id="restartCommand"' in page
    assert "systemctl --user restart canonical-v2-backend" in page
    for group in ("collection", "serving", "paths"):
        assert f'data-save-card="{group}"' in page, group
        assert f'id="save-{group}"' in page, group


def test_removed_markers_are_gone_from_page_script_and_style() -> None:
    page = _page()
    script = _script()
    style = _client().get("/static/admin.css")

    assert style.status_code == 200
    assert ".card" in style.text
    for marker in _REMOVED_MARKERS:
        assert marker not in page, marker
        assert marker not in script, marker
    assert "providerTable" not in style.text


def test_assets_carry_the_page_contracts() -> None:
    page = _page()
    script = _script()

    for call in _API_CALLS:
        assert call in script, call
    assert "密钥只写不读" in page
    assert 'id="testRerank"' in page


def test_banner_semantics_are_present_in_the_page_script() -> None:
    script = _script()

    assert "项未保存" in script
    assert "需重启生效" in script
    assert "systemctl --user restart canonical-v2-backend" in script
    assert "navigator.clipboard" in script


def test_the_three_state_gesture_is_rendered_per_kind() -> None:
    script = _script()

    assert "默认" in script and "启用" in script and "停用" in script
    assert "回到默认" in script


# -- 模型与连接（按角色） -----------------------------------------------------
# The role taxonomy is the card's information architecture, so the shell owns the
# five blocks (titles + the containers the script fills); the per-role controls
# stay script-built, which is why 测试连通性 / 拉取模型列表 must not appear here.


def test_shell_lists_the_five_model_roles_in_order() -> None:
    page = _page()

    assert "模型与连接" in page
    titles = (
        "对话模型（回答与改写用它）",
        "采集模型（摘要与富化用它）",
        "嵌入模型（检索向量用它）",
        "重排模型",
        "Web 搜索",
    )
    cursor = -1
    for title in titles:
        at = page.find(f">{title}<")
        assert at > cursor, title
        cursor = at
    for role_id in _ROLE_IDS:
        assert f'data-role="{role_id}"' in page, role_id


def test_every_role_block_has_the_containers_the_script_fills() -> None:
    """A role without its containers would render nothing: the invariant is per role."""

    page = _page()

    for role_id in _ROLE_IDS:
        assert f'id="role-{role_id}-state"' in page, role_id
    for role_id, container in (
        ("chat", "chatBody"),
        ("collection", "collectionBody"),
        ("embedding", "embeddingBody"),
        ("rerank", "rerankBody"),
        ("web", "webBody"),
    ):
        assert f'id="{container}"' in page, role_id
    for role_id in ("chat", "collection", "embedding", "rerank"):
        assert f'id="{role_id}Effective"' in page, role_id
        assert f'id="{role_id}Actions"' in page, role_id


def test_the_shell_has_no_duplicate_element_ids() -> None:
    """Duplicate ids are silent and destructive: `getElementById` returns the first,
    so a role writing into its state node can wipe another card's rows (found by the
    real-browser pass on 2026-09-19: role `collection` shared card 1's id)."""

    page = _page()
    ids = re.findall(r'id="([^"]+)"', page)
    duplicates = sorted({value for value in ids if ids.count(value) > 1})

    assert duplicates == []


def test_every_id_the_script_looks_up_exists_in_the_shell() -> None:
    """`el()` on a missing id fails silently: every literal lookup must be in the shell."""

    page = _page()
    script = _script()
    shell_ids = set(re.findall(r'id="([^"]+)"', page))
    missing = sorted(set(re.findall(r'el\("([^"]+)"\)', script)) - shell_ids)

    assert missing == []


def test_embedding_role_spells_out_the_rebuild_consequence() -> None:
    page = _page()

    assert "服务线索引由发布包冻结：改它需要重建全部向量" in page
    assert 'id="role-embedding"' in page


def test_the_probe_buttons_stay_script_built() -> None:
    page = _page()

    # The labels may appear in prose (the card explains the shared rate limit), but
    # no probe control may be in the shell: the script builds them from the payload.
    assert ">测试连通性<" not in page
    assert ">拉取模型列表<" not in page
    # The role copy that must travel with each control, however, is script-side.
    script = _script()
    assert "保存 ≠ 测试" in script
    assert "高级：采集侧覆盖" in script
    assert "只影响后续采集/构建，不改服务线索引" in script
