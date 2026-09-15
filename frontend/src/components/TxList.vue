<script setup>
import { computed, reactive, ref } from "vue";
import {
  state,
  refreshAssets,
  toggleTxFilterItem,
  resetTxFilters,
  setTxFilters,
  setTxPage,
  setTxPageSize,
} from "../store";
import { formatTime, toLocalInput } from "../utils";

const typeLabel = { expense: "支出", income: "收入", transfer: "转账", adjust: "校准" };
const TYPE_OPTS = [
  { value: "expense", label: "支出" },
  { value: "income", label: "收入" },
  { value: "transfer", label: "转账" },
  { value: "adjust", label: "校准" },
];

function acctName(id) {
  const a = state.accounts.find((x) => x.id === id);
  return a ? a.name : id;
}

const txs = computed(() => [...state.txs]);

const fmtMoney = (n) => (Number(n) < 0 ? "-" : "") + "¥" + Math.abs(Number(n)).toFixed(2);

// ---- 筛选 / 分页 ----
const hasFilter = computed(() => !!(
  state.txFilters.from || state.txFilters.to
  || state.txFilters.channels.length || state.txFilters.types.length
  || state.txFilters.tags.length
));
const totalPages = computed(() => Math.max(1, Math.ceil(state.txTotal / state.txPageSize)));

function applyDates() {
  // 起止日期改动 → 回第 1 页重新查询
  setTxFilters({ from: state.txFilters.from, to: state.txFilters.to });
}

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
    // 删掉当前页最后一条 → 回退上一页，避免空白页
    if (state.txs.length === 0 && state.txPage > 1) await setTxPage(state.txPage - 1);
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
      <span class="muted">共 {{ state.txTotal }} 条</span>
    </div>

    <!-- 筛选栏：默认全部不筛选；日期/渠道/类型可同时多选组合 -->
    <div class="tx-filters">
      <div class="tx-filter-row">
        <span class="tx-filter-label">日期</span>
        <input type="date" v-model="state.txFilters.from" @change="applyDates">
        <span class="muted">至</span>
        <input type="date" v-model="state.txFilters.to" @change="applyDates">
        <button v-if="hasFilter" type="button" class="ghost tiny" @click="resetTxFilters">清空筛选</button>
        <span v-else class="muted">（默认不筛选）</span>
      </div>
      <div class="tx-filter-row">
        <span class="tx-filter-label">渠道</span>
        <template v-if="state.accounts.length">
          <button v-for="a in state.accounts" :key="a.id" type="button" class="chip"
                  :class="{ on: state.txFilters.channels.includes(a.id) }"
                  @click="toggleTxFilterItem('channels', a.id)">{{ a.name }}</button>
        </template>
        <span v-else class="muted">（还没有账户）</span>
      </div>
      <div class="tx-filter-row">
        <span class="tx-filter-label">类型</span>
        <button v-for="opt in TYPE_OPTS" :key="opt.value" type="button" class="chip"
                :class="{ on: state.txFilters.types.includes(opt.value) }"
                @click="toggleTxFilterItem('types', opt.value)">{{ opt.label }}</button>
        <span class="muted">可多选；不选=不限</span>
      </div>
      <div class="tx-filter-row" v-if="state.txTags.length">
        <span class="tx-filter-label">标签</span>
        <button v-for="tg in state.txTags" :key="tg" type="button" class="chip"
                :class="{ on: state.txFilters.tags.includes(tg) }"
                @click="toggleTxFilterItem('tags', tg)">{{ tg }}</button>
        <span class="muted">可多选；不选=不限</span>
      </div>
    </div>

    <p v-if="txs.length === 0" class="muted">
      {{ hasFilter ? '没有符合筛选条件的流水。' : '还没有流水。' }}
    </p>
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

    <!-- 分页 -->
    <div class="tx-pager" v-if="state.txTotal > 0">
      <span class="muted">第 {{ state.txPage }} / {{ totalPages }} 页</span>
      <select :value="state.txPageSize" @change="setTxPageSize(Number($event.target.value))" title="每页条数">
        <option :value="10">10 条 / 页</option>
        <option :value="20">20 条 / 页</option>
        <option :value="50">50 条 / 页</option>
      </select>
      <button type="button" class="ghost tiny" :disabled="state.txPage <= 1" @click="setTxPage(1)">首页</button>
      <button type="button" class="ghost tiny" :disabled="state.txPage <= 1"
              @click="setTxPage(state.txPage - 1)">上一页</button>
      <button type="button" class="ghost tiny" :disabled="state.txPage >= totalPages"
              @click="setTxPage(state.txPage + 1)">下一页</button>
      <button type="button" class="ghost tiny" :disabled="state.txPage >= totalPages"
              @click="setTxPage(totalPages)">末页</button>
    </div>
  </section>
</template>
