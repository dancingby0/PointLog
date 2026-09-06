import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 构建产物输出到 Flask 托管的 static/dist，由后端页面引用。
// API 保持同源（开发时 proxy 到 Flask 5000）。
export default defineConfig({
  plugins: [vue()],
  base: "/static/dist/",
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
});
