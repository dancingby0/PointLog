<script setup>
import { state, submitEntry, endEdit } from "../store";
import { toLocalInput } from "../utils";
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

// 一键把时段"结束"设为此刻（适合做完立刻打卡）
function endNow() {
  state.form.end = toLocalInput(new Date());
}

// 清空时段（＝本条不选时间，只记录）
function clearSpan() {
  state.form.start = "";
  state.form.end = "";
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
        <input v-model="state.form.start" type="datetime-local" aria-label="开始时间">
        <span class="muted">→</span>
        <input v-model="state.form.end" type="datetime-local" aria-label="结束时间">
        <button type="button" class="ghost tiny" @click="endNow" :disabled="!state.form.start">结束＝现在</button>
        <button type="button" class="ghost tiny" @click="clearSpan"
                v-if="state.form.start || state.form.end">清空</button>
      </div>
    </label>
    <p class="muted" style="margin:0 0 10px">
      填了时段就会在记录里显示消耗时长；留空则只记录内容与点数。
      记录归属到 {{ state.selectedDay }}（凌晨 4 点前算昨日）。
    </p>
    <button type="submit">{{ state.editingId ? '保存修改' : '提交' }}</button>
    <button type="button" class="ghost" v-if="state.editingId" @click="endEdit">取消编辑</button>
  </form>
</template>

