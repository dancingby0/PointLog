"""资产 API：账户、收支、转账、余额校准（个人级/全局共享）。

金额一律以"分"（整数）存储，展示层换算元，避免浮点误差。
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import data
from utils import parse_ts

bp = Blueprint("assets", __name__, url_prefix="/api")


def _yuan_to_fen(x) -> int:
    """人民币元 → 分（整数）；支持小数，两位内。"""
    try:
        return int(round(float(x) * 100))
    except (TypeError, ValueError):
        raise ValueError("金额格式不正确")


def _fen_to_yuan(fen: int) -> float:
    return round(fen / 100, 2)


def _require_account(g: dict, account_id: str) -> dict:
    acc = next((a for a in g["accounts"] if a["id"] == account_id), None)
    if acc is None:
        raise KeyError("账户不存在")
    return acc


def _acct_id() -> str:
    return data.new_id()


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat()


@bp.get("/accounts")
def list_accounts():
    """返回账户列表 + 个人总资产。"""
    g = data.load_global()
    total_fen = 0
    out = []
    for a in g["accounts"]:
        bal = int(a.get("balance_fen", 0))
        total_fen += bal
        out.append({
            "id": a["id"],
            "name": a["name"],
            "kind": a.get("kind", "asset"),
            "balance": _fen_to_yuan(bal),
        })
    return jsonify({"accounts": out, "total": _fen_to_yuan(total_fen)})


@bp.post("/accounts")
def create_account():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not name:
        return jsonify({"error": "账户名不能为空"}), 400
    if len(name) > 30:
        return jsonify({"error": "账户名过长（最多30字）"}), 400
    kind = body.get("kind", "asset")
    if kind not in ("asset", "liability"):
        return jsonify({"error": "kind 应为 asset 或 liability"}), 400
    try:
        init_bal = _yuan_to_fen(body.get("balance", 0))
    except ValueError:
        return jsonify({"error": "初始金额格式不正确"}), 400

    account = {
        "id": _acct_id(),
        "name": name,
        "kind": kind,
        "balance_fen": init_bal,
    }
    g = data.load_global()
    g["accounts"].append(account)
    data.save_global(g)
    return jsonify({
        "id": account["id"], "name": name, "kind": kind,
        "balance": _fen_to_yuan(init_bal),
    }), 201


@bp.put("/accounts/<account_id>")
def rename_account(account_id: str):
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not name:
        return jsonify({"error": "账户名不能为空"}), 400
    g = data.load_global()
    try:
        acc = _require_account(g, account_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    acc["name"] = name
    data.save_global(g)
    return jsonify({"id": acc["id"], "name": acc["name"], "kind": acc["kind"],
                    "balance": _fen_to_yuan(acc["balance_fen"])})


@bp.delete("/accounts/<account_id>")
def delete_account(account_id: str):
    g = data.load_global()
    if not any(a["id"] == account_id for a in g["accounts"]):
        return jsonify({"error": "账户不存在"}), 404
    # 该账户流水一并删除（删除前提示不可恢复由前端负责）
    g["accounts"] = [a for a in g["accounts"] if a["id"] != account_id]
    g["txs"] = [t for t in g["txs"]
                if t.get("account_id") != account_id
                and t.get("from_account") != account_id
                and t.get("to_account") != account_id]
    data.save_global(g)
    return jsonify({"ok": True})


@bp.post("/accounts/<account_id>/adjust")
def adjust_balance(account_id: str):
    """手动校准余额：直接把账户余额设为给定值（重置基准，不理会与流水的差值）。"""
    body = request.get_json(silent=True) or {}
    try:
        new_bal = _yuan_to_fen(body.get("balance"))
    except ValueError:
        return jsonify({"error": "金额格式不正确"}), 400
    ts_iso = body.get("ts") or _now_iso()
    try:
        # 统一存为本地时区、秒级 ISO（naive 视为本地时间），与既有 +08:00 数据同构
        ts_iso = parse_ts(ts_iso).isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return jsonify({"error": "时间格式不正确"}), 400
    note = str(body.get("note", "")).strip()

    g = data.load_global()
    try:
        acc = _require_account(g, account_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404

    old_fen = acc["balance_fen"]
    acc["balance_fen"] = new_bal

    # 校准也留痕：type=adjust，记录新旧值
    g["txs"].append({
        "id": _acct_id(),
        "type": "adjust",
        "account_id": account_id,
        "amount_fen": new_bal - old_fen,   # 差值（可为负/正），仅作说明
        "balance_after_fen": new_bal,
        "note": note or "手动校准余额",
        "ts": ts_iso,
    })
    data.save_global(g)
    return jsonify({"id": acc["id"], "name": acc["name"], "kind": acc["kind"],
                    "balance": _fen_to_yuan(new_bal)})


def _csv_ids(value) -> list:
    """把 "a,b,c" 解析为去空列表（多渠道/多类型参数）。"""
    return [x.strip() for x in (value or "").split(",") if x.strip()]


@bp.get("/transactions")
def list_transactions():
    """流水列表（新→旧）：支持筛选与分页。

    查询参数：
      account_id    单账户过滤（兼容旧接口）
      channels      渠道多选：账户 id，逗号分隔（转账任一端匹配即算）
      types         类型多选：expense/income/transfer/adjust，逗号分隔
      tags          标签多选：命中任一标签即算（逗号分隔）
      from / to     发生日期区间 YYYY-MM-DD（含端点，按本地日期）
      page/page_size 页码（缺省则不分页、返回全部）
    返回 {transactions, total, page, page_size, available_tags}
    """
    g = data.load_global()
    account_id = (request.args.get("account_id") or "").strip()
    channels = _csv_ids(request.args.get("channels"))
    types = _csv_ids(request.args.get("types"))
    tags = _csv_ids(request.args.get("tags"))
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()

    try:
        d_from = dt.date.fromisoformat(date_from) if date_from else None
        d_to = dt.date.fromisoformat(date_to) if date_to else None
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    if d_from and d_to and d_from > d_to:
        return jsonify({"error": "起始日期不能晚于结束日期"}), 400

    rows = []
    for t in g["txs"]:
        if account_id and not (
            t.get("account_id") == account_id
            or t.get("from_account") == account_id
            or t.get("to_account") == account_id
        ):
            continue
        if channels:
            involved = {t.get("account_id"), t.get("from_account"), t.get("to_account")}
            involved.discard(None)
            if not (involved & set(channels)):
                continue
        if types and t.get("type") not in types:
            continue
        if tags and not (set(t.get("tags") or []) & set(tags)):
            continue
        if d_from or d_to:
            try:
                day = parse_ts(t.get("ts")).astimezone().date()
            except (ValueError, TypeError):
                continue
            if d_from and day < d_from:
                continue
            if d_to and day > d_to:
                continue
        rows.append(_serialize_tx(t))

    # 新→旧；同秒多笔时以记录 id（毫秒，越晚越大）为次级排序
    rows.sort(key=lambda t: (t["ts"], str(t.get("id") or "")), reverse=True)
    total = len(rows)

    page_raw = request.args.get("page")
    if page_raw:
        try:
            page = max(1, int(page_raw))
            size = int(request.args.get("page_size") or 20)
        except ValueError:
            return jsonify({"error": "分页参数不正确"}), 400
        size = max(1, min(size, 200))
        start = (page - 1) * size
        items = rows[start:start + size]
    else:
        page, size, items = 1, total, rows

    # 可供筛选的标签集合（全部流水出现过的标签，不受当前筛选影响）
    available_tags = sorted({tg for t in g["txs"] for tg in (t.get("tags") or []) if tg})

    return jsonify({
        "transactions": items,
        "total": total,
        "page": page,
        "page_size": size,
        "available_tags": available_tags,
    })


def _serialize_tx(t: dict) -> dict:
    amount_fen = t.get("amount_fen", 0)
    return {
        "id": t.get("id"),
        "type": t.get("type"),                     # expense | income | transfer | adjust
        "account_id": t.get("account_id"),
        "from_account": t.get("from_account"),
        "to_account": t.get("to_account"),
        "amount": _fen_to_yuan(amount_fen),
        "note": t.get("note", ""),
        "tags": t.get("tags", []),
        "ts": t.get("ts"),
    }


@bp.post("/transactions")
def create_transaction():
    """记一笔：expense/income 单账户；transfer 双账户。自动同步余额。"""
    body = request.get_json(silent=True) or {}
    tx_type = body.get("type")
    if tx_type not in ("expense", "income", "transfer"):
        return jsonify({"error": "type 应为 expense/income/transfer"}), 400

    try:
        amount_fen = _yuan_to_fen(body.get("amount"))
    except ValueError:
        return jsonify({"error": "金额格式不正确"}), 400
    if amount_fen <= 0:
        return jsonify({"error": "金额必须大于 0"}), 400

    ts_iso = body.get("ts") or _now_iso()
    try:
        # 统一存为本地时区、秒级 ISO（naive 视为本地时间），与既有 +08:00 数据同构
        ts_iso = parse_ts(ts_iso).isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return jsonify({"error": "时间格式不正确"}), 400
    note = str(body.get("note", "")).strip()
    tags = body.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    tags = [str(t).strip() for t in tags if str(t).strip()]

    g = data.load_global()
    tx = {
        "id": _acct_id(),
        "type": tx_type,
        "note": note,
        "tags": tags,
        "ts": ts_iso,
    }

    if tx_type == "transfer":
        from_id = str(body.get("from", ""))
        to_id = str(body.get("to", ""))
        if not from_id or not to_id or from_id == to_id:
            return jsonify({"error": "转账需选择两个不同账户"}), 400
        try:
            fa = _require_account(g, from_id)
            ta = _require_account(g, to_id)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        fa["balance_fen"] -= amount_fen
        ta["balance_fen"] += amount_fen
        tx["from_account"] = from_id
        tx["to_account"] = to_id
        tx["amount_fen"] = amount_fen
    else:
        account_id = str(body.get("account_id", ""))
        try:
            acc = _require_account(g, account_id)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        # 支出从余额减，收入向余额加
        if tx_type == "expense":
            acc["balance_fen"] -= amount_fen
        else:
            acc["balance_fen"] += amount_fen
        tx["account_id"] = account_id
        tx["amount_fen"] = amount_fen

    g["txs"].append(tx)
    data.save_global(g)
    return jsonify(_serialize_tx(tx)), 201


@bp.put("/transactions/<tx_id>")
def update_transaction(tx_id: str):
    """编辑流水：允许修改发生时间 / 备注 / 标签。

    金额、账户、类型不可直接改（改动会牵动余额历史口径）；
    如需调整请删除后重记，或用"校准"直接修正余额。
    """
    g = data.load_global()
    tx = next((t for t in g["txs"] if t.get("id") == tx_id), None)
    if tx is None:
        return jsonify({"error": "流水不存在"}), 404
    if tx.get("type") == "adjust":
        return jsonify({"error": "校准记录不可编辑"}), 400

    body = request.get_json(silent=True) or {}
    changed = False
    if "ts" in body:
        raw = body.get("ts")
        if not raw:
            return jsonify({"error": "时间不能为空"}), 400
        try:
            # 与新增一致：naive 视为本地，统一存本地秒级 ISO
            ts_iso = parse_ts(raw).isoformat(timespec="seconds")
        except (ValueError, TypeError):
            return jsonify({"error": "时间格式不正确"}), 400
        tx["ts"] = ts_iso
        changed = True
    if "note" in body:
        tx["note"] = str(body.get("note") or "").strip()
        changed = True
    if "tags" in body:
        tags = body.get("tags") or []
        if not isinstance(tags, list):
            tags = [tags]
        tx["tags"] = [str(x).strip() for x in tags if str(x).strip()]
        changed = True
    if not changed:
        return jsonify(_serialize_tx(tx))
    data.save_global(g)
    return jsonify(_serialize_tx(tx))
@bp.delete("/transactions/<tx_id>")
def delete_transaction(tx_id: str):
    """删除流水：同步回滚该笔对账户余额的影响。

    支出 → 余额加回；收入 → 扣回；转账 → 两端还原。
    校准记录不可删（它是余额基准留痕）。删除后余额与剩余流水保持一致；
    若此前存在校准差额，用户可再校准。
    """
    g = data.load_global()
    tx = next((t for t in g["txs"] if t.get("id") == tx_id), None)
    if tx is None:
        return jsonify({"error": "流水不存在"}), 404
    ttype = tx.get("type")
    if ttype == "adjust":
        return jsonify({"error": "校准记录不可删除（保留校准痕迹）"}), 400

    amount_fen = int(tx.get("amount_fen", 0))
    if ttype == "expense":
        acc = next((a for a in g["accounts"] if a["id"] == tx.get("account_id")), None)
        if acc is not None:
            acc["balance_fen"] += amount_fen
    elif ttype == "income":
        acc = next((a for a in g["accounts"] if a["id"] == tx.get("account_id")), None)
        if acc is not None:
            acc["balance_fen"] -= amount_fen
    elif ttype == "transfer":
        fa = next((a for a in g["accounts"] if a["id"] == tx.get("from_account")), None)
        ta = next((a for a in g["accounts"] if a["id"] == tx.get("to_account")), None)
        if fa is not None:
            fa["balance_fen"] += amount_fen
        if ta is not None:
            ta["balance_fen"] -= amount_fen

    g["txs"] = [t for t in g["txs"] if t.get("id") != tx_id]
    data.save_global(g)
    return jsonify({"ok": True})

