"""页面渲染探针（Story 3.4 新增）：把列表页解析成「物品名 → 单元格」。

三种列表的表格结构不同，但断言方式一致：
- 学生列表 `items.html`、管理列表 `admin_items.html`：第 3 列（index 2）是展示态；
- 我的借阅 `my_loans.html`：第 4 列（index 3）是借阅态。

解析本身带一条断言：同一物品在一页里出现两次即失败。LEFT JOIN 若因多条
未归还记录把行数翻倍，「状态 ⇔ 未归还计数」的对应关系就断了——这属于
NFR-1.4 要禁止的中间态之一，必须让它当场失败而不是被后续断言掩盖。

本文件是测试脚手架（非产品代码），不参与 PC-1 的分层判定。
"""

import re

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

STATE_COLUMN_ITEMS = 2
STATE_COLUMN_MY_LOANS = 3


def text_of(fragment):
    """去掉标签与多余空白，只留可见文本（按钮与表单也在单元格内，一并剥掉）。"""
    return " ".join(_TAG_RE.sub(" ", fragment).split())


def table_rows(html):
    """返回 [(物品名, [单元格文本...], 行 HTML)]；页面没有表格时返回空列表。"""
    if "<tbody>" not in html:
        return []
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    rows = []
    for row_html in _ROW_RE.findall(body):
        cells = [text_of(cell) for cell in _CELL_RE.findall(row_html)]
        if not cells:
            continue
        rows.append((cells[0], cells, row_html))
    return rows


def rows_by_name(html):
    """物品名 → (单元格文本, 行 HTML)；同一名称出现两行即断言失败。"""
    result = {}
    for name, cells, row_html in table_rows(html):
        assert name not in result, f"页面里「{name}」出现了两行"
        result[name] = (cells, row_html)
    return result


def names(html):
    return list(rows_by_name(html))


def state_map(html, state_column=STATE_COLUMN_ITEMS):
    """物品名 → 该页展示的状态文案（可借 / 在借 / 已停用 / 已逾期 N 天）。"""
    return {
        name: cells[state_column]
        for name, (cells, _row_html) in rows_by_name(html).items()
    }


def row_of(html, name):
    """取指定物品的 (单元格文本, 行 HTML)；不存在即断言失败。"""
    rows = rows_by_name(html)
    assert name in rows, f"页面里没有「{name}」这一行"
    return rows[name]


def state_of(html, name, state_column=STATE_COLUMN_ITEMS):
    cells, _row_html = row_of(html, name)
    return cells[state_column]
