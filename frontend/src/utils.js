// PointLog 前端日期/时间工具 + 贡献日历网格算法

const pad = (n) => String(n).padStart(2, "0");

// Date → 本地时区的 YYYY-MM-DDTHH:MM（<input type=datetime-local>）
export function toLocalInput(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Date → YYYY-MM-DD
export function toDateStr(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// "YYYY-MM-DD" → 本地 Date（避免 UTC 解析偏移）
export function fromDateStr(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

// 按凌晨4点规则，ISO 时刻属于哪一天
export function dayOf(iso) {
  const shifted = new Date(new Date(iso).getTime() - 4 * 3600 * 1000);
  return toDateStr(shifted);
}

const WEEK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

// "YYYY-MM-DD" → 中文星期
export function weekdayLabel(dstr) {
  return WEEK[fromDateStr(dstr).getDay()];
}

// 把 ISO 时间格式化为可读显示
export function formatTime(iso) {
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

// ISO → HH:MM（本地，用于时段起止的紧凑显示）
export function formatClock(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 分钟数 → 可读消耗时长：90 → "1 小时 30 分"；45 → "45 分钟"
export function formatDuration(min) {
  const total = Math.round(Number(min) || 0);
  if (total <= 0) return "0 分钟";
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m} 分钟`;
  if (!m) return `${h} 小时`;
  return `${h} 小时 ${m} 分`;
}

// ---------- 贡献日历：把每日数组排成 GitHub 风格热力图网格（周一为每周起点） ----------
export function buildContribGrid(days) {
  if (!days.length) return { weeks: [], months: [] };
  const first = fromDateStr(days[0].date);
  const last = fromDateStr(days[days.length - 1].date);
  const start = new Date(first);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); // 回到所在周周一
  const map = new Map(days.map((d) => [d.date, d]));
  const cells = [];
  let cursor = new Date(start);
  while (cursor <= last) {
    const ds = toDateStr(cursor);
    const hit = map.get(ds);
    cells.push(
      hit
        ? { date: ds, points: hit.points, level: hit.level, inRange: true }
        : { date: ds, points: 0, level: 0, inRange: false }
    );
    cursor.setDate(cursor.getDate() + 1);
  }
  const weekCount = Math.ceil(cells.length / 7);
  const weeks = [];
  for (let w = 0; w < weekCount; w++) {
    const col = [];
    for (let r = 0; r < 7; r++) {
      col.push(cells[w * 7 + r] || { date: "", points: 0, level: 0, inRange: false });
    }
    weeks.push(col);
  }
  // 月份标签：把 "2026-09" → "9月"
  const fmtMonth = (ym) => (ym ? String(parseInt(ym.slice(5, 7), 10)) + "月" : "");
  const months = [];
  let prev = "";
  for (const col of weeks) {
    const firstCell = col.find((c) => c.inRange && c.date);
    const m = firstCell ? fmtMonth(firstCell.date.slice(0, 7)) : "";
    months.push(m !== prev ? m : "");
    prev = m;
  }
  return { weeks, months };
}
