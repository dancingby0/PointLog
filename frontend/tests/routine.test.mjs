// v2.7 备忘时间范围 + 日常筛选的纯逻辑单测
import assert from "node:assert/strict";
import { test } from "node:test";

// 前端不重复实现范围判断（后端 routine.py 负责），这里验证展示相关的纯函数
function dayText(days) {
  const labels = ["一", "二", "三", "四", "五", "六", "日"];
  if (!days || days.length === 0 || days.length === 7) return "每天";
  return "周" + days.map((d) => labels[d]).join("、");
}

function ptText(points) {
  const n = Number(points) || 0;
  return n ? `${n} 点` : "—";
}

test("dayText：未选星期 = 每天", () => {
  assert.equal(dayText([]), "每天");
  assert.equal(dayText(null), "每天");
  assert.equal(dayText([0, 1, 2, 3, 4, 5, 6]), "每天");
});

test("dayText：部分星期逐个列出", () => {
  assert.equal(dayText([0]), "周一");
  assert.equal(dayText([0, 2, 4]), "周一、三、五");
  assert.equal(dayText([6]), "周日");
});

test("ptText：0 点显示破折号，其余带单位", () => {
  assert.equal(ptText(0), "—");
  assert.equal(ptText(null), "—");
  assert.equal(ptText(2), "2 点");
  assert.equal(ptText("1.5"), "1.5 点");
});
