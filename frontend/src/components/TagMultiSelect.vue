<script setup>
// 多选标签选择器：从池中点选多个（再点取消），或手输自定义（新词可加入池）
import { computed, ref } from "vue";

const props = defineProps({
  tags: { type: Array, default: () => [] },        // 标签池
  modelValue: { type: Array, default: () => [] },  // 已选标签数组
});
const emit = defineEmits(["update:modelValue", "add-tag"]);

const editing = ref(false);
const custom = ref("");

// 候选 = 标签池 ∪ 已选（已选可能来自旧数据、不在池中）
const pool = computed(() => [...new Set([...props.tags, ...props.modelValue])].filter(Boolean).sort());
const selected = computed(() => props.modelValue || []);

function toggle(tag) {
  const has = selected.value.includes(tag);
  emit(
    "update:modelValue",
    has ? selected.value.filter((t) => t !== tag) : [...selected.value, tag]
  );
}

function startCustom() {
  editing.value = true;
  custom.value = "";
}

function confirmCustom() {
  const v = custom.value.trim();
  editing.value = false;
  if (!v) return;
  if (!selected.value.includes(v)) emit("update:modelValue", [...selected.value, v]);
  if (!props.tags.includes(v)) emit("add-tag", v);
}
</script>

<template>
  <div class="tag-select">
    <template v-if="!editing">
      <button type="button" v-for="t in pool" :key="t"
              class="tag-opt" :class="{ on: selected.includes(t) }"
              @click="toggle(t)">{{ t }}</button>
      <button type="button" class="tag-opt custom" @click="startCustom">✚ 自定义</button>
      <span v-if="selected.length" class="tag-chosen">已选：{{ selected.join('、') }}</span>
    </template>
    <template v-else>
      <input v-model="custom" type="text" maxlength="20" class="plain"
             placeholder="输入标签后回车（可加入标签池）" @keyup.enter="confirmCustom" @blur="confirmCustom">
    </template>
  </div>
</template>
