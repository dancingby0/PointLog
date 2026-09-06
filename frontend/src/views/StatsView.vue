<script setup>
import { computed, onMounted } from "vue";
import { state, loadStatsSummary } from "../store";

const RANGES = [
  { key: "week", label: "本周" },
  { key: "month", label: "本月" },
  { key: "year", label: "本年" },
  { key: "all", label: "全部" },
];

async function changeRange(r) {
  state.statsRange = r;
  await loadStatsSummary();
}

const s = computed(() => state.statsSummary);

// 最近 30 天打卡格（streak 视觉）
const last30 = computed(() => {
  if (!s.value) return [];
  const today = new Date();
  const cells = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    // start<=day<=end 判断该天是否在统计范围内且有点
    const on = iso >= s.value.start && iso <= s.value.end;
    cells.push({ iso, on, isToday: i === 0 });
  }
  return cells;
});

onMounted(loadStatsSummary);
</script>

<template>
  <div class="views">
    <div class="page-head">
      <h1 style="margin-bottom:0">统计</h1>
      <div class="range-switch">
        <button v-for="r in RANGES" :key="r.key" type="button"
                :class="{ on: state.statsRange === r.key }" @click="changeRange(r.key)">
          {{ r.label }}
        </button>
      </div>
    </div>

    <template v-if="s">
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-num">{{ s.total_days }}</div>
          <div class="stat-label">打卡天数</div>
        </div>
        <div class="stat-card accent">
          <div class="stat-num">{{ s.period_points }}</div>
          <div class="stat-label">期间点数</div>
        </div>
        <div class="stat-card fire">
          <div class="stat-num">🔥 {{ s.current_streak }}</div>
          <div class="stat-label">当前连续</div>
        </div>
        <div class="stat-card">
          <div class="stat-num">{{ s.longest_streak }}</div>
          <div class="stat-label">最长连续</div>
        </div>
      </div>

      <section class="card">
        <div class="card-head">
          <h2>近 30 天打卡</h2>
          <span class="muted">绿点 = 有打卡 · 圈 = 今天</span>
        </div>
        <div class="streak-cells">
          <span v-for="(c, i) in last30" :key="i" class="scell"
                :class="{ fill: c.on, today: c.isToday }"
                :title="c.iso"></span>
        </div>
        <p class="muted" style="margin-top:10px">期间写了 {{ s.notes_days }} 天感想。</p>
      </section>
    </template>
    <p v-else class="muted">加载统计中…</p>
  </div>
</template>
