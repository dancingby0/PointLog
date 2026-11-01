<script setup>
import ProfileBar from "../components/ProfileBar.vue";
import TodayCard from "../components/TodayCard.vue";
import GoalCard from "../components/GoalCard.vue";
import DayPicker from "../components/DayPicker.vue";
import ContribCalendar from "../components/ContribCalendar.vue";
import RoutineCard from "../components/RoutineCard.vue";
import EntryForm from "../components/EntryForm.vue";
import EntryList from "../components/EntryList.vue";
import EntryExportCard from "../components/EntryExportCard.vue";
import NoteCard from "../components/NoteCard.vue";
import MemoCard from "../components/MemoCard.vue";
</script>

<template>
  <div class="views">
    <ProfileBar />
    <TodayCard />
    <GoalCard />
    <DayPicker />
    <ContribCalendar />
    <RoutineCard />
    <EntryForm />
    <EntryList />
    <EntryExportCard />
    <NoteCard />
    <MemoCard />
  </div>
</template>
