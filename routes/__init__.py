"""路由层：集中注册所有 Blueprint。

分层说明：
- routes/pages.py    页面路由
- routes/entries.py  打卡记录 API
- routes/days.py     日期总览与贡献日历 API
- routes/notes.py    每日感想 API
- routes/memos.py    备忘录 + 置顶主目标 API
- routes/profiles.py 本地档案 API（账号内，无档案锁）
- routes/export.py   数据导出 API
- routes/tags.py     标签池 API（日记档案级 + 资产个人级）
- routes/assets.py   资产 API（账户/收支/转账/余额校准，个人级）
- routes/statistics.py 统计 API（坚持与概况等）
- routes/accounts.py  本地账号 API（v2.3）
- routes/activity.py  活动数据 API（v2.6，从本机 ActivityWatch 拉取桌面活动）
- routes/schedule.py  每日日常 + 点数标准 API（v2.7，档案级，两段独立文本）
- routes/focus.py     专注会话 API（v2.8，桌面计时器上传 + 点数系统统计）
"""

from . import (
    accounts,
    activity,
    assets,
    days,
    entries,
    export,
    focus,
    memos,
    notes,
    pages,
    profiles,
    schedule,
    statistics,
    tags,
)


def register_blueprints(app):
    app.register_blueprint(pages.bp)
    app.register_blueprint(entries.bp)
    app.register_blueprint(days.bp)
    app.register_blueprint(notes.bp)
    app.register_blueprint(memos.bp)
    app.register_blueprint(profiles.bp)
    app.register_blueprint(export.bp)
    app.register_blueprint(tags.bp)
    app.register_blueprint(assets.bp)
    app.register_blueprint(statistics.bp)
    app.register_blueprint(accounts.bp)
    app.register_blueprint(activity.bp)
    app.register_blueprint(schedule.bp)
    app.register_blueprint(focus.bp)