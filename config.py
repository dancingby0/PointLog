"""全局配置。

路由层通过 `import config` 读取当前账号与档案（动态）。
- CURRENT_ACCOUNT：当前本地账号（v2.3），初始为空，由账号 API 设置。
- CURRENT_PROFILE：当前档案（账号内），随 /api/profiles/switch 修改。
"""

# 当前本地账号名（v2.3；初始为空 = 未登录，账号 API 会设置）
CURRENT_ACCOUNT = ""

# 当前档案名（账号内；随 /api/profiles/switch 动态修改）
CURRENT_PROFILE = "default"

# 免输窗口：某账号解锁后 now < UNLOCKED_UNTIL 则重进该账号免输（服务进程内存）。
UNLOCKED_ACCOUNT = ""   # 免输窗口所属账号
UNLOCKED_UNTIL = 0.0    # 窗口截止 epoch 秒；服务重启清零