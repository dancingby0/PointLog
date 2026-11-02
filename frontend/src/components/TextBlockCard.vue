<script setup>
// 通用「多行文字卡片」：每日日常 / 点数标准都用它，各自独立读写。
// 阅读态按原样保留换行（pre-wrap），编辑态用 textarea；Ctrl+Enter 保存，Esc 取消。
import { computed, ref, watch } from "vue";
import { state, saveTextBlock } from "../store";

const props = defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: "" },
  field: { type: String, required: true },        // "dailyRoutine" / "pointRules"
  placeholder: { type: String, default: "" },
  emptyText: { type: String, default: "还没有内容，点「编辑」写点什么。" },
});

const editing = ref(false);
const draft = ref("");
const busy = ref(false);
const error = ref("");

const block = computed(() => state[props.field] || { text: "", lines: 0, chars: 0, empty: true });
const text = computed(() => block.value.text || "");

function startEdit() {
  draft.value = text.value;
  error.value = "";
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  error.value = "";
}

async function save() {
  busy.value = true;
  error.value = "";
  try {
    await saveTextBlock(props.field, draft.value);
    editing.value = false;
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

function onKeydown(ev) {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
    ev.preventDefault();
    save();
  } else if (ev.key === "Escape") {
    ev.preventDefault();
    cancelEdit();
  }
}

// 切换档案后草稿失效
watch(() => state.currentProfile, () => {
  if (editing.value) cancelEdit();
});
</script>

<template>
  <section class="card textblock-card">
    <div class="card-head">
      <h2>{{ title }}</h2>
      <span class="muted" v-if="!block.empty">{{ block.lines }} 行 · {{ block.chars }} 字</span>
    </div>

    <template v-if="editing">
      <textarea v-model="draft" rows="8" class="textblock-input"
                :placeholder="placeholder" @keydown="onKeydown"></textarea>
      <div class="note-actions">
        <button type="button" :disabled="busy" @click="save">{{ busy ? "保存中…" : "保存" }}</button>
        <button type="button" class="ghost" @click="cancelEdit">取消</button>
        <span class="muted">Ctrl+Enter 保存 · Esc 取消</span>
        <span class="error" v-if="error">{{ error }}</span>
      </div>
    </template>

    <template v-else>
      <p class="textblock-view" v-if="!block.empty">{{ text }}</p>
      <p class="muted" v-else>{{ emptyText }}</p>
      <div class="note-actions">
        <button type="button" class="ghost" @click="startEdit">
          {{ block.empty ? "✏️ 编辑" : "✏️ 修改" }}
        </button>
        <span class="muted" v-if="hint">{{ hint }}</span>
      </div>
    </template>
  </section>
</template>
