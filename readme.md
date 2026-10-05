# PointLog

一个轻量的个人点数记录系统，量化每天的投入，找回"今天没白过"的正反馈。

## 核心特性

- 自定义点数打卡（内容 / 点数 0~N / 类别 / 可选时段 → 消耗时长；「填用时」自动回推开始时间、「现在结束」一键收尾、「🌙 记睡眠」快捷记录（自动跨天、支持午睡多次）、0 时长＝只记时间点、凌晨4点前算昨日）
- 日期切换器（git log 风格）+ 历史补录
- 每日感想（一天一篇，可补写 / 追加 / 删除当天）
- 备忘录 + 置顶主目标（🎯 常驻横幅）
- 点数线（最近 60 天、剔极值后 40% 分位数）
- 贡献日历（当年热力图，年份翻页，点击跳转日期）
- 多本地档案隔离 + 每档案 PIN 锁（闲置 5 分钟自动锁）
- 数据存本地 JSON 文件；打卡记录与资产账本均可按日期区间导出（默认落盘 `exports/`，也可下载到浏览器）

## 快速开始

**Windows**：双击 `start.bat`（首次会自动建虚拟环境并装依赖），浏览器自动打开 `http://127.0.0.1:5000/`。

> 页面是前端工程构建产物（`static/dist/`）。若页面提示"前端尚未构建"，先在 `frontend/` 执行：

```powershell
npm install
npm run build
```

**手动启动后端**：

```powershell
.\.venv\Scripts\python app.py    # 或先 py -m venv .venv && pip install -r requirements.txt
```

## 开发前端

前端源码在 `frontend/`（Vite + Vue 3 单文件组件）。

- **方式一（推荐开发）**：终端 A 跑后端 `python app.py`，终端 B 在 `frontend/` 跑 `npm run dev`，浏览器访问 `http://localhost:5173`（Vite 会把 `/api` 代理到 Flask）。
- **方式二**：在 `frontend/` 执行 `npm run build`，产物输出到 `static/dist/`，再通过 Flask（5000 端口）访问。

```
frontend/
├─ index.html            # 入口壳
├─ vite.config.js        # 构建配置（产物 → ../static/dist，/api 代理）
└─ src/
   ├─ main.js            # 启动 Vue
   ├─ App.vue            # 根组件
   ├─ store.js           # 全局状态 + 业务动作
   ├─ utils.js           # 日期工具 + 日历算法
   ├─ assets/main.css    # 全局样式
   └─ components/        # 按功能拆的 .vue 组件
```

## 状态

✅ **v1 已完工**（2026-09-05）— 验收文档见 `docs/requirements-v1.md`。
🚧 **v2 需求确定中** — 标签池 / 资产随性记账 / 统计仪表盘 / 设置页，见 `docs/requirements-v2.md`。

![status](https://img.shields.io/badge/status-v1%20done-green)