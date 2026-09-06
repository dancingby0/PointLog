"""资产 API 测试：账户、收支、转账、余额校准（个人级）。"""

import unittest

from base import ApiTestCase


class AssetsApiTest(ApiTestCase):
    """账户 / 收支 / 转账 / 校准。"""

    def _mk_acct(self, name="微信", kind="asset", balance=0):
        r = self.client.post("/api/accounts", json={"name": name, "kind": kind, "balance": balance})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

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