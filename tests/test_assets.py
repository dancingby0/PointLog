"""资产 API 测试：账户、收支、转账、余额校准（个人级）。"""

import json
import unittest
from urllib.parse import unquote

from base import ApiTestCase


class AssetsApiTest(ApiTestCase):
    """账户 / 收支 / 转账 / 校准。"""

    def _mk_acct(self, name="微信", kind="asset", balance=0):
        r = self.client.post("/api/accounts", json={"name": name, "kind": kind, "balance": balance})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def _balance(self, account_id):
        body = self.client.get("/api/accounts").get_json()
        return next(a for a in body["accounts"] if a["id"] == account_id)["balance"]

    def test_create_and_list(self):
        self._mk_acct("现金", "asset", 100.5)
        self._mk_acct("欠款", "liability", -50)
        r = self.client.get("/api/accounts")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(len(body["accounts"]), 2)
        # 总资产 = 100.5 + (-50)
        self.assertEqual(body["total"], 50.5)
        by_name = {a["name"]: a for a in body["accounts"]}
        self.assertEqual(by_name["现金"]["balance"], 100.5)
        self.assertEqual(by_name["欠款"]["kind"], "liability")

    def test_expense_updates_balance(self):
        acc = self._mk_acct("微信", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": acc["id"], "amount": 23.5, "note": "午饭",
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        body = self.client.get("/api/accounts").get_json()
        target = next(a for a in body["accounts"] if a["id"] == acc["id"])
        self.assertEqual(target["balance"], 76.5)

    def test_income_updates_balance(self):
        acc = self._mk_acct("支付宝", "asset", 0)
        self.client.post("/api/transactions", json={
            "type": "income", "account_id": acc["id"], "amount": 200, "note": "生活费",
        })
        body = self.client.get("/api/accounts").get_json()
        target = next(a for a in body["accounts"] if a["id"] == acc["id"])
        self.assertEqual(target["balance"], 200)

    def test_transfer_two_sides(self):
        a = self._mk_acct("银行卡", "asset", 500)
        b = self._mk_acct("微信", "asset", 0)
        r = self.client.post("/api/transactions", json={
            "type": "transfer", "from": a["id"], "to": b["id"], "amount": 100, "note": "转到微信",
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(r.get_json()["type"], "transfer")
        body = self.client.get("/api/accounts").get_json()
        by_id = {x["id"]: x for x in body["accounts"]}
        self.assertEqual(by_id[a["id"]]["balance"], 400)
        self.assertEqual(by_id[b["id"]]["balance"], 100)
        # 总资产不变
        self.assertEqual(body["total"], 500)

    def test_adjust_resets_balance(self):
        """手动校准 = 直接设值（不理会与流水推算的差值）。"""
        acc = self._mk_acct("现金", "asset", 100)
        self.client.post("/api/transactions", json={
            "type": "expense", "account_id": acc["id"], "amount": 20, "note": "花了一笔",
        })
        # 现在按流水是 80；实际可能因漏记只有 60，校准到 60
        r = self.client.post(f"/api/accounts/{acc['id']}/adjust", json={"balance": 60, "note": "看真实钱包校准"})
        self.assertEqual(r.status_code, 200, r.get_json())
        body = self.client.get("/api/accounts").get_json()
        target = next(x for x in body["accounts"] if x["id"] == acc["id"])
        self.assertEqual(target["balance"], 60)

    def test_transactions_list(self):
        a = self._mk_acct("微信", "asset", 100)
        self.client.post("/api/transactions", json={"type": "expense", "account_id": a["id"], "amount": 10, "note": "A"})
        self.client.post("/api/transactions", json={"type": "income", "account_id": a["id"], "amount": 30, "note": "B"})
        r = self.client.get("/api/transactions")
        txs = r.get_json()["transactions"]
        self.assertEqual(len(txs), 2)
        # 新→旧：B 在前
        self.assertEqual(txs[0]["note"], "B")
        # 过滤单账户
        r = self.client.get(f"/api/transactions?account_id={a['id']}")
        self.assertEqual(len(r.get_json()["transactions"]), 2)

    def test_transaction_with_custom_time(self):
        """补录：可传历史发生时间（datetime-local naive，视为本地时区）。"""
        from utils import parse_ts
        acc = self._mk_acct("微信", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": acc["id"], "amount": 12,
            "note": "昨天晚上的饭", "ts": "2026-07-03T21:05",
        })
        self.assertEqual(r.status_code, 201, r.get_json())
        ts = r.get_json()["ts"]
        # 存为本地秒级 ISO，保留用户时刻
        self.assertEqual(parse_ts(ts), parse_ts("2026-07-03T21:05"))
        # 默认时间存在时，列表新→旧仍正确（带历史时间的那条更旧）
        self.client.post("/api/transactions", json={
            "type": "income", "account_id": acc["id"], "amount": 50, "note": "刚收到",
        })
        r = self.client.get("/api/transactions")
        txs = r.get_json()["transactions"]
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0]["note"], "刚收到")
        self.assertEqual(txs[1]["note"], "昨天晚上的饭")
        # 余额不受时间影响（仍按记账顺序算）
        body = self.client.get("/api/accounts").get_json()
        target = next(x for x in body["accounts"] if x["id"] == acc["id"])
        self.assertEqual(target["balance"], 138)

    def test_transaction_bad_time_rejected(self):
        acc = self._mk_acct("现金", "asset", 0)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": acc["id"], "amount": 1, "ts": "不是时间",
        })
        self.assertEqual(r.status_code, 400)

    def test_update_transaction_time_and_note(self):
        """编辑已有流水：可改发生时间与备注；余额不变。"""
        from utils import parse_ts
        acc = self._mk_acct("微信", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": acc["id"], "amount": 12, "note": "旧备注",
        })
        tx_id = r.get_json()["id"]
        r = self.client.put(f"/api/transactions/{tx_id}", json={
            "ts": "2026-05-01T08:30", "note": "改到 5 月 1 日",
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        self.assertEqual(parse_ts(body["ts"]), parse_ts("2026-05-01T08:30"))
        self.assertEqual(body["note"], "改到 5 月 1 日")
        # 仅改时间不动余额
        r = self.client.get("/api/accounts")
        target = next(a for a in r.get_json()["accounts"] if a["id"] == acc["id"])
        self.assertEqual(target["balance"], 88)
        # 列表返回编辑后内容
        txs = self.client.get("/api/transactions").get_json()["transactions"]
        self.assertTrue(any(t["id"] == tx_id and t["note"] == "改到 5 月 1 日" for t in txs))

    def test_update_transaction_amount_account_type(self):
        """编辑可改金额 / 账户 / 类型：等价"撤销原记录 + 重新入账"，余额自动重算。"""
        a = self._mk_acct("A", "asset", 100)
        b = self._mk_acct("B", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": a["id"], "amount": 10})
        tx_id = r.get_json()["id"]
        self.assertEqual(self._balance(a["id"]), 90)
        # 改金额 10 → 25
        r = self.client.put(f"/api/transactions/{tx_id}", json={"amount": 25})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["amount"], 25)
        self.assertEqual(self._balance(a["id"]), 75)
        # 改账户 A → B
        r = self.client.put(f"/api/transactions/{tx_id}", json={"account_id": b["id"]})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self._balance(a["id"]), 100)
        self.assertEqual(self._balance(b["id"]), 75)
        # 改类型 支出 → 收入（余额方向反转）
        r = self.client.put(f"/api/transactions/{tx_id}", json={"type": "income"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["type"], "income")
        self.assertEqual(self._balance(b["id"]), 125)
        self.assertEqual(self._balance(a["id"]), 100)

    def test_update_transfer_to_expense_and_back(self):
        """转账 ⇄ 支出 互转：两端余额正确还原与重算。"""
        a = self._mk_acct("A", "asset", 500)
        b = self._mk_acct("B", "asset", 0)
        r = self.client.post("/api/transactions", json={
            "type": "transfer", "from": a["id"], "to": b["id"], "amount": 100})
        tx_id = r.get_json()["id"]
        self.assertEqual(self._balance(a["id"]), 400)
        self.assertEqual(self._balance(b["id"]), 100)
        # 改成支出（A 花 100）：撤销转账 → 再应用支出
        r = self.client.put(f"/api/transactions/{tx_id}", json={
            "type": "expense", "account_id": a["id"], "amount": 100})
        self.assertEqual(r.status_code, 200, r.get_json())
        body = r.get_json()
        self.assertEqual(body["type"], "expense")
        self.assertIsNone(body["from_account"])
        self.assertIsNone(body["to_account"])
        self.assertEqual(self._balance(a["id"]), 400)
        self.assertEqual(self._balance(b["id"]), 0)
        # 再改回转账（金额沿用 100）
        r = self.client.put(f"/api/transactions/{tx_id}", json={
            "type": "transfer", "from": a["id"], "to": b["id"]})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self._balance(a["id"]), 400)
        self.assertEqual(self._balance(b["id"]), 100)

    def test_update_transaction_validation_keeps_balance(self):
        """非法编辑被拒且不影响余额与记录。"""
        a = self._mk_acct("A", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": a["id"], "amount": 10})
        tx_id = r.get_json()["id"]
        self.assertEqual(self.client.put(f"/api/transactions/{tx_id}", json={"amount": 0}).status_code, 400)
        self.assertEqual(self.client.put(f"/api/transactions/{tx_id}", json={"amount": -3}).status_code, 400)
        self.assertEqual(self.client.put(f"/api/transactions/{tx_id}", json={"type": "bad"}).status_code, 400)
        self.assertEqual(self.client.put(f"/api/transactions/{tx_id}", json={"account_id": "nope"}).status_code, 404)
        self.assertEqual(self.client.put(
            f"/api/transactions/{tx_id}", json={"type": "transfer", "from": a["id"], "to": a["id"]}).status_code, 400)
        self.assertEqual(self.client.put(f"/api/transactions/{tx_id}", json={"ts": ""}).status_code, 400)
        # 余额与记录未被破坏
        self.assertEqual(self._balance(a["id"]), 90)
        body = self.client.get("/api/transactions").get_json()
        self.assertEqual(body["transactions"][0]["amount"], 10)
        self.assertEqual(body["transactions"][0]["type"], "expense")

    def test_update_transaction_not_found(self):
        r = self.client.put("/api/transactions/nope", json={"ts": "2026-05-01T08:30"})
        self.assertEqual(r.status_code, 404)

    def test_adjust_record_not_editable(self):
        acc = self._mk_acct("现金", "asset", 50)
        self.client.post(f"/api/accounts/{acc['id']}/adjust", json={"balance": 60, "note": "校准"})
        txs = self.client.get("/api/transactions").get_json()["transactions"]
        adj = next(t for t in txs if t["type"] == "adjust")
        r = self.client.put(f"/api/transactions/{adj['id']}", json={"ts": "2026-05-01T08:30"})
        self.assertEqual(r.status_code, 400)

    def test_delete_expense_rolls_back_balance(self):
        """删除支出 → 余额自动加回，流水移除。"""
        acc = self._mk_acct("微信", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": acc["id"], "amount": 23.5, "note": "午饭",
        })
        tx_id = r.get_json()["id"]
        # 删前余额 76.5
        r = self.client.get("/api/accounts")
        self.assertEqual(next(a for a in r.get_json()["accounts"] if a["id"] == acc["id"])["balance"], 76.5)
        r = self.client.delete(f"/api/transactions/{tx_id}")
        self.assertEqual(r.status_code, 200, r.get_json())
        # 余额还原到 100，流水为空
        r = self.client.get("/api/accounts")
        self.assertEqual(next(a for a in r.get_json()["accounts"] if a["id"] == acc["id"])["balance"], 100)
        txs = self.client.get("/api/transactions").get_json()["transactions"]
        self.assertFalse(any(t["id"] == tx_id for t in txs))

    def test_delete_income_and_transfer_rollback(self):
        """收入删除扣回；转账删除两端还原。"""
        a = self._mk_acct("银行卡", "asset", 500)
        b = self._mk_acct("微信", "asset", 0)
        # 收入 200
        r1 = self.client.post("/api/transactions", json={"type": "income", "account_id": a["id"], "amount": 200})
        # 转账 100 A→B
        r2 = self.client.post("/api/transactions", json={
            "type": "transfer", "from": a["id"], "to": b["id"], "amount": 100})
        body = self.client.get("/api/accounts").get_json()
        by_id = {x["id"]: x for x in body["accounts"]}
        self.assertEqual(by_id[a["id"]]["balance"], 600)
        self.assertEqual(by_id[b["id"]]["balance"], 100)
        # 删除收入 → A 600 → 400；再删转账 → A 400 → 500、B 100 → 0
        self.client.delete(f"/api/transactions/{r1.get_json()['id']}")
        body = self.client.get("/api/accounts").get_json()
        by_id = {x["id"]: x for x in body["accounts"]}
        self.assertEqual(by_id[a["id"]]["balance"], 400)
        self.client.delete(f"/api/transactions/{r2.get_json()['id']}")
        body = self.client.get("/api/accounts").get_json()
        by_id = {x["id"]: x for x in body["accounts"]}
        self.assertEqual(by_id[a["id"]]["balance"], 500)
        self.assertEqual(by_id[b["id"]]["balance"], 0)

    def test_delete_validation(self):
        self.assertEqual(self.client.delete("/api/transactions/nope").status_code, 404)
        acc = self._mk_acct("现金", "asset", 10)
        self.client.post(f"/api/accounts/{acc['id']}/adjust", json={"balance": 15, "note": "校准"})
        txs = self.client.get("/api/transactions").get_json()["transactions"]
        adj = next(t for t in txs if t["type"] == "adjust")
        r = self.client.delete(f"/api/transactions/{adj['id']}")
        self.assertEqual(r.status_code, 400)

    def _seed_for_filter(self):
        """两账户 + 4 笔跨日期/类型/渠道/标签的流水（用于筛选与分页测试）。"""
        a = self._mk_acct("微信", "asset", 1000)
        b = self._mk_acct("支付宝", "asset", 1000)
        self.client.post("/api/transactions", json={
            "type": "expense", "account_id": a["id"], "amount": 10, "note": "当天微信支出",
            "tags": ["餐饮"], "ts": "2026-09-15T10:00"})
        self.client.post("/api/transactions", json={
            "type": "income", "account_id": a["id"], "amount": 20, "note": "当天微信收入",
            "tags": ["工资"], "ts": "2026-09-15T12:00"})
        self.client.post("/api/transactions", json={
            "type": "expense", "account_id": b["id"], "amount": 30, "note": "前日支付宝支出",
            "tags": ["餐饮", "交通"], "ts": "2026-09-14T09:00"})
        self.client.post("/api/transactions", json={
            "type": "transfer", "from": a["id"], "to": b["id"], "amount": 5, "note": "前日转账",
            "ts": "2026-09-14T20:00"})
        return a, b

    def _get_txs(self, query=""):
        return self.client.get(f"/api/transactions{query}").get_json()

    def test_transactions_default_no_filter(self):
        """默认不筛选：返回全部（新→旧）并带 total。"""
        self._seed_for_filter()
        body = self._get_txs()
        self.assertEqual(body["total"], 4)
        self.assertEqual(len(body["transactions"]), 4)
        self.assertEqual(body["transactions"][0]["note"], "当天微信收入")

    def test_transactions_filter_by_date(self):
        """日期区间筛选（单日 = from 与 to 相同）。"""
        self._seed_for_filter()
        body = self._get_txs("?from=2026-09-15&to=2026-09-15")
        self.assertEqual(body["total"], 2)
        self.assertTrue(all(t["note"].startswith("当天") for t in body["transactions"]))
        # 开区间：只给 from
        body = self._get_txs("?from=2026-09-15")
        self.assertEqual(body["total"], 2)

    def test_transactions_filter_by_channel_multi(self):
        """渠道多选：转账任一端匹配即算。"""
        a, b = self._seed_for_filter()
        body = self._get_txs(f"?channels={a['id']}")
        self.assertEqual(body["total"], 3)   # 微信两笔 + 转账（微信端）
        body = self._get_txs(f"?channels={a['id']},{b['id']}")
        self.assertEqual(body["total"], 4)
        body = self._get_txs(f"?channels={b['id']}")
        self.assertEqual(body["total"], 2)   # 支付宝支出 + 转账

    def test_transactions_filter_by_type_multi(self):
        self._seed_for_filter()
        self.assertEqual(self._get_txs("?types=expense")["total"], 2)
        self.assertEqual(self._get_txs("?types=expense,income")["total"], 3)
        self.assertEqual(self._get_txs("?types=transfer")["total"], 1)

    def test_transactions_filter_by_tag_multi(self):
        """标签多选：命中任一标签即算；并返回可筛选标签集合。"""
        self._seed_for_filter()
        body = self._get_txs("?tags=%E9%A4%90%E9%A5%AE")            # 餐饮
        self.assertEqual(body["total"], 2)
        body = self._get_txs("?tags=%E9%A4%90%E9%A5%AE,%E5%B7%A5%E8%B5%84")  # 餐饮,工资
        self.assertEqual(body["total"], 3)
        body = self._get_txs("?tags=%E4%BA%A4%E9%80%9A")            # 交通
        self.assertEqual(body["total"], 1)
        # 可筛选标签（全部出现过，去重）
        body = self._get_txs()
        self.assertEqual(set(body["available_tags"]), {"餐饮", "工资", "交通"})

    def test_transactions_filter_combined(self):
        """组合筛选：日期 + 渠道 + 标签（如 9月15日 且 微信）。"""
        from urllib.parse import quote
        a, b = self._seed_for_filter()
        body = self._get_txs(f"?from=2026-09-15&to=2026-09-15&channels={a['id']}")
        self.assertEqual(body["total"], 2)
        body = self._get_txs(f"?from=2026-09-15&to=2026-09-15&channels={b['id']}")
        self.assertEqual(body["total"], 0)
        body = self._get_txs(f"?from=2026-09-15&to=2026-09-15&types=expense")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["transactions"][0]["note"], "当天微信支出")
        # 日期 + 标签
        body = self._get_txs(f"?from=2026-09-15&to=2026-09-15&tags={quote('餐饮')}")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["transactions"][0]["note"], "当天微信支出")
        # 日期 + 渠道 + 标签 三条件组合
        body = self._get_txs(
            f"?from=2026-09-14&to=2026-09-14&channels={b['id']}&tags={quote('交通')}")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["transactions"][0]["note"], "前日支付宝支出")

    def test_settlements_mark_and_list(self):
        """平账标记：未平账列表 = 有流水的日期 − 已平账日期。"""
        a = self._mk_acct("微信", "asset", 1000)
        self.client.post("/api/transactions", json={
            "type": "expense", "account_id": a["id"], "amount": 10, "ts": "2026-09-15T10:00"})
        self.client.post("/api/transactions", json={
            "type": "expense", "account_id": a["id"], "amount": 20, "ts": "2026-09-14T09:00"})
        body = self.client.get("/api/asset-settlements").get_json()
        self.assertEqual(body["settled_days"], [])
        self.assertEqual(body["unsettled_days"], ["2026-09-14", "2026-09-15"])
        # 标记 9/15 已平账
        r = self.client.put("/api/asset-settlements", json={"day": "2026-09-15", "settled": True})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["settled_days"], ["2026-09-15"])
        body = self.client.get("/api/asset-settlements").get_json()
        self.assertEqual(body["settled_days"], ["2026-09-15"])
        self.assertEqual(body["unsettled_days"], ["2026-09-14"])
        # 取消标记
        r = self.client.put("/api/asset-settlements", json={"day": "2026-09-15", "settled": False})
        self.assertEqual(r.get_json()["settled_days"], [])
        self.assertEqual(
            self.client.get("/api/asset-settlements").get_json()["unsettled_days"],
            ["2026-09-14", "2026-09-15"])

    def test_settlements_validation(self):
        self.assertEqual(
            self.client.put("/api/asset-settlements", json={"day": ""}).status_code, 400)
        self.assertEqual(
            self.client.put("/api/asset-settlements", json={"day": "2026/09/15"}).status_code, 400)

    def test_transactions_filter_unsettled(self):
        """仅看未平账日期：已平账日期的流水被排除；可与其它筛选叠加。"""
        self._seed_for_filter()   # 09-15 两笔、09-14 两笔
        self.assertEqual(self._get_txs("?unsettled=1")["total"], 4)
        self.client.put("/api/asset-settlements", json={"day": "2026-09-15", "settled": True})
        body = self._get_txs("?unsettled=1")
        self.assertEqual(body["total"], 2)
        self.assertTrue(all(t["note"].startswith("前日") for t in body["transactions"]))
        # 叠加类型筛选
        body = self._get_txs("?unsettled=1&types=expense")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["transactions"][0]["note"], "前日支付宝支出")
        # 全部平账后为空
        self.client.put("/api/asset-settlements", json={"day": "2026-09-14", "settled": True})
        self.assertEqual(self._get_txs("?unsettled=1")["total"], 0)
        # 不传参数则不受影响
        self.assertEqual(self._get_txs()["total"], 4)

    def test_transaction_multi_tags(self):
        """记一笔可带多个标签；都能用于筛选。"""
        from urllib.parse import quote
        acc = self._mk_acct("微信", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "expense", "account_id": acc["id"], "amount": 18,
            "tags": ["餐饮", "外卖"], "note": "晚饭外卖"})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(r.get_json()["tags"], ["餐饮", "外卖"])
        body = self._get_txs()
        self.assertEqual(set(body["available_tags"]), {"餐饮", "外卖"})
        self.assertEqual(self._get_txs(f"?tags={quote('外卖')}")["total"], 1)
        self.assertEqual(self._get_txs(f"?tags={quote('餐饮')}")["total"], 1)
        # 编辑为另一个标签集合
        tx_id = r.get_json()["id"]
        r = self.client.put(f"/api/transactions/{tx_id}", json={"tags": ["打车"]})
        self.assertEqual(r.get_json()["tags"], ["打车"])
        self.assertEqual(self._get_txs(f"?tags={quote('打车')}")["total"], 1)
        self.assertEqual(self._get_txs(f"?tags={quote('餐饮')}")["total"], 0)

    def test_balance_after_each_tx(self):
        """每笔后余额：最近校准为锚点逐笔重放；锚点前流水不重复计；无锚点=null。"""
        a = self._mk_acct("A", "asset", 0)
        b = self._mk_acct("B", "asset", 0)
        # 锚点之前的一笔（余额已含在后续校准值里，不应重复计算 → 不显示余额）
        self.client.post("/api/transactions", json={
            "type": "expense", "account_id": a["id"], "amount": 5, "note": "锚点前的旧账"})
        # 锚点：A 校准到 200
        self.client.post(f"/api/accounts/{a['id']}/adjust", json={"balance": 200, "note": "校准A"})
        self.client.post("/api/transactions", json={
            "type": "expense", "account_id": a["id"], "amount": 10, "note": "支出x"})
        self.client.post("/api/transactions", json={
            "type": "income", "account_id": a["id"], "amount": 20, "note": "收入y"})
        self.client.post("/api/transactions", json={
            "type": "transfer", "from": a["id"], "to": b["id"], "amount": 30, "note": "转给B"})

        txs = self.client.get("/api/transactions").get_json()["transactions"]
        by_note = {t["note"]: t for t in txs}
        self.assertEqual(by_note["锚点前的旧账"]["balance_after"], None)   # 锚点前
        self.assertEqual(by_note["校准A"]["balance_after"], 200.0)
        self.assertEqual(by_note["支出x"]["balance_after"], 190.0)        # 200 - 10
        self.assertEqual(by_note["收入y"]["balance_after"], 210.0)        # 190 + 20
        tr = by_note["转给B"]
        self.assertEqual(tr["balance_after_from"], 180.0)                 # 210 - 30
        self.assertEqual(tr["balance_after_to"], None)                    # B 无锚点

    def test_transactions_filter_invert(self):
        """反选：勾上=排除所选项（渠道/类型/标签各自可取反）。"""
        from urllib.parse import quote
        a, b = self._seed_for_filter()
        # 渠道反选：排除微信 → 支付宝支出（+ 无渠道? 转账含微信→排除）
        body = self._get_txs(f"?channels={a['id']}&invert=channels")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["transactions"][0]["note"], "前日支付宝支出")
        # 类型反选：排除支出 → 收入 + 转账
        body = self._get_txs("?types=expense&invert=types")
        self.assertEqual(body["total"], 2)
        self.assertEqual({t["type"] for t in body["transactions"]}, {"income", "transfer"})
        # 标签反选：排除餐饮 → 工资(收入) + 无标签(转账)
        body = self._get_txs(f"?tags={quote('餐饮')}&invert=tags")
        self.assertEqual(body["total"], 2)
        self.assertEqual({t["note"] for t in body["transactions"]}, {"当天微信收入", "前日转账"})
        # 正反混合：类型反选（排除转账） + 渠道正选（微信）
        body = self._get_txs(f"?types=transfer&invert=types&channels={a['id']}")
        self.assertEqual(body["total"], 2)
        self.assertEqual({t["type"] for t in body["transactions"]}, {"expense", "income"})
        # 反选但未选任何项 = 不筛选
        body = self._get_txs("?invert=channels,types,tags")
        self.assertEqual(body["total"], 4)
        # 反选与日期区间组合
        body = self._get_txs(f"?from=2026-09-15&to=2026-09-15&channels={a['id']}&invert=channels")
        self.assertEqual(body["total"], 0)

    def test_transactions_pagination(self):
        """分页：page/page_size 切页；total 为筛选后总数。"""
        self._seed_for_filter()
        p1 = self._get_txs("?page=1&page_size=2")
        self.assertEqual(p1["total"], 4)
        self.assertEqual(p1["page"], 1)
        self.assertEqual(len(p1["transactions"]), 2)
        self.assertEqual(p1["transactions"][0]["note"], "当天微信收入")
        p2 = self._get_txs("?page=2&page_size=2")
        self.assertEqual(p2["page"], 2)
        self.assertEqual([t["note"] for t in p2["transactions"]], ["前日转账", "前日支付宝支出"])
        p3 = self._get_txs("?page=3&page_size=2")
        self.assertEqual(p3["transactions"], [])
        # 分页与筛选叠加
        body = self._get_txs("?types=expense&page=1&page_size=1")
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["transactions"]), 1)
        self.assertEqual(body["transactions"][0]["note"], "当天微信支出")

    def test_transactions_bad_filter_params(self):
        self.assertEqual(self.client.get("/api/transactions?from=2026/09/15").status_code, 400)
        self.assertEqual(
            self.client.get("/api/transactions?from=2026-09-16&to=2026-09-15").status_code, 400)
        self.assertEqual(self.client.get("/api/transactions?page=abc").status_code, 400)

    def test_export_assets_range_and_time_order(self):
        """导出：按 from/to 区间筛选，且 txs 按发生时间升序（早→晚）。"""
        a = self._mk_acct("微信", "asset", 1000)
        # 故意乱序写入：中间的日期先写
        for ts, note, amount in [
            ("2026-09-15T10:00:00+08:00", "b-中", 20),
            ("2026-09-01T09:00:00+08:00", "a-早", 10),
            ("2026-10-01T08:00:00+08:00", "d-晚", 40),
            ("2026-09-30T23:30:00+08:00", "c-次晚", 30),
        ]:
            r = self.client.post("/api/transactions", json={
                "type": "expense", "account_id": a["id"], "amount": amount,
                "note": note, "ts": ts})
            self.assertEqual(r.status_code, 201, r.get_json())

        # 指定区间：只含区间内，并按时间升序
        r = self.client.get("/api/assets/export?from=2026-09-01&to=2026-09-30")
        self.assertEqual(r.status_code, 200)
        cd = r.headers.get("Content-Disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn("assets-2026-09-01_2026-09-30-", unquote(cd))
        body = json.loads(r.data.decode("utf-8"))
        self.assertEqual(body["meta"]["range"], {"from": "2026-09-01", "to": "2026-09-30"})
        self.assertEqual(body["meta"]["amount_unit"], "fen")
        self.assertEqual(body["meta"]["tx_count"], 3)
        self.assertEqual([t["note"] for t in body["txs"]], ["a-早", "b-中", "c-次晚"])
        # 内容与账本同构：账户/标签原样
        self.assertEqual(body["accounts"][0]["balance_fen"], 100000 - (10 + 20 + 30 + 40) * 100)
        self.assertIn("asset_tags", body)

        # 不传参数 = 全部，仍按时间升序
        all_body = json.loads(self.client.get("/api/assets/export").data.decode("utf-8"))
        self.assertEqual(all_body["meta"]["range"], {"from": None, "to": None})
        self.assertEqual([t["note"] for t in all_body["txs"]], ["a-早", "b-中", "c-次晚", "d-晚"])
        self.assertIn("assets-all-", unquote(
            self.client.get("/api/assets/export").headers["Content-Disposition"]))

        # 只给一端（to）：含该日及之前
        head = json.loads(self.client.get("/api/assets/export?to=2026-09-15").data.decode("utf-8"))
        self.assertEqual([t["note"] for t in head["txs"]], ["a-早", "b-中"])

    def test_export_assets_settled_days_and_validation(self):
        """导出：settled_days 同样按区间过滤；非法区间/格式返回 400。"""
        self.client.put("/api/asset-settlements", json={"day": "2026-09-10", "settled": True})
        self.client.put("/api/asset-settlements", json={"day": "2026-10-01", "settled": True})

        r = self.client.get("/api/assets/export?from=2026-09-01&to=2026-09-30")
        body = json.loads(r.data.decode("utf-8"))
        self.assertEqual(body["settled_days"], ["2026-09-10"])
        # 不限范围 → 全部已平账日期
        all_body = json.loads(self.client.get("/api/assets/export").data.decode("utf-8"))
        self.assertEqual(all_body["settled_days"], ["2026-09-10", "2026-10-01"])

        self.assertEqual(self.client.get("/api/assets/export?from=2026/09/01").status_code, 400)
        self.assertEqual(
            self.client.get("/api/assets/export?from=2026-09-30&to=2026-09-01").status_code, 400)

    def test_assets_are_global(self):
        """账户数据是个人级：切档案后仍存在。"""
        self._mk_acct("我的卡", "asset", 66)
        self.client.post("/api/profiles", json={"name": "other"})
        self.client.post("/api/profiles/switch", json={"name": "other"})
        body = self.client.get("/api/accounts").get_json()
        self.assertEqual(len(body["accounts"]), 1)
        self.assertEqual(body["accounts"][0]["balance"], 66)

    def test_validation(self):
        r = self.client.post("/api/transactions", json={"type": "expense", "amount": -5})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/transactions", json={"type": "badtype", "amount": 1})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/accounts", json={"name": "", "kind": "asset"})
        self.assertEqual(r.status_code, 400)
        # 转移同账户拒绝
        a = self._mk_acct("卡", "asset", 100)
        r = self.client.post("/api/transactions", json={
            "type": "transfer", "from": a["id"], "to": a["id"], "amount": 5})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()