// PointLog 前端：打卡记录 + 日期切换（M2 · Vue 3）
const { createApp } = Vue;

// ---------- 日期/时间工具 ----------
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

// 按凌晨4点规则，ISO 时刻属于哪天
function dayOf(iso) {
  const shifted = new Date(new Date(iso).getTime() - 4 * 3600 * 1000);
  return toDateStr(shifted);
}

const WEEK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
function weekdayLabel(dstr) {
  return WEEK[fromDateStr(dstr).getDay()];
}

createApp({
  data() {
    return {
      entries: [],            // 当前所选天的记录
      dayPoints: 0,           // 当前所选天的点数
      selectedDay: "",        // 当前所选日期 YYYY-MM-DD
      days: [],               // 日期切换列表（git log 风格）
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
  },

  mounted() {
    this.init();
  },

  methods: {
    weekdayLabel,

    async init() {
      try {
        await this.loadDays();
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

    // 刷新记录 + 日期列表（点数会变）
    async refresh() {
      await Promise.all([this.loadEntries(), this.loadDays()]);
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