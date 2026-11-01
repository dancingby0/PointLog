<script setup>
// 每日日常 + 点数规定（v2.7，档案级）。
// 展示所选日生效的日常（按时段排序）与"当天生效"的备忘提醒；过期备忘标红但不删除。
import { computed } from "vue";
import {
  state,
  startRoutineEdit,
  cancelRoutineEdit,
  toggleRoutineDay,
  saveRoutine,
  delRoutine,
} from "../store";

const WEEKDAYS = [
  { key: 0, label: "一" }, { key: 1, label: "二" }, { key: 2, label: "三" },
  { key: 3, label: "四" }, { key: 4, label: "五" }, { key: 5, label: "六" },
  { key: 6, label: "日" },
];

const view = computed(() => state.schedule);
const editing = computed(() => state.routineEditingId);
const draft = computed(() => state.routineDraft);

function dayText(days) {
  if (!days || days.length === 0) return "每天";
  if (days.length === 7) return "每天";
  return "周" + days.map((d) => WEEKDAYS[d].label).join("、");
}

function ptText(points) {
  const n = Number(points) || 0;
  return n ? `${n} 点` : "—";
}
</script>

<template>
  <section class="card routine-card">
    <div class="card-head">
      <h2>每日日常 · 点数规定</h2>
      <span class="muted" v-if="view">
        {{ view.day }}（周{{ view.weekday_label }}） · 计划 {{ view.planned_points }} 点
      </span>
    </div>

    <!-- 当天生效的日常 -->
    <ul class="routine-list" v-if="view && view.items.length">
      <li v-for="item in view.items" :key="item.id" class="routine-item">
        <span class="routine-time">{{ item.start }}–{{ item.end }}</span>
        <span class="routine-text">{{ item.text }}
          <span class="routine-note muted" v-if="item.note">（{{ item.note }}）</span>
        </span>
        <span class="routine-days muted">{{ dayText(item.days) }}</span>
        <span class="routine-points">{{ ptText(item.points) }}</span>
        <span class="routine-ops">
          <button type="button" class="ghost tiny" @click="startRoutineEdit(item)">改</button>
          <button type="button" class="ghost tiny danger" @click="delRoutine(item.id)">删</button>
        </span>
      </li>
    </ul>
    <p class="muted" v-else-if="view">这一天没有安排日常。</p>
    <p class="muted" v-else>加载中…</p>

    <!-- 备忘提醒：时间符合的自动出现；过期的标红 -->
    <template v-if="view && view.reminders.length">
      <div class="card-head routine-sub">
        <h3>今日提醒</h3>
        <span class="muted">来自带时间的备忘录</span>
      </div>
      <ul class="routine-reminders">
        <li v-for="m in view.reminders" :key="m.id"
            class="routine-reminder" :class="{ expired: m.expired }">
          <span class="rem-text">{{ m.text }}</span>
          <span class="rem-when muted">{{ m.expired ? `已过期 · ${m.when}` : m.when }}</span>
        </li>
      </ul>
    </template>

    <!-- 编辑 / 新增 -->
    <div class="routine-edit" v-if="editing && draft">
      <div class="routine-edit-row">
        <label>时段
          <input type="time" v-model="draft.start" /> ~
          <input type="time" v-model="draft.end" />
        </label>
        <label class="grow">内容
          <input type="text" v-model.trim="draft.text" maxlength="60" placeholder="例：晨读 30 分钟" />
        </label>
        <label>点数
          <input type="number" v-model.number="draft.points" min="0" step="1" style="width:80px" />
        </label>
      </div>
      <div class="routine-edit-row">
        <span class="muted">适用：</span>
        <button v-for="w in WEEKDAYS" :key="w.key" type="button" class="tiny"
                :class="draft.days.includes(w.key) ? 'on' : 'ghost'"
                @click="toggleRoutineDay(w.key)">{{ w.label }}</button>
        <span class="muted">（都不选＝每天）</span>
      </div>
      <div class="routine-edit-row">
        <label class="grow">备注（可选）
          <input type="text" v-model.trim="draft.note" maxlength="120" placeholder="例：只做昨天没做完的" />
        </label>
        <label class="inline"><input type="checkbox" v-model="draft.enabled" /> 启用</label>
      </div>
      <div class="note-actions">
        <button type="button" @click="saveRoutine">保存</button>
        <button type="button" class="ghost" @click="cancelRoutineEdit">取消</button>
      </div>
    </div>

    <button type="button" class="ghost" v-else @click="startRoutineEdit(null)">＋ 添加日常</button>
  </section>
</template>
