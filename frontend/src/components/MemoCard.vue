<script setup>
// 备忘录（v2.7）：每条可选时间范围；过期标红但保留，由用户自己删。
import { ref } from "vue";
import { state, addMemo, delMemo, updateMemo, resetMemoSchedule } from "../store";
import ScheduleEditor from "./ScheduleEditor.vue";

const editingId = ref(null);
const editText = ref("");
const editSchedule = ref({ mode: "none", ranges: [], monthdays: [] });

// 新增区的「时间」默认收起，避免干扰随手记
const showNewSchedule = ref(false);

function startEdit(m) {
  editingId.value = m.id;
  editText.value = m.text;
  editSched(m);
}

function editSched(m) {
  editSchedule.value = {
    mode: m.schedule?.mode || "none",
    ranges: [...(m.schedule?.ranges || [])],
    monthdays: [...(m.schedule?.monthdays || [])],
  };
}

function cancelEdit() {
  editingId.value = null;
  editText.value = "";
}

async function saveEdit(m) {
  const text = editText.value.trim();
  if (!text) return;
  const ok = await updateMemo(m.id, { text, schedule: editSchedule.value });
  if (ok) cancelEdit();
}

function toggleNewSchedule() {
  showNewSchedule.value = !showNewSchedule.value;
  if (!showNewSchedule.value) resetMemoSchedule();
}

function onAdd() {
  addMemo();
  showNewSchedule.value = false;
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>备忘录</h2>
      <span class="muted">可设时间 → 自动出现在当天「每日日常」里</span>
    </div>

    <div class="memo-input">
      <input v-model.trim="state.memoDraft" type="text" maxlength="200"
             placeholder="例：周六和同学约了出去玩 / 借的书在10月30号前还" @keyup.enter="onAdd">
      <button type="button" @click="onAdd">添加</button>
      <button type="button" class="ghost" @click="toggleNewSchedule">
        {{ showNewSchedule ? "收起时间" : (state.memoSchedule.mode === "none" ? "加时间" : "已设时间") }}
      </button>
    </div>
    <ScheduleEditor v-if="showNewSchedule" v-model:schedule="state.memoSchedule" />

    <p v-if="state.memos.length === 0" class="muted">还没有备忘，随手记点什么吧。</p>
    <ul v-else class="memo-list">
      <li v-for="m in state.memos" :key="m.id" class="memo-item"
          :class="{ expired: m.expired, editing: editingId === m.id }">
        <!-- 编辑态 -->
        <template v-if="editingId === m.id">
          <div class="memo-edit">
            <input type="text" v-model.trim="editText" maxlength="200" />
            <ScheduleEditor v-model:schedule="editSchedule" />
            <div class="note-actions">
              <button type="button" @click="saveEdit(m)">保存</button>
              <button type="button" class="ghost" @click="cancelEdit">取消</button>
            </div>
          </div>
        </template>

        <!-- 展示态 -->
        <template v-else>
          <span class="memo-text">{{ m.text }}</span>
          <span class="memo-when" v-if="m.schedule && m.schedule.mode !== 'none'"
                :class="{ expired: m.expired }">
            ⏰ {{ m.when }}<template v-if="m.expired"> · 已过期</template>
          </span>
          <button class="edit ghost tiny" @click="startEdit(m)" title="修改内容与时间">✏️</button>
          <button class="delete" @click="delMemo(m.id)" title="删除">×</button>
        </template>
      </li>
    </ul>
  </section>
</template>

