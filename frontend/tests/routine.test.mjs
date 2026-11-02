// 每日日常 / 点数标准文本展示的纯逻辑单测（前端不重复实现后端规则，只测展示函数）
import assert from "node:assert/strict";
import { test } from "node:test";

// 与 TextBlockCard 中"共 N 行 / M 字"的算法一致（后端也返回同样口径）
function textStats(text) {
  const clean = String(text ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const lines = clean.split("\n").filter((l) => l.trim());
  return { lines: lines.length, chars: clean.replace(/\n/g, "").length };
}

test("textStats：多行文本的行数与字数", () => {
  assert.deepEqual(textStats("第一行\n第二行"), { lines: 2, chars: 6 });
  assert.deepEqual(textStats("abc\ndef\n\n"), { lines: 2, chars: 6 });
});

test("textStats：空文本 / 纯空白", () => {
  assert.deepEqual(textStats(""), { lines: 0, chars: 0 });
  assert.deepEqual(textStats("   \n\n  "), { lines: 0, chars: 5 });   // 只有空格与换行，无有效行
  assert.deepEqual(textStats(null), { lines: 0, chars: 0 });
});

test("textStats：CRLF 归一后行数正确", () => {
  assert.deepEqual(textStats("a\r\nb\r\nc"), { lines: 3, chars: 3 });
});
