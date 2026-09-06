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
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // 把 echarts 单独拆成 vendor chunk，主包更小、浏览器可长缓存
        manualChunks: {
          echarts: ["echarts/core", "echarts/charts", "echarts/components", "echarts/renderers"],
          vendor: ["vue", "vue-router"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
});
