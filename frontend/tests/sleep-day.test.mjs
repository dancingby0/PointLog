// 睡眠归属日回归测试 —— `npm test`（Node 内置 test runner，零依赖）
//
// 起因：9 号记 03:10 → 12:20 的睡眠被记到 8 号。
// 原因：睡眠记录的归属时刻取"入睡时刻"，撞上"凌晨 4 点回退"规则 → 03:10 被算作前一天。
// 约定：睡眠归属到**入睡那一天**（4 点规则是给熬夜工作用的，睡眠跨零点属正常）。
import test from "node:test";
import assert from "node:assert/strict";

import {
  sleepBaseFor,
  sleepOwnerTs,
  resolveSleepSpan,
  dayOf,
  fromDateStr,
  toDateStr,
} from "../src/utils.js";

// 复刻 store.submitSleep 的归属链路，返回这条记录最终会落在哪一天
function ownerDayOf(selectedDay, from, to, base = "auto") {
  const resolved = base === "auto" ? sleepBaseFor(from, to) : base;
  const prev = fromDateStr(selectedDay);
  prev.setDate(prev.getDate() - 1);
  const day = resolved === "today" ? selectedDay : toDateStr(prev);
  const span = resolveSleepSpan(day, from, to);
  const ts = sleepOwnerTs(span.start);
  return { resolved, span, ts, ownerDay: dayOf(new Date(ts)) };
}

test("03:10–12:20（当天补记）归属当天——回归：曾被甩到前一天", () => {
  const r = ownerDayOf("2026-10-09", "03:10", "12:20");
  assert.equal(r.resolved, "today");
  assert.equal(r.span.start, "2026-10-09T03:10");
  assert.equal(r.span.end, "2026-10-09T12:20");
  assert.equal(r.ownerDay, "2026-10-09");
});

test("通宵 23:00 → 07:00 自动跨到次日，归属入睡日（前一天）", () => {
  const r = ownerDayOf("2026-10-09", "23:00", "07:00");
  assert.equal(r.resolved, "yesterday");
  assert.equal(r.span.start, "2026-10-08T23:00");
  assert.equal(r.span.end, "2026-10-09T07:00");
  assert.equal(r.ownerDay, "2026-10-08");
});

test("午睡 13:00 → 14:00 归属当天", () => {
  const r = ownerDayOf("2026-10-09", "13:00", "14:00");
  assert.equal(r.resolved, "today");
  assert.equal(r.ownerDay, "2026-10-09");
});

test("凌晨补觉 02:00 → 09:00 归属当天", () => {
  assert.equal(ownerDayOf("2026-10-09", "02:00", "09:00").ownerDay, "2026-10-09");
});

test("0 时长（起止同刻）归属当天", () => {
  assert.equal(ownerDayOf("2026-10-09", "03:10", "03:10").ownerDay, "2026-10-09");
});

test("手动基准「昨晚 / 今天」覆盖自动判定", () => {
  assert.equal(ownerDayOf("2026-10-09", "03:10", "12:20", "yesterday").ownerDay, "2026-10-08");
  assert.equal(ownerDayOf("2026-10-09", "23:00", "07:00", "today").ownerDay, "2026-10-09");
});

test("任意入睡时刻（含凌晨）的归属日都等于入睡的日历日", () => {
  for (const hh of ["00:00", "01:30", "03:59", "04:00", "07:59", "12:00", "12:01", "23:59"]) {
    const r = ownerDayOf("2026-10-09", hh, "23:59");
    assert.equal(r.ownerDay, "2026-10-09", `入睡 ${hh} 应归属 2026-10-09`);
  }
});

test("sleepBaseFor：起床早于入睡＝昨晚，否则＝今天", () => {
  assert.equal(sleepBaseFor("23:00", "07:00"), "yesterday");
  assert.equal(sleepBaseFor("03:10", "12:20"), "today");
  assert.equal(sleepBaseFor("13:00", "14:00"), "today");
  assert.equal(sleepBaseFor("03:10", "03:10"), "today");
});

test("sleepOwnerTs：本地 12:00 前的入睡锚到当天 12:00，之后保持原样", () => {
  assert.equal(sleepOwnerTs("2026-10-09T03:10"), "2026-10-09T12:00");
  assert.equal(sleepOwnerTs("2026-10-09T14:05"), "2026-10-09T14:05");
});

test("sleepOwnerTs 对非法/空输入返回空串", () => {
  assert.equal(sleepOwnerTs(""), "");
  assert.equal(sleepOwnerTs("nope"), "");
});
