<script setup>
import { computed } from "vue";
import { state, calYearLabel, calCanNext, prevYear, nextYear, goCalendarLatest, selectDay, cellTitle } from "../store";
import { buildContribGrid } from "../utils";

const contrib = computed(() => buildContribGrid(state.calendarDays));
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>贡献日历</h2>
      <div class="cal-actions">
        <button type="button" class="ghost nav-btn" @click="prevYear" title="往前一年">‹</button>
        <span class="cal-year-label">{{ calYearLabel() }}</span>
        <button type="button" class="ghost nav-btn" @click="nextYear" :disabled="!calCanNext()" title="往近一年">›</button>
        <button type="button" class="ghost" v-if="state.calendarYear" @click="goCalendarLatest" title="回到最近一年">回今年</button>
      </div>
    </div>
    <div class="contrib">
      <div class="contrib-months" :style="{ width: (contrib.weeks.length * 16 - 3) + 'px' }">
        <template v-for="(m, idx) in contrib.months" :key="idx">
          <span v-if="m" class="contrib-month" :style="{ left: (idx * 16) + 'px' }">{{ m }}</span>
        </template>
      </div>
      <div class="contrib-row">
        <div class="contrib-weekdays">
          <span>一</span><span></span><span>三</span><span></span><span>五</span><span></span><span>日</span>
        </div>
        <div class="contrib-grid">
          <div v-for="(col, wi) in contrib.weeks" :key="wi" class="contrib-col">
            <div v-for="(c, ri) in col" :key="ri" class="contrib-cell"
                 :class="{ 'cell-empty': !c.inRange, ['lvl' + c.level]: c.inRange }"
                 :title="cellTitle(c)"
                 @click="c.inRange && selectDay(c.date)"></div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
