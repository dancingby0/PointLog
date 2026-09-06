<script setup>
// 单选标签选择器：从池中点选，或手输自定义（新词可加入池）
import { computed, ref } from "vue";

const props = defineProps({
  tags: { type: Array, default: () => [] },   // 标签池
  modelValue: { type: String, default: "" },    // 当前选择文本
});
const emit = defineEmits(["update:modelValue", "add-tag"]);

const editing = ref(false);
const custom = ref("");

const pool = computed(() => [...new Set(props.tags)].filter(Boolean).sort());

function pick(tag) {
  emit("update:modelValue", tag);
  editing.value = false;
}

function startCustom() {
  editing.value = true;
  custom.value = props.modelValue;
}

function confirmCustom() {
  const v = custom.value.trim();
  if (!v) { editing.value = false; return; }
  emit("update:modelValue", v);
  if (!props.tags.includes(v)) emit("add-tag", v);
  editing.value = false;
}
</script>

<template>
  <div class="tag-select">
    <template v-if="!editing">
      <button type="button" v-for="t in pool" :key="t"
              class="tag-opt" :class="{ on: t === modelValue }"
              @click="pick(t)">{{ t }}</button>
      <button type="button" class="tag-opt custom" @click="startCustom">
        {{ modelValue && !pool.includes(modelValue) ? modelValue + '（自定义）' : '✚ 自定义' }}
      </button>
      <span v-if="modelValue && pool.includes(modelValue)" class="tag-chosen">{{ modelValue }}</span>
    </template>
    <template v-else>
      <input v-model="custom" type="text" maxlength="20" class="plain"
             placeholder="输入自定义类别" @keyup.enter="confirmCustom" @blur="confirmCustom">
    </template>
  </div>
</template>
