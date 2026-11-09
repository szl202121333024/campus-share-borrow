"""唯一启动入口（NFR-2、PC-12、PC-15）。

干净机器上 `python app.py` 一次执行即成功：自举建库 + 种子数据 + 断言 PRAGMA + 起服务。
任何启动期失败打印一行中文原因并以非零码退出，不静默挂起（AC-1.1.3、AC-1.1.4）。
"""

import os
import secrets
import socket

from flask import Flask, redirect, render_template, url_for

import db as db_module
from config import ERROR_MESSAGES, BizError
from db import BootstrapError, close_db

HOST = "127.0.0.1"
PORT = 5000

# ADR-003 §2：SECRET_KEY 严禁硬编码进仓库。优先级——
# ① 环境变量 CAMPUS_SECRET_KEY；② instance/secret_key（首次启动随机生成，已被 .gitignore 覆盖）。
SECRET_KEY_ENV = "CAMPUS_SECRET_KEY"
INSTANCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
SECRET_KEY_FILE = os.path.join(INSTANCE_DIR, "secret_key")


def load_secret_key():
    """按 ADR-003 §2 取得 SECRET_KEY，绝不回退到源码字面量。

    测试通过环境变量注入固定值以保证可复跑；生产/演示首次启动随机生成并落盘，
    重启后复用同一份，避免「每次重启全员登出」。
    """
    from_env = os.environ.get(SECRET_KEY_ENV)
    if from_env:
        return from_env
    try:
        with open(SECRET_KEY_FILE, encoding="utf-8") as handle:
            stored = handle.read().strip()
        if stored:
            return stored
    except FileNotFoundError:
        pass
    generated = secrets.token_hex(32)
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    with open(SECRET_KEY_FILE, "w", encoding="utf-8") as handle:
        handle.write(generated)
    return generated


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = load_secret_key()
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400
    app.teardown_appcontext(close_db)

    from routes.items import bp as items_bp

    app.register_blueprint(items_bp)

    @app.get("/")
    def index():
        return redirect(url_for("items.items_page"))

    @app.errorhandler(BizError)
    def handle_biz_error(err):
        return (
            render_template("error.html", error_code=err.error_code, message=err.message),
            err.status_code,
            {"Cache-Control": "no-store"},
        )

    @app.errorhandler(404)
    def handle_not_found(_err):
        return (
            render_template(
                "error.html",
                error_code="RESOURCE_NOT_FOUND",
                message=ERROR_MESSAGES["RESOURCE_NOT_FOUND"],
            ),
            404,
            {"Cache-Control": "no-store"},
        )

    return app


def main():
    app = create_app()
    try:
        db_module.bootstrap_db(app)
    except BootstrapError as exc:
        print(f"启动失败：{exc}")
        return 1
    try:
        app.run(host=HOST, port=PORT, threaded=True)
    except OSError as exc:
        if isinstance(exc, socket.timeout):
            print(f"启动失败：网络超时：{exc}")
        else:
            print(f"启动失败：端口 {HOST}:{PORT} 可能被占用：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
