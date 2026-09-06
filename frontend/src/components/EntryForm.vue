<script setup>
import { state, selectedIsToday, submitEntry, endEdit } from "../store";
</script>

<template>
  <form class="card" @submit.prevent="submitEntry">
    <h2>{{ state.editingId ? '编辑打卡' : '新增打卡' }}</h2>
    <label>做什么（一句话）
      <input v-model.trim="state.form.content" type="text" maxlength="100" placeholder="例：背完30个英语单词">
    </label>
    <label>点数
      <input v-model.number="state.form.points" type="number" min="0" step="1" placeholder="1">
    </label>
    <label>类别（可选）
      <input v-model.trim="state.form.category" type="text" maxlength="20" placeholder="例：学习 / 生活 / 运动">
    </label>
    <label>时间（默认：{{ selectedIsToday() ? '现在' : state.selectedDay + ' 12:00' }}，凌晨4点前算昨日）
      <input v-model="state.form.ts" type="datetime-local">
    </label>
    <button type="submit">{{ state.editingId ? '保存修改' : '提交' }}</button>
    <button type="button" class="ghost" v-if="state.editingId" @click="endEdit">取消编辑</button>
  </form>
</template>
