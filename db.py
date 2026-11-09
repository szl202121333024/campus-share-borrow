"""数据库唯一入口（PC-2、AR-6）：连接、建表、自举与种子数据。

全项目唯一允许出现 sqlite3.connect( 的文件；四项 PRAGMA 只在 get_db() 内集中设置。
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from flask import g

from config import BORROW_DAYS, TIME_FORMAT
from security import hash_password

DB_PATH = os.environ.get(
    "CAMPUS_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus_share_borrow.sqlite"),
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('student', 'admin')),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL CHECK (category IN ('book', 'equipment')),
    status     TEXT NOT NULL DEFAULT 'available'
               CHECK (status IN ('available', 'unavailable')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES items(id),
    user_id     INTEGER NOT NULL REFERENCES users(id),
    borrowed_at TEXT NOT NULL,
    due_at      TEXT NOT NULL,
    returned_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_loans_active_item
    ON loans(item_id) WHERE returned_at IS NULL;
"""

# 自举后的 PRAGMA 自检期望值（AR-7：不得静默退化）
EXPECTED_PRAGMAS = {
    "journal_mode": "wal",
    "busy_timeout": "5000",
    "foreign_keys": "1",
    "synchronous": "1",
}

SEED_USERS = [
    ("2024001", "林晓", "student", "stu123456"),
    ("2024002", "陈默", "student", "stu123456"),
    ("A001", "周衡", "admin", "admin123456"),
]

# 种子物品：3 本图书 + 3 件器材（AC-1.1.2）
SEED_ITEMS = [
    ("算法图解", "book"),
    ("活着", "book"),
    ("三体", "book"),
    ("热熔胶枪", "equipment"),
    ("蓝牙音箱", "equipment"),
    ("投影仪", "equipment"),
]


class BootstrapError(Exception):
    """自举失败：由 app.main() 打印一行中文原因并以非零码退出（AC-1.1.3/1.1.4）。"""


def now_text():
    return datetime.now().strftime(TIME_FORMAT)


def due_text(from_text=None):
    base = datetime.strptime(from_text or now_text(), TIME_FORMAT)
    return (base + timedelta(days=BORROW_DAYS)).strftime(TIME_FORMAT)


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, isolation_level=None)  # 自动提交，事务边界自己管（PC-4）
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")      # 库级持久设置，幂等
        conn.execute("PRAGMA busy_timeout = 5000")     # 连接级
        conn.execute("PRAGMA foreign_keys = ON")       # 连接级
        conn.execute("PRAGMA synchronous = NORMAL")
        g.db = conn
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def write_transaction():
    """写事务唯一原语（PC-4、AC-2.1.10）：显式 BEGIN IMMEDIATE，异常必回滚。"""
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _seed_if_empty(db):
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count > 0:
        return
    created_at = now_text()
    for student_id, name, role, password in SEED_USERS:
        db.execute(
            "INSERT INTO users (student_id, name, password_hash, role, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (student_id, name, hash_password(password), role, created_at),
        )
    for name, category in SEED_ITEMS:
        db.execute(
            "INSERT INTO items (name, category, status, created_at) VALUES (?, ?, 'available', ?)",
            (name, category, created_at),
        )


def _assert_pragmas(app):
    """在自举连接关闭后，用【新连接】断言四项 PRAGMA（AC-1.1.3）。"""
    with app.app_context():
        db = get_db()
        for pragma, expected in EXPECTED_PRAGMAS.items():
            actual = str(db.execute(f"PRAGMA {pragma}").fetchone()[0]).lower()
            if actual != expected:
                raise BootstrapError(
                    f"数据库自检未通过：PRAGMA {pragma} 实际为 {actual}，期望 {expected}"
                )


def bootstrap_db(app):
    try:
        with app.app_context():
            db = get_db()
            db.executescript(SCHEMA_SQL)
            _seed_if_empty(db)
    except (sqlite3.OperationalError, PermissionError, OSError) as exc:
        raise BootstrapError(f"无法读写数据库文件（目录不可写或文件损坏）：{exc}") from exc
    _assert_pragmas(app)
