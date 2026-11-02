"""标签池 API：日记标签池（档案级）+ 资产标签池（个人级）。

约定：
- 记录里存标签文本；标签池只是快捷填写词库，**删除池中标签不影响历史记录**；
- 支持改名（v2.9）：把池里的 A 改成 B。可选 ``cascade=true`` 时，把历史记录里的 A
  也一并改成 B（打卡的 category、流水的 tags、日常/备忘文本里的独立词不动）。
- v2.9 起日记标签池**默认不再塞任何预置标签**：池里有什么完全由用户决定。
"""

from flask import Blueprint, jsonify, request

import config
import data

bp = Blueprint("tags", __name__, url_prefix="/api/tags")

MAX_TAG_LEN = 20


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


def _rename_in_entries(profile: str, old: str, new: str) -> int:
    """把该档案里所有打卡记录的旧类别改成新类别（多选类别逐项替换）。"""
    d = data.load(profile)
    changed = 0
    for entry in d.get("entries", []):
        cats = entry.get("category")
        if isinstance(cats, list) and old in cats:
            replaced = []
            for item in cats:
                text = new if str(item).strip() == old else item
                if text not in replaced:
                    replaced.append(text)
            entry["category"] = replaced
            changed += 1
        elif isinstance(cats, str) and cats.strip() == old:
            entry["category"] = [new]
            changed += 1
    if changed:
        data.save(profile, d)
    return changed


def _add(tags: list, tag: str) -> tuple[list, str | None]:
    if not tag:
        return tags, "标签不能为空"
    if len(tag) > MAX_TAG_LEN:
        return tags, f"标签过长（最多 {MAX_TAG_LEN} 字）"
    if tag in tags:
        return tags, None
    tags.append(tag)
    return tags, None


@bp.get("/diary")
def list_diary_tags():
    """当前档案的日记标签池。"""
    return jsonify({"tags": sorted(_diary_tags()), "scope": "diary"})


@bp.post("/diary")
def add_diary_tag():
    body = request.get_json(silent=True) or {}
    tags, err = _add(_diary_tags(), _clean_tag(body.get("tag")))
    if err:
        return jsonify({"error": err}), 400
    _save_diary_tags(tags)
    return jsonify({"tags": sorted(tags), "scope": "diary"})


@bp.put("/diary")
def rename_diary_tag():
    """改名：{"from": "旧", "to": "新", "cascade": false}。

    cascade=true 时把该档案历史打卡记录里的旧类别一并改成新名称。
    """
    body = request.get_json(silent=True) or {}
    old = _clean_tag(body.get("from"))
    new = _clean_tag(body.get("to"))
    tags = _diary_tags()
    if old not in tags:
        return jsonify({"error": "标签不存在"}), 404
    if not new:
        return jsonify({"error": "新标签不能为空"}), 400
    if len(new) > MAX_TAG_LEN:
        return jsonify({"error": f"标签过长（最多 {MAX_TAG_LEN} 字）"}), 400
    tags = [new if t == old else t for t in tags]
    deduped = []
    for t in tags:                      # 改名后可能与已有标签撞名 → 合并去重
        if t not in deduped:
            deduped.append(t)
    _save_diary_tags(deduped)
    changed = _rename_in_entries(config.CURRENT_PROFILE, old, new) \
        if body.get("cascade") else 0
    return jsonify({"tags": sorted(deduped), "scope": "diary", "entries_changed": changed})


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
    tags, err = _add(_asset_tags(), _clean_tag(body.get("tag")))
    if err:
        return jsonify({"error": err}), 400
    _save_asset_tags(tags)
    return jsonify({"tags": sorted(tags), "scope": "asset"})


@bp.put("/asset")
def rename_asset_tag():
    """改名：{"from": "旧", "to": "新", "cascade": false}；cascade 时同步历史流水的标签。"""
    body = request.get_json(silent=True) or {}
    old = _clean_tag(body.get("from"))
    new = _clean_tag(body.get("to"))
    tags = _asset_tags()
    if old not in tags:
        return jsonify({"error": "标签不存在"}), 404
    if not new:
        return jsonify({"error": "新标签不能为空"}), 400
    if len(new) > MAX_TAG_LEN:
        return jsonify({"error": f"标签过长（最多 {MAX_TAG_LEN} 字）"}), 400
    deduped = []
    for t in [new if t == old else t for t in tags]:
        if t not in deduped:
            deduped.append(t)
    _save_asset_tags(deduped)

    changed = 0
    if body.get("cascade"):
        g = data.load_global()
        for tx in g.get("txs", []):
            ttags = tx.get("tags")
            if isinstance(ttags, list) and old in ttags:
                replaced = []
                for item in ttags:
                    text = new if str(item).strip() == old else item
                    if text not in replaced:
                        replaced.append(text)
                tx["tags"] = replaced
                changed += 1
        if changed:
            data.save_global(g)
    return jsonify({"tags": sorted(deduped), "scope": "asset", "txs_changed": changed})


@bp.delete("/asset")
def delete_asset_tag():
    tag = _clean_tag(request.args.get("tag"))
    tags = _asset_tags()
    if tag not in tags:
        return jsonify({"error": "标签不存在"}), 404
    tags.remove(tag)
    _save_asset_tags(tags)
    return jsonify({"tags": sorted(tags), "scope": "asset"})