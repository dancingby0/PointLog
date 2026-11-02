<script setup>
// 专注统计（v2.8）：从桌面计时器上传的会话里算出来的「今日 / 累计」时长。
// 计时器在桌面端跑（focus_timer.py），这里只展示与"上传/删除"操作。
import { computed } from "vue";
import { state, uploadFocusSession, delFocusSession, loadFocusStats } from "../store";

const stats = computed(() => state.focusStats);
const sessions = computed(() => state.focusSessions || []);

const byLabel = computed(() => (stats.value?.by_label || []).slice(0, 8));
const maxMin = computed(() => Math.max(1, ...byLabel.value.map((x) => x.min)));

function pct(min) {
  return Math.max(2, Math.round((Number(min) || 0) / maxMin.value * 100));
}

function when(iso) {
  if (!iso) return "";
  return iso.slice(5, 16).replace("T", " ");
}

async function doUpload(s) {
  const points = prompt(`上传「${s.label || "未命名"} ${s.elapsed_text}」为打卡，点数：`, "1");
  if (points === null) return;
  const value = Number(points);
  if (!Number.isFinite(value) || value < 0) {
    alert("点数应为非负数字");
    return;
  }
  await uploadFocusSession(s.id, { points: value, label: s.label });
}

async function refresh() {
  await loadFocusStats();
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>专注统计</h2>
      <span class="muted">来自桌面计时器（focus_timer.py）· 上传后才计入点数</span>
    </div>

    <div class="stat-cards" v-if="stats">
      <div class="stat-card accent">
        <div class="stat-num">{{ stats.today_text }}</div>
        <div class="stat-label">今日专注</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.total_text }}</div>
        <div class="stat-label">累计专注</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.days }}</div>
        <div class="stat-label">累计天数</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.sessions }}</div>
        <div class="stat-label">会话数</div>
      </div>
    </div>

    <div class="focus-labels" v-if="byLabel.length">
      <div v-for="row in byLabel" :key="row.label" class="focus-label-row">
        <span class="focus-label-name">{{ row.label }}</span>
        <span class="focus-bar"><span class="focus-bar-fill" :style="{ width: pct(row.min) + '%' }" /></span>
        <span class="focus-label-time">{{ row.text }}</span>
      </div>
    </div>
    <p class="muted" v-else>还没有可统计的专注会话。运行桌面计时器记一次就会出现在这里。</p>

    <div class="focus-sessions" v-if="sessions.length">
      <div class="card-head" style="margin-top:14px">
        <h3>最近会话</h3>
        <button type="button" class="ghost tiny" @click="refresh">刷新</button>
      </div>
      <ul class="entry-list">
        <li v-for="s in sessions" :key="s.id" class="entry">
          <span class="entry-time">{{ when(s.created_at) }}</span>
          <span class="entry-content">
            {{ s.label || "未命名" }}
            <span class="entry-cat" v-if="s.uploaded">已上传</span>
            <span class="muted" v-else-if="s.state !== 'stopped'">进行中</span>
          </span>
          <span class="entry-points">{{ s.elapsed_text }}</span>
          <button v-if="!s.uploaded && s.state === 'stopped'" type="button"
                  class="ghost tiny" @click="doUpload(s)">上传</button>
          <button type="button" class="delete" @click="delFocusSession(s.id)" title="删除会话">×</button>
        </li>
      </ul>
    </div>
  </section>
</template>
