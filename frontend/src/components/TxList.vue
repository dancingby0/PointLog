<script setup>
import { computed } from "vue";
import { state } from "../store";
import { formatTime } from "../utils";

const typeLabel = { expense: "支出", income: "收入", transfer: "转账", adjust: "校准" };

function acctName(id) {
  const a = state.accounts.find((x) => x.id === id);
  return a ? a.name : id;
}

const txs = computed(() => [...state.txs]);

const fmtMoney = (n) => (Number(n) < 0 ? "-" : "") + "¥" + Math.abs(Number(n)).toFixed(2);
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
        </div>
      </li>
    </ul>
  </section>
</template>
