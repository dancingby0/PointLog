<script setup>
// 通用标签池管理器：给定 API scope（diary/asset）做 增 / 改名 / 删
import { onMounted, ref } from "vue";

const props = defineProps({
  scope: { type: String, required: true },   // "diary" | "asset"
  title: { type: String, required: true },
  hint: { type: String, default: "" },
});
const emit = defineEmits(["changed"]);        // 供父组件刷新（如打卡表单的类别池）

const tags = ref([]);
const draft = ref("");
const loading = ref(false);
// 改名：editing 为正在改的标签原文，editDraft 为新名字
const editing = ref("");
const editDraft = ref("");
const msg = ref("");
const err = ref("");

const base = `/api/tags/${props.scope}`;
const label = () => (props.scope === "diary" ? "打卡类别" : "流水标签");
const recordLabel = () => (props.scope === "diary" ? "历史打卡" : "历史流水");

async function load() {
  loading.value = true;
  try {
    const res = await fetch(base);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载失败");
    tags.value = data.tags;
  } catch (e) {
    err.value = "加载标签失败：" + e.message;
  } finally {
    loading.value = false;
  }
}

function notify() {
  emit("changed", tags.value);
}

async function add() {
  const tag = draft.value.trim();
  if (!tag) return;
  err.value = "";
  msg.value = "";
  try {
    const res = await fetch(base, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "添加失败");
    tags.value = data.tags;
    draft.value = "";
    msg.value = `已添加「${tag}」`;
    notify();
  } catch (e) {
    err.value = "添加失败：" + e.message;
  }
}

function startRename(tag) {
  editing.value = tag;
  editDraft.value = tag;
  err.value = "";
  msg.value = "";
}

function cancelRename() {
  editing.value = "";
  editDraft.value = "";
}

async function saveRename(ev) {
  const from = editing.value;
  const to = editDraft.value.trim();
  err.value = "";
  msg.value = "";
  if (!to) {
    err.value = "新标签不能为空";
    return;
  }
  if (to === from) {
    cancelRename();
    return;
  }
  // 询问是否同时改写历史记录（默认不勾；改历史不可撤销，要用户明确同意）
  const cascade = ev && ev.shiftKey
    ? true
    : confirm(`把「${from}」改名为「${to}」？\n\n点「确定」只改标签池（历史记录不动）。\n`
      + `如需连${recordLabel()}一起改，请取消后按住 Shift 再回车。`);
  try {
    const res = await fetch(base, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from, to, cascade }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "改名失败");
    tags.value = data.tags;
    const changed = data.entries_changed ?? data.txs_changed ?? 0;
    msg.value = changed
      ? `已改名，并同步更新 ${changed} 条${recordLabel()}`
      : `已改名（${recordLabel()}未改动）`;
    cancelRename();
    notify();
  } catch (e) {
    err.value = "改名失败：" + e.message;
  }
}

async function remove(tag) {
  if (!confirm(`从标签池删除「${tag}」？\n（不影响任何历史记录）`)) return;
  err.value = "";
  msg.value = "";
  try {
    const res = await fetch(`${base}?tag=${encodeURIComponent(tag)}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "删除失败");
    tags.value = data.tags;
    msg.value = `已删除「${tag}」`;
    notify();
  } catch (e) {
    err.value = "删除失败：" + e.message;
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>{{ title }}</h2>
      <span class="muted" v-if="hint">{{ hint }}</span>
    </div>
    <div class="tag-input-row">
      <input v-model="draft" type="text" maxlength="20" placeholder="新增标签，回车添加"
             @keyup.enter="add">
      <button type="button" @click="add" :disabled="!draft.trim()">添加</button>
    </div>

    <div class="tag-chips">
      <template v-for="t in tags" :key="t">
        <!-- 改名态：就地输入 -->
        <span v-if="editing === t" class="tag-chip editing">
          <input v-model="editDraft" type="text" maxlength="20" class="tag-rename-input"
                 @keyup.enter="saveRename" @keyup.esc="cancelRename">
          <button type="button" class="tag-x" @click="saveRename" title="保存（按住 Shift 点=同时改历史）">✓</button>
          <button type="button" class="tag-x" @click="cancelRename" title="取消">✕</button>
        </span>
        <!-- 展示态 -->
        <span v-else class="tag-chip">
          {{ t }}
          <button type="button" class="tag-edit" @click="startRename(t)" title="改名">✏️</button>
          <button type="button" class="tag-x" @click="remove(t)" title="删除标签">×</button>
        </span>
      </template>
      <span v-if="!loading && tags.length === 0" class="muted">
        还没有标签。标签池完全由你自己维护（打卡时自定义的{{ label() }}也会自动进来）。
      </span>
    </div>

    <p class="muted tag-tip">改名只改标签池；按住 Shift 点 ✓ 或按住 Shift 回车可同时改写历史记录。</p>
    <p class="muted" v-if="msg">{{ msg }}</p>
    <p class="error" v-if="err">{{ err }}</p>
  </section>
</template>

