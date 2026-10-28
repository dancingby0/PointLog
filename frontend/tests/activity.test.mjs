// 活动数据页用到的纯函数（formatMinutesCompact）单测
import assert from "node:assert/strict";
import { test } from "node:test";

import { formatMinutesCompact } from "../src/utils.js";

test("formatMinutesCompact：不足 1 小时只显示分钟", () => {
  assert.equal(formatMinutesCompact(0), "0m");
  assert.equal(formatMinutesCompact(45), "45m");
  assert.equal(formatMinutesCompact(59.4), "59m");
});

test("formatMinutesCompact：>=1 小时显示 h + 两位分钟", () => {
  assert.equal(formatMinutesCompact(60), "1h00m");
  assert.equal(formatMinutesCompact(90), "1h30m");
  assert.equal(formatMinutesCompact(95.6), "1h36m");
  assert.equal(formatMinutesCompact(1234), "20h34m");
});

test("formatMinutesCompact：非法/负数不炸", () => {
  assert.equal(formatMinutesCompact(null), "0m");
  assert.equal(formatMinutesCompact("abc"), "0m");
  assert.equal(formatMinutesCompact(-5), "0m");
});
