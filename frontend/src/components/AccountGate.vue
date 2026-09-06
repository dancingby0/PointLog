<script setup>
// 账号门禁：未登录时显示的账号选择/登录/新建页
import { reactive, ref } from "vue";
import {
  state,
  loginAccount,
  createAccount,
  initAuth,
} from "../store";

const selected = ref(null);        // 选中账号名（待输 PIN）
const pinInput = ref("");
const showNew = ref(false);
const newForm = reactive({ name: "", pin: "", confirmPin: "" });
const errMsg = ref("");
const busy = ref(false);

async function pick(account) {
  selected.value = account.name;
  pinInput.value = "";
  errMsg.value = "";
  if (!account.has_pin) {
    await doLogin(account.name, "");
  }
}

async function doLogin(name, pin) {
  busy.value = true;
  errMsg.value = "";
  const ok = await loginAccount(name, pin);
  if (!ok) errMsg.value = state.dialogError || "登录失败";
  busy.value = false;
}

async function confirmPin() {
  await doLogin(selected.value, pinInput.value);
}

async function submitNew() {
  const name = newForm.name.trim();
  if (!name) { errMsg.value = "请输入账号名"; return; }
  if (newForm.pin !== newForm.confirmPin) { errMsg.value = "两次 PIN 不一致"; return; }
  busy.value = true;
  errMsg.value = "";
  await createAccount(name, newForm.pin);
  // createAccount 成功后自动登录，不再处于门禁；失败则留在本页
  busy.value = false;
  if (!state.currentAccount) errMsg.value = state.dialogError || "创建失败";
}

async function cancelPick() {
  selected.value = null;
  pinInput.value = "";
  errMsg.value = "";
  await initAuth();
}
</script>

<template>
  <div class="gate">
    <h1>🎯 PointLog</h1>
    <p class="muted" style="margin:0 0 18px">选择账号开始记录</p>

    <!-- 登录 PIN 输入 -->
    <div v-if="selected" class="gate-card">
      <h2>登录「{{ selected }}」</h2>
      <input v-model="pinInput" type="password" inputmode="numeric" maxlength="8"
             placeholder="输入账号 PIN" @keyup.enter="confirmPin">
      <p class="lock-err">{{ errMsg }}</p>
      <div class="gate-actions">
        <button type="button" @click="confirmPin" :disabled="busy">登录</button>
        <button type="button" class="ghost" @click="cancelPick">返回</button>
      </div>
    </div>

    <!-- 账号列表 -->
    <template v-else>
      <div v-if="state.authAccounts.length === 0" class="gate-card">
        <p class="muted">还没有账号，先新建一个吧。</p>
      </div>
      <ul v-else class="gate-accounts">
        <li v-for="a in state.authAccounts" :key="a.name" class="gate-acct" @click="pick(a)">
          <span class="gate-acct-name">{{ a.name }}</span>
          <span class="gate-acct-lock" v-if="a.has_pin">🔒</span>
          <span class="gate-acct-go" v-else>进入 →</span>
        </li>
      </ul>

      <!-- 新建账号 -->
      <div v-if="!showNew" class="gate-newbar">
        <button type="button" @click="showNew = true">＋ 新建账号</button>
      </div>
      <div v-else class="gate-card">
        <h2>新建账号</h2>
        <input v-model="newForm.name" type="text" maxlength="30" placeholder="账号名（如 我的账号）">
        <input v-model="newForm.pin" type="password" inputmode="numeric" maxlength="8" placeholder="账号 PIN（可选，4~8位数字）">
        <input v-model="newForm.confirmPin" type="password" inputmode="numeric" maxlength="8" placeholder="确认 PIN">
        <p class="lock-err">{{ errMsg }}</p>
        <div class="gate-actions">
          <button type="button" @click="submitNew" :disabled="busy">创建并进入</button>
          <button type="button" class="ghost" @click="showNew = false; errMsg=''">取消</button>
        </div>
      </div>
    </template>
  </div>
</template>
