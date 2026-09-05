"""路由层：集中注册所有 Blueprint。

分层说明：
- routes/pages.py    页面路由
- routes/entries.py  打卡记录 API
- routes/days.py     日期总览与贡献日历 API
- routes/notes.py    每日感想 API
- routes/memos.py    备忘录 + 置顶主目标 API
- routes/profiles.py 本地档案 + PIN 锁 API
- routes/export.py   数据导出 API
"""

from . import days, entries, export, memos, notes, pages, profiles


def register_blueprints(app):
    app.register_blueprint(pages.bp)
    app.register_blueprint(entries.bp)
    app.register_blueprint(days.bp)
    app.register_blueprint(notes.bp)
    app.register_blueprint(memos.bp)
    app.register_blueprint(profiles.bp)
    app.register_blueprint(export.bp)