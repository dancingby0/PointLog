// 打卡类别多选（v2.5）回归测试 —— `npm test`（Node 内置 test runner，零依赖）
//
// 约定：记录的 category 恒为**字符串数组**（可多选，空数组＝无类别）。
// 老数据里的单值写法（"学习" / null）由 toCategoryList 统一规范化为 ["学习"] / []，
// 因此老档案不需要任何数据迁移，界面与统计都能直接多选。
import test from "node:test";
import assert from "node:assert/strict";

import { toCategoryList } from "../src/utils.js";

test("数组：去空白、去重、丢掉空串，保留勾选顺序", () => {
  assert.deepEqual(toCategoryList([" 学习 ", "数学", "学习", ""]), ["学习", "数学"]);
});

test("老数据的单值字符串 → 单元素数组", () => {
  assert.deepEqual(toCategoryList("学习"), ["学习"]);
  assert.deepEqual(toCategoryList("  学习  "), ["学习"]);
});

test("无类别（null / undefined / 空串 / 空数组）→ 空数组", () => {
  assert.deepEqual(toCategoryList(null), []);
  assert.deepEqual(toCategoryList(undefined), []);
  assert.deepEqual(toCategoryList(""), []);
  assert.deepEqual(toCategoryList("   "), []);
  assert.deepEqual(toCategoryList([]), []);
});

test("自定义类别（含空格）会被清干净，与后端 clean_categories 一致", () => {
  assert.deepEqual(toCategoryList([" 边学边听歌 "]), ["边学边听歌"]);
});

test("返回新数组，不修改传入的数组", () => {
  const raw = ["学习"];
  const out = toCategoryList(raw);
  out.push("数学");
  assert.deepEqual(raw, ["学习"]);
  assert.deepEqual(out, ["学习", "数学"]);
});
