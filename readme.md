# PointLog

一个轻量的个人点数记录系统，量化每天的投入，找回"今天没白过"的正反馈。

## 核心特性

- 自定义点数打卡（内容 / 点数 0~N / 类别（可多选）/ 可选时段 → 消耗时长；「填用时」自动回推开始时间、「现在结束」一键收尾、「🌙 记睡眠」快捷记录（自动跨天、支持午睡多次）、0 时长＝只记时间点、凌晨4点前算昨日）
- 日期切换器（git log 风格）+ 历史补录
- 每日感想（一天一篇，可补写 / 追加 / 删除当天）
- 备忘录 + 置顶主目标（🎯 常驻横幅）
- 点数线（最近 60 天、剔极值后 80% 分位数）
- **每日日常 + 点数规定**（v2.7，档案级）：按时段列出每天该做的事与建议点数，可限定星期；备忘设了时间就自动出现在当天日常里提醒，过期标红但不删除
- 贡献日历（当年热力图，年份翻页，点击跳转日期）
- 多本地档案隔离 + 每档案 PIN 锁（闲置 5 分钟自动锁）
- 数据存本地 JSON 文件；打卡记录与资产账本均可按日期区间导出（默认落盘 `exports/`，也可下载到浏览器）
- **桌面活动统计（可选，v2.6）**：接入本机 [ActivityWatch](https://activitywatch.net/) —— 自动汇总每天的真实活跃时长、应用、网站、页面（装 `aw-watcher-web` 扩展可精确到 `deepseek.com` / `bilibili.com` 这类具体站点），类别规则可自定义；ActivityWatch 不装也不影响任何其他功能

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

## 桌面活动统计（可选，需要 ActivityWatch）

不装也能正常用；装上之后「活动」页会显示每天真实的活跃时长、应用、网站与具体页面。

1. 安装并运行 [ActivityWatch](https://activitywatch.net/)（托盘常驻，本地服务 `http://127.0.0.1:5600`）；
2. 想精确到具体网页（区分 DeepSeek / B 站这类站点），再装官方浏览器扩展
   [aw-watcher-web](https://github.com/ActivityWatch/aw-watcher-web)（Chrome / Firefox 商店）；
3. 打开 PointLog 的「活动」页 → 点「同步今天 / 近 7 天」，即可看到明细；
   类别规则（正则匹配 `app` / `title` / `url`）在页面底部编辑，例如
   `url=bilibili.com` + `title=课程|考研` → 学习。

口径：活跃时长 = 前台窗口事件 ∩ 非 AFK 区间；归属日沿用凌晨 4 点规则；网页只算活动标签页。
数据只在本机流转，同步幂等（重跑只覆盖当天摘要）。

## 数据维护

数据都是本地 JSON（`data/`，不入版本库）。附带脚本可做批量维护：都支持 `--dry-run` 先预览、
写盘前自动备份、可重复执行（幂等），建议先停掉服务再跑。

- `python migrate_entries.py`：把旧打卡记录统一为"不选时间"（`ts` → 归属日 12:00，时段两端置 `null`，归属日与点数不变）。
- `python transfer_entries.py --from <源档案> --to <目标档案> [--account <账号>] [--copy]`：
  **档案间转移打卡记录**（默认转移＝源档案记录清空，`--copy` 只复制；只搬打卡记录，感想 / 备忘 / 主目标不动，类别池取并集）。

## 状态

✅ **v1 已完工**（2026-09-05）— 验收文档见 `docs/requirements-v1.md`。
🚧 **v2 需求确定中** — 标签池 / 资产随性记账 / 统计仪表盘 / 设置页，见 `docs/requirements-v2.md`。

![status](https://img.shields.io/badge/status-v1%20done-green)