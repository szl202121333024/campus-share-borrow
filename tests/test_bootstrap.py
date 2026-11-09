"""Story 1.1 验收测试：一条命令启动、自动建表与种子数据（AC-1.1.1 ~ AC-1.1.8）。"""

import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

import app as app_module
import db as db_module

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_SEED_ITEM_NAMES = [
    "活着", "算法图解", "三体", "热熔胶枪", "蓝牙音箱", "投影仪",
]


@contextmanager
def _fresh_db(app):
    """自举连接关闭后，经唯一入口 get_db() 在新上下文里取新连接。"""
    with app.app_context():
        yield db_module.get_db()


def test_get_items_returns_200_with_6_seed_items(client):
    """AC-1.1.1 / AC-1.1.2：启动后 GET /items 返回 200 并列出 6 件种子物品。"""
    resp = client.get("/items")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for name in EXPECTED_SEED_ITEM_NAMES:
        assert name in html


def test_unknown_route_returns_rendered_404(client):
    """Unknown routes use the shared error template and real 404 status."""
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert "RESOURCE_NOT_FOUND" in response.get_data(as_text=True)


def test_bootstrap_creates_three_tables_and_seed_rows(app):
    """AC-1.1.2：users/items/loans 三表存在；2 学生 + 1 管理员 + 6 物品（3+3）。"""
    with _fresh_db(app) as db:
        tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"users", "items", "loans"} <= tables
        assert db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'student'"
        ).fetchone()[0] == 2
        assert db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        ).fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 6
        for category in ("book", "equipment"):
            assert db.execute(
                "SELECT COUNT(*) FROM items WHERE category = ?", (category,)
            ).fetchone()[0] == 3


def test_bootstrap_completes_within_10_seconds(tmp_path, monkeypatch):
    """AC-1.1.1：自举（建表 + 种子 + 自检）在 10 秒内完成。"""
    from app import create_app

    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "fresh.sqlite"))
    started = time.monotonic()
    fresh_app = create_app()
    db_module.bootstrap_db(fresh_app)
    assert time.monotonic() - started < 10


def test_pragma_self_check_on_new_connection(app):
    """AC-1.1.3：新连接上四项 PRAGMA 返回 wal / 5000 / 1 / 1。"""
    with _fresh_db(app) as db:
        assert str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        assert str(db.execute("PRAGMA busy_timeout").fetchone()[0]) == "5000"
        assert str(db.execute("PRAGMA foreign_keys").fetchone()[0]) == "1"
        assert str(db.execute("PRAGMA synchronous").fetchone()[0]) == "1"


def test_bootstrap_error_exits_nonzero_with_one_line_reason(monkeypatch, capsys):
    """AC-1.1.3：PRAGMA 自检失败 → main() 打印一行中文原因、返回非零码。"""
    def _raise(_app):
        raise db_module.BootstrapError(
            "数据库自检未通过：PRAGMA journal_mode 实际为 delete，期望 wal"
        )

    monkeypatch.setattr(db_module, "bootstrap_db", _raise)
    assert app_module.main() == 1
    out = capsys.readouterr().out
    assert out.strip().count("\n") == 0
    assert out.startswith("启动失败：")


def test_port_occupied_exits_nonzero_with_one_line_reason(monkeypatch, capsys):
    """AC-1.1.4：端口被占用 → 非零退出 + 一行可读中文原因，不静默挂起。"""
    class FakeApp:
        def run(self, *args, **kwargs):
            raise OSError("Only one usage of each socket address")

    monkeypatch.setattr(app_module, "create_app", lambda: FakeApp())
    monkeypatch.setattr(db_module, "bootstrap_db", lambda _app: None)
    assert app_module.main() == 1
    out = capsys.readouterr().out
    assert out.strip().count("\n") == 0
    assert "启动失败" in out and "占用" in out


def test_delete_db_file_restarts_from_seed_state(app):
    """AC-1.1.5：删除 .sqlite 并重启 → 回到初始种子状态，无残留数据。"""
    with _fresh_db(app) as db:
        db.execute(
            "INSERT INTO loans (item_id, user_id, borrowed_at, due_at)"
            " VALUES (1, 1, '2026-11-09 10:00:00', '2026-11-16 10:00:00')"
        )
    db_file = Path(db_module.DB_PATH)
    assert db_file.exists()
    db_file.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(db_file) + suffix).unlink(missing_ok=True)
    db_module.bootstrap_db(app)
    with _fresh_db(app) as db2:
        assert db2.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 0
        assert db2.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        assert db2.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 6


def test_no_build_chain_and_dependency_floors():
    """AC-1.1.6：无前端构建产物；requirements 含两条硬性下限（AR-9）。"""
    for banned in ("package.json", "node_modules", "dist"):
        assert not (REPO_ROOT / banned).exists()
    assert not list(REPO_ROOT.glob("vite.config.*"))
    req = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"(?im)^Flask>=3\.1\.0\s*$", req)
    assert re.search(r"(?im)^Werkzeug>=3\.1\.0\s*$", req)


def test_partial_unique_index_shape(app):
    """AC-1.1.7：ux_loans_active_item partial=1，索引列仅 item_id（D-018）。"""
    with _fresh_db(app) as db:
        index_rows = db.execute("PRAGMA index_list('loans')").fetchall()
        target = [r for r in index_rows if r["name"] == "ux_loans_active_item"]
        assert len(target) == 1
        assert target[0]["partial"] == 1
        cols = [
            r["name"]
            for r in db.execute("PRAGMA index_info('ux_loans_active_item')")
        ]
        assert cols == ["item_id"]


def test_check_constraint_rejects_borrowed_status(app):
    """AC-1.1.7：直接 UPDATE items SET status='borrowed' 被 CHECK 拒绝（AR-4）。"""
    with _fresh_db(app) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE items SET status = 'borrowed' WHERE id = 1")


def test_sqlite_connect_only_in_get_db():
    """AC-1.1.8 / PC-2：建库调用只命中 db.py::get_db 一处（唯一连接入口）。"""
    needle = "sqlite3" ".connect("  # 运行期拼接，避免本测试文件自匹配
    skip_dirs = {".git", "node_modules", ".claude", "__pycache__", "_bmad", "testtmp", "tests"}
    hits = []
    for py in REPO_ROOT.rglob("*.py"):
        rel = py.relative_to(REPO_ROOT)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if needle in py.read_text(encoding="utf-8"):
            hits.append(str(rel))
    assert hits == [str(Path("db.py"))]
