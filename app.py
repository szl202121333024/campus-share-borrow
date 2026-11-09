"""唯一启动入口（NFR-2、PC-12、PC-15）。

干净机器上 `python app.py` 一次执行即成功：自举建库 + 种子数据 + 断言 PRAGMA + 起服务。
任何启动期失败打印一行中文原因并以非零码退出，不静默挂起（AC-1.1.3、AC-1.1.4）。
"""

import socket

from flask import Flask, redirect, render_template, url_for

import db as db_module
from config import ERROR_MESSAGES, BizError
from db import BootstrapError, close_db

HOST = "127.0.0.1"
PORT = 5000


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "campus-share-borrow-dev-secret"
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
