<script setup>
// 今日提醒：只列"今天生效"的备忘（时间来自备忘录），过期的标红并排末尾。
// 与「每日日常 / 点数标准」是两回事：那两段是文字，这里是由备忘时间算出来的清单。
import { computed } from "vue";
import { state, selectedDayLabel } from "../store";

const reminders = computed(() => state.todayView?.reminders || []);
const active = computed(() => reminders.value.filter((m) => !m.expired));
const expired = computed(() => reminders.value.filter((m) => m.expired));
</script>

<template>
  <section class="card" v-if="reminders.length">
    <div class="card-head">
      <h2>今日提醒</h2>
      <span class="muted">{{ selectedDayLabel() }} · 来自设了时间的备忘录</span>
    </div>
    <ul class="routine-reminders">
      <li v-for="m in active" :key="m.id" class="routine-reminder">
        <span class="rem-text">{{ m.text }}</span>
        <span class="rem-when muted">{{ m.when }}</span>
      </li>
      <li v-for="m in expired" :key="m.id" class="routine-reminder expired">
        <span class="rem-text">{{ m.text }}</span>
        <span class="rem-when">已过期 · {{ m.when }}</span>
      </li>
    </ul>
  </section>
</template>
