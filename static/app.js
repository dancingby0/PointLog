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
      selectedDay: "",        // 当前所选日期 YYYY-MM-DD
      days: [],               // 日期切换列表（git log 风格）
      calendarDays: [],       // 贡献日历原始数据（按年份窗口）
      calendarYear: 0,        // 贡献日历当前显示的年份（0=当前年）
      jumpTo: "",             // 快速跳转输入
      editingId: null,        // 正在编辑的记录 id；null 表示新增
      form: { content: "", points: 1, category: "", ts: "" },
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
  },

  mounted() {
    this.init();
  },

  methods: {
    weekdayLabel,

    async init() {
      try {
        await this.loadDays();
        await this.loadCalendar();
        // 默认选中今天
        const today = this.days.find((d) => d.is_today);
        await this.selectDay(today ? today.date : this.todayStr);
      } catch (err) {
        alert("初始化失败：" + err.message);
      }
    },

    // 切换所选日期：加载记录 + 表单时间预设
    async selectDay(day) {
      this.selectedDay = day;
      if (!this.editingId) {
        this.form.ts = this.defaultTsFor(day);
      }
      await this.loadEntries();
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

    // 刷新记录 + 日期列表 + 贡献日历（点数会变）
    async refresh() {
      await Promise.all([this.loadEntries(), this.loadDays(), this.loadCalendar()]);
    },

    formatTime(iso) {
      return new Date(iso).toLocaleString("zh-CN", { hour12: false });
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