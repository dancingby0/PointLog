<script setup>
// 活动数据页（v2.6）：ActivityWatch 桌面活动的读取、同步与展示。
// 设计原则：ActivityWatch 未安装/未启动时，本页只显示"未连接 + 安装指引"，不影响其他页面。
import { computed, onMounted, ref } from "vue";
import EChart from "../components/EChart.vue";
import {
  state,
  todayStr,
  loadActivityStatus,
  loadActivityRange,
  loadActivityDay,
  syncActivity,
  loadActivityConfig,
  saveActivityConfig,
} from "../store";
import { formatClock, formatMinutesCompact } from "../utils";

const status = computed(() => state.activityStatus);
const day = computed(() => state.activityDay);

// 模板里用短名字，逻辑放在 utils.js（可单测）
const fmtMin = formatMinutesCompact;
const fmtTime = formatClock;

const dayInput = ref("");
const rules = ref([]);
const cfg = ref({ base_url: "", host: "", gap_allow_sec: 120, ignored_apps: "" });
const cfgMsg = ref("");
const cfgErr = ref("");

const PALETTE = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
                 "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#64748b"];

function shiftDay(delta) {
  const base = dayInput.value || todayStr();
  const d = new Date(`${base}T12:00`);
  d.setDate(d.getDate() + delta);
  dayInput.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  loadActivityDay(dayInput.value);
}

async function onDayChange() {
  if (dayInput.value) await loadActivityDay(dayInput.value);
}

async function doSync(days) {
  try {
    await syncActivity(days);
    dayInput.value = state.activityDayKey;
  } catch (err) {
    console.warn("同步活动数据失败：", err.message);   // 详细原因已显示在状态卡
  }
}

async function refreshStatus() {
  await loadActivityStatus();
  await loadActivityRange();
  if (state.activityDayKey) await loadActivityDay(state.activityDayKey);
}

async function loadCfg() {
  await loadActivityConfig();
  const c = state.activityConfig || {};
  cfg.value = {
    base_url: c.base_url || "http://127.0.0.1:5600",
    host: c.host || "",
    gap_allow_sec: c.gap_allow_sec ?? 120,
    ignored_apps: (c.ignored_apps || []).join(", "),
  };
  rules.value = (c.rules || []).map((r) => ({
    category: r.category || "", app: r.app || "", title: r.title || "", url: r.url || "",
  }));
}

async function saveCfg() {
  cfgErr.value = "";
  cfgMsg.value = "";
  try {
    await saveActivityConfig({
      base_url: cfg.value.base_url,
      host: cfg.value.host,
      gap_allow_sec: Number(cfg.value.gap_allow_sec) || 0,
      ignored_apps: String(cfg.value.ignored_apps || "")
        .split(",").map((s) => s.trim()).filter(Boolean),
      rules: rules.value.filter((r) => r.category.trim()),
    });
    cfgMsg.value = "已保存（下次同步生效）";
  } catch (err) {
    cfgErr.value = err.message;
  }
}

function addRule() {
  rules.value.push({ category: "", app: "", title: "", url: "" });
}

function removeRule(i) {
  rules.value.splice(i, 1);
}

// 应用 Top（横向条形）
const appsOption = computed(() => {
  const apps = (day.value?.apps || []).slice(0, 8).reverse();
  return {
    tooltip: { trigger: "axis", valueFormatter: (v) => `${Math.round(v)} 分钟` },
    grid: { left: 90, right: 24, top: 10, bottom: 24 },
    xAxis: { type: "value", axisLabel: { formatter: "{value}m" } },
    yAxis: { type: "category", data: apps.map((a) => a.app), axisLabel: { fontSize: 11 } },
    series: [{
      type: "bar", barWidth: "60%",
      data: apps.map((a) => a.min),
      itemStyle: { color: "#3b82f6", borderRadius: [0, 3, 3, 0] },
    }],
  };
});

// 类别占比（环形）
const catOption = computed(() => {
  const cats = day.value?.categories || [];
  return {
    tooltip: { trigger: "item", valueFormatter: (v) => `${Math.round(v)} 分钟` },
    legend: { type: "scroll", bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: "pie", radius: ["38%", "65%"], center: ["50%", "45%"],
      itemStyle: { borderRadius: 4, borderColor: "#fff", borderWidth: 1 },
      label: { show: false },
      data: cats.map((c, i) => ({
        name: c.category, value: c.min,
        itemStyle: { color: PALETTE[i % PALETTE.length] },
      })),
    }],
  };
});

onMounted(async () => {
  await loadActivityStatus();
  await loadActivityRange();
  dayInput.value = state.activityDayKey || todayStr();
  await loadActivityDay(dayInput.value);
  await loadCfg();
});
</script>

<template>
  <div class="views">
    <!-- 连接状态 + 同步 -->
    <section class="card">
      <div class="card-head">
        <h2>桌面活动 · ActivityWatch</h2>
        <span class="act-state" :class="status && status.connected ? 'ok' : 'off'">
          {{ status && status.connected ? "已连接" : "未连接" }}
        </span>
      </div>
      <p class="muted" v-if="status">
        {{ status.base_url }} · 已同步 {{ status.synced_days }} 天
        <span v-if="status.last_imported_at">
          · 最近 {{ status.last_imported_at.slice(0, 16).replace("T", " ") }}
        </span>
      </p>
      <p class="error" v-if="state.activityError">{{ state.activityError }}</p>
      <p class="muted" v-if="status && status.hint">{{ status.hint }}</p>

      <div class="act-actions">
        <button type="button" :disabled="state.activityBusy" @click="doSync(1)">同步今天</button>
        <button type="button" :disabled="state.activityBusy" @click="doSync(7)">近 7 天</button>
        <button type="button" :disabled="state.activityBusy" @click="doSync(30)">近 30 天</button>
        <button type="button" class="ghost" @click="refreshStatus">重新检测</button>
        <span class="muted" v-if="state.activityBusy">同步中…</span>
      </div>

      <div class="act-buckets" v-if="status && status.buckets.length">
        <span v-for="b in status.buckets" :key="b.id" class="tag-chip">
          {{ b.type }}<span class="muted" v-if="status.picked.window === b.id"> ·窗口</span>
          <span class="muted" v-if="status.picked.afk === b.id"> ·AFK</span>
          <span class="muted" v-if="status.picked.web === b.id"> ·网页</span>
        </span>
      </div>
      <p class="muted" v-if="status && !status.connected">
        需要本机运行 <a href="https://activitywatch.net/" target="_blank" rel="noreferrer">ActivityWatch</a>
        （默认 http://127.0.0.1:5600）。想让网页区分到具体站点，再装官方扩展 aw-watcher-web。
      </p>
    </section>

    <!-- 每日明细 -->
    <section class="card">
      <div class="card-head">
        <h2>每日明细</h2>
        <div class="day-controls">
          <button type="button" class="ghost tiny" @click="shiftDay(-1)">← 前一天</button>
          <input type="date" v-model="dayInput" @change="onDayChange" />
          <button type="button" class="ghost tiny" @click="shiftDay(1)">后一天 →</button>
        </div>
      </div>

      <template v-if="day">
        <div class="stat-cards">
          <div class="stat-card accent">
            <div class="stat-num">{{ fmtMin(day.active_min) }}</div>
            <div class="stat-label">活跃时长</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ fmtTime(day.first_ts) }}–{{ fmtTime(day.last_ts) }}</div>
            <div class="stat-label">首末活跃</div>
          </div>
          <div class="stat-card">
            <div class="stat-num">{{ (day.sites || []).length }}</div>
            <div class="stat-label">网站数</div>
          </div>
          <div class="stat-card" v-if="day.excluded_min">
            <div class="stat-num">{{ fmtMin(day.excluded_min) }}</div>
            <div class="stat-label">已忽略应用</div>
          </div>
        </div>

        <div class="dist-row">
          <div class="act-chart-box">
            <div class="card-head"><h3>应用 Top</h3></div>
            <div class="dist-chart-sm"><EChart :option="appsOption" /></div>
          </div>
          <div class="act-chart-box">
            <div class="card-head"><h3>类别占比</h3></div>
            <div class="dist-chart-sm"><EChart :option="catOption" /></div>
          </div>
        </div>

        <div class="act-table" v-if="day.sites && day.sites.length">
          <div class="card-head"><h3>网站</h3><span class="muted">需要 aw-watcher-web，只算活动标签页</span></div>
          <ul class="entry-list">
            <li v-for="s in day.sites" :key="s.domain" class="entry">
              <span class="entry-content">{{ s.domain }}<span class="entry-cat">{{ s.category }}</span>
                <span v-if="s.audible" title="该标签页在出声（背景播放）">🔊</span></span>
              <span class="entry-points">{{ fmtMin(s.min) }}</span>
            </li>
          </ul>
        </div>

        <div class="act-table" v-if="day.pages && day.pages.length">
          <div class="card-head">
            <h3>具体页面</h3><span class="muted">同域名按标题拆开（区分"B 站课程"和"B 站娱乐"）</span>
          </div>
          <ul class="entry-list">
            <li v-for="(p, i) in day.pages" :key="i" class="entry">
              <span class="entry-content">{{ p.title || "(无标题)" }}<span class="muted"> · {{ p.domain }}</span></span>
              <span class="entry-points">{{ fmtMin(p.min) }}</span>
            </li>
          </ul>
        </div>

        <div class="act-table" v-if="day.apps && day.apps.length">
          <div class="card-head"><h3>应用</h3></div>
          <ul class="entry-list">
            <li v-for="a in day.apps" :key="a.app" class="entry">
              <span class="entry-content">{{ a.app }}<span class="entry-cat">{{ a.category }}</span></span>
              <span class="entry-points">{{ fmtMin(a.min) }}</span>
            </li>
          </ul>
        </div>
      </template>

      <p class="muted" v-else>
        {{ state.activityError || "这一天还没有活动数据，点上面的同步按钮拉取。" }}
      </p>
    </section>
    <!-- 设置：地址 + 类别规则 -->
    <section class="card">
      <div class="card-head">
        <h2>活动数据设置</h2>
        <span class="muted">规则自上而下、首个命中生效；同一行填多个字段＝必须同时满足</span>
      </div>
      <div class="act-cfg-row">
        <label>ActivityWatch 地址
          <input type="text" v-model="cfg.base_url" placeholder="http://127.0.0.1:5600" />
        </label>
        <label>主机名（多机时填，留空自动挑）
          <input type="text" v-model="cfg.host" placeholder="我的台式机" />
        </label>
        <label>连续判定阈值（秒）
          <input type="number" v-model.number="cfg.gap_allow_sec" min="0" max="3600" />
        </label>
      </div>
      <label class="label-block">不统计的应用（逗号分隔，子串匹配）
        <input type="text" v-model="cfg.ignored_apps" placeholder="activitywatch, pointlog" />
      </label>

      <div class="card-head" style="margin-top:16px">
        <h3>类别规则</h3>
        <span class="muted">app / title / url 填正则；例：url=bilibili ＋ title=课程 → 学习</span>
      </div>
      <div class="act-rules">
        <div class="act-rule-row act-rule-head">
          <span>类别</span><span>应用(app)</span><span>标题(title)</span><span>网址(url)</span><span></span>
        </div>
        <div class="act-rule-row" v-for="(r, i) in rules" :key="i">
          <input type="text" v-model="r.category" placeholder="学习" />
          <input type="text" v-model="r.app" placeholder="code|pycharm" />
          <input type="text" v-model="r.title" placeholder="课程|教程" />
          <input type="text" v-model="r.url" placeholder="bilibili\.com" />
          <button type="button" class="ghost danger tiny" @click="removeRule(i)">删除</button>
        </div>
      </div>
      <div class="act-actions">
        <button type="button" class="ghost" @click="addRule">+ 添加规则</button>
        <button type="button" @click="saveCfg">保存设置</button>
        <span class="muted" v-if="cfgMsg">{{ cfgMsg }}</span>
        <span class="error" v-if="cfgErr">{{ cfgErr }}</span>
      </div>
    </section>
  </div>
</template>

