<script setup>
import { reactive, ref } from "vue";
import TagPoolManager from "../components/TagPoolManager.vue";
import {
  state,
  logoutAccount,
  deleteAccount,
  setAutoLogin,
  setAccountPin,
} from "../store";

const confirmMode = ref("");        // "" | "logout" | "delete"
const delForm = reactive({ code: "", pin: "", err: "" });
const delCode = ref("");
const accountPinMode = ref(false);
const newPin = ref("");
const pinErr = ref("");

function openLogout() {
  confirmMode.value = "logout";
}

function openDelete() {
  confirmMode.value = "delete";
  delCode.value = String(Math.floor(1000 + Math.random() * 9000));
  delForm.code = "";
  delForm.pin = "";
  delForm.err = "";
}

function closeConfirm() {
  confirmMode.value = "";
  delCode.value = "";
  delForm.err = "";
}

async function confirmAction() {
  if (confirmMode.value === "logout") {
    closeConfirm();
    await logoutAccount();
    return;
  }
  if (delForm.code.trim() !== delCode.value) {
    delForm.err = "验证码不正确";
    delForm.code = "";
    return;
  }
  const ok = await deleteAccount(state.currentAccount, delForm.pin);
  if (ok) closeConfirm();
  else delForm.err = state.dialogError || "注销失败";
}

async function toggleAuto(ev) {
  await setAutoLogin(ev.target.checked);
}

async function saveAccountPin() {
  const pin = newPin.value.trim();
  if (pin && !/^\d{4,8}$/.test(pin)) { pinErr.value = "PIN 需为 4~8 位数字"; return; }
  await setAccountPin(pin);
  pinErr.value = "";
  accountPinMode.value = false;
  newPin.value = "";
}
</script>

<template>
  <div class="views">
    <h1 style="margin-bottom:12px">设置</h1>

    <section class="card">
      <div class="card-head">
        <h2>👤 当前账号：{{ state.currentAccount }}</h2>
      </div>

      <div class="set-row">
        <label class="switch-line">
          <input type="checkbox" :checked="state.autoLogin" @change="toggleAuto">
          自动登录（下次打开直接进入本账号）
        </label>
      </div>

      <div class="set-row" v-if="!accountPinMode">
        <span>账号 PIN：{{ state.accountHasPin ? '已设置 🔒' : '未设置' }}</span>
        <button type="button" class="ghost" @click="accountPinMode = true">设置 / 修改</button>
      </div>
      <div class="set-row" v-else>
        <input v-model="newPin" type="password" inputmode="numeric" maxlength="8"
               placeholder="输入新账号 PIN（留空保存=清除）">
        <button type="button" @click="saveAccountPin">保存</button>
        <button type="button" class="ghost" @click="accountPinMode = false; newPin=''">取消</button>
        <span class="lock-err">{{ pinErr }}</span>
      </div>

      <div class="set-row danger-zone">
        <button type="button" class="ghost" @click="openLogout">登出当前账号</button>
        <button type="button" class="ghost danger" @click="openDelete">注销当前账号</button>
      </div>

      <div class="set-delete" v-if="confirmMode === 'delete'">
        <p class="muted">⚠️ 将永久删除「{{ state.currentAccount }}」及其全部档案与资产，不可恢复！</p>
        <p class="muted">请输入下方数字确认：<strong class="del-code">{{ delCode }}</strong></p>
        <input v-model="delForm.code" type="text" inputmode="numeric" maxlength="4" placeholder="输入验证码">
        <input v-if="state.accountHasPin" v-model="delForm.pin" type="password" inputmode="numeric" maxlength="8" placeholder="账号 PIN">
        <p class="lock-err">{{ delForm.err }}</p>
        <div class="gate-actions">
          <button type="button" @click="confirmAction">确认注销</button>
          <button type="button" class="ghost" @click="closeConfirm">取消</button>
        </div>
      </div>
      <div class="set-delete" v-else-if="confirmMode === 'logout'">
        <p class="muted">登出后将返回账号选择页，本机数据保留。</p>
        <div class="gate-actions">
          <button type="button" @click="confirmAction">确认登出</button>
          <button type="button" class="ghost" @click="closeConfirm">取消</button>
        </div>
      </div>
    </section>

    <TagPoolManager
      scope="diary"
      title="日记标签池（当前档案）"
      hint="用于打卡类别；随档案隔离"
    />
    <TagPoolManager
      scope="asset"
      title="资产标签池（当前账号）"
      hint="用于收支/平台标签；随账号隔离"
    />
  </div>
</template>
