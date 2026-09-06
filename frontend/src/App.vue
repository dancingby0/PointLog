<script setup>
import { onMounted } from "vue";
import { RouterView } from "vue-router";
import DialogOverlay from "./components/DialogOverlay.vue";
import { state, loadProfiles, loadAll, showLock, watchIdle } from "./store";

onMounted(async () => {
  await loadProfiles();
  if (state.currentHasPin) {
    showLock("此档案已加密，请输入 PIN 解锁");
  } else {
    await loadAll();
  }
  watchIdle();
});
</script>

<template>
  <main class="wrap">
    <h1>PointLog</h1>

    <nav class="topnav">
      <RouterLink to="/" class="brand">🎯 PointLog</RouterLink>
      <div class="nav-links">
        <RouterLink to="/">日记</RouterLink>
        <RouterLink to="/assets">资产</RouterLink>
        <RouterLink to="/stats">统计</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </div>
    </nav>

    <RouterView />

    <DialogOverlay />
  </main>
</template>
