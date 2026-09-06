<script setup>
import { state, startGoalEdit, cancelGoalEdit, saveGoal } from "../store";

function startGoalEditFn() {
  startGoalEdit();
}
function cancelGoalEditFn() {
  cancelGoalEdit();
}
</script>

<template>
  <section class="card goal-card">
    <template v-if="state.goalEditing">
      <input v-model.trim="state.goalDraft" type="text" maxlength="100"
             placeholder="写下当前的主目标，如：读完一本书" @keyup.enter="saveGoal">
      <div class="goal-actions">
        <button type="button" @click="saveGoal" :disabled="!state.goalDraft.trim()">保存主目标</button>
        <button type="button" class="ghost" @click="cancelGoalEditFn">取消</button>
      </div>
    </template>
    <template v-else>
      <span class="goal-icon">🎯</span>
      <span class="goal-label">{{ state.mainGoal ? '当前主目标' : '尚未设置主目标' }}</span>
      <span class="goal-text" v-if="state.mainGoal">{{ state.mainGoal }}</span>
      <button type="button" class="ghost" @click="startGoalEditFn" style="margin-left:auto">{{ state.mainGoal ? '修改' : '设置' }}</button>
    </template>
  </section>
</template>
