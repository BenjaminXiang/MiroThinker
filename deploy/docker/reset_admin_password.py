#!/opt/mirothinker/.venv/bin/python
"""管理员口令重置（忘了口令时唯一的出路；容器交付件）。

**为什么需要它**：口令只存 scrypt 加盐哈希、永不存明文（`admin_auth.py` 模块 docstring 原话：
"a stored password is only ever a salted ``scrypt`` hash"）⇒ 忘了**无法找回，只能重置**。
2026-09-22 现场撞上过一次：有人在 `/main` 改了口令、忘了新口令 ⇒ 登录不进去，而交付包里
**没有任何一条可执行的出路**。

做四件事，全部走模块自己的入口（**不手写 SQL** —— 手写会跳过模块的审计与不变量）：

1. 解析**服务在用的那个库**：`admin_auth.default_db_path()` —— `CANONICAL_V2_ADMIN_AUTH_DB` →
   否则取 `CANONICAL_V2_ACCESS_LOG_DB` 的**同目录** → 否则状态目录
   `/var/tmp/mirothinker-canonical-v2-s12f/`（容器里这就是 compose 挂载出来的那个目录）。
   **库不存在就拒绝执行**（绝不新建一个"容器层里的临时副本"让人白改一场）。
2. `AdminAuthStore.set_password()`：换哈希 + 换盐 + 递增 `password_epoch`（旧会话当场失效）；
   新口令用模块自己的 `generate_password()` 生成（16 位、去掉了 l/1/o/0 这类手抄易错字符）。
3. `append_audit(action="admin.password_reset")` 记一条（actor = `cli:<USER|uid:N>`）。
4. 新口令**只写进**状态目录里 0600 的 `admin-password-reset-<YYYY-MM-DD>.txt`
   （沿用首启口令 `admin-initial-password.txt` 的命名与权限约定），**从不打印** —— 只打印路径。

**不用重启服务**：登录时是一次新的 SELECT，SQLite WAL 下别的连接提交的写入立即可见
（容器内两进程实测见 `.agents/runs/docker-embedding-slot-symmetry-20260922/07-*`）。
旧口令与旧会话立即失效（epoch 递增）。

**不碰登录限流**：限流是**服务进程内**的内存态（`AdminLoginThrottle`：5 次口令错误锁 1 分钟、
按次数递增到 30 分钟），本工具读都不读它 ⇒ 重置**不会**解除已经生效的锁定（等它到期即可，
页面文案见 `static/main.html:31`）。

CLI：
    mirothinker-reset-admin-password                 # 重置 admin，写今天的重置文件
    mirothinker-reset-admin-password --status        # 只看：库路径、账号、口令文件（不改任何东西）
    mirothinker-reset-admin-password --username ops  # 重置别的账号
    mirothinker-reset-admin-password --db /path      # 显式指定库（非常规布局才用）

退出码：0 成功 / 3 库或账号不存在 / 4 口令文件写不进去。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys

APP_DIR = "/opt/mirothinker/apps/admin-console"
DEFAULT_USERNAME = "admin"
RESET_FILENAME_PREFIX = "admin-password-reset"

EXIT_OK = 0
EXIT_NOT_FOUND = 3
EXIT_WRITE_FAILED = 4


def _admin_auth():
    """Import the console's own credential module (never re-implement its rules)."""

    try:
        from backend.services import admin_auth
    except ModuleNotFoundError:
        sys.path.insert(0, APP_DIR)
        from backend.services import admin_auth
    return admin_auth


def _actor() -> str:
    """Who ran this: honest enough for the audit row, and never a password."""

    user = (os.environ.get("USER") or os.environ.get("LOGNAME") or "").strip()
    return f"cli:{user or f'uid:{os.getuid()}'}"


def _reset_path(state_dir: Path, now: datetime) -> Path:
    return state_dir / f"{RESET_FILENAME_PREFIX}-{now:%Y-%m-%d}.txt"


def _password_files(admin_auth, state_dir: Path) -> list[Path]:
    names = (admin_auth.PASSWORD_FILENAME,)
    files = [state_dir / name for name in names if (state_dir / name).is_file()]
    files += sorted(state_dir.glob(f"{RESET_FILENAME_PREFIX}-*.txt"), reverse=True)
    return files


def _describe(path: Path) -> str:
    if not path.exists():
        return f"{path}（不存在）"
    stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return f"{path}（{stamp}）"


def report_status(admin_auth, *, db_path: Path, key_path: Path, state_dir: Path) -> int:
    """Read-only: what an operator needs before/after a reset. Never prints a secret."""

    print("== 管理员账号库 ==")
    print(f"  口令库：{_describe(db_path)}")
    print(f"  会话签名密钥：{_describe(key_path)}")
    if not db_path.is_file():
        print("  ⇒ 库还不存在：站点还没首启过（先起服务，首启会建库并写下首启口令）")
        return EXIT_NOT_FOUND
    store = admin_auth.AdminAuthStore(db_path)
    try:
        accounts = store.accounts()
        if not accounts:
            print("  ⇒ 库里一个账号都没有（首启播种没跑成功？看容器日志 [admin-auth]）")
            return EXIT_NOT_FOUND
        for account in accounts:
            print(
                f"  账号：{account.username}（role={account.role}，"
                f"口令最后修改 {account.updated_at}，epoch={account.password_epoch}）"
            )
    finally:
        store.close()
    print("== 状态目录里的口令文件（只列文件名，从不打印内容）==")
    for path in _password_files(admin_auth, state_dir):
        print(f"  {_describe(path)}")
    print("  ⇒ `admin-initial-password.txt` 是**首启**那一次的口令：改过密之后它就不管用了；")
    print("     以最近一个 `admin-password-reset-<日期>.txt` 为准。")
    return EXIT_OK


def reset_password(
    admin_auth, *, db_path: Path, username: str, state_dir: Path, now: datetime
) -> int:
    if not db_path.is_file():
        print(f"[FAIL] 口令库不存在：{db_path}")
        print(
            "       本工具**不新建**库（否则你可能改到一个空副本上、服务还在用旧的那个）。"
            "先确认状态目录挂载对了、服务已经首启过。"
        )
        return EXIT_NOT_FOUND
    store = admin_auth.AdminAuthStore(db_path)
    try:
        if store.account(username) is None:
            known = "、".join(account.username for account in store.accounts()) or "（无）"
            print(f"[FAIL] 账号不存在：{username}（库里现有：{known}）")
            return EXIT_NOT_FOUND
        password = admin_auth.generate_password()
        store.set_password(username, password)
        store.append_audit(
            actor=_actor(),
            action="admin.password_reset",
            target=username,
            result="ok",
            detail="mirothinker-reset-admin-password",
        )
        # 自检：写出去的这份口令现在就真的能过校验（否则宁可当场红，也别让操作者扑空）
        if not store.verify_credentials(username, password):
            print("[FAIL] 自检失败：刚写入的口令没通过 verify_credentials（库可能不可写）")
            return EXIT_WRITE_FAILED
    finally:
        store.close()

    target = _reset_path(state_dir, now)
    if not state_dir.is_dir():
        print(f"[FAIL] 状态目录不存在：{state_dir}")
        return EXIT_WRITE_FAILED
    overwrote = target.is_file()
    try:
        admin_auth.prepare_private_file(target)
        target.write_text(password + "\n", encoding="utf-8")
        os.chmod(target, 0o600)
    except OSError as exc:
        print(f"[FAIL] 写口令文件失败：{exc}")
        return EXIT_WRITE_FAILED

    print("== 管理员口令已重置 ==")
    print(f"  库：{db_path}（服务在用的那个）")
    print(f"  账号：{username}（旧口令与旧会话**立即失效**；不需要重启服务）")
    print(f"  新口令在这个文件里（0600，{'已覆盖今天的文件' if overwrote else '刚创建'}）：")
    print(f"      {target}")
    print(f"  读出来：sudo cat {target}")
    print("  完整说明：CONFIG-GUIDE.md §5（甲方运维版；读完请立刻记到安全的地方）")
    print(
        "  若页面提示锁定：那是服务进程内的登录限流（5 次错误锁 1 分钟、按次数递增），"
        "重置不会解除它，稍等再登。"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    admin_auth = _admin_auth()
    parser = argparse.ArgumentParser(
        description="重置管理员口令（忘了口令时唯一的出路）。", allow_abbrev=False
    )
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="账号（默认 admin）")
    parser.add_argument("--db", type=Path, default=None, help="显式指定口令库路径")
    parser.add_argument("--status", action="store_true", help="只报告，不改任何东西")
    args = parser.parse_args(argv)

    db_path = Path(args.db) if args.db else admin_auth.default_db_path()
    key_path = admin_auth.default_key_path(db_path=db_path)
    state_dir = db_path.parent
    if args.status:
        return report_status(admin_auth, db_path=db_path, key_path=key_path, state_dir=state_dir)
    return reset_password(
        admin_auth,
        db_path=db_path,
        username=args.username,
        state_dir=state_dir,
        now=datetime.now(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
