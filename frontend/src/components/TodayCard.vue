<script setup>
import { state, selectedLabel, lineText } from "../store";
</script>

<template>
  <section class="today">
    <div class="points">{{ selectedLabel() }} 点数 <strong>{{ state.dayPoints }}</strong></div>
    <div class="today-line" v-if="state.line">
      <span class="line-label">点数线</span>
      <strong class="line-value">{{ lineText() }}</strong>
      <span class="line-hint" v-if="state.line.active_days > 0">
        （近 {{ state.line.window_days }} 天 · {{ state.line.active_days }} 个打卡日
        <template v-if="state.line.method === 'trimmed'">· 剔最高最低各 {{ state.line.trimmed_low }} 天后</template>
        取 40% 分位）
      </span>
    </div>
  </section>
</template>
