#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
import sqlite3
import string
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domain.config import VERSION
from domain.auth import get_password_hash
from domain.permission.types import PERMISSION_DEFINITIONS
from domain.role.types import SystemRoles


def _project_root() -> Path:
    return PROJECT_ROOT


def _supports_color() -> bool:
    return sys.stderr.isatty() and not os.getenv("NO_COLOR")


def _print_banner() -> None:
    if not sys.stderr.isatty():
        return

    banner = "\n".join(
        [
            "███████╗ ██████╗ ██╗  ██╗███████╗██╗",
            "██╔════╝██╔═══██╗╚██╗██╔╝██╔════╝██║",
            "█████╗  ██║   ██║ ╚███╔╝ █████╗  ██║",
            "██╔══╝  ██║   ██║ ██╔██╗ ██╔══╝  ██║",
            "██║     ╚██████╔╝██╔╝ ██╗███████╗███████╗",
            "╚═╝      ╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝",
        ]
    )
    title = f"Foxel Admin CLI  {VERSION}"

    if _supports_color():
        c_reset = "\033[0m"
        c_bold = "\033[1m"
        c_orange = "\033[38;5;208m"
        c_orange_light = "\033[38;5;214m"
        c_orange_lighter = "\033[38;5;220m"

        banner_lines = banner.splitlines()
        shades = [
            c_orange,
            c_orange_light,
            c_orange_lighter,
            c_orange_lighter,
            c_orange_light,
            c_orange,
        ]
        for line, color in zip(banner_lines, shades, strict=False):
            print(f"{c_bold}{color}{line}{c_reset}", file=sys.stderr)
        print(f"{c_bold}{title}{c_reset}\n", file=sys.stderr)
    else:
        print(banner, file=sys.stderr)
        print(f"{title}\n", file=sys.stderr)


def _default_db_path() -> Path:
    return _project_root() / "data/db/db.sqlite3"


def _gen_password(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _find_user(conn: sqlite3.Connection, username_or_email: str) -> tuple[int, str] | None:
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM user WHERE username = ?", (username_or_email,))
    row = cursor.fetchone()
    if row:
        return int(row[0]), str(row[1])

    cursor.execute("SELECT id, username FROM user WHERE email = ?", (username_or_email,))
    row = cursor.fetchone()
    if row:
        return int(row[0]), str(row[1])

    normalized = username_or_email.strip().lower()
    if normalized and normalized != username_or_email:
        cursor.execute("SELECT id, username FROM user WHERE email = ?", (normalized,))
        row = cursor.fetchone()
        if row:
            return int(row[0]), str(row[1])

    return None


def _cmd_reset_password(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser() if args.db else _default_db_path()

    if args.random:
        password = _gen_password(args.length)
    else:
        password = args.password

    hashed_password = get_password_hash(password)

    conn = sqlite3.connect(str(db_path))
    try:
        user = _find_user(conn, args.username_or_email)
        if not user:
            print(f"用户不存在: {args.username_or_email}", file=sys.stderr)
            return 1
        user_id, username = user
        conn.execute(
            "UPDATE user SET hashed_password = ? WHERE id = ?",
            (hashed_password, user_id),
        )
        conn.commit()
    finally:
        conn.close()

    if args.random:
        print(password)
    print(f"已重置用户密码: {username} (id={user_id})", file=sys.stderr)
    return 0


def _cmd_init_rbac(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser() if args.db else _default_db_path()

    role_definitions = [
        {
            "name": SystemRoles.ADMIN,
            "description": "管理员角色，拥有所有系统和适配器权限",
        },
        {
            "name": SystemRoles.USER,
            "description": "普通用户角色，需要管理员配置路径权限",
        },
        {
            "name": SystemRoles.VIEWER,
            "description": "只读用户角色，仅可查看文件",
        },
    ]

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT 1 FROM permissions LIMIT 1")
            cursor.execute("SELECT 1 FROM roles LIMIT 1")
            cursor.execute("SELECT 1 FROM role_permissions LIMIT 1")
            cursor.execute("SELECT 1 FROM path_rules LIMIT 1")
        except sqlite3.OperationalError as exc:
            print(f"数据库未初始化（缺少表）。请先启动一次服务生成表。{exc}", file=sys.stderr)
            return 1

        # upsert permissions
        for perm in PERMISSION_DEFINITIONS:
            cursor.execute(
                """
                INSERT INTO permissions (code, name, category, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                  name = excluded.name,
                  category = excluded.category,
                  description = excluded.description
                """,
                (
                    perm["code"],
                    perm["name"],
                    perm["category"],
                    perm.get("description"),
                ),
            )

        # upsert roles
        for role in role_definitions:
            cursor.execute(
                """
                INSERT INTO roles (name, description, is_system)
                VALUES (?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET
                  description = excluded.description,
                  is_system = 1
                """,
                (role["name"], role["description"]),
            )

        # grant all permissions to Admin role
        cursor.execute("SELECT id FROM roles WHERE name = ?", (SystemRoles.ADMIN,))
        admin_row = cursor.fetchone()
        if not admin_row:
            print("初始化失败：未找到 Admin 角色", file=sys.stderr)
            return 1
        admin_role_id = int(admin_row[0])

        cursor.execute("DELETE FROM role_permissions WHERE role_id = ?", (admin_role_id,))
        cursor.execute("SELECT id FROM permissions")
        permission_ids = [int(row[0]) for row in cursor.fetchall()]
        cursor.executemany(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            [(admin_role_id, pid) for pid in permission_ids],
        )

        # ensure Admin has full access path rule
        cursor.execute(
            "SELECT id FROM path_rules WHERE role_id = ? AND path_pattern = ? LIMIT 1",
            (admin_role_id, "/**"),
        )
        existing_rule = cursor.fetchone()
        if existing_rule:
            cursor.execute(
                """
                UPDATE path_rules
                SET is_regex = 0,
                    can_read = 1,
                    can_write = 1,
                    can_delete = 1,
                    can_share = 1,
                    priority = 100
                WHERE id = ?
                """,
                (int(existing_rule[0]),),
            )
        else:
            cursor.execute(
                """
                INSERT INTO path_rules (
                  role_id, path_pattern, is_regex,
                  can_read, can_write, can_delete, can_share,
                  priority
                )
                VALUES (?, ?, 0, 1, 1, 1, 1, 100)
                """,
                (admin_role_id, "/**"),
            )

        conn.commit()
    finally:
        conn.close()

    print(f"已初始化权限: {len(PERMISSION_DEFINITIONS)} 条", file=sys.stderr)
    print("已补齐内置角色: Admin / User / Viewer", file=sys.stderr)
    print("已为 Admin 角色授予全部权限并设置 /** 全路径规则", file=sys.stderr)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foxel")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_password = subparsers.add_parser("reset-password", help="重置用户密码")
    reset_password.add_argument("username_or_email", help="用户名或邮箱")
    reset_password.add_argument("password", nargs="?", help="新密码（或用 --random）")
    reset_password.add_argument("--random", action="store_true", help="生成随机密码并输出到 stdout")
    reset_password.add_argument("--length", type=int, default=16, help="随机密码长度（默认 16）")
    reset_password.add_argument("--db", help="sqlite db 路径（默认 data/db/db.sqlite3）")
    reset_password.set_defaults(func=_cmd_reset_password)

    init_rbac = subparsers.add_parser("init-rbac", help="初始化权限与内置角色")
    init_rbac.add_argument("--db", help="sqlite db 路径（默认 data/db/db.sqlite3）")
    init_rbac.set_defaults(func=_cmd_init_rbac)

    return parser


def main(argv: list[str] | None = None) -> int:
    _print_banner()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "reset-password" and not args.random and not args.password:
        parser.error("reset-password 需要提供 password 或使用 --random")

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
