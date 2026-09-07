<script setup>
import { computed, reactive, ref } from "vue";
import { state, refreshAssets } from "../store";
import { formatTime, toLocalInput } from "../utils";

const typeLabel = { expense: "支出", income: "收入", transfer: "转账", adjust: "校准" };

function acctName(id) {
  const a = state.accounts.find((x) => x.id === id);
  return a ? a.name : id;
}

const txs = computed(() => [...state.txs]);

const fmtMoney = (n) => (Number(n) < 0 ? "-" : "") + "¥" + Math.abs(Number(n)).toFixed(2);

// 行内编辑（只改发生时间 / 备注；校准记录不可编辑）
const editingId = ref(null);
const edit = reactive({ ts: "", note: "" });

// 行内删除（两步确认防误触；校准记录不可删除）
const confirmDeleteId = ref(null);

function askDelete(t) {
  confirmDeleteId.value = t.id;
}

async function deleteTx(t) {
  try {
    const res = await fetch(`/api/transactions/${encodeURIComponent(t.id)}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "删除失败");
    confirmDeleteId.value = null;
    await refreshAssets();
  } catch (err) {
    alert("删除失败：" + err.message);
  }
}

function startEdit(t) {
  editingId.value = t.id;
  confirmDeleteId.value = null;
  edit.ts = toLocalInput(new Date(t.ts));
  edit.note = t.note || "";
}

function cancelEdit() {
  editingId.value = null;
}

async function saveEdit(t) {
  try {
    const res = await fetch(`/api/transactions/${encodeURIComponent(t.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ts: edit.ts, note: edit.note }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存失败");
    editingId.value = null;
    await refreshAssets();
  } catch (err) {
    alert("保存失败：" + err.message);
  }
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>流水</h2>
      <span class="muted">{{ txs.length }} 条</span>
    </div>
    <p v-if="txs.length === 0" class="muted">还没有流水。</p>
    <ul v-else class="tx-list">
      <li v-for="t in txs" :key="t.id" class="tx-item">
        <div class="tx-main">
          <span class="tx-type" :class="t.type">{{ typeLabel[t.type] || t.type }}</span>
          <span class="tx-desc">
            <template v-if="t.type === 'transfer'">
              {{ acctName(t.from_account) }} → {{ acctName(t.to_account) }}
            </template>
            <template v-else>
              {{ acctName(t.account_id) }}
            </template>
            <span v-if="t.note"> · {{ t.note }}</span>
          </span>
          <span v-for="tag in t.tags" :key="tag" class="tx-tag">{{ tag }}</span>
        </div>
        <div class="tx-side">
          <span class="tx-amount" :class="t.type">{{ fmtMoney(t.amount) }}</span>
          <span class="tx-time">{{ formatTime(t.ts) }}</span>
          <div v-if="t.type !== 'adjust'" class="tx-ops">
            <button v-if="confirmDeleteId !== t.id" type="button" class="ghost tiny"
                    @click="startEdit(t)" title="修改发生时间 / 备注">✏️ 编辑</button>
            <button v-if="confirmDeleteId !== t.id" type="button" class="ghost tiny danger"
                    @click="askDelete(t)" title="删除该笔并回滚余额">🗑 删除</button>
          </div>
        </div>
        <div v-if="editingId === t.id" class="tx-edit">
          <label>发生时间
            <input v-model="edit.ts" type="datetime-local">
          </label>
          <label>备注
            <input v-model="edit.note" type="text" maxlength="100" placeholder="备注（可留空）">
          </label>
          <button type="button" @click="saveEdit(t)">保存</button>
          <button type="button" class="ghost" @click="cancelEdit">取消</button>
          <span class="tx-edit-hint">金额 / 账户 / 类型如需调整，请删除后重记（或用"校准"修正余额）</span>
        </div>
        <div v-if="confirmDeleteId === t.id" class="tx-edit">
          <span class="tx-del-warn">⚠️ 将永久删除这笔 {{ typeLabel[t.type] }}（¥{{ Number(t.amount).toFixed(2) }}），并<b>回滚账户余额</b>，不可恢复！</span>
          <button type="button" class="danger" @click="deleteTx(t)">确认删除</button>
          <button type="button" class="ghost" @click="confirmDeleteId = null">取消</button>
          <span class="tx-edit-hint">误记/记错了？删除后余额自动还原这笔影响；有历史差额可用"校准"修正</span>
        </div>
      </li>
    </ul>
  </section>
</template>
