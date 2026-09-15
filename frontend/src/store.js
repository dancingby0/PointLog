// PointLog 全局 store：共享状态 + 业务动作
// （原 app.js 的 data + methods 集中于此；组件通过具名导入使用）
import { reactive } from "vue";
import { toLocalInput, toDateStr, fromDateStr, dayOf, weekdayLabel } from "./utils";

export const state = reactive({
  entries: [],            // 当前所选天的记录
  dayPoints: 0,           // 当前所选天的点数
  line: null,             // 点数线计算结果
  selectedDay: "",        // 当前所选日期 YYYY-MM-DD
  viewMonth: "",          // 日期选择器当前年月 YYYY-MM
  days: [],               // 当月逐日列表
  yearOptions: [],        // 可选年份
  calendarDays: [],       // 贡献日历数据
  calendarYear: 0,        // 贡献日历当前年份（0=今年）
  diaryTags: [],          // 日记标签池（当前档案）
  assetTags: [],          // 资产标签池（个人级）
  accounts: [],           // 账户列表
  totalAssets: 0,         // 个人总资产
  txs: [],                // 流水列表（当前筛选+分页结果）
  txFilters: {
    from: "", to: "", channels: [], types: [], tags: [],
    invert: { channels: false, types: false, tags: false },   // 各维度是否反选（排除所选项）
    unsettledOnly: false,                                     // 仅看未平账日期的流水
  },
  txTags: [],             // 可筛选标签（流水实际出现过的）
  txPage: 1,              // 流水当前页
  txPageSize: 20,         // 流水每页条数
  txTotal: 0,             // 流水筛选后总条数
  settledDays: [],        // 已平账日期（本地 YYYY-MM-DD）
  unsettledDays: [],      // 有流水但尚未平账的日期
  statsSummary: null,     // 统计：坚持与概况
  statsRange: "month",    // 统计时间范围
  statsTrend: [],         // 统计：月度趋势
  statsDist: null,        // 统计：分布（标签/星期/时段）
  statsAssets: [],        // 统计：收支月度趋势
  assetStats: null,       // 资产统计分析（筛选+粒度+折线/饼图）
  editingId: null,        // 正在编辑的记录 id
  form: { content: "", points: 1, category: "", ts: "" },
  noteDraft: "",          // 感想草稿
  hasNote: false,         // 当天是否有感想
  noteEditing: false,     // 是否在编辑感想
  memos: [],
  memoDraft: "",
  mainGoal: "",
  goalDraft: "",
  goalEditing: false,
  // 档案
  profiles: [],
  currentProfile: "",
  // 账号（v2.3）
  currentAccount: "",      // 当前本地账号名
  accountHasPin: false,    // 当前账号是否有锁
  unlockedAccount: "",     // 免输窗口内账号名（服务端内存态）
  lockHint: null,          // 锁定信息 {account, has_pin}（null=未锁定）
  authAccounts: [],        // 账号列表 [{name, has_pin, auto_login}]
  autoLogin: false,        // 自动登录开关
  dialog: null,           // {mode, tip, code?, target?}
  newProfileName: "",
  renameName: "",
  codeInput: "",
  dialogError: "",
});

// ---------- 小工具（组件共用） ----------
export const todayStr = () => toDateStr(new Date());

export function selectedLabel() {
  if (!state.selectedDay) return "";
  if (state.selectedDay === todayStr()) return "今天";
  const diff = Math.round((fromDateStr(todayStr()) - fromDateStr(state.selectedDay)) / 86400000);
  if (diff === 1) return "昨天";
  return `${state.selectedDay} ${weekdayLabel(state.selectedDay)}`;
}

export const selectedIsToday = () => state.selectedDay === todayStr();

export function lineText() {
  if (!state.line || state.line.active_days === 0) return "—";
  const b = state.line.baseline;
  return Number.isInteger(b) ? String(b) : b.toFixed(1);
}

export function dialogTitle() {
  if (!state.dialog) return "";
  switch (state.dialog.mode) {
    case "new": return "新建档案";
    case "rename": return "重命名当前档案";
    case "delete": return "⚠️ 删除当前档案";
    default: return "";
  }
}

export const currentYear = () => new Date().getFullYear();

export const calYearLabel = () => state.calendarYear || currentYear();

export const calCanNext = () => !!state.calendarYear && state.calendarYear < currentYear();

// ================= 账号（v2.3） =================

export async function initAuth() {
  try {
    const res = await fetch("/api/auth");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载账号失败");
    state.authAccounts = data.accounts;
    state.currentAccount = data.logged_in || "";
    state.autoLogin = data.auto_login;
    state.unlockedAccount = data.unlocked || "";
    if (data.logged_in) {
      const cur = state.authAccounts.find((a) => a.name === data.logged_in);
      state.accountHasPin = !!(cur && cur.has_pin);
    }
  } catch (err) {
    console.error(err);
  }
}

export async function loginAccount(name, pin = "") {
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, pin }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "登录失败");
    state.currentAccount = data.account;
    state.currentProfile = data.profile;
    state.lockHint = null;  // 解锁/登录成功 → 清除锁定提示
    await initAuth();
    resetForProfileChange();
    await loadProfiles();
    await loadAll();
    return true;
  } catch (err) {
    state.dialogError = err.message;
    return false;
  }
}

export async function lockAccount() {
  try {
    const res = await fetch("/api/auth/lock", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "锁定失败");
    state.currentAccount = "";
    state.currentProfile = "";
    state.accountHasPin = false;
    state.lockHint = data;   // {account, has_pin} → 前端显示解锁界面
    resetForProfileChange();
    await initAuth();
    return true;
  } catch (err) {
    state.dialogError = err.message;
    return false;
  }
}

export async function logoutAccount() {
  try {
    const res = await fetch("/api/auth/logout", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "登出失败");
    state.currentAccount = "";
    state.currentProfile = "";
    state.accountHasPin = false;
    state.lockHint = null;
    resetForProfileChange();
    await initAuth();
  } catch (err) {
    console.error(err);
  }
}

export async function createAccount(name, pin = "") {
  try {
    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, pin }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "创建失败");
    await initAuth();
    await loginAccount(name, pin);
  } catch (err) {
    state.dialogError = err.message;
  }
}

export async function deleteAccount(name, pin = "") {
  try {
    const res = await fetch(`/api/auth/${encodeURIComponent(name)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "注销失败");
    if (state.currentAccount === name) state.currentAccount = "";
    state.accountHasPin = false;
    resetForProfileChange();
    await initAuth();
    return true;
  } catch (err) {
    state.dialogError = err.message;
    return false;
  }
}

export async function renameAccount(name, pin = "") {
  try {
    const res = await fetch("/api/auth/rename", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, pin }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "改名失败");
    state.currentAccount = data.account;
    await initAuth();
    return true;
  } catch (err) {
    state.dialogError = err.message;
    return false;
  }
}

export async function setAutoLogin(enabled) {
  try {
    const res = await fetch("/api/auth/set-auto-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存失败");
    state.autoLogin = data.auto_login;
  } catch (err) {
    console.error(err);
  }
}

export async function setAccountPin(pin) {
  try {
    const res = await fetch("/api/auth/pin", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存失败");
    state.accountHasPin = data.has_pin;
  } catch (err) {
    state.dialogError = err.message;
  }
}

// ================= 档案 =================

export async function loadProfiles() {
  try {
    const res = await fetch("/api/profiles");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载档案失败");
    state.profiles = data.profiles;
    state.currentProfile = data.current;
  } catch (err) {
    console.error(err);
  }
}

export function resetForProfileChange() {
  state.dialog = null;
  state.dialogError = "";
  state.newProfileName = "";
  state.entries = [];
  state.dayPoints = 0;
  state.selectedDay = "";
  state.viewMonth = "";
  state.days = [];
  state.yearOptions = [];
  state.calendarDays = [];
  state.calendarYear = 0;
  state.editingId = null;
  state.form = { content: "", points: 1, category: "", ts: "" };
  state.noteDraft = "";
  state.hasNote = false;
  state.noteEditing = false;
  state.memos = [];
  state.memoDraft = "";
  state.mainGoal = "";
  state.goalDraft = "";
  state.goalEditing = false;
  state.line = null;
  state.diaryTags = [];
}

export async function doSwitch(name) {
  try {
    const res = await fetch("/api/profiles/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "切换失败");
    resetForProfileChange();
    await loadProfiles();
    await loadAll();
  } catch (err) {
    state.dialogError = err.message;
  }
}

export async function onProfileSelect(ev) {
  const name = ev.target.value;
  if (name === state.currentProfile) return;
  await doSwitch(name);
}

export function openNewProfile() {
  state.dialog = { mode: "new", tip: "创建一个全新的空档案（数据与其他档案隔离）" };
  state.newProfileName = "";
  state.dialogError = "";
}

export function openRenameProfile() {
  state.dialog = {
    mode: "rename",
    tip: `给「${state.currentProfile}」起个新名字`,
  };
  state.renameName = state.currentProfile;
  state.dialogError = "";
}

export function openDeleteProfile() {
  const code = String(Math.floor(1000 + Math.random() * 9000));
  state.dialog = {
    mode: "delete",
    code,
    tip: `将永久删除「${state.currentProfile}」的所有数据，不可恢复！`,
  };
  state.codeInput = "";
  state.dialogError = "";
}

export function closeDialog() {
  state.dialog = null;
  state.dialogError = "";
}

export function exportData() {
  // 附件下载不会离开当前页
  window.location.href = "/api/export";
}

export async function submitDialog() {
  const mode = state.dialog && state.dialog.mode;
  state.dialogError = "";
  if (mode === "new") {
    const name = state.newProfileName.trim();
    if (!name) { state.dialogError = "档案名不能为空"; return; }
    try {
      const res = await fetch("/api/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "创建失败");
      state.dialog = null;
      await doSwitch(name);
    } catch (err) {
      state.dialogError = err.message;
    }
  } else if (mode === "rename") {
    const name = state.renameName.trim();
    if (!name) { state.dialogError = "新档案名不能为空"; return; }
    try {
      const res = await fetch("/api/profiles/rename", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "重命名失败");
      state.dialog = null;
      await refreshAfterProfileChange(data.current);
    } catch (err) {
      state.dialogError = err.message;
    }
  } else if (mode === "delete") {
    if (state.codeInput.trim() !== state.dialog.code) {
      state.dialogError = "验证码不正确，已取消";
      state.codeInput = "";
      return;
    }
    try {
      const res = await fetch(`/api/profiles/${encodeURIComponent(state.currentProfile)}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "删除失败");
      state.dialog = null;
      await refreshAfterProfileChange(data.current);
    } catch (err) {
      state.dialogError = err.message;
    }
  }
}

async function refreshAfterProfileChange(newCurrent) {
  state.currentProfile = newCurrent;
  state.dialog = null;
  await loadProfiles();
  resetForProfileChange();
  await loadAll();
}


// ================= 初始化 / 数据加载 =================

export function initYearOptions() {
  const cur = new Date().getFullYear();
  state.yearOptions = [];
  for (let y = cur - 5; y <= cur; y++) state.yearOptions.push(y);
}

export async function loadDiaryTags() {
  try {
    const res = await fetch("/api/tags/diary");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载日记标签失败");
    state.diaryTags = data.tags;
  } catch (err) {
    console.error(err);
    state.diaryTags = [];
  }
}

export async function loadAll() {
  try {
    initYearOptions();
    state.viewMonth = todayStr().slice(0, 7);   // 默认当年当月
    await loadDiaryTags();
    await loadDays();
    await loadCalendar();
    await loadMemos();
    await loadLine();
    const target = state.days.find((d) => d.is_today) || state.days[0];
    await selectDay(target ? target.date : todayStr());
  } catch (err) {
    alert("初始化失败：" + err.message);
  }
}

export async function loadLine() {
  try {
    const res = await fetch("/api/line");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载点数线失败");
    state.line = data;
  } catch (err) {
    console.error(err);
    state.line = null;
  }
}

export function defaultTsFor(day) {
  return day === todayStr() ? toLocalInput(new Date()) : `${day}T12:00`;
}

export async function selectDay(day) {
  state.selectedDay = day;
  if (!state.editingId) {
    state.form.ts = defaultTsFor(day);
  }
  await loadEntries();
  await loadNote();
}

export async function loadDays() {
  const month = state.viewMonth || todayStr().slice(0, 7);
  const res = await fetch(`/api/days?month=${month}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "加载日期失败");
  state.days = data.days;
  state.viewMonth = data.month;
}

function pickMonthDay() {
  const todayIn = state.days.find((d) => d.is_today);
  if (todayIn) return todayIn.date;
  return state.days[state.days.length - 1].date;
}

async function reloadMonthView() {
  await loadDays();
  await selectDay(pickMonthDay());
}

export async function onYearChange(ev) {
  const year = ev.target.value;
  const month = state.viewMonth.slice(5, 7);
  state.viewMonth = `${year}-${month}`;
  await reloadMonthView();
}

export async function onMonthChange(ev) {
  const month = ev.target.value;
  const year = state.viewMonth.slice(0, 4);
  const ym = `${year}-${month}`;
  const cur = todayStr().slice(0, 7);
  if (ym > cur) { alert("不能查看未来月份"); return; }
  state.viewMonth = ym;
  await reloadMonthView();
}

export async function shiftMonth(delta) {
  const d = fromDateStr(state.viewMonth + "-01");
  d.setMonth(d.getMonth() + delta);
  const ym = toDateStr(d).slice(0, 7);
  const cur = todayStr().slice(0, 7);
  if (ym > cur) { alert("不能查看未来月份"); return; }
  state.viewMonth = ym;
  await reloadMonthView();
}

export async function goToday() {
  state.viewMonth = todayStr().slice(0, 7);
  await loadDays();
  await selectDay(todayStr());
}

export async function loadEntries() {
  try {
    const res = await fetch(`/api/entries?day=${state.selectedDay}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载失败");
    state.entries = data.entries;
    state.dayPoints = data.day_points;
  } catch (err) {
    console.error(err);
    alert("加载失败：" + err.message);
  }
}


export async function loadNote() {
  try {
    const res = await fetch(`/api/notes?day=${state.selectedDay}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载感想失败");
    state.noteDraft = data.note || "";
    state.hasNote = !!data.note;
    state.noteEditing = false;
  } catch (err) {
    console.error(err);
    state.noteDraft = "";
    state.hasNote = false;
    state.noteEditing = false;
  }
}

export function startNoteEdit() {
  state.noteEditing = true;
}

export function cancelNoteEdit() {
  // 丢弃草稿，重新加载已保存内容
  loadNote();
}

export async function saveNote() {
  const content = state.noteDraft.trim();
  if (!content) {
    alert("感想不能为空");
    return;
  }
  try {
    const res = await fetch("/api/notes", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: state.selectedDay, content }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存失败");
    state.noteDraft = data.note;
    state.hasNote = true;
    state.noteEditing = false;   // 保存完毕收起编辑框
  } catch (err) {
    alert("保存失败：" + err.message);
  }
}

export async function deleteNote() {
  if (!confirm(`删除 ${selectedLabel()} 的整篇感想？`)) return;
  try {
    const res = await fetch(`/api/notes?day=${state.selectedDay}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok && res.status !== 404) throw new Error(data.error || "删除失败");
    state.noteDraft = "";
    state.hasNote = false;
    state.noteEditing = false;
  } catch (err) {
    alert("删除失败：" + err.message);
  }
}

export function stampNote() {
  const now = new Date();
  const p = (n) => String(n).padStart(2, "0");
  const stamp = `[${p(now.getHours())}:${p(now.getMinutes())}] `;
  state.noteDraft = state.noteDraft.trimEnd()
    ? `${state.noteDraft.trimEnd()}\n\n${stamp}`
    : stamp;
}

export async function submitEntry() {
  const payload = {
    content: state.form.content.trim(),
    points: Number(state.form.points),
    category: state.form.category || null,
  };
  if (!payload.content) return;

  const tsInput = state.form.ts || defaultTsFor(state.selectedDay);
  const d = new Date(tsInput);
  if (Number.isNaN(d.getTime())) {
    alert("时间格式不正确");
    return;
  }
  payload.ts = d.toISOString();

  const url = state.editingId ? `/api/entries/${state.editingId}` : "/api/entries";
  const method = state.editingId ? "PUT" : "POST";
  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || (state.editingId ? "保存失败" : "提交失败"));
    endEdit();
    const ownerDay = dayOf(data.ts);
    if (ownerDay !== state.selectedDay) {
      state.selectedDay = ownerDay;
      state.form.ts = defaultTsFor(ownerDay);
    }
    await refresh();
  } catch (err) {
    alert("提交失败：" + err.message);
  }
}

export function startEdit(entry) {
  state.editingId = entry.id;
  state.form.content = entry.content;
  state.form.points = entry.points;
  state.form.category = entry.category || "";
  state.form.ts = toLocalInput(new Date(entry.ts));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

export function endEdit() {
  state.editingId = null;
  state.form.content = "";
  state.form.points = 1;
  state.form.category = "";
  state.form.ts = defaultTsFor(state.selectedDay);
}

export async function refresh() {
  await Promise.all([loadEntries(), loadDays(), loadCalendar(), loadNote(), loadLine()]);
}

export async function delEntry(entry) {
  if (!confirm(`删除这条记录？\n${entry.content}`)) return;
  try {
    const res = await fetch(`/api/entries/${entry.id}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "删除失败");
    await refresh();
  } catch (err) {
    alert("删除失败：" + err.message);
  }
}


// ================= 贡献日历 =================

export async function loadCalendar() {
  const url = state.calendarYear ? `/api/calendar?year=${state.calendarYear}` : "/api/calendar";
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "加载贡献日历失败");
  state.calendarDays = data;
}

export async function prevYear() {
  const year = (state.calendarYear || currentYear()) - 1;
  state.calendarYear = year;
  await loadCalendar();
}

export async function nextYear() {
  if (!calCanNext()) return;
  state.calendarYear += 1;
  if (state.calendarYear >= currentYear()) state.calendarYear = 0;
  await loadCalendar();
}

export async function goCalendarLatest() {
  state.calendarYear = 0;
  await loadCalendar();
}

export function cellTitle(c) {
  if (!c.inRange) return "";
  return c.points > 0 ? `${c.date} · ${c.points} 点` : c.date;
}

// ================= 备忘录 + 主目标 =================

export async function loadMemos() {
  try {
    const res = await fetch("/api/memos");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载备忘录失败");
    state.memos = data.memos;
    state.mainGoal = data.main_goal || "";
  } catch (err) {
    console.error(err);
  }
}

export async function addMemo() {
  const text = state.memoDraft.trim();
  if (!text) return;
  try {
    const res = await fetch("/api/memos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "添加失败");
    state.memos.push(data);
    state.memoDraft = "";
  } catch (err) {
    alert("添加失败：" + err.message);
  }
}

export async function delMemo(id) {
  try {
    const res = await fetch(`/api/memos/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "删除失败");
    state.memos = state.memos.filter((m) => m.id !== id);
  } catch (err) {
    alert("删除失败：" + err.message);
  }
}

export function startGoalEdit() {
  state.goalDraft = state.mainGoal;
  state.goalEditing = true;
}

export function cancelGoalEdit() {
  state.goalEditing = false;
  state.goalDraft = "";
}

export async function saveGoal() {
  try {
    const res = await fetch("/api/main-goal", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: state.goalDraft.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存失败");
    state.mainGoal = data.main_goal || "";
    state.goalEditing = false;
  } catch (err) {
    alert("保存失败：" + err.message);
  }
}


// ================= 资产（个人级） =================

export async function loadAccounts() {
  try {
    const res = await fetch("/api/accounts");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载账户失败");
    state.accounts = data.accounts;
    state.totalAssets = data.total;
  } catch (err) {
    console.error(err);
  }
}

export async function loadTxs() {
  try {
    const p = new URLSearchParams();
    const f = state.txFilters;
    if (f.from) p.set("from", f.from);
    if (f.to) p.set("to", f.to);
    if (f.channels.length) p.set("channels", f.channels.join(","));
    if (f.types.length) p.set("types", f.types.join(","));
    if (f.tags.length) p.set("tags", f.tags.join(","));
    const inverted = Object.keys(f.invert).filter((k) => f.invert[k]);
    if (inverted.length) p.set("invert", inverted.join(","));
    if (f.unsettledOnly) p.set("unsettled", "1");
    p.set("page", String(state.txPage));
    p.set("page_size", String(state.txPageSize));
    const res = await fetch(`/api/transactions?${p.toString()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载流水失败");
    state.txs = data.transactions;
    state.txTotal = data.total;
    state.txPage = data.page;
    state.txPageSize = data.page_size;
    state.txTags = data.available_tags || [];
  } catch (err) {
    console.error(err);
  }
}

// ---- 流水筛选 / 分页 ----
export async function setTxFilters(patch) {
  Object.assign(state.txFilters, patch);
  state.txPage = 1;
  await loadTxs();
}

export async function toggleTxFilterItem(key, value) {
  const arr = state.txFilters[key];
  const i = arr.indexOf(value);
  if (i >= 0) arr.splice(i, 1);
  else arr.push(value);
  state.txPage = 1;
  await loadTxs();
}

export async function resetTxFilters() {
  state.txFilters = {
    from: "", to: "", channels: [], types: [], tags: [],
    invert: { channels: false, types: false, tags: false },
    unsettledOnly: false,
  };
  state.txPage = 1;
  await loadTxs();
}

export async function setTxUnsettledOnly(value) {
  state.txFilters.unsettledOnly = value;
  state.txPage = 1;
  await loadTxs();
}

export async function setTxInvert(key, value) {
  state.txFilters.invert[key] = value;
  state.txPage = 1;
  await loadTxs();
}

export async function setTxPage(page) {
  state.txPage = Math.max(1, page);
  await loadTxs();
}

export async function setTxPageSize(size) {
  state.txPageSize = size;
  state.txPage = 1;
  await loadTxs();
}

export async function loadAssetTags() {
  try {
    const res = await fetch("/api/tags/asset");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载资产标签失败");
    state.assetTags = data.tags;
  } catch (err) {
    console.error(err);
    state.assetTags = [];
  }
}

export async function refreshAssets() {
  await Promise.all([loadAccounts(), loadTxs(), loadAssetTags(), loadSettlements()]);
}

// ---- 平账标记（按天） ----
export async function loadSettlements() {
  try {
    const res = await fetch("/api/asset-settlements");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载平账标记失败");
    state.settledDays = data.settled_days || [];
    state.unsettledDays = data.unsettled_days || [];
  } catch (err) {
    console.error(err);
  }
}

export async function setDaySettled(day, settled) {
  try {
    const res = await fetch("/api/asset-settlements", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day, settled }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存失败");
    await loadSettlements();
    await loadTxs();   // 若正筛"仅未平账"，列表需同步刷新
    return true;
  } catch (err) {
    alert("保存失败：" + err.message);
    return false;
  }
}


// ================= 统计 =================

export async function loadStatsSummary() {
  try {
    const res = await fetch(`/api/stats/summary?range=${state.statsRange}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载统计失败");
    state.statsSummary = data;
  } catch (err) {
    console.error(err);
  }
}

export async function loadStatsTrend() {
  try {
    const res = await fetch("/api/stats/trend?months=12");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载趋势失败");
    state.statsTrend = data;
  } catch (err) {
    console.error(err);
  }
}

export async function loadStatsDist() {
  try {
    const res = await fetch(`/api/stats/distribution?range=${state.statsRange}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载分布失败");
    state.statsDist = data;
  } catch (err) {
    console.error(err);
  }
}

export async function loadStatsAssets() {
  try {
    const res = await fetch("/api/stats/assets?months=12");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载收支趋势失败");
    state.statsAssets = data;
  } catch (err) {
    console.error(err);
  }
}

// ---- 资产统计分析（多筛选 + 粒度 + 折线/饼图） ----
export async function loadAssetAnalysis(params = {}) {
  try {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (Array.isArray(v)) {
        if (v.length) p.set(k, v.join(","));
      } else if (v !== "" && v !== null && v !== undefined) {
        p.set(k, String(v));
      }
    });
    const res = await fetch(`/api/stats/asset-analysis?${p.toString()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载资产统计失败");
    state.assetStats = data;
    return data;
  } catch (err) {
    state.dialogError = err.message;
    alert("加载资产统计失败：" + err.message);
    return null;
  }
}

