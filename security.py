"""密码哈希唯一入口（PC-11、AR-8）。

Werkzeug 3.x 默认算法为 scrypt，必须显式传 method="pbkdf2:sha256"（ADR-004 §5）。
日志与响应体不得出现明文密码或哈希。
"""

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(plain_password):
    return generate_password_hash(plain_password, method="pbkdf2:sha256")


def verify_password(password_hash, plain_password):
    return check_password_hash(password_hash, plain_password)
