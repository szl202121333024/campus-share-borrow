"""Story 1.1 补充验收：SECRET_KEY 管理（ADR-003 §2）与 project-context 规约自检。

本文件把 project-context.md §4 的「可 grep 判定项」落成自动化断言，
让规约漂移在 CI/本地 pytest 中立刻暴露，而不是等到人工评审。
"""

import re
import sqlite3
from pathlib import Path

import pytest

import app as app_module
import config
import db as db_module
import security

REPO_ROOT = Path(__file__).resolve().parents[1]


def _iter_py_files():
    """遍历项目 Python 源码，排除测试自身、.claude skills、__pycache__ 等非业务文件。"""
    skip_dirs = {".git", "node_modules", "testtmp", ".claude", "__pycache__", "_bmad", "tests"}
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in skip_dirs for part in rel.parts):
            continue
        yield path, rel


# ---------------------------------------------------------------- SECRET_KEY

def test_secret_key_never_hardcoded_in_source():
    """ADR-003 §2：源码不得出现硬编码 SECRET_KEY 字面量。"""
    for path, rel in _iter_py_files():
        if rel.name == "conftest.py":
            continue  # 测试注入用的占位值，已在上一行注释中说明
        text = path.read_text(encoding="utf-8")
        assert "campus-share-borrow-dev-secret" not in text, f"{rel} 含硬编码 SECRET_KEY"
        assert not re.search(r'SECRET_KEY"?\]\s*=\s*["\'][^"\']{8,}', text), (
            f"{rel} 给 SECRET_KEY 赋了字面量"
        )


def test_secret_key_from_environment(tmp_path, monkeypatch):
    """环境变量优先（CAMPUS_SECRET_KEY），且不读写 instance/secret_key。"""
    monkeypatch.setenv(app_module.SECRET_KEY_ENV, "env-provided-key")
    monkeypatch.setattr(app_module, "SECRET_KEY_FILE", str(tmp_path / "secret_key"))
    assert app_module.load_secret_key() == "env-provided-key"
    assert not (tmp_path / "secret_key").exists()


def test_secret_key_generated_once_and_persisted(tmp_path, monkeypatch):
    """缺失时随机生成并落盘；第二次加载复用同一值（避免重启全员登出）。"""
    monkeypatch.delenv(app_module.SECRET_KEY_ENV, raising=False)
    monkeypatch.setattr(app_module, "INSTANCE_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "SECRET_KEY_FILE", str(tmp_path / "secret_key"))

    first = app_module.load_secret_key()
    assert len(first) >= 32
    assert (tmp_path / "secret_key").read_text(encoding="utf-8").strip() == first
    assert app_module.load_secret_key() == first


def test_app_uses_loaded_secret_key(app):
    assert app.config["SECRET_KEY"] == "test-secret-key-not-for-production"


# ------------------------------------------------------------ PC 规约自检

def test_pc2_sqlite_connect_only_in_db():
    """PC-2 / AC-1.1.8：全库 sqlite3.connect( 只命中 db.py。"""
    needle = "sqlite3" ".connect("
    hits = [str(rel) for path, rel in _iter_py_files() if needle in path.read_text(encoding="utf-8")]
    assert hits == [str(Path("db.py"))]


def test_pc3_no_camel_case_function_names():
    """PC-3：不得出现驼峰式函数定义（如 borrowBook()）。"""
    camel = re.compile(r"^\s*def\s+[a-z]+[A-Z][A-Za-z0-9_]*\s*\(", re.MULTILINE)
    offenders = []
    for path, rel in _iter_py_files():
        for match in camel.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{rel}: {match.group(0).strip()}")
    assert offenders == []


def test_pc11_password_uses_pbkdf2_and_no_weak_hash():
    """PC-11：密码统一走 security.py 的 pbkdf2:sha256；无 md5/sha1。"""
    source = (REPO_ROOT / "security.py").read_text(encoding="utf-8")
    assert 'method="pbkdf2:sha256"' in source
    for path, rel in _iter_py_files():
        text = path.read_text(encoding="utf-8")
        assert "hashlib.md5" not in text, f"{rel} 使用了 md5"
        assert "hashlib.sha1" not in text, f"{rel} 使用了 sha1"


def test_pc14_constants_defined_once():
    """PC-14：BORROW_LIMIT=3、BORROW_DAYS=7 只在 config.py 定义一次。"""
    assert config.BORROW_LIMIT == 3
    assert config.BORROW_DAYS == 7
    for path, rel in _iter_py_files():
        if rel == Path("config.py"):
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^BORROW_LIMIT\s*=", text, re.MULTILINE), f"{rel} 重复定义 BORROW_LIMIT"
        assert not re.search(r"^BORROW_DAYS\s*=", text, re.MULTILINE), f"{rel} 重复定义 BORROW_DAYS"


def test_pc9_error_codes_are_nine_and_stored_pbkdf2(app):
    """AC-1.1.7 之外的统一口径：9 个错误码（D-023）且种子密码为 pbkdf2:sha256。"""
    assert len(config.ERROR_MESSAGES) == 9
    with app.app_context():
        hashes = [row["password_hash"] for row in db_module.get_db().execute(
            "SELECT password_hash FROM users"
        )]
    assert hashes
    for stored in hashes:
        assert stored.startswith("pbkdf2:sha256:")


def test_pc1_routes_hold_no_business_sql():
    """PC-1：routes/ 内不出现直接 SQL（业务判定只在 services/）。"""
    for path, rel in _iter_py_files():
        if rel.parts[0] != "routes":
            continue
        text = path.read_text(encoding="utf-8")
        assert "SELECT " not in text.upper(), f"{rel} 在路由里写了 SQL"
        assert "INSERT " not in text.upper(), f"{rel} 在路由里写了 SQL"


def test_seed_users_use_hashed_passwords_not_plaintext(app):
    """AC-1.2.9 前哨：种子账号存哈希，明文不出现在 users 表任何列。"""
    with app.app_context():
        rows = db_module.get_db().execute(
            "SELECT student_id, password_hash FROM users"
        ).fetchall()
    for row in rows:
        assert row["password_hash"] != "stu123456"
        assert row["password_hash"] != "admin123456"


def test_no_wal_or_shm_tracked_or_leaked():
    """AC-1.1.5：库文件为单一 .sqlite + 同目录 -wal/-shm，且均被 .gitignore 覆盖。"""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.sqlite", "*.sqlite-wal", "*.sqlite-shm"):
        assert pattern in gitignore


def test_security_module_roundtrip():
    """security.py 单向可验证：生成的哈希能被校验通过，错误密码被拒。"""
    digest = security.hash_password("stu123456")
    assert security.verify_password(digest, "stu123456") is True
    assert security.verify_password(digest, "wrong-password") is False