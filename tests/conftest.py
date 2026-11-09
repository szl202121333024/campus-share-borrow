"""pytest 公共夹具：每个用例用独立临时库，走唯一入口 bootstrap_db()。"""

import pytest

import db as db_module
from app import create_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.sqlite"))
    flask_app = create_app()
    db_module.bootstrap_db(flask_app)
    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
