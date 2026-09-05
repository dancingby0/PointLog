// PointLog 前端：打卡记录 + 日期切换 + 贡献日历（M2 · Vue 3）
const { createApp } = Vue;
const { toLocalInput, toDateStr, fromDateStr, dayOf, weekdayLabel } = window.PointLogUtils;

// ---------- 贡献日历：把每日数组排成 GitHub 风格热力图网格（周一为每周起点） ----------
function buildContribGrid(days) {
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

createApp({
  data() {
    return {
      entries: [],            // 当前所选天的记录
      dayPoints: 0,           // 当前所选天的点数
      line: null,             // 点数线（40%分位剔极值）计算结果
      selectedDay: "",        // 当前所选日期 YYYY-MM-DD
      days: [],               // 日期切换列表（git log 风格）
      calendarDays: [],       // 贡献日历原始数据（按年份窗口）
      calendarYear: 0,        // 贡献日历当前显示的年份（0=当前年）
      jumpTo: "",             // 快速跳转输入
      editingId: null,        // 正在编辑的记录 id；null 表示新增
      form: { content: "", points: 1, category: "", ts: "" },
      noteDraft: "",          // 每日感想编辑框内容（随所选日期切换）
      hasNote: false,         // 所选日期是否已有保存的感想
      memos: [],              // 备忘录列表
      memoDraft: "",          // 新增备忘输入框
      mainGoal: "",           // 置顶主目标
      goalDraft: "",          // 主目标编辑框
      goalEditing: false,     // 是否正在编辑主目标
      // ---- 档案 + PIN ----
      profiles: [],           // 档案列表 [{name, has_pin}]
      currentProfile: "",     // 当前档案名
      currentHasPin: false,   // 当前档案是否设了 PIN
      dialog: null,           // 弹窗状态 {mode, tip}；mode: lock/switch/pinSetup/new
      pinInput: "",           // PIN 输入框
      newProfileName: "",     // 新建档案名输入
      dialogError: "",        // 弹窗错误提示
      lastActivity: Date.now(), // 最近一次操作时间（闲置判定）
    };
  },

  computed: {
    // 当前所选天的记录，按时间从新到旧
    sortedEntries() {
      return [...this.entries].sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0));
    },
    todayStr() {
      return toDateStr(new Date());
    },
    // 顶部大标题：今天 / 昨天 / "2026-09-03 周三"
    selectedLabel() {
      if (!this.selectedDay) return "";
      if (this.selectedDay === this.todayStr) return "今天";
      const idx = this.days.findIndex((d) => d.date === this.selectedDay);
      if (idx === 1) return "昨天";
      return `${this.selectedDay} ${weekdayLabel(this.selectedDay)}`;
    },
    selectedIsToday() {
      return this.selectedDay === this.todayStr;
    },
    // 贡献日历网格（表格化布局）
    contrib() {
      return buildContribGrid(this.calendarDays);
    },
    // 当前系统年份
    currentYear() {
      return new Date().getFullYear();
    },
    // 贡献日历显示的年份（默认当前年）
    calYearLabel() {
      return this.calendarYear || this.currentYear;
    },
    // 显示的是过去某年时，才能"往近翻"
    calCanNext() {
      return !!this.calendarYear && this.calendarYear < this.currentYear;
    },
    // 点数线展示文本
    lineText() {
      if (!this.line || this.line.active_days === 0) return "—";
      const b = this.line.baseline;
      return Number.isInteger(b) ? String(b) : b.toFixed(1);
    },
    // 弹窗标题
    dialogTitle() {
      if (!this.dialog) return "";
      switch (this.dialog.mode) {
        case "lock": return "🔒 已锁定";
        case "switch": return `切换到「${this.dialog.target}」`;
        case "pinSetup": return this.currentHasPin ? "修改 PIN" : "设置 PIN";
        case "new": return "新建档案";
        default: return "";
      }
    },
    // 是否处于锁屏态
    isLocked() {
      return !!(this.dialog && this.dialog.mode === "lock");
    },
  },

  mounted() {
    this.init();
    this.watchIdle();
  },

  methods: {
    weekdayLabel,

    // 启动：先取档案信息，判断当前档案是否需 PIN 解锁
    async init() {
      await this.loadProfiles();
      if (this.currentHasPin) {
        this.showLock("此档案已加密，请输入 PIN 解锁");
      } else {
        await this.loadAll();
      }
    },

    // 解锁后（或无需 PIN 时）加载全部业务数据
    async loadAll() {
      try {
        await this.loadDays();
        await this.loadCalendar();
        await this.loadMemos();
        await this.loadLine();
        const today = this.days.find((d) => d.is_today);
        await this.selectDay(today ? today.date : this.todayStr);
      } catch (err) {
        alert("初始化失败：" + err.message);
      }
    },

    // ---------- 档案 + PIN ----------

    async loadProfiles() {
      try {
        const res = await fetch("/api/profiles");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "加载档案失败");
        this.profiles = data.profiles;
        this.currentProfile = data.current;
        const cur = this.profiles.find((p) => p.name === data.current);
        this.currentHasPin = !!(cur && cur.has_pin);
      } catch (err) {
        console.error(err);
      }
    },

    showLock(tip) {
      this.dialog = { mode: "lock", tip };
      this.pinInput = "";
      this.dialogError = "";
    },

    // 下拉切换档案
    async onProfileSelect(ev) {
      const name = ev.target.value;
      if (name === this.currentProfile) return;
      const target = this.profiles.find((p) => p.name === name);
      if (target && target.has_pin) {
        // 有锁：弹窗输入 PIN
        this.dialog = { mode: "switch", tip: `档案「${name}」已设 PIN，请输入后切换`, target: name };
        this.pinInput = "";
        this.dialogError = "";
      } else {
        await this.doSwitch(name, "");
      }
    },

    async doSwitch(name, pin) {
      try {
        const res = await fetch("/api/profiles/switch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, pin }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "切换失败");
        // 切换成功后整体刷新（档案数据全变了）
        location.reload();
      } catch (err) {
        this.dialogError = err.message;
      }
    },

    // 新建档案
    openNewProfile() {
      this.dialog = { mode: "new", tip: "创建一个全新的空档案（数据与其他档案隔离）" };
      this.newProfileName = "";
      this.dialogError = "";
    },

    // 设置 / 修改 PIN
    openPinSetup() {
      this.dialog = { mode: "pinSetup", tip: this.currentHasPin ? "输入新的 4~8 位数字 PIN" : "为当前档案设置 4~8 位数字 PIN" };
      this.pinInput = "";
      this.dialogError = "";
    },

    // 手动立即锁定
    doLock() {
      this.showLock("已锁定，输入 PIN 解锁");
    },

    clearPin() {
      this.dialogError = "";
      this.setPin("");
    },

    // 弹窗确认按钮分派
    async submitDialog() {
      const mode = this.dialog && this.dialog.mode;
      this.dialogError = "";
      if (mode === "lock" || mode === "switch") {
        const pin = this.pinInput.trim();
        if (mode === "switch") {
          await this.doSwitch(this.dialog.target, pin);
        } else {
          try {
            const res = await fetch("/api/unlock", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ pin }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "解锁失败");
            this.dialog = null;
            await this.loadAll();
          } catch (err) {
            this.dialogError = err.message;
            this.pinInput = "";
          }
        }
      } else if (mode === "pinSetup") {
        await this.setPin(this.pinInput.trim());
      } else if (mode === "new") {
        const name = this.newProfileName.trim();
        if (!name) { this.dialogError = "档案名不能为空"; return; }
        try {
          const res = await fetch("/api/profiles", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || "创建失败");
          this.dialog = null;
          // 新建后直接切过去
          await this.doSwitch(name, "");
        } catch (err) {
          this.dialogError = err.message;
        }
      }
    },

    async setPin(pin) {
      try {
        const res = await fetch("/api/pin", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        this.currentHasPin = data.has_pin;
        this.dialog = null;
      } catch (err) {
        this.dialogError = err.message;
      }
    },

    closeDialog() {
      // 锁定态不能直接关
      if (this.dialog && this.dialog.mode === "lock") return;
      this.dialog = null;
      this.dialogError = "";
    },

    // ---------- 闲置自动锁 ----------
    watchIdle() {
      // 用户活动重置时间戳
      const touch = () => { this.lastActivity = Date.now(); };
      ["mousemove", "keydown", "click", "scroll"].forEach((ev) =>
        window.addEventListener(ev, touch, { passive: true })
      );
      // 每 30 秒检查是否闲置超 5 分钟
      window.setInterval(() => {
        if (!this.currentHasPin || this.dialog) return;
        if (Date.now() - this.lastActivity > 5 * 60 * 1000) {
          this.showLock("已闲置 5 分钟，输入 PIN 解锁");
        }
      }, 30 * 1000);
    },

    // 加载点数线（40% 分位、剔极值；最多最近 60 天）
    async loadLine() {
      try {
        const res = await fetch("/api/line");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "加载点数线失败");
        this.line = data;
      } catch (err) {
        console.error(err);
        this.line = null;
      }
    },

    // 切换所选日期：加载记录、感想 + 表单时间预设
    async selectDay(day) {
      this.selectedDay = day;
      if (!this.editingId) {
        this.form.ts = this.defaultTsFor(day);
      }
      await this.loadEntries();
      await this.loadNote();
    },

    // 表单默认时间：今天=现在；其它天=该日 12:00（便于补录）
    defaultTsFor(day) {
      return day === this.todayStr ? toLocalInput(new Date()) : `${day}T12:00`;
    },

    // 拉取日期切换列表（最近14天各天点数）
    async loadDays() {
      const res = await fetch("/api/days");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "加载日期失败");
      this.days = data;
    },

    // 拉取贡献日历数据（按年份窗口）
    async loadCalendar() {
      const url = this.calendarYear ? `/api/calendar?year=${this.calendarYear}` : "/api/calendar";
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "加载贡献日历失败");
      this.calendarDays = data;
    },

    // 往前翻一年（更久远）
    async prevYear() {
      const year = (this.calendarYear || this.currentYear) - 1;
      this.calendarYear = year;
      await this.loadCalendar();
    },

    // 往后翻一年（更接近今天；到当前年后回到最新窗口）
    async nextYear() {
      if (!this.calCanNext) return;
      this.calendarYear += 1;
      if (this.calendarYear >= this.currentYear) this.calendarYear = 0;
      await this.loadCalendar();
    },

    // 回到最近一年
    async goCalendarLatest() {
      this.calendarYear = 0;
      await this.loadCalendar();
    },

    // 贡献日历格子悬浮提示
    cellTitle(c) {
      if (!c.inRange) return "";
      return c.points > 0 ? `${c.date} · ${c.points} 点` : c.date;
    },

    // 加载所选日期的感想
    async loadNote() {
      try {
        const res = await fetch(`/api/notes?day=${this.selectedDay}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "加载感想失败");
        this.noteDraft = data.note || "";
        this.hasNote = !!data.note;
      } catch (err) {
        console.error(err);
        this.noteDraft = "";
        this.hasNote = false;
      }
    },

    // 保存（覆盖）当天整篇感想
    async saveNote() {
      const content = this.noteDraft.trim();
      if (!content) {
        alert("感想不能为空");
        return;
      }
      try {
        const res = await fetch("/api/notes", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ day: this.selectedDay, content }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        this.noteDraft = data.note;
        this.hasNote = true;
      } catch (err) {
        alert("保存失败：" + err.message);
      }
    },

    // 删除当天整篇感想
    async deleteNote() {
      if (!confirm(`删除 ${this.selectedLabel} 的整篇感想？`)) return;
      try {
        const res = await fetch(`/api/notes?day=${this.selectedDay}`, { method: "DELETE" });
        const data = await res.json();
        if (!res.ok && res.status !== 404) throw new Error(data.error || "删除失败");
        this.noteDraft = "";
        this.hasNote = false;
      } catch (err) {
        alert("删除失败：" + err.message);
      }
    },

    // 在感想末尾插入此刻时间，方便追加新段落
    stampNote() {
      const now = new Date();
      const p = (n) => String(n).padStart(2, "0");
      const stamp = `[${p(now.getHours())}:${p(now.getMinutes())}] `;
      this.noteDraft = this.noteDraft.trimEnd()
        ? `${this.noteDraft.trimEnd()}\n\n${stamp}`
        : stamp;
      // 聚焦并把光标移到末尾
      this.$nextTick(() => {
        const ta = document.querySelector(".card textarea");
        if (ta) {
          ta.focus();
          ta.selectionStart = ta.selectionEnd = ta.value.length;
        }
      });
    },

    async loadEntries() {
      try {
        const res = await fetch(`/api/entries?day=${this.selectedDay}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "加载失败");
        this.entries = data.entries;
        this.dayPoints = data.day_points;
      } catch (err) {
        console.error(err);
        alert("加载失败：" + err.message);
      }
    },

    // 日期输入框跳转
    jumpToDay() {
      if (!this.jumpTo) return;
      if (!this.days.some((d) => d.date === this.jumpTo)) {
        this.days.unshift({ date: this.jumpTo, points: null, is_today: false });
      }
      this.selectDay(this.jumpTo);
    },

    goToday() {
      this.jumpTo = "";
      this.selectDay(this.todayStr);
    },

    async submit() {
      const payload = {
        content: this.form.content.trim(),
        points: Number(this.form.points),
        category: this.form.category || null,
      };
      if (!payload.content) return;

      // 设置时间（ISO）：优先用户输入，否则用所选天默认
      const tsInput = this.form.ts || this.defaultTsFor(this.selectedDay);
      const d = new Date(tsInput);
      if (Number.isNaN(d.getTime())) {
        alert("时间格式不正确");
        return;
      }
      payload.ts = d.toISOString();

      const url = this.editingId ? `/api/entries/${this.editingId}` : "/api/entries";
      const method = this.editingId ? "PUT" : "POST";
      try {
        const res = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || (this.editingId ? "保存失败" : "提交失败"));
        this.endEdit();
        // 凌晨4点规则：记录可能归属别的天 → 自动跳到那天展示
        const ownerDay = dayOf(data.ts);
        if (ownerDay !== this.selectedDay) {
          this.selectedDay = ownerDay;
          this.form.ts = this.defaultTsFor(ownerDay);
        }
        await this.refresh();
      } catch (err) {
        alert("提交失败：" + err.message);
      }
    },

    startEdit(entry) {
      this.editingId = entry.id;
      this.form.content = entry.content;
      this.form.points = entry.points;
      this.form.category = entry.category || "";
      this.form.ts = toLocalInput(new Date(entry.ts));
      window.scrollTo({ top: 0, behavior: "smooth" });
    },

    endEdit() {
      this.editingId = null;
      this.form.content = "";
      this.form.points = 1;
      this.form.category = "";
      this.form.ts = this.defaultTsFor(this.selectedDay);
    },

    // 刷新记录 + 日期列表 + 贡献日历 + 当日感想 + 点数线
    async refresh() {
      await Promise.all([this.loadEntries(), this.loadDays(), this.loadCalendar(), this.loadNote(), this.loadLine()]);
    },

    formatTime(iso) {
      return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    },

    // ---------- 备忘录 + 主目标 ----------

    // 加载备忘录与主目标
    async loadMemos() {
      try {
        const res = await fetch("/api/memos");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "加载备忘录失败");
        this.memos = data.memos;
        this.mainGoal = data.main_goal || "";
      } catch (err) {
        console.error(err);
      }
    },

    // 添加一条备忘
    async addMemo() {
      const text = this.memoDraft.trim();
      if (!text) return;
      try {
        const res = await fetch("/api/memos", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "添加失败");
        this.memos.push(data);
        this.memoDraft = "";
      } catch (err) {
        alert("添加失败：" + err.message);
      }
    },

    // 删除一条备忘
    async delMemo(id) {
      try {
        const res = await fetch(`/api/memos/${id}`, { method: "DELETE" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "删除失败");
        this.memos = this.memos.filter((m) => m.id !== id);
      } catch (err) {
        alert("删除失败：" + err.message);
      }
    },

    // 进入主目标编辑模式
    startGoalEdit() {
      this.goalDraft = this.mainGoal;
      this.goalEditing = true;
    },

    cancelGoalEdit() {
      this.goalEditing = false;
      this.goalDraft = "";
    },

    // 保存主目标（允许空 = 清除）
    async saveGoal() {
      try {
        const res = await fetch("/api/main-goal", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ goal: this.goalDraft.trim() }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        this.mainGoal = data.main_goal || "";
        this.goalEditing = false;
      } catch (err) {
        alert("保存失败：" + err.message);
      }
    },

    async del(entry) {
      if (!confirm(`删除这条记录？\n${entry.content}`)) return;
      try {
        const res = await fetch(`/api/entries/${entry.id}`, { method: "DELETE" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "删除失败");
        await this.refresh();
      } catch (err) {
        alert("删除失败：" + err.message);
      }
    },
  },
}).mount("#app");