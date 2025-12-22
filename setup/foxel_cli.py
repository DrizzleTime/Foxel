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

from domain.auth.service import get_password_hash
from domain.config.service import VERSION


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
