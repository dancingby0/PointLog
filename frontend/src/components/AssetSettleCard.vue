<script setup>
// 平账标记：按天标记"这天的账已经平了"，并可快速查看/清理未平账日期
import { ref } from "vue";
import { state, setDaySettled } from "../store";
import { toDateStr } from "../utils";

const day = ref(toDateStr(new Date()));
const busy = ref(false);

async function mark(settled) {
  busy.value = true;
  await setDaySettled(day.value, settled);
  busy.value = false;
}

const isSettled = (d) => state.settledDays.includes(d);
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>✅ 平账标记</h2>
      <span class="muted">{{ state.unsettledDays.length }} 天未平账</span>
    </div>
    <p class="muted" style="margin:0 0 10px">
      某天的账核对完不必再回头看，就给这天打上"已平账"；流水筛选里可只看未平账的日期。
    </p>

    <div class="settle-row">
      <input type="date" v-model="day">
      <button type="button" :disabled="busy" @click="mark(true)">标记为已平账</button>
      <button type="button" class="ghost" :disabled="busy" @click="mark(false)">取消标记</button>
      <span v-if="isSettled(day)" class="settle-tag on">这天已平账</span>
      <span v-else class="muted">这天未平账</span>
    </div>

    <div class="settle-block">
      <h3>未平账日期（有流水但未标记）</h3>
      <p v-if="!state.unsettledDays.length" class="muted">全部已平账 🎉</p>
      <div v-else class="settle-chips">
        <button v-for="d in state.unsettledDays" :key="d" type="button" class="chip"
                @click="setDaySettled(d, true)" title="点击标记为已平账">{{ d }} ✓</button>
      </div>
    </div>

    <div class="settle-block">
      <h3>已平账日期</h3>
      <p v-if="!state.settledDays.length" class="muted">还没有标记。</p>
      <div v-else class="settle-chips">
        <span v-for="d in state.settledDays" :key="d" class="settle-tag on">
          {{ d }}
          <button type="button" class="tag-x" @click="setDaySettled(d, false)" title="取消平账标记">×</button>
        </span>
      </div>
    </div>
  </section>
</template>
