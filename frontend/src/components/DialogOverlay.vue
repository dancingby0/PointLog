<script setup>
import { state, dialogTitle, submitDialog, closeDialog, clearPin } from "../store";
</script>

<template>
  <div class="lock-overlay" v-if="state.dialog">
    <div class="lock-box">
      <h2>{{ dialogTitle() }}</h2>
      <p class="lock-tip">{{ state.dialog.tip }}</p>

      <!-- 新建档案：只需名字 -->
      <template v-if="state.dialog.mode === 'new'">
        <input v-model="state.newProfileName" type="text" maxlength="30"
               placeholder="档案名（如 study）" @keyup.enter="submitDialog">
      </template>

      <!-- 重命名：新名字（若已设 PIN 还需要 PIN） -->
      <template v-else-if="state.dialog.mode === 'rename'">
        <input v-model="state.renameName" type="text" maxlength="30" class="plain"
               placeholder="新的档案名" @keyup.enter="submitDialog">
        <input v-if="state.currentHasPin" v-model="state.pinInput" type="password" inputmode="numeric" maxlength="8"
               placeholder="输入当前 PIN 确认" @keyup.enter="submitDialog">
      </template>

      <!-- 删除档案：验证码（防误触）+ PIN（若已设） -->
      <template v-else-if="state.dialog.mode === 'delete'">
        <p class="lock-tip" style="margin-bottom:6px">请输入下方数字确认删除（不可恢复）：</p>
        <p class="delete-code">{{ state.dialog.code }}</p>
        <input v-model="state.codeInput" type="text" inputmode="numeric" maxlength="4" class="plain"
               placeholder="输入上面这串数字" @keyup.enter="submitDialog">
        <input v-if="state.currentHasPin" v-model="state.pinInput" type="password" inputmode="numeric" maxlength="8"
               placeholder="输入当前 PIN 确认" @keyup.enter="submitDialog">
      </template>

      <!-- 其余（解锁 / 切换 / 设PIN）：只需 PIN -->
      <template v-else>
        <input v-model="state.pinInput" type="password" inputmode="numeric" maxlength="8"
               placeholder="输入 4~8 位数字 PIN" @keyup.enter="submitDialog">
      </template>

      <p class="lock-err">{{ state.dialogError }}</p>
      <div class="lock-actions">
        <button type="button" @click="submitDialog">{{ state.dialog.mode === 'delete' ? '确认删除' : '确定' }}</button>
        <button type="button" class="ghost" v-if="state.dialog.mode !== 'lock'" @click="closeDialog">取消</button>
        <button type="button" class="ghost" v-if="state.dialog.mode === 'pinSetup' && state.currentHasPin" @click="clearPin">清除 PIN</button>
      </div>
    </div>
  </div>
</template>
