<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import { RouterView } from "vue-router";
import AccountGate from "./components/AccountGate.vue";
import DialogOverlay from "./components/DialogOverlay.vue";
import {
  state,
  initAuth,
  loadProfiles,
  loadAll,
  logoutAccount,
  lockAccount,
} from "./store";

const booted = ref(false);

// ---- 账号层闲置自动锁：设 PIN 账号连续无操作 10 分钟 → 自动锁定（需 PIN 重进） ----
const IDLE_LOCK_MS = 10 * 60 * 1000;
let lastActive = Date.now();
let idleTimer = null;

function onActivity() {
  lastActive = Date.now();
}

function startIdleLock() {
  ["mousemove", "keydown", "click", "scroll", "touchstart"].forEach((ev) =>
    window.addEventListener(ev, onActivity, { passive: true })
  );
  idleTimer = window.setInterval(async () => {
    if (!state.currentAccount || !state.accountHasPin || state.lockHint) return;
    if (Date.now() - lastActive > IDLE_LOCK_MS) {
      await lockAccount();
    }
  }, 15 * 1000);
}

onMounted(async () => {
  await initAuth();
  if (state.currentAccount) {
    // 后端已登录（如自动登录）→ 直接进主界面
    await loadProfiles();
    await loadAll();
  }
  booted.value = true;
  startIdleLock();
});

onBeforeUnmount(() => {
  if (idleTimer) window.clearInterval(idleTimer);
  ["mousemove", "keydown", "click", "scroll", "touchstart"].forEach((ev) =>
    window.removeEventListener(ev, onActivity)
  );
});

// 登出当前账号 → 回账号门禁
async function doLogout() {
  await logoutAccount();
}

async function doLock() {
  await lockAccount();
}
</script>

<template>
  <main class="wrap">
    <!-- 未登录 → 账号门禁（含锁定后解锁） -->
    <AccountGate v-if="booted && !state.currentAccount" />

    <!-- 已登录 → 主应用 -->
    <template v-else-if="booted && state.currentAccount">
      <nav class="topnav">
        <RouterLink to="/" class="brand">🎯 PointLog</RouterLink>
        <div class="nav-right">
          <span class="account-pill" :title="'当前账号'">
            {{ state.currentAccount }}
            <button type="button" class="ghost tiny" v-if="state.accountHasPin" @click="doLock"
                    title="立即锁定，需输入账号 PIN 解锁">🔒 锁定</button>
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
