<script setup>
import { nextTick } from "vue";
import { state, selectedLabel, startNoteEdit, cancelNoteEdit, saveNote, deleteNote, stampNote } from "../store";
import { weekdayLabel } from "../utils";

function doStartNoteEdit() {
  startNoteEdit();
  nextTick(() => {
    const ta = document.querySelector(".card textarea");
    if (ta) ta.focus();
  });
}

function doStampNote() {
  stampNote();
  nextTick(() => {
    const ta = document.querySelector(".card textarea");
    if (ta) {
      ta.focus();
      ta.selectionStart = ta.selectionEnd = ta.value.length;
    }
  });
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>{{ selectedLabel() }} 的感想</h2>
      <button type="button" class="ghost" v-if="state.noteEditing" @click="doStampNote" title="在末尾插入此刻时间，方便追加一段">⏱ 插入此刻时间</button>
    </div>

    <!-- 编辑 / 追加模式 -->
    <template v-if="state.noteEditing">
      <textarea v-model="state.noteDraft" rows="6"
        placeholder="写下这一天的感想：梦、遇见了谁、今天的心情、任何想记的事……（选中历史日期即可补写当天）"></textarea>
      <div class="note-actions">
        <button type="button" @click="saveNote">保存感想</button>
        <button type="button" class="ghost" @click="cancelNoteEdit">取消</button>
      </div>
    </template>

    <!-- 展示模式：已有感想 -->
    <template v-else-if="state.hasNote">
      <p class="note-view">{{ state.noteDraft }}</p>
      <div class="note-actions">
        <button type="button" class="ghost" @click="doStartNoteEdit">✏️ 修改感想</button>
        <button type="button" class="ghost" @click="deleteNote">🗑️ 删除感想</button>
      </div>
    </template>

    <!-- 展示模式：还没有感想 -->
    <template v-else>
      <p class="muted">这一天还没有感想。</p>
      <button type="button" @click="doStartNoteEdit">✏️ 写感想</button>
    </template>
  </section>
</template>
