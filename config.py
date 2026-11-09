"""全局常量与错误码定义（PC-9、PC-14）——错误码与中文文案的唯一真相。

9 个错误码口径见 decision-log D-023（O-1 订正：ADR 原「8 个」为转述笔误，
PRD §4 逐条可数出 9 个）。
"""

BORROW_LIMIT = 3
BORROW_DAYS = 7
MAX_NAME_LEN = 50
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 错误码 -> 中文提示；每码只对应一种失败原因，两处刻意合并见 PRD §4 错误约定
ERROR_MESSAGES = {
    "INVALID_CREDENTIALS": "学号或密码不正确",          # 401
    "FORBIDDEN": "仅管理员可访问",                      # 403
    "RESOURCE_NOT_FOUND": "资源不存在或不可见",          # 404
    "ALREADY_BORROWED": "该物品已被借出",               # 409
    "ITEM_UNAVAILABLE": "该物品已停用",                 # 409
    "LIMIT_EXCEEDED": f"你已借满 {BORROW_LIMIT} 件，请先归还",  # 409
    "ALREADY_RETURNED": "该记录已归还",                 # 409
    "ITEM_IN_BORROW": "该物品在借中，无法删除",          # 409
    "INVALID_INPUT": "输入不合法",                      # 400
}


class BizError(Exception):
    """业务失败：一律映射为真实 4xx + 已定义错误码（PC-9，禁止 200+错误文案）。"""

    def __init__(self, status_code, error_code):
        self.status_code = status_code
        self.error_code = error_code
        self.message = ERROR_MESSAGES[error_code]
        super().__init__(f"{status_code} {error_code}: {self.message}")
