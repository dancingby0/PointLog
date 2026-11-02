<script setup>
import ProfileBar from "../components/ProfileBar.vue";
import TodayCard from "../components/TodayCard.vue";
import GoalCard from "../components/GoalCard.vue";
import DayPicker from "../components/DayPicker.vue";
import ContribCalendar from "../components/ContribCalendar.vue";
import TextBlockCard from "../components/TextBlockCard.vue";
import ReminderCard from "../components/ReminderCard.vue";
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

    <!-- 每日日常（点数线下方）→ 点数标准 → 今日提醒（由备忘时间算出） -->
    <TextBlockCard
      field="dailyRoutine"
      title="每日日常"
      hint="档案级，所有天通用；可换行排版"
      placeholder="例：
早餐 + 背单词 30 个
上午 刷题 2 小时
下午 处理邮件和杂事
晚上 复盘 + 早睡"
      empty-text="还没有写日常，点「编辑」写一段（可换行）。" />

    <TextBlockCard
      field="pointRules"
      title="点数标准"
      hint="什么事算多少点；与每日日常互相独立"
      placeholder="例：
专注 1h 10 点
游泳 100m 1 点
组会/讲座 5 点
小事（刷牙/洗澡/洗衣服/记账）1 次 1 点"
      empty-text="还没有写点数标准，点「编辑」写一段（可换行）。" />

    <ReminderCard />

    <EntryForm />
    <EntryList />
    <EntryExportCard />
    <NoteCard />
    <MemoCard />
  </div>
</template>
