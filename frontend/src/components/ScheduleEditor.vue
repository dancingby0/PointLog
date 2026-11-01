<script setup>
// 备忘时间范围编辑器（v2.7）：不设定 / 每天 / 绝对日期段（可多段）/ 每月几号到几号（可多段）。
// 用 v-model:schedule 双向绑定：内部只 emit 新对象，不直接改父组件的 props。
import { computed, reactive, watch } from "vue";

const props = defineProps({
  schedule: { type: Object, default: () => ({ mode: "none", ranges: [], monthdays: [] }) },
});
const emit = defineEmits(["update:schedule"]);

const MODES = [
  { key: "none", label: "不设定" },
  { key: "daily", label: "每天" },
  { key: "dates", label: "指定日期" },
  { key: "monthdays", label: "每月几号" },
];

const local = reactive({
  mode: props.schedule?.mode || "none",
  ranges: [...(props.schedule?.ranges || [])],
  monthdays: [...(props.schedule?.monthdays || [])],
});

// 外部（切换编辑对象 / 保存后刷新）改了就同步进来
watch(
  () => props.schedule,
  (next) => {
    local.mode = next?.mode || "none";
    local.ranges = [...(next?.ranges || [])];
    local.monthdays = [...(next?.monthdays || [])];
  },
  { deep: true }
);

function emitChange() {
  emit("update:schedule", {
    mode: local.mode,
    ranges: local.ranges.map((r) => ({ ...r })),
    monthdays: local.monthdays.map((r) => ({ ...r })),
  });
}

function setMode(key) {
  local.mode = key;
  if (key === "dates" && !local.ranges.length) local.ranges = [{ from: "", to: "" }];
  if (key === "monthdays" && !local.monthdays.length) local.monthdays = [{ from: 1, to: 1 }];
  emitChange();
}

function addRange() {
  local.ranges.push({ from: "", to: "" });
  emitChange();
}

function removeRange(i) {
  local.ranges.splice(i, 1);
  emitChange();
}

function onRangeFrom(i, value) {
  local.ranges[i] = { from: value, to: local.ranges[i].to || value };   // 只填起点 = 单日
  emitChange();
}

function onRangeTo(i, value) {
  local.ranges[i] = { ...local.ranges[i], to: value };
  emitChange();
}

function addMonthRange() {
  local.monthdays.push({ from: 1, to: 1 });
  emitChange();
}

function removeMonthRange(i) {
  local.monthdays.splice(i, 1);
  emitChange();
}

function onMonth(index, key, value) {
  const num = Math.max(1, Math.min(31, Number(value) || 1));
  const item = { ...local.monthdays[index], [key]: num };
  if (key === "from" && item.to < num) item.to = num;    // 起点后移时把终点顶上去
  if (key === "to" && item.from > num) item.from = num;
  local.monthdays[index] = item;
  emitChange();
}

const hint = computed(() => {
  if (local.mode === "dates") return "闭区间，含首尾两天；可加多段（如 10-08~10-09、10-11~10-12）";
  if (local.mode === "monthdays") return "每月固定几号生效；可加多段（如 8→9、11→12）";
  if (local.mode === "daily") return "每天都出现在日常提醒里";
  return "只当备忘保存，不出现在日常提醒里";
});
</script>

<template>
  <div class="sched-editor">
    <div class="sched-modes">
      <button v-for="m in MODES" :key="m.key" type="button" class="tiny"
              :class="local.mode === m.key ? 'on' : 'ghost'"
              @click="setMode(m.key)">{{ m.label }}</button>
    </div>

    <div v-if="local.mode === 'dates'" class="sched-rows">
      <div v-for="(r, i) in local.ranges" :key="i" class="sched-row">
        <input type="date" :value="r.from" @input="onRangeFrom(i, $event.target.value)" />
        <span class="muted">~</span>
        <input type="date" :value="r.to" @input="onRangeTo(i, $event.target.value)" />
        <button type="button" class="ghost tiny danger" @click="removeRange(i)">删除</button>
      </div>
      <button type="button" class="ghost tiny" @click="addRange">＋ 加一段</button>
    </div>

    <div v-else-if="local.mode === 'monthdays'" class="sched-rows">
      <div v-for="(r, i) in local.monthdays" :key="i" class="sched-row">
        <input type="number" min="1" max="31" :value="r.from"
               @input="onMonth(i, 'from', $event.target.value)" />
        <span class="muted">号 ~</span>
        <input type="number" min="1" max="31" :value="r.to"
               @input="onMonth(i, 'to', $event.target.value)" />
        <span class="muted">号</span>
        <button type="button" class="ghost tiny danger" @click="removeMonthRange(i)">删除</button>
      </div>
      <button type="button" class="ghost tiny" @click="addMonthRange">＋ 加一段</button>
    </div>

    <p class="muted sched-hint">{{ hint }}</p>
  </div>
</template>
