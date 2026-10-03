"""全局配置。

路由层通过 `import config` 读取当前账号与档案（动态）。
- CURRENT_ACCOUNT：当前本地账号（v2.3），初始为空，由账号 API 设置。
- CURRENT_PROFILE：当前档案（账号内），随 /api/profiles/switch 修改。
- EXPORTS_DIR：导出文件默认落盘目录（不入版本库，见 .gitignore）。
"""

from pathlib import Path

# 当前本地账号名（v2.3；初始为空 = 未登录，账号 API 会设置）
CURRENT_ACCOUNT = ""

# 当前档案名（账号内；随 /api/profiles/switch 动态修改）
CURRENT_PROFILE = "default"

# 免输窗口：某账号解锁后 now < UNLOCKED_UNTIL 则重进该账号免输（服务进程内存）。
UNLOCKED_ACCOUNT = ""   # 免输窗口所属账号
UNLOCKED_UNTIL = 0.0    # 窗口截止 epoch 秒；服务重启清零

# 自动登录抑制：用户主动登出后置 True → 本次进程内不再自动登录（停在账号选择页），
# 服务重启重置为 False → 下次启动才自动登录。
AUTO_LOGIN_SUPPRESSED = False

# 导出目录：资产 JSON 导出默认写到 <项目根>/exports/（测试会指到临时目录）
EXPORTS_DIR = Path(__file__).resolve().parent / "exports"