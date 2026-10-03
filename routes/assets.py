"""资产 API：账户、收支、转账、余额校准（个人级/全局共享）。

金额一律以"分"（整数）存储，展示层换算元，避免浮点误差。
"""

import datetime as dt
import json

from flask import Blueprint, jsonify, request

import data
import export_io
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


def _find_account(g: dict, account_id):
    return next((a for a in g["accounts"] if a["id"] == account_id), None)


def _apply_tx_effect(g: dict, tx_type: str, amount_fen: int, ref: dict, sign: int = 1) -> None:
    """应用（sign=1）或撤销（sign=-1）一笔流水对账户余额的影响。

    ref 提供账户引用键：account_id / from_account / to_account。
    账户不存在时跳过（如账户已删除）。
    """
    if tx_type == "expense":
        acc = _find_account(g, ref.get("account_id"))
        if acc is not None:
            acc["balance_fen"] -= sign * amount_fen
    elif tx_type == "income":
        acc = _find_account(g, ref.get("account_id"))
        if acc is not None:
            acc["balance_fen"] += sign * amount_fen
    elif tx_type == "transfer":
        fa = _find_account(g, ref.get("from_account"))
        ta = _find_account(g, ref.get("to_account"))
        if fa is not None:
            fa["balance_fen"] -= sign * amount_fen
        if ta is not None:
            ta["balance_fen"] += sign * amount_fen


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


def _build_balance_map(g: dict) -> dict:
    """{(account_id, tx_id): balance_after_fen}：每笔发生后的账户余额。

    以该账户最近的"校准(adjust)"（balance_after_fen）为锚点，其后的流水逐笔
    应用到每笔之后；锚点之前的流水（已体现在校准值里）不再重复计算。
    无校准锚点的账户/笔 → 该笔无余额（None，前端不显示）。
    """
    by_account = {}
    for t in g["txs"]:
        accs = {t.get("account_id"), t.get("from_account"), t.get("to_account")}
        accs.discard(None)
        for acc in accs:
            by_account.setdefault(acc, []).append((t.get("ts", ""), str(t.get("id", "")), t))

    index = {}
    for acc, items in by_account.items():
        items.sort(key=lambda x: (x[0], x[1]))
        bal = None
        anchored = False
        for _, tid, t in items:
            kind = t.get("type")
            amt = int(t.get("amount_fen", 0))
            if kind == "adjust":
                bal = int(t.get("balance_after_fen", 0))
                anchored = True
            elif not anchored:
                continue
            else:
                if t.get("account_id") == acc:
                    if kind == "expense":
                        bal -= amt
                    elif kind == "income":
                        bal += amt
                if t.get("from_account") == acc:
                    bal -= amt
                if t.get("to_account") == acc:
                    bal += amt
            index[(acc, tid)] = bal
    return index


def _attach_balances(ser: dict, t: dict, bmap: dict) -> None:
    """给序列化流水挂上该笔后的账户余额（无锚点 → null，前端不显示）。"""
    tid = t.get("id")
    if t.get("type") == "transfer":
        fa = bmap.get((t.get("from_account"), tid))
        ta = bmap.get((t.get("to_account"), tid))
        ser["balance_after_from"] = round(fa / 100.0, 2) if fa is not None else None
        ser["balance_after_to"] = round(ta / 100.0, 2) if ta is not None else None
    else:
        ba = bmap.get((t.get("account_id"), tid))
        ser["balance_after"] = round(ba / 100.0, 2) if ba is not None else None


@bp.get("/transactions")
def list_transactions():
    """流水列表（新→旧）：支持筛选与分页。

    查询参数：
      account_id    单账户过滤（兼容旧接口）
      channels      渠道多选：账户 id，逗号分隔（转账任一端匹配即算）
      types         类型多选：expense/income/transfer/adjust，逗号分隔
      tags          标签多选：命中任一标签即算（逗号分隔）
      invert        反选维度：channels/types/tags 中以逗号列出者取反（排除所选项）
      unsettled     1=仅返回"发生日期尚未平账"的流水
      from / to     发生日期区间 YYYY-MM-DD（含端点，按本地日期）
      page/page_size 页码（缺省则不分页、返回全部）
    返回 {transactions, total, page, page_size, available_tags}
    """
    g = data.load_global()
    account_id = (request.args.get("account_id") or "").strip()
    channels = _csv_ids(request.args.get("channels"))
    types = _csv_ids(request.args.get("types"))
    tags = _csv_ids(request.args.get("tags"))
    invert = set(_csv_ids(request.args.get("invert")))
    not_channels = "channels" in invert
    not_types = "types" in invert
    not_tags = "tags" in invert
    unsettled_only = (request.args.get("unsettled") or "").strip() not in ("", "0", "false", "no")
    settled_days = set(g.get("settled_days") or [])
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
            hit = bool(involved & set(channels))
            # 正选：保留命中；反选：保留未命中
            if hit == not_channels:
                continue
        if types:
            hit = t.get("type") in types
            if hit == not_types:
                continue
        if tags:
            hit = bool(set(t.get("tags") or []) & set(tags))
            if hit == not_tags:
                continue
        if d_from or d_to or unsettled_only:
            try:
                day = parse_ts(t.get("ts")).astimezone().date()
            except (ValueError, TypeError):
                continue
            if d_from and day < d_from:
                continue
            if d_to and day > d_to:
                continue
            if unsettled_only and day.isoformat() in settled_days:
                continue
        rows.append((t, _serialize_tx(t)))

    # 新→旧；同秒多笔时以记录 id（毫秒，越晚越大）为次级排序
    rows.sort(key=lambda p: (p[1]["ts"], str(p[1].get("id") or "")), reverse=True)
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
        part = rows[start:start + size]
    else:
        page, size, part = 1, total, rows

    # 每笔"该笔后余额"：以最近校准为锚点逐笔重放（无锚点 → null 不显示）
    balance_map = _build_balance_map(g)
    items = []
    for t, ser in part:
        _attach_balances(ser, t, balance_map)
        items.append(ser)

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


@bp.get("/asset-settlements")
def list_settlements():
    """平账标记：已平账日期 + 有流水但尚未平账的日期（均按本地日期）。"""
    g = data.load_global()
    settled = sorted(set(g.get("settled_days") or []))
    settled_set = set(settled)
    tx_days = set()
    for t in g["txs"]:
        try:
            tx_days.add(parse_ts(t.get("ts")).astimezone().date().isoformat())
        except (ValueError, TypeError):
            continue
    unsettled = sorted(d for d in tx_days if d not in settled_set)
    return jsonify({"settled_days": settled, "unsettled_days": unsettled})


@bp.put("/asset-settlements")
def set_settlement():
    """标记/取消某天已平账。body {day: 'YYYY-MM-DD', settled: true/false}。"""
    body = request.get_json(silent=True) or {}
    day = str(body.get("day") or "").strip()
    if not day:
        return jsonify({"error": "日期不能为空"}), 400
    try:
        dt.date.fromisoformat(day)
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400

    settled_flag = bool(body.get("settled", True))
    g = data.load_global()
    days = set(g.get("settled_days") or [])
    if settled_flag:
        days.add(day)
    else:
        days.discard(day)
    g["settled_days"] = sorted(days)
    data.save_global(g)
    return jsonify({"day": day, "settled": settled_flag, "settled_days": g["settled_days"]})


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
    """编辑流水：类型 / 金额 / 账户 / 标签 / 发生时间 / 备注 均可改。

    实现上等价于"删除原记录 + 重新入账"：先撤销旧记录对余额的影响，
    再按新参数应用影响，做到余额与流水一致；保留原 id（列表不跳变）。
    校准记录不可编辑。
    """
    g = data.load_global()
    tx = next((t for t in g["txs"] if t.get("id") == tx_id), None)
    if tx is None:
        return jsonify({"error": "流水不存在"}), 404
    if tx.get("type") == "adjust":
        return jsonify({"error": "校准记录不可编辑"}), 400

    body = request.get_json(silent=True) or {}
    old = {
        "type": tx.get("type"),
        "amount_fen": int(tx.get("amount_fen", 0)),
        "account_id": tx.get("account_id"),
        "from_account": tx.get("from_account"),
        "to_account": tx.get("to_account"),
    }

    # 目标类型
    new_type = str(body.get("type") or old["type"])
    if new_type not in ("expense", "income", "transfer"):
        return jsonify({"error": "type 应为 expense/income/transfer"}), 400

    # 目标金额（未提供则沿用旧值）
    if "amount" in body:
        try:
            new_amount_fen = _yuan_to_fen(body.get("amount"))
        except ValueError:
            return jsonify({"error": "金额格式不正确"}), 400
    else:
        new_amount_fen = old["amount_fen"]
    if new_amount_fen <= 0:
        return jsonify({"error": "金额必须大于 0"}), 400

    # 目标账户（按新类型校验）
    new_ref = {"type": new_type, "amount_fen": new_amount_fen}
    if new_type == "transfer":
        from_id = str(body.get("from") or old["from_account"] or "")
        to_id = str(body.get("to") or old["to_account"] or "")
        if not from_id or not to_id or from_id == to_id:
            return jsonify({"error": "转账需选择两个不同账户"}), 400
        if _find_account(g, from_id) is None or _find_account(g, to_id) is None:
            return jsonify({"error": "账户不存在"}), 404
        new_ref["from_account"] = from_id
        new_ref["to_account"] = to_id
    else:
        account_id = str(body.get("account_id") or old["account_id"] or "")
        if not account_id:
            return jsonify({"error": "请选择账户"}), 400
        if _find_account(g, account_id) is None:
            return jsonify({"error": "账户不存在"}), 404
        new_ref["account_id"] = account_id

    # 目标时间（未提供则沿用旧值）
    if "ts" in body:
        raw = body.get("ts")
        if not raw:
            return jsonify({"error": "时间不能为空"}), 400
        try:
            # 与新增一致：naive 视为本地，统一存本地秒级 ISO
            new_ts = parse_ts(raw).isoformat(timespec="seconds")
        except (ValueError, TypeError):
            return jsonify({"error": "时间格式不正确"}), 400
    else:
        new_ts = tx.get("ts")

    # 撤销旧影响 → 应用新影响
    _apply_tx_effect(g, old["type"], old["amount_fen"], old, sign=-1)
    _apply_tx_effect(g, new_type, new_amount_fen, new_ref, sign=1)

    # 写回流水字段（清理不再适用的账户键）
    tx["type"] = new_type
    tx["amount_fen"] = new_amount_fen
    tx["ts"] = new_ts
    for key in ("account_id", "from_account", "to_account"):
        tx.pop(key, None)
    if new_type == "transfer":
        tx["from_account"] = new_ref["from_account"]
        tx["to_account"] = new_ref["to_account"]
    else:
        tx["account_id"] = new_ref["account_id"]
    if "note" in body:
        tx["note"] = str(body.get("note") or "").strip()
    if "tags" in body:
        tags = body.get("tags") or []
        if not isinstance(tags, list):
            tags = [tags]
        tx["tags"] = [str(x).strip() for x in tags if str(x).strip()]

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

    _apply_tx_effect(g, ttype, int(tx.get("amount_fen", 0)), tx, sign=-1)
    g["txs"] = [t for t in g["txs"] if t.get("id") != tx_id]
    data.save_global(g)
    return jsonify({"ok": True})


def _tx_ts_key(t: dict):
    """流水排序键：发生时间（时间戳）+ 记录 id，均升序；时间不可解析的排在最前。"""
    try:
        return (parse_ts(t.get("ts")).timestamp(), str(t.get("id") or ""))
    except (ValueError, TypeError):
        return (float("-inf"), str(t.get("id") or ""))


@bp.get("/assets/export")
def export_assets():
    """资产数据导出为 JSON 文件。

    查询参数：
      from / to   发生日期区间 YYYY-MM-DD（含端点，按本地自然日；可省略＝不限）
      download    1/true/yes → 返回附件下载；默认（不传）→ 写入导出目录并返回落盘信息

    导出内容与 assets.json 同构（asset_tags / accounts / txs / settled_days），
    另附 meta（导出时间、范围、条数、金额单位）。其中：
    - txs 按发生时间**升序**（早→晚）排列，同一时刻按记录 id 升序；
    - settled_days 只导出区间内的日期（未指定范围则全部）。
    """
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    try:
        d_from = dt.date.fromisoformat(date_from) if date_from else None
        d_to = dt.date.fromisoformat(date_to) if date_to else None
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    if d_from and d_to and d_from > d_to:
        return jsonify({"error": "起始日期不能晚于结束日期"}), 400
    f_iso = d_from.isoformat() if d_from else None
    t_iso = d_to.isoformat() if d_to else None

    g = data.load_global()

    def in_range(t: dict) -> bool:
        if not (d_from or d_to):
            return True
        try:
            day = parse_ts(t.get("ts")).astimezone().date()
        except (ValueError, TypeError):
            return False
        if d_from and day < d_from:
            return False
        if d_to and day > d_to:
            return False
        return True

    txs = [t for t in g.get("txs", []) if in_range(t)]
    txs.sort(key=_tx_ts_key)          # 时间顺序（升序）

    settled = sorted(
        str(d) for d in (g.get("settled_days") or [])
        if (f_iso is None or str(d) >= f_iso) and (t_iso is None or str(d) <= t_iso)
    )

    now = dt.datetime.now().astimezone()
    payload = {
        "meta": {
            "exported_at": now.isoformat(timespec="seconds"),
            "range": {"from": f_iso, "to": t_iso},
            "amount_unit": "fen",          # 金额单位：分（整数）
            "account_count": len(g.get("accounts", [])),
            "tx_count": len(txs),
        },
        "asset_tags": g.get("asset_tags", []),
        "accounts": g.get("accounts", []),
        "txs": txs,
        "settled_days": settled,
    }

    if f_iso and t_iso:
        span = f"{f_iso}_{t_iso}"
    else:
        span = f_iso or t_iso or "all"
    filename = f"assets-{span}-{now.strftime('%Y%m%d-%H%M%S')}.json"
    body = json.dumps(payload, ensure_ascii=False, indent=2)

    # 显式要求下载时：直接以附件返回（不落盘）
    if export_io.download_requested(request.args):
        return export_io.attachment(filename, body)

    # 默认：写入导出目录 exports/，返回落盘信息（前端展示路径）
    info = export_io.save_text(filename, body)
    info["range"] = {"from": f_iso, "to": t_iso}
    info["account_count"] = payload["meta"]["account_count"]
    info["tx_count"] = len(txs)
    info["settled_day_count"] = len(settled)
    return jsonify(info)

