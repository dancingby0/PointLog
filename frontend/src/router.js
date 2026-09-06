import { createRouter, createWebHashHistory } from "vue-router";
import DiaryView from "./views/DiaryView.vue";
import AssetsView from "./views/AssetsView.vue";
import StatsView from "./views/StatsView.vue";
import SettingsView from "./views/SettingsView.vue";

// 使用 hash 模式（#/...）：无需后端路由配合，Flask 单一页面即可承载多页
export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "diary", component: DiaryView },
    { path: "/assets", name: "assets", component: AssetsView },
    { path: "/stats", name: "stats", component: StatsView },
    { path: "/settings", name: "settings", component: SettingsView },
  ],
});
