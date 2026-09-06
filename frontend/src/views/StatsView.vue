<script setup>
import { computed, onMounted } from "vue";
import EChart from "../components/EChart.vue";
import { state, loadStatsSummary, loadStatsDist, loadStatsTrend } from "../store";

const RANGES = [
  { key: "week", label: "本周" },
  { key: "month", label: "本月" },
  { key: "year", label: "本年" },
  { key: "all", label: "全部" },
];

async function changeRange(r) {
  state.statsRange = r;
  await loadStatsSummary();
  await loadStatsDist();
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

// 月度趋势 option（ECharts 柱 + 感想线）
const trendOption = computed(() => {
  const labels = state.statsTrend.map((x) => x.label);
  const points = state.statsTrend.map((x) => x.points);
  const notes = state.statsTrend.map((x) => x.notes_days);
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 30, bottom: 24 },
    xAxis: { type: "category", data: labels, axisLabel: { interval: 0, rotate: 30, fontSize: 10 } },
    yAxis: { type: "value", minInterval: 1 },
    series: [
      {
        name: "点数", type: "bar", data: points,
        itemStyle: { color: "#3b82f6", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "感想天数", type: "line", data: notes, smooth: true,
        itemStyle: { color: "#f59e0b" }, lineStyle: { color: "#f59e0b" },
      },
    ],
    legend: { top: 0, data: ["点数", "感想天数"] },
  };
});

// 标签占比（环形）
const tagOption = computed(() => {
  const tags = state.statsDist?.tags || [];
  const palette = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];
  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} 点 ({d}%)" },
    legend: { type: "scroll", bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      name: "类别点数", type: "pie", radius: ["38%", "65%"],
      center: ["50%", "45%"],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: "#fff", borderWidth: 1 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 13, fontWeight: "bold" } },
      data: tags.map((t, i) => ({
        name: t.tag, value: t.points,
        itemStyle: { color: palette[i % palette.length] },
      })),
    }],
    title: { text: tags.length === 0 ? "暂无带标签的记录" : "", left: "center", top: "middle", textStyle: { fontSize: 12, color: "#aaa" } },
  };
});

// 星期分布（条形）
const weekdayOption = computed(() => {
  const wd = state.statsDist?.weekdays || [];
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 12, top: 10, bottom: 24 },
    xAxis: { type: "category", data: wd.map((x) => x.label) },
    yAxis: { type: "value", minInterval: 1 },
    series: [{
      name: "点数", type: "bar", barWidth: "55%",
      data: wd.map((x) => x.points),
      itemStyle: { color: "#10b981", borderRadius: [3, 3, 0, 0] },
    }],
  };
});

// 时段分布（条形）
const periodOption = computed(() => {
  const pd = state.statsDist?.periods || [];
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 12, top: 10, bottom: 24 },
    xAxis: { type: "category", data: pd.map((x) => x.label) },
    yAxis: { type: "value", minInterval: 1 },
    series: [{
      name: "点数", type: "bar", barWidth: "50%",
      data: pd.map((x) => x.points),
      itemStyle: { color: "#f59e0b", borderRadius: [3, 3, 0, 0] },
    }],
  };
});

onMounted(() => {
  loadStatsSummary();
  loadStatsDist();
  loadStatsTrend();
});
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

      <!-- 结构与规律 -->
      <section class="card">
        <div class="card-head">
          <h2>类别占比</h2>
          <span class="muted">带标签的打卡点数分布</span>
        </div>
        <div class="dist-chart">
          <EChart :option="tagOption" />
        </div>
      </section>

      <div class="dist-row">
        <section class="card">
          <div class="card-head"><h2>星期分布</h2></div>
          <div class="dist-chart-sm"><EChart :option="weekdayOption" /></div>
        </section>
        <section class="card">
          <div class="card-head"><h2>时段分布</h2></div>
          <div class="dist-chart-sm"><EChart :option="periodOption" /></div>
        </section>
      </div>

      <section class="card">
        <div class="card-head">
          <h2>近 12 个月趋势</h2>
          <span class="muted">柱 = 每月点数 · 线 = 感想天数</span>
        </div>
        <div class="trend-chart">
          <EChart :option="trendOption" />
        </div>
      </section>
    </template>
    <p v-else class="muted">加载统计中…</p>
  </div>
</template>
