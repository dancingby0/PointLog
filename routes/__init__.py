"""路由层：集中注册所有 Blueprint。

分层说明：
- routes/pages.py    页面路由
- routes/entries.py  打卡记录 API
- routes/days.py     日期总览与贡献日历 API
"""

from . import days, entries, pages


def register_blueprints(app):
    app.register_blueprint(pages.bp)
    app.register_blueprint(entries.bp)
    app.register_blueprint(days.bp)