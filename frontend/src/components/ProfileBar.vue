<script setup>
import {
  state,
  onProfileSelect,
  exportData,
  openRenameProfile,
  openDeleteProfile,
  openNewProfile,
} from "../store";
</script>

<template>
  <div class="profile-bar">
    <span>📁 档案：</span>
    <strong class="pf-name">{{ state.currentProfile }}</strong>
    <select :value="state.currentProfile" @change="onProfileSelect" title="切换档案">
      <option v-for="p in state.profiles" :key="p.name" :value="p.name">{{ p.name }}</option>
    </select>
    <span class="spacer"></span>
    <button type="button" class="ghost" @click="exportData" title="导出当前档案全部数据为 JSON 文件">导出 JSON</button>
    <button type="button" class="ghost" @click="openRenameProfile" title="重命名当前档案">✏️ 改名</button>
    <button type="button" class="ghost danger" @click="openDeleteProfile" title="删除当前档案">🗑 删除</button>
    <button type="button" class="ghost" @click="openNewProfile">＋新建</button>
  </div>
</template>
