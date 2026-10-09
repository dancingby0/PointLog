<script setup>
import { computed, ref } from "vue";
import {
  state, submitEntry, endEdit, submitSleep,
  applyDuration, setEndNow, unlockDuration,
  onSpanStartChanged, onSpanEndChanged,
} from "../store";
import { minutesBetween, formatDuration, toLocalInput } from "../utils";
import TagSelect from "./TagSelect.vue";

async function onAddDiaryTag(tag) {
  try {
    await fetch("/api/tags/diary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag }),
    });
    // 同步最新池（简单再拉一次）
    const res = await fetch("/api/tags/diary");
    const data = await res.json();
    if (res.ok) state.diaryTags = data.tags;
  } catch (err) {
    console.error(err);
  }
}

// 用时快捷（分钟）：点一下 ＝ 结束（缺省＝现在）减去该用时，自动填入开始时间
const QUICK_MIN = [15, 30, 45, 60, 90, 120];
const customMin = ref("");

function applyCustomDuration() {
  applyDuration(customMin.value);
}

// 清空时段（＝本条不选时间，只记录）并解除时长锁定
function clearSpan() {
  state.form.start = "";
  state.form.end = "";
  unlockDuration();
}

// 当前填出的用时（未填 / 结束早于开始 → null；同一时刻 → 0），用于实时提示
const spanMinutes = computed(() => minutesBetween(state.form.start, state.form.end));

// ---- 睡眠快捷记录（入睡 / 起床，起床不晚于入睡时自动跨到次日） ----
const sleepFrom = ref("23:00");
const sleepTo = ref("07:00");
const sleepBase = ref("auto");   // 入睡日基准：自动（跨零点→昨晚；否则→今天） / 昨晚 / 今天

async function onSleepSubmit() {
  if (!sleepFrom.value || !sleepTo.value) {
    alert("请填写入睡与起床时间");
    return;
  }
  if (!state.diaryTags.includes("睡眠")) await onAddDiaryTag("睡眠");
  await submitSleep(sleepFrom.value, sleepTo.value, sleepBase.value);
}

// 只记此刻：起止＝现在（0 时长，只记时间点、不计时长）
function pointNow() {
  const now = toLocalInput(new Date());
  state.form.start = now;
  state.form.end = now;
  state.form.lockMin = null;
}
</script>

<template>
  <form class="card" @submit.prevent="submitEntry">
    <h2>{{ state.editingId ? '编辑打卡' : '新增打卡' }}</h2>
    <label>做什么（一句话）
      <input v-model.trim="state.form.content" type="text" maxlength="100" placeholder="例：背完30个英语单词">
    </label>
    <label>点数（0＝只记录，不做激励）
      <input v-model.number="state.form.points" type="number" min="0" step="1" placeholder="1">
    </label>
    <label class="label-block">类别（可选）
      <TagSelect :tags="state.diaryTags" v-model="state.form.category" @add-tag="onAddDiaryTag" />
    </label>
    <label class="label-block">时段（可选，默认不选：从 xx 起到 xx 结束）
      <div class="span-row">
        <input v-model="state.form.start" @change="onSpanStartChanged" type="datetime-local" aria-label="开始时间">
        <span class="muted">→</span>
        <input v-model="state.form.end" @change="onSpanEndChanged" type="datetime-local" aria-label="结束时间">
        <button type="button" class="ghost tiny" @click="setEndNow"
                title="结束设为此刻；开始未填（或晚于此刻）时按 30 分钟回推">⏱ 现在结束</button>
        <button type="button" class="ghost tiny" @click="clearSpan"
                v-if="state.form.start || state.form.end">清空</button>
      </div>
    </label>
    <div class="span-quick">
      <span class="muted">填用时：</span>
      <button v-for="m in QUICK_MIN" :key="m" type="button" class="ghost tiny"
              :class="{ on: state.form.lockMin === m }" @click="applyDuration(m)"
              :title="`结束（缺省＝现在）减去 ${formatDuration(m)}，自动填入开始时间`">
        {{ formatDuration(m) }}
      </button>
      <input class="dur-input" v-model.number="customMin" type="number" min="1" step="5"
             placeholder="自定义" aria-label="自定义用时（分钟）"
             @keydown.enter.prevent="applyCustomDuration">
      <span class="muted">分钟</span>
      <button type="button" class="ghost tiny" @click="applyCustomDuration">按此时长</button>
      <button type="button" class="ghost tiny" @click="pointNow"
              title="起止都设为此刻：0 时长，只记时间点、不计时长">📍 只记此刻</button>
      <button v-if="state.form.lockMin" type="button" class="ghost tiny" @click="unlockDuration"
              title="解除后：开始 / 结束各自独立编辑">🔗 已锁定时长 {{ formatDuration(state.form.lockMin) }} · 解除</button>
    </div>
    <div class="sleep-quick">
      <span class="muted">🌙 记睡眠：</span>
      <input v-model="sleepFrom" type="time" aria-label="入睡时间">
      <span class="muted">→</span>
      <input v-model="sleepTo" type="time" aria-label="起床时间">
      <select v-model="sleepBase" aria-label="入睡日期基准">
        <option value="auto">自动</option>
        <option value="yesterday">昨晚</option>
        <option value="today">今天</option>
      </select>
      <button type="button" class="ghost tiny" @click="onSleepSubmit">记一条</button>
      <span class="muted">（起床早于入睡时自动跨到次日；归属到入睡那天）</span>
    </div>
    <label class="label-block">归属时刻（可选；决定记到哪一天）
      <input v-model="state.form.ts" type="datetime-local">
    </label>
    <p class="muted span-hint">
      <template v-if="spanMinutes != null">
        {{ spanMinutes === 0 ? '0 时长：只记时间点、不计时长；' : `本时段用时 ${formatDuration(spanMinutes)}；` }}
      </template>
      填了时段就会在记录里显示消耗时长（留空＝只记录内容与点数）。
      归属时刻留空＝自动（填了时段取时段开始，否则＝现在）。
    </p>
    <button type="submit">{{ state.editingId ? '保存修改' : '提交' }}</button>
    <button type="button" class="ghost" v-if="state.editingId" @click="endEdit">取消编辑</button>
  </form>
</template>

