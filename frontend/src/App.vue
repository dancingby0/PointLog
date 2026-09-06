<script setup>
import { onMounted, ref } from "vue";
import { RouterView } from "vue-router";
import AccountGate from "./components/AccountGate.vue";
import DialogOverlay from "./components/DialogOverlay.vue";
import {
  state,
  initAuth,
  loadProfiles,
  loadAll,
  logoutAccount,
} from "./store";

const booted = ref(false);

onMounted(async () => {
  await initAuth();
  if (state.currentAccount) {
    // 后端已登录（如自动登录）→ 直接进主界面
    await loadProfiles();
    await loadAll();
  }
  booted.value = true;
});

// 登出当前账号 → 回账号门禁
async function doLogout() {
  await logoutAccount();
}
</script>

<template>
  <main class="wrap">
    <!-- 未登录 → 账号门禁 -->
    <AccountGate v-if="booted && !state.currentAccount" />

    <!-- 已登录 → 主应用 -->
    <template v-else-if="booted && state.currentAccount">
      <nav class="topnav">
        <RouterLink to="/" class="brand">🎯 PointLog</RouterLink>
        <div class="nav-right">
          <span class="account-pill" :title="'当前账号'">
            {{ state.currentAccount }}
            <button type="button" class="ghost tiny" @click="doLogout">登出</button>
          </span>
          <div class="nav-links">
            <RouterLink to="/">日记</RouterLink>
            <RouterLink to="/assets">资产</RouterLink>
            <RouterLink to="/stats">统计</RouterLink>
            <RouterLink to="/settings">设置</RouterLink>
          </div>
        </div>
      </nav>

      <RouterView />
    </template>

    <div v-else class="muted" style="padding:40px;text-align:center">加载中…</div>

    <DialogOverlay />
  </main>
</template>
