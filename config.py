"""全局配置（v1 阶段）。

路由层通过 `import config` 并读取 `config.CURRENT_PROFILE`（动态，
切换档案会实时生效）。多档案切换见 routes/profiles.py。
"""

# 当前档案名（随 /api/profiles/switch 动态修改）
CURRENT_PROFILE = "default"