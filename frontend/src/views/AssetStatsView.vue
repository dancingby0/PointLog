<script setup>
// 资产统计：账户/标签/收支/日期多筛选 + 粒度可调；折线（收入支出趋势）+ 饼图（标签占比）
import { computed, onMounted, reactive } from "vue";
import EChart from "../components/EChart.vue";
import { state, loadAssetAnalysis } from "../store";
import { toDateStr } from "../utils";

const GRANS = [
  { value: "day", label: "按日" },
  { value: "month", label: "按月" },
  { value: "year", label: "按年" },
];
const FLOWS = [
  { value: "both", label: "收支都看" },
  { value: "income", label: "只看收入" },
  { value: "expense", label: "只看支出" },
];

function daysAgoStr(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toDateStr(d);
}
function monthsAgoStr(n) {
  const d = new Date();
  d.setMonth(d.getMonth() - n);
  return toDateStr(d);
}

const filters = reactive({
  from: monthsAgoStr(11),
  to: toDateStr(new Date()),
  granularity: "month",
  accounts: [],       // 账户多选（空=不限）
  tags: [],           // 标签多选（空=不限）
  flow: "both",       // income | expense | both
});

const tagOptions = computed(() => [...new Set([...state.assetTags, ...state.txTags])].sort());

async function refresh() {
  await loadAssetAnalysis({ ...filters });
}

function toggleItem(key, value) {
  const arr = filters[key];
  const i = arr.indexOf(value);
  if (i >= 0) arr.splice(i, 1);
  else arr.push(value);
  refresh();
}

function quick(kind) {
  if (kind === "30d") {
    filters.from = daysAgoStr(29);
    filters.to = toDateStr(new Date());
    filters.granularity = "day";
  } else if (kind === "12m") {
    filters.from = monthsAgoStr(11);
    filters.to = toDateStr(new Date());
    filters.granularity = "month";
  } else if (kind === "y") {
    filters.from = `${new Date().getFullYear()}-01-01`;
    filters.to = toDateStr(new Date());
    filters.granularity = "month";
  } else if (kind === "all") {
    filters.from = "2000-01-01";
    filters.to = toDateStr(new Date());
    filters.granularity = "year";
  }
  refresh();
}

function resetAll() {
  filters.from = monthsAgoStr(11);
  filters.to = toDateStr(new Date());
  filters.granularity = "month";
  filters.accounts = [];
  filters.tags = [];
  filters.flow = "both";
  refresh();
}

// ---- 折线图：收入 / 支出趋势 ----
const showIncome = computed(() => filters.flow !== "expense");
const showExpense = computed(() => filters.flow !== "income");

const lineOption = computed(() => {
  const rows = state.assetStats?.series || [];
  const labels = rows.map((r) => r.label);
  const series = [];
  if (showIncome.value) {
    series.push({
      name: "收入", type: "line", smooth: true, symbolSize: 6,
      data: rows.map((r) => r.income), itemStyle: { color: "#15803d" },
    });
  }
  if (showExpense.value) {
    series.push({
      name: "支出", type: "line", smooth: true, symbolSize: 6,
      data: rows.map((r) => r.expense), itemStyle: { color: "#dc2626" },
    });
  }
  return {
    tooltip: { trigger: "axis", valueFormatter: (v) => "¥" + Number(v).toFixed(2) },
    legend: { data: series.map((s) => s.name), top: 0 },
    grid: { left: 58, right: 18, top: 34, bottom: labels.length > 14 ? 56 : 34 },
    xAxis: {
      type: "category", data: labels, boundaryGap: false,
      axisLabel: { rotate: labels.length > 14 ? 45 : 0, fontSize: 11 },
    },
    yAxis: { type: "value", axisLabel: { formatter: (v) => "¥" + v } },
    series,
  };
});

// ---- 饼图：标签占比 ----
function pieOption(list, name) {
  return {
    tooltip: { trigger: "item", formatter: "{b}<br>¥{c}（{d}%）" },
    legend: { type: "scroll", orient: "vertical", right: 0, top: 8, bottom: 8, textStyle: { fontSize: 11 } },
    series: [{
      name, type: "pie", radius: ["42%", "68%"], center: ["36%", "52%"],
      avoidLabelOverlap: true,
      label: { formatter: "{b}\n{d}%", fontSize: 11 },
      data: list.map((x) => ({ name: x.tag, value: x.amount })),
    }],
  };
}
const pieIncome = computed(() => pieOption(state.assetStats?.tag_income || [], "收入标签"));
const pieExpense = computed(() => pieOption(state.assetStats?.tag_expense || [], "支出标签"));
const hasIncomeData = computed(() => (state.assetStats?.tag_income || []).length > 0);
const hasExpenseData = computed(() => (state.assetStats?.tag_expense || []).length > 0);

const money = (n) => "¥" + Number(n || 0).toFixed(2);

onMounted(refresh);
</script>

<template>
  <div class="views">
    <h1 style="margin-bottom:12px">资产统计</h1>

    <!-- 筛选区 -->
    <section class="card">
      <div class="tx-filters">
        <div class="tx-filter-row">
          <span class="tx-filter-label">日期</span>
          <input type="date" v-model="filters.from" @change="refresh">
          <span class="muted">至</span>
          <input type="date" v-model="filters.to" @change="refresh">
          <button type="button" class="ghost tiny" @click="quick('30d')">近 30 天</button>
          <button type="button" class="ghost tiny" @click="quick('12m')">近 12 个月</button>
          <button type="button" class="ghost tiny" @click="quick('y')">今年</button>
          <button type="button" class="ghost tiny" @click="quick('all')">全部（按年）</button>
        </div>
        <div class="tx-filter-row">
          <span class="tx-filter-label">粒度</span>
          <button v-for="g in GRANS" :key="g.value" type="button" class="chip"
                  :class="{ on: filters.granularity === g.value }"
                  @click="filters.granularity = g.value; refresh()">{{ g.label }}</button>
        </div>
        <div class="tx-filter-row">
          <span class="tx-filter-label">收支</span>
          <button v-for="f in FLOWS" :key="f.value" type="button" class="chip"
                  :class="{ on: filters.flow === f.value }"
                  @click="filters.flow = f.value; refresh()">{{ f.label }}</button>
        </div>
        <div class="tx-filter-row">
          <span class="tx-filter-label">账户</span>
          <template v-if="state.accounts.length">
            <button v-for="a in state.accounts" :key="a.id" type="button" class="chip"
                    :class="{ on: filters.accounts.includes(a.id) }"
                    @click="toggleItem('accounts', a.id)">{{ a.name }}</button>
          </template>
          <span v-else class="muted">（还没有账户）</span>
          <span class="muted">可多选；不选=不限</span>
        </div>
        <div class="tx-filter-row">
          <span class="tx-filter-label">标签</span>
          <template v-if="tagOptions.length">
            <button v-for="t in tagOptions" :key="t" type="button" class="chip"
                    :class="{ on: filters.tags.includes(t) }"
                    @click="toggleItem('tags', t)">{{ t }}</button>
          </template>
          <span v-else class="muted">（还没有标签）</span>
          <span class="muted">可多选；不选=不限</span>
        </div>
        <div class="tx-filter-row">
          <button type="button" class="ghost tiny" @click="resetAll">重置全部筛选</button>
        </div>
      </div>

      <div class="as-summary" v-if="state.assetStats">
        <span>区间：{{ state.assetStats.from }} ~ {{ state.assetStats.to }}</span>
        <span v-if="showIncome">收入 <b class="up">{{ money(state.assetStats.totals.income) }}</b></span>
        <span v-if="showExpense">支出 <b class="down">{{ money(state.assetStats.totals.expense) }}</b></span>
        <span v-if="filters.flow === 'both'">净额 <b>{{ money(state.assetStats.totals.net) }}</b></span>
      </div>
    </section>

    <!-- 折线图 -->
    <section class="card">
      <div class="card-head">
        <h2>收入 / 支出趋势</h2>
        <span class="muted">{{ (GRANS.find((g) => g.value === filters.granularity) || {}).label }}</span>
      </div>
      <div class="as-line">
        <EChart :option="lineOption" />
      </div>
    </section>

    <!-- 饼图：标签占比 -->
    <section class="card">
      <div class="card-head">
        <h2>标签占比</h2>
        <span class="muted">一笔多标签按标签数均摊；无标签计入"未分类"</span>
      </div>
      <div class="as-pie-grid">
        <div v-if="showIncome" class="as-pie">
          <h3>收入标签</h3>
          <div class="as-pie-chart" v-if="hasIncomeData"><EChart :option="pieIncome" /></div>
          <p v-else class="muted">区间内暂无收入。</p>
        </div>
        <div v-if="showExpense" class="as-pie">
          <h3>支出标签</h3>
          <div class="as-pie-chart" v-if="hasExpenseData"><EChart :option="pieExpense" /></div>
          <p v-else class="muted">区间内暂无支出。</p>
        </div>
      </div>
    </section>
  </div>
</template>

