"""标签池 API：日记标签池（档案级）+ 资产标签池（个人级）。

约定：记录里存标签文本；标签池只是快捷填写词库，删除池中标签不影响历史记录。
"""

from flask import Blueprint, jsonify, request

import config
import data

bp = Blueprint("tags", __name__, url_prefix="/api/tags")


def _clean_tag(raw) -> str:
    """规范化标签文本：去首尾空白、去重时以文本为准。"""
    return str(raw or "").strip()


def _diary_tags() -> list:
    """当前档案的日记标签池。"""
    d = data.load(config.CURRENT_PROFILE)
    tags = d.get("diary_tags", [])
    if not isinstance(tags, list):
        tags = []
    return tags


def _save_diary_tags(tags: list) -> None:
    d = data.load(config.CURRENT_PROFILE)
    d["diary_tags"] = tags
    data.save(config.CURRENT_PROFILE, d)


@bp.get("/diary")
def list_diary_tags():
    """当前档案的日记标签池。"""
    return jsonify({"tags": sorted(_diary_tags()), "scope": "diary"})


@bp.post("/diary")
def add_diary_tag():
    body = request.get_json(silent=True) or {}
    tag = _clean_tag(body.get("tag"))
    if not tag:
        return jsonify({"error": "标签不能为空"}), 400
    if len(tag) > 20:
        return jsonify({"error": "标签过长（最多 20 字）"}), 400
    tags = _diary_tags()
    if tag in tags:
        return jsonify({"tags": sorted(tags), "scope": "diary"})
    tags.append(tag)
    _save_diary_tags(tags)
    return jsonify({"tags": sorted(tags), "scope": "diary"})


@bp.delete("/diary")
def delete_diary_tag():
    tag = _clean_tag(request.args.get("tag"))
    tags = _diary_tags()
    if tag not in tags:
        return jsonify({"error": "标签不存在"}), 404
    tags.remove(tag)
    _save_diary_tags(tags)
    return jsonify({"tags": sorted(tags), "scope": "diary"})


def _asset_tags() -> list:
    g = data.load_global()
    tags = g.get("asset_tags", [])
    if not isinstance(tags, list):
        tags = []
    return tags


def _save_asset_tags(tags: list) -> None:
    g = data.load_global()
    g["asset_tags"] = tags
    data.save_global(g)


@bp.get("/asset")
def list_asset_tags():
    """个人级资产标签池（全局，不随档案变）。"""
    return jsonify({"tags": sorted(_asset_tags()), "scope": "asset"})


@bp.post("/asset")
def add_asset_tag():
    body = request.get_json(silent=True) or {}
    tag = _clean_tag(body.get("tag"))
    if not tag:
        return jsonify({"error": "标签不能为空"}), 400
    if len(tag) > 20:
        return jsonify({"error": "标签过长（最多 20 字）"}), 400
    tags = _asset_tags()
    if tag in tags:
        return jsonify({"tags": sorted(tags), "scope": "asset"})
    tags.append(tag)
    _save_asset_tags(tags)
    return jsonify({"tags": sorted(tags), "scope": "asset"})


@bp.delete("/asset")
def delete_asset_tag():
    tag = _clean_tag(request.args.get("tag"))
    tags = _asset_tags()
    if tag not in tags:
        return jsonify({"error": "标签不存在"}), 404
    tags.remove(tag)
    _save_asset_tags(tags)
    return jsonify({"tags": sorted(tags), "scope": "asset"})