<script setup>
import { state, todayStr, selectedIsToday, shiftMonth, onYearChange, onMonthChange, goToday, selectDay } from "../store";
import { weekdayLabel } from "../utils";
</script>

<template>
  <section class="card day-picker">
    <div class="day-picker-head">
      <h2>日期</h2>
      <div class="day-controls">
        <button type="button" class="ghost nav-btn" @click="shiftMonth(-1)" title="上个月">‹</button>
        <select :value="state.viewMonth.slice(0, 4)" @change="onYearChange" class="month-sel">
          <option v-for="y in state.yearOptions" :key="y" :value="String(y)">{{ y }} 年</option>
        </select>
        <select :value="state.viewMonth.slice(5, 7)" @change="onMonthChange" class="month-sel">
          <option v-for="m in 12" :key="m" :value="String(m).padStart(2, '0')">{{ m }} 月</option>
        </select>
        <button type="button" class="ghost nav-btn" @click="shiftMonth(1)" title="下个月">›</button>
        <button type="button" class="ghost" @click="goToday" :disabled="selectedIsToday() && state.viewMonth === todayStr().slice(0,7)">今天</button>
      </div>
    </div>
    <ul class="day-list">
      <li v-for="d in state.days" :key="d.date"
          class="day-item" :class="{ active: d.date === state.selectedDay, future: d.is_future }"
          @click="!d.is_future && selectDay(d.date)">
        <span class="day-date">{{ d.date.slice(8) }}</span>
        <span class="day-week">{{ weekdayLabel(d.date) }}</span>
        <span class="day-tag" v-if="d.is_today">今天</span>
        <span class="day-note" v-if="d.has_note" title="这一天写了感想">📝</span>
        <span class="day-points">{{ d.points }} 点</span>
      </li>
    </ul>
  </section>
</template>
