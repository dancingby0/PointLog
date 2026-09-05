# PointLog

一个轻量的个人点数记录系统，量化每天的投入，找回"今天没白过"的正反馈。

## 核心特性

- 自定义点数打卡（内容 / 点数 / 类别 / 时间，凌晨4点前算昨日）
- 日期切换器（git log 风格）+ 历史补录
- 每日感想（一天一篇，可补写 / 追加 / 删除当天）
- 备忘录 + 置顶主目标（🎯 常驻横幅）
- 点数线（最近 60 天、剔极值后 40% 分位数）
- 贡献日历（当年热力图，年份翻页，点击跳转日期）
- 多本地档案隔离 + 每档案 PIN 锁（闲置 5 分钟自动锁）
- 数据存本地 JSON 文件，可一键导出备份 / 统计

## 快速开始

**Windows**：双击 `start.bat`（首次会自动建虚拟环境并装依赖），浏览器自动打开 `http://127.0.0.1:5000/`。

**手动启动**：

```powershell
.\.venv\Scripts\python app.py    # 或先 py -m venv .venv && pip install -r requirements.txt
```

## 状态

✅ **v1 已完工**（2026-09-05）— 全部验收项通过，详见 `docs/requirements.md`。

![status](https://img.shields.io/badge/status-v1%20done-green)