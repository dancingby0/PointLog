"""全局配置（v1 阶段）。

各模块通过 `from config import CURRENT_PROFILE` 读取当前档案。
多档案切换在 M6 之前固定为 "default"。
"""

# 当前档案名
CURRENT_PROFILE = "default"