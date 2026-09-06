<script setup>
import { computed } from "vue";
import { state, selectedLabel, startEdit, delEntry } from "../store";
import { formatTime } from "../utils";

const sortedEntries = computed(() =>
  [...state.entries].sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0))
);
</script>

<template>
  <section class="card">
    <h2>{{ selectedLabel() }} 的记录</h2>
    <p v-if="sortedEntries.length === 0" class="muted">这一天还没有记录。</p>
    <ul v-else class="entry-list">
      <li v-for="e in sortedEntries" :key="e.id" class="entry">
        <span class="entry-time">{{ formatTime(e.ts) }}</span>
        <span class="entry-content">{{ e.content }}</span>
        <span v-if="e.category" class="entry-cat">{{ e.category }}</span>
        <span class="entry-points">+{{ e.points }}</span>
        <button class="edit" @click="startEdit(e)">编辑</button>
        <button class="delete" @click="delEntry(e)">×</button>
      </li>
    </ul>
  </section>
</template>
