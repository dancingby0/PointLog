"""档案级多行文本（每日日常 / 点数标准）。

v2.7 修正：这两个是**独立**的纯文本，之前的"日常项清单（时段+点数）"结构已废弃。

- 存 data.json 的 ``daily_routine`` / ``point_rules`` 两个字符串字段；
- 保留换行（用户用它排版），去掉行尾空白与首尾空行；
- 老数据缺字段 → 读出空串，无需迁移。
"""

MAX_TEXT = 4000          # 够写满一屏；同时防止把 data.json 撑爆


def normalize_text(raw) -> str:
    """把各种写法规范化为多行文本；非法/超长按规则裁剪。"""
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):          # 容错：万一被存成数组
        raw = "\n".join(str(x) for x in raw if str(x).strip())
    text = str(raw).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)[:MAX_TEXT]


def text_stats(text: str) -> dict:
    """文本概要（界面显示"共 N 行 / M 字"）。"""
    clean = normalize_text(text)
    lines = [line for line in clean.split("\n") if line.strip()]
    return {"lines": len(lines), "chars": len(clean.replace("\n", "")), "empty": not lines}
