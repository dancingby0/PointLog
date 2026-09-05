"""数据导出 API：把当前档案完整导出为 JSON 文件。"""

import datetime as dt
import json
from urllib.parse import quote

from flask import Blueprint, Response

import config
import data
from utils import date_of

bp = Blueprint("export", __name__, url_prefix="/api")


@bp.get("/export")
def export_data():
    """导出当前档案全部数据（与 data.json 同构，便于统计/备份）。

    返回 JSON 附件，文件名：pointlog-<档案>-<YYYY-MM-DD>.json
    """
    profile = config.CURRENT_PROFILE
    payload = data.load(profile)

    today = date_of(dt.datetime.now().astimezone())
    filename = f"pointlog-{profile}-{today.isoformat()}.json"

    body = json.dumps(payload, ensure_ascii=False, indent=2)
    resp = Response(body, mimetype="application/json")
    # filename* 支持中文档案名
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return resp