"""忘了管理员口令的出路：`mirothinker-reset-admin-password`（容器交付件）。

Fixture source: TestClient over a scratch credential store in ``tmp_path``（沿用
``test_admin_auth_http.py`` 的夹具形状）。口令全是夹具现场生成的临时值，从不出现在输出里。

钉住的三条：
* **重置后新口令可登、旧口令被拒**（真走 `POST /api/auth/login`，不是只调 store）；
* **改的是服务在用的那个库**（路径由 `CANONICAL_V2_ACCESS_LOG_DB` 决定，与本包冻结命令文件一致），
  且**库不存在时拒绝执行、绝不新建**一个空副本；
* **不削弱登录限流**：重置前触发的锁定，重置后依然生效。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import importlib.util
import secrets

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.services.admin_auth import (
    DB_PATH_ENV,
    KEY_PATH_ENV,
    ACCESS_LOG_PATH_ENV,
    AdminAuthStore,
    AdminLoginThrottle,
)

_LOGIN = "/api/auth/login"
_USERNAME = "admin"
_TOOL = Path(__file__).resolve().parents[3] / "deploy" / "docker" / "reset_admin_password.py"


def _scratch_password() -> str:
    return secrets.token_urlsafe(12)


def _tool_module():
    if not _TOOL.is_file():
        pytest.skip(f"工具不在这个 checkout 里：{_TOOL}")
    spec = importlib.util.spec_from_file_location("_reset_admin_password", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def fresh_login_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The login limiter is process-wide by design; each test needs its own."""

    from backend.api import admin_auth as admin_auth_api

    monkeypatch.setattr(admin_auth_api, "_LOGIN_LIMITER", AdminLoginThrottle())


@pytest.fixture()
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把状态目录指到 tmp_path，只设冻结命令文件里那一个变量（与本包真实布局一致）。

    **安全闸**：连模块的兜底 `DEFAULT_STATE_DIR` 也一起挪到 tmp_path，并断言解析结果落在 tmp_path 里。
    这条不是洁癖 —— 开发机上 `/var/tmp/mirothinker-canonical-v2-s12f` 就是**真活线**的状态目录：
    工具一旦忽略环境变量（或有变异版这么做），测试就会**真的把活线口令改掉**（2026-09-22 踩过，
    一次变异测试往活线写了 34 条 admin.password_reset）。有了这道闸，任何"改错地方"的版本
    都只会在 tmp_path 里打转。
    """

    from backend.services import admin_auth

    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.delenv(DB_PATH_ENV, raising=False)
    monkeypatch.delenv(KEY_PATH_ENV, raising=False)
    monkeypatch.setenv(ACCESS_LOG_PATH_ENV, str(state / "access-logs.sqlite3"))
    monkeypatch.setattr(admin_auth, "DEFAULT_STATE_DIR", tmp_path / "default-state")
    resolved = admin_auth.default_db_path()
    assert tmp_path in resolved.parents, f"测试要改的库必须落在 tmp_path 里，实得 {resolved}"
    return state


def _seed(state: Path, password: str) -> AdminAuthStore:
    """First boot on this scratch state dir: one admin, plus the initial-password file."""

    store = AdminAuthStore(state / "admin-auth.sqlite3")
    store.seed_initial_admin(password=password, username=_USERNAME, announce=lambda _: None)
    return store


def _login(client: TestClient, password: str, username: str = _USERNAME):
    return client.post(_LOGIN, json={"username": username, "password": password})


def _read_reset_password(state: Path) -> tuple[Path, str]:
    path = state / f"admin-password-reset-{datetime.now():%Y-%m-%d}.txt"
    assert path.is_file(), f"没写出重置文件：{sorted(p.name for p in state.iterdir())}"
    return path, path.read_text(encoding="utf-8").strip()


def test_reset_rotates_the_password_and_the_old_one_is_rejected(
    client: TestClient, state_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """一旧一新两条口令走真登录路由：旧 401 invalid_credentials、新 200。"""

    old_password = _scratch_password()
    store = _seed(state_dir, old_password)
    try:
        assert _login(client, old_password).status_code == 200
        assert _tool_module().main([]) == 0
        _, new_password = _read_reset_password(state_dir)
        assert new_password != old_password
        assert _login(client, new_password).status_code == 200
        rejected = _login(client, old_password)
        assert rejected.status_code == 401
        assert rejected.json()["detail"] == "invalid_credentials"
    finally:
        store.close()
    capsys.readouterr()


def test_the_tool_never_prints_the_password(
    state_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """只打印路径，从不打印口令 —— 这是交付件的硬约束。"""

    store = _seed(state_dir, _scratch_password())
    try:
        assert _tool_module().main([]) == 0
        path, password = _read_reset_password(state_dir)
    finally:
        store.close()
    captured = capsys.readouterr()
    assert password not in captured.out
    assert password not in captured.err
    assert str(path) in captured.out


def test_the_reset_file_lands_beside_the_mounted_db_at_0600(state_dir: Path) -> None:
    """沿用首启口令的约定：0600、写在库旁边（容器里 = 挂载出来的状态目录）。"""

    store = _seed(state_dir, _scratch_password())
    try:
        assert _tool_module().main([]) == 0
        path, password = _read_reset_password(state_dir)
        mode = path.stat().st_mode & 0o777
    finally:
        store.close()
    assert path.parent == state_dir
    assert mode == 0o600
    assert len(password) == 16


def test_the_tool_targets_the_database_the_service_uses(
    state_dir: Path, tmp_path: Path
) -> None:
    """改的是 `CANONICAL_V2_ACCESS_LOG_DB` 指向的那个库；别处的同名库一个字节都不动。"""

    store = _seed(state_dir, _scratch_password())
    decoy_dir = tmp_path / "elsewhere"
    decoy_dir.mkdir()
    decoy_password = _scratch_password()
    decoy = AdminAuthStore(decoy_dir / "admin-auth.sqlite3")
    try:
        decoy.create_account(_USERNAME, decoy_password)
        assert _tool_module().main([]) == 0
        _, new_password = _read_reset_password(state_dir)
        served = AdminAuthStore(state_dir / "admin-auth.sqlite3")
        try:
            assert served.verify_credentials(_USERNAME, new_password)
        finally:
            served.close()
        assert decoy.verify_credentials(_USERNAME, decoy_password)
        assert not (decoy_dir / f"admin-password-reset-{datetime.now():%Y-%m-%d}.txt").exists()
    finally:
        store.close()
        decoy.close()


def test_the_tool_refuses_a_missing_database_instead_of_creating_one(
    state_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """库不存在 ⇒ 红着退出，并且**不新建**（否则操作者会改到一个空副本上）。"""

    assert _tool_module().main([]) == 3
    assert not (state_dir / "admin-auth.sqlite3").exists()
    assert not (state_dir / f"admin-password-reset-{datetime.now():%Y-%m-%d}.txt").exists()
    assert "口令库不存在" in capsys.readouterr().out


def test_a_second_run_is_idempotent(state_dir: Path) -> None:
    """连跑两次都成功；以今天的文件为准（后来那次覆盖前一次），epoch 逐次递增。"""

    store = _seed(state_dir, _scratch_password())
    try:
        assert _tool_module().main([]) == 0
        _, first = _read_reset_password(state_dir)
        assert _tool_module().main([]) == 0
        path, second = _read_reset_password(state_dir)
        assert second != first
        assert path.read_text(encoding="utf-8").strip() == second
        accounts = store.accounts()
        assert len(accounts) == 1
        assert accounts[0].password_epoch == 3  # 首启 1 + 两次重置
        store.close()
        fresh = AdminAuthStore(state_dir / "admin-auth.sqlite3")
        try:
            assert fresh.verify_credentials(_USERNAME, second)
            assert not fresh.verify_credentials(_USERNAME, first)
        finally:
            fresh.close()
    finally:
        pass


def test_the_audit_trail_records_the_reset(state_dir: Path) -> None:
    """走模块自己的入口 ⇒ 审计里留下一条 admin.password_reset（不是"改了但没有记录"）。"""

    store = _seed(state_dir, _scratch_password())
    try:
        assert _tool_module().main([]) == 0
        records = store.audit_records(action="admin.password_reset")
    finally:
        store.close()
    assert [record.result for record in records] == ["ok"]
    assert records[0].target == _USERNAME
    assert records[0].actor.startswith("cli:")
    assert "reset-admin-password" in (records[0].detail or "")


def test_a_reset_invalidates_the_old_session(
    client: TestClient, state_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """旧会话立刻失效：重置前拿到的 cookie，重置后连 `/me` 都过不去（口令代次 +1）。"""

    old_password = _scratch_password()
    store = _seed(state_dir, old_password)
    try:
        login = _login(client, old_password)
        assert login.status_code == 200
        cookie = login.headers["set-cookie"].split(";", 1)[0]
        assert client.get("/api/auth/me", headers={"Cookie": cookie}).status_code == 200
        assert _tool_module().main([]) == 0
        _, new_password = _read_reset_password(state_dir)
        stale = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert stale.status_code == 401
        assert stale.json()["detail"] == "authentication_required"
        assert _login(client, new_password).status_code == 200
    finally:
        store.close()
    capsys.readouterr()


def test_the_login_route_still_locks_after_a_reset(
    client: TestClient, state_dir: Path
) -> None:
    """限流不被重置削弱：锁定期间重置口令，新口令一样要等锁定到期。"""

    store = _seed(state_dir, _scratch_password())
    try:
        for _ in range(5):
            assert _login(client, "definitely-not-the-password").status_code == 401
        assert _login(client, "definitely-not-the-password").status_code == 429
        assert _tool_module().main([]) == 0
        _, new_password = _read_reset_password(state_dir)
        locked = _login(client, new_password)
        assert locked.status_code == 429
        assert locked.json()["detail"]["error"] == "locked"
    finally:
        store.close()


def test_status_is_read_only(
    state_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--status` 只报告：不动库、不写文件，且只列口令文件名、不打印内容。"""

    password = _scratch_password()
    store = _seed(state_dir, password)
    try:
        before = (state_dir / "admin-auth.sqlite3").read_bytes()
        assert _tool_module().main(["--status"]) == 0
        after = (state_dir / "admin-auth.sqlite3").read_bytes()
    finally:
        store.close()
    out = capsys.readouterr().out
    assert before == after
    assert not (state_dir / f"admin-password-reset-{datetime.now():%Y-%m-%d}.txt").exists()
    assert "账号：admin" in out
    assert password not in out
