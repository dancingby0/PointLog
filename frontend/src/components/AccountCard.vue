<script setup>
// 账户管理：总资产 + 账户列表 + 增/改/删/校准
import { ref } from "vue";
import { state, loadAccounts, refreshAssets } from "../store";

const showNew = ref(false);
const newName = ref("");
const newKind = ref("asset");
const newBal = ref("");

const editId = ref(null);       // 编辑中的账户（改名）
const editName = ref("");
const adjustId = ref(null);     // 校准中的账户
const adjustBal = ref("");
const adjustNote = ref("");

async function addAccount() {
  const name = newName.value.trim();
  if (!name) return;
  try {
    const res = await fetch("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, kind: newKind.value, balance: newBal.value || 0 }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "创建失败");
    newName.value = ""; newBal.value = ""; newKind.value = "asset"; showNew.value = false;
    await loadAccounts();
  } catch (err) { alert("创建失败：" + err.message); }
}

async function rename(id) {
  const name = editName.value.trim();
  if (!name) return;
  try {
    const res = await fetch(`/api/accounts/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "改名失败");
    editId.value = null;
    await loadAccounts();
  } catch (err) { alert("改名失败：" + err.message); }
}

async function adjust(id) {
  try {
    const res = await fetch(`/api/accounts/${id}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ balance: adjustBal.value, note: adjustNote.value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "校准失败");
    adjustId.value = null; adjustBal.value = ""; adjustNote.value = "";
    await refreshAssets();
  } catch (err) { alert("校准失败：" + err.message); }
}

async function remove(id, name) {
  if (!confirm(`删除账户「${name}」及其全部流水？不可恢复！`)) return;
  try {
    const res = await fetch(`/api/accounts/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "删除失败");
    await refreshAssets();
  } catch (err) { alert("删除失败：" + err.message); }
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>💰 个人总资产</h2>
      <button type="button" class="ghost" @click="showNew = !showNew">＋ 账户</button>
    </div>
    <p class="total-assets">¥ {{ state.totalAssets.toFixed(2) }}</p>

    <div v-if="showNew" class="acct-form">
      <input v-model="newName" type="text" placeholder="账户名（如 微信 / 现金）">
      <select v-model="newKind">
        <option value="asset">资产</option>
        <option value="liability">负债</option>
      </select>
      <input v-model="newBal" type="number" step="0.01" placeholder="初始余额（负债为负）">
      <button type="button" @click="addAccount">创建</button>
    </div>

    <ul class="acct-list">
      <li v-for="a in state.accounts" :key="a.id" class="acct-item">
        <div class="acct-main">
          <strong>{{ a.name }}</strong>
          <span class="acct-bal" :class="{ neg: a.balance < 0 }">
            ¥ {{ a.balance.toFixed(2) }}
          </span>
        </div>
        <div class="acct-ops">
          <button type="button" class="ghost" @click="adjustId = a.id; adjustBal = String(a.balance); adjustNote=''">校准</button>
          <button type="button" class="ghost" @click="editId = a.id; editName = a.name">改名</button>
          <button type="button" class="ghost danger" @click="remove(a.id, a.name)">删除</button>
        </div>

        <!-- 改名行 -->
        <div v-if="editId === a.id" class="acct-inline">
          <input v-model="editName" type="text" @keyup.enter="rename(a.id)">
          <button type="button" @click="rename(a.id)">保存</button>
          <button type="button" class="ghost" @click="editId = null">取消</button>
        </div>
        <!-- 校准行 -->
        <div v-if="adjustId === a.id" class="acct-inline">
          <input v-model="adjustBal" type="number" step="0.01" placeholder="真实余额">
          <input v-model="adjustNote" type="text" placeholder="备注（可选）">
          <button type="button" @click="adjust(a.id)">设为该值</button>
          <button type="button" class="ghost" @click="adjustId = null">取消</button>
        </div>
      </li>
    </ul>
    <p v-if="state.accounts.length === 0" class="muted">还没有账户，点「＋账户」添加你的第一个钱包。</p>
  </section>
</template>
