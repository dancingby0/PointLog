from flask import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return "<h1>PointLog 服务已启动 ✅</h1><p>M0 里程碑：Flask 正常运行。</p>"


if __name__ == "__main__":
    # debug=True 便于开发期自动重载与报错页；host 固定 127.0.0.1 保证只有本机能访问
    app.run(host="127.0.0.1", port=5000, debug=True)
