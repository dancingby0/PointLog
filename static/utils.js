// PointLog 前端日期/时间工具（独立模块，供 app.js 等复用）
window.PointLogUtils = (() => {
  const pad = (n) => String(n).padStart(2, "0");

  // Date → 本地时区的 YYYY-MM-DDTHH:MM（<input type=datetime-local>）
  function toLocalInput(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // Date → YYYY-MM-DD
  function toDateStr(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  // "YYYY-MM-DD" → 本地 Date（避免 UTC 解析偏移）
  function fromDateStr(s) {
    const [y, m, d] = s.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  // 按凌晨4点规则，ISO 时刻属于哪一天
  function dayOf(iso) {
    const shifted = new Date(new Date(iso).getTime() - 4 * 3600 * 1000);
    return toDateStr(shifted);
  }

  const WEEK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

  // "YYYY-MM-DD" → 中文星期
  function weekdayLabel(dstr) {
    return WEEK[fromDateStr(dstr).getDay()];
  }

  return { toLocalInput, toDateStr, fromDateStr, dayOf, weekdayLabel, WEEK };
})();