<script setup>
// 通用标签池管理器：给定 API scope（diary/asset）做增删
import { onMounted, ref } from "vue";

const props = defineProps({
  scope: { type: String, required: true },   // "diary" | "asset"
  title: { type: String, required: true },
  hint: { type: String, default: "" },
});

const tags = ref([]);
const draft = ref("");
const loading = ref(false);

const base = `/api/tags/${props.scope}`;

async function load() {
  loading.value = true;
  try {
    const res = await fetch(base);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载失败");
    tags.value = data.tags;
  } catch (err) {
    alert("加载标签失败：" + err.message);
  } finally {
    loading.value = false;
  }
}

async function add() {
  const tag = draft.value.trim();
  if (!tag) return;
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
  } catch (err) {
    alert("添加失败：" + err.message);
  }
}

async function remove(tag) {
  if (!confirm(`从标签池删除「${tag}」？\n（不影响任何历史记录）`)) return;
  try {
    const res = await fetch(`${base}?tag=${encodeURIComponent(tag)}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "删除失败");
    tags.value = data.tags;
  } catch (err) {
    alert("删除失败：" + err.message);
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
      <span v-for="t in tags" :key="t" class="tag-chip">
        {{ t }}
        <button type="button" class="tag-x" @click="remove(t)" title="删除标签">×</button>
      </span>
      <span v-if="!loading && tags.length === 0" class="muted">还没有标签。</span>
    </div>
  </section>
</template>
