<script setup>
import { onMounted } from "vue";
import ProfileBar from "./components/ProfileBar.vue";
import TodayCard from "./components/TodayCard.vue";
import GoalCard from "./components/GoalCard.vue";
import DayPicker from "./components/DayPicker.vue";
import ContribCalendar from "./components/ContribCalendar.vue";
import EntryForm from "./components/EntryForm.vue";
import EntryList from "./components/EntryList.vue";
import NoteCard from "./components/NoteCard.vue";
import MemoCard from "./components/MemoCard.vue";
import DialogOverlay from "./components/DialogOverlay.vue";
import {
  state,
  loadProfiles,
  loadAll,
  showLock,
  watchIdle,
} from "./store";

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

    <ProfileBar />
    <TodayCard />
    <GoalCard />
    <DayPicker />
    <ContribCalendar />
    <EntryForm />
    <EntryList />
    <NoteCard />
    <MemoCard />

    <DialogOverlay />
  </main>
</template>
