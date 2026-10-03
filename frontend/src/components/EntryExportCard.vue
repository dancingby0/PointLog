<script setup>
// 打卡记录导出：按"从几号到几号"导出 JSON（记录按归属日 + 时间升序，早 → 晚）
// 默认落到项目根的 exports/ 目录；也可选择下载到浏览器
import { ref } from "vue";
import { exportEntries, downloadEntries } from "../store";
import { toDateStr, fromDateStr, formatDuration } from "../utils";

const from = ref("");
const to = ref(toDateStr(new Date()));
const busy = ref(false);
const msg = ref("");
const err = ref("");

// 快捷区间
function lastDays(n) {
  const end = new Date();
  const start = new Date(end.getTime() - (n - 1) * 86400000);
  from.value = toDateStr(start);
  to.value = toDateStr(end);
}

function thisMonth() {
  const d = new Date();
  from.value = toDateStr(new Date(d.getFullYear(), d.getMonth(), 1));
  to.value = toDateStr(d);
}

function all() {
  from.value = "";
  to.value = "";
}

function valid() {
  if (from.value && to.value
      && fromDateStr(from.value).getTime() > fromDateStr(to.value).getTime()) {
    err.value = "起始日期不能晚于结束日期";
    return false;
  }
  return true;
}

async function run(fn) {
  if (busy.value || !valid()) return;
  busy.value = true;
  msg.value = "";
  err.value = "";
  try {
    msg.value = await fn();
  } catch (e) {
    err.value = "导出失败：" + e.message;
  } finally {
    busy.value = false;
  }
}

const save = () => run(async () => {
  const r = await exportEntries(from.value, to.value);
  const dur = r.total_duration_min ? `，时长合计 ${formatDuration(r.total_duration_min)}` : "";
  return `已导出 ${r.entry_count} 条记录（${r.day_count} 天 / ${r.total_points} 点${dur}，`
    + `${r.bytes} 字节）→ ${r.rel_path}`;
});

const download = () => run(async () => {
  const name = await downloadEntries(from.value, to.value);
  return `已下载 ${name}`;
});
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>⬇️ 导出打卡记录</h2>
      <span class="muted">按归属日 + 时间升序（早 → 晚）</span>
    </div>
    <p class="muted" style="margin:0 0 10px">
      导出记录的内容、点数、时段与消耗时长，默认保存到项目的 <code>exports/</code> 目录。
      日期区间含首尾两天（按凌晨 4 点归属日）；留空＝不限（导出全部）。
    </p>

    <div class="export-row">
      <input type="date" v-model="from" aria-label="起始日期">
      <span class="muted">→</span>
      <input type="date" v-model="to" aria-label="结束日期">
      <button type="button" :disabled="busy" @click="save">
        {{ busy ? "导出中…" : "导出到 exports/" }}
      </button>
      <button type="button" class="ghost" :disabled="busy" @click="download">下载到浏览器</button>
    </div>

    <div class="export-row">
      <button type="button" class="ghost" @click="lastDays(7)">近 7 天</button>
      <button type="button" class="ghost" @click="lastDays(30)">近 30 天</button>
      <button type="button" class="ghost" @click="thisMonth">本月</button>
      <button type="button" class="ghost" @click="all">全部</button>
    </div>

    <p v-if="msg" class="export-msg">{{ msg }}</p>
    <p v-if="err" class="export-msg error">{{ err }}</p>
  </section>
</template>
