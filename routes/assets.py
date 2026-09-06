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
        parse_ts(ts_iso)
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


@bp.get("/transactions")
def list_transactions():
    """流水列表：?account_id 过滤，默认返回全部（新→旧）。"""
    g = data.load_global()
    account_id = request.args.get("account_id")
    txs = []
    for t in g["txs"]:
        if account_id and not (
            t.get("account_id") == account_id
            or t.get("from_account") == account_id
            or t.get("to_account") == account_id
        ):
            continue
        txs.append(_serialize_tx(t))
    txs.sort(key=lambda t: t["ts"], reverse=True)
    return jsonify({"transactions": txs})


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
        parse_ts(ts_iso)
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
