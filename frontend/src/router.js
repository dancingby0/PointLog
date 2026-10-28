import { createRouter, createWebHashHistory } from "vue-router";
import DiaryView from "./views/DiaryView.vue";
import AssetsView from "./views/AssetsView.vue";
import AssetStatsView from "./views/AssetStatsView.vue";
import StatsView from "./views/StatsView.vue";
import ActivityView from "./views/ActivityView.vue";
import SettingsView from "./views/SettingsView.vue";

// 使用 hash 模式（#/...）：无需后端路由配合，Flask 单一页面即可承载多页
export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "diary", component: DiaryView },
    { path: "/assets", name: "assets", component: AssetsView },
    { path: "/asset-stats", name: "assetStats", component: AssetStatsView },
    { path: "/stats", name: "stats", component: StatsView },
    { path: "/activity", name: "activity", component: ActivityView },
    { path: "/settings", name: "settings", component: SettingsView },
  ],
});
