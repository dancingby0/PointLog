<script setup>
import { computed, ref } from "vue";
import {
  state, submitEntry, endEdit,
  applyDuration, setEndNow, unlockDuration,
  onSpanStartChanged, onSpanEndChanged,
} from "../store";
import { minutesBetween, formatDuration } from "../utils";
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

// 当前填出的用时（未填 / 结束不晚于开始 → null），用于实时提示
const spanMinutes = computed(() => minutesBetween(state.form.start, state.form.end));
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
      <button v-if="state.form.lockMin" type="button" class="ghost tiny" @click="unlockDuration"
              title="解除后：开始 / 结束各自独立编辑">🔗 已锁定时长 {{ formatDuration(state.form.lockMin) }} · 解除</button>
    </div>
    <p class="muted span-hint">
      <template v-if="spanMinutes != null">本时段用时 {{ formatDuration(spanMinutes) }}；</template>
      填了时段就会在记录里显示消耗时长，留空＝只记录内容与点数。
      记录归属到 {{ state.selectedDay }}（凌晨 4 点前算昨日）。
    </p>
    <button type="submit">{{ state.editingId ? '保存修改' : '提交' }}</button>
    <button type="button" class="ghost" v-if="state.editingId" @click="endEdit">取消编辑</button>
  </form>
</template>

