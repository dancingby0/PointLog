<script setup>
import { state, addMemo, delMemo } from "../store";
</script>

<template>
  <section class="card">
    <h2>备忘录</h2>
    <div class="memo-input">
      <input v-model.trim="state.memoDraft" type="text" maxlength="200"
             placeholder="例：周六和同学约了出去玩 / 借的书在10月30号前还" @keyup.enter="addMemo">
      <button type="button" @click="addMemo">添加</button>
    </div>
    <p v-if="state.memos.length === 0" class="muted">还没有备忘，随手记点什么吧。</p>
    <ul v-else class="memo-list">
      <li v-for="m in state.memos" :key="m.id" class="memo-item">
        <span class="memo-text">{{ m.text }}</span>
        <button class="delete" @click="delMemo(m.id)" title="删除">×</button>
      </li>
    </ul>
  </section>
</template>
