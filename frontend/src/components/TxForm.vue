<script setup>
// 记账表单：支出 / 收入 / 转账
import { reactive, ref } from "vue";
import { state, refreshAssets, loadAccounts } from "../store";
import TagSelect from "./TagSelect.vue";

const form = reactive({ type: "expense", account_id: "", from: "", to: "", amount: "", tag: "", note: "" });
const busy = ref(false);

const ASSET_ACCTS = () => state.accounts.filter((a) => a.kind === "asset");

async function submit() {
  if (busy.value) return;
  const amount = Number(form.amount);
  if (!amount || amount <= 0) { alert("请输入大于 0 的金额"); return; }

  const payload = {
    type: form.type,
    amount,
    note: form.note.trim(),
    ts: undefined,
  };
  if (form.tag.trim()) payload.tags = [form.tag.trim()];

  if (form.type === "transfer") {
    if (!form.from || !form.to || form.from === form.to) { alert("请选择两个不同账户"); return; }
    payload.from = form.from;
    payload.to = form.to;
  } else {
    if (!form.account_id) { alert("请选择账户"); return; }
    payload.account_id = form.account_id;
  }

  busy.value = true;
  try {
    const res = await fetch("/api/transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存失败");
    form.amount = ""; form.note = ""; form.tag = "";
    await refreshAssets();
    await loadAccounts();
  } catch (err) {
    alert("保存失败：" + err.message);
  } finally {
    busy.value = false;
  }
}

async function onAddAssetTag(tag) {
  try {
    await fetch("/api/tags/asset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag }),
    });
    const res = await fetch("/api/tags/asset");
    const d = await res.json();
    if (res.ok) state.assetTags = d.tags;
  } catch (err) { console.error(err); }
}
</script>

<template>
  <section class="card">
    <h2>记一笔</h2>
    <div class="tx-type-switch">
      <button type="button" :class="{ on: form.type === 'expense' }" @click="form.type = 'expense'">支出</button>
      <button type="button" :class="{ on: form.type === 'income' }" @click="form.type = 'income'">收入</button>
      <button type="button" :class="{ on: form.type === 'transfer' }" @click="form.type = 'transfer'">转账</button>
    </div>

    <div v-if="form.type !== 'transfer'" class="tx-field">
      <label>账户
        <select v-model="form.account_id">
          <option value="" disabled>选择账户…</option>
          <option v-for="a in state.accounts" :key="a.id" :value="a.id">
            {{ a.name }}（¥{{ a.balance.toFixed(2) }}）
          </option>
        </select>
      </label>
    </div>
    <div v-else class="tx-field">
      <label>从（转出）
        <select v-model="form.from">
          <option value="" disabled>选择账户…</option>
          <option v-for="a in ASSET_ACCTS()" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
      </label>
      <label>到（转入）
        <select v-model="form.to">
          <option value="" disabled>选择账户…</option>
          <option v-for="a in ASSET_ACCTS()" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
      </label>
    </div>

    <label class="label-block">金额（¥）
      <input v-model="form.amount" type="number" min="0" step="0.01" placeholder="如 23.50">
    </label>
    <label class="label-block">标签（可选）
      <TagSelect :tags="state.assetTags" v-model="form.tag" @add-tag="onAddAssetTag" />
    </label>
    <label class="label-block">备注
      <input v-model="form.note" type="text" maxlength="100" placeholder="这笔钱花在哪 / 备注">
    </label>

    <button type="button" @click="submit" :disabled="busy">保存</button>
  </section>
</template>
