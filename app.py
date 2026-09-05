"""PointLog 本地服务入口。

运行方式：.venv\\Scripts\\python app.py  →  http://127.0.0.1:5000/

代码分层：
- app.py          入口（构造 Flask 应用 + 启动）
- routes/         路由层（按功能分 Blueprint）
- data.py         数据读写层
- utils.py        通用时间工具
- config.py       全局配置
"""

from flask import Flask

import routes


def create_app() -> Flask:
    app = Flask(__name__)
    routes.register_blueprints(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
