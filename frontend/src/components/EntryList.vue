<script setup>
import { computed } from "vue";
import { state, selectedLabel, startEdit, delEntry } from "../store";
import { formatTime, formatClock, formatDuration, toDateStr } from "../utils";

const sortedEntries = computed(() =>
  [...state.entries].sort((a, b) => {
    const av = new Date(a.start_ts || a.ts).getTime();
    const bv = new Date(b.start_ts || b.ts).getTime();
    if (av !== bv) return bv - av;              // 时间降序（新 → 旧）
    return a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0;
  })
);

// 当日已记录的消耗时长合计（仅有填时段的记录）
const totalDuration = computed(() =>
  state.entries.reduce((sum, e) => sum + (e.duration_min || 0), 0)
);
const hasDuration = computed(() => state.entries.some((e) => (e.duration_min || 0) > 0));

// 时段文本：09:00–10:30；跨天（如睡眠）标"次日"；0 时长只显示一个时刻；
// 未选时间则退回显示记录时刻
function timeText(e) {
  if (e.start_ts && e.end_ts) {
    const s = new Date(e.start_ts);
    const t = new Date(e.end_ts);
    if (s.getTime() === t.getTime()) return formatClock(e.start_ts);
    const cross = toDateStr(s) !== toDateStr(t);
    return `${formatClock(e.start_ts)}${cross ? "–次日" : "–"}${formatClock(e.end_ts)}`;
  }
  return formatTime(e.ts);
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>{{ selectedLabel() }} 的记录</h2>
      <span v-if="hasDuration" class="muted">已记录时长合计 {{ formatDuration(totalDuration) }}</span>
    </div>
    <p v-if="sortedEntries.length === 0" class="muted">这一天还没有记录。</p>
    <ul v-else class="entry-list">
      <li v-for="e in sortedEntries" :key="e.id" class="entry">
        <span class="entry-time" :title="e.start_ts ? '时段' : '记录时刻（本条未选时间）'">
          {{ timeText(e) }}
        </span>
        <span class="entry-content">{{ e.content }}</span>
        <span v-if="e.category" class="entry-cat">{{ e.category }}</span>
        <span v-if="e.duration_min > 0" class="entry-duration">用时 {{ formatDuration(e.duration_min) }}</span>
        <span class="entry-points">{{ e.points > 0 ? '+' + e.points : '0 点' }}</span>
        <button class="edit" @click="startEdit(e)">编辑</button>
        <button class="delete" @click="delEntry(e)">×</button>
      </li>
    </ul>
  </section>
</template>
